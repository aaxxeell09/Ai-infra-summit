"""Console rendering and control selection. No hardware, no model, no network.

The selector tests live here too: turbo/optimizer/successive_halving.py is
stubbed into sys.modules so this file exercises the delegation contract without
depending on the rule module being present or on what it currently decides.
"""
import io
import sys
import types

import pytest

from turbo.optimizer import console as console_module
from turbo.optimizer import selector, state
from turbo.optimizer.console import Console

#: 2023-11-14T22:13:20Z. The console stamps UTC, so this is timezone stable.
FROZEN = 1_700_000_000.0
AT = '[22:13:20]'


def sink(colour=None):
    stream = io.StringIO()
    return stream, Console(stream, clock=lambda: FROZEN, colour=colour)


def written(stream):
    return stream.getvalue().splitlines()


def test_generated_and_guard_lines_align_in_the_same_columns():
    stream, log = sink()
    log.generated('sampler', 126)
    log.guard('sampler', 87, 39)
    lines = written(stream)
    assert lines == [AT + ' GEN   sampler    126 candidates',
                     AT + ' GUARD sampler     87 accepted / 39 rejected']
    assert lines[0].index('sampler') == lines[1].index('sampler')


def test_stage_promotion_and_control_lines():
    stream, log = sink()
    log.stage('S1', 'C-0034', 'PASS  load=1.8s')
    log.stage('S2', 'C-0034', '  6/8  med=548ms  SURVIVE')
    log.stage('S4', 'C-0034', ' 22/35 +3 cases  PROMOTION_PENDING')
    log.promotion('C-0034', 'confirmed on 3 repeats')
    log.control('EXP-XYZ', 'C-0034')
    assert written(stream) == [
        AT + ' S1    C-0034     PASS  load=1.8s',
        AT + ' S2    C-0034       6/8  med=548ms  SURVIVE',
        AT + ' DEV35 C-0034      22/35 +3 cases  PROMOTION_PENDING',
        AT + ' PROMO C-0034     confirmed on 3 repeats',
        AT + ' CONTROL EXP-XYZ -> C-0034']


def test_stage_label_mapping_is_declared_and_s4_reads_dev35():
    assert console_module.STAGE_LABELS['S4'] == 'DEV35'
    assert console_module.STAGE_LABELS['S5'] == 'CONFIRM'
    for stage in state.STAGES:
        assert stage in console_module.STAGE_LABELS


def test_an_unmapped_stage_is_printed_verbatim_not_guessed():
    stream, log = sink()
    log.stage('S9', 'C-0002', 'detail')
    assert written(stream) == [AT + ' S9    C-0002     detail']


@pytest.mark.parametrize('call, expected', [
    (lambda log: log.generated('sampler', None), AT + ' GEN   sampler    unknown candidates'),
    (lambda log: log.guard('sampler', None, 39), AT + ' GUARD sampler    unknown accepted / 39 rejected'),
    (lambda log: log.guard('sampler', 87, None), AT + ' GUARD sampler     87 accepted / unknown rejected'),
    (lambda log: log.stage('S2', 'C-0034', None), AT + ' S2    C-0034     unknown'),
    (lambda log: log.stage('S2', None, 'SURVIVE'), AT + ' S2    unknown    SURVIVE'),
    (lambda log: log.control(None, 'C-0034'), AT + ' CONTROL unknown -> C-0034'),
    (lambda log: log.promotion('C-0034', None), AT + ' PROMO C-0034     unknown'),
])
def test_a_missing_value_renders_as_unknown_never_zero_never_blank(call, expected):
    stream, log = sink()
    call(log)
    line = written(stream)[0]
    assert line == expected
    assert console_module.UNKNOWN in line


def test_warn_error_and_free_lines():
    stream, log = sink()
    log.warn('device idle for 90s')
    log.error('reload failed')
    log.line('budget 240 minutes, backend qairt_npu')
    assert written(stream) == [AT + ' WARN  device idle for 90s',
                               AT + ' ERROR reload failed',
                               AT + ' budget 240 minutes, backend qairt_npu']


def test_no_ansi_when_the_stream_is_not_a_tty_even_if_colour_requested():
    for colour in (None, True, False):
        stream, log = sink(colour=colour)
        assert log.colour is False
        log.error('red would be nice')
        log.guard('stop', 1, 2)
        assert '\x1b' not in stream.getvalue()


def test_colour_is_applied_only_on_a_tty_and_only_when_not_disabled():
    class Tty(io.StringIO):
        def isatty(self):
            return True

    painted = Tty()
    Console(painted, clock=lambda: FROZEN).error('boom')
    assert painted.getvalue().startswith(console_module.ANSI['ERROR'])
    assert painted.getvalue().rstrip('\n').endswith(console_module.RESET)

    plain = Tty()
    Console(plain, clock=lambda: FROZEN, colour=False).error('boom')
    assert '\x1b' not in plain.getvalue()


