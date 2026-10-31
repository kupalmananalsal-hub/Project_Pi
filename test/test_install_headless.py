import re
import shutil
import subprocess
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INSTALLER = PROJECT_ROOT / "raspberry_pi" / "scripts" / "install_headless.sh"
UPGRADE_DOC = PROJECT_ROOT / "docs" / "m1_m2_upgrade_and_rollback.md"


class InstallHeadlessTest(unittest.TestCase):
    def setUp(self):
        self.text = INSTALLER.read_text(encoding="utf-8")

    @unittest.skipUnless(shutil.which("bash"), "bash not available")
    def test_installer_parses(self):
        subprocess.run(["bash", "-n", str(INSTALLER)], check=True)

    def test_legacy_vosk_unit_is_stopped_before_kws_restart(self):
        stop = self.text.index("systemctl disable --now kws-alert-vosk.service")
        guard = self.text.index("systemctl is-active --quiet kws-alert-vosk.service")
        restart = re.search(r"^systemctl restart .*kws-alert\.service", self.text, re.M).start()
        self.assertLess(stop, guard)
        self.assertLess(guard, restart)
        # A failed stop must abort the install, not be swallowed.
        stop_line = self.text[stop:self.text.index("\n", stop)]
        self.assertNotIn("|| true", stop_line)
        self.assertNotIn("2>/dev/null", stop_line)
        self.assertIn("exit 1", self.text[guard:restart])
        self.assertIn("set -euo pipefail", self.text)

    def test_upgrade_doc_keeps_a_branch_for_refresh(self):
        step2 = UPGRADE_DOC.read_text(encoding="utf-8").split("## 2.", 1)[1].split("## 3.", 1)[0]
        self.assertIn("git switch main", step2)
        self.assertIn("git merge --ff-only <REVIEWED_COMMIT>", step2)
        self.assertNotIn("git checkout <REVIEWED_COMMIT>", step2)
        self.assertNotRegex(step2, r"git reset|--force|-f\b")


if __name__ == "__main__":
    unittest.main()
