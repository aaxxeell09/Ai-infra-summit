"""Read-only diagnostic reports for sealed experiment archives; no winner selection."""
from __future__ import annotations

from collections import Counter, defaultdict
import json
import math
from pathlib import Path

from .experiments import PRIMARY, digest, finite, kpis, read_json, rows_of, stats, taxonomy, verify

IDENTITY = ('benchmark_version', 'protocol_version', 'dataset_sha256', 'fixture_sha256',
            'inventory_sha256', 'action_schema_sha256', 'system_prompt_sha256',
            'evaluator_sha256', 'generation_protocol', 'model_sha256', 'warmup', 'runtime_version')


def load_archive(path):
    """Verify every sealed artifact before interpreting its data."""
    path = Path(path)
    if path.is_symlink():
        raise ValueError('Archive symlinks are unsupported')
    path = path.resolve()
    errors = verify(path)
    if errors:
        raise ValueError(f'{path.name}: ' + '; '.join(errors))
    for name in ('manifest.json', 'result.json', 'kpi.json'):
        if not (path / name).is_file():
            raise ValueError(f'{path.name}: missing {name}')
    manifest = read_json(path / 'manifest.json')
    result = read_json(path / 'result.json')
    saved = read_json(path / 'kpi.json')
    if not all(isinstance(x, dict) for x in (manifest, result, saved)):
        raise ValueError('Archive JSON artifacts must be objects')
    telemetry = read_json(path / 'telemetry.json') if (path / 'telemetry.json').exists() else None
    if 'results' in result and not isinstance(result['results'], list):
        raise ValueError('Archived result.results must be an array')
    if isinstance(result.get('results'), list):
        rows_of(result)
        complete = (manifest.get('status') not in ('failed', 'timeout')
                    and manifest.get('case_set_complete') is not False and result.get('status') == 'measured')
        try:
            calculated = kpis(result, telemetry, complete=complete)
        except (AttributeError, TypeError, KeyError, ValueError, OverflowError) as exc:
            raise ValueError('Malformed archived result or telemetry: ' + type(exc).__name__) from exc
        if calculated != saved:
            raise ValueError(f'{path.name}: archived KPI differs from derived result/telemetry')
    else:
        calculated = {key: None for key in PRIMARY}
    return dict(path=path, manifest=manifest, result=result, kpi=calculated, telemetry=telemetry)


def treatment(item):
    result, manifest = item['result'], item['manifest']
    return dict(backend=result.get('inference_backend', manifest.get('inference_backend')),
                config=result.get('config', manifest.get('config')),
                config_sha256=result.get('config_sha256', manifest.get('config_sha256')),
                git_commit=result.get('git_commit', manifest.get('git_commit')),
                artifact_identity=manifest.get('artifact_identity_before'),
                application_sources_sha256=result.get('application_sources_sha256'),
                control_experiment=manifest.get('control_experiment'))


def case_identity(result):
    rows = rows_of(result)
    ids = [r.get('id') for r in rows]
    if not rows or any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
        raise ValueError('Empty, missing or duplicate case IDs')
    if any(not isinstance(r.get('case_sha256'), str) or not r['case_sha256'] for r in rows):
        raise ValueError('Missing per-case hashes')
    return sorted((r['id'], r['case_sha256']) for r in rows)


def energy_identity(item):
    """Qualify only commissioned warm-task evidence; block counters stay diagnostic.

    The current tracker deliberately emits energy_comparable=false. Resolution and
    stable power labels cannot promote those diagnostic observations to qualification.
    """
    from eval.decision_table import SLOTS, build as validate_decision_evidence, energy_summary
    k, manifest, result = item['kpi'], item['manifest'], item['result']
    telemetry = item.get('telemetry')
    if telemetry is not None and not isinstance(telemetry, dict):
        raise ValueError('Malformed telemetry qualification object')
    if isinstance(telemetry, dict) and (telemetry.get('energy_comparable') is False
            or telemetry.get('energy_qualification') == 'diagnostic_uncommissioned'):
        raise ValueError('Telemetry explicitly marks energy diagnostic/uncommissioned')
    if not all(isinstance(value, dict) for value in (k, manifest, result)):
        raise ValueError('Malformed energy qualification objects')
    if (k.get('energy_comparable') is not True or manifest.get('energy_comparable') is not True
            or k.get('energy_qualification') != 'commissioned'
            or manifest.get('energy_qualification') != 'commissioned'):
        raise ValueError('Energy is diagnostic/uncommissioned or qualification is missing; no qualified comparison')
    if k.get('energy_denominator_complete') is not True:
        raise ValueError('Energy denominator is incomplete')
    if k.get('energy_scope') != 'warm_task_v1':
        raise ValueError('Unsupported commissioned energy scope; block energy remains diagnostic')
    backend = result.get('inference_backend')
    slot = next((slot for slot, name in SLOTS.items() if isinstance(backend, dict) and backend.get('backend_id') == name), None)
    if slot is None:
        raise ValueError('Commissioned backend identity unavailable')
    validated = validate_decision_evidence({slot: result}, None,
        {'min_accuracy_pct': None, 'max_e2e_latency_ms': None}, {}, None)
    row = next(row for row in validated['rows'] if row['backend'] == SLOTS[slot])
    if row['status'] != 'MEASURED':
        raise ValueError('Commissioned measurement validation failed: ' + '; '.join(row['reasons']))
    derived = energy_summary(rows_of(result))['joules_per_correct_task']
    reported = k.get('gross_sys_j_per_correct_task')
    if not finite(derived) or not finite(reported) or not math.isclose(derived, reported, rel_tol=1e-9):
        raise ValueError('Qualified energy KPI differs from validated task evidence')
    return result['energy_measurement']['signature']