def test_a_stream_that_cannot_answer_isatty_is_treated_as_not_a_terminal():
    class Awkward(io.StringIO):
        def isatty(self):
            raise ValueError('closed')

    stream = Awkward()
    log = Console(stream, clock=lambda: FROZEN)
    assert log.colour is False
    log.warn('still logs')
    assert '\x1b' not in stream.getvalue()


def session():
    return state.new_session(backend='qairt_npu', split='development', budget_minutes=30,
                             control_name='EXP-XYZ', control_config={'max_tokens': 128})


def candidate(max_tokens=64):
    config = {'max_tokens': max_tokens}
    return {'candidate_id': 'C-0034', 'family': 'output_budget', 'variable': 'max_tokens',
            'config': config, 'config_hash': state.config_hash(config)}


def stub_rules(monkeypatch, verdict, recorder=None):
    module = types.ModuleType('turbo.optimizer.successive_halving')

    def promotion_decision(**kwargs):
        if recorder is not None:
            recorder.update(kwargs)
        return verdict

    module.promotion_decision = promotion_decision
    monkeypatch.setitem(sys.modules, 'turbo.optimizer.successive_halving', module)
    return module


def test_consider_delegates_every_input_to_the_halving_rule(monkeypatch):
    seen = {}
    stub_rules(monkeypatch, {'decision': 'reject', 'reasons': ['flat on dev35']}, seen)
    record, item = session(), candidate()
    selection = selector.consider(record, item, dev35_deltas=[1, -1, 0], confirmation_deltas=[],
                                  latency_gate_ok=True, deterministic_output=True)
    assert seen == {'dev35_deltas': [1, -1, 0], 'confirmation_deltas': [],
                    'latency_gate_ok': True, 'deterministic_output': True}
    assert selection['decision'] == 'reject'
    assert selection['reasons'] == ['flat on dev35']
    assert selection['net_cases'] == 0
    assert record['current_control']['name'] == 'EXP-XYZ'
    assert record['counters']['promotions'] == 0


def test_promotion_makes_the_candidate_control_and_returns_the_previous_one(monkeypatch):
    stub_rules(monkeypatch, {'decision': 'promote', 'reasons': ['+3 net cases confirmed']})
    record, item = session(), candidate()
    selection = selector.consider(record, item, dev35_deltas=[1, 1, 1], confirmation_deltas=[1, 1],
                                  latency_gate_ok=True, deterministic_output=True,
                                  experiment_id='EXP-0042')
    assert selection['decision'] == 'promote'
    assert selection['net_cases'] == 3 and selection['confirmed'] is True
    assert selection['experiment_id'] == 'EXP-0042'
    assert selection['experiment_id_status'] == 'recorded'
    assert selection['previous_control']['name'] == 'EXP-XYZ'
    assert record['current_control']['name'] == 'C-0034'
    assert record['current_control']['experiment_id'] == 'EXP-0042'
    assert record['counters']['promotions'] == 1


def test_a_promotion_without_a_tracker_experiment_is_marked_unknown(monkeypatch):
    stub_rules(monkeypatch, {'decision': 'promote'})
    record = session()
    selection = selector.consider(record, candidate(), dev35_deltas=[1, 1], confirmation_deltas=[1],
                                  latency_gate_ok=True, deterministic_output=True,
                                  experiment_id=None)
    assert selection['decision'] == 'promote'
    assert selection['experiment_id'] is None
    assert selection['experiment_id_status'] == 'unknown'
    assert selector.UNTRACKED_PROMOTION in selection['reasons']
    assert 'cannot be cited as measured evidence' in selector.UNTRACKED_PROMOTION
    assert record['current_control']['experiment_id'] is None


@pytest.mark.parametrize('gates', [{'latency_gate_ok': False, 'deterministic_output': True},
                                   {'latency_gate_ok': None, 'deterministic_output': True}])
def test_a_promote_verdict_is_refused_when_the_latency_gate_is_not_an_explicit_pass(monkeypatch, gates):
    stub_rules(monkeypatch, {'decision': 'promote'})
    record = session()
    selection = selector.consider(record, candidate(), dev35_deltas=[2], confirmation_deltas=[1],
                                  experiment_id='EXP-0042', **gates)
    assert selection['decision'] == 'reject'
    assert any('explicit pass' in reason for reason in selection['reasons'])
    assert record['current_control']['name'] == 'EXP-XYZ'


