"""Router helper tests: no hardware, no HTTP, all inference stubbed."""
from turbo.router import ModelProfile, Requirements, plan_route, run_with_fallback


def small(**kw):
    base = dict(name="small", model="1b", runtime="geniex@1", weights_hash="aaa",
                prefill_tps=1000.0, decode_tps=50.0, load_s=1.0, context=4096,
                quality_rate=0.9, quality_evidence="heldout-100", calibrated=True)
    base.update(kw)
    return ModelProfile(**base)


def large(**kw):
    return small(name="large", model="7b", weights_hash="bbb", larger=True,
                 prefill_tps=400.0, decode_tps=20.0, load_s=3.0, **kw)


REQ = Requirements(task_kind="secretary", context_tokens=512, output_tokens=128,
                   quality_minimum=0.8, objective="latency")


def test_fast_small_chosen_within_quality():
    plan = plan_route([small(), large()], REQ)
    assert plan["status"] == "ok" and plan["selected"].name == "small"
    assert plan["trace"][0]["model"] == "small"
    assert plan["trace"][1]["why"].endswith("held for fallback")


def test_larger_escalation_only_on_invalid_action():
    calls = []

    def invoke(profile, req):
        calls.append(profile.name)
        return {"bad": "not an action"} if profile.name == "small" else {"action": "ok"}

    ok, _ = None, None
    plan = plan_route([small(), large()], REQ)
    run = run_with_fallback(plan, invoke,
                            lambda out, req: (out.get("action") == "ok", "checked"))
    assert calls == ["small", "large"], "escalates only after small fails validation"
    assert run["status"] == "ok" and run["attempts"] == 2
    assert run["trace"][0]["validation"] == "invalid"
    assert run["trace"][1]["validation"] == "valid"


def test_quality_unavailable_excludes_and_never_infers():
    no_quality = small(quality_rate=None, quality_evidence="")
    plan = plan_route([no_quality, large(quality_rate=None, quality_evidence="")], REQ)
    assert plan["status"] == "no_route"
    reasons = {r["reason"] for r in plan["rejected"]}
    assert "task-quality rate/evidence unavailable" in reasons
    assert all(r["name"] for r in plan["rejected"])
    bigger_ok = small(quality_rate=None)  # 7b without measurement must not pass either
    plan2 = plan_route([large(quality_rate=None, quality_evidence="")], REQ)
    assert plan2["status"] == "no_route"


def test_uncalibrated_never_auto_accepted_without_optin():
    boot = small(calibrated=False)
    plan = plan_route([boot], REQ)
    assert plan["status"] == "no_route"
    assert plan["rejected"][0]["reason"] == "uncalibrated; opt-in required"
    optin = Requirements(**{**REQ.__dict__, "allow_uncalibrated": True})
    plan2 = plan_route([boot], optin)
    assert plan2["status"] == "ok"
    assert plan2["uncalibrated_disclosed"] is True


def test_manual_bootstrap_route_labeled():
    optin = Requirements(**{**REQ.__dict__, "allow_uncalibrated": True,
                            "manual_model": "small"})
    plan = plan_route([small(calibrated=False)], optin)
    assert plan["trace"][0]["status"] == "manual-uncalibrated"
    run = run_with_fallback(plan, lambda p, r: {"action": "ok"},
                            lambda out, r: (True, "ok"))
    assert run["trace"][0]["status"] == "manual-uncalibrated"


def test_overhead_total_and_failed_trace():
    plan = plan_route([small(), large()], REQ)
    runs = {"n": 0}

    def invoke(profile, req):
        runs["n"] += 1
        return {"action": "bad"}

    run = run_with_fallback(plan, invoke, lambda out, r: (False, "invalid"),
                            attempts=2)
    assert run["status"] == "failed" and run["result"] is None
    assert run["attempts"] == 2 and runs["n"] == 2
    assert run["total_s"] >= sum(t["elapsed_s"] for t in run["trace"]) >= 0
    assert all(t["validation"] == "invalid" for t in run["trace"])
    assert run["predicted_order"] == ["small", "large"]
    assert "predictions" in run["disclosure"]


def test_no_execution_side_effects_before_validate():
    executed = []
    plan = plan_route([small()], REQ)
    assert plan["status"] == "ok"
    assert executed == [], "planning alone performs no calls"
    run = run_with_fallback(plan, lambda p, r: executed.append(p.name) or {"action": "ok"},
                            lambda out, r: (True, "ok"))
    assert executed == ["small"] and run["attempts"] == 1


def test_validation_sees_no_gold_answers():
    seen = {}
    plan = plan_route([small()], REQ)
    run_with_fallback(plan, lambda p, r: {"action": "ok"},
                      lambda out, r: (seen.update(out=out, req=r) or (True, "ok")))
    assert "expected" not in seen["req"].__dict__ and seen["out"] == {"action": "ok"}
