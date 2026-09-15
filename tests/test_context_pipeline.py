import json

import pytest

from turbo.context import ContextStore
from turbo.context_pipeline import (
    RECOVERY_TOOL_SCHEMA,
    Policy,
    break_even,
    caveman_prose_instruction,
    execute_recovery,
    optimize_messages,
    project_search,
    stable_prefix_fingerprint,
)


def recover(store, envelope):
    call = {"name": RECOVERY_TOOL_SCHEMA["function"]["name"],
            "arguments": json.dumps({"raw_ref": envelope["raw_ref"]})}
    return execute_recovery(store, call)


def make_messages():
    return [
        {"role": "system", "content": "You are terse."},
        {"role": "user", "content": "List failed units"},
        {"role": "assistant", "tool_calls": [
            {"id": "call_1", "type": "function",
             "function": {"name": "search_units", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "call_1", "name": "search_units",
         "content": json.dumps([
             {"path": "a/b.py", "line": 3, "negated": True,
              "snippet": "x" * 80, "raw_blob": "z" * 100},
             {"path": "c/d.py", "line": 9, "not_found": False,
              "snippet": "y" * 80, "raw_blob": "w" * 100}])},
    ]


def test_protected_roles_and_tool_ids_untouched(tmp_path):
    msgs = make_messages()
    result = optimize_messages(msgs, ContextStore(tmp_path / "ctx"),
                               Policy(tools=frozenset(["search_units"]),
                                      fields={"search_units": ["snippet"]}))
    for original, new in zip(msgs[:3], result["messages"][:3]):
        assert original is new  # same object reference, byte-for-byte
    tool_msg = result["messages"][3]
    assert tool_msg["tool_call_id"] == "call_1"
    assert tool_msg["name"] == "search_units"
    assert "raw_ref" in tool_msg["content"]


def test_unselected_tool_result_kept_verbatim(tmp_path):
    msgs = make_messages()
    result = optimize_messages(msgs, ContextStore(tmp_path / "ctx"), Policy())
    assert result["messages"][3] is msgs[3]
    assert result["records"] == []


def test_exact_raw_recovery(tmp_path):
    store = ContextStore(tmp_path / "ctx")
    msgs = make_messages()
    original_content = msgs[3]["content"]
    result = optimize_messages(msgs, store,
                               Policy(tools=frozenset(["search_units"]),
                                      fields={"search_units": ["snippet"]}))
    envelope = json.loads(result["messages"][3]["content"])
    assert envelope["lossy"] is True
    assert envelope["mode"] == "field_projection"
    record = result["records"][0]
    assert record["saved_chars"] > 0 and record["elapsed_s"] >= 0
    assert recover(store, envelope) == {"ok": True, "text": original_content}


def test_projection_keeps_paths_numbers_negation():
    out, removed, ok = project_search(
        json.dumps([{"path": "p", "line": 2, "negated": True, "extra": "junk"}]),
        fields=[])
    row = json.loads(out)[0]
    assert ok and removed == 1 and "extra" not in row
    assert row == {"path": "p", "line": 2, "negated": True}


def test_small_data_skips_when_envelope_not_smaller(tmp_path):
    store = ContextStore(tmp_path / "ctx")
    msgs = [{"role": "assistant", "tool_calls": [
        {"id": "c", "type": "function", "function": {"name": "t", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "c", "name": "t", "content": "ok"}]
    result = optimize_messages(msgs, store, Policy(tools=frozenset(["t"])))
    assert result["messages"][1] is msgs[1]
    assert result["records"][0]["applied"] is False


def test_negative_budget_disables_hook(tmp_path):
    store = ContextStore(tmp_path / "ctx")
    msgs = make_messages()
    calls = []
    policy = Policy(tools=frozenset(["search_units"]),
                    compressor=lambda text, name: calls.append(name) or "tiny",
                    cost_budget_chars=-1)
    result = optimize_messages(msgs, store, policy)
    assert calls == []  # negative budget disables the hook entirely
    assert result["records"][0]["applied"] is False
    assert result["messages"][3] is msgs[3]


def test_preview_requires_explicit_opt_in(tmp_path):
    store = ContextStore(tmp_path / "ctx")
    msgs = make_messages()
    msgs[3]["content"] = "z" * 400
    result = optimize_messages(msgs, store, Policy(tools=frozenset(["search_units"])))
    assert result["messages"][3] is msgs[3]  # no preview by default
    result = optimize_messages(msgs, store,
                               Policy(tools=frozenset(["search_units"]),
                                      preview_opt_in=True, preview_chars=50))
    envelope = json.loads(result["messages"][3]["content"])
    assert len(envelope["text"]) == 50 and envelope["lossy"] is True


def test_rtk_label_preserves_exit_and_failure_text(tmp_path):
    store = ContextStore(tmp_path / "ctx")
    msgs = make_messages()
    failure = "connection refused: " + "x" * 2000
    msgs[3]["content"] = failure
    # Labeling alone grows the payload; pair it with a reduction hook.
    policy = Policy(call_map={"call_1": {"exit_code": 2}}, rtk_label=True,
                    compressor=lambda text, name: "ERR: connection refused")
    result = optimize_messages(msgs, store, policy)
    assert result["messages"][3]["content"] == failure
    assert result["records"][0]["applied"] is False


def test_break_even_rejects_unmeasured_and_negative():
    with pytest.raises(ValueError):
        break_even(None, 0.10, 0.0, 0.0)  # no tokenizer measurement
    with pytest.raises(ValueError):
        break_even(-5, 0.10, 0.0, 0.0)
    assert break_even(1_000_000, 0.10, 0.01, 0.005) == pytest.approx(0.085)


def test_prefix_fingerprint_stable_under_optimization(tmp_path):
    msgs = make_messages()
    store = ContextStore(tmp_path / "ctx")
    before = stable_prefix_fingerprint(msgs)
    result = optimize_messages(msgs, store, Policy(tools=frozenset(["search_units"])))
    assert result["prefix_fingerprint"] == before
    msgs[3]["content"] = "totally different"
    assert stable_prefix_fingerprint(msgs) == before


def test_caveman_instruction_is_optin_text_only():
    text = caveman_prose_instruction()
    assert "JSON" in text and "user prompt" in text

def test_bad_compressor_and_recovery_arguments(tmp_path):
    store = ContextStore(tmp_path / "ctx")
    msgs = make_messages()
    result = optimize_messages(msgs, store, Policy(tools=frozenset(["search_units"]), compressor=lambda *_: None))
    assert result["messages"][3]["content"] == msgs[3]["content"]
    assert not execute_recovery(store, {"name": "context_recover", "arguments": []})["ok"]
