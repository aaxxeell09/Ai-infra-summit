import json
import pytest

from turbo.tuning import (
    Variant, SearchSpace, TuningError,
    plan_cells, build_command, rank_results, pareto_frontier,
    _energy_comparable, export_recommended,
)


def _v(**kw):
    base = dict(id="m1", path="/tmp/m.gguf", architecture="x1e",
                quantization="q4_k", plugin="llama_cpp", kind="llm")
    base.update(kw)
    return Variant.from_dict(base)


def test_plan_rejects_qairt_cpu_gpu_without_coercion():
    v = _v(plugin="qairt", compiled_contexts=["4096"])
    cells = plan_cells([v], SearchSpace(devices=("cpu", "gpu", "npu")))
    assert all(c.unsupported_reason for c in cells if c.device in ("cpu", "gpu"))
    npu = [c for c in cells if c.device == "npu"]
    assert npu and npu[0].unsupported_reason is None


def test_plan_rejects_unsupported_compiled_context():
    v = _v(plugin="qairt", compiled_contexts=["1024"])
    cells = plan_cells([v], SearchSpace(devices=("npu",),
                                        contexts=(640,)))
    assert cells[0].unsupported_reason  # -c 640 not registered
    ok = _v(plugin="qairt", compiled_contexts=["4096"])
    good = plan_cells([ok], SearchSpace(devices=("npu",), contexts=(4096,)))
    assert good[0].unsupported_reason is None


def test_vlm_requires_image_and_uses_native_flags():
    bad = _v(kind="vlm", requiredimage=False, mmproj_path="/tmp/mm")
    assert plan_cells([bad], SearchSpace())[0].unsupported_reason
    ok = _v(kind="vlm", requiredimage=True, mmproj_path="/tmp/mm")
    cmd = build_command("bench", ok, plan_cells([ok], SearchSpace())[0],
                        SearchSpace(), image_path="/tmp/x.jpg")
    assert "--vlm" in cmd and "--mmproj-path" in cmd and "--image" in cmd
    with pytest.raises(TuningError):
        build_command("bench", ok, plan_cells([ok], SearchSpace())[0], SearchSpace())


def test_batch_ubatch_refused_not_fabricated():
    v = _v()
    cell = plan_cells([v], SearchSpace())[0]
    with pytest.raises(TuningError, match="planned"):
        build_command("bench", v, cell, SearchSpace(batch=128))
    with pytest.raises(TuningError, match="planned"):
        build_command("bench", v, cell, SearchSpace(ubatch=128))


def test_command_has_exactly_the_supported_flags():
    v = _v()
    space = SearchSpace(threads=(4,), contexts=(2048,))
    cmd = build_command("bench", v, plan_cells([v], space)[0], space)
    for flag in ("-t", "-c", "-p", "-n"):
        assert flag in cmd
    assert "-b" not in cmd and "--batch-size" not in cmd


def test_ranking_skips_missing_metrics_instead_of_zero():
    results = [
        {"status": "completed", "complete_length_runs": 1,
         "decode_tps": 10.0, "prefill_tps": 100.0, "repeats": 3},
        {"status": "completed", "complete_length_runs": 1,
         "decode_tps": None, "prefill_tps": None},
        {"status": "failed"},
        {"status": "completed", "complete_length_runs": 0,
         "decode_tps": 99.0, "prefill_tps": 99.0},
    ]
    ranked = rank_results(results, objective="decode")
    assert len(ranked) == 1
    assert ranked[0]["decode_tps"] == 10.0
    assert ranked[0]["provisional"] is False


def test_ranking_balanced_across_variants():
    results = [
        {"variant_id": "a", "status": "completed", "complete_length_runs": 1,
         "decode_tps": 8.0, "prefill_tps": 400.0},
        {"variant_id": "b", "status": "completed", "complete_length_runs": 1,
         "decode_tps": 10.0, "prefill_tps": 20.0},
    ]
    ranked = rank_results(results, objective="balanced")
    # harmonic means: a ~15.7 (8 decode / 400 prefill),
    # b ~13.3 (10 decode / 20 prefill): the higher raw decode loses here
    assert ranked[0]["variant_id"] == "a"
    assert ranked[1]["variant_id"] == "b"


def test_export_recommended_writes_full_identity(tmp_path):
    record = {"objective": "decode", "recommended": {
        "variant_id": "m1", "plugin": "llama_cpp", "model_sha256": "abc",
        "device": "cpu", "threads": 6, "context": 4096,
        "gen_tokens": 128, "provisional": True}}
    cfg = export_recommended(record, str(tmp_path / "rec.json"))
    assert cfg["model"]["sha256"] == "abc"
    on_disk = json.loads((tmp_path / "rec.json").read_text())
    assert on_disk["tuning"]["threads"] == 6
    assert on_disk["scope"]["provisional"] is True


def test_fast_and_efficient_objectives():
    results = [
        {"status": "completed", "complete_length_runs": 1,
         "decode_tps": 10.0, "prefill_tps": 20.0, "tokens_per_joule": 0.4},
        {"status": "completed", "complete_length_runs": 1,
         "decode_tps": 8.0, "prefill_tps": 400.0, "tokens_per_joule": 0.9},
    ]
    fast = rank_results(results, objective="fast")
    assert fast[0]["decode_tps"] == 10.0
    efficient = rank_results(results, objective="efficient")
    assert efficient[0]["tokens_per_joule"] == 0.9
    # efficient falls back to decode when tokens/J missing
    no_energy = [{k: v for k, v in r.items() if k != "tokens_per_joule"}
                 for r in results]
    assert rank_results(no_energy, objective="efficient")[0]["decode_tps"] == 10.0


def test_variability_penalty_applies_only_when_present():
    results = [
        {"status": "completed", "complete_length_runs": 1, "decode_tps": 10.0,
         "variability_ratio": 0.5},
        {"status": "completed", "complete_length_runs": 1, "decode_tps": 9.0},
    ]
    assert rank_results(results, objective="decode")[0]["decode_tps"] == 10.0
    penalized = rank_results(results, objective="decode", variability_penalty=1.0)
    assert penalized[0]["decode_tps"] == 9.0  # 10 reduced to 5


def test_pareto_frontier_excludes_dominated_and_missing():
    results = [
        {"status": "completed", "decode_tps": 10.0, "prefill_tps": 100.0},
        {"status": "completed", "decode_tps": 5.0, "prefill_tps": 50.0},   # dominated
        {"status": "completed", "decode_tps": 1.0, "prefill_tps": 500.0},  # tradeoff
        {"status": "completed", "decode_tps": None, "prefill_tps": 999.0}, # ineligible
        {"status": "failed", "decode_tps": 99.0, "prefill_tps": 99.0},
    ]
    frontier = pareto_frontier(results)
    ids = [(r["decode_tps"], r["prefill_tps"]) for r in frontier]
    assert (5.0, 50.0) not in ids and len(ids) == 2
    assert frontier[0]["decode_tps"] == 10.0


def test_energy_comparability_requires_same_workload_and_quant():
    base = {"status": "completed", "gen_tokens": 128, "prompt_tokens": 512,
            "quantization": "q4_k", "architecture": "x1e",
            "tokens_per_joule": 0.5}
    same = [dict(base), dict(base)]
    assert _energy_comparable(same) is None
    diff_gen = [dict(base), {**base, "gen_tokens": 64}]
    assert "gen_tokens" in _energy_comparable(diff_gen)
    diff_quant = [dict(base), {**base, "quantization": "q8"}]
    assert "quantization" in _energy_comparable(diff_quant)
    assert _energy_comparable([base]) is None
