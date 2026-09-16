import shutil
import pytest
from turbo.runtime_identity import binding_matches, runtime_identity


def sdk(tmp_path):
    root = tmp_path/'sdk'; (root/'bin').mkdir(parents=True)
    exe = root/'bin/geniex-bench.exe'; exe.write_bytes(b'bench')
    (root/'lib/qairt/htp-files').mkdir(parents=True)
    (root/'lib/geniex.dll').write_bytes(b'bridge')
    nested = root/'lib/qairt/htp-files/libQnnHtpV73.so'; nested.write_bytes(b'HTP')
    return exe, root, nested


def test_runtime_identity_covers_nested_htp_and_survives_relocation(tmp_path):
    exe, root, nested = sdk(tmp_path)
    first = runtime_identity(exe, use_cache=True)
    assert 'sdk/lib/qairt/htp-files/libQnnHtpV73.so' in first['files']
    shutil.copytree(root, tmp_path/'renamed-sdk')
    assert first == runtime_identity(tmp_path/'renamed-sdk/bin/geniex-bench.exe')
    nested.write_bytes(b'changed')
    assert not binding_matches(first, runtime_identity(exe, use_cache=True))


def test_missing_executable_or_bridge_never_becomes_partial_identity(tmp_path):
    exe, root, nested = sdk(tmp_path)
    exe.unlink()
    with pytest.raises(ValueError): runtime_identity(exe)
    exe.write_bytes(b'bench'); (root/'lib/geniex.dll').unlink()
    with pytest.raises(ValueError): runtime_identity(exe)


def test_added_removed_library_and_cache_copy(tmp_path):
    exe, root, nested = sdk(tmp_path)
    first = runtime_identity(exe, use_cache=True)
    polluted = runtime_identity(exe, use_cache=True); polluted['files'].clear()
    assert runtime_identity(exe, use_cache=True) == first
    extra = nested.with_name('extra.dll'); extra.write_bytes(b'new')
    assert runtime_identity(exe, use_cache=True) != first
    extra.unlink(); assert runtime_identity(exe, use_cache=True) == first
    nested.unlink(); assert runtime_identity(exe, use_cache=True) != first


def test_override_is_not_misrepresented_by_packaged_sdk_hash(tmp_path, monkeypatch):
    exe, _, _ = sdk(tmp_path)
    monkeypatch.setenv('GENIEX_QAIRT_LIB','external.dll')
    with pytest.raises(ValueError, match='override'): runtime_identity(exe)
