"""The pre-upgrade backup and the read-only inventory gate, run against a throwaway repo."""
import hashlib
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test.test_install_runtime import bash_usable

SCRIPTS = Path(__file__).resolve().parents[1] / "raspberry_pi" / "scripts"
ASSETS = ["raspberry_pi/backend/alerts.db", "raspberry_pi/backend/alerts.db.backup",
          "dataset/thermal/models/thermal_human_shape.tflite"]


@unittest.skipUnless(bash_usable(), "needs bash with GNU coreutils")
class PreupgradeInventoryTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        base = Path(temp.name)
        self.repo = base / "Project_Pi"
        self.backup = base / "backup"
        self.manifest = base / "protected_assets.txt"
        self.manifest.write_text("# test manifest\n" + "".join(a + "\n" for a in ASSETS),
                                 encoding="utf-8", newline="\n")
        (self.repo / "raspberry_pi").mkdir(parents=True)
        (self.repo / "README").write_text("tracked\n", encoding="utf-8")
        (self.repo / ".gitignore").write_text("raspberry_pi/backend/alerts.db*\nrecordings/\n",
                                              encoding="utf-8")
        self.git("init", "-q")
        self.git("config", "core.autocrlf", "false")
        self.git("add", "-A")
        self.git("commit", "-qm", "base")
        self.target = self.git("rev-parse", "HEAD")
        # Production state: a live WAL database with rows not yet checkpointed, and files.
        db = self.repo / ASSETS[0]
        db.parent.mkdir(parents=True)
        self.live = sqlite3.connect(db)
        self.addCleanup(self.live.close)
        self.live.execute("PRAGMA journal_mode=WAL")
        self.live.execute("PRAGMA wal_autocheckpoint=0")
        self.live.execute("CREATE TABLE alerts (id INTEGER PRIMARY KEY, keyword TEXT)")
        self.live.executemany("INSERT INTO alerts (keyword) VALUES (?)", [("help",)] * 25)
        self.live.commit()
        (self.repo / ASSETS[1]).write_bytes(b"older database copy")
        model = self.repo / ASSETS[2]
        model.parent.mkdir(parents=True)
        model.write_bytes(b"\x00tflite model bytes")
        (self.repo / "recordings").mkdir()
        (self.repo / "recordings" / "take1.wav").write_bytes(b"RIFF")

    def git(self, *args):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                               "-C", str(self.repo), *args], check=True, capture_output=True,
                              text=True).stdout.strip()

    def run_script(self, name, *args):
        env = dict(os.environ, PROJECT_PI_PROTECTED_ASSETS=self.manifest.as_posix(),
                   PYTHON=Path(sys.executable).as_posix())
        return subprocess.run([shutil.which("bash"), (SCRIPTS / name).as_posix(), *args],
                              cwd=self.repo, env=env, capture_output=True, text=True, timeout=60)

    def backup_now(self):
        result = self.run_script("preupgrade_backup.sh", f"--backup-dir={self.backup.as_posix()}")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def inventory(self, target=None):
        return self.run_script("preupgrade_inventory.sh", f"--target={target or self.target}",
                               f"--backup-dir={self.backup.as_posix()}")

    def tree_digest(self):
        return {p.relative_to(self.repo).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(self.repo.rglob("*")) if p.is_file()}

    def test_backup_then_inventory_passes_and_writes_nothing(self):
        self.backup_now()
        before = self.tree_digest()
        result = self.inventory()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS", result.stdout)
        self.assertEqual(self.tree_digest(), before)
        # Other local files are reported, never blocking.
        self.assertIn("LOCAL    ignored: recordings/", result.stdout)

    def test_live_wal_database_snapshot_is_consistent_and_complete(self):
        self.assertTrue((self.repo / (ASSETS[0] + "-wal")).exists())  # rows still in the WAL
        self.backup_now()
        snapshot = sqlite3.connect(self.backup / ASSETS[0])
        self.addCleanup(snapshot.close)
        self.assertEqual(snapshot.execute("SELECT COUNT(*) FROM alerts").fetchone()[0], 25)
        self.assertEqual(snapshot.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        # The live database keeps changing; the gate still passes on the snapshot.
        self.live.execute("INSERT INTO alerts (keyword) VALUES ('later')")
        self.live.commit()
        self.assertEqual(self.inventory().returncode, 0)

    def test_untracked_file_outside_the_manifest_is_a_warning_only(self):
        self.backup_now()
        (self.repo / "notes.txt").write_text("local\n", encoding="utf-8")
        result = self.inventory()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("WARN     untracked, not in the manifest: notes.txt", result.stdout)

    def test_target_commit_that_tracks_a_protected_path_is_blocked(self):
        self.backup_now()
        self.git("checkout", "-q", "-b", "upgrade")
        (self.repo / "dataset/thermal/models/thermal_human_shape.tflite").write_bytes(b"other")
        self.git("add", "-f", ASSETS[2])
        self.git("commit", "-qm", "tracks the model")
        target = self.git("rev-parse", "HEAD")
        self.git("checkout", "-q", "-")  # (this checkout removes it: the hazard itself)
        (self.repo / ASSETS[2]).parent.mkdir(parents=True, exist_ok=True)
        (self.repo / ASSETS[2]).write_bytes(b"\x00tflite model bytes")
        result = self.inventory(target)
        self.assertEqual(result.returncode, 1)
        self.assertIn("tracked by the target commit", result.stdout)

    def test_missing_changed_or_unbacked_assets_are_blocked(self):
        result = self.inventory()  # no backup yet
        self.assertEqual(result.returncode, 1)
        self.assertIn("no recorded backup", result.stdout)
        self.backup_now()
        (self.repo / ASSETS[2]).write_bytes(b"retrained")
        self.assertIn("changed since the backup", self.inventory().stdout)
        (self.repo / ASSETS[1]).unlink()
        result = self.inventory()
        self.assertEqual(result.returncode, 1)
        self.assertIn("alerts.db.backup: missing", result.stdout)

    def test_tampered_backup_and_tracked_edits_are_blocked(self):
        self.backup_now()
        (self.backup / ASSETS[1]).write_bytes(b"tampered")
        self.assertIn("a backup copy changed", self.inventory().stdout)
        (self.backup / ASSETS[1]).write_bytes(b"older database copy")
        (self.repo / "README").write_text("edited on the Pi\n", encoding="utf-8")
        result = self.inventory()
        self.assertEqual(result.returncode, 1)
        self.assertIn("tracked files have local edits", result.stdout)

    def test_backup_never_reuses_an_existing_directory(self):
        self.backup.mkdir()
        result = self.run_script("preupgrade_backup.sh", f"--backup-dir={self.backup.as_posix()}")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(list(self.backup.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
