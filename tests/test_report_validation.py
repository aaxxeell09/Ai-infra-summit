"""Imported evidence validation and non-destructive report writing."""
import pytest
from eval.report_validation import backend_identity_errors, energy_evidence_errors, write_report_pair
from tests.test_decision_table import fixture


def test_complete_synthetic_commissioning_is_accepted():
    reports, _ = fixture()
    assert energy_evidence_errors(reports['cpu']) == []


@pytest.mark.parametrize('mutation', ['protocol_hash', 'resolution', 'idle_missing', 'idle_unstable', 'warmup_missing', 'power', 'runtime'])
def test_inconsistent_commissioning_is_rejected(mutation):
    reports, _ = fixture()
    report = reports['cpu']; energy = report['energy_measurement']
    if mutation == 'protocol_hash': energy['signature']['protocol_sha256'] = 'wrong'
    if mutation == 'resolution': energy['signature']['counter_resolution_s'] = .01
    if mutation == 'idle_missing': del energy['idle_platform']
    if mutation == 'idle_unstable': energy['idle_runtime']['samples'][0]['gross_energy_j'] *= 2
    if mutation == 'warmup_missing': energy['warmups'].pop()
    if mutation == 'power': energy['power_ready']['ac_line_status'] = 'battery'
    if mutation == 'runtime': energy['signature']['runtime_files_sha256'] = {}
    assert energy_evidence_errors(report)


@pytest.mark.parametrize('record', [dict(config={'plugin': 'qairt'}), dict(results=[{'selected_device':'cpu'}]), dict(inference_backend={'backend_id':'llama_cpp_htp','runtime':'qairt'})])
def test_backend_metadata_contradictions(record):
    report = {'inference_backend': {'backend_id': 'llama_cpp_htp'}}
    report.update(record)
    assert backend_identity_errors(report, 'llama_cpp_htp')


def test_unverified_dispatch_does_not_mean_cpu():
    report = {'inference_backend': {'backend_id':'qairt_npu', 'runtime':'qairt', 'dispatch_verified':False},
              'results':[{'selected_device':'HTP0'}]}
    assert backend_identity_errors(report, 'qairt_npu') == []


def test_pair_write_creates_both(tmp_path):
    target = tmp_path/'report.md'
    write_report_pair(target, '# Report', '{}')
    assert target.read_text() == '# Report'
    assert target.with_suffix('.json').read_text() == '{}'


@pytest.mark.parametrize('suffix', ['.md', '.json'])
def test_pair_refuses_either_existing_output(tmp_path, suffix):
    target = tmp_path/'report.md'; existing = target.with_suffix(suffix)
    existing.write_text('frozen')
    with pytest.raises(ValueError): write_report_pair(target, '# Report', '{}')
    assert existing.read_text() == 'frozen'
    assert not target.with_suffix('.json' if suffix == '.md' else '.md').exists()


def test_pair_refuses_inputs_and_bad_suffix(tmp_path):
    target = tmp_path/'report.md'
    with pytest.raises(ValueError): write_report_pair(target, '', '', inputs=[target.with_suffix('.json')])
    with pytest.raises(ValueError): write_report_pair(target.with_suffix('.json'), '', '')
    assert not list(tmp_path.iterdir())


def test_companion_creation_race_preserves_other_writer(tmp_path, monkeypatch):
    from pathlib import Path
    target = tmp_path/'report.md'
    companion = target.with_suffix('.json')
    original = Path.open
    def race(path, mode='r', *args, **kwargs):
        if path == companion and mode == 'x':
            with original(path, 'w') as handle:
                handle.write('other writer')
        return original(path, mode, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', race)
    with pytest.raises(FileExistsError):
        write_report_pair(target, '# Report', '{}')
    assert not target.exists()
    assert companion.read_text() == 'other writer'


def test_identity_classification_never_uses_requested_device_as_dispatch():
    from eval.report_validation import classify_backend_identity
    report = {'inference_backend': {'backend_id':'qairt_npu','runtime':'qairt',
                                    'requested_device':'npu','dispatch_verified':True}}
    assert classify_backend_identity(report)['classification'] == 'consistent_but_dispatch_unverified'
    report['inference_backend']['resolved_device'] = 'HTP0'
    assert classify_backend_identity(report)['classification'] == 'verified_consistent'
    report['inference_backend']['dispatch_verified'] = False
    assert classify_backend_identity(report)['classification'] == 'consistent_but_dispatch_unverified'
    assert classify_backend_identity({'config':{'device':'npu'}}, 'qairt_npu')['classification'] == 'unknown'


@pytest.mark.parametrize('field', ['model_sha256','config_sha256','runtime_sha256','geniex_version','qairt_version'])
def test_conflicting_fingerprints_and_versions_rejected(field):
    from eval.report_validation import classify_backend_identity
    report = {'inference_backend':{'backend_id':'qairt_npu'}, field:'first', 'results':[{field:'other'}]}
    assert classify_backend_identity(report)['classification'] == 'contradiction'


@pytest.mark.parametrize('value', [[], [1], {}, {'bad':'value'}, 5, False])
def test_malformed_backend_scalar_fails_closed(value):
    from eval.report_validation import classify_backend_identity
    report = {'inference_backend':{'backend_id':value}}
    assert classify_backend_identity(report)['classification'] in ('unknown','contradiction')
    assert backend_identity_errors(report)


@pytest.mark.parametrize('mutation', ['root','identity','cases','case','energy','signature','power','raw','id','expected'])
def test_decision_malformed_nested_import_is_not_comparable(mutation):
    from eval.decision_table import build
    from tests.test_decision_table import POLICY, QUALITY
    reports, baseline = fixture()
    report = reports['cpu']
    if mutation == 'root': reports['cpu'] = [1]
    if mutation == 'identity': report['inference_backend'] = [1]
    if mutation == 'cases': report['results'] = {'bad':1}
    if mutation == 'case': report['results'][0] = [1]
    if mutation == 'energy': report['energy_measurement'] = [1]
    if mutation == 'signature': report['energy_measurement']['signature'] = [1]
    if mutation == 'power': report['energy_measurement']['signature']['power_condition'] = [1]
    if mutation == 'raw': report['results'][0]['energy']['raw_before'] = [1]
    if mutation == 'id': report['results'][0]['id'] = []
    if mutation == 'expected': report['results'][0]['expected'] = [1]
    result = build(reports, baseline, POLICY, QUALITY, 'test-head')
    assert result['comparison_status'] == 'NOT_COMPARABLE'
    assert result['winner'] is None
