"""A cheap probe must be cheap, bounded, and unable to masquerade as evidence."""
import subprocess

import pytest

from turbo.optimizer import probe

QAIRT = {'backend': 'qairt_npu', 'plugin': 'qairt', 'model_path': 'local/bundle',
         'max_tokens': 128, 'stop_after_tool_call': True}


class FakeCompleted:
    def __init__(self, returncode, stderr=''):
        self.returncode, self.stderr, self.stdout = returncode, stderr, ''


def test_static_precheck_mirrors_the_runner_and_the_native_layer():
    assert probe.config_acceptable(QAIRT, 'qairt_npu') == []
    assert probe.config_acceptable(dict(QAIRT, threads=8), 'qairt_npu')
    assert probe.config_acceptable(dict(QAIRT, top_k=4), 'qairt_npu')
    assert probe.config_acceptable(dict(QAIRT, grammar=True), 'qairt_npu')
    cpu = {'backend': 'llama_cpp_cpu', 'model_path': 'm.gguf', 'stop_after_tool_call': True}
    assert probe.config_acceptable(cpu, 'llama_cpp_cpu')


def test_a_successful_startup_reports_load_time_and_no_correctness_claim():
    record = probe.run_startup_probe(['true'], timeout_s=5,
                                     runner=lambda *a, **k: FakeCompleted(0))
    assert record['outcome'] == probe.LOADED and record['loaded'] is True
    assert record['startup_seconds'] is not None
    assert record['correctness_claim'] is False


def test_a_refusal_is_distinguished_from_a_crash():
    refused = probe.run_startup_probe(
        ['x'], timeout_s=5,
        runner=lambda *a, **k: FakeCompleted(2, 'error: Unknown configuration keys: top_k'))
    crashed = probe.run_startup_probe(
        ['x'], timeout_s=5, runner=lambda *a, **k: FakeCompleted(139, 'Segmentation fault'))
    assert refused['outcome'] == probe.REFUSED
    assert crashed['outcome'] == probe.CRASHED
    assert 'top_k' in refused['runtime_error']


def test_a_timeout_reports_no_duration_rather_than_a_fabricated_one():
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd='x', timeout=1)
    record = probe.run_startup_probe(['x'], timeout_s=1, runner=timeout)
    assert record['outcome'] == probe.TIMED_OUT and record['startup_seconds'] is None


def test_a_probe_that_cannot_launch_raises_rather_than_reporting_a_pass():
    def missing(*args, **kwargs):
        raise OSError('No such file')
    with pytest.raises(probe.ProbeUnavailable):
        probe.run_startup_probe(['x'], timeout_s=1, runner=missing)


def test_a_shell_string_is_refused():
    with pytest.raises(ValueError):
        probe.run_startup_probe('python -c pass', timeout_s=1)


def test_the_subset_is_fixed_before_the_session_and_never_adapts():
    cases = ['case-%02d' % i for i in range(35)]
    first = probe.fixed_subset(cases, 8, seed_label='AT-123')
    assert first == probe.fixed_subset(cases, 8, seed_label='AT-123')
    assert first != probe.fixed_subset(cases, 8, seed_label='AT-124')
    assert len(first) == 8 and set(first) <= set(cases)
    assert probe.fixed_subset(cases, 8, seed_label='AT-123') == sorted(first)


def test_an_oversized_or_empty_subset_is_refused():
    with pytest.raises(ValueError):
        probe.fixed_subset(['a', 'b'], 5, seed_label='x')
    with pytest.raises(ValueError):
        probe.fixed_subset(['a', 'b'], 0, seed_label='x')


def test_a_canary_labels_itself_and_refuses_to_be_promotion_evidence():
    record = probe.canary_result(subset=['a', 'b', 'c'], correct=2, attempted=3, invalid=0,
                                 median_latency_ms=540.0)
    assert record['label'] == probe.DIAGNOSTIC_LABEL
    assert record['qualified'] is False and record['promotion_evidence'] is False
    assert record['split'] == 'development'
    assert 'promotion requires a tracked development run' in probe.refuse_as_evidence(record).lower()


def test_a_canary_must_attempt_every_case_it_declares():
    with pytest.raises(ValueError):
        probe.canary_result(subset=['a', 'b', 'c'], correct=1, attempted=2, invalid=0,
                            median_latency_ms=1.0)
