"""Exercise the actual fallback worker functions with synthetic engines only."""
import queue
import unittest
from unittest.mock import Mock

from raspberry_pi.resident_control import KwsMuteGate, Settings
from test.test_keyword_fusion import load_kws_module, restore_modules, FakeArray


class WorkerGateTests(unittest.TestCase):
    def setUp(self):
        self.kws, previous = load_kws_module()
        self.addCleanup(restore_modules, previous)
        self.gate = KwsMuteGate(Settings())
        self.gate.epoch = 2
        self.dispatcher = Mock()
        self.dispatcher.mute_gate = self.gate
        self.packets = queue.Queue()
        for epoch in (0, 2):
            self.packets.put(dict(recognition_epoch=epoch, mono_bytes=b'fixture-pcm', mono_samples=FakeArray([1, 2])))
        original_get = self.packets.get
        def get(**kwargs):
            if self.packets.empty():
                self.kws.RUNNING = False
                raise queue.Empty()
            return original_get(**kwargs)
        self.packets.get = get

    def test_vosk_discards_old_epoch_and_resets_before_fresh_audio(self):
        recognizer = Mock()
        self.kws.read_vosk_text = Mock(return_value='tulong')
        self.kws.vosk_worker(self.packets, self.dispatcher, dict(sample_rate=16000,
            debug=False, confidence=.75, wav2vec2_verify_below_confidence=.7,
            wav2vec2_context_seconds=1, model_path='fixture'), recognizer, None)
        self.assertEqual(self.kws.read_vosk_text.call_count, 1)
        self.assertEqual(recognizer.Reset.call_count, 2)
        self.assertEqual(self.dispatcher.submit.call_count, 1)
        self.assertEqual(self.dispatcher.submit.call_args.kwargs['context']['recognition_epoch'], 2)

    def test_snowboy_recreates_detector_and_discards_old_epoch(self):
        detector = Mock()
        detector.RunDetection.return_value = 1
        self.kws.create_snowboy_detector = Mock(return_value=detector)
        sensitivity = Mock(current_value=.38)
        sensitivity.sensitivity_list.return_value = ['.38']
        self.kws.snowboy_worker(self.packets, self.dispatcher,
            dict(keywords=['help'], model_paths=['fixture'], alert_keyword='help', confidence=.75),
            sensitivity, detector)
        self.assertEqual(self.kws.create_snowboy_detector.call_count, 1)
        self.assertEqual(detector.RunDetection.call_count, 1)
        self.assertEqual(self.dispatcher.submit.call_count, 1)

    def test_muted_worker_does_not_feed_engine_or_publish(self):
        self.gate.muted = True
        recognizer = Mock()
        self.kws.read_vosk_text = Mock(return_value='tulong')
        self.kws.vosk_worker(self.packets, self.dispatcher, dict(sample_rate=16000,
            debug=False, confidence=.75, wav2vec2_verify_below_confidence=.7,
            wav2vec2_context_seconds=1, model_path='fixture'), recognizer, None)
        self.kws.read_vosk_text.assert_not_called()
        self.dispatcher.submit.assert_not_called()


if __name__ == '__main__':
    unittest.main()
