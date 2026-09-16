"""All model artifacts here are synthetic byte strings, never loaded."""
import hashlib
import json
from pathlib import Path

import pytest
from scripts.inspect_model_artifact import inspect_artifact, write_manifest


def bundle(tmp_path):
    root = tmp_path/'modèle W4A16'; root.mkdir()
    (root/'shards').mkdir()
    (root/'shards'/'é.bin').write_bytes(b'\x00\xff\r\n')
    (root/'tokenizer.json').write_text('{}')
    (root/'geniex.json').write_text(json.dumps({'name':'synthetic'}))
    (root/'genie_config.json').write_text(json.dumps({'dialog':{
        'context':{'size':4096}, 'sampler':{'temp':.8,'top-k':40},
        'tokenizer':{'path':'tokenizer.json'},
        'engine':{'backend':{'type':'QnnHtp','extensions':'htp.json'},
                  'model':{'binary':{'ctx-bins':['shards/é.bin']}}}}}), encoding='utf-8')
    (root/'htp.json').write_text(json.dumps({'devices':[{'dsp_arch':'v73'}]}))
    return root


def test_inventory_is_reproducible_and_reports_only_explicit_metadata(tmp_path):
    root = bundle(tmp_path)
    first = inspect_artifact(root)
    assert inspect_artifact(root) == first
    assert list(first['files']) == sorted(first['files'])
    assert first['files']['shards/é.bin'] == {'bytes':4, 'sha256':hashlib.sha256(b'\x00\xff\r\n').hexdigest()}
    assert first['quantization'] is None  # directory label must not become evidence
    assert {'source':'genie_config.json','field':'dialog.context','value':{'size':4096}} in first['observed_metadata']
    assert {'source':'htp.json','field':'devices','value':[{'dsp_arch':'v73'}]} in first['observed_metadata']
    assert inspect_artifact(root, first) == first


def test_expected_inventory_mismatch_rejected(tmp_path):
    root = bundle(tmp_path); expected = inspect_artifact(root)
    (root/'shards'/'é.bin').write_bytes(b'changed')
    with pytest.raises(ValueError, match='does not match'): inspect_artifact(root, expected)


@pytest.mark.parametrize('target', ['missing.bin', '../outside.bin', 'C:\\outside.bin', '/outside.bin'])
def test_missing_or_escaping_declared_shard_rejected(tmp_path, target):
    root = bundle(tmp_path); config = root/'genie_config.json'
    data = json.loads(config.read_text()); data['dialog']['engine']['model']['binary']['ctx-bins'] = [target]
    config.write_text(json.dumps(data))
    with pytest.raises(ValueError): inspect_artifact(root)


def test_symlinks_refused_even_inside_bundle(tmp_path):
    root = bundle(tmp_path)
    try: (root/'alias.bin').symlink_to(root/'shards'/'é.bin')
    except OSError: pytest.skip('Symlink creation unavailable')
    with pytest.raises(ValueError, match='Symlinks'): inspect_artifact(root)


def test_output_cannot_mutate_source_or_overwrite(tmp_path):
    root = bundle(tmp_path); result = inspect_artifact(root)
    with pytest.raises(ValueError, match='outside'): write_manifest(root, root/'new/manifest.json', result)
    assert not (root/'new').exists()
    target = tmp_path/'manifest.json'
    write_manifest(root, target, result)
    raw = target.read_bytes()
    with pytest.raises(ValueError, match='overwrite'): write_manifest(root, target, result)
    assert target.read_bytes() == raw


def test_single_file_unknown_quantization(tmp_path):
    path = tmp_path/'q4_0.gguf'; path.write_bytes(b'synthetic-not-a-model')
    result = inspect_artifact(path)
    assert result['artifact_kind'] == 'file'
    assert result['quantization'] is None
    assert result['observed_metadata'] == []
    with pytest.raises(ValueError, match='outside'): write_manifest(path, path, result)


def test_utf8_bom_tokenizer_fields_are_retained(tmp_path):
    root = bundle(tmp_path)
    (root/'tokenizer_config.json').write_text(json.dumps({'model_max_length':2048,'chat_template':'{{ messages }}'}), encoding='utf-8-sig')
    result = inspect_artifact(root)
    assert {'source':'tokenizer_config.json','field':'model_max_length','value':2048} in result['observed_metadata']


def test_cli_creates_manifest_and_refuses_second_write(tmp_path):
    import subprocess
    import sys
    root = bundle(tmp_path)
    target = tmp_path/'artifact manifest.json'
    script = Path(__file__).resolve().parents[1]/'scripts/inspect_model_artifact.py'
    command = [sys.executable, str(script), str(root), '--output', str(target)]
    first = subprocess.run(command, capture_output=True, text=True)
    assert first.returncode == 0, first.stderr
    raw = target.read_bytes()
    second = subprocess.run(command, capture_output=True, text=True)
    assert second.returncode != 0 and 'overwrite' in second.stderr
    assert target.read_bytes() == raw
