"""Session reporting. Synthetic state only: no hardware, no archive, no network.

The point of these tests is terminology. The five populations must stay five
separate numbers, and an unmeasured figure must never arrive as a zero.
"""
import json
import tempfile
from pathlib import Path

import pytest

from turbo.optimizer import report, state


def session(**counters):
    record = state.new_session(backend='qairt_npu', split='development', budget_minutes=240,
                               control_name='EXP-XYZ', control_config={'max_tokens': 128},
                               session_id='AT-000000000001')
    record['counters'].update(counters)
    return record


def summary_of(record, **kwargs):
    arguments = dict(started_at='2026-09-16T22:00:00+00:00', finished_at='2026-09-17T04:00:00+00:00',
                     initial_control={'name': 'EXP-XYZ'}, final_control={'name': 'C-0034'})
    arguments.update(kwargs)
    return report.session_summary(record, **arguments)


def qualified(experiment_id):
    return {'experiment_id': experiment_id, 'status': 'completed_qualified'}


def test_the_five_populations_stay_five_distinct_numbers():
    record = session(generated=500, statically_valid=40, diagnostic_admitted=12, hardware_attempts=6)
    experiments = [qualified('EXP-0041'), qualified('EXP-0042'), qualified('EXP-0043'),
                   qualified('EXP-0044'), {'experiment_id': 'EXP-0045', 'status': 'completed_diagnostic'},
                   {'experiment_id': 'EXP-0046', 'status': 'failed'}]
    counts = summary_of(record, experiments=experiments)['counts']
    assert counts == {report.GENERATED_CANDIDATES: 500,
                      report.STATICALLY_VALID_CANDIDATES: 40,
                      report.DIAGNOSTIC_CANDIDATES: 12,
                      report.HARDWARE_ATTEMPTS: 6,
                      report.QUALIFIED_EXPERIMENTS: 4}
    assert len(set(counts.values())) == 5


def test_markdown_renders_all_five_names_and_never_conflates_them():
    record = session(generated=500, statically_valid=40, diagnostic_admitted=12, hardware_attempts=6)
    summary = summary_of(record, experiments=[qualified('EXP-004%d' % i) for i in range(1, 5)])
    text = report.render_markdown(summary)
    for name in report.COUNT_NAMES:
        assert text.count('| ' + name + ' |') == 1
    generated_row = [line for line in text.splitlines() if report.GENERATED_CANDIDATES in line][0]
    assert '| 500 |' in generated_row
    assert '| ' + report.HARDWARE_ATTEMPTS + ' | 6 |' in text
    assert '| ' + report.QUALIFIED_EXPERIMENTS + ' | 4 |' in text
    assert 'not a\ntest, not a run and not an experiment' in text
    for forbidden in ('500 experiments', '500 runs', '500 tests'):
        assert forbidden not in text


def test_generated_candidates_are_never_described_as_experiments_or_runs():
    record = session(generated=500, statically_valid=40, hardware_attempts=0)
    text = report.render_markdown(summary_of(record))
    assert report.COUNT_MEANINGS[report.GENERATED_CANDIDATES] in text
    assert 'Only QUALIFIED_EXPERIMENTS is measured evidence' in text


def test_statically_valid_is_derived_only_when_both_inputs_were_counted():
    derived = session(generated=120, static_rejected=33)
    assert summary_of(derived)['counts'][report.STATICALLY_VALID_CANDIDATES] == 87
    silent = session(generated=120)
    silent['counters'].pop('static_rejected')
    assert summary_of(silent)['counts'][report.STATICALLY_VALID_CANDIDATES] is None


def test_counts_that_the_session_never_recorded_are_none_not_zero():
    record = session()
    for key in ('generated', 'static_rejected', 'S1'):
        record['counters'].pop(key, None)
    counts = summary_of(record)['counts']
    assert counts[report.GENERATED_CANDIDATES] is None
    assert counts[report.STATICALLY_VALID_CANDIDATES] is None
    assert counts[report.DIAGNOSTIC_CANDIDATES] is None
    assert counts[report.HARDWARE_ATTEMPTS] is None
    assert counts[report.QUALIFIED_EXPERIMENTS] == 0


def test_hardware_attempts_falls_back_to_the_first_hardware_stage():
    record = session()
    record['counters']['S1'] = 6
    assert summary_of(record)['counts'][report.HARDWARE_ATTEMPTS] == 6


@pytest.mark.parametrize('busy, idle, expected', [(0, 0, None), (0.0, 0.0, None),
                                                  (None, 10.0, None), (10.0, None, None),
                                                  (-1.0, 1.0, None), (3.0, 1.0, 75.0),
                                                  (10.0, 0.0, 100.0), (0.0, 10.0, 0.0)])
def test_utilisation(busy, idle, expected):
    assert report.utilisation(busy, idle) == expected


def test_utilisation_of_a_session_that_touched_no_hardware_is_absent_in_the_summary():
    summary = summary_of(session())
    assert summary['hardware_busy_seconds'] == 0.0 and summary['hardware_idle_seconds'] == 0.0
    assert summary['hardware_utilisation_pct'] is None
    assert 'not measured' in report.render_markdown(summary)


