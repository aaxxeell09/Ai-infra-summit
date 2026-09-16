"""Read-only, descriptive Secretary correctness/latency comparison; no winner selection."""
import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from eval.decision_table import SLOTS, build as energy_build, distribution, finite

MATCH = ('benchmark_version', 'protocol_version', 'scope', 'dataset_sha256',
         'fixture_sha256', 'action_schema_sha256', 'system_prompt_sha256', 'evaluator_sha256', 'warmup')
LATENCY_BOUNDARY = 'latency_ms: timed model inference request, before scoring and fixture execution; not end-to-end task latency'


def identity(report, cases):
    explicit = report.get('inference_backend') or {}
    if explicit.get('backend_id'):
        return {**explicit, 'identity_source': 'inference_backend'}
    # Older reports predate explicit backend_id. Require plugin AND actual selected devices.
    plugin = (report.get('config') or {}).get('plugin')
    devices = sorted({c.get('selected_device') for c in cases if isinstance(c.get('selected_device'), str)})
    complete = len(devices) == 1 and all(c.get('selected_device') == devices[0] for c in cases)
    backend = None
    if plugin == 'llama_cpp' and complete:
        backend = {'cpu': 'llama_cpp_cpu', 'HTP0': 'llama_cpp_htp'}.get(devices[0])
    return {'backend_id': backend, 'runtime': plugin, 'resolved_devices': devices,
            'identity_source': 'legacy config.plugin + per-case selected_device', 'dispatch_verified': False}


def build(reports, dataset='all'):
    out = {'schema_version': 'secretary-descriptive-comparison-v1', 'selection': dataset,
           'latency_boundary': LATENCY_BOUNDARY, 'rows': [], 'overall_winner': None,
           'correctness_latency_comparable': False, 'energy_comparable': False,
           'correctness_latency_reasons': [], 'energy_reasons': [],
           'warnings': ['Descriptive results do not establish a hardware-only speedup or an official quality gate. Model artifacts and generation settings are reported treatments.']}
    reasons = out['correctness_latency_reasons']
    selected = {}
    for slot, expected_backend in SLOTS.items():
        report = reports.get(slot)
        row = {'slot': slot, 'backend': None, 'metrics': None, 'provenance': {}, 'cases': [], 'reasons': []}
        out['rows'].append(row)
        if not isinstance(report, dict):
            row['reasons'].append('Missing report')
            continue
        cases = report.get('results')
        if not isinstance(cases, list) or any(not isinstance(c, dict) for c in cases):
            row['reasons'].append('Invalid results array')
            continue
        if dataset == 'dev':
            cases = [c for c in cases if c.get('split') == 'development']
        selected[slot] = {**report, 'results': cases}
        row['backend'] = identity(report, cases)
        row['provenance'] = {k: report.get(k) for k in MATCH + ('git_commit', 'dirty', 'environment', 'model_sha256', 'model_label', 'config_sha256', 'generation_protocol', 'config', 'runtime_version', '_source')}
        row['cases'] = [{'id': c.get('id'), 'case_sha256': c.get('case_sha256')} for c in cases]
        row['source_case_count'] = len(report['results'])
        if report.get('status') != 'measured' or report.get('schema_version') != 2:
            row['reasons'].append('Expected measured schema_version 2 report')
        if row['backend']['backend_id'] != expected_backend:
            row['reasons'].append('Backend identity missing or does not match slot')
        for key in MATCH:
            if not report.get(key): row['reasons'].append('Missing provenance: ' + key)
        if not cases:
            row['reasons'].append('No selected cases')
            continue
        if any(not isinstance(c.get('id'), str) or not c['id'] or not isinstance(c.get('case_sha256'), str) or not c['case_sha256'] for c in cases) or len({str(c.get('id')) for c in cases}) != len(cases):
            row['reasons'].append('Missing or duplicate case provenance')
        if any(type(c.get(k)) is not bool for c in cases for k in ('task_success', 'invalid_output', 'no_action_correct')):
            row['reasons'].append('Scoring flags must be booleans')
            continue
        if any(not c.get('expected_tool', (c.get('expected') or {}).get('tool')) for c in cases):
            row['reasons'].append('Missing expected tool for clarification denominator')
            continue
        if any(not finite(c.get('latency_ms')) for c in cases):
            row['reasons'].append('Missing/nonfinite/negative inference latency')
        clarify = [c for c in cases if c.get('expected_tool', (c.get('expected') or {}).get('tool')) == 'clarify']
        success = sum(c['task_success'] for c in cases)
        row['metrics'] = {'tasks': len(cases), 'task_success': success, 'accuracy_pct': 100 * success / len(cases),
                          'invalid_output_rate': sum(c['invalid_output'] for c in cases) / len(cases),
                          'clarification_cases': len(clarify),
                          'clarification_accuracy_pct': 100 * sum(c['no_action_correct'] for c in clarify) / len(clarify) if clarify else None,
                          'inference_latency_ms': distribution([c.get('latency_ms') for c in cases])}
    for row in out['rows']:
        reasons.extend(row['slot'] + ': ' + r for r in row['reasons'])
    if all(slot in selected for slot in SLOTS):
        ref = selected['cpu']
        for slot in ('htp', 'qairt'):
            other = selected[slot]
            for key in MATCH:
                if ref.get(key) != other.get(key): reasons.append(slot + ': incompatible ' + key)
            if sorted(out['rows'][0]['cases'], key=lambda c: str(c['id'])) != sorted(next(r for r in out['rows'] if r['slot'] == slot)['cases'], key=lambda c: str(c['id'])):
                reasons.append(slot + ': different case ids or case_sha256')
            for key in ('generation_protocol', 'model_sha256', 'config_sha256', 'environment', 'git_commit'):
                if ref.get(key) != other.get(key): out['warnings'].append(slot + ': different ' + key + ' (see provenance)')
    out['correctness_latency_comparable'] = not reasons
    # Reuse the stricter energy protocol validation, independent of policy thresholds.
    # Its MEASURED status precedes eligibility/quality-gate checks; no reference or winner is requested.
    try:
        energy = energy_build(copy.deepcopy(selected), None, {'min_accuracy_pct': None, 'max_e2e_latency_ms': None}, {}, None)
        out['energy_comparable'] = out['correctness_latency_comparable'] and energy['comparison_status'] == 'COMPARABLE'
        out['energy_reasons'] = energy['comparison_reasons'][:]
        for row in energy['rows']:
            if row['status'] != 'MEASURED':
                out['energy_reasons'].extend(row['backend'] + ': ' + r for r in row['reasons'] if r not in ('Accuracy and latency thresholds require an explicit decision', 'Official correctness quality gate is not PASS', 'Invalid output safety limit failed'))
        if not out['correctness_latency_comparable']:
            out['energy_reasons'].append('Correctness/latency provenance is incompatible')
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
        out['energy_reasons'].append('Invalid or unavailable energy report: ' + str(exc))
    return out


