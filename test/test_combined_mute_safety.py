"""Combined-source review regressions; synthetic IPC and manual recognizer timers."""
import os
import json
import queue
import signal
import unittest
from unittest.mock import Mock, patch

from raspberry_pi.resident_control import KwsMuteGate, RecognitionPoster, Settings
from test import test_resident_control as controls
from test import test_runtime_safety_blockers as recognition


class CombinedMuteSafetyTest(unittest.TestCase):
    setUp = controls.ResidentControlTests.setUp
    command = controls.ResidentControlTests.command

    @unittest.skipUnless(hasattr(os, 'mkfifo') and hasattr(signal, 'setitimer'), 'POSIX IPC fixture')
    def test_fifo_request_and_ack_cannot_block_recognition_or_backend(self):
        def timed_out(signum, frame):
            raise AssertionError('Invalid FIFO blocked IPC instead of failing open')
        previous = signal.signal(signal.SIGALRM, timed_out)
        try:
            for name in ('request.json', 'ack.json'):
                path = self.root / name
                path.unlink(missing_ok=True)
                os.mkfifo(path)
                signal.setitimer(signal.ITIMER_REAL, .3)
                try:
                    self.assertEqual(self.files.read(name), {})
                finally:
                    signal.setitimer(signal.ITIMER_REAL, 0)
                    path.unlink()
        finally:
            signal.signal(signal.SIGALRM, previous)

    def test_malformed_worker_ack_never_advertises_or_acquires_mute(self):
        valid = self.files.read('ack.json')
        for changes in ({'worker': None}, {'epoch': True}, {'muted': 'false'},
                        {'observed_at': True}, {'worker': 'not-a-worker'}, {'epoch': -1}):
            with self.subTest(changes=changes):
                self.files.write('ack.json', dict(valid, **changes))
                self.assertFalse(self.plane.snapshot()['remote_mute_available'])
                with self.assertRaises(ValueError):
                    self.command('mute_start')
        self.files.write('ack.json', {'observed_at': self.now})
        self.assertFalse(self.plane.snapshot()['remote_mute_available'])
        with self.assertRaises(ValueError):
            self.command('mute_start')

    def test_ack_write_failure_releases_once_without_dropping_every_frame(self):
        self.gate.poll()
        self.command('mute_start')
        reset, cancel = Mock(), Mock()
        with patch.object(self.gate.files, 'write', side_effect=OSError('synthetic ACK failure')):
            self.assertTrue(self.gate.capture_boundary([queue.Queue()], reset, cancel))
            self.assertFalse(self.gate.muted)
            epoch = self.gate.epoch
            for _ in range(3):
                self.assertFalse(self.gate.capture_boundary([queue.Queue()], reset, cancel))
                self.assertFalse(self.gate.muted)
                self.assertEqual(self.gate.epoch, epoch)
        # A recovered channel cannot reactivate a previously failed hold.
        self.assertFalse(self.gate.capture_boundary([], reset, cancel))
        self.assertFalse(self.gate.muted)

    def test_poll_never_returns_muted_after_ack_write_fails(self):
        self.gate.poll()
        self.command('mute_start')
        with patch.object(self.gate.files, 'write', side_effect=OSError('synthetic ACK failure')):
            self.assertFalse(self.gate.poll())
            self.assertFalse(self.gate.muted)

    def test_oversized_numeric_timestamps_fail_open(self):
        self.files.write('ack.json', dict(self.files.read('ack.json'), observed_at=10**400))
        self.assertFalse(self.plane.snapshot()['remote_mute_available'])
        self.files.write('request.json', dict(worker=self.gate.worker, active=True,
                         lease_id='fixture', boot='fixture', expires_at=10**400))
        self.assertFalse(self.gate.poll())

    def test_excessively_nested_ipc_and_credentials_are_invalid(self):
        nested = '[' * 1100 + '0' + ']' * 1100
        (self.root / 'request.json').write_text(nested)
        self.assertEqual(self.files.read('request.json'), {})
        (self.root / 'credentials.json').write_text(nested)
        self.assertFalse(self.plane.authenticate('fixture-resident', 'fixture-resident-secret-not-production'))


class CombinedRecognitionFenceTest(unittest.TestCase):
    setUp = recognition.RuntimeSafetyCounterexamples.setUp

    def dispatcher(self):
        gate = KwsMuteGate(Settings(), clock=lambda: self.now)
        poster = recognition.Recorder()
        dispatcher = self.kws.DetectionDispatcher(RecognitionPoster(poster, gate),
                        self.kws.CooldownGate(2), 1.2, 2.2)
        dispatcher.mute_gate = gate
        return dispatcher, poster, gate

    def test_stale_delayed_help_cannot_consume_fresh_independent_help_cooldown(self):
        dispatcher, poster, gate = self.dispatcher()
        dispatcher.submit('help', .9, 'snowboy', context={'recognition_epoch': 0})
        timer = dispatcher.pending_help_timer
        gate.epoch = 1  # Capture won the boundary before a previously queued timer runs.
        timer.fire()
        self.assertNotIn('help', dispatcher.cooldown.last_seen)
        dispatcher.submit('help', .9, 'openwakeword', context={'recognition_epoch': 1})
        self.assertEqual(poster.events, [('help', .9, 'openwakeword')])

    def test_stale_submission_cannot_mutate_accepted_source_state(self):
        dispatcher, poster, gate = self.dispatcher()
        gate.epoch = 1
        dispatcher.submit('tulong', .9, 'vosk', context={'recognition_epoch': 0})
        self.assertEqual(dispatcher.last_tulong_by_source, {})
        self.assertEqual(dispatcher.cooldown.last_seen, {})
        self.assertEqual(poster.events, [])

    def test_timer_validates_and_publishes_with_capture_gate_held(self):
        dispatcher, poster, gate = self.dispatcher()
        dispatcher.submit('help', .9, 'snowboy', context={'recognition_epoch': 0})
        original = dispatcher.cooldown.allow
        observed = []
        def allow(keyword):
            observed.append(gate.lock._is_owned())
            return original(keyword)
        dispatcher.cooldown.allow = allow
        dispatcher.pending_help_timer.fire()
        self.assertEqual(observed, [True])
        self.assertEqual(poster.events, [('help', .9, 'snowboy')])

    def test_canceled_callback_cannot_consume_replacement_confirmation_timer(self):
        dispatcher, poster, gate = self.dispatcher()
        dispatcher.submit('help', .9, 'snowboy', context={'recognition_epoch': 0})
        old = dispatcher.pending_help_timer
        with gate.lock, dispatcher.lock:
            old.cancel()
            dispatcher.pending_help_timer = None
            dispatcher.pending_help_payload = None
            gate.epoch = 1
        dispatcher.submit('help', .9, 'snowboy', context={'recognition_epoch': 1})
        fresh = dispatcher.pending_help_timer
        old.callback()  # Simulate a callback already running when cancel() happened.
        self.assertEqual(poster.events, [])
        self.assertIs(dispatcher.pending_help_timer, fresh)
        fresh.fire()
        self.assertEqual(poster.events, [('help', .9, 'snowboy')])
