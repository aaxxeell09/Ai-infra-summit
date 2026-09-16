"""Admission control must fail closed on every path that could corrupt evidence."""
import json
import tempfile
from pathlib import Path

import pytest

from turbo.optimizer import guard, search_space as space
from turbo.optimizer.state import config_hash

QAIRT = {'backend': 'qairt_npu', 'plugin': 'qairt', 'device': 'npu',
         'model_path': 'local/bundle', 'sdk_dir': 'local/sdk',
         'max_tokens': 128, 'stop_after_tool_call': False}
CPU = {'backend': 'llama_cpp_cpu', 'plugin': 'llama_cpp', 'device': 'cpu',
       'model_path': 'local/m.gguf', 'threads': 10, 'threads_batch': 0,
       'n_batch': 0, 'ubatch': 0, 'context': 4096, 'max_tokens': 128, 'spec_type': 'none'}


def candidate(control, backend='qairt_npu', **overrides):
    config = dict(control)
    config.update(overrides.pop('config', {}))
    record = {'config': config, 'config_hash': config_hash(config),
              'hypothesis': 'A stated hypothesis'}
    record.update(overrides)
    return record


def test_a_valid_single_variable_candidate_is_admitted():
    assert guard.check(candidate(QAIRT, config={'max_tokens': 64}),
                       control_config=QAIRT, backend='qairt_npu') == []


def test_sampler_controls_never_pass_in_either_lane():
    for lane in guard.LANES:
        reasons = guard.check(candidate(QAIRT, config={'top_k': 4}),
                              control_config=QAIRT, backend='qairt_npu', lane=lane)
        assert any('top_k' in reason for reason in reasons)


def test_heldout_is_unreachable():
    for field, value in (('dataset', 'heldout'), ('dataset', 'all'), ('split', 'heldout')):
        reasons = guard.check(candidate(QAIRT, config={'max_tokens': 64}, **{field: value}),
                              control_config=QAIRT, backend='qairt_npu')
        assert reasons, (field, value)
    assert guard.check(candidate(QAIRT, config={'max_tokens': 64}),
                       control_config=QAIRT, backend='qairt_npu', split='heldout')


def test_frozen_and_historical_paths_are_refused():
    for path in ('eval/scoring.py', 'eval/datasets/secretary_heldout.json',
                 'eval/results/baseline.json', 'local/experiments/EXP-001/manifest.json'):
        reasons = guard.check(candidate(QAIRT, config={'max_tokens': 64}),
                              control_config=QAIRT, backend='qairt_npu', paths_touched=[path])
        assert reasons, path


def test_hidden_multi_variable_mutation_is_refused_but_a_declared_grid_point_is_not():
    hidden = candidate(CPU, config={'threads': 8, 'n_batch': 256})
    assert guard.check(hidden, control_config=CPU, backend='llama_cpp_cpu')
    declared = candidate(CPU, config={'threads': 8, 'n_batch': 256},
                         integration_test=True, variables=['n_batch', 'threads'],
                         causal_attribution=False)
    assert guard.check(declared, control_config=CPU, backend='llama_cpp_cpu') == []


def test_a_grid_point_cannot_claim_causal_attribution():
    claiming = candidate(CPU, config={'threads': 8, 'n_batch': 256},
                         integration_test=True, variables=['n_batch', 'threads'],
                         causal_attribution=True)
    assert any('causal_attribution' in reason
               for reason in guard.check(claiming, control_config=CPU, backend='llama_cpp_cpu'))


def test_energy_objectives_are_refused_until_commissioning():
    energy = candidate(QAIRT, config={'max_tokens': 64}, objective='j_per_correct_task')
    assert guard.check(energy, control_config=QAIRT, backend='qairt_npu')
    assert guard.check(energy, control_config=QAIRT, backend='qairt_npu',
                       energy_commissioned=True) == []
    flagged = candidate(QAIRT, config={'max_tokens': 64}, optimize_energy=True)
    assert guard.check(flagged, control_config=QAIRT, backend='qairt_npu')


def test_undecided_owner_questions_fail_closed():
    needs = candidate(QAIRT, config={'max_tokens': 64},
                      requires_owner_decision=['mandatory_counter_resolution'])
    assert guard.check(needs, control_config=QAIRT, backend='qairt_npu')
    assert guard.check(needs, control_config=QAIRT, backend='qairt_npu',
                       owner_decisions=['mandatory_counter_resolution']) == []


def test_a_repeated_treatment_is_refused_by_hash():
    record = candidate(QAIRT, config={'max_tokens': 64})
    assert guard.check(record, control_config=QAIRT, backend='qairt_npu',
                       tested_exact={record['config_hash']: {}})


def test_a_lane_c_item_is_refused_with_its_reason():
    reasons = guard.check({'lane_c_item': 'QAIRT_EXPLICIT_SAMPLER_CONTROL'},
                          control_config=QAIRT, backend='qairt_npu')
    assert len(reasons) == 1 and 'Lane C' in reasons[0]


def test_a_candidate_without_a_hypothesis_or_hash_is_refused():
    no_hypothesis = candidate(QAIRT, config={'max_tokens': 64}, hypothesis='   ')
    assert any('hypothesis' in reason for reason in
               guard.check(no_hypothesis, control_config=QAIRT, backend='qairt_npu'))
    record = candidate(QAIRT, config={'max_tokens': 64})
    record.pop('config_hash')
    assert any('config hash' in reason for reason in
               guard.check(record, control_config=QAIRT, backend='qairt_npu'))


def test_identical_to_control_and_measurement_boundary_changes_are_refused():
    assert guard.check(candidate(QAIRT), control_config=QAIRT, backend='qairt_npu')
    moving = candidate(QAIRT, config={'max_tokens': 64}, changes_measurement_boundary=True)
    assert guard.check(moving, control_config=QAIRT, backend='qairt_npu')


def test_backend_contradiction_is_refused():
    wrong = candidate(QAIRT, config={'max_tokens': 64, 'backend': 'llama_cpp_cpu'})
    assert guard.check(wrong, control_config=QAIRT, backend='qairt_npu')


def test_admit_partitions_and_keeps_every_reason():
    good = candidate(QAIRT, config={'max_tokens': 64})
    bad = candidate(QAIRT, config={'top_k': 4})
    accepted, rejected = guard.admit([good, bad], control_config=QAIRT, backend='qairt_npu')
    assert accepted == [good] and len(rejected) == 1 and rejected[0][1]


def test_frozen_path_list_names_files_that_exist():
    root = Path(__file__).resolve().parents[1]
    for name in guard.FROZEN_PATHS:
        assert (root / name).exists(), name
