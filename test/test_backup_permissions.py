"""Run on Linux to verify actual permissions, including under umask 000."""
from pathlib import Path
import os
import sqlite3
import stat
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'raspberry_pi/scripts/backup_alerts.py'


@unittest.skipUnless(sys.platform.startswith('linux'), 'Linux filesystem permission verification requires Linux')
class BackupPermissionsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source.db'
        db = sqlite3.connect(self.source)
        db.execute('CREATE TABLE evidence(value TEXT)')
        db.execute("INSERT INTO evidence VALUES('retained')")
        db.commit()
        db.close()

    def run_backup(self, target):
        return subprocess.run([sys.executable, str(SCRIPT), str(self.source), str(target)], capture_output=True, text=True, timeout=10, umask=0)

    def test_owner_only_under_permissive_umask_and_no_overwrite(self):
        target = self.root / 'backup.db'
        result = self.run_backup(target)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
        self.assertEqual(target.stat().st_uid, os.geteuid())
        before = target.read_bytes()
        self.assertNotEqual(self.run_backup(target).returncode, 0)
        self.assertEqual(target.read_bytes(), before)
        db = sqlite3.connect(target)
        try:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(db.execute('SELECT value FROM evidence').fetchone()[0], 'retained')
        finally:
            db.close()

    def test_shared_directory_rejected_before_creation(self):
        shared = self.root / 'shared'
        shared.mkdir(mode=0o700)
        shared.chmod(0o755)
        target = shared / 'backup.db'
        result = self.run_backup(target)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('owner-only', result.stderr)
        self.assertFalse(target.exists())

    def test_symlink_destination_does_not_overwrite_target(self):
        link = self.root / 'backup.db'
        link.symlink_to(self.source)
        before = self.source.read_bytes()
        self.assertNotEqual(self.run_backup(link).returncode, 0)
        self.assertEqual(self.source.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
