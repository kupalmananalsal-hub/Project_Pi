"""C1.58 real dispatcher regressions; synthetic packets and manual timers only."""
import unittest
from test import test_runtime_safety_blockers as fixtures


class IndependentEvidenceTest(unittest.TestCase):
    setUp = fixtures.RuntimeSafetyCounterexamples.setUp
    dispatcher = fixtures.RuntimeSafetyCounterexamples.dispatcher
    run_worker = fixtures.RuntimeSafetyCounterexamples.run_worker

    def test_hint_revision_retains_pending_snowboy(self):
        d, p = self.dispatcher()
        d.submit('help', .9, 'snowboy')
        timer = d.pending_help_timer
        d.note_vosk_text('tulong')
        d.note_vosk_text('tulog')
        self.assertFalse(timer.cancelled)
        timer.fire()
        self.assertEqual(p.events, [('help', .9, 'snowboy')])

    def test_all_independent_arrival_orders_survive_vosk_revision(self):
        for source in ('snowboy', 'openwakeword'):
            for arrival in ('before', 'between', 'after'):
                with self.subTest(source=source, arrival=arrival):
                    self.now = 1000
                    d, p = self.dispatcher()
                    if arrival == 'before': d.submit('help', .9, source)
                    def inject(index):
                        if index == 1 and arrival == 'between': d.submit('help', .9, source)
                    self.run_worker([(1000.1, False, 'tulong'), (1000.2, True, 'tulog')], d, inject)
                    if arrival == 'after': d.submit('help', .9, source)
                    if d.pending_help_timer: d.pending_help_timer.fire()
                    self.assertCountEqual(p.events, [('tulong', .75, 'vosk'), ('help', .9, source)])

    def test_rejected_tulong_neither_refreshes_nor_cancels(self):
        d, p = self.dispatcher()
        d.submit('tulong', .75, 'vosk')
        self.now = 1001.9
        d.submit('help', .9, 'snowboy')
        timer = d.pending_help_timer
        d.note_vosk_text('tulong')
        d.submit('tulong', .75, 'vosk')
        self.assertEqual(d.last_tulong_at, 1000)
        self.assertIs(d.pending_help_timer, timer)
        self.assertFalse(timer.cancelled)
        timer.fire()
        self.assertEqual(p.events, [('tulong', .75, 'vosk'), ('help', .9, 'snowboy')])

    def test_text_hint_alone_does_not_change_veto_state(self):
        d, p = self.dispatcher()
        before = (d.last_tulong_at, d.last_tulong_hint_at, dict(d.cooldown.last_seen))
        for text in ('tulong', 'tulog', '', 'ordinary speech'): d.note_vosk_text(text)
        self.assertEqual((d.last_tulong_at, d.last_tulong_hint_at, d.cooldown.last_seen), before)
        self.assertEqual(p.events, [])

    def test_engine_failure_and_recovery_leave_independent_pending_help(self):
        d, p = self.dispatcher()
        d.submit('help', .9, 'snowboy')
        timer = d.pending_help_timer
        with self.assertRaisesRegex(RuntimeError, 'fixture failure'):
            self.run_worker([(1000.1, False, 'tulong'), (1000.2, False, RuntimeError('fixture failure'))], d)
        self.run_worker([(1000.3, True, '')], d)  # Missing/empty text is not silence proof.
        self.assertFalse(timer.cancelled)
        timer.fire()
        self.assertCountEqual(p.events, [('tulong', .75, 'vosk'), ('help', .9, 'snowboy')])

    def test_same_engine_correlation_and_keyword_cooldown_are_preserved(self):
        d, p = self.dispatcher()
        d.submit('tulong', .9, 'openwakeword')
        d.submit('help', .9, 'openwakeword')
        self.assertEqual(p.events, [('tulong', .9, 'openwakeword')])

    def test_repeated_help_and_later_eligible_event_keep_existing_cooldown(self):
        d, p = self.dispatcher()
        d.submit('help', .9, 'snowboy'); timer = d.pending_help_timer
        d.submit('help', .9, 'snowboy')
        self.assertIs(timer, d.pending_help_timer)
        timer.fire(); d.submit('help', .9, 'openwakeword')
        self.assertEqual(len(p.events), 1)
        self.now += 3  # Fixture beyond existing 2-second test cooldown, not new episode policy.
        d.submit('help', .9, 'openwakeword')
        self.assertEqual(len(p.events), 2)

    def test_other_engine_cannot_overwrite_same_engine_correlation_window(self):
        d, p = self.dispatcher()
        d.submit('tulong', .9, 'openwakeword')
        self.now = 1002.05  # Existing test cooldown=2, correlation=2.2.
        d.submit('tulong', .75, 'vosk')
        self.now = 1002.1
        d.submit('help', .9, 'openwakeword')
        self.assertEqual(p.events, [('tulong', .9, 'openwakeword'), ('tulong', .75, 'vosk')])
