"""Encoding and shape validation never rewrite input artifacts."""
import json
import pytest
from turbo.json_io import read_json


@pytest.mark.parametrize('bom', [b'', b'\xef\xbb\xbf'])
def test_utf8_with_optional_bom_and_crlf(tmp_path, bom):
    path = tmp_path/'private settings.json'
    raw = bom + '{\r\n"model_path": "C:\\\\Modèles\\\\modèle.gguf"\r\n}'.encode('utf-8')
    path.write_bytes(raw)
    assert read_json(path, require_object=True)['model_path'] == 'C:\\Modèles\\modèle.gguf'
    assert path.read_bytes() == raw


@pytest.mark.parametrize('raw', [b'{"x":NaN}', b'{"x":Infinity}', b'{"x":-Infinity}', b'{"x":1e999}',
                                b'{"x":1,"x":2}', b'{"x":{"k":1,"k":2}}', b'{"x":"\xff"}', b'{broken'])
def test_invalid_json_is_rejected_without_rewrite(tmp_path, raw):
    path = tmp_path/'input.json'; path.write_bytes(raw)
    with pytest.raises(ValueError): read_json(path)
    assert path.read_bytes() == raw


@pytest.mark.parametrize('value', [None, [], 'string', 4, True])
def test_private_config_requires_object(tmp_path, value):
    path = tmp_path/'input.json'; path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='root must be an object'):
        read_json(path, require_object=True)
    assert read_json(path) == value


def test_runner_keeps_sampler_evidence_additive():
    from eval.run_secretary_eval import execute
    from eval.secretary_adapter import SecretaryAdapter
    from eval.scoring import load_dataset
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    case = load_dataset([root/'eval/datasets/secretary_dev.json'])[0]
    sampling = {'sdk_top_k': 0, 'temperature': 0, 'zero_temperature_default_source': 'bundle_then_plugin'}
    rows = execute([case], SecretaryAdapter.from_files([]), lambda messages: {
        'text': '{"name":"list_files","arguments":{}}', 'sampling': sampling})
    assert rows[0]['sampling'] == sampling


@pytest.mark.parametrize('raw', [b'{"success":false,"success":true}',b'{"nested":[1e999]}',b'{"nested":[-1e999]}'])
def test_captured_snapshot_uses_identical_strict_decoder(raw):
    from turbo.json_io import parse_json
    with pytest.raises(ValueError): parse_json(raw)


def test_captured_snapshot_preserves_bom_unicode_and_object_requirement():
    from turbo.json_io import parse_json
    raw=b'\xef\xbb\xbf'+json.dumps({'name':'été'},ensure_ascii=False).encode()
    assert parse_json(raw,require_object=True)=={'name':'été'}
    with pytest.raises(ValueError,match='root must be an object'):
        parse_json(b'[]',require_object=True)
