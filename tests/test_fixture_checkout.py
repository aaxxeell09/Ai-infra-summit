"""Exercise Git's Windows checkout filters without changing frozen fixture bytes."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path('eval/fixtures/secretary_workspace')


def test_frozen_fixture_bytes_survive_autocrlf_checkout(tmp_path):
    source = tmp_path/'source'
    source.mkdir()
    def git(*args):
        return subprocess.check_output(['git', '-C', str(source), *args])
    git('init', '-q')
    git('config', 'core.autocrlf', 'true')
    git('config', 'core.safecrlf', 'false')
    (source/'.gitattributes').write_bytes((ROOT/'.gitattributes').read_bytes())
    originals = {}
    for file in sorted((ROOT/FIXTURES).rglob('*')):
        if file.is_file():
            relative = file.relative_to(ROOT)
            originals[relative] = file.read_bytes()
            target = source/relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(originals[relative])
    assert originals, 'Frozen fixture unexpectedly empty'
    (source/'control.txt').write_bytes(b'control\nline\n')
    git('add', '.')
    # Both the clean filter (index) and smudge filter (checkout) must preserve bytes.
    for relative, contents in originals.items():
        assert git('show', ':'+relative.as_posix()) == contents
        attribute = git('check-attr', 'text', '--', relative.as_posix()).decode().strip()
        assert attribute.endswith(': text: unset')
    checkout = tmp_path/'checkout'
    checkout.mkdir()
    git('checkout-index', '--all', '--force', '--prefix='+str(checkout)+'/')
    for relative, contents in originals.items():
        assert (checkout/relative).read_bytes() == contents
    assert (checkout/'control.txt').read_bytes() == b'control\r\nline\r\n'
