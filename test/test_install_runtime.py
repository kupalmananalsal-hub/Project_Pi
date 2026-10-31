"""Runs the real installer and boot script under bash against a scratch root.

systemctl, visudo, id and the network tools are mocked; systemctl keeps unit state in
files so stop/mask/enable are observable. Linux-compatible; also runs under Git Bash.
"""
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INSTALLER = PROJECT_ROOT / "raspberry_pi" / "scripts" / "install_headless.sh"
BOOT = PROJECT_ROOT / "raspberry_pi" / "scripts" / "headless_boot.sh"
LOCKS = PROJECT_ROOT / "raspberry_pi" / "requirements"

SYSTEMCTL = r'''#!/usr/bin/env bash
# Mock systemctl: unit state lives in $STUB_STATE/{active,enabled,masked}.
echo "$*" >> "$STUB_STATE/log"
IFS='|' read -ra fails <<< "${STUB_FAIL:-}"
for f in "${fails[@]}"; do [[ -n "$f" && "$*" == ${f}* ]] && exit 1; done
# STUB_NOOP: report success but change nothing (a unit that "starts" and dies at once).
IFS='|' read -ra noops <<< "${STUB_NOOP:-}"
for n in "${noops[@]}"; do [[ -n "$n" && "$*" == ${n}* ]] && exit 0; done
has() { grep -qxF "$2" "$STUB_STATE/$1" 2>/dev/null; }
add() { has "$1" "$2" || echo "$2" >> "$STUB_STATE/$1"; }
del() { touch "$STUB_STATE/$1"; grep -vxF "$2" "$STUB_STATE/$1" > "$STUB_STATE/$1.tmp" || true; mv "$STUB_STATE/$1.tmp" "$STUB_STATE/$1"; }
cmd="$1"; shift
[[ "${1:-}" == --quiet ]] && shift
case "$cmd" in
  cat) f="$PROJECT_PI_INSTALL_ROOT/etc/systemd/system/$1"; [[ -f "$f" ]] && cat "$f"; exit 0 ;;
  is-active) has active "$1" && exit 0; exit 3 ;;
  is-enabled) has masked "$1" && { echo masked; exit 1; }
              has enabled "$1" && { echo enabled; exit 0; }; echo disabled; exit 1 ;;
  stop) del active "$1" ;;
  start|restart) for u in "$@"; do add active "$u"; done ;;
  enable) for u in "$@"; do add enabled "$u"; done ;;
  disable) for u in "$@"; do del enabled "$u"; done ;;
  mask) add masked "$1" ;;
  unmask) del masked "$1" ;;
esac
exit 0
'''


