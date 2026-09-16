"""Conservative cross-backend decision report; never runs inference."""
import argparse
import hashlib
import hashlib
import json
import math
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from eval.scoring import compare, summarize

SLOTS = {'cpu': 'llama_cpp_cpu', 'htp': 'llama_cpp_htp', 'qairt': 'qairt_npu'}
PROVENANCE = ('git_commit', 'benchmark_version', 'protocol_version', 'dataset_sha256',
              'fixture_sha256', 'action_schema_sha256', 'system_prompt_sha256',
              'evaluator_sha256', 'generation_protocol')


def finite(value, positive=False):
    return type(value) in (int, float) and math.isfinite(value) and (value > 0 if positive else value >= 0)


def distribution(values):
    if not values or any(not finite(v) for v in values):
        return {'mean': None, 'median': None, 'p95': None, 'samples': len(values)}
    return {'mean': statistics.mean(values), 'median': statistics.median(values),
            'p95': sorted(values)[math.ceil(.95*len(values))-1] if len(values) >= 20 else None,
            'samples': len(values)}


def energy_summary(cases):
    """Suite aggregation: failures count; missing values never become zero."""
    gross = [(c.get('energy') or {}).get('gross_energy_j') for c in cases]
    net = [(c.get('energy') or {}).get('net_energy_j') for c in cases]
    correct = sum(c.get('task_success') is True for c in cases)
    total = sum(gross) if gross and all(finite(v) for v in gross) else None
    net_total = sum(net) if net and all(finite(v) for v in net) else None
    return {'total_gross_energy_j': total, 'total_net_energy_j': net_total,
            'net_unavailable_reason': None if net_total is not None else 'Missing or invalid net energy; no partial total',
            'joules_per_task': total/len(cases) if total is not None else None,
            'joules_per_correct_task': total/correct if total is not None and correct else None,
            'energy_per_task_j': distribution(gross),
            'warm_task_latency_ms': distribution([c.get('warm_task_latency_ms') for c in cases]),
            'successful_tasks_energy_j_diagnostic_only': distribution([
                (c.get('energy') or {}).get('gross_energy_j') for c in cases if c.get('task_success') is True])}


def known(value):
    return isinstance(value, str) and bool(value.strip()) and value.lower() not in ('unknown', 'unavailable')


def raw_valid(energy):
    before, after = energy.get('raw_before') or {}, energy.get('raw_after') or {}
    return (not before.get('error') and not after.get('error')
            and finite(before.get('monotonic_s')) and finite(after.get('monotonic_s'))
            and after['monotonic_s'] > before['monotonic_s']
            and finite((before.get('channels_pwh') or {}).get('SYS'))
            and finite((after.get('channels_pwh') or {}).get('SYS'))
            and after['channels_pwh']['SYS'] > before['channels_pwh']['SYS']
            and finite(energy.get('duration_s'), True) and finite(energy.get('gross_energy_j'))
            and math.isclose(energy['duration_s'], after['monotonic_s'] - before['monotonic_s'], rel_tol=1e-7, abs_tol=1e-9)
            and math.isclose(energy['gross_energy_j'], (after['channels_pwh']['SYS'] - before['channels_pwh']['SYS']) * 3.6e-9, rel_tol=1e-7, abs_tol=1e-9))