def signature(item, *, energy=False):
    result = item['result']
    if item['manifest'].get('status') not in ('completed_qualified', 'completed_diagnostic', 'historical_diagnostic'):
        raise ValueError('Attempt did not complete')
    if item['manifest'].get('case_set_complete') is False:
        raise ValueError('Case set is incomplete')
    if result.get('status') != 'measured' or result.get('dirty') is not False:
        raise ValueError('Requires a clean measured result')
    missing = [key for key in IDENTITY if result.get(key) is None or result.get(key) == '' or result.get(key) == {}]
    if missing:
        raise ValueError('Missing comparison provenance: ' + ', '.join(missing))
    boundary = item['kpi'].get('latency_boundary')
    if not boundary or not finite(item['kpi'].get('median_e2e_ms')):
        raise ValueError('Task timing boundary unavailable')
    identity = {key: result[key] for key in IDENTITY}
    sources = result.get('application_sources_sha256') or {}
    semantic_sources = {key: sources.get(key) for key in ('turbo/secretary.py', 'turbo/service.py')}
    if not all(semantic_sources.values()):
        raise ValueError('Parser/executor source identity unavailable')
    identity.update(semantic_sources=semantic_sources, cases=case_identity(result), latency_boundary=boundary,
                    environment=result.get('environment'))
    if not isinstance(identity['environment'], dict) or not identity['environment']:
        raise ValueError('Environment identity unavailable')
    if energy:
        identity['energy'] = energy_identity(item)
    return identity


def compatibility(left, right, *, energy=False):
    try:
        a, b = signature(left, energy=energy), signature(right, energy=energy)
    except (AttributeError, ValueError, TypeError, KeyError, OverflowError) as exc:
        return dict(comparable=False, reasons=[str(exc)])
    differences = [key for key in a if a[key] != b[key]]
    return dict(comparable=not differences, reasons=['Different ' + key for key in differences])


def public_item(item):
    k = item['kpi']; m = item['manifest']
    try:
        energy_identity(item)
        energy_comparable, energy_reason = True, None
    except (AttributeError, ValueError, TypeError, KeyError, OverflowError) as exc:
        energy_comparable, energy_reason = False, str(exc)
    return dict(archive=item['path'].name, experiment_id=m.get('experiment_id'),
                status=m.get('status'), qualification=m.get('qualification_status') or 'unqualified_missing_status',
                energy_qualification=k.get('energy_qualification') or 'unavailable',
                energy_comparable=energy_comparable, energy_comparability_reason=energy_reason,
                diagnostic_energy={'gross_sys_j': k.get('gross_sys_j'),
                                   'gross_sys_j_per_correct_task': k.get('gross_sys_j_per_correct_task'),
                                   'scope': k.get('energy_scope'),
                                   'qualification': k.get('energy_qualification') or 'unavailable'},
                primary={key: k.get(key) for key in PRIMARY},
                latency_scope=k.get('latency_boundary'), energy_scope=k.get('energy_scope'),
                correct_tasks=k.get('correct_tasks'), attempted_tasks=k.get('total_tasks'),
                energy_unavailable_reason=k.get('energy_unavailable_reason'), treatment=treatment(item))


def collect(paths):
    valid, failures = [], []
    for path in paths:
        try:
            valid.append(load_archive(path))
        except (AttributeError, ValueError, OSError, TypeError, KeyError, OverflowError) as exc:
            failures.append(dict(archive=Path(path).name, status='integrity_or_format_failure', reason=str(exc)))
    return valid, failures


