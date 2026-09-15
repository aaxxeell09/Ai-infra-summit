"""Real schema-4 fixture plus a fake external benchmark; no hardware/network."""
import copy
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from turbo import tuning as t

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "benchmarks/results/screen-01/cpu-t0.json"


@pytest.fixture
def native():
    return json.loads(SAMPLE.read_text())


@pytest.fixture
def setup(tmp_path, monkeypatch, native):
    real_run = subprocess.run

    def execute(cmd, **kwargs):
        # Run the fake CLI as a separate process on any Python platform.
        return real_run([sys.executable, *cmd], **kwargs)

    monkeypatch.setattr(t.subprocess, "run", execute)
    model = tmp_path / "weights.gguf"
    model.write_bytes(b"test weights only")
    exe = tmp_path / "fake-bench.py"
    exe.write_text(f"""
import json, sys, time
from pathlib import Path
a = sys.argv[1:]
def arg(flag): return a[a.index(flag) + 1]
# Regression guard: without --output-json there is deliberately no report.
if "--output-json" not in a:
    print("no output requested")
    sys.exit(0)
data = {native!r}
n, p, r = int(arg("-n")), int(arg("-p")), int(arg("-r"))
data.update(plugin=arg("--plugin"), device=arg("--device"),
            model_path=arg("-m"), cell_id=arg("--cell-id"))
data["params"].update(warmup=int(arg("--warmup")), repetitions=r, n_prompt=p,
    n_gen=n, temperature=float(arg("--temperature")), seed=int(arg("--seed")),
    n_ctx=0 if arg("--plugin") == "qairt" else int(arg("-c")), n_threads=int(arg("-t")))
data["runs"] = [dict(data["runs"][i % 3], gen_tokens=n, prompt_tokens=p) for i in range(r)]
mode = Path(arg("-m")).name
if mode.startswith("partial"):
    data["runs"][-1].update(gen_tokens=n-1, stop_reason="eos")
if mode.startswith("wrong"):
    data["params"]["seed"] += 1
if mode.startswith("nan"):
    data["agg"]["decode_tps"]["median"] = float("nan")
if mode.startswith("sleep"):
    time.sleep(1)
print("fake benchmark stdout", flush=True)
print("fake benchmark stderr", file=sys.stderr, flush=True)
if mode.startswith("absent"):
    sys.exit(0)
target = Path(arg("--output-json"))
target.write_text("{{" if mode.startswith("broken") else json.dumps(data), encoding="utf-8")
sys.exit(7 if mode.startswith("nonzero") else 0)
""")
    variant = t.Variant("qwen06-q4", str(model), "qwen3", "Q4_0", "llama_cpp", "llm")
    return exe, variant, tmp_path


def _row(native, **overrides):
    row = dict(t._parse_result_json(native, 128, 3), variant_id="qwen06-q4",
        model_sha256="a" * 64, artifact_sha256={"model": "a" * 64}, architecture="qwen3",
        quantization="Q4_0", kind="llm", plugin="llama_cpp", workload_id="b" * 64,
        power_state="ac", power_scope="declared", runtime_sha256="c" * 64,
        status="completed", gen_tokens=128, prompt_tokens=512, repeats=3, warmup=0)
    row.update(overrides)
    return row


def test_actual_native_schema_numeric_medians(native):
    row = _row(native)
    assert row["decode_tps"] == pytest.approx(95.950082)
    assert row["prefill_tps"] == pytest.approx(1578.303262)
    assert row["ttft_ms"] == pytest.approx(324.606)
    assert row["latency_s"] == pytest.approx(1.658426)
    assert row["full_length"] and row["run_count"] == 3
    assert row["variability_ratio"] > 0
    assert t.rank_results([row])[0]["score"] == pytest.approx(95.950082)
    assert t.rank_results([row], "balanced")[0]["score"] == pytest.approx(1 / 1.658426)


def test_plan_rejects_coercion_and_unselectable_compiled_context(setup):
    _, v, _ = setup
    q = replace(v, plugin="qairt", compiled_contexts=(4096,))
    cells = t.plan_cells([q], t.SearchSpace(devices=("cpu", "gpu", "npu", "hybrid"),
                                           contexts=(2048, 4096)))
    valid = [c for c in cells if c.unsupported_reason is None]
    assert [(c.device, c.context) for c in valid] == [("npu", 4096)]
    multi = replace(q, compiled_contexts=(2048, 4096))
    assert all(c.unsupported_reason for c in t.plan_cells([multi], t.SearchSpace(devices=("npu",))))


