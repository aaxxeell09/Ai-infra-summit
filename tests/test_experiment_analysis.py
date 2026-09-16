"""Synthetic local archive tests: no models, telemetry hardware or golden edits."""
import pytest

from turbo.experiments import finish, initialize, seal, verify
from turbo.experiment_analysis import (campaign, case_comparison, load_archive,
                                       summary, write_report)


def fixture_report():
    return dict(status='measured', dirty=False, benchmark_version='synthetic', protocol_version='single-action',
                dataset_sha256='dataset', fixture_sha256='fixture', inventory_sha256='inventory',
                action_schema_sha256='schema', system_prompt_sha256='prompt', evaluator_sha256={'code': 'abc'},
                generation_protocol={'max_tokens': 128, 'reset': True}, model_sha256='model',
                warmup='fixed warmup', runtime_version='synthetic-sdk', environment={'machine': 'synthetic-only'},
                application_sources_sha256={'turbo/secretary.py': 'executor', 'turbo/service.py': 'parser'},
                config={'threads': 1}, config_sha256='config', git_commit='code',
                inference_backend={'backend_id': 'llama_cpp_cpu'},
                results=[dict(id='dev-synthetic', case_sha256='case', split='development', expected_tool='read_file',
                              task_success=True, invalid_output=False, no_action_correct=True, failure_reasons=[],
                              task_latency_ms=12, latency_ms=10, profile={'generated_tokens': 8},
                              output_text='synthetic raw output', tool='read_file', arguments={'path': 'x'})])


def fixture_energy():
    return dict(measurement_scope='full_process_energy', declared_counter_resolution_s=.1,
                raw_before={'channels_pwh': {'SYS': 100}, 'monotonic_s': 1},
                raw_after={'channels_pwh': {'SYS': 1000000100}, 'monotonic_s': 11},
                power_before={'ac_line_status': 'ac', 'active_scheme_guid': 'scheme', 'battery_saver': False},
                power_after={'ac_line_status': 'ac', 'active_scheme_guid': 'scheme', 'battery_saver': False})


def archive(tmp_path, name, report=None, energy=None, status='completed_diagnostic', control='EXP-control'):
    path = tmp_path / name
    path.mkdir()
    report = fixture_report() if report is None else report
    metadata = initialize(path, {'control_experiment': control})
    finish(path, metadata, report if 'results' in report else None, energy, status=status)
    return path


def test_summary_no_energy_allows_only_correctness_latency_deltas(tmp_path):
    a = archive(tmp_path, 'EXP-001_a')
    other = fixture_report(); other['results'][0]['task_latency_ms'] = 8
    other['config'] = {'threads': 4}; other['config_sha256'] = 'newconfig'
    b = archive(tmp_path, 'EXP-002_b', other)
    out = summary([a, b])
    assert out['overall_winner'] is None and out['descriptive_pareto'] == []
    pair = out['comparisons'][0]
    assert pair['correctness_latency']['comparable'] and not pair['energy']['comparable']
    assert pair['delta_right_minus_left']['median_e2e_ms'] == -4
    assert pair['treatment_right']['config'] == {'threads': 4}
    assert not verify(a) and not verify(b)


@pytest.mark.parametrize('field,value', [('evaluator_sha256', {'code': 'different'}),
                                       ('protocol_version', 'different'), ('model_sha256', 'other')])
def test_provenance_mismatch_blocks_deltas(tmp_path, field, value):
    a = archive(tmp_path, 'EXP-001_a')
    other = fixture_report(); other[field] = value
    b = archive(tmp_path, 'EXP-002_b', other)
    pair = summary([a, b])['comparisons'][0]
    assert not pair['correctness_latency']['comparable']
    assert pair['delta_right_minus_left'] == {}


def test_case_hash_and_timing_mismatch_block(tmp_path):
    a = archive(tmp_path, 'EXP-001_a')
    other = fixture_report(); other['results'][0]['case_sha256'] = 'changed'
    b = archive(tmp_path, 'EXP-002_b', other)
    with pytest.raises(ValueError, match='Incompatible'):
        case_comparison(a, b)
    other = fixture_report(); other['results'][0]['warm_task_latency_ms'] = 9
    c = archive(tmp_path, 'EXP-003_c', other)
    assert not summary([a, c])['comparisons'][0]['correctness_latency']['comparable']