def summary(paths):
    items, failures = collect(paths)
    comparisons = []
    for index, left in enumerate(items):
        for right in items[index + 1:]:
            ordinary = compatibility(left, right)
            energy = compatibility(left, right, energy=True)
            delta = {}
            if ordinary['comparable']:
                for key in PRIMARY[:2]:
                    delta[key] = right['kpi'][key] - left['kpi'][key]
            if energy['comparable']:
                delta[PRIMARY[2]] = right['kpi'][PRIMARY[2]] - left['kpi'][PRIMARY[2]]
            comparisons.append(dict(left=left['path'].name, right=right['path'].name,
                                     correctness_latency=ordinary, energy=energy,
                                     delta_right_minus_left=delta,
                                     treatment_left=treatment(left), treatment_right=treatment(right)))
    groups = defaultdict(list)
    for item in items:
        try:
            key = digest(signature(item, energy=True))
        except (AttributeError, ValueError, TypeError, KeyError, OverflowError):
            continue
        groups[key].append(item)
    fronts = []
    for key, members in groups.items():
        if len(members) < 2:
            continue
        def dominates(a, b):
            x, y = a['kpi'], b['kpi']
            return (x[PRIMARY[0]] >= y[PRIMARY[0]] and x[PRIMARY[1]] <= y[PRIMARY[1]]
                    and x[PRIMARY[2]] <= y[PRIMARY[2]] and any(x[k] != y[k] for k in PRIMARY))
        fronts.append(dict(compatibility_group=key, archives=[m['path'].name for m in members],
                           nondominated=[m['path'].name for m in members
                                         if not any(dominates(other, m) for other in members)]))
    return dict(kind='experiment_summary', overall_winner=None,
                interpretation='Descriptive only. No quality approval or causal speedup claim. Diagnostic energy is displayed separately and cannot qualify deltas or Pareto groups; those require validated commissioned energy.',
                experiments=[public_item(item) for item in items], failures=failures,
                comparisons=comparisons, descriptive_pareto=fronts)


def campaign(paths):
    items, failures = collect(paths)
    groups = defaultdict(list); ungrouped = []
    for item in items:
        try:
            identity = signature(item)
        except (AttributeError, ValueError, TypeError, KeyError, OverflowError) as exc:
            ungrouped.append({**public_item(item), 'reason': str(exc)})
            continue
        # Repeated trials must share treatment and declared control; backend changes
        # belong in separate groups even when descriptive comparisons are possible.
        key = digest(dict(identity=identity, treatment=treatment(item)))
        groups[key].append(item)
    output = []
    for key, members in groups.items():
        energy_signatures = []
        for item in members:
            try:
                energy_signatures.append(digest(signature(item, energy=True)))
            except (AttributeError, ValueError, TypeError, KeyError, OverflowError):
                energy_signatures.append(None)
        energy_complete = None not in energy_signatures and len(set(energy_signatures)) == 1
        metrics = {metric: stats([item['kpi'].get(metric) for item in members]) for metric in PRIMARY[:2]}
        metrics[PRIMARY[2]] = stats([item['kpi'].get(PRIMARY[2]) for item in members]) if energy_complete else stats([None for _ in members])
        output.append(dict(group=key, n=len(members), attempts=[public_item(item) for item in members],
                           metrics=metrics, energy_comparable=energy_complete,
                           energy_reason=None if energy_complete else 'Missing or incompatible energy; no pooled energy statistic'))
    return dict(kind='experiment_campaign', overall_winner=None, total_attempts=len(items) + len(failures),
                groups=output, ungrouped_attempts=ungrouped, integrity_failures=failures,
                interpretation='All archives retained, including failed/incomplete attempts. Statistics are descriptive repetitions, not an uncertainty-adjusted winner.')


