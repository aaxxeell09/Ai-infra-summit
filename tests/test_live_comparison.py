"""Presentation adapter: exact config, cancellation, partial failure, isolation."""
import copy
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from turbo.live_comparison import LiveComparisons, ROOT, PROMPTS, _hash, _manifest_hashes


class Engine:
    def __init__(self, directory):
        self.config = {'live_comparison_enabled': True, 'data_dir': directory, 'sdk_dir': 'unused'}
        self.lock = threading.RLock()
        self.runtime = object()
        self.tuning_process = None
        self.loaded = {}


class Model:
    instances = []
    fail_threads = None
    block = None
    def __init__(self, runtime, path, **config):
        self.config = config
        self.closed = False
        self.instances.append(self)
    def provenance(self):
        return {'backend_id': 'llama_cpp_cpu'}
    def chat(self, messages, **kwargs):
        if self.block:
            self.block.wait(2)
        if self.config['threads'] == self.fail_threads:
            raise RuntimeError('native failure in second lane')
        kwargs['on_token']('Local ')
        kwargs['on_token']('answer')
        return {'text': 'Local answer', 'profile': {'ttft': 1200, 'generated_tokens': 2, 'decoding_speed': 30, 'stop_reason': 'eos'},
                'timings': {'total': 0.2}, 'sampling': {'requested_temperature': 0, 'sdk_top_k': 0}}
    def close(self):
        self.closed = True


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = Engine(self.temp.name)
        self.manager = LiveComparisons(self.engine, model_factory=Model)
        self.identity = patch.object(self.manager, '_identity', return_value=('qwen06', {'path': 'model.gguf'}, {'sha256': 'sdk'}))
        self.identity.start()
        self.git = patch('turbo.live_comparison.subprocess.check_output', side_effect=lambda args, **kw: 'commit\n' if args[1]=='rev-parse' else '')
        self.git.start()
        Model.instances, Model.fail_threads, Model.block = [], None, None
        self.request = {'schema_version': 'local-turbo.comparison-request.v1', 'request_id': 'test-1',
                        'comparison': 'speed', 'execution': 'sequential', 'prompt_id': 'quick', 'prompt': PROMPTS['quick']}
        for lane, cell in [('baseline', 'cpu-t0'), ('selected', 'cpu-t10')]:
            self.request[lane] = {'cell_id': cell, 'model': self.manager.manifest['model_name'],
                'model_sha256': self.manager.manifest['model_sha256'], 'runtime_sha256': self.manager.manifest['runtime_sha256'],
                'plugin': 'llama_cpp', 'requested_device': 'cpu', 'source_sha256': _hash(self.manager.source/'sweep.json'),
                'params': json.loads((self.manager.source/(cell+'.json')).read_text())['params']}
    def tearDown(self):
        if Model.block:
            Model.block.set()
        if self.manager.active:
            self.manager.cancel(self.manager.active)
            self.finish()
        self.git.stop()
        self.identity.stop()
        self.temp.cleanup()
    def finish(self):
        for _ in range(200):
            state = self.manager.snapshot('test-1')
            if state['state'] != 'running':
                return state
            time.sleep(.005)
        self.fail('Worker did not reconcile')
    def test_actual_configuration_and_native_metrics_preserved(self):
        self.manager.start(self.request)
        state = self.finish()
        self.assertEqual(state['state'], 'completed')
        self.assertEqual([m.config['threads'] for m in Model.instances], [0, 10])
        self.assertTrue(all(m.closed for m in Model.instances))
        self.assertEqual([e['lane'] for e in state['events'] if e['type']=='complete'], ['default','turbo'])
        result=state['result']; lane=result['lanes']['turbo']
        self.assertEqual(lane['ttft_ms'], 1.2)
        self.assertEqual(lane['output_tokens'], 2)
        self.assertTrue(lane['configuration_applied'])
        self.assertIsNone(result['winner'])
        self.assertIsNone(result['speedup'])
        self.assertIsNone(lane['energy'])
        self.assertTrue((Path(self.temp.name)/'live-comparisons/test-1/result.json').is_file())
    def test_request_identity_and_configuration_are_not_trusted(self):
        for field, value in [('model_sha256', 'wrong'), ('runtime_sha256', 'wrong'), ('requested_device','auto')]:
            request=copy.deepcopy(self.request); request['selected'][field]=value
            with self.assertRaises(ValueError): self.manager.start(request)
        request=copy.deepcopy(self.request);request['selected']['params']['n_threads']=12
        with self.assertRaises(ValueError): self.manager.start(request)
        request=copy.deepcopy(self.request);request['comparison']='routing'
        with self.assertRaises(ValueError): self.manager.start(request)
        self.assertEqual(Model.instances, [])
    def test_partial_first_lane_survives_second_failure(self):
        Model.fail_threads=10
        self.manager.start(self.request);state=self.finish()
        self.assertEqual(state['state'], 'failed')
        self.assertEqual(state['result']['lanes']['default']['status'], 'completed')
        self.assertEqual(state['result']['lanes']['turbo']['status'], 'failed')
        self.assertTrue(all(m.closed for m in Model.instances))
    def test_cancel_does_not_free_device_until_native_cleanup(self):
        Model.block=threading.Event()
        self.manager.start(self.request)
        for _ in range(100):
            if Model.instances: break
            time.sleep(.005)
        state=self.manager.cancel('test-1')
        self.assertEqual(state['state'],'running')
        other=copy.deepcopy(self.request);other['request_id']='another'
        with self.assertRaises(ValueError): self.manager.start(other)
        Model.block.set();state=self.finish()
        self.assertEqual(state['state'], 'cancelled')
        self.assertEqual(len(Model.instances), 1)
        self.assertTrue(Model.instances[0].closed)
        self.assertIsNone(self.manager.active)
    def test_duplicate_id_is_idempotent_but_different_inputs_rejected(self):
        self.manager.start(self.request);self.finish()
        self.manager.start(self.request)
        self.assertEqual(len(Model.instances), 2)
        changed=copy.deepcopy(self.request);changed['prompt_id']='reasoning';changed['prompt']=PROMPTS['reasoning']
        with self.assertRaises(ValueError): self.manager.start(changed)
    def test_gateway_other_work_prevents_overlapping_inference(self):
        ready=threading.Event();release=threading.Event()
        def hold():
            with self.engine.lock:
                ready.set();release.wait(2)
        thread=threading.Thread(target=hold);thread.start();ready.wait(1)
        try:
            self.manager.start(self.request);state=self.finish()
            self.assertEqual(state['state'], 'failed')
            self.assertEqual(Model.instances, [])
        finally:
            release.set();thread.join()
    def test_disabled_adapter_cannot_launch(self):
        self.manager.enabled=False
        with self.assertRaises(ValueError): self.manager.start(self.request)
        self.assertFalse(self.manager.capabilities()['available'])

    def test_git_line_endings_are_portable_but_content_changes_are_rejected(self):
        import hashlib
        path = Path(self.temp.name)/'manifest.json'
        lf = b'{\n  "value": 1\n}\n'
        path.write_bytes(lf.replace(b'\n', b'\r\n'))
        self.assertIn(hashlib.sha256(lf).hexdigest(), _manifest_hashes(path))
        self.assertNotIn(hashlib.sha256(lf.replace(b'1', b'2')).hexdigest(), _manifest_hashes(path))
        self.request['baseline']['source_sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            self.manager.start(self.request)

if __name__ == '__main__':
    unittest.main()
