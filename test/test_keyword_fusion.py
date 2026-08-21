"""test_keyword_fusion.py -- Unit tests for the KWS keyword fusion logic."""
import importlib.util, sys, time, types, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
KWS_MODULE = PROJECT_ROOT / "raspberry_pi" / "kws" / "kws_alert_dual.py"
KWS_ROOT = PROJECT_ROOT / "raspberry_pi" / "kws"


class FakeArray:
    def __init__(self, data=None): self._data = data or []
    def __len__(self): return len(self._data)
    @property
    def size(self): return len(self._data)
    def tobytes(self): return b"\x00" * (len(self._data) * 2)
    def copy(self): return FakeArray(list(self._data))


def fake_asarray(x, dtype=None):
    return x if isinstance(x, FakeArray) else FakeArray(list(x) if hasattr(x, "__iter__") else [x])


def fake_concatenate(arrays):
    r = []
    for a in arrays:
        if isinstance(a, FakeArray): r.extend(a._data)
    return FakeArray(r)


def install_kws_stubs():
    np = types.ModuleType("numpy")
    np.float32 = float; np.int16 = int; np.ndarray = FakeArray
    np.clip = lambda v, lo, hi: max(lo, min(hi, v))
    np.asarray = fake_asarray; np.concatenate = fake_concatenate
    np.sqrt = lambda x: x ** 0.5
    np.mean = lambda x, **kw: 0.0
    np.square = lambda x: FakeArray()
    np.max = lambda x, **kw: 0.0
    pa = types.ModuleType("pyaudio"); pa.paInt16 = 8; pa.PyAudio = object
    req = types.ModuleType("requests")
    class FS:
        def post(self, url, json=None, timeout=None):
            return types.SimpleNamespace(raise_for_status=lambda: None)
    req.Session = FS
    vosk = types.ModuleType("vosk"); vosk.KaldiRecognizer = object; vosk.Model = object
    ap = types.ModuleType("audio_preprocessor"); ap.AudioPreprocessor = object
    ns = types.ModuleType("noise_suppressor")
    ns.DEFAULT_CONFIG_PATH = Path("noise.json")
    ns.NoiseSuppressionConfigStore = object; ns.NoiseSuppressor = object
    w2v = types.ModuleType("wav2vec2_verifier"); w2v.Wav2Vec2Verifier = object
    stubs = {"numpy": np, "pyaudio": pa, "requests": req, "vosk": vosk,
             "audio_preprocessor": ap, "noise_suppressor": ns, "wav2vec2_verifier": w2v}
    prev = {k: sys.modules.get(k) for k in stubs}
    sys.modules.update(stubs)
    if str(KWS_ROOT) not in sys.path: sys.path.insert(0, str(KWS_ROOT))
    return prev


def restore_modules(prev):
    for k, v in prev.items():
        if v is None: sys.modules.pop(k, None)
        else: sys.modules[k] = v


def load_kws_module():
    prev = install_kws_stubs()
    try:
        spec = importlib.util.spec_from_file_location("kws_fusion_test", KWS_MODULE)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        return mod, prev
    except Exception:
        restore_modules(prev); raise


def _ctx():
    return {"direction": "front", "snr_db": 25.0, "noise_level_db": -50.0,
            "signal_level_db": -20.0, "noise_reduction_db": 0.0,
            "noise_suppression_active": False, "strength": 0.7, "sensitivity": 0.5,
            "openwakeword_available": True, "openwakeword_vad_score": 0.8,
            "openwakeword_is_speech": True, "openwakeword_model_dir": None,
            "openwakeword_discovered_models": [], "openwakeword_loaded_models": [],
            "openwakeword_missing_models": [], "openwakeword_skipped_models": {},
            "openwakeword_wake_word": None, "openwakeword_wake_word_score": 0.0,
            "openwakeword_wake_words": [], "openwakeword_scores": []}


