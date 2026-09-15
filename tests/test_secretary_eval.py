import copy
import json
from pathlib import Path
import tempfile
import unittest

from eval.scoring import load_dataset, score, summarize, compare
from eval.run_secretary_eval import execute, PROTOCOL
from turbo.action_codec import ActionCodec

ROOT = Path(__file__).resolve().parents[1]


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.codec = ActionCodec.from_files(['a.txt', 'b.txt'])
        self.case = {'id':'read1', 'split':'development', 'category':'read', 'prompt':'Read a.txt',
                     'expected':{'tool':'read_file','arguments':{'path':'a.txt'},'clarification_required':False}}
        self.policy = {'max_accuracy_drop_points':3, 'max_category_drop_points':10,
                       'critical_categories':['read']}

    def test_dataset_split_and_fixture_references(self):
        dev = load_dataset([ROOT/'eval/datasets/secretary_dev.json'])
        heldout = load_dataset([ROOT/'eval/datasets/secretary_heldout.json'])
        self.assertEqual((len(dev),len(heldout)), (35,15))
        self.assertFalse({c['id'] for c in dev} & {c['id'] for c in heldout})
        files = set(json.loads((ROOT/'eval/fixtures/files.json').read_text()))
        for c in dev + heldout:
            if c['expected']['tool'] in {'read_file','move_file'}:
                self.assertIn(c['expected']['arguments'].get('path', c['expected']['arguments'].get('source')), files)

    def test_duplicate_cases_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'cases.json'
            path.write_text(json.dumps([self.case,self.case]))
            with self.assertRaises(ValueError): load_dataset([path])

    def test_tool_and_action_and_argument_selection(self):
        good = score(self.case, '{"r":0}', self.codec)
        self.assertTrue(good['task_success'])
        self.assertEqual(good['action'], 'read_file')
        wrong_path = score(self.case, '{"r":1}', self.codec)
        self.assertTrue(wrong_path['tool_correct'])
        self.assertFalse(wrong_path['arguments_correct'])
        self.assertFalse(score(self.case, '{"m":[0,"c.txt"]}', self.codec)['action_correct'])

    def test_move_path_normalization_preserves_semantics(self):
        case = copy.deepcopy(self.case)
        case['expected'] = {'tool':'move_file','arguments':{'source':'a.txt','destination':'archive/a.txt'},'clarification_required':False}
        self.assertTrue(score(case, json.dumps({'m':[0,'archive\\a.txt']}), self.codec)['task_success'])
        self.assertFalse(score(case, '{"m":[0,"archive/../a.txt"]}', self.codec)['task_success'])
        self.assertFalse(score(case, '{"m":[0,"ARCHIVE/a.txt"]}', self.codec)['task_success'])

    def test_clarification_and_unnecessary_action(self):
        case = copy.deepcopy(self.case)
        case['expected'] = {'tool':'clarify','arguments':{},'clarification_required':True}
        self.assertTrue(score(case, '{"q":"Which file?"}', self.codec)['task_success'])
        self.assertTrue(score(case, '{"r":0}', self.codec)['unnecessary_tool_call'])
        for output in ['{}','{"q":""}','not json','{"r":true}']:
            result = score(case, output, self.codec)
            self.assertFalse(result['task_success'])
            self.assertFalse(result['no_action_correct'])

    def report(self):
        rows = execute([self.case], self.codec, lambda messages:{'text':'{"r":0}'})
        rows[0]['latency_ms'] = 10
        return {'status':'measured','type':'baseline','dirty':False,
                'baseline_approval':{'status':'confirmed','confirmed_by':'Henry','application_commit':'test','config_sha256':'cfg'},
                'git_commit':'test','config_sha256':'cfg','model_sha256':'model','benchmark_version':'v2',
                'action_schema_sha256':'schema','evaluator_sha256':{'test':'hash'},'generation_protocol':{'reset':True},
                'dataset_sha256':'a','fixture_sha256':'b','protocol_version':PROTOCOL,
                'metrics':summarize(rows),'results':rows}

    def test_metric_denominators_and_errors(self):
        rows = execute([self.case]*20, self.codec, lambda messages:{'text':'{"r":1}'})
        for i,row in enumerate(rows): row['latency_ms'] = i+1
        m = summarize(rows)
        self.assertEqual(m['task_accuracy'],0)
        self.assertEqual(m['tool_accuracy'],100)
        self.assertEqual(m['median_latency_ms'],10.5)
        self.assertEqual(m['p95_latency_ms'],19)
        self.assertIsNone(summarize(rows[:2])['p95_latency_ms'])
        def fail(messages): raise TimeoutError('private location')
        row = execute([self.case],self.codec,fail)[0]
        self.assertEqual(row['execution_error'],'TimeoutError')
        self.assertFalse(row['task_success'])

    def test_gate_pass_fail_and_missing_baseline(self):
        baseline = self.report()
        self.assertEqual(compare(baseline, baseline, self.policy)['status'],'PASS')
        self.assertEqual(compare(baseline, None, self.policy)['status'],'NOT_EVALUATED')
        candidate = copy.deepcopy(baseline)
        candidate['results'][0]['task_success'] = False
        candidate['metrics'] = summarize(candidate['results'])
        result = compare(candidate, baseline, self.policy)
        self.assertEqual(result['status'],'FAIL')
        self.assertEqual(result['category_regressions'][0]['category'],'read')
        self.assertTrue(any('critical' in r for r in result['reasons']))

    def test_invalid_completion_is_counted_not_crashed(self):
        for value in [None, [], "text"]:
            row = execute([self.case], self.codec, lambda messages: value)[0]
            self.assertFalse(row['task_success'])
            self.assertEqual(row['execution_error'], 'ValueError')

    def test_development_subset_compares_only_matching_reference_rows(self):
        baseline = self.report()
        extra = copy.deepcopy(baseline['results'][0])
        extra['id'] = 'heldout1'
        extra['task_success'] = False
        baseline['results'].append(extra)
        baseline['metrics'] = summarize(baseline['results'])
        candidate = self.report()
        candidate['dataset_sha256'] = 'subset'
        self.assertEqual(compare(candidate, baseline, self.policy)['status'], 'PASS')
        candidate['results'][0]['case_sha256'] = 'changed expectation'
        self.assertEqual(compare(candidate, baseline, self.policy)['status'], 'NOT_COMPARABLE')

    def test_incompatible_benchmark_never_passes(self):
        baseline = self.report()
        for key in ['dataset_sha256','fixture_sha256','protocol_version']:
            candidate = copy.deepcopy(baseline)
            candidate[key] = 'changed'
            self.assertEqual(compare(candidate,baseline,self.policy)['status'],'NOT_COMPARABLE')


if __name__ == '__main__': unittest.main()
