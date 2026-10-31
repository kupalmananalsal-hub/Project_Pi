"""The upgrade runbook's own guard blocks and preupgrade_switch.sh, run in disposable repos.

The blocks are extracted from docs/m1_m2_upgrade_and_rollback.md (<!-- runbook:... -->),
so the tested procedure is the documented one. Nothing here touches a real Pi.
"""
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

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = PROJECT_ROOT / "docs" / "m1_m2_upgrade_and_rollback.md"
TOOLS = ["raspberry_pi/scripts/preupgrade_backup.sh", "raspberry_pi/scripts/preupgrade_inventory.sh",
         "raspberry_pi/scripts/preupgrade_switch.sh", "raspberry_pi/config/protected_assets.txt"]
PROTECTED = ["raspberry_pi/backend/alerts.db", "raspberry_pi/backend/alerts.db.backup",
             "dataset/thermal/models/thermal_human_shape.tflite",
             "dataset/thermal/models/thermal_human_shape_labels.json"]


def runbook_block(name):
    text = RUNBOOK.read_text(encoding="utf-8")
    return re.search(rf"<!-- runbook:{re.escape(name)} -->\n```bash\n(.*?)```", text, re.S).group(1)


@unittest.skipUnless(bash_usable(), "needs bash with GNU coreutils")
class UpgradeProcedureTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        origin = self.base / "origin.git"
        dev = self.base / "dev"
        self.pi = self.base / "Project_Pi"
        self.run_git(self.base, "init", "-q", "--bare", "-b", "main", str(origin))
        self.run_git(self.base, "clone", "-q", str(origin), str(dev))
        # The deployed baseline: no preflight tools; the database and the custom model
        # name are ignored there.
        (dev / ".gitignore").write_text("raspberry_pi/backend/alerts.db*\nlocal-model.bin\n",
                                        encoding="utf-8")
        (dev / "README").write_text("baseline\n", encoding="utf-8")
        self.run_git(dev, "add", "-A")
        self.run_git(dev, "commit", "-qm", "deployed baseline")
        self.run_git(dev, "push", "-q", "origin", "HEAD:main")
        self.run_git(self.base, "clone", "-q", str(origin), str(self.pi))
        self.baseline = self.run_git(self.pi, "rev-parse", "HEAD")
        # The reviewed commit on origin/main brings the real preflight tools.
        for path in TOOLS:
            (dev / path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(PROJECT_ROOT / path, dev / path)
        self.run_git(dev, "add", "-A")
        self.run_git(dev, "commit", "-qm", "reviewed upgrade")
        self.reviewed = self.run_git(dev, "rev-parse", "HEAD")
        self.run_git(dev, "push", "-q", "origin", "HEAD:main")
        # An unmerged PR-branch commit and a reviewed commit that tracks a local file.
        self.run_git(dev, "checkout", "-q", "-b", "pr")
        (dev / "pr.txt").write_text("unmerged\n", encoding="utf-8")
        self.run_git(dev, "add", "-A")
        self.run_git(dev, "commit", "-qm", "unmerged PR")
        self.unmerged = self.run_git(dev, "rev-parse", "HEAD")
        self.run_git(dev, "push", "-q", "origin", "pr")
        self.dev = dev
        # The Pi's untracked production files.
        (self.pi / PROTECTED[0]).parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.pi / PROTECTED[0])
        db.execute("CREATE TABLE alerts (id INTEGER PRIMARY KEY)")
        db.commit()
        db.close()
        for path in PROTECTED[1:]:
            (self.pi / path).parent.mkdir(parents=True, exist_ok=True)
            (self.pi / path).write_bytes(b"production " + path.encode())

    @staticmethod
    def run_git(cwd, *args):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                               "-c", "init.defaultBranch=main", *args], cwd=cwd, check=True,
                              capture_output=True, text=True).stdout.strip()

    def run_block(self, name, reviewed=None):
        env = dict(os.environ, PI_REPO=self.pi.as_posix(), REVIEWED=reviewed or self.reviewed,
                   T=(self.base / "preflight").as_posix(), B=(self.base / "backup").as_posix(),
                   PYTHON=Path(sys.executable).as_posix(),
                   GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")
        return subprocess.run([shutil.which("bash"), "-c", runbook_block(name)], env=env,
                              capture_output=True, text=True, timeout=120)

    def head(self):
        return self.run_git(self.pi, "rev-parse", "HEAD")

    def run_all(self):
        for name in ("0a", "0b", "0c", "2"):
            result = self.run_block(name)
            if result.returncode != 0:
                return name, result
        return None, result

    def test_documented_procedure_switches_only_after_every_check(self):
        failed, result = self.run_all()
        self.assertIsNone(failed, result.stdout + result.stderr)
        self.assertEqual(self.head(), self.reviewed)
        self.assertEqual(self.run_git(self.pi, "rev-parse", "--abbrev-ref", "main@{upstream}"),
                         "origin/main")
        self.assertEqual((self.base / "backup" / "PRESWITCH_VERIFIED").read_text().strip(),
                         self.reviewed)
        for path in PROTECTED[1:]:
            self.assertEqual((self.pi / path).read_bytes(), b"production " + path.encode())

    def test_target_not_on_origin_main_stops_before_anything(self):
        self.run_git(self.pi, "fetch", "-q", "origin", "pr")
        result = self.run_block("0a", reviewed=self.unmerged)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("STOP:", result.stderr)
        self.assertFalse(any((self.base / "preflight").rglob("*.sh")))
        self.assertEqual(self.head(), self.baseline)

    def test_unconfirmable_model_path_stops(self):
        self.assertEqual(self.run_block("0a").returncode, 0)
        (self.pi / PROTECTED[2]).unlink()
        result = self.run_block("0b")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(f"STOP: {PROTECTED[2]} not found", result.stderr)
        self.assertNotEqual(self.run_block("0c").returncode, 0)  # backup refuses too
        self.assertNotEqual(self.run_block("2").returncode, 0)
        self.assertEqual(self.head(), self.baseline)

    def test_tampered_tool_stops_the_switch(self):
        for name in ("0a", "0b", "0c"):
            self.assertEqual(self.run_block(name).returncode, 0)
        tool = self.base / "preflight" / "raspberry_pi/scripts/preupgrade_inventory.sh"
        tool.write_text(tool.read_text(encoding="utf-8").replace("exit 1", "exit 0"),
                        encoding="utf-8", newline="\n")
        result = self.run_block("2")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("differs from the reviewed preupgrade_inventory.sh", result.stderr)
        self.assertEqual(self.head(), self.baseline)
        self.assertFalse((self.base / "backup" / "PRESWITCH_VERIFIED").exists())

    def test_inventory_failure_stops_before_git_overwrites_a_local_file(self):
        # The reviewed commit tracks a path that is an ignored custom file on the Pi.
        self.run_git(self.dev, "checkout", "-q", "main")
        (self.dev / "local-model.bin").write_bytes(b"shipped")
        self.run_git(self.dev, "add", "-f", "local-model.bin")
        self.run_git(self.dev, "commit", "-qm", "tracks local-model.bin")
        self.reviewed = self.run_git(self.dev, "rev-parse", "HEAD")
        self.run_git(self.dev, "push", "-q", "origin", "HEAD:main")
        (self.pi / "local-model.bin").write_bytes(b"CUSTOM-UNTRACKED-MODEL")
        failed, result = self.run_all()
        self.assertEqual(failed, "0c", result.stdout + result.stderr)
        self.assertIn("local-model.bin: local file at a path", result.stdout)
        # Even if the operator ignores the failed block, the switch refuses on its own.
        result = self.run_block("2")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("STOP: the pre-upgrade inventory did not pass", result.stderr)
        self.assertEqual(self.head(), self.baseline)
        self.assertEqual((self.pi / "local-model.bin").read_bytes(), b"CUSTOM-UNTRACKED-MODEL")

    def test_diverged_local_main_is_never_reset(self):
        (self.pi / "local.txt").write_text("pi-only commit\n", encoding="utf-8")
        self.run_git(self.pi, "add", "local.txt")
        self.run_git(self.pi, "commit", "-qm", "pi-only")
        local = self.head()
        failed, result = self.run_all()
        self.assertEqual(failed, "2", result.stdout + result.stderr)
        self.assertEqual(self.head(), local)
        self.assertFalse((self.base / "backup" / "PRESWITCH_VERIFIED").exists())


@unittest.skipUnless(bash_usable(), "needs bash with GNU coreutils")
class TokenRotationTest(unittest.TestCase):
    SCRIPT = PROJECT_ROOT / "raspberry_pi" / "scripts" / "rotate_api_token.sh"

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        base = Path(temp.name)
        self.root = base / "root"
        self.conf = self.root / "etc/project-pi/backend.env"
        self.conf.parent.mkdir(parents=True)
        stubs = base / "stubs"
        stubs.mkdir()
        stub = stubs / "id"
        stub.write_text('#!/usr/bin/env bash\n[[ "$1" == -u ]] && { echo 0; exit 0; }\n'
                        'exec /usr/bin/id "$@"\n', encoding="utf-8", newline="\n")
        stub.chmod(0o755)
        self.env = dict(os.environ, PROJECT_PI_INSTALL_ROOT=self.root.as_posix(),
                        PATH=f"{stubs.as_posix()}:/usr/bin:/bin:{os.environ.get('PATH', '')}")

    def rotate(self):
        return subprocess.run([shutil.which("bash"), self.SCRIPT.as_posix()], env=self.env,
                              capture_output=True, text=True, timeout=60)

    def test_rotation_replaces_only_the_token_and_never_shows_it(self):
        old = "old-token-0123456789abcdef"
        self.conf.write_text("# keep me\nPROJECT_PI_API_AUTH=required\n"
                             f"PROJECT_PI_API_TOKEN={old}\nPROJECT_PI_CORS_ORIGINS=x\n",
                             encoding="utf-8", newline="\n")
        result = self.rotate()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        lines = self.conf.read_text(encoding="utf-8").splitlines()
        token = next(l for l in lines if l.startswith("PROJECT_PI_API_TOKEN="))
        token = token.split("=", 1)[1]
        self.assertRegex(token, r"^[0-9a-f]{64}$")
        self.assertNotEqual(token, old)
        self.assertEqual([l for l in lines if not l.startswith("PROJECT_PI_API_TOKEN=")],
                         ["# keep me", "PROJECT_PI_API_AUTH=required", "PROJECT_PI_CORS_ORIGINS=x"])
        self.assertNotIn(token, result.stdout + result.stderr)
        self.assertEqual(sorted(p.name for p in self.conf.parent.iterdir()), ["backend.env"])
        if os.name != "nt":
            self.assertEqual(self.conf.stat().st_mode & 0o777, 0o600)

    def test_rotation_refuses_outside_required_mode(self):
        text = "PROJECT_PI_API_AUTH=open\nPROJECT_PI_OPEN_MODE_ACK=isolated-network-verified\n"
        self.conf.write_text(text, encoding="utf-8", newline="\n")
        result = self.rotate()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.conf.read_text(encoding="utf-8"), text)

    def test_token_only_ever_reaches_shell_builtins(self):
        # External commands show their arguments to every local user; printf is a builtin.
        for line in self.SCRIPT.read_text(encoding="utf-8").splitlines():
            if "${token}" in line or "$token" in line:
                self.assertRegex(line.strip(), r"^printf ", line)


if __name__ == "__main__":
    unittest.main()
