"""Protocol/failure-artifact tests only; these never load a model."""
import json
import subprocess
from unittest.mock import patch

import pytest

from scripts.verify_tuner_loop import capture_feedback, checked_rpc_reply


@pytest.mark.parametrize('reply', [
    [], {'jsonrpc': '2.0', 'id': True, 'result': {}},
    {'jsonrpc': '2.0', 'id': 2, 'result': {}},
    {'jsonrpc': '2.0', 'id': 1, 'result': [], 'error': {}},
    {'jsonrpc': '2.0', 'id': 1, 'result': []},
    {'jsonrpc': '2.0', 'id': 1},
])
def test_wrong_or_ambiguous_reply_rejected(reply):
    with pytest.raises(ValueError):
        checked_rpc_reply(json.dumps(reply), 1)


def test_correctly_addressed_error_preserved():
    reply = {'jsonrpc': '2.0', 'id': 1, 'error': {'message': 'actual failure'}}
    assert checked_rpc_reply(json.dumps(reply), 1) == reply


def test_timeout_preserves_partial_bytes_and_reraises(tmp_path):
    failure = subprocess.TimeoutExpired('feedback', 210, output=b'{"partial":', stderr=b'\xffnative error')
    with patch('scripts.verify_tuner_loop.subprocess.run', side_effect=failure):
        with pytest.raises(subprocess.TimeoutExpired) as caught:
            capture_feedback(['feedback'], wire_path=tmp_path/'wire', stderr_path=tmp_path/'stderr')
    assert caught.value is failure
    assert (tmp_path/'wire').read_bytes() == b'{"partial":'
    assert (tmp_path/'stderr').read_bytes() == b'\xffnative error'


def test_completed_failure_preserves_all_output(tmp_path):
    child = subprocess.CompletedProcess(['feedback'], 1, stdout='failure reply\n', stderr='native failure\n')
    with patch('scripts.verify_tuner_loop.subprocess.run', return_value=child):
        actual = capture_feedback(['feedback'], wire_path=tmp_path/'wire', stderr_path=tmp_path/'stderr')
    assert actual is child
    assert (tmp_path/'wire').read_text() == 'failure reply\n'
    assert (tmp_path/'stderr').read_text() == 'native failure\n'


def test_launch_failure_recorded_without_invented_response(tmp_path):
    with patch('scripts.verify_tuner_loop.subprocess.run', side_effect=OSError('missing executable')):
        with pytest.raises(OSError):
            capture_feedback(['feedback'], wire_path=tmp_path/'wire', stderr_path=tmp_path/'stderr')
    assert (tmp_path/'wire').read_bytes() == b''
    assert 'missing executable' in (tmp_path/'stderr').read_text()
