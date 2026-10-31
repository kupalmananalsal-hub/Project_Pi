"""Static checks of the Pi deployment scripts and units (they cannot run on a dev machine)."""
import hashlib
import re
import shutil
import subprocess
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PI = PROJECT_ROOT / "raspberry_pi"
SCRIPTS = PI / "scripts"
INSTALLER = SCRIPTS / "install_headless.sh"
BOOT = SCRIPTS / "headless_boot.sh"
DEPS = SCRIPTS / "install_kws_openwakeword_deps.sh"
UPGRADE_DOC = PROJECT_ROOT / "docs" / "m1_m2_upgrade_and_rollback.md"


def read(path):
    return path.read_text(encoding="utf-8")


def code_lines(path):
    """Non-comment lines, so documentation inside a script never satisfies a check."""
    return [line for line in read(path).splitlines() if not line.lstrip().startswith("#")]


class InstallHeadlessTest(unittest.TestCase):
    def setUp(self):
        self.text = read(INSTALLER)
        self.code = "\n".join(code_lines(INSTALLER))
        # Everything after this point runs only with --apply.
        self.apply_at = self.code.index('if [[ "${MODE}" != "apply" ]]; then')

    @unittest.skipUnless(shutil.which("bash"), "bash not available")
    def test_scripts_parse(self):
        for script in sorted(SCRIPTS.glob("*.sh")):
            subprocess.run(["bash", "-n", str(script)], check=True)

    def test_default_mode_is_a_dry_run_that_writes_nothing(self):
        self.assertIn("MODE=dry-run", self.code)
        before = self.code[:self.apply_at]
        writes = re.compile(
            r"^\s*(install\s+-|cp\s|rm\s|mv\s|mkdir\s|chmod\s|chown\s|ln\s|"
            r"systemctl\s+(enable|disable|mask|unmask|stop|start|restart|daemon-reload))", re.M)
        self.assertEqual(writes.findall(before), [])
        # Redirections before --apply only fill the private staging directory.
        for target in re.findall(r'>\s*"([^"]+)"', before):
            self.assertTrue(target.startswith("${STAGE}"), target)
        self.assertIn("exit 0", self.code[self.apply_at:self.apply_at + 200])

    def test_installer_never_installs_packages_or_touches_networkmanager(self):
        for forbidden in ("install_kws_openwakeword_deps", "apt-get", "pip install",
                          "pip3 install", "nmcli", "project-pi-boot\n"):
            self.assertNotIn(forbidden, self.code, forbidden)
        self.assertNotRegex(self.code, r"/usr/local/sbin/project-pi-boot\s*$")

    def test_local_dropin_is_created_only_if_absent_and_seeded_from_installed_unit(self):
        self.assertIn('if [[ ! -e "${THERMAL_DROPIN}" ]]; then', self.code)
        self.assertIn("systemctl cat thermal-backend.service", self.code)
        for key in ("LGPIO_CHIP", "THERMAL_HUMAN_MODEL_PATH", "THERMAL_HUMAN_MODEL_METADATA_PATH",
                    "THERMAL_HUMAN_MODEL_THRESHOLD", "THERMAL_REFRESH_HZ"):
            self.assertIn(key, self.code)
        self.assertIn("Environment=MLX90640_VARIANT=unverified", self.code)
        self.assertIn("Environment=THERMAL_REFRESH_HZ=4", self.code)
        self.assertIn("variant not verified", self.text)
        # The only .service.d path the installer names is the one it creates if absent.
        self.assertEqual(re.findall(r"[\w.-]+\.service\.d/[\w.-]*", self.code),
                         ["thermal-backend.service.d/10-local.conf"])

    def test_backend_env_is_created_only_if_absent_in_open_mode(self):
        self.assertIn('if [[ ! -e "${BACKEND_CONF}" ]]; then', self.code)
        self.assertIn("PROJECT_PI_API_AUTH=open", self.code)

    def test_hotspot_config_needs_explicit_flag(self):
        block = self.code[self.code.index('if [[ "${CONFIGURE_HOTSPOT}" -eq 1 ]]; then'):]
        block = block[:block.index("\nfi\n")]
        self.assertIn('TARGETS+=("${STAGE}/hotspot.env|${HOTSPOT_CONF}|600")', block)
        self.assertEqual(self.code.count("${HOTSPOT_CONF}|"), 1)

    def test_legacy_vosk_failures_are_never_hidden(self):
        # Order, masking and rollback are exercised in test_install_runtime.
        apply_part = self.code[self.apply_at:]
        for line in apply_part.splitlines():
            if "LEGACY_VOSK_UNIT" in line and "systemctl" in line:
                self.assertNotIn("|| true", line)
                self.assertNotIn("2>/dev/null", line)
        self.assertIn("set -Eeuo pipefail", self.code)
        self.assertIn("trap rollback ERR", apply_part)
        self.assertIn("thesis-camera.service", self.code)
        self.assertNotRegex(self.code, r"systemctl\s+(disable|stop|mask)\s+thesis-camera")

    def test_every_restart_is_gated_by_the_restart_flag(self):
        lines = self.code.splitlines()
        restarts = [i for i, line in enumerate(lines) if re.match(r"\s*systemctl restart", line)]
        self.assertTrue(restarts)
        for i in restarts:
            self.assertRegex("\n".join(lines[i - 2:i]),
                             r'if \[\[ "\$\{RESTART(_ATTEMPTED)?\}" -eq 1 \]\]; then')
            self.assertGreater(self.code.index(lines[i]), self.apply_at)