def test_bounded_validated_search_and_batch_capability(setup):
    _, v, _ = setup
    for space in (t.SearchSpace(devices=()), t.SearchSpace(threads=(-1,)),
                  t.SearchSpace(contexts=(0,)), t.SearchSpace(repeats=0),
                  t.SearchSpace(threads=tuple(range(257)))):
        with pytest.raises(t.TuningError):
            t.plan_cells([v], space)
    with pytest.raises(t.TuningError, match="duplicate"):
        t.plan_cells([v, v], t.SearchSpace())
    for axis in ("batch", "ubatch"):
        space = t.SearchSpace(**{axis: 128})
        cell = t.plan_cells([v], space)[0]
        assert "planned" in cell.unsupported_reason
        with pytest.raises(t.TuningError, match="unsupported"):
            t.build_command("bench", v, cell, space)


def test_llama_vlm_exact_flags_and_missing_artifacts(setup):
    exe, v, root = setup
    image, prompt, projector = [root / x for x in ("image.png", "prompt.txt", "projector.gguf")]
    for p in (image, prompt, projector):
        p.write_bytes(b"fixture")
    v = replace(v, kind="vlm", mmproj_path=str(projector))  # kind itself requires image
    space = t.SearchSpace()
    cell = t.plan_cells([v], space)[0]
    with pytest.raises(t.TuningError, match="image workload"):
        t.build_command(exe, v, cell, space)
    cmd = t.build_command(exe, v, cell, space, image, prompt, root / "result.json", "trial")
    for flag, val in (("--mmproj-path", str(projector)), ("--image", str(image)),
                      ("--prompt-file", str(prompt)), ("--output-json", str(root / "result.json"))):
        assert cmd[cmd.index(flag) + 1] == val
    assert "--vlm" in cmd and "--batch-size" not in cmd and "-b" not in cmd
    projector.unlink()
    with pytest.raises(t.TuningError, match="missing local artifact"):
        t.build_command(exe, v, cell, space, image, prompt)


def test_qairt_bundle_without_projector_wires_shared_options_and_tokenizer(setup):
    exe, v, root = setup
    bundle = root / "bundle"
    bundle.mkdir()
    (bundle / "context.bin").write_bytes(b"compiled context fixture")
    image, prompt, tokenizer = [root / x for x in ("image.png", "prompt.txt", "tokenizer.json")]
    for p in (image, prompt, tokenizer):
        p.write_bytes(b"fixture")
    q = replace(v, path=str(bundle), plugin="qairt", kind="vlm",
                compiled_contexts=(4096,), tokenizer_path=str(tokenizer))
    space = t.SearchSpace(devices=("npu",), warmup=2, repeats=3, temperature=0.2, seed=17)
    cmd = t.build_command(exe, q, t.plan_cells([q], space)[0], space, image, prompt)
    assert "--vlm" in cmd and "--mmproj-path" not in cmd
    for flag, val in (("--tokenizer-path", str(tokenizer)), ("--warmup", "2"),
                      ("-r", "3"), ("--temperature", "0.2"), ("--seed", "17")):
        assert cmd[cmd.index(flag) + 1] == val
    record = t.run_tuning(exe, [q], space, root / "qairt-run", image_path=image, prompt_file=prompt)
    assert record["results"][0]["status"] == "completed"
    assert record["results"][0]["reported_params"]["n_ctx"] == 0
    assert record["recommended"]["context"] == 4096