def test_diagnostic_energy_never_qualifies_pareto_or_energy_deltas(tmp_path):
    a = archive(tmp_path, 'EXP-001_a', energy=fixture_energy())
    other = fixture_report(); other['results'][0]['task_latency_ms'] = 8
    b = archive(tmp_path, 'EXP-002_b', other, fixture_energy())
    out = summary([a, b])
    assert out['overall_winner'] is None
    assert out['descriptive_pareto'] == []
    assert not out['comparisons'][0]['energy']['comparable']
    assert 'gross_sys_j_per_correct_task' not in out['comparisons'][0]['delta_right_minus_left']
    assert out['experiments'][0]['diagnostic_energy']['gross_sys_j_per_correct_task'] > 0
    assert out['experiments'][0]['energy_qualification'] == 'diagnostic_uncommissioned'
    assert not out['experiments'][0]['energy_comparable']
    energy = fixture_energy(); energy['measurement_scope'] = 'warm_suite_block'
    c = archive(tmp_path, 'EXP-003_c', other, energy)
    assert not summary([a, c])['comparisons'][0]['energy']['comparable']


def test_tampering_is_reported_not_used_and_no_overwrite(tmp_path):
    a = archive(tmp_path, 'EXP-001_a')
    (a / 'result.json').write_text('{}', encoding='utf-8')
    out = summary([a])
    assert not out['experiments'] and len(out['failures']) == 1
    with pytest.raises(ValueError):
        load_archive(a)
    with pytest.raises(ValueError, match='outside'):
        write_report(a / 'report.json', out, [a])
    path = write_report(tmp_path / 'summary.json', out, [a])
    with pytest.raises(FileExistsError):
        write_report(path, out, [a])


def test_campaign_counts_failures_and_groups_treatments_and_controls(tmp_path):
    a = archive(tmp_path, 'EXP-001_a', energy=fixture_energy())
    other = fixture_report(); other['results'][0]['task_latency_ms'] = 16
    b = archive(tmp_path, 'EXP-002_b', other, fixture_energy())
    c = archive(tmp_path, 'EXP-003_c', status='failed', report={'availability': 'not_recorded'})
    d = archive(tmp_path, 'EXP-004_d', other, fixture_energy(), control='different')
    e = tmp_path / 'EXP-005_partial'; e.mkdir()
    out = campaign([a, b, c, d, e])
    assert out['total_attempts'] == 5 and len(out['groups']) == 2
    repeated = next(group for group in out['groups'] if group['n'] == 2)
    stat = repeated['metrics']['median_e2e_ms']
    assert stat['mean'] == stat['median'] == 14
    assert stat['stddev'] > 0 and stat['cv'] > 0 and stat['min'] == 12 and stat['max'] == 16
    assert len(out['ungrouped_attempts']) == len(out['integrity_failures']) == 1


def test_development_case_diagnostics_fixed_and_raw_preserved(tmp_path):
    bad = fixture_report(); bad['results'][0].update(task_success=False, failure_reasons=['WRONG_SOURCE'])
    a = archive(tmp_path, 'EXP-001_a', bad)
    b = archive(tmp_path, 'EXP-002_b')
    out = case_comparison(a, b)
    assert out['cases'][0]['outcome'] == 'fixed'
    assert out['cases'][0]['left']['output_text'] == 'synthetic raw output'
    assert out['per_tool_error_taxonomy']['read_file']['left']['wrong_arguments'] == 1
    bad['results'][0]['split'] = 'heldout'
    c = archive(tmp_path, 'EXP-003_c', bad)
    with pytest.raises(ValueError, match='development-only'):
        case_comparison(c, b)


def test_resealed_inconsistent_kpi_is_not_trusted(tmp_path):
    a = archive(tmp_path, 'EXP-001_a')
    (a / 'artifact-hashes.sha256').unlink()
    (a / 'kpi.json').write_text('{"success_rate_pct": 100}', encoding='utf-8')
    seal(a)
    with pytest.raises(ValueError, match='KPI differs'):
        load_archive(a)


