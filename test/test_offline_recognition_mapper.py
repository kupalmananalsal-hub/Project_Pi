"""Synthetic app-shaped engine metadata; no engines, audio or application imports."""
import ast
from copy import deepcopy
import itertools
import json
from pathlib import Path
import threading
import types
import unittest

try:
    from experiments.offline_recognition_mapper import OfflineRecognitionHarness
except ModuleNotFoundError as exc:
    if exc.name != 'experiments.offline_recognition_mapper': raise
    OfflineRecognitionHarness = None

ROOT=Path(__file__).resolve().parents[1]


def source_vocabulary():
    tree=ast.parse((ROOT/'raspberry_pi/kws/kws_alert_dual.py').read_text())
    node=next(n for n in tree.body if isinstance(n,ast.AnnAssign) and getattr(n.target,'id',None)=='TAGALOG_KEYWORD_ALIASES')
    original=ast.literal_eval(node.value)
    return [[keyword,sorted(aliases)] for keyword,aliases in original.items()], original, tree


def meta(identity='v1',sequence=1,revision=1,candidate='call',generation='g1'):
    return dict(observation_id=identity,producer_id='fixture',generation_id=generation,
        candidate_id=candidate,sequence=sequence,revision=revision,
        observed_at='2026-11-02T04:00:00+00:00',clock_domain='fixture',
        capture_range={'first':1,'last':2})


def oww(score=.6,*,detected=True):
    row=dict(name='help',raw_name='help_model',score=score,threshold=.3)
    return dict(available=True,is_speech=True,scores=[row],
                wake_words=[deepcopy(row)] if detected else [],vad_score=.9,error=None)


class OfflineMappingTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(OfflineRecognitionHarness,'C1.54 mapper is absent')
        self.aliases,self.original_aliases,self.tree=source_vocabulary()
        self.harness=self.fresh()

    def fresh(self):
        h=OfflineRecognitionHarness(self.aliases)
        for engine in ('vosk','snowboy','openwakeword'):h.begin_generation(engine,'fixture','g1')
        return h

    def snow(self,context=None,result=1):
        return self.harness.snowboy(context or meta('s1'),result,
            config={'keywords':['help'],'alert_keyword':'help','confidence':.95})

    def test_vosk_partial_then_ordinary_final_preserves_raw_and_revision(self):
        raw=' {"partial": "TULONG", "fixture_extra": [true, 1, 1.0]} '
        first=self.harness.vosk(meta(),raw,final=False)
        final=self.harness.vosk(meta('v2',2,2),'{"text":"tulog"}',final=True)
        self.assertEqual(first['original_payload']['raw_json'],raw)
        self.assertEqual(first['status'],'partial');self.assertEqual(first['keyword'],'tulong')
        self.assertEqual(final['status'],'final');self.assertIsNone(final['keyword'])
        self.assertEqual(self.harness.snapshot()['candidates'][0]['revision_history'],['v1','v2'])

    def test_partial_only_has_no_final_or_confidence_or_authority(self):
        record=self.harness.vosk(meta(),'{"partial":"tulong"}',final=False)
        self.assertIsNone(record['confidence']);self.assertEqual(record['score_state'],'missing')
        self.assertEqual(record['status'],'partial');self.assertNotIn('decision_state',record)

    def test_final_distress_keeps_word_confidences_raw_without_aggregation(self):
        payload={'text':'tulong','result':[{'word':'tulong','conf':.91,'start':1.,'end':1.4}]}
        record=self.harness.vosk(meta(),json.dumps(payload),final=True,
            application_context={'configured_confidence':.75,'verifier_used':False})
        self.assertEqual(record['keyword'],'tulong');self.assertIsNone(record['confidence'])
        self.assertEqual(record['original_payload']['engine_output'],payload)
        self.assertEqual(record['original_payload']['application_context']['configured_confidence'],.75)

    def test_vocabulary_and_precedence_match_existing_pure_matcher(self):
        nodes=[n for n in self.tree.body if isinstance(n,ast.FunctionDef) and n.name in ('_normalize_vosk_text','detect_tagalog_keyword')]
        ns={'TAGALOG_KEYWORD_ALIASES':self.original_aliases}
        exec(compile(ast.Module(body=nodes,type_ignores=[]),'source-matcher','exec'),ns)
        phrases=[alias for _,aliases in self.aliases for alias in aliases]+['TULONG!','ang sakitness','tul','tulog','aray tulong','masakit','hello']
        for i,text in enumerate(phrases,1):
            record=self.harness.vosk(meta('v'+str(i),i,1,'case'+str(i)),json.dumps({'text':text}),final=True)
            self.assertEqual(record['keyword'],ns['detect_tagalog_keyword'](text),text)

    def test_malformed_vosk_json_and_flags_are_atomic(self):
        for raw,flag in [('{bad',False),('[]',False),('{"partial":4}',False),('{"text":"tulong"}',False),('{"partial":"a","partial":"b"}',False),('{"partial":"tulong","x":NaN}',False),('{"partial":"tulong"}',1)]:
            before=self.harness.snapshot()
            with self.subTest(raw=raw,flag=flag):
                with self.assertRaises(ValueError):self.harness.vosk(meta(),raw,final=flag)
                self.assertEqual(self.harness.snapshot(),before)

    def test_snowboy_positive_has_no_engine_confidence_or_asr_finality(self):
        record=self.snow()
        self.assertEqual(record['status'],'detection');self.assertEqual(record['keyword'],'help')
        self.assertIsNone(record['confidence'])
        self.assertEqual(record['original_payload']['engine_output'],1)
        self.assertEqual(record['original_payload']['config']['confidence'],.95)

    def test_snowboy_engine_label_and_application_alert_label_are_distinct(self):
        record=self.harness.snowboy(meta('s1'),1,config={'keywords':['spoken-help'],'alert_keyword':'configured-alert','confidence':.95})
        self.assertEqual(record['keyword'],'spoken-help')
        self.assertEqual(record['original_payload']['config']['alert_keyword'],'configured-alert')

    def test_snowboy_zero_is_no_detection_not_silence_or_failure(self):
        record=self.snow(meta('s0',revision=None,candidate=None),0)
        self.assertEqual(record['status'],'no_detection');self.assertEqual(record['health'],'healthy')
        self.assertEqual(self.harness.snapshot()['candidates'],[])

    def test_snowboy_error_code_is_gap_not_declared_generation_death(self):
        record=self.snow(meta('se',revision=None,candidate=None),-1)
        self.assertEqual(record['status'],'gap');self.assertEqual(record['health'],'unknown')
        self.snow(meta('s2',2),1)
        self.assertEqual(self.harness.snapshot()['candidates'][0]['keyword'],'help')

    def test_snowboy_invalid_index_bool_and_config_do_not_mutate(self):
        for result in (True,1.0,2):
            before=self.harness.snapshot()
            with self.assertRaises(ValueError):self.snow(result=result)
            self.assertEqual(self.harness.snapshot(),before)

    def test_openwakeword_score_and_detector_metadata_are_preserved(self):
        payload=oww();record=self.harness.openwakeword(meta('o1'),payload,model_name='help_model')
        self.assertEqual(record['confidence'],.6);self.assertEqual(record['status'],'score')
        self.assertEqual(record['original_payload']['engine_output'],payload)
        self.assertTrue(record['original_payload']['reported_detection'])

    def test_openwakeword_below_threshold_score_is_data_not_an_alert(self):
        record=self.harness.openwakeword(meta('o1'),oww(.1,detected=False),model_name='help_model')
        self.assertEqual(record['confidence'],.1)
        self.assertFalse(record['original_payload']['reported_detection'])
        self.assertNotIn('event_id',record)

    def test_openwakeword_no_score_and_nonspeech_are_missing_not_zero(self):
        payload=oww();payload.update(scores=[],wake_words=[],is_speech=False)
        record=self.harness.openwakeword(meta('o1',revision=None),payload,model_name='help_model')
        self.assertEqual(record['status'],'missing');self.assertIsNone(record['confidence'])
        self.assertEqual(record['health'],'healthy')

    def test_missing_openwakeword_score_retains_previous_candidate(self):
        self.harness.openwakeword(meta('o1'),oww(),model_name='help_model')
        payload=oww(None,detected=False)
        record=self.harness.openwakeword(meta('o2',2,None),payload,model_name='help_model')
        self.assertEqual(record['status'],'missing')
        candidate=self.harness.snapshot()['candidates'][0]
        self.assertEqual(candidate['confidence'],.6);self.assertEqual(candidate['evidence_observation_id'],'o1')

    def test_unavailable_openwakeword_does_not_invent_engine_restart(self):
        payload=oww();payload.update(available=False,scores=[],wake_words=[],error='synthetic unavailable')
        record=self.harness.openwakeword(meta('o1',revision=None),payload,model_name='help_model')
        self.assertEqual(record['status'],'missing');self.assertEqual(record['health'],'unavailable')
        self.harness.openwakeword(meta('o2',2),oww(),model_name='help_model')

    def test_unavailable_prediction_preserves_empty_exception_message(self):
        payload=dict(available=False,is_speech=True,scores=[],wake_words=[],vad_score=1.0,error=str(RuntimeError()))
        try:
            record=self.harness.openwakeword(meta('o1',revision=None),payload,model_name='help_model')
        except ValueError as exc:
            self.fail('runtime str(exc) may be empty and must remain representable: '+str(exc))
        self.assertEqual(record['status'],'missing')
        self.assertEqual(record['health'],'unavailable')
        self.assertEqual(record['original_payload']['engine_output']['error'],'')

    def test_openwakeword_malformed_scores_rows_and_metadata_are_atomic(self):
        for score in (True,'0.6',float('nan'),1.1):
            before=self.harness.snapshot()
            with self.subTest(score=repr(score)):
                with self.assertRaises(ValueError):self.harness.openwakeword(meta('o1'),oww(score),model_name='help_model')
                self.assertEqual(self.harness.snapshot(),before)
        for mutate in ('duplicate','contradictory','audio'):
            payload=oww()
            if mutate=='duplicate':payload['scores'].append(deepcopy(payload['scores'][0]))
            if mutate=='contradictory':payload['wake_words'][0]['score']=.7
            if mutate=='audio':payload['cleaned_audio']=object()
            with self.assertRaises(ValueError):self.harness.openwakeword(meta('o1'),payload,model_name='help_model')

    def test_both_independent_help_sources_survive_vosk_ordinary_speech(self):
        for source in ('snowboy','openwakeword'):
            h=self.fresh();h.vosk(meta(),'{"partial":"tulong"}',final=False)
            h.vosk(meta('v2',2,2),'{"text":"tulog"}',final=True)
            if source=='snowboy':h.snowboy(meta('s1'),1,config={'keywords':['help'],'alert_keyword':'help','confidence':.95})
            else:h.openwakeword(meta('o1'),oww(),model_name='help_model')
            view=next(v for v in h.snapshot()['candidates'] if v['engine']==source)
            self.assertEqual(view['keyword'],'help')

    def test_explicit_failure_requires_explicit_new_generation(self):
        self.harness.vosk(meta(),'{"partial":"tulong"}',final=False)
        self.harness.failure(meta('f1',2,None),engine='vosk',error={'exception_type':'RuntimeError','message':'synthetic'})
        before=self.harness.snapshot()
        with self.assertRaises(ValueError):self.harness.vosk(meta('v2',3,2),'{"text":"tulong"}',final=True)
        self.assertEqual(self.harness.snapshot(),before)
        self.harness.begin_generation('vosk','fixture','g2')
        self.harness.vosk(meta('v3',generation='g2'),'{"partial":"tulong"}',final=False)
        self.assertEqual(len(self.harness.snapshot()['candidates']),2)

    def test_duplicate_retry_and_conflicting_raw_identity_are_atomic(self):
        raw='{"partial":"tulong"}';self.harness.vosk(meta(),raw,final=False)
        before=self.harness.snapshot();self.harness.vosk(meta(),raw,final=False)
        self.assertEqual(self.harness.snapshot(),before)
        with self.assertRaises(ValueError):self.harness.vosk(meta(),' {"partial":"tulong"}',final=False)
        self.assertEqual(self.harness.snapshot(),before)

    def test_out_of_order_and_candidate_revision_conflicts_are_atomic(self):
        self.harness.vosk(meta(),'{"partial":"tulong"}',final=False);before=self.harness.snapshot()
        for context in (meta('v2',1,2),meta('v2',2,3)):
            with self.assertRaises(ValueError):self.harness.vosk(context,'{"partial":"tulong"}',final=False)
            self.assertEqual(self.harness.snapshot(),before)

    def test_actual_cooldown_rejection_maps_only_a_supplied_receipt(self):
        node=next(n for n in self.tree.body if isinstance(n,ast.ClassDef) and n.name=='CooldownGate')
        clock=types.SimpleNamespace(now=1000.)
        ns={'threading':threading,'time':types.SimpleNamespace(monotonic=lambda:clock.now)}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'source-cooldown','exec'),ns)
        gate=ns['CooldownGate'](2.0);self.assertTrue(gate.allow('tulong'))
        clock.now=1000.1;self.assertFalse(gate.allow('tulong'))
        self.harness.vosk(meta(),'{"partial":"tulong"}',final=False)
        before=self.harness.snapshot()
        self.harness.publication_receipt(dict(receipt_id='r1',observation_id='v1',outcome='rejected',
            observed_at=meta()['observed_at'],clock_domain='fixture',reason='fixture: actual gate returned False'))
        after=self.harness.snapshot();self.assertEqual(after['candidates'],before['candidates'])
        self.snow();self.assertEqual(len(self.harness.snapshot()['candidates']),2)

    def test_interleaved_independent_engines_have_deterministic_outcomes(self):
        expected=None;count=0
        for order in itertools.permutations(range(4)):
            if order.index(0)>order.index(1):continue
            h=self.fresh()
            steps=[lambda:h.vosk(meta(),'{"partial":"tulong"}',final=False),
                lambda:h.vosk(meta('v2',2,2),'{"text":"tulog"}',final=True),
                lambda:h.snowboy(meta('s1'),1,config={'keywords':['help'],'alert_keyword':'help','confidence':.95}),
                lambda:h.openwakeword(meta('o1'),oww(),model_name='help_model')]
            for index in order:steps[index]()
            if expected is None:expected=h.snapshot()
            self.assertEqual(h.snapshot(),expected);count+=1
        self.assertEqual(count,12)

    def test_input_config_output_mutation_does_not_change_evidence(self):
        payload=oww();context=meta('o1');record=self.harness.openwakeword(context,payload,model_name='help_model')
        before=self.harness.snapshot();payload['scores'][0]['score']=.1
        context['capture_range']['last']=999;record['keyword']='changed'
        record['original_payload']['engine_output']['scores'].clear()
        snapshot=self.harness.snapshot();snapshot['observations'].clear()
        self.assertEqual(self.harness.snapshot(),before)

    def test_mapping_has_no_runtime_import_io_clock_or_publication_callback(self):
        import experiments.offline_recognition_mapper as mapper
        tree=ast.parse(Path(mapper.__file__).read_text());imports=set()
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):imports.update(a.name for a in node.names)
            if isinstance(node,ast.ImportFrom):imports.add(node.module)
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Name):self.assertNotIn(node.func.id,{'open','exec','eval','__import__'})
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute):self.assertNotIn(node.func.attr,{'now','publish','post','connect','system','Popen'})
        self.assertLessEqual(imports,{'json','math','experiments.recognition_observation_contract'})


if __name__=='__main__':unittest.main()