@pytest.mark.parametrize('determinism', [None, False, 'probably'])
def test_unproven_determinism_is_not_a_promotion_gate(monkeypatch, determinism):
    """Determinism relaxes how many repeats a promotion needs. It is not a gate.

    Treating it as one would make promotion impossible for any stochastic
    runtime, which is the normal case here. The repetition requirement inside
    the rule module is what handles the non-deterministic branch, by demanding a
    confirming repeat, and that branch is exercised by the rule module's own
    tests. The selector must not add a second, stricter condition on top.
    """
    stub_rules(monkeypatch, {'decision': 'promote'})
    record = session()
    selection = selector.consider(record, candidate(), dev35_deltas=[2], confirmation_deltas=[1],
                                  latency_gate_ok=True, deterministic_output=determinism,
                                  experiment_id='EXP-0042')
    assert selection['decision'] == 'promote'
    assert not any('Deterministic output' in reason for reason in selection['reasons'])


def test_rollback_restores_the_previous_control(monkeypatch):
    stub_rules(monkeypatch, {'decision': 'promote'})
    record = session()
    selector.consider(record, candidate(), dev35_deltas=[3], confirmation_deltas=[1],
                      latency_gate_ok=True, deterministic_output=True, experiment_id='EXP-0042')
    undone = selector.rollback(record, 'confirmation regressed on repeat 2')
    assert undone['decision'] == 'rolled_back' and undone['rolled_back'] is True
    assert undone['reasons'] == ['confirmation regressed on repeat 2']
    assert undone['candidate_id'] == 'EXP-XYZ'
    assert record['current_control']['name'] == 'EXP-XYZ'
    assert record['current_control']['config'] == {'max_tokens': 128}
    assert record['counters']['promotions'] == 0


def test_a_missing_halving_module_is_an_explicit_error_not_a_promotion(monkeypatch):
    monkeypatch.setitem(sys.modules, 'turbo.optimizer.successive_halving', None)
    record = session()
    with pytest.raises(ImportError) as exc:
        selector.consider(record, candidate(), dev35_deltas=[5], confirmation_deltas=[5],
                          latency_gate_ok=True, deterministic_output=True)
    assert 'successive_halving' in str(exc.value)
    assert record['current_control']['name'] == 'EXP-XYZ'


def test_a_rule_module_without_promotion_decision_is_refused(monkeypatch):
    monkeypatch.setitem(sys.modules, 'turbo.optimizer.successive_halving',
                        types.ModuleType('turbo.optimizer.successive_halving'))
    with pytest.raises(ImportError):
        selector.consider(session(), candidate(), dev35_deltas=[5], confirmation_deltas=[5],
                          latency_gate_ok=True, deterministic_output=True)


def test_a_bare_decision_string_is_accepted_and_deltas_still_drive_net_cases(monkeypatch):
    stub_rules(monkeypatch, 'reject')
    selection = selector.consider(session(), candidate(), dev35_deltas=[1, 1, -1],
                                  confirmation_deltas=[], latency_gate_ok=True,
                                  deterministic_output=True)
    assert selection['decision'] == 'reject' and selection['net_cases'] == 1


def test_unusable_deltas_leave_net_cases_unknown(monkeypatch):
    stub_rules(monkeypatch, 'reject')
    selection = selector.consider(session(), candidate(), dev35_deltas=None, confirmation_deltas=[],
                                  latency_gate_ok=True, deterministic_output=True)
    assert selection['net_cases'] is None


def test_a_nonsense_rule_return_is_refused(monkeypatch):
    stub_rules(monkeypatch, 17)
    with pytest.raises(TypeError):
        selector.consider(session(), candidate(), dev35_deltas=[1], confirmation_deltas=[],
                          latency_gate_ok=True, deterministic_output=True)


def test_the_real_halving_module_plugs_in_unstubbed():
    """Integration with the sibling rule module, so a signature drift shows here."""
    halving = pytest.importorskip('turbo.optimizer.successive_halving')
    record = session()
    promoted = selector.consider(record, candidate(), dev35_deltas=[1, 1, 1],
                                 confirmation_deltas=[1, 1], latency_gate_ok=True,
                                 deterministic_output=True, experiment_id='EXP-0042')
    assert promoted['decision'] == 'promote'
    assert promoted['net_cases'] == 3
    assert record['current_control']['name'] == 'C-0034'

    refused = selector.consider(session(), candidate(), dev35_deltas=[1, 1, 1],
                                confirmation_deltas=[1, 1], latency_gate_ok=False,
                                deterministic_output=True)
    assert refused['decision'] != 'promote'
    assert halving.PROMOTION_MIN_NET >= 1