def case_comparison(left_path, right_path):
    left, right = load_archive(left_path), load_archive(right_path)
    for item in (left, right):
        if any(row.get('split') != 'development' for row in rows_of(item['result'])):
            raise ValueError('Case diagnostics require development-only archives; heldout/mixed/unknown split refused')
    comparable = compatibility(left, right)
    if not comparable['comparable']:
        raise ValueError('Incompatible case comparison: ' + '; '.join(comparable['reasons']))
    before = {r['id']: r for r in left['result']['results']}
    after = {r['id']: r for r in right['result']['results']}
    cases = []; tools = defaultdict(lambda: {'left': Counter(), 'right': Counter()})
    for id in sorted(before):
        a, b = before[id], after[id]
        tool = a.get('expected_tool', (a.get('expected') or {}).get('tool', 'unknown'))
        for side, row in [('left', a), ('right', b)]:
            tools[tool][side].update(taxonomy(row))
        def diagnostic(row):
            return dict(success=row['task_success'], errors=taxonomy(row), output_text=row.get('output_text'),
                        arguments=row.get('arguments'), action=row.get('tool'),
                        generated_tokens=(row.get('profile') or {}).get('generated_tokens'),
                        inference_latency_ms=row.get('latency_ms'),
                        task_latency_ms=row.get('warm_task_latency_ms', row.get('task_latency_ms')))
        da, db = diagnostic(a), diagnostic(b)
        deltas = {key: db[key] - da[key] if finite(da[key]) and finite(db[key]) else None
                  for key in ('generated_tokens', 'inference_latency_ms', 'task_latency_ms')}
        cases.append(dict(id=id, case_sha256=a['case_sha256'], expected_tool=tool,
                          outcome='fixed' if not a['task_success'] and b['task_success'] else
                                  'regressed' if a['task_success'] and not b['task_success'] else 'unchanged',
                          left=da, right=db, delta_right_minus_left=deltas))
    return dict(kind='development_case_comparison', left=left['path'].name, right=right['path'].name,
                overall_winner=None, treatment_left=treatment(left), treatment_right=treatment(right),
                correctness_latency=comparable, energy=compatibility(left, right, energy=True),
                per_tool_error_taxonomy=dict(tools), cases=cases,
                interpretation='Frozen flags are preserved; raw output is diagnostic only and has not been rescored. Token/length changes do not establish native decode speedup.')


def error_analysis(path):
    """Single-archive development diagnostics; preserve frozen flags and raw evidence."""
    item = load_archive(path)
    rows = rows_of(item['result'])
    if not rows or any(row.get('split') != 'development' for row in rows):
        raise ValueError('Error diagnostics require development-only archives; heldout/mixed/unknown split refused')
    failures, by_tool, mechanisms = [], defaultdict(Counter), Counter()
    clarification_total = clarification_failures = 0
    for row in rows:
        expected = row.get('expected')
        if expected is not None and not isinstance(expected, dict):
            raise ValueError('Malformed expected action')
        expected_tool = row.get('expected_tool', (expected or {}).get('tool'))
        if not isinstance(expected_tool, str) or not expected_tool:
            raise ValueError('Missing expected tool')
        labels = taxonomy(row)
        by_tool[expected_tool].update(labels)
        if expected_tool == 'clarify':
            clarification_total += 1
            clarification_failures += row['task_success'] is not True
        if row['task_success'] is True:
            continue
        raw = row.get('output_text')
        profile = row.get('profile') or {}
        if not isinstance(profile, dict):
            raise ValueError('Malformed generation profile')
        observed = []
        if row.get('invalid_output') is True: observed.append('invalid_output_flag')
        if row.get('parse_error'): observed.append('parser_error_recorded')
        if isinstance(raw, str) and raw.count('</tool_call>') > 1:
            observed.append('multiple_closing_tool_tags_in_raw_text')
        if expected_tool == 'clarify' and row.get('tool') not in (None, 'clarify'):
            observed.append('nonclarifying_action_on_expected_clarification')
        if row.get('execution_error'): observed.append('runtime_error_recorded')
        if row.get('execution_ok') is False: observed.append('execution_failed')
        if row.get('final_state_match') is False: observed.append('final_state_mismatch')
        mechanisms.update(observed)
        failures.append(dict(id=row.get('id'), case_sha256=row.get('case_sha256'),
            prompt=row.get('prompt'), expected=expected, expected_tool=expected_tool, actual_tool=row.get('tool'),
            actual_arguments=row.get('arguments'), output_text=raw,
            failure_reasons=row.get('failure_reasons'), taxonomy=labels,
            observed_mechanisms=observed, invalid_output=row.get('invalid_output'),
            parse_error=row.get('parse_error'), execution_error=row.get('execution_error'),
            generated_tokens=profile.get('generated_tokens'), stop_reason=profile.get('stop_reason'),
            generation_control=row.get('generation_control'), sampling=row.get('sampling'),
            inference_latency_ms=row.get('latency_ms'), task_latency_ms=row.get('task_latency_ms'),
            warm_task_latency_ms=row.get('warm_task_latency_ms')))
    return dict(kind='development_error_analysis', overall_winner=None,
        archive=public_item(item), result_dirty=item['result'].get('dirty'),
        recorded_cases=len(rows), recorded_failures=len(failures),
        clarification=dict(cases=clarification_total, failed=clarification_failures,
                           failed_case_ids=[r['id'] for r in failures if r['expected_tool'] == 'clarify']),
        per_tool_error_taxonomy={key: dict(value) for key, value in by_tool.items()},
        observed_mechanism_counts=dict(mechanisms), cases=failures,
        interpretation='Single-archive development diagnostics; no comparative provenance or quality approval is claimed. Dirty/historical status remains visible. Frozen flags and raw evidence are preserved without rescoring. Observed text patterns and failure flags are not causal diagnoses. Missing tokens/stop reasons remain unavailable.')