class BootScriptTest(unittest.TestCase):
    def test_network_is_changed_only_with_force_hotspot(self):
        code = "\n".join(code_lines(BOOT))
        main = code[code.index("main() {"):]
        gate = main.index('if [[ "${PROJECT_PI_FORCE_HOTSPOT:-0}" == "1" ]]; then')
        self.assertLess(gate, main.index("connect_hotspot"))
        self.assertLess(main.index("connect_hotspot"), main.index("log_network"))
        # connect_hotspot is the only path to nmcli writes, and it is called only under the gate.
        self.assertEqual(len(re.findall(r"^\s*connect_hotspot(?!\(\))\b", code, re.M)), 1)
        for line in code.splitlines():
            if re.search(r"nmcli .*(up|modify|add|connect)\b", line):
                function_start = code.rindex("() {", 0, code.index(line))
                name = code[code.rindex("\n", 0, function_start) + 1:function_start]
                self.assertIn(name, {"ensure_hotspot_profile", "configure_static_ipv4",
                                     "connect_hotspot"}, line)

    def test_boot_never_waits_for_network_or_updates_packages_by_default(self):
        code = "\n".join(code_lines(BOOT))
        main = code[code.index("main() {"):]
        gate = main.index('if [[ "${PROJECT_PI_FORCE_HOTSPOT:-0}" == "1" ]]; then')
        self.assertGreater(main.index("wait_for_network"), gate)
        self.assertLess(main.index("wait_for_network"), main.index("else"))
        self.assertNotIn("apt-get", code)


class OfflineStartupTest(unittest.TestCase):
    """Detection must start without Wi-Fi/internet and without waiting for boot preparation."""

    NETWORK_GATES = ("network-online.target", "network.target", "NetworkManager-wait-online",
                     "project-pi-boot.service", "project-pi-apt-update", "systemd-time-wait-sync")

    def test_detection_units_never_wait_for_network_or_boot_preparation(self):
        for name in ("thermal-backend.service", "kws-alert.service"):
            for line in code_lines(PI / "systemd" / name):
                if re.match(r"(After|Requires|Wants|BindsTo|Requisite|PartOf)=", line):
                    for gate in self.NETWORK_GATES:
                        self.assertNotIn(gate, line, f"{name}: {line}")

    def test_detection_units_talk_only_to_localhost(self):
        unit = read(PI / "systemd" / "kws-alert.service")
        self.assertIn("BACKEND_ALERT_URL=http://127.0.0.1:8765/api/alerts", unit)
        self.assertIn("--host 0.0.0.0", read(PI / "systemd" / "thermal-backend.service"))


class DependencyScriptTest(unittest.TestCase):
    def test_deps_script_needs_acknowledgement_and_installs_only_pinned(self):
        code = "\n".join(code_lines(DEPS))
        self.assertIn("--i-understand-this-upgrades-packages", code)
        self.assertLess(code.index("--i-understand-this-upgrades-packages"), code.index("apt-get"))
        self.assertNotIn("--upgrade", code)
        self.assertIn('install -r "${LOCK_FILE}"', code)
        self.assertIn("MANUAL USE ONLY", read(DEPS))


