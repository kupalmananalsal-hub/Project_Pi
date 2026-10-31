"""The pre-upgrade backup and the read-only inventory gate, run against a throwaway repo."""
import hashlib
import os
import re
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


def make_production_files(repo):
    """The Pi's untracked state: a live WAL database with rows not yet checkpointed
    (returns its open connection), an older copy, a model and ignored recordings."""
    db = repo / ASSETS[0]
    db.parent.mkdir(parents=True, exist_ok=True)
    live = sqlite3.connect(db)
    live.execute("PRAGMA journal_mode=WAL")
    live.execute("PRAGMA wal_autocheckpoint=0")
    live.execute("CREATE TABLE alerts (id INTEGER PRIMARY KEY, keyword TEXT)")
    live.executemany("INSERT INTO alerts (keyword) VALUES (?)", [("help",)] * 25)
    live.commit()
    (repo / ASSETS[1]).write_bytes(b"older database copy")
    model = repo / ASSETS[2]
    model.parent.mkdir(parents=True, exist_ok=True)
    model.write_bytes(b"\x00tflite model bytes")
    return live


def run_script(name, *args, cwd=None):
    env = dict(os.environ, PYTHON=Path(sys.executable).as_posix())
    return subprocess.run([shutil.which("bash"), (SCRIPTS / name).as_posix(), *args],
                          cwd=cwd, env=env, capture_output=True, text=True, timeout=120)


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
        (self.repo / ".gitignore").write_text(
            "raspberry_pi/backend/alerts.db*\nrecordings/\n*.bin\n", encoding="utf-8")
        self.git("init", "-q")
        self.git("config", "core.autocrlf", "false")
        self.git("add", "-A")
        self.git("commit", "-qm", "base")
        self.target = self.git("rev-parse", "HEAD")
        self.live = make_production_files(self.repo)
        self.addCleanup(self.live.close)
        (self.repo / "recordings").mkdir()
        (self.repo / "recordings" / "take1.wav").write_bytes(b"RIFF")

    def git(self, *args):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                               "-C", str(self.repo), *args], check=True, capture_output=True,
                              text=True).stdout.strip()

    def backup_now(self, manifest=None):
        result = run_script("preupgrade_backup.sh", f"--repo={self.repo.as_posix()}",
                            f"--manifest={(manifest or self.manifest).as_posix()}",
                            f"--backup-dir={self.backup.as_posix()}")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def inventory(self, target=None):
        return run_script("preupgrade_inventory.sh", f"--repo={self.repo.as_posix()}",
                          f"--target={target or self.target}",
                          f"--backup-dir={self.backup.as_posix()}")

    def tree_digest(self):
        return {p.relative_to(self.repo).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(self.repo.rglob("*")) if p.is_file()}

    def target_tracking(self, path, content=b"tracked version"):
        """A commit that tracks `path`, built with plumbing: the worktree is untouched."""
        index = self.repo / ".git" / "target-index"
        env = dict(os.environ, GIT_INDEX_FILE=str(index), GIT_AUTHOR_NAME="t",
                   GIT_AUTHOR_EMAIL="t@example.invalid", GIT_COMMITTER_NAME="t",
                   GIT_COMMITTER_EMAIL="t@example.invalid")

        def git(*args, data=None):
            return subprocess.run(["git", "-C", str(self.repo), *args], env=env, check=True,
                                  input=data, capture_output=True).stdout.decode().strip()
        blob = git("hash-object", "-w", "--stdin", data=content)
        git("read-tree", "HEAD")
        git("update-index", "--add", "--cacheinfo", f"100644,{blob},{path}")
        commit = git("commit-tree", git("write-tree"), "-p", "HEAD", "-m", f"tracks {path}")
        index.unlink()
        return commit

    def test_backup_then_inventory_passes_and_writes_nothing(self):
        self.backup_now()
        before = self.tree_digest()
        result = self.inventory()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS", result.stdout)
        self.assertEqual(self.tree_digest(), before)  # .git included: no index refresh
        self.assertIn("LOCAL    ignored: recordings/", result.stdout)

    def test_live_wal_snapshot_is_complete_and_the_source_is_untouched(self):
        wal = self.repo / (ASSETS[0] + "-wal")
        self.assertTrue(wal.exists())  # rows still only in the WAL
        sources = {p: hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in (self.repo / ASSETS[0], wal)}
        self.backup_now()
        self.assertEqual({p: hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
                         sources)
        snapshot = sqlite3.connect(self.backup / ASSETS[0])
        self.addCleanup(snapshot.close)
        self.assertEqual(snapshot.execute("SELECT COUNT(*) FROM alerts").fetchone()[0], 25)
        self.assertEqual(snapshot.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        # The live database keeps changing; the gate checks the snapshot, not the live hash.
        self.live.execute("INSERT INTO alerts (keyword) VALUES ('later')")
        self.live.commit()
        self.assertEqual(self.inventory().returncode, 0)

    def test_closed_wal_database_is_backed_up_without_writing_it(self):
        self.live.close()  # backend stopped: no -wal/-shm left
        db = self.repo / ASSETS[0]
        before = hashlib.sha256(db.read_bytes()).hexdigest()
        result = self.backup_now()
        self.assertEqual(hashlib.sha256(db.read_bytes()).hexdigest(), before)
        # A read-only WAL reader must create empty companions; they are reported.
        wal = self.repo / (ASSETS[0] + "-wal")
        if wal.exists():
            self.assertEqual(wal.stat().st_size, 0)
            self.assertIn("NOTE     SQLite created empty", result.stdout)

    def test_snapshot_code_never_creates_a_missing_source(self):
        # The race: the database disappears between the existence check and the open.
        code = (SCRIPTS / "preupgrade_backup.sh").read_text(encoding="utf-8")
        snippet = re.search(r"<<'PY'\n(.*?)\nPY\n", code, re.S).group(1)
        missing = self.repo / "raspberry_pi" / "backend" / "gone.db"
        result = subprocess.run([sys.executable, "-", str(missing),
                                 str(self.repo / "snapshot.db")],
                                input=snippet, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(missing.exists())

    def test_ignored_local_model_overwritten_by_a_plain_switch_is_blocked(self):
        # Reproduce the hazard: git switch replaces an ignored local file, no force needed.
        model = self.repo / "models" / "model.bin"
        model.parent.mkdir()
        model.write_bytes(b"CUSTOM-UNTRACKED-MODEL")
        target = self.target_tracking("models/model.bin")
        self.assertEqual(model.read_bytes(), b"CUSTOM-UNTRACKED-MODEL")
        self.backup_now()
        result = self.inventory(target)
        self.assertEqual(result.returncode, 1)
        self.assertIn("models/model.bin: local file at a path", result.stdout)
        self.git("switch", "-q", "--detach", target)
        self.assertEqual(model.read_bytes(), b"tracked version")  # what the gate prevents

    def test_ignored_files_under_a_path_the_target_tracks_as_a_file_are_blocked(self):
        target = self.target_tracking("recordings", b"now a file")
        self.backup_now()
        result = self.inventory(target)
        self.assertEqual(result.returncode, 1)
        self.assertIn("recordings/take1.wav: local file at a path", result.stdout)

    def test_target_commit_that_tracks_a_protected_path_is_blocked(self):
        target = self.target_tracking(ASSETS[2], b"other model")
        self.backup_now()
        result = self.inventory(target)
        self.assertEqual(result.returncode, 1)
        self.assertIn(f"{ASSETS[2]}: local file at a path", result.stdout)

    def test_untracked_file_without_a_collision_is_a_warning_only(self):
        self.backup_now()
        (self.repo / "notes.txt").write_text("local\n", encoding="utf-8")
        result = self.inventory()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("WARN     untracked, not in the manifest: notes.txt", result.stdout)

    def test_provisional_manifest_entries_block_backup_and_inventory(self):
        provisional = self.manifest.with_name("provisional.txt")
        provisional.write_text(f"{ASSETS[0]}\n? {ASSETS[2]}\n", encoding="utf-8", newline="\n")
        result = run_script("preupgrade_backup.sh", f"--repo={self.repo.as_posix()}",
                            f"--manifest={provisional.as_posix()}",
                            f"--backup-dir={self.backup.as_posix()}")
        self.assertEqual(result.returncode, 2)
        self.assertIn("provisional", result.stderr)
        self.assertFalse(self.backup.exists())
        # The repo's own manifest is provisional until the Pi paths are confirmed.
        repo_manifest = SCRIPTS.parent / "config" / "protected_assets.txt"
        self.assertRegex(repo_manifest.read_text(encoding="utf-8"), r"(?m)^\? ")

    def test_missing_changed_or_unbacked_assets_are_blocked(self):
        result = self.inventory()  # no backup yet
        self.assertEqual(result.returncode, 1)
        self.assertIn("not a complete backup", result.stdout)
        self.backup_now()
        (self.repo / ASSETS[2]).write_bytes(b"retrained")
        self.assertIn("changed since the backup", self.inventory().stdout)
        (self.repo / ASSETS[1]).unlink()
        result = self.inventory()
        self.assertEqual(result.returncode, 1)
        self.assertIn("alerts.db.backup: missing", result.stdout)

    def test_tampered_backup_or_manifest_and_tracked_edits_are_blocked(self):
        self.backup_now()
        (self.backup / ASSETS[1]).write_bytes(b"tampered")
        self.assertIn("changed since", self.inventory().stdout)
        (self.backup / ASSETS[1]).write_bytes(b"older database copy")
        manifest = self.backup / "protected_assets.txt"
        original = manifest.read_bytes()
        manifest.write_bytes(original.replace(ASSETS[2].encode() + b"\n", b""))
        self.assertIn("changed since", self.inventory().stdout)
        manifest.write_bytes(original)
        (self.repo / "README").write_text("edited on the Pi\n", encoding="utf-8")
        result = self.inventory()
        self.assertEqual(result.returncode, 1)
        self.assertIn("tracked files have local edits", result.stdout)

    def test_backup_never_reuses_an_existing_directory(self):
        self.backup.mkdir()
        result = run_script("preupgrade_backup.sh", f"--repo={self.repo.as_posix()}",
                            f"--manifest={self.manifest.as_posix()}",
                            f"--backup-dir={self.backup.as_posix()}")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(list(self.backup.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