def markdown(report):
    lines = ['# Three-backend descriptive comparison', '',
             'Correctness/latency comparable: **' + str(report['correctness_latency_comparable']) + '**.',
             'Energy comparable: **' + str(report['energy_comparable']) + '**. No overall winner is selected.', '',
             report['latency_boundary'] + '. p95 is nearest-rank and requires at least 20 samples.', '',
             '| Slot | Backend identity | Success | Accuracy % | Invalid rate | Clarify % | Mean ms | Median ms | p95 ms |',
             '|---|---|---:|---:|---:|---:|---:|---:|---:|']
    def fmt(v): return 'unavailable' if v is None else str(round(v, 3)) if isinstance(v, float) else str(v)
    for row in report['rows']:
        m = row['metrics'] or {}; lat = m.get('inference_latency_ms') or {}
        values = [row['slot'], (row['backend'] or {}).get('backend_id'), str(m.get('task_success')) + '/' + str(m.get('tasks')), m.get('accuracy_pct'), m.get('invalid_output_rate'), m.get('clarification_accuracy_pct'), lat.get('mean'), lat.get('median'), lat.get('p95')]
        lines.append('| ' + ' | '.join(fmt(v) for v in values) + ' |')
    for key in ('correctness_latency_reasons', 'energy_reasons', 'warnings'):
        lines += ['', '## ' + key, ''] + ['- ' + r for r in report[key]]
    lines += ['', '## Provenance and exact selected cases', '', 'Source dataset hashes remain unchanged when selecting development rows. Full provenance and case hashes follow.', '']
    for row in report['rows']:
        lines += ['### ' + row['slot'], '', '```json', json.dumps({k: row[k] for k in ('backend', 'provenance', 'cases')}, indent=2), '```', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for slot in SLOTS: parser.add_argument('--' + slot, type=Path, required=True)
    parser.add_argument('--dataset', choices=('all', 'dev'), default='all', help='dev selects rows explicitly labeled development; source hashes are preserved')
    parser.add_argument('--output', type=Path, help='New .md report; also writes .json companion. Existing files are never overwritten.')
    args = parser.parse_args()
    reports = {}
    for slot in SLOTS:
        path = getattr(args, slot); raw = path.read_bytes()
        reports[slot] = json.loads(raw)
        reports[slot]['_source'] = {'filename': path.name, 'sha256': hashlib.sha256(raw).hexdigest()}
    report = build(reports, args.dataset)
    if args.output:
        if args.output.suffix != '.md': parser.error('--output must end in .md')
        paths = [args.output, args.output.with_suffix('.json')]
        if any(p.exists() for p in paths): parser.error('Refusing to overwrite existing report')
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with paths[0].open('x', encoding='utf-8') as f: f.write(markdown(report) + '\n')
        with paths[1].open('x', encoding='utf-8') as f: json.dump(report, f, indent=2, allow_nan=False)
    else:
        print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == '__main__': main()