def test_fake_external_command_full_pipeline_incremental_record_and_export(setup):
    exe, v, root = setup
    out = root / "run"
    calls = []

    def progress(done, total):
        disk = json.loads((out / "record.json").read_text())
        assert len(disk["results"]) == done
        assert disk["results"][-1]["status"] == "completed"
        calls.append((done, total))

    record = t.run_tuning(exe, [v], t.SearchSpace(threads=(0, 6), repeats=3), out,
                          power_state="ac", progress=progress)
    assert calls == [(1, 2), (2, 2)]
    assert len(record["ranking"]) == 2 and record["recommended"]
    assert len({r["result_path"] for r in record["results"]}) == 2
    for row in record["results"]:
        assert row["command"][row["command"].index("--output-json") + 1] == row["result_path"]
        assert Path(row["result_path"]).is_file()
        assert "fake benchmark stdout" in Path(row["log_path"]).read_text()
        assert "fake benchmark stderr" in Path(row["log_path"]).read_text()
        assert row["tokens_per_joule"] is None and not row["energy_valid"]
    config = t.export_recommended(record, root / "recommended.json")
    assert config["model"]["id"] == v.id
    assert config["model_sha256"] == t._sha256(v.path)
    assert config["scope"]["workload"]["gen_tokens"] == 128
    assert config["provisional"] and config["requires_paired_confirmation"]
    with pytest.raises(FileExistsError):
        t.run_tuning(exe, [v], t.SearchSpace(), out)


@pytest.mark.parametrize("name,status", [
    ("partial.gguf", "partial"), ("broken.gguf", "failed"), ("nan.gguf", "failed"),
    ("absent.gguf", "failed"), ("wrong.gguf", "failed"), ("nonzero.gguf", "failed"),
    ("sleep.gguf", "timeout"),
])
def test_bad_trials_persist_and_are_never_ranked(setup, name, status):
    exe, v, root = setup
    bad_path = root / name
    bad_path.write_bytes(b"bad variant")
    bad = replace(v, id="bad", path=str(bad_path))
    rec = t.run_tuning(exe, [bad, v], t.SearchSpace(repeats=3), root / "run",
                       timeout_s=0.1 if status == "timeout" else 5)
    assert [r["status"] for r in rec["results"]] == [status, "completed"]
    assert len(rec["ranking"]) == 1
    assert rec["recommended"] is None  # cannot recommend globally across two weights
    if status == "partial":
        assert rec["results"][0]["complete_length_runs"] == 2
        assert len(rec["results"][0]["runs"]) == 3
    assert json.loads((root / "run/record.json").read_text())["results"][0]["status"] == status


def test_missing_image_retained_as_failure_then_continues(setup):
    exe, v, root = setup
    vlm = replace(v, id="vlm", kind="vlm")
    rec = t.run_tuning(exe, [vlm, v], t.SearchSpace(), root / "run")
    assert [r["status"] for r in rec["results"]] == ["failed", "completed"]
    assert "image" in rec["results"][0]["error"]


def test_total_budget_prevents_later_launches(setup):
    exe, v, root = setup
    sleeper = root / "sleep.gguf"
    sleeper.write_bytes(b"fixture")
    rec = t.run_tuning(exe, [replace(v, path=str(sleeper))],
                       t.SearchSpace(threads=(0, 6, 8)), root / "run", timeout_s=10, budget_s=0.05)
    assert all(r["status"] == "timeout" for r in rec["results"])
    assert sum("command" in r for r in rec["results"]) <= 1
    assert not rec["ranking"]


def test_all_repeats_full_length_and_always_provisional(native):
    good = _row(native)
    bad = copy.deepcopy(native)
    bad["runs"][-1].update(gen_tokens=2, stop_reason="eos")
    partial = _row(bad)
    short = _row(native, run_count=2)
    ranked = t.rank_results([partial, short, good])
    assert len(ranked) == 1 and ranked[0]["provisional"]
    assert ranked[0]["requires_paired_confirmation"]
    assert len(t.pareto_frontier([partial, short, good])) == 1


@pytest.mark.parametrize("metric", [None, {}, {"median": 10}, float("nan"), float("inf"), 0, -1, True])
def test_missing_or_invalid_metric_is_ineligible(native, metric):
    row = _row(native, decode_tps=metric)
    assert t.rank_results([row]) == []
    assert t.pareto_frontier([row]) == []