def test_dirty_and_semantic_dependency_changes_do_not_compare(tmp_path):
    a = archive(tmp_path, 'EXP-001_a')
    dirty = fixture_report(); dirty['dirty'] = True
    b = archive(tmp_path, 'EXP-002_b', dirty)
    changed = fixture_report(); changed['application_sources_sha256']['turbo/service.py'] = 'new-parser'
    c = archive(tmp_path, 'EXP-003_c', changed)
    for other in (b, c):
        pair = summary([a, other])['comparisons'][0]
        assert not pair['correctness_latency']['comparable']
        assert not pair['delta_right_minus_left']


def test_zero_success_and_incomplete_energy_never_enter_pareto(tmp_path):
    bad = fixture_report(); bad['results'][0].update(task_success=False, failure_reasons=['MODEL_ERROR'])
    a = archive(tmp_path, 'EXP-001_a', bad, fixture_energy())
    b = archive(tmp_path, 'EXP-002_b', energy=fixture_energy())
    out = summary([a, b])
    assert out['experiments'][0]['primary']['gross_sys_j_per_correct_task'] is None
    assert not out['descriptive_pareto']
    c = archive(tmp_path, 'EXP-003_c')
    group = campaign([b, c])['groups'][0]
    assert group['n'] == 2 and not group['energy_comparable']
    assert group['metrics']['gross_sys_j_per_correct_task']['mean'] is None


def test_cli_entrypoints_create_readable_exclusive_local_reports(tmp_path, capsys):
    from scripts.render_experiment_summary import main as render
    from scripts.analyze_experiment_campaign import main as analyze
    from scripts.compare_experiment_cases import main as compare
    a = archive(tmp_path, 'EXP-001_a')
    b = archive(tmp_path, 'EXP-002_b')
    for function, name in [(render, 'summary'), (analyze, 'campaign'), (compare, 'cases')]:
        target = tmp_path / (name + '.md')
        assert function([str(a), str(b), '--output', str(target)]) == 0
        text = target.read_text()
        assert 'No overall winner' in text and '| ' in text
        with pytest.raises(SystemExit):
            function([str(a), str(b), '--output', str(target)])
    assert 'synthetic raw output' not in capsys.readouterr().out
    assert not verify(a) and not verify(b)



def test_failed_archive_kpis_recompute_with_incomplete_denominator(tmp_path):
    path = archive(tmp_path, 'EXP-001_failed', energy=fixture_energy(), status='failed')
    item = load_archive(path)
    assert item['kpi']['gross_sys_j'] > 0
    assert item['kpi']['gross_sys_j_per_correct_task'] is None
    assert item['kpi']['energy_denominator_complete'] is False
    out = campaign([path])
    assert out['total_attempts'] == 1
    assert len(out['ungrouped_attempts']) == 1
    assert not out['integrity_failures']


def test_missing_qualification_is_explicit(tmp_path):
    path = archive(tmp_path, 'EXP-001_noqualification', energy=fixture_energy())
    row = summary([path])['experiments'][0]
    assert row['qualification'] == 'unqualified_missing_status'
    assert not row['energy_comparable']
    assert row['energy_comparability_reason']


@pytest.mark.parametrize('field,value', [('profile', []), ('expected', [1]), ('failure_reasons', [{}])])
def test_malformed_nested_archive_rejected_without_summary_crash(tmp_path, field, value):
    from turbo.experiments import write_json
    path = archive(tmp_path, 'EXP-001_a')
    (path/'artifact-hashes.sha256').unlink()
    report = fixture_report()
    report['results'][0].update(task_success=False, **{field:value})
    write_json(path/'result.json', report)
    seal(path)
    out = summary([path])
    assert not out['experiments']
    assert len(out['failures']) == 1


def test_qualified_energy_requires_full_commissioning_not_labels():
    from turbo.experiment_analysis import energy_identity
    item = dict(result=fixture_report(), manifest={'energy_comparable':True,'energy_qualification':'commissioned'},
                kpi={'energy_comparable':True,'energy_qualification':'commissioned',
                     'energy_denominator_complete':True,'energy_scope':'warm_task_v1',
                     'gross_sys_j_per_correct_task':3.6})
    with pytest.raises(ValueError, match='validation failed'):
        energy_identity(item)