def test_control_comparison_reports_measured_fields_and_nothing_else():
    record = session()
    initial = {'name': 'EXP-XYZ', 'experiment_id': 'EXP-0001',
               'kpi': {'success_rate_pct': 60.0, 'correct_tasks': 21, 'total_tasks': 35,
                       'invalid_count': 2, 'median_e2e_ms': 548.0, 'p95_e2e_ms': None,
                       'error_taxonomy': {'wrong_arguments': 5, 'invalid_format': 2}}}
    final = {'name': 'C-0034', 'experiment_id': None}
    summary = summary_of(record, initial_control=initial, final_control=final)
    assert summary['initial_control']['measured'] is True
    assert summary['initial_control']['success_rate_pct'] == 60.0
    assert summary['initial_control']['median_task_latency_ms'] == 548.0
    assert summary['initial_control']['p95_task_latency_ms'] is None
    assert summary['initial_control']['failure_taxonomy'] == {'wrong_arguments': 5, 'invalid_format': 2}
    assert summary['final_control']['measured'] is False
    for field in report.CONTROL_FIELDS:
        assert summary['final_control'][field] is None
    text = report.render_markdown(summary)
    assert '| success % | 60.0 | not measured |' in text
    assert '| p95 task latency ms | not measured | not measured |' in text
    assert '| failure taxonomy | invalid_format=2, wrong_arguments=5 | not measured |' in text


def test_heldout_is_absent_unless_explicitly_supplied():
    summary = summary_of(session())
    assert 'heldout_evaluation' not in summary
    text = report.render_markdown(summary)
    assert 'The optimization loop cannot reach those cases.' in text
    assert 'Heldout evaluation' not in text


def test_heldout_appears_only_when_passed_and_is_labelled_as_separate():
    heldout = {'experiment_id': 'EXP-0099', 'correct_tasks': 9, 'total_tasks': 15}
    summary = summary_of(session(), heldout_evaluation=heldout)
    assert summary['heldout_evaluation'] == heldout
    text = report.render_markdown(summary)
    assert '## Heldout evaluation' in text
    assert 'not by the optimization loop' in text
    assert '"total_tasks": 15' in text


def test_heldout_must_be_an_object():
    with pytest.raises(TypeError):
        summary_of(session(), heldout_evaluation='9/15 correct')


def test_only_the_final_script_may_supply_heldout_figures_per_the_docstring():
    assert 'scripts/autotune_final.py' in report.session_summary.__doc__


def test_duration_is_none_when_an_endpoint_is_missing_or_unparseable():
    assert summary_of(session(), finished_at=None)['duration_seconds'] is None
    assert summary_of(session(), started_at='last night')['duration_seconds'] is None
    assert summary_of(session())['duration_seconds'] == 6 * 3600.0


def test_families_explored_are_projected_from_state():
    record = session()
    state.touch_family(record, 'output_budget')
    record['families']['output_budget']['attempted'] = 9
    record['families']['output_budget']['dev35_wins'] = 1
    summary = summary_of(record)
    assert summary['families_explored'] == [{'family': 'output_budget', 'attempted': 9,
                                             'survived_s2': 0, 'survived_s3': 0, 'dev35_wins': 1,
                                             'confirmed_wins': 0, 'hardware_seconds_spent': 0.0}]
    assert '| output_budget | 9 |' in report.render_markdown(summary)


def test_write_summary_writes_both_files_and_round_trips():
    with tempfile.TemporaryDirectory() as directory:
        summary = summary_of(session(generated=500, statically_valid=40, hardware_attempts=6))
        md_path, json_path = report.write_summary(summary, directory)
        assert md_path.name == 'session-summary.md' and json_path.name == 'session-summary.json'
        assert json.loads(json_path.read_text(encoding='utf-8')) == summary
        assert md_path.read_text(encoding='utf-8') == report.render_markdown(summary)


def test_write_summary_replaces_only_its_own_session():
    with tempfile.TemporaryDirectory() as directory:
        first = summary_of(session(generated=10))
        report.write_summary(first, directory)
        again = summary_of(session(generated=11))
        report.write_summary(again, directory)
        stored = json.loads((Path(directory) / 'session-summary.json').read_text(encoding='utf-8'))
        assert stored['counts'][report.GENERATED_CANDIDATES] == 11


def test_write_summary_refuses_a_different_session_id():
    with tempfile.TemporaryDirectory() as directory:
        report.write_summary(summary_of(session(generated=10)), directory)
        other = session(generated=10)
        other['session_id'] = 'AT-000000000002'
        with pytest.raises(ValueError) as exc:
            report.write_summary(summary_of(other), directory)
        assert 'AT-000000000001' in str(exc.value) and 'AT-000000000002' in str(exc.value)
        stored = json.loads((Path(directory) / 'session-summary.json').read_text(encoding='utf-8'))
        assert stored['session_id'] == 'AT-000000000001'


def test_write_summary_refuses_an_unidentifiable_existing_markdown():
    with tempfile.TemporaryDirectory() as directory:
        (Path(directory) / 'session-summary.md').write_text('# hand written', encoding='utf-8')
        with pytest.raises(ValueError):
            report.write_summary(summary_of(session()), directory)


def test_write_summary_refuses_a_summary_with_no_session_id():
    with tempfile.TemporaryDirectory() as directory:
        summary = summary_of(session())
        summary['session_id'] = None
        with pytest.raises(ValueError):
            report.write_summary(summary, directory)


def test_energy_is_never_a_selection_or_ranking_figure():
    summary = summary_of(session())
    assert summary['energy_commissioned'] is False
    text = report.render_markdown(summary)
    assert 'Energy is not commissioned' in text
    assert 'j_per_correct' not in text.lower()


def test_an_unrecorded_name_or_experiment_id_reads_unknown_not_not_measured():
    summary = summary_of(session(), final_control={'name': 'C-0034'})
    text = report.render_markdown(summary)
    assert '| experiment id | unknown | unknown |' in text
    assert '| name | EXP-XYZ | C-0034 |' in text
