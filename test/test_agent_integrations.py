"""Regression tests for inert agent-integration tooling; no physical hardware required."""
from __future__ import annotations

import importlib.util
import json
import math
import subprocess
import sys
import tempfile
import time
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'tools/agent_integrations'


def load(name):
    spec = importlib.util.spec_from_file_location(name, TOOLS / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


audit_sources = load('audit_sources')
check_configuration = load('check_configuration')
offline_hil = load('offline_hil')
preflight = load('read_only_pi_preflight')
validate_skills = load('validate_skills')


class SkillAndConfigTests(unittest.TestCase):
    def test_all_project_skills_have_valid_codex_and_claude_entrypoints(self):
        self.assertEqual(validate_skills.validate(), {})
        self.assertEqual(len(validate_skills.NAMES), 8)

    def test_configuration_is_inert_and_credential_free(self):
        report = check_configuration.check()
        self.assertEqual(report['errors'], [])

    def test_secret_detector_catches_private_key_and_token(self):
        self.assertTrue(check_configuration.secret_hits('-----BEGIN OPENSSH PRIVATE KEY-----'))
        self.assertTrue(check_configuration.secret_hits('api_key=abcdefghijklmnop'))

    def test_no_toolkit_file_can_be_an_active_mcp_config(self):
        self.assertFalse((ROOT / '.mcp.json').exists())
        self.assertTrue((TOOLS / 'mcp.optional.example.json').is_file())

    def test_tooling_contains_no_installer_or_plugin_activation(self):
        text = '\n'.join(path.read_text(encoding='utf-8') for path in TOOLS.glob('*.py'))
        self.assertNotIn('pip install', text)
        self.assertNotIn('npm install', text)
        self.assertNotIn('plugin install', text)


class SourceAuditTests(unittest.TestCase):
    def test_rejects_traversal_and_unpinned_revision_before_network(self):
        with self.assertRaises(ValueError):
            audit_sources.fetch_file('owner/repo', 'a' * 40, '../run.py')
        with self.assertRaises(ValueError):
            audit_sources.fetch_file('owner/repo', 'main', 'README.md')

    def test_fetch_is_text_only_and_never_executes_source(self):
        class Response:
            def geturl(self): return 'https://raw.githubusercontent.com/owner/repo/'
            def read(self, _): return b'print("not executed")'
            def __enter__(self): return self
            def __exit__(self, *_): return False
        evidence = audit_sources.fetch_file('owner/repo', 'a' * 40, 'README.md', lambda *_a, **_k: Response())
        self.assertEqual(evidence['text'], 'print("not executed")')


class ReadOnlyProbeTests(unittest.TestCase):
    def test_default_is_a_plan_and_never_starts_runner(self):
        def forbidden(_):
            raise AssertionError('runner must not be called in plan mode')
        result = preflight.run_probes(['os'], runner=forbidden)
        self.assertEqual(result['mode'], 'PLAN_ONLY')
        self.assertEqual(result['commands']['os'], list(preflight.PROBES['os']))

    def test_remote_requires_explicit_enable_and_approval(self):
        config = {'enabled': False, 'hosts': {}}
        with self.assertRaises(PermissionError):
            preflight.ssh_argv(config, 'missing', 'os', approved=False)

    def test_remote_rejects_root_and_unknown_commands(self):
        with tempfile.TemporaryDirectory() as temp:
            key = Path(temp) / 'key'; known = Path(temp) / 'known'
            key.write_text('placeholder'); known.write_text('placeholder')
            bad = {'enabled': True, 'hosts': {'pi': {'host': 'pi.local', 'user': 'root',
                   'identity_file': str(key), 'known_hosts_file': str(known)}}}
            with self.assertRaises(ValueError): preflight.ssh_argv(bad, 'pi', 'os', approved=True)
            with self.assertRaises(ValueError): preflight.ssh_argv(bad, 'pi', 'anything', approved=True)

    def test_bounded_run_times_out(self):
        result = preflight.bounded_run([sys.executable, '-c', 'import time; time.sleep(2)'], timeout=.05)
        self.assertTrue(result['timeout'])

    def test_backend_probe_never_reads_body_or_sends_credentials(self):
        argv = preflight.PROBES['backend']
        self.assertNotIn('--fail', argv)  # --fail would turn 401 into "probe failed"
        self.assertIn('/dev/null', argv)
        self.assertFalse(any('authorization' in part.lower() or 'token' in part.lower() for part in argv))

    def test_backend_401_means_reachable_not_healthy(self):
        classify = preflight.classify_backend
        self.assertEqual(classify({'exit_code': 0, 'output': '401'}), 'BACKEND_REACHABLE_AUTH_REQUIRED')
        self.assertEqual(classify({'exit_code': 0, 'output': '200'}), 'BACKEND_REACHABLE_AUTH_NOT_ENFORCED')
        self.assertEqual(classify({'exit_code': 7, 'output': '000'}), 'BACKEND_UNREACHABLE')
        self.assertEqual(classify({'exit_code': 0, 'output': '500'}), 'BACKEND_HTTP_500')
        self.assertEqual(classify({'exit_code': None, 'output': ''}), 'BACKEND_UNREACHABLE')


class OfflineHilTests(unittest.TestCase):
    def test_valid_thermal_fixture(self):
        payload = {'temperatures': [22.0] * 768, 'timestamp': time.time(), 'read_latency_ms': 35}
        self.assertTrue(offline_hil.thermal_frame(payload)['passed'])

    def test_invalid_thermal_fixture_is_not_a_hardware_read(self):
        result = offline_hil.thermal_frame({'temperatures': [math.nan], 'timestamp': 0, 'read_latency_ms': 9999}, now=10)
        self.assertFalse(result['passed'])
        self.assertEqual(result['mode'], 'OFFLINE_FIXTURE')

    def test_pcm16_audio_fixture(self):
        with tempfile.TemporaryDirectory() as temp:
            audio = Path(temp) / 'fixture.wav'
            with wave.open(str(audio), 'wb') as wav:
                wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)
                wav.writeframes(b'\0\0' * 160)
            result = offline_hil.audio_file(audio)
        self.assertEqual(result['mode'], 'OFFLINE_FILE')
        self.assertTrue(result['silent'])
        self.assertEqual(result['vad_activity'], 'NOT_MEASURED')


if __name__ == '__main__':
    unittest.main()
