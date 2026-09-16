import hashlib
import pytest
from scripts.inspect_secretary_prefix import inspect_prefix, main
from eval.secretary_adapter import SecretaryAdapter


def test_exact_unicode_composition_without_claiming_tokens():
    files=['資料/é.txt','alpha.txt']
    report=inspect_prefix(files)
    raw=SecretaryAdapter(files).instructions().encode('utf-8')
    assert report['system_with_inventory']['sha256']==hashlib.sha256(raw).hexdigest()
    assert report['system_without_inventory']['utf8_bytes']+report['inventory']['utf8_bytes']==len(raw)
    assert report['inventory']['utf8_bytes']>report['inventory']['characters']
    assert report['system_with_inventory']['tokens'] is None
    assert report['user_tokens'] is None and report['heldout_inspected'] is False


def test_empty_inventory_retains_instructions():
    r=inspect_prefix([])
    assert r['inventory']['utf8_bytes']==0
    assert r['system_with_inventory']==r['system_without_inventory']


def test_output_never_overwrites(tmp_path):
    p=tmp_path/'prefix.json'
    assert main(['--output',str(p)])==0
    raw=p.read_bytes()
    with pytest.raises(SystemExit):main(['--output',str(p)])
    assert p.read_bytes()==raw
