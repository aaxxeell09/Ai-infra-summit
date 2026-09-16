"""Backend selection and ABI plumbing without a device or downloaded model."""
import json
from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_native_layout import _make_runtime
from turbo.native import NativeModel, NativeRuntime, backend_options
from turbo.tuning import _sha256
from eval.run_secretary_eval import main


def test_explicit_identities_and_legacy_defaults(tmp_path):
    (tmp_path / 'geniex.json').write_text('{}')
    assert backend_options() == (None, 'cpu')
    assert backend_options('llama_cpp_cpu') == ('llama_cpp', 'cpu')
    assert backend_options('llama_cpp_htp') == ('llama_cpp', 'npu')
    assert backend_options('llama_cpp_htp', device='HTP0') == ('llama_cpp', 'HTP0')
    assert backend_options('qairt_npu', model_path=tmp_path) == ('qairt', 'npu')


@pytest.mark.parametrize('options', [
    {'backend':'qairt_npu'},
    {'backend':'unknown'},
    {'backend':'qairt_npu', 'device':'cpu'},
    {'backend':'llama_cpp_htp', 'plugin':'qairt'},
    {'backend':'llama_cpp_cpu', 'model_path':'bundle'},
])
def test_invalid_selection_fails_before_sdk(options):
    with pytest.raises(ValueError):
        backend_options(**options)


def test_qairt_reuses_native_abi_and_additive_metadata(tmp_path):
    (tmp_path / 'geniex.json').write_text('{}')
    NativeRuntime._shared.clear()
    runtime, lib = _make_runtime()
    with NativeModel(runtime, tmp_path, backend='qairt_npu') as model:
        cin = lib.captured_create_input
        assert cin.plugin_id == b'qairt'
        assert cin.device_id == b'HTP0'
        result = model.chat([{'role':'user','content':'Hello'}], max_tokens=16)
        assert result['backend'] == 'geniex'
        assert result['backend_id'] == 'qairt_npu'
        assert result['runtime'] == 'qairt'
        assert result['requested_device'] == 'npu'
        assert result['resolved_device'] == 'HTP0'
        assert result['qairt_version'] is None
        assert result['dispatch_verified'] is False
    runtime.close()


def test_bundle_fingerprint_changes_with_shard(tmp_path):
    (tmp_path / 'geniex.json').write_text('{}')
    shard = tmp_path / 'model.bin'
    shard.write_bytes(b'a')
    original = _sha256(tmp_path)
    shard.write_bytes(b'b')
    assert _sha256(tmp_path) != original


def test_runner_accepts_backend_key_but_requires_configured_qairt(tmp_path, capsys):
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'backend':'qairt_npu','sdk_dir':'missing','model_path':''}))
    with pytest.raises(SystemExit) as exc:
        main(['--candidate-name','qairt','--config',str(config)])
    assert exc.value.code == 2
    assert 'QAIRT model not configured' in capsys.readouterr().err


def test_explicit_npu_rejects_cpu_resolution(tmp_path):
    (tmp_path / 'geniex.json').write_text('{}')
    NativeRuntime._shared.clear()
    runtime, lib = _make_runtime()
    lib._resolve = ('CPU', 0, None)
    with pytest.raises(ValueError, match='refusing fallback'):
        NativeModel(runtime, tmp_path, backend='qairt_npu')
    assert not any(call[0] == 'llm_create' for call in lib.calls)
    runtime.close()


def test_cpu_and_htp_identities_reach_existing_sdk():
    for backend, resolved, ngl in [('llama_cpp_cpu','CPU',0), ('llama_cpp_htp','HTP0',99)]:
        NativeRuntime._shared.clear()
        runtime, lib = _make_runtime()
        lib._resolve = (resolved, ngl, None)
        with NativeModel(runtime, '/fake/model.gguf', backend=backend) as model:
            assert lib.captured_create_input.plugin_id == b'llama_cpp'
            assert lib.captured_create_input.device_id == resolved.encode()
            assert model.provenance()['backend_id'] == backend
        runtime.close()


def test_candidate_report_redacts_private_artifact_path(tmp_path, monkeypatch):
    import turbo.native as native
    model_path = tmp_path / 'private-location' / 'model.gguf'
    model_path.parent.mkdir()
    model_path.write_bytes(b'fake test artifact')
    config_path = tmp_path / 'config.json'
    config_path.write_text(json.dumps({'model_path':str(model_path), 'sdk_dir':str(tmp_path),
                                      'backend':'llama_cpp_cpu'}))
    class Runtime:
        def __init__(self, *args): pass
        def close(self): pass
    class Model:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def provenance(self): return {'backend_id':'llama_cpp_cpu','model_path_or_id':str(model_path)}
        def chat(self, *args, **kwargs):
            return {'text':'{"name":"clarify","arguments":{"question":"Which file?"}}'}
    monkeypatch.setattr(native, 'NativeRuntime', Runtime)
    monkeypatch.setattr(native, 'NativeModel', Model)
    output = tmp_path / 'reports'
    main(['--candidate-name','redaction-test','--config',str(config_path),'--output-dir',str(output)])
    report = (output / 'candidate_redaction-test.json').read_text()
    assert str(model_path) not in report
    assert json.loads(report)['inference_backend']['model_path_or_id'] == 'model.gguf'