def test_complete_synthetic_commissioned_task_evidence_can_be_recognized():
    from tests.test_decision_table import fixture
    from eval.decision_table import energy_summary
    from turbo.experiment_analysis import energy_identity
    reports, _ = fixture(); report = reports['cpu']
    item = dict(result=report, manifest={'energy_comparable':True,'energy_qualification':'commissioned'},
                kpi={'energy_comparable':True,'energy_qualification':'commissioned',
                     'energy_denominator_complete':True,'energy_scope':'warm_task_v1',
                     'gross_sys_j_per_correct_task':energy_summary(report['results'])['joules_per_correct_task']})
    assert energy_identity(item) == report['energy_measurement']['signature']
    item['kpi']['gross_sys_j_per_correct_task'] += 1
    with pytest.raises(ValueError, match='differs'): energy_identity(item)


def test_single_archive_errors_preserve_dirty_clarification_failure_evidence(tmp_path):
    from turbo.experiment_analysis import error_analysis
    report = fixture_report(); report['dirty'] = True
    report['results'][0].update(expected_tool='clarify', expected={'tool':'clarify','arguments':{}},
        task_success=False, failure_reasons=['FAILED_TO_CLARIFY'], tool='read_file',
        output_text='<tool_call>first</tool_call><tool_call>second</tool_call>',
        profile={'generated_tokens':17,'stop_reason':'synthetic-stop'}, invalid_output=True)
    path = archive(tmp_path, 'EXP-001_dirty', report)
    before = (path/'result.json').read_bytes()
    out = error_analysis(path)
    assert out['result_dirty'] is True
    assert out['clarification'] == {'cases':1,'failed':1,'failed_case_ids':['dev-synthetic']}
    row = out['cases'][0]
    assert row['output_text'] == report['results'][0]['output_text']
    assert row['expected'] == report['results'][0]['expected']
    assert row['actual_arguments'] == {'path':'x'}
    assert row['generated_tokens'] == 17 and row['stop_reason'] == 'synthetic-stop'
    assert 'multiple_closing_tool_tags_in_raw_text' in row['observed_mechanisms']
    assert 'nonclarifying_action_on_expected_clarification' in row['observed_mechanisms']
    assert (path/'result.json').read_bytes() == before and not verify(path)


@pytest.mark.parametrize('split', ['heldout', None, 'unknown'])
def test_single_archive_errors_reject_non_development(tmp_path, split):
    from turbo.experiment_analysis import error_analysis
    report = fixture_report(); report['results'][0]['split'] = split
    path = archive(tmp_path, 'EXP-001_notdev', report)
    with pytest.raises(ValueError, match='development-only'): error_analysis(path)


def test_single_archive_error_cli_keeps_raw_evidence_local(tmp_path, capsys):
    from scripts.analyze_experiment_errors import main
    report = fixture_report(); report['results'][0].update(task_success=False, failure_reasons=['WRONG_ACTION'])
    path = archive(tmp_path, 'EXP-001_errors', report)
    target = tmp_path/'errors.md'
    assert main([str(path), '--output', str(target)]) == 0
    assert 'synthetic raw output' in target.read_text()
    assert 'synthetic raw output' not in capsys.readouterr().out
    with pytest.raises(SystemExit): main([str(path), '--output', str(target)])



def test_single_archive_errors_reject_mixed_split(tmp_path):
    import copy
    from turbo.experiment_analysis import error_analysis
    report = fixture_report()
    other = copy.deepcopy(report['results'][0]); other.update(id='other', split='heldout')
    report['results'].append(other)
    path = archive(tmp_path, 'EXP-001_mixed', report)
    with pytest.raises(ValueError, match='development-only'): error_analysis(path)


def test_explicit_telemetry_energy_false_cannot_be_promoted():
    from turbo.experiment_analysis import energy_identity
    item = dict(result={}, manifest={}, kpi={}, telemetry={'energy_comparable':False})
    with pytest.raises(ValueError, match='explicitly marks'): energy_identity(item)