def bash_usable():
    bash = shutil.which("bash")
    if not bash:
        return False
    try:
        out = subprocess.run([bash, "-c", "stat -c %a . && install --version"],
                             capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return False
    return out.returncode == 0


@unittest.skipUnless(bash_usable(), "needs bash with GNU coreutils")
class InstallerRuntimeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.root = base / "root"
        self.state = base / "state"
        self.stubs = base / "stubs"
        for path in (self.root, self.state, self.stubs):
            path.mkdir()
        self.write_stub("systemctl", SYSTEMCTL)
        self.write_stub("visudo", "#!/usr/bin/env bash\nexit 0\n")
        self.write_stub("id", '#!/usr/bin/env bash\n[[ "$1" == -u ]] && { echo 0; exit 0; }\n'
                              'exec /usr/bin/id "$@"\n')
        if os.name == "nt":
            # NTFS (Git Bash) cannot chmod a directory to 0700; Linux runs install unshimmed.
            self.write_stub("install", '#!/usr/bin/env bash\nargs=()\nfor a in "$@"; do\n'
                                       '  [[ "$a" == 0700 ]] && a=0755\n  args+=("$a")\ndone\n'
                                       'exec /usr/bin/install "${args[@]}"\n')
        for venv, lock in (("kws-env", "kws-env.lock.txt"),
                           ("thermal-env-sys", "thermal-env-sys.lock.txt")):
            self.fake_venv(venv, f'cat "{(LOCKS / lock).as_posix()}"')
        # A throwaway checkout with two commits, so code rollback never touches this repo.
        self.repo = base / "Project_Pi"
        for part in ("scripts", "systemd", "sudoers", "requirements"):
            shutil.copytree(PROJECT_ROOT / "raspberry_pi" / part, self.repo / "raspberry_pi" / part)
        self.git("init", "-q")
        self.git("config", "core.autocrlf", "false")
        self.git("add", "-A")
        self.git("commit", "-qm", "before upgrade")
        self.before_sha = self.git("rev-parse", "HEAD")
        (self.repo / "VERSION").write_text("new\n", encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-qm", "the upgrade")
        self.after_sha = self.git("rev-parse", "HEAD")

    def git(self, *args):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                               "-C", str(self.repo), *args], check=True, capture_output=True,
                              text=True).stdout.strip()

    def write_stub(self, name, body, directory=None):
        path = (directory or self.stubs) / name
        path.write_text(body, encoding="utf-8", newline="\n")
        path.chmod(0o755)

    def fake_venv(self, name, freeze_command):
        bin_dir = self.root / "home" / "thesis" / name / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        self.write_stub("python", f"#!/usr/bin/env bash\n{freeze_command}\n", bin_dir)

    def put(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        return path

    def set_state(self, name, *units):
        (self.state / name).write_text("".join(u + "\n" for u in units), encoding="utf-8",
                                       newline="\n")

    def state_of(self, name):
        path = self.state / name
        return set(path.read_text(encoding="utf-8").split()) if path.exists() else set()

    def calls(self):
        log = self.state / "log"
        return log.read_text(encoding="utf-8").splitlines() if log.exists() else []

    def run_installer(self, *args, fail=None, noop=None, rollback_commit="before"):
        if "--apply" in args and rollback_commit:
            sha = self.before_sha if rollback_commit == "before" else rollback_commit
            args = (*args, f"--rollback-commit={sha}")
        env = dict(os.environ,
                   PATH=f"{self.stubs.as_posix()}{os.pathsep}{os.environ.get('PATH', '')}",
                   PROJECT_PI_INSTALL_ROOT=self.root.as_posix(),
                   PROJECT_PI_REPO=self.repo.as_posix(),
                   STUB_STATE=self.state.as_posix())
        env.pop("STUB_FAIL", None)
        env.pop("STUB_NOOP", None)
        if fail:
            env["STUB_FAIL"] = fail
        if noop:
            env["STUB_NOOP"] = noop
        if os.name == "nt":  # Git Bash resolves stubs only via its own PATH syntax
            env["PATH"] = f"{self.stubs.as_posix()}:/usr/bin:/bin:{os.environ.get('PATH', '')}"
        return subprocess.run([shutil.which("bash"), INSTALLER.as_posix(), *args], env=env,
                              capture_output=True, text=True, timeout=120)

    def files(self):
        return sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob("*")
                      if p.is_file() and "home/thesis" not in p.as_posix())

    def test_dry_run_writes_nothing(self):
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Dry run: nothing was changed", result.stdout)
        self.assertIn("NEW        ", result.stdout)
        self.assertEqual(self.files(), [])
        self.assertFalse(any(c.split()[0] in {"enable", "disable", "mask", "stop", "restart",
                                              "daemon-reload"} for c in self.calls()))

    def test_apply_refuses_package_drift_before_any_write(self):
        self.fake_venv("kws-env", "echo onnxruntime==9.9.9")
        result = self.run_installer("--apply")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Refusing --apply", result.stderr)
        self.assertEqual(self.files(), [])

    def test_fresh_apply_installs_masks_legacy_and_restarts_nothing(self):
        result = self.run_installer("--apply")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        unit = self.root / "etc/systemd/system/kws-alert.service"
        self.assertEqual(unit.read_bytes(),
                         (self.repo / "raspberry_pi/systemd/kws-alert.service").read_bytes())
        self.assertEqual(self.git("rev-parse", "HEAD"), self.after_sha)  # success: code untouched
        self.assertIn("PROJECT_PI_API_AUTH=open",
                      (self.root / "etc/project-pi/backend.env").read_text(encoding="utf-8"))
        dropin = (self.root / "etc/systemd/system/thermal-backend.service.d/10-local.conf"
                  ).read_text(encoding="utf-8")
        self.assertIn("Environment=THERMAL_REFRESH_HZ=4", dropin)
        self.assertIn("kws-alert-vosk.service", self.state_of("masked"))
        self.assertIn("kws-alert.service", self.state_of("enabled"))
        self.assertFalse(any(c.startswith("restart") for c in self.calls()))
        self.assertFalse((self.root / "etc/project-pi/hotspot.env").exists())

    def legacy_pi(self):
        """The deployed Pi's shape: old units, a local drop-in, a running legacy KWS."""
        self.put("etc/systemd/system/thermal-backend.service",
                 '[Service]\nEnvironment="LGPIO_CHIP=11"\n')
        self.put("etc/systemd/system/kws-alert-vosk.service", "[Service]\nExecStart=/bin/true\n")
        self.put("etc/project-pi/backend.env", "PROJECT_PI_API_AUTH=open\n# mine\n")
        self.put("etc/project-pi/hotspot.env", "PROJECT_PI_HOTSPOT_SSID=keep-me\n")
        self.set_state("active", "kws-alert-vosk.service", "thermal-backend.service")
        self.set_state("enabled", "kws-alert-vosk.service")

    def test_apply_backs_up_replaced_files_and_keeps_local_config(self):
        self.legacy_pi()
        self.put("etc/systemd/system/thermal-backend.service.d/10-local.conf", "LOCAL\n")
        result = self.run_installer("--apply")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        backups = list((self.root / "var/lib/project-pi/install-backups").glob(
            "*/etc/systemd/system/thermal-backend.service"))
        self.assertEqual(len(backups), 1)
        self.assertIn("LGPIO_CHIP=11", backups[0].read_text(encoding="utf-8"))
        self.assertEqual((self.root / "etc/systemd/system/thermal-backend.service.d/10-local.conf"
                          ).read_text(encoding="utf-8"), "LOCAL\n")
        self.assertIn("# mine", (self.root / "etc/project-pi/backend.env").read_text(encoding="utf-8"))
        self.assertIn("keep-me", (self.root / "etc/project-pi/hotspot.env").read_text(encoding="utf-8"))
        # The scratch files are not root-owned: reported, not silently accepted or changed.
        self.assertIn("hotspot.env is", result.stderr)
        self.assertIn("expected root-owned 600", result.stderr)
        # Legacy owner stopped before the mask; its unit file kept in the backup.
        self.assertNotIn("kws-alert-vosk.service", self.state_of("active"))
        self.assertIn("kws-alert-vosk.service", self.state_of("masked"))
        self.assertFalse((self.root / "etc/systemd/system/kws-alert-vosk.service").exists())
        calls = self.calls()
        self.assertLess(calls.index("stop kws-alert-vosk.service"),
                        calls.index("mask kws-alert-vosk.service"))

    def test_seeded_dropin_preserves_installed_device_settings(self):
        self.legacy_pi()
        result = self.run_installer("--apply")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        dropin = (self.root / "etc/systemd/system/thermal-backend.service.d/10-local.conf"
                  ).read_text(encoding="utf-8")
        self.assertIn('Environment="LGPIO_CHIP=11"', dropin)
        self.assertIn("Environment=MLX90640_VARIANT=unverified", dropin)

    def assert_code_untouched_and_reported(self, result):
        # The installer never changes the checkout; it reports both commits instead.
        self.assertEqual(self.git("rev-parse", "HEAD"), self.after_sha)
        self.assertEqual(self.git("symbolic-ref", "--short", "HEAD"),
                         self.git("rev-parse", "--abbrev-ref", "HEAD"))  # still on its branch
        self.assertIn(f"HEAD is {self.after_sha}", result.stderr)
        self.assertIn(f"recorded rollback commit {self.before_sha}", result.stderr)
        self.assertIn("CODE MISMATCH", result.stderr)

    def assert_rolled_back(self, result):
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("ROLLBACK VERIFIED", result.stderr)
        self.assertNotIn("ROLLBACK INCOMPLETE", result.stderr)
        self.assertIn("LGPIO_CHIP=11", (self.root / "etc/systemd/system/thermal-backend.service"
                                        ).read_text(encoding="utf-8"))
        for created in ("etc/systemd/system/kws-alert.service", "usr/local/sbin/project-pi-boot",
                        "etc/sudoers.d/project-pi-thesis",
                        "etc/systemd/system/thermal-backend.service.d/10-local.conf"):
            self.assertFalse((self.root / created).exists(), created)
        self.assertTrue((self.root / "etc/systemd/system/kws-alert-vosk.service").exists())
        self.assertNotIn("kws-alert-vosk.service", self.state_of("masked"))
        self.assertIn("kws-alert-vosk.service", self.state_of("enabled"))
        self.assertIn("kws-alert-vosk.service", self.state_of("active"))
        self.assertIn("# mine", (self.root / "etc/project-pi/backend.env").read_text(encoding="utf-8"))
        self.assert_code_untouched_and_reported(result)

    def test_apply_requires_a_valid_rollback_commit_before_any_write(self):
        result = self.run_installer("--apply", rollback_commit=None)
        self.assertEqual(result.returncode, 2)
        self.assertIn("--apply needs --rollback-commit", result.stderr)
        result = self.run_installer("--apply", rollback_commit="0" * 40)
        self.assertEqual(result.returncode, 2)
        self.assertIn("is not a commit", result.stderr)
        self.assertEqual(self.files(), [])
        self.assertEqual(self.calls(), [])

    def test_reinstall_rollback_keeps_an_existing_mask(self):
        # A previous install already masked the legacy unit (symlink, no unit file).
        self.put("etc/systemd/system/thermal-backend.service", '[Service]\nEnvironment="LGPIO_CHIP=11"\n')
        self.set_state("masked", "kws-alert-vosk.service")
        result = self.run_installer("--apply", fail="enable project-pi-boot")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("ROLLBACK VERIFIED", result.stderr)
        self.assertIn("kws-alert-vosk.service", self.state_of("masked"))
        self.assertFalse(any(c.split()[0] in {"mask", "unmask"} for c in self.calls()))

    def test_rollback_never_touches_the_checkout_or_local_edits(self):
        self.legacy_pi()
        (self.repo / "VERSION").write_text("edited on the Pi\n", encoding="utf-8")
        result = self.run_installer("--apply", fail="enable project-pi-boot")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual((self.repo / "VERSION").read_text(encoding="utf-8"), "edited on the Pi\n")
        self.assert_code_untouched_and_reported(result)

    def test_failed_restoration_is_reported_as_incomplete(self):
        self.legacy_pi()
        result = self.run_installer("--apply", fail="enable project-pi-boot|unmask")
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("ROLLBACK INCOMPLETE", result.stderr)
        self.assertNotIn("ROLLBACK VERIFIED", result.stderr)
        self.assertIn("FAILED: unmask kws-alert-vosk.service", result.stderr)
        self.assertIn("NOT VERIFIED: kws-alert-vosk.service unmasked", result.stderr)
        # The steps that could be undone still were.
        self.assertIn("LGPIO_CHIP=11", (self.root / "etc/systemd/system/thermal-backend.service"
                                        ).read_text(encoding="utf-8"))

    def test_rollback_checks_the_end_state_not_just_exit_codes(self):
        self.legacy_pi()
        # A start that exits 0 but leaves the legacy service down must not count as restored.
        result = self.run_installer("--apply", fail="enable project-pi-boot",
                                    noop="start kws-alert-vosk")
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertNotIn("FAILED: start", result.stderr)
        self.assertIn("NOT VERIFIED: kws-alert-vosk.service active", result.stderr)
        self.assertIn("ROLLBACK INCOMPLETE", result.stderr)

    def test_failure_after_mask_rolls_back_files_and_legacy_unit(self):
        self.legacy_pi()
        self.assert_rolled_back(self.run_installer("--apply", fail="enable project-pi-boot"))
        self.assertNotIn("kws-alert.service", self.state_of("enabled"))

    def test_failed_restart_is_retried_once_and_never_reported_as_restored(self):
        self.legacy_pi()
        # The restart fails again during rollback: kws-alert never comes up.
        result = self.run_installer("--apply", "--restart", fail="restart thermal-backend")
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertEqual(sum(c.startswith("restart thermal-backend") for c in self.calls()), 2)
        self.assertIn("FAILED: restart thermal-backend.service kws-alert.service", result.stderr)
        self.assertIn("NOT VERIFIED: kws-alert.service active", result.stderr)
        self.assertIn("ROLLBACK INCOMPLETE", result.stderr)

    def test_restart_only_with_flag(self):
        result = self.run_installer("--apply", "--restart")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("restart thermal-backend.service kws-alert.service", self.calls())