def build(reports, baseline, policy, quality_policy, current_commit):
    """All energy includes failed tasks. Selection requires all three current runs."""
    accuracy = policy.get('min_accuracy_pct')
    limit = policy.get('max_e2e_latency_ms')
    stat = policy.get('latency_stat', 'p95')
    if stat not in ('p95', 'median', 'mean'):
        raise ValueError('latency_stat must be p95, median or mean')
    if accuracy is not None and (not finite(accuracy) or accuracy > 100):
        raise ValueError('Invalid minimum accuracy')
    if limit is not None and not finite(limit, True):
        raise ValueError('Invalid latency limit')
    output = {'schema_version': 'secretary-decision-v1', 'current_commit': current_commit,
              'generated_at': datetime.now(timezone.utc).isoformat(), 'policy': policy, 'rows': [], 'comparison_status': 'NOT_ENOUGH_DATA',
              'comparison_reasons': [], 'winner': None,
              'objective_winners': {k: None for k in ('lowest_joules_per_correct_task', 'lowest_latency', 'highest_accuracy', 'lowest_joules_per_task', 'best_eligible')},
              'modes': {'FAST': None, 'BALANCED': None, 'EFFICIENT': None}}
    for slot, backend in SLOTS.items():
        report = reports.get(slot)
        row = {'backend': backend, 'status': 'NOT_MEASURED', 'reasons': [], 'eligible': False,
               'accuracy_pct': None, 'invalid_rate': None, 'latency_ms': None,
               'gross_energy_j': None, 'joules_per_task': None, 'joules_per_correct_task': None,
               'correct_tasks': None, 'tasks': None, 'peak_ram': None, 'clarification_accuracy_pct': None,
               'critical_move_failures': None, 'measurement_summary': None, 'provenance': None,
               'quality_gate': {'status': 'NOT_EVALUATED', 'reasons': ['Measured run unavailable']}}
        output['rows'].append(row)
        if not report or report.get('status') != 'measured':
            row['reasons'].append('No measured report supplied')
            continue
        row['status'] = 'NOT_COMPARABLE'
        row['provenance'] = {**{k: report.get(k) for k in PROVENANCE},
                             'source': report.get('_source'), 'timestamp': report.get('timestamp'),
                             'energy_measurement': report.get('energy_measurement')}
        cases = report.get('results', [])
        if report.get('schema_version') != 2:
            row['reasons'].append('Expected report schema_version 2')
            continue
        boolean_fields = ('task_success', 'tool_correct', 'action_correct', 'arguments_correct', 'no_action_correct', 'invalid_output')
        if any(type(c.get(k)) is not bool for c in cases for k in boolean_fields):
            row['reasons'].append('Scoring flags must be booleans')
            continue
        if not cases:
            row['reasons'].append('No task results')
            continue
        if any(not finite(c.get('latency_ms')) for c in cases):
            row['reasons'].append('Inference latency is missing or nonfinite')
            continue
        if baseline and any(type(c.get(k)) is not bool for c in baseline.get('results', []) for k in boolean_fields):
            row['reasons'].append('Baseline scoring flags must be booleans')
            continue
        try:
            metrics = summarize(cases)
            row.update(accuracy_pct=metrics['task_accuracy'], invalid_rate=metrics['invalid_output_rate'],
                       tasks=len(cases), correct_tasks=metrics['task_success'],
                       clarification_accuracy_pct=metrics['clarification_accuracy'],
                       critical_move_failures=sum(not c['task_success'] for c in cases if c.get('expected_tool', c.get('expected', {}).get('tool')) == 'move_file'))
            row['measurement_summary'] = energy_summary(cases)
            row['quality_gate'] = compare(report, baseline, quality_policy)
        except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
            row['reasons'].append('Invalid scoring report: ' + str(exc))
            continue
        energy = report.get('energy_measurement') or {}
        signature = energy.get('signature') or {}
        if baseline:
            baseline_energy = baseline.get('energy_measurement') or {}
            if (baseline_energy.get('valid') is not True or baseline_energy.get('invalid_reasons') != [] or baseline_energy.get('signature') != signature
                    or any(baseline.get(k) != report.get(k) for k in PROVENANCE)):
                row['reasons'].append('Decision reference is NOT_COMPARABLE: energy protocol or current provenance differs')
        row['peak_ram'] = energy.get('process_memory')
        if report.get('dirty') is not False or not report.get('git_commit'):
            row['reasons'].append('Run is dirty or measurement commit is unknown')
        for key in PROVENANCE + ('model_sha256', 'config_sha256'):
            if not report.get(key): row['reasons'].append('Missing provenance: ' + key)
        if (report.get('inference_backend') or {}).get('backend_id') != backend:
            row['reasons'].append('Backend identity does not match slot')
        if len({c.get('id') for c in cases}) != len(cases) or any(not c.get('id') or not c.get('case_sha256') for c in cases):
            row['reasons'].append('Missing or duplicate case provenance')
        if energy.get('valid') is not True or energy.get('schema_version') != 'secretary-energy-v1' or energy.get('invalid_reasons') != []:
            row['reasons'].append('Energy measurement is missing or invalid')
        for key in ('boundary', 'channel', 'warmup_count', 'idle_window_s', 'idle_repeats',
                    'counter_resolution_s', 'instrumentation_sha256', 'protocol_sha256',
                    'runtime_files_sha256', 'power_condition', 'machine'):
            if signature.get(key) is None or signature.get(key) == {}:
                row['reasons'].append('Missing energy signature: ' + key)
        if type(signature.get('warmup_count')) is not int or signature['warmup_count'] < 1:
            row['reasons'].append('Warmup count must be a positive integer')
        for key in ('idle_window_s', 'idle_repeats', 'counter_resolution_s'):
            if not finite(signature.get(key), True):
                row['reasons'].append('Invalid energy signature: ' + key)
        if signature.get('boundary') != 'warm_task_v1' or signature.get('channel') != 'SYS':
            row['reasons'].append('Energy boundary/channel is not warm task SYS')
        power = signature.get('power_condition') or {}
        if (power.get('ac_line_status') not in ('ac', 'battery') or not known(power.get('active_scheme_guid'))
                or not known(power.get('power_mode')) or type(power.get('battery_saver')) is not bool):
            row['reasons'].append('Power signature is unknown or incomplete')
        machine = signature.get('machine') or {}
        if any(not known(machine.get(k)) for k in ('system', 'machine', 'hardware_note')):
            row['reasons'].append('Machine identity is incomplete')
        for observed in ('power_before', 'power_ready', 'power_after'):
            record = energy.get(observed) or {}
            if any(record.get(k) != power.get(k) for k in ('ac_line_status', 'active_scheme_guid', 'battery_saver')):
                row['reasons'].append('Power observation missing or inconsistent: ' + observed)
        if any(not raw_valid(c.get('energy') or {}) for c in cases):
            row['reasons'].append('Raw SYS counter observations are missing or inconsistent with energy/duration')
        resolution = signature.get('counter_resolution_s')
        if finite(resolution, True) and any(not finite((c.get('energy') or {}).get('duration_s'), True) or c['energy']['duration_s'] < 2 * resolution for c in cases):
            row['reasons'].append('Task duration is below two declared counter intervals')
        energies = [(c.get('energy') or {}).get('gross_energy_j') for c in cases]
        if any(not finite(e) for e in energies) or any(not finite((c.get('energy') or {}).get('duration_s'), True) for c in cases) or any((c.get('energy') or {}).get('scope') != 'warm_task' or (c.get('energy') or {}).get('channel') != 'SYS' for c in cases):
            row['reasons'].append('Missing or invalid per-task gross SYS energy')
        else:
            total = sum(energies)
            row.update(gross_energy_j=total, joules_per_task=total/len(cases),
                       joules_per_correct_task=total/metrics['task_success'] if metrics['task_success'] else None)
            if not metrics['task_success']: row['reasons'].append('Zero correct tasks: J/correct task undefined')
        latencies = [c.get('warm_task_latency_ms') for c in cases]
        if any(not finite(v, True) for v in latencies) or (stat == 'p95' and len(cases) < 20):
            row['reasons'].append('Missing valid warm-task latency or fewer than 20 p95 samples')
        else:
            row['latency_ms'] = {'mean': statistics.mean, 'median': statistics.median,
                                 'p95': lambda x: sorted(x)[math.ceil(.95*len(x))-1]}[stat](latencies)
        if not row['reasons']: row['status'] = 'MEASURED'
        if accuracy is None or limit is None:
            row['reasons'].append('Accuracy and latency thresholds require an explicit decision')
        elif row['accuracy_pct'] < accuracy or row['latency_ms'] is None or row['latency_ms'] > limit:
            row['reasons'].append('Accuracy or latency threshold failed')
        if row['invalid_rate'] > quality_policy.get('max_invalid_action_rate', .02):
            row['reasons'].append('Invalid output safety limit failed')
        if row['quality_gate']['status'] != 'PASS':
            row['reasons'].append('Official correctness quality gate is not PASS')
        row['eligible'] = not row['reasons']
    if all(reports.get(k) and r['status'] == 'MEASURED' for k, r in zip(SLOTS, output['rows'])):
        ref = reports['cpu']
        for slot in ('htp', 'qairt'):
            other = reports[slot]
            for key in PROVENANCE:
                if ref.get(key) != other.get(key): output['comparison_reasons'].append(slot + ': incompatible ' + key)
            if ref['energy_measurement']['signature'] != other['energy_measurement']['signature']:
                output['comparison_reasons'].append(slot + ': incompatible energy signature')
            if {c['id']: c['case_sha256'] for c in ref['results']} != {c['id']: c['case_sha256'] for c in other['results']}:
                output['comparison_reasons'].append(slot + ': different cases')
        if ref['model_sha256'] != reports['htp']['model_sha256']:
            output['comparison_reasons'].append('CPU and HTP must use the same GGUF artifact')
        output['comparison_status'] = 'NOT_COMPARABLE' if output['comparison_reasons'] else 'COMPARABLE'
        eligible = [r for r in output['rows'] if r['eligible']]
        if not output['comparison_reasons'] and eligible:
            output['winner'] = min(eligible, key=lambda r: r['joules_per_correct_task'])['backend']
            output['modes']['EFFICIENT'] = output['winner']
            output['modes']['FAST'] = min(eligible, key=lambda r: r['latency_ms'])['backend']
            for name, metric in [('lowest_joules_per_correct_task', 'joules_per_correct_task'),
                                 ('lowest_latency', 'latency_ms'), ('lowest_joules_per_task', 'joules_per_task')]:
                output['objective_winners'][name] = min(eligible, key=lambda r: r[metric])['backend']
            output['objective_winners']['highest_accuracy'] = max(eligible, key=lambda r: r['accuracy_pct'])['backend']
            output['objective_winners']['best_eligible'] = output['winner']
    if all(reports.get(k) and reports[k].get('status') == 'measured' for k in SLOTS) and any(r['status'] == 'NOT_COMPARABLE' for r in output['rows']):
        output['comparison_status'] = 'NOT_COMPARABLE'
    return output


