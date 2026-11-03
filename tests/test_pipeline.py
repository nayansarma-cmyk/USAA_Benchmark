"""Integrity checks for the benchmark harness.  Run:  python -m tests.test_pipeline
These verify the *measuring instrument* (scoring, model separation, resumability), not any model."""
import json, tempfile
from pathlib import Path
from src import config, run, score


def _case():
    return run.load_cases("test")[0]


def test_oracle_scores_perfect():
    c = _case()
    pred = [dict(location=e["location"]) for e in c["key"] if e["expected"]]
    s = score.score_one(pred, c)
    assert (s["fp"], s["fn"], s["cos_fp"]) == (0, 0, 0), s


def test_empty_prediction_misses_everything():
    c = _case()
    s = score.score_one([], c)
    assert s["tp"] == 0 and s["fn"] == sum(e["expected"] for e in c["key"])


def test_cosmetic_flag_is_counted_as_false_alarm():
    c = _case()
    cos = [e for e in c["key"] if not e["expected"]]
    if not cos:
        return
    s = score.score_one([dict(location=cos[0]["location"])], c)
    assert s["cos_fp"] == 1 and s["fp"] == 1


def test_explain_matches_score():
    c = _case()
    exp = [e for e in c["key"] if e["expected"]]
    pred = [dict(location=exp[0]["location"]), dict(location="Collision Deductible XYZ-not-real")]
    s, ex = score.score_one(pred, c), score.explain(pred, c)
    assert sum(r["status"] == "HIT" for r in ex) == s["tp"]
    assert sum(r["status"] == "MISSED" for r in ex) == s["fn"]
    assert sum("FALSE ALARM" in r["status"] for r in ex) == s["fp"]


def test_models_are_kept_separate_and_resumable():
    old = config.RESULTS
    with tempfile.TemporaryDirectory() as d:
        config.RESULTS = Path(d)
        try:
            kw = dict(arm_list=["A_rules", "B_llm"], probe_list=["none"], runs=2, n_cases=2, passes=1, mock=True)
            r1 = run.execute(judge_models=["model-x"], **kw)
            r2 = run.execute(judge_models=["model-y"], **kw)   # must NOT be skipped as "done"
            r3 = run.execute(judge_models=["model-x", "model-y"], **kw)  # fully resumable -> nothing new
            assert r1["new"] == 2 + 2 * 2 and r2["new"] == 2 * 2 and r3["new"] == 0, (r1, r2, r3)
            rows = [json.loads(l) for l in open(r1["path"])]
            assert {r["judge"] for r in rows} == {"-", "model-x", "model-y"}
            # every LLM chain is complete: levels 0..passes present
            chains = {}
            for r in rows:
                chains.setdefault((r["case"], r["arm"], r["run"], r["judge"]), []).append(r["level"])
            assert all(sorted(v) == list(range(len(v))) for v in chains.values())
            assert all(len(v) == 2 for k, v in chains.items() if k[1] == "B_llm")
            assert all(r["calls"] for r in rows if r["arm"] == "B_llm" and r["level"] == 0)
        finally:
            config.RESULTS = old


def test_failed_chain_leaves_no_partial_rows():
    from src import arms
    old, real = config.RESULTS, arms.ARMS["B_llm"]

    def boom(llm, a, b, swap, nonce, verifier_model, passes, usage, **kw):
        yield 0, []
        raise TimeoutError("simulated API timeout")
    with tempfile.TemporaryDirectory() as d:
        config.RESULTS = Path(d)
        arms.ARMS["B_llm"] = (boom, True)
        try:
            r = run.execute(["B_llm"], ["none"], 1, 1, 1, mock=True, judge_models=["m"])
            assert r["new"] == 0 and r["errors"] == 1
            assert not Path(r["path"]).read_text().strip(), "partial chain was written"
            assert "simulated API timeout" in (Path(d) / "errors_mock.jsonl").read_text()
        finally:
            arms.ARMS["B_llm"] = real
            config.RESULTS = old


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for f in fns:
        f(); print("PASS", f.__name__)
    print(f"{len(fns)} checks passed")