@unittest.skipUnless(bash_usable(), "needs bash with GNU coreutils")
class BootOfflineTest(unittest.TestCase):
    def run_boot(self, hotspot_text=None, mode=0o600):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        base = Path(temp.name)
        stubs = base / "stubs"
        stubs.mkdir()
        calls = base / "calls"
        # Anything that waits for or changes the network records itself and fails.
        for name in ("nmcli", "apt-get", "sleep", "ping"):
            (stubs / name).write_text(f'#!/usr/bin/env bash\necho "{name} $*" >> "{calls.as_posix()}"\nexit 1\n',
                                      encoding="utf-8", newline="\n")
        (stubs / "iwgetid").write_text("#!/usr/bin/env bash\necho home-wifi\n", encoding="utf-8",
                                       newline="\n")
        (stubs / "logger").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8",
                                      newline="\n")
        for stub in stubs.iterdir():
            stub.chmod(0o755)
        hotspot = base / "hotspot.env"
        if hotspot_text is not None:
            hotspot.write_text(hotspot_text, encoding="utf-8", newline="\n")
            hotspot.chmod(mode)
        env = dict(os.environ, PROJECT_PI_STATE_DIR=(base / "state").as_posix(),
                   PROJECT_PI_HOTSPOT_CONF=hotspot.as_posix(),
                   PATH=f"{stubs.as_posix()}:/usr/bin:/bin:{os.environ.get('PATH', '')}")
        env.pop("PROJECT_PI_FORCE_HOTSPOT", None)
        started = time.monotonic()
        result = subprocess.run([shutil.which("bash"), BOOT.as_posix()], env=env,
                                capture_output=True, text=True, timeout=60)
        elapsed = time.monotonic() - started
        recorded = calls.read_text(encoding="utf-8").splitlines() if calls.exists() else []
        return result, recorded, elapsed

    def test_offline_boot_finishes_fast_without_network_or_package_updates(self):
        result, calls, elapsed = self.run_boot()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Network unchanged: SSID=home-wifi", result.stdout)
        self.assertEqual(calls, [])  # no nmcli, apt-get, sleep or ping
        self.assertLess(elapsed, 10)

    def test_hotspot_flag_in_untrusted_file_is_ignored(self):
        # Owned by the (non-root) test user: root must not source it.
        result, calls, _ = self.run_boot("PROJECT_PI_FORCE_HOTSPOT=1\n")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("not root-owned", result.stdout)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