@pytest.mark.parametrize("field,new", [
    ("model_sha256", "d" * 64), ("variant_id", "other"),
    ("architecture", "llama"), ("quantization", "Q8_0"),
    ("workload_id", "other-prompt"), ("power_state", "battery"),
    ("artifact_sha256", {"model": "a" * 64, "mmproj": "different"}),
])
def test_no_cross_identity_ranking_or_pareto_dominance(native, field, new):
    first = _row(native, decode_tps=10, prefill_tps=10)
    second = _row(native, decode_tps=1000, prefill_tps=1000, **{field: new})
    ranked = t.rank_results([first, second])
    assert [r["rank"] for r in ranked] == [1, 1]
    assert len({r["group_id"] for r in ranked}) == 2
    assert len(t.pareto_frontier([first, second])) == 2


def test_efficient_never_falls_back_or_mixes_energy_scopes(native):
    missing = _row(native, decode_tps=100000, tokens_per_joule=999999)
    valid = _row(native, energy_valid=True, energy_j=100, energy_duration_s=10,
                 energy_channel="SYS", energy_scope="full_process_trial")
    assert t.rank_results([missing], "efficient") == []
    ranked = t.rank_results([missing, valid], "efficient")
    assert len(ranked) == 1 and ranked[0]["score"] == pytest.approx(384 / 100)
    for changes in ({"warmup": 1}, {"power_state": "unavailable"}, {"energy_j": 0},
                    {"energy_scope": "decode_only"}, {"energy_valid": False},
                    {"energy_duration_s": None}):
        assert t.rank_results([{**valid, **changes}], "efficient") == []
    rail = {**valid, "energy_channel": "GPU", "energy_j": 1}
    assert [r["rank"] for r in t.rank_results([valid, rail], "efficient")] == [1, 1]


def test_efficient_runner_has_no_recommendation_until_meter_is_connected(setup):
    exe, v, root = setup
    rec = t.run_tuning(exe, [v], t.SearchSpace(), root / "run", objective="efficient")
    assert rec["results"][0]["status"] == "completed"
    assert rec["recommended"] is None and rec["ranking"] == []


def test_constraints_variability_and_balanced_latency(native):
    a = _row(native, decode_tps=10, latency_s=2, variability_ratio=0.8)
    b = _row(native, decode_tps=9, latency_s=1, variability_ratio=0.01)
    assert t.rank_results([a, b], "fast")[0]["decode_tps"] == 10
    assert t.rank_results([a, b], "balanced")[0]["decode_tps"] == 9
    assert t.rank_results([a, b], variability_penalty=1)[0]["decode_tps"] == 9
    assert len(t.rank_results([a, b], constraints={"rules": [["decode_tps", "min", 9.5]]})) == 1
    assert t.rank_results([a], constraints={"rules": [["peak_working_set_mb", "max", 100]]}) == []
    with pytest.raises(t.TuningError):
        t.rank_results([a], constraints={"rules": [["decode_tps", "bogus", 1]]})


def test_multi_variant_recommendation_requires_explicit_group(setup):
    exe, v, root = setup
    other = root / "other.gguf"
    other.write_bytes(b"other weights")
    record = t.run_tuning(exe, [v, replace(v, id="other", path=str(other), architecture="llama")],
                          t.SearchSpace(), root / "run")
    assert len(record["recommendations"]) == 2 and record["recommended"] is None
    with pytest.raises(t.TuningError, match="select a group"):
        t.export_recommended(record, root / "global.json")
    group = next(iter(record["recommendations"]))
    assert t.export_recommended(record, root / "scoped.json", group)["scope"]["group_id"] == group


def test_malformed_native_shapes_and_media_latency(native):
    for field, value in (("params", []), ("runs", {}), ("agg", [])):
        bad = {**native, field: value}
        with pytest.raises(t.TuningError):
            t._parse_result_json(bad, 128, 3)
    with_media = copy.deepcopy(native)
    for run in with_media["runs"]:
        run["media_us"] = 1000000
    assert t._parse_result_json(with_media, 128, 3)["latency_s"] == pytest.approx(2.658426)


def test_prompt_contents_and_projector_are_part_of_group_identity(setup):
    exe, v, root = setup
    prompt = root / "prompt.txt"
    prompt.write_text("first prompt")
    first = t.run_tuning(exe, [v], t.SearchSpace(), root / "one",
                         prompt_file=prompt, power_state="ac")
    prompt.write_text("different prompt")
    second = t.run_tuning(exe, [v], t.SearchSpace(), root / "two",
                          prompt_file=prompt, power_state="ac")
    assert first["recommended"]["group_id"] != second["recommended"]["group_id"]
    assert first["results"][0]["group_id"] == first["recommended"]["group_id"]
    assert first["results"][0]["workload"]["prompt_file"] == str(prompt)


