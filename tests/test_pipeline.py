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


def test_plain_english_names():
    from src import viewmodel as vm
    assert vm.short_model("claude-sonnet-5-5") == "Sonnet 5.5" and vm.short_model("my-custom") == "my-custom"
    assert vm.pretty_arm("B_llm @ claude-haiku-5-5") == "AI only · Haiku 5.5" and vm.pretty_arm("A_rules") == "Rules only"
    assert vm.verifier_note("cross:claude-opus-5-5") == "checked by Opus 5.5" and vm.verifier_note("-") == ""
    ms = [dict(key=("B_llm @ x", "cross:claude-opus-5-5"), arm="B_llm @ x"), dict(key=("B_llm @ x", "same:x"), arm="B_llm @ x")]
    n = vm.unique_names(ms)
    assert len(set(n.values())) == 2, n   # collisions are disambiguated


def test_summary_and_neutral_verdicts():
    from src import viewmodel as vm
    with tempfile.TemporaryDirectory() as d:
        old = config.RESULTS
        config.RESULTS = Path(d)
        try:
            r = run.execute(["A_rules", "B_llm"], ["none"], 2, 6, 1, mock=True, judge_models=["claude-sonnet-5-5"])
            rows, _ = vm.load_scored(r["path"])
        finally:
            config.RESULTS = old
    ms = vm.summarize(rows)
    assert {m["arm"] for m in ms} == {"A_rules", "B_llm @ claude-sonnet-5-5"}
    assert all(0 <= m["found"] <= 1 and 0 <= m["correct"] <= 1 for m in ms)
    comps = vm.compare_to_rules(rows)
    assert comps[("B_llm @ claude-sonnet-5-5", "cross:claude-opus-5-5")]["verdict"] in ("better", "worse", "unclear")
    text = vm.headline(ms, vm.unique_names(ms), comps, 6).lower()
    assert "baseline" in text and "scored best" not in text and "beat" not in text   # neutral framing
    case = _case()
    tbl, cols = vm.side_by_side(rows, dict(case, id=rows[0]["case"]), "none",
                                [(m["arm"], m["verifier"], vm.pretty_arm(m["arm"])) for m in ms])
    assert len(cols) == 2 and tbl[-1]["Item"] == "SCORE: Overall score"


def test_review_table_identifies_case_where_and_why():
    from src import viewmodel as vm
    with tempfile.TemporaryDirectory() as d:
        old = config.RESULTS
        config.RESULTS = Path(d)
        try:
            r = run.execute(["A_rules", "B_llm"], ["none"], 3, 4, 1, mock=True, judge_models=["claude-sonnet-5-5"])
            rows, cases = vm.load_scored(r["path"])
        finally:
            config.RESULTS = old
    t = vm.review_table(rows, cases)
    assert t and all(x["Case"].startswith("Case ") and x["Where"] and x["Why"] and x["Method"] for x in t)
    # every answer-key item appears once per method per case
    n_items = sum(len(cases[c]["key"]) for c in {x["_case"] for x in t})
    rules_rows = [x for x in t if x["Method"] == "Rules only" and x["_case"] in cases and x["Difficulty"] != "—"]
    assert len(rules_rows) >= n_items
    # wherever the rules missed a semantic change, the explanation says why in plain terms
    miss = [x for x in t if x["Method"] == "Rules only" and x["_outcome"] == "Missed" and x["Difficulty"] == "hard"]
    assert miss and all("meaning" in x["Why"] for x in miss)
    # AI aggregated over 3 attempts: outcomes are one of the known labels
    assert {x["_outcome"] for x in t} <= {"Found", "Missed", "Wrongly flagged", "Correctly ignored", "Inconsistent"}
    # excerpt shows the actual policy text for a declarations field and for a section
    c0 = next(iter(cases.values()))
    assert vm.excerpt(c0, "Collision Deductible")[1].startswith("$")
    h, o, n = vm.excerpt(c0, "3.1")
    assert h.startswith("Section 3.1") and "notify" in o.lower()


def test_no_rules_baseline_is_handled():
    from src import viewmodel as vm
    ms = [dict(key=("B_llm @ x", "-"), arm="B_llm @ x", found=.9, correct=.8)]
    assert "nothing to compare" in vm.headline(ms, vm.unique_names(ms), {}, 3)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for f in fns:
        f(); print("PASS", f.__name__)
    print(f"{len(fns)} checks passed")