class UnitFileTest(unittest.TestCase):
    def test_generic_thermal_unit_has_detector_model_and_no_device_settings(self):
        unit = "\n".join(code_lines(PI / "systemd" / "thermal-backend.service"))
        self.assertIn("/dataset/thermal/models/thermal_human_detector.tflite", unit)
        self.assertIn("/dataset/thermal/models/thermal_human_detector.metadata.json", unit)
        for absent in ("THERMAL_HUMAN_MODEL_THRESHOLD", "THERMAL_REFRESH_HZ", "LGPIO_CHIP",
                       "MLX90640_VARIANT", "thermal_human_shape"):
            self.assertNotIn(absent, unit)
        self.assertIn('Environment="GPIOZERO_PIN_FACTORY=lgpio"', unit)

    def test_kws_unit_conflicts_with_legacy_and_keeps_baseline_settings(self):
        unit = read(PI / "systemd" / "kws-alert.service")
        self.assertIn("Conflicts=kws-alert-vosk.service", unit)
        # Thresholds, keywords, VAD, cooldowns and model paths must match the deployed Pi
        # (commit 1a5c309) byte for byte; only the outbox path moved off tmpfs.
        env = [line for line in unit.splitlines()
               if line.startswith("Environment=") and "ALERT_QUEUE_PATH" not in line]
        digest = hashlib.sha256("".join(line + "\n" for line in env).encode()).hexdigest()
        self.assertEqual(digest, "aba1bd34432d5f71dc9338ccd50e7764a525c0c1bf404b56c224f1a3808b83c3")


class DataPreservationTest(unittest.TestCase):
    PROTECTED = re.compile(
        r"dataset|alerts\.db|\.tflite|\.onnx|\.pmdl|thesis_dataset|voice_samples|vosk-models|"
        r"snowboy|caregivers\.json|\$\{BACKEND_CONF\}|\$\{HOTSPOT_CONF\}|/etc/project-pi/[\w.-]+\.env")
    WRITE = re.compile(
        r"(^|[;&|]\s*)(rm|mv|cp|install|truncate|tee|dd|shred|chmod|chown|ln)\s|sed\s+-i|"
        r"find\s.*-delete|>\s*\S")
    # Every write that names a protected path must be one of these reviewed cases.
    ALLOWED = {
        # Read-only: the drift check and the refresh hint never write these.
        "PROJECT_PI_CAREGIVER_CREDENTIALS=/var/lib/project-pi/backend/caregivers.json",
        "if grep -qs \"^PROJECT_PI_API_TOKEN=${LEGACY_TOKEN}\\$\" \"${BACKEND_CONF}\"; then",
    }

    def test_scripts_never_write_or_delete_protected_paths(self):
        for script in (INSTALLER, BOOT, SCRIPTS / "pi_refresh.sh", SCRIPTS / "log_cleanup.sh"):
            for line in code_lines(script):
                stripped = line.strip()
                if stripped.startswith("echo ") or stripped in self.ALLOWED:
                    continue
                if self.PROTECTED.search(stripped) and self.WRITE.search(stripped):
                    self.fail(f"{script.name}: {stripped}")

    def test_installer_writes_protected_config_only_via_staged_create_if_absent(self):
        code = "\n".join(code_lines(INSTALLER))
        # backend.env and hotspot.env reach /etc only through TARGETS entries staged above.
        self.assertIn('TARGETS+=("${STAGE}/backend.env|${BACKEND_CONF}|600")', code)
        self.assertNotRegex(code, r'>\s*"\$\{(BACKEND|HOTSPOT)_CONF\}"')


class UpgradeDocTest(unittest.TestCase):
    def test_upgrade_doc_keeps_a_branch_for_refresh(self):
        step2 = read(UPGRADE_DOC).split("## 2.", 1)[1].split("## 3.", 1)[0]
        self.assertIn("git switch main", step2)
        self.assertIn("git merge --ff-only <REVIEWED_COMMIT>", step2)
        self.assertNotIn("git checkout <REVIEWED_COMMIT>", step2)
        self.assertNotRegex(step2, r"git reset|--force|-f\b")

    def test_upgrade_doc_runs_the_dry_run_before_apply(self):
        step3 = read(UPGRADE_DOC).split("## 3.", 1)[1].split("## 4.", 1)[0]
        self.assertLess(step3.index("install_headless.sh\n"), step3.index("--apply"))


if __name__ == "__main__":
    unittest.main()