@pytest.mark.parametrize("diagnostic", [None, {}, float("nan"), float("inf"), "unknown"])
def test_invalid_optional_variability_never_poison_scores(native, diagnostic):
    row = _row(native, variability_ratio=diagnostic)
    assert t.rank_results([row])[0]["score"] == pytest.approx(95.950082)
    assert t.rank_results([row], variability_penalty=0.1) == []


def test_service_modes_record_is_derived_from_measured_cells(setup):
    exe, v, root = setup
    rec = t.run_tuning(exe, [v], t.SearchSpace(threads=(0, 6), repeats=3), root / "run")
    service = rec["recommendation"]
    assert json.loads(Path(rec["recommendation_path"]).read_text()) == service
    assert service["model_sha256"] == t._sha256(v.path)
    assert service["model_id"] == v.id
    assert Path(service["scope"]["evidence"]).is_file()
    assert set(service["modes"]) == {"fast", "balanced"}
    assert "efficient" in service["unavailable_modes"]
    for mode, chosen in service["modes"].items():
        winner = t.rank_results(rec["results"], mode)[0]
        assert {k: chosen[k] for k in ("device", "threads", "context")} == {
            k: winner[k] for k in ("device", "threads", "context")}
        assert chosen["metrics"]["decode_tps"] == winner["decode_tps"]
        assert chosen["evidence"] == winner["result_path"]


def test_parent_apply_and_load_use_the_new_measured_config(setup, monkeypatch):
    # Optional local integration with the parent's uncommitted service, read only.
    # CI still runs the portable schema/command tests when that source is absent.
    import importlib.util
    import types
    service_path = ROOT.parents[1] / "Ai-infra-summit/turbo/service.py"
    if not service_path.is_file():
        pytest.skip("parent service checkout not available")
    spec = importlib.util.spec_from_file_location("turbo._parent_service_contract", service_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    exe, v, root = setup
    rec = t.run_tuning(exe, [v], t.SearchSpace(devices=("cpu",), threads=(6,),
                       contexts=(2048,), repeats=3), root / "run")
    engine = module.Engine({"models": {v.id: {"path": v.path}}, "default": v.id,
                            "recommendation_file": rec["recommendation_path"], "sdk_dir": "fake"})
    selected = rec["recommendation"]["modes"]["fast"]
    applied = engine.apply("fast", v.id)
    assert applied["config"] == {"device": "cpu", "threads": 6, "context": 2048}
    assert applied["config"] == {k: selected[k] for k in ("device", "threads", "context")}
    assert applied["evidence"]["metrics"] == selected["metrics"]
    loaded = []
    monkeypatch.setitem(sys.modules, "turbo.native", types.SimpleNamespace(
        NativeRuntime=lambda path: object(),
        NativeModel=lambda runtime, path, **kw: loaded.append((path, kw)) or object()))
    engine.load(v.id)
    assert loaded[0][0] == v.path
    assert {k: loaded[0][1][k] for k in ("device", "threads", "context")} == applied["config"]
    with pytest.raises(ValueError, match="no eligible"):
        engine.apply("efficient", v.id)
    wrong = root / "unmeasured.gguf"
    wrong.write_bytes(b"different weights")
    engine.config["models"]["other"] = {"path": str(wrong)}
    with pytest.raises(ValueError, match="different model weights"):
        engine.apply("fast", "other")


def test_service_export_rejects_unapplyable_plugin_and_requires_explicit_group(setup):
    exe, v, root = setup
    other = replace(v, id="another-variant")
    rec = t.run_tuning(exe, [v, other], t.SearchSpace(), root / "run")
    assert rec["recommendation"] is None and rec["recommendation_path"] is None
    group = rec["results"][0]["group_id"]
    service = t.recommendation_record(rec, group)
    assert service["model_id"] == v.id
    rec["results"][0]["model"]["tokenizer_path"] = "explicit-tokenizer.json"
    with pytest.raises(t.TuningError, match="artifact overrides"):
        t.recommendation_record(rec, group)
