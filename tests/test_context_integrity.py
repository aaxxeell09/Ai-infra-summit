"""Exact UTF-8 recovery and content-address integrity, without model inference."""
import hashlib

import pytest

from turbo.context import ContextStore


@pytest.mark.parametrize('text', ['a\r\nb\r\n', 'a\rb\n', '\ufeffété 🦊\r\n\x00tail', ''])
def test_exact_utf8_bytes_and_recovery(tmp_path, text):
    store = ContextStore(tmp_path)
    raw = text.encode('utf-8')
    key = store.put(text)
    assert key == hashlib.sha256(raw).hexdigest()
    assert (tmp_path / (key + '.txt')).read_bytes() == raw
    assert store.get(key) == text
    assert store.put(text) == key


def test_corruption_rejected_on_read_and_duplicate_write(tmp_path):
    store = ContextStore(tmp_path)
    key = store.put('original\r\n')
    path = tmp_path / (key + '.txt')
    path.write_bytes(b'original\n')
    with pytest.raises(ValueError, match='integrity mismatch'):
        store.get(key)
    with pytest.raises(ValueError, match='integrity mismatch'):
        store.put('original\r\n')
    assert path.read_bytes() == b'original\n'