def make_dispatcher(m, cooldown_seconds=2.0):
    import tempfile
    qp = Path(tempfile.mkdtemp()) / "alerts.jsonl"
    poster = m.AlertPoster("http://fake/api/alerts", qp)
    class SS:
        def post(self, url, json=None, timeout=None):
            raise RuntimeError('backend offline')
    poster.session = SS()
    cooldown = m.CooldownGate(cooldown_seconds)
    dispatcher = m.DetectionDispatcher(poster=poster, cooldown=cooldown,
        help_confirm_seconds=0.05, help_suppress_after_tulong_seconds=0.5)
    return dispatcher, poster


class TestKeywordFusion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._prev = install_kws_stubs()
        cls.m, _ = load_kws_module()

    @classmethod
    def tearDownClass(cls):
        restore_modules(cls._prev)

    def test_01_keyword_candidate_dataclass_exists(self):
        m = self.m
        self.assertTrue(hasattr(m, "KeywordCandidate"))
        kc = m.KeywordCandidate(keyword="tulong", confidence=0.75, source="vosk",
                                accepted=True, reason="fallback_accepted")
        self.assertEqual(kc.keyword, "tulong")
        self.assertIsNone(kc.original_confidence)
        self.assertFalse(kc.verifier_used)

    def test_02_strong_openwakeword_accepted_directly(self):
        m = self.m
        d, poster = make_dispatcher(m)
        d.submit("tulong", 0.88, "openwakeword", context=_ctx())
        time.sleep(0.05)
        self.assertEqual(len(poster.pending), 1)
        self.assertEqual(poster.pending[0]["keyword"], "tulong")
        self.assertAlmostEqual(poster.pending[0]["confidence"], 0.88, places=2)

    def test_03_wav2vec2_confirms_boosts_confidence(self):
        m = self.m
        kc = m.KeywordCandidate(keyword="tulong", confidence=0.60, source="vosk",
                                accepted=True, reason="fallback_accepted")
        verified, vc = True, 0.95
        kc.verifier_used = True; kc.verifier_result = verified
        if verified:
            kc.original_confidence = kc.confidence
            kc.confidence = vc
            kc.reason = "verifier_boosted"
        self.assertAlmostEqual(kc.confidence, 0.95)
        self.assertAlmostEqual(kc.original_confidence, 0.60)
        self.assertEqual(kc.reason, "verifier_boosted")

    def test_04_wav2vec2_reject_does_not_veto(self):
        """wav2vec2 rejection must NOT drop the Vosk detection."""
        m = self.m
        final_confidence = 0.75
        kc = m.KeywordCandidate(keyword="tulong", confidence=0.75, source="vosk",
                                accepted=True, reason="fallback_accepted")
        verified, vc = False, 0.0
        kc.verifier_used = True; kc.verifier_result = verified
        if verified:
            final_confidence = vc; kc.reason = "verifier_boosted"
        self.assertTrue(kc.accepted)
        self.assertAlmostEqual(final_confidence, 0.75)
        self.assertEqual(kc.reason, "fallback_accepted")
        d, poster = make_dispatcher(m)
        d.submit("tulong", final_confidence, "vosk", context=_ctx())
        time.sleep(0.05)
        self.assertEqual(len(poster.pending), 1)

    def test_05_vosk_non_keyword_rejected(self):
        m = self.m
        for word in ["hello", "good morning", "magandang umaga", "", "   "]:
            self.assertIsNone(m.detect_tagalog_keyword(word), f"Expected None for: {word!r}")

    def test_06_vosk_configured_keywords_detected(self):
        m = self.m
        self.assertEqual(m.detect_tagalog_keyword("tulong"), "tulong")
        self.assertEqual(m.detect_tagalog_keyword("saklolo"), "saklolo")
        self.assertEqual(m.detect_tagalog_keyword("sunog"), "sunog")
        self.assertEqual(m.detect_tagalog_keyword("ang sakit"), "ang sakit")
        self.assertEqual(m.detect_tagalog_keyword("aray"), "aray")
        self.assertEqual(m.detect_tagalog_keyword("agai"), "agai")
        self.assertEqual(m.detect_tagalog_keyword("tolong"), "tulong")

    def test_07_snowboy_help_accepted(self):
        m = self.m
        d, poster = make_dispatcher(m)
        d.submit("help", 0.95, "snowboy", context=_ctx())
        time.sleep(0.12)
        self.assertEqual(len(poster.pending), 1)
        self.assertEqual(poster.pending[0]["keyword"], "help")

    def test_08_one_utterance_one_event(self):
        m = self.m
        d, poster = make_dispatcher(m, cooldown_seconds=2.0)
        for _ in range(3):
            d.submit("saklolo", 0.8, "openwakeword", context=_ctx())
        time.sleep(0.05)
        self.assertEqual(len(poster.pending), 1)

    def test_09_cooldown_timing(self):
        m = self.m
        g = m.CooldownGate(0.08)
        self.assertTrue(g.allow("help"))
        self.assertFalse(g.allow("help"))
        time.sleep(0.10)
        self.assertTrue(g.allow("help"))

    def test_10_cooldown_per_keyword_independent(self):
        m = self.m
        g = m.CooldownGate(5.0)
        self.assertTrue(g.allow("help"))
        self.assertFalse(g.allow("help"))
        self.assertTrue(g.allow("tulong"))

    def test_11_rejected_weak_does_not_poison_strong(self):
        m = self.m
        g = m.CooldownGate(0.05)
        self.assertTrue(g.allow("tulong"))
        time.sleep(0.07)
        self.assertTrue(g.allow("tulong"))

    def test_12_nan_score_safe(self):
        m = self.m
        self.assertIsNone(m.detect_tagalog_keyword(""))
        self.assertIsNone(m.detect_tagalog_keyword("123"))

    def test_13_wav2vec2_unavailable_openwakeword_works(self):
        m = self.m
        d, poster = make_dispatcher(m)
        d.submit("help", 0.90, "openwakeword", context=_ctx())
        time.sleep(0.05)
        self.assertEqual(len(poster.pending), 1)
        self.assertAlmostEqual(poster.pending[0]["confidence"], 0.90, places=2)

    def test_14_vosk_confidence_default_075(self):
        src = KWS_MODULE.read_text(encoding="utf-8")
        self.assertIn("VOSK_KEYWORD_CONFIDENCE", src)
        # New default must be 0.75 not 0.40
        self.assertIn("0.75", src)
        self.assertNotIn('getenv("VOSK_KEYWORD_CONFIDENCE", "0.40")', src)

    def test_15_wav2vec2_boost_only_no_veto(self):
        src = KWS_MODULE.read_text(encoding="utf-8")
        self.assertNotIn("wav2vec2 verifier rejected Vosk detection", src)
        self.assertIn("wav2vec2 verifier did not confirm", src)

    def test_16_all_17_onnx_models_have_threshold_mappings(self):
        model_dir = PROJECT_ROOT / "dataset" / "audio" / "openwakeword_models"
        service_file = PROJECT_ROOT / "raspberry_pi" / "systemd" / "kws-alert.service"
        if not model_dir.is_dir():
            self.skipTest("Model dir not on this machine")
        service_text = service_file.read_text(encoding="utf-8")
        thresh_line = next(
            (line for line in service_text.splitlines() if "OPENWAKEWORD_MODEL_THRESHOLDS" in line), ""
        )
        missing = []
        for f in model_dir.glob("*.onnx"):
            phrase = " ".join(f.stem.replace("_", " ").replace("-", " ").lower().split())
            if phrase not in thresh_line:
                missing.append(f"{f.name} -> {phrase!r}")
        self.assertEqual(missing, [], f"Missing threshold mappings: {missing}")


if __name__ == "__main__":
    unittest.main(verbosity=2)