def markdown(report):
    """Compact primary KPI view; full evidence remains in the same local report."""
    def cell(value):
        if value is None:
            return 'UNAVAILABLE'
        if type(value) is float:
            return f'{value:.3f}'
        return str(value).replace('|', r'\|').replace('\n', ' ')
    lines = ['# ' + report['kind'].replace('_', ' ').title(), '',
             report.get('interpretation', ''), '', '**No overall winner.**', '']
    if report['kind'] == 'experiment_summary':
        lines += ['| Archive | Success % | Median task ms | SYS J/correct (see qualification) | Latency scope | Energy scope | Status | Energy qualification |',
                  '|---|---:|---:|---:|---|---|---|---|']
        for item in report['experiments']:
            values = [item['archive'], *(item['primary'][k] for k in PRIMARY),
                      item['latency_scope'], item['energy_scope'], item['status'], item['energy_qualification']]
            lines.append('| ' + ' | '.join(cell(v) for v in values) + ' |')
        if report['failures']:
            lines += ['', '## Archives excluded from numerical comparison', '']
            lines += [f"- {cell(item['archive'])}: {cell(item['reason'])}" for item in report['failures']]
    elif report['kind'] == 'development_error_analysis':
        lines += [f"Archive: {cell(report['archive']['archive'])}; qualification: {cell(report['archive']['qualification'])}; dirty: {cell(report['result_dirty'])}.", '',
                  f"Recorded cases: {report['recorded_cases']}; failures: {report['recorded_failures']}; clarification failures: {report['clarification']['failed']}/{report['clarification']['cases']}.", '',
                  '| Case | Expected tool | Actual tool | Error taxonomy | Tokens | Stop reason |',
                  '|---|---|---|---|---:|---|']
        for item in report['cases']:
            values = [item['id'], item['expected_tool'], item['actual_tool'], ', '.join(item['taxonomy']), item['generated_tokens'], item['stop_reason']]
            lines.append('| ' + ' | '.join(cell(v) for v in values) + ' |')
    elif report['kind'] == 'experiment_campaign':
        lines += [f"Total attempts: {report['total_attempts']}; ungrouped attempts: {len(report['ungrouped_attempts'])}; integrity failures: {len(report['integrity_failures'])}.", '',
                  '| Group | Metric | n | Mean | Median | Sample SD | CV | Min | Max |',
                  '|---|---|---:|---:|---:|---:|---:|---:|---:|']
        for group in report['groups']:
            for metric, statistic in group['metrics'].items():
                values = [group['group'][:12], metric, *(statistic.get(k) for k in ('n', 'mean', 'median', 'stddev', 'cv', 'min', 'max'))]
                lines.append('| ' + ' | '.join(cell(v) for v in values) + ' |')
    else:
        lines += ['| Case | Expected tool | Outcome | Token delta | Inference ms delta | Task ms delta |',
                  '|---|---|---|---:|---:|---:|']
        for item in report['cases']:
            values = [item['id'], item['expected_tool'], item['outcome'],
                      *(item['delta_right_minus_left'][k] for k in ('generated_tokens', 'inference_latency_ms', 'task_latency_ms'))]
            lines.append('| ' + ' | '.join(cell(v) for v in values) + ' |')
    return '\n'.join(lines)


def write_report(output, report, sources):
    """Exclusive new report outside every source archive; never changes its evidence."""
    path = Path(output).resolve()
    for source in sources:
        source = Path(source).resolve()
        if path == source or path.is_relative_to(source):
            raise ValueError('Report output must be outside source archives')
    if path.suffix not in ('.json', '.md'):
        raise ValueError('Report output must end in .json or .md')
    data = json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False)
    if path.suffix == '.md':
        data = markdown(report) + '\n\n## Complete evidence\n\n```json\n' + data + '\n```'
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as handle:
        handle.write(data + '\n')
    return path