def markdown(report):
    def cell(value): return 'NOT_MEASURED' if value is None else str(round(value, 4)) if isinstance(value, float) else str(value)
    lines = ['# Secretary energy decision matrix', '', 'Objective: minimize gross SYS joules per correct task, subject to correctness and latency limits.',
             '', 'Comparison: **' + report['comparison_status'] + '**. Winner: **' + (report['winner'] or 'NOT ENOUGH DATA') + '**.',
             '', '| Config | Accuracy % | E2E latency ms | J/task | J/correct | Invalid | Clarify % | Peak RAM MB | Notes |',
             '|---|---:|---:|---:|---:|---:|---:|---:|---|']
    for r in report['rows']:
        values = [r[k] for k in ('backend', 'accuracy_pct', 'latency_ms', 'joules_per_task', 'joules_per_correct_task', 'invalid_rate', 'clarification_accuracy_pct')]
        values += [(r['peak_ram'] or {}).get('peak_working_set_mb'), r['status'] + '; gate=' + r['quality_gate']['status'] + '; move failures=' + ('UNAVAILABLE' if r['critical_move_failures'] is None else str(r['critical_move_failures']))]
        lines.append('| ' + ' | '.join(('NOT_MEASURED' if r['status'] == 'NOT_MEASURED' else 'UNAVAILABLE') if v is None else cell(v) for v in values) + ' |')
    lines += ['', '## Selection policy', '', '```json', json.dumps(report['policy'], indent=2), '```', '',
              'All tasks, including failures, contribute to total energy. J/correct task is undefined with zero successes. Latency excludes fixture preparation and final state comparison; parsing and execution are inside the measured boundary. p95 requires at least 20 samples.',
              '', 'Gross energy is the primary metric. Net energy is diagnostic only. Peak process RAM, available only when measured, is preserved in the JSON companion; it is not total system memory.',
              '', '## Readiness and exclusions', '']
    for r in report['rows']:
        lines.append('- **' + r['backend'] + '**: ' + ('; '.join(r['reasons']) or 'Eligible'))
        for reason in r['quality_gate'].get('reasons', []): lines.append('  - Quality gate: ' + reason)
    lines.extend('- ' + reason for reason in report['comparison_reasons'])
    lines += ['', '## Modes', '']
    lines.extend('- ' + mode + ': ' + (backend or 'NOT ENOUGH DATA') for mode, backend in report['modes'].items())
    lines += ['', 'EFFICIENT minimizes J/correct task; FAST minimizes the configured latency statistic. BALANCED remains undefined until an explicit Pareto/tie policy is agreed. These are report recommendations, not routing changes.',
              '', 'Historical references are never promoted to a current baseline. No winner is issued without all three current comparable measurements, explicit thresholds and an approved correctness gate. Missing measurements remain unknown.', '']
    lines += ['## Winners by objective', '']
    lines.extend('- ' + name + ': ' + (value or 'NOT ENOUGH DATA') for name, value in report['objective_winners'].items())
    lines += ['', '## Measurement provenance and summaries', '', 'Generated: ' + report['generated_at'], '', 'Generator: ' + json.dumps(report.get('generator', {'commit':report['current_commit']})), '']
    for row in report['rows']:
        lines += ['### ' + row['backend'], '', '```json', json.dumps({'provenance': row['provenance'], 'summary': row['measurement_summary']}, indent=2), '```', '']
    return '\n'.join(lines)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for slot in SLOTS: p.add_argument('--' + slot, type=Path)
    p.add_argument('--baseline', type=Path)
    p.add_argument('--policy', type=Path, default=ROOT/'eval/decision_policy.json')
    p.add_argument('--output', type=Path, default=ROOT/'docs/decision-matrix.md')
    args = p.parse_args()
    def read(path):
        if not path: return None
        data = json.loads(path.read_text())
        if isinstance(data, dict) and 'results' in data:
            resolved = path.resolve()
            try: label = resolved.relative_to(ROOT).as_posix()
            except ValueError: label = path.name
            data['_source'] = {'path': label, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        return data
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    result = build({slot: read(getattr(args, slot)) for slot in SLOTS}, read(args.baseline),
                   read(args.policy), read(ROOT/'eval/quality_policy.json'), commit)
    result['generator'] = {'commit':commit,
        'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'dirty':bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip())}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(markdown(result), encoding='utf-8')
    args.output.with_suffix('.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    print(result['comparison_status'] + ': ' + (result['winner'] or 'NOT ENOUGH DATA'))


if __name__ == '__main__': main()
