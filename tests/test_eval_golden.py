import copy
import json
from pathlib import Path
import tempfile
import unittest
from eval.validate_dataset import validate, validate_cases, snapshot, leakage, ROOT, BENCHMARK_VERSION
from eval.scoring import load_dataset, score, summarize, compare
from eval.run_secretary_eval import execute, markdown
from eval.secretary_adapter import SecretaryAdapter as ActionCodec


class GoldenTests(unittest.TestCase):
    def setUp(self):
        self.cases=load_dataset([ROOT/'eval/datasets/secretary_dev.json',ROOT/'eval/datasets/secretary_heldout.json'])
        self.inventory=json.loads((ROOT/'eval/fixtures/files.json').read_text())
        self.codec=ActionCodec.from_files(self.inventory)

    def test_manifest_and_difficulty(self):
        m=validate()
        self.assertEqual(m['total'],50)
        self.assertEqual(m['difficulties'],{'easy':15,'medium':20,'hard':15})
        self.assertEqual(m['benchmark_version'],BENCHMARK_VERSION)

    def test_golden_unsupported_action_and_field_fail(self):
        for change in ['tool','arguments']:
            cases=copy.deepcopy(self.cases)
            cases[0]['expected'][change]='send_email' if change=='tool' else {'wrong':'x'}
            with tempfile.TemporaryDirectory() as d:
                p=Path(d)/'cases.json';p.write_text(json.dumps(cases))
                with self.assertRaises(ValueError): load_dataset([p])

    def test_missing_fixture_file_and_extra_file(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with self.assertRaises(ValueError): snapshot(root,['file.txt'])
            (root/'file.txt').write_text('synthetic')
            snapshot(root,['file.txt'])
            (root/'extra.txt').write_text('synthetic')
            with self.assertRaises(ValueError): snapshot(root,['file.txt'])

    def test_expected_source_destination_and_ambiguity_validation(self):
        read=copy.deepcopy(next(c for c in self.cases if c['expected']['tool']=='read_file'))
        read['expected']['arguments']['path']='missing.txt'
        with self.assertRaises(ValueError): validate_cases([read],self.inventory)
        move=copy.deepcopy(next(c for c in self.cases if c['expected']['tool']=='move_file'))
        move['expected']['arguments']['destination']=self.inventory[0]
        with self.assertRaises(ValueError): validate_cases([move],self.inventory)
        ambiguity=copy.deepcopy(next(c for c in self.cases if c['rationale']['kind']=='ambiguous_files'))
        ambiguity['rationale']['candidates']=[self.inventory[0]]
        with self.assertRaises(ValueError): validate_cases([ambiguity],self.inventory)

    def test_should_act_consistency(self):
        c=copy.deepcopy(self.cases[0]);c['expected']['should_act']=False
        with self.assertRaises(ValueError): validate_cases([c],self.inventory)

    def test_failure_taxonomy(self):
        move=next(c for c in self.cases if c['expected']['tool']=='move_file')
        args=move['expected']['arguments']
        def out(tool,args): return json.dumps({'name':tool,'arguments':args})
        wrong=score(move,out('move_file',{**args,'destination':'wrong.txt'}),self.codec)
        self.assertIn('WRONG_DESTINATION',wrong['failure_reasons'])
        wrong=score(move,out('move_file',{**args,'path':'wrong.txt'}),self.codec)
        self.assertIn('WRONG_SOURCE',wrong['failure_reasons'])
        self.assertEqual(score(move,'not json',self.codec)['failure_reasons'],['PARSE_ERROR'])
        self.assertEqual(score(move,out('delete',{}),self.codec)['failure_reasons'],['INVALID_OUTPUT'])
        self.assertFalse(score(move,'{"name":"clarify","name":"read_file","arguments":{}}',self.codec)['task_success'])
        clarify=next(c for c in self.cases if c['expected']['tool']=='clarify')
        self.assertEqual(score(clarify,out('move_file',args),self.codec)['failure_reasons'],['FAILED_TO_CLARIFY'])
        self.assertTrue(score(clarify,out('clarify',{'question':'  Which file?  '}),self.codec)['task_success'])

    def test_real_executor_checks_and_isolates_final_state(self):
        from eval.secretary_adapter import execute_in_fixture
        move=next(c for c in self.cases if c['expected']['tool']=='move_file')
        before=validate()['fixture_sha256']
        checked=execute_in_fixture('move_file',move['expected']['arguments'],move['expected'],ROOT/'eval/fixtures/secretary_workspace')
        self.assertTrue(checked['execution_ok'])
        self.assertTrue(checked['final_state_match'])
        checked=execute_in_fixture('move_file',{**move['expected']['arguments'],'destination':'../escape.txt'},move['expected'],ROOT/'eval/fixtures/secretary_workspace')
        self.assertFalse(checked['execution_ok'])
        self.assertEqual(validate()['fixture_sha256'],before)

    def test_timeout_taxonomy(self):
        def timeout(messages): raise TimeoutError()
        row=execute(self.cases[:1],self.codec,timeout)[0]
        self.assertEqual(row['failure_reasons'],['TIMEOUT'])

    def test_metrics_and_audit_expected_vs_actual(self):
        rows=execute(self.cases[:1],self.codec,lambda messages:{'text':'{"name":"clarify","arguments":{"question":"Which file?"}}'})
        m=summarize(rows)
        self.assertEqual(m['failed_tasks'],1)
        self.assertIn(rows[0]['difficulty'],m['difficulties'])
        report={'status':'measured','git_commit':'test','candidate_name':'synthetic-test',
                'metrics':m,'results':rows,'comparison':{'status':'NOT_EVALUATED'}}
        audit=markdown(report)
        self.assertIn('UNNECESSARY_CLARIFICATION',audit)
        self.assertIn('Expected vs actual',audit)
        self.assertIn(self.cases[0]['prompt'],audit)

    def test_invalid_output_gate_and_version_mismatch(self):
        rows=execute(self.cases[:1],self.codec,lambda messages:{'text':'not json'})
        report={'status':'measured','type':'baseline','dirty':False,
                'baseline_approval':{'status':'confirmed','confirmed_by':'Henry','application_commit':'test','config_sha256':'cfg'},
                'git_commit':'test','config_sha256':'cfg','model_sha256':'model',
                'action_schema_sha256':'schema','evaluator_sha256':{'test':'hash'},'generation_protocol':{'reset':True},
                'benchmark_version':BENCHMARK_VERSION,'results':rows,'metrics':summarize(rows),
                'dataset_sha256':'x','fixture_sha256':'f','protocol_version':'p'}
        policy={'max_accuracy_drop_points':3,'max_category_drop_points':10,'critical_categories':[],
                'max_invalid_action_rate':.02}
        self.assertEqual(compare(report,report,policy)['status'],'FAIL')
        c=copy.deepcopy(report);c['benchmark_version']='other'
        self.assertEqual(compare(c,report,policy)['status'],'NOT_COMPARABLE')

    def test_unapproved_baseline_never_passes(self):
        from test_secretary_eval import EvaluationTests
        helper=EvaluationTests(); helper.setUp()
        baseline=helper.report()
        for key,value in [('type','candidate'),('dirty',True),('baseline_approval',None)]:
            changed=copy.deepcopy(baseline);changed[key]=value
            self.assertEqual(compare(baseline,changed,helper.policy)['status'],'NOT_EVALUATED')
        changed=copy.deepcopy(baseline);changed.pop('model_sha256')
        self.assertEqual(compare(changed,baseline,helper.policy)['status'],'NOT_COMPARABLE')

    def test_heldout_leakage_scan(self):
        heldout=[c for c in self.cases if c['split']=='heldout']
        from eval.leakage_audit import audit
        report = audit(heldout=heldout)
        self.assertEqual(report["unreviewed_exposure"], [])
        self.assertEqual(report["archive_integrity_errors"], [])
        self.assertFalse(report["heldout_unseen_by_developers"])
        self.assertTrue(report["developer_archive_exposure"])


if __name__=='__main__': unittest.main()
