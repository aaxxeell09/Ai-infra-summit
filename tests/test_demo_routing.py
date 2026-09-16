"""Public-demo routing must disclose policy and reject resolver fallback."""
import copy
import unittest
from unittest.mock import patch

from turbo.demo_routing import choose_route, resolved_matches


class Runtime:
    def __init__(self, unavailable=()):
        self.unavailable = unavailable
    def resolve_device(self, plugin, device):
        if plugin in self.unavailable:
            raise RuntimeError('Plugin unavailable')
        return ({('qairt', 'npu'): 'NPU', ('llama_cpp', 'npu'): 'HTP0',
                 ('llama_cpp', 'gpu'): 'GPUOpenCL', ('llama_cpp', 'cpu'): 'CPU'}[(plugin, device)], 99, None)


class RoutingTests(unittest.TestCase):
    def rows(self):
        from turbo.demo_routing import ROUTES
        return [dict(id=i, model_id=m, plugin=p, device=d, backend_id=b, available=True, reason='registered')
                for i, _, m, p, d, b, _ in ROUTES]
    def choose(self, prompt='quick', selection='auto', runtime=None, rows=None):
        with patch('turbo.demo_routing.catalog', return_value=copy.deepcopy(self.rows() if rows is None else rows)):
            return choose_route({}, {'prompt_id': prompt, 'routing': {'selection': selection}}, runtime or Runtime())
    def test_auto_selects_small_qairt_and_larger_cpu_with_disclosure(self):
        small, decision = self.choose()
        large, _ = self.choose(prompt='reasoning')
        self.assertEqual(small['id'], 'qwen06-qairt')
        self.assertEqual(large['id'], 'qwen4b-cpu')
        self.assertEqual(decision['quality'], 'not_calibrated')
        self.assertFalse(decision['fastest_claim'])
    def test_unavailable_qairt_records_reason_then_checks_htp(self):
        selected, decision = self.choose(runtime=Runtime(['qairt']))
        self.assertEqual(selected['id'], 'qwen06-htp')
        failed = decision['candidates'][0]
        self.assertFalse(failed['available'])
        self.assertEqual(failed['reason'], 'Plugin unavailable')
    def test_explicit_route_and_large_policy_do_not_silently_downgrade(self):
        with self.assertRaises(ValueError):
            self.choose(selection='qwen06-qairt', runtime=Runtime(['qairt']))
        rows = self.rows(); rows[-1]['available'] = False
        with self.assertRaises(ValueError):
            self.choose(prompt='reasoning', rows=rows)
    def test_conflicting_resolver_is_rejected_and_not_dispatch_proof(self):
        runtime = Runtime(); runtime.resolve_device = lambda *args: ('CPU', 0, None)
        with self.assertRaises(ValueError): self.choose(selection='qwen06-gpu', runtime=runtime)
        self.assertTrue(resolved_matches('llama_cpp_gpu', 'GPUOpenCL'))
        self.assertFalse(resolved_matches('llama_cpp_htp', None))
        self.assertFalse(resolved_matches('qairt_npu', 'CPU'))
