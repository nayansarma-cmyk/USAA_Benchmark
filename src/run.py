import argparse, glob, json, time
from . import config, arms, probes
from .llm import LLM, parse_json

FATAL = ("AuthenticationError", "PermissionDeniedError", "NotFoundError", "BadRequestError")


def load_cases(split, case_set=None):
    """case_set: None = every case; otherwise only cases whose "set" matches (cases without one are "synthetic")."""
    cs = [json.load(open(f, encoding="utf-8")) for f in sorted(glob.glob(str(config.CASES / f"{split}_*.json")))]
    return [c for c in cs if case_set is None or c.get("set", "synthetic") == case_set]


def plan(arm_list, probe_list, runs, n_cases, n_judges=1):
    """Total (case, probe, arm, judge-model, run) chains a run would cover."""
    per_case = sum(runs * n_judges if arms.ARMS[a][1] else 1 for a in arm_list)
    return n_cases * len(probe_list) * per_case


def _row_key(r):
    return (r["case"], r["arm"], r["probe"], r["run"], r["verifier"], r.get("judge", "-"), r.get("vmodel", "-"))


def execute(arm_list, probe_list, runs, n_cases=0, passes=config.VERIFY_PASSES, verifier="cross",
            mock=False, progress=None, should_stop=None, judge_models=None, verifier_model=None, case_set=None):
    """Run the benchmark. `progress(done, total, label)` is called after each chain.

    * Every LLM chain is recorded with the judge/verifier model that produced it, so results from
      different models never overwrite or mask each other.
    * A chain is written atomically (all levels or none), so a crash never leaves a half-finished
      chain that a resume would treat as done.
    * Per-chain failures are logged to results/errors.jsonl and the run continues; auth / bad-model
      errors abort immediately with a clear message.
    Returns dict(new, errors, path)."""
    llm = LLM(mock=mock)
    judge_models = judge_models or [config.JUDGE_MODEL]
    cases = load_cases("test", case_set)
    cases = cases[:n_cases] if n_cases else cases
    config.RESULTS.mkdir(parents=True, exist_ok=True)
    out = config.RESULTS / ("runs_mock.jsonl" if mock else "runs.jsonl")
    err_path = config.RESULTS / ("errors_mock.jsonl" if mock else "errors.jsonl")
    done = set()
    if out.exists():
        for l in open(out):
            if l.strip():
                done.add(_row_key(json.loads(l)))
    total, step, n, errors = plan(arm_list, probe_list, runs, len(cases), len(judge_models)), 0, 0, 0
    with open(out, "a") as fh:
        for case in cases:
            for probe in probe_list:
                ta, tb, swap = probes.apply(probe, case["text_a"], case["text_b"], seed=case["seed"])
                for arm in arm_list:
                    fn, is_llm = arms.ARMS[arm]
                    for judge in (judge_models if is_llm else ["-"]):
                        vmodel = "-" if not is_llm else (judge if verifier == "same" else (verifier_model or config.VERIFIER_CROSS_MODEL))
                        vtag = verifier if is_llm else "-"
                        for run in range(runs if is_llm else 1):
                            if should_stop and should_stop():
                                return dict(new=n, errors=errors, path=out)
                            step += 1
                            key = (case["id"], arm, probe, run, vtag, judge, vmodel)
                            if key not in done:
                                usage, rows, seen = [], [], 0
                                nonce = f"{case['id']}|{arm}|{probe}|{run}"
                                try:
                                    for level, pred in fn(llm=llm, a=ta, b=tb, swap=swap, nonce=nonce, verifier_model=vmodel,
                                                          passes=passes, usage=usage, judge_model=None if judge == "-" else judge):
                                        calls = [dict(model=u.get("model"), text=u["text"], tin=u["tin"], tout=u["tout"],
                                                      latency=u["latency"], parse_ok=bool(parse_json(u["text"])))
                                                 for u in usage[seen:]]
                                        seen = len(usage)
                                        rows.append(dict(case=case["id"], arm=arm, probe=probe, run=run, level=level,
                                                         verifier=vtag, judge=judge, vmodel=vmodel, pred=pred, calls=calls,
                                                         tin=sum(u["tin"] for u in usage), tout=sum(u["tout"] for u in usage),
                                                         latency=round(sum(u["latency"] for u in usage), 2)))
                                    msg = None if rows else "arm produced no output (missing AI-written ruleset? run Generate rulesets)"
                                except Exception as e:
                                    if type(e).__name__ in FATAL and not mock:
                                        raise RuntimeError(f"{type(e).__name__} for model '{judge}' / verifier '{vmodel}': {e}") from e
                                    msg, rows = f"{type(e).__name__}: {e}", []
                                if msg:
                                    errors += 1
                                    with open(err_path, "a") as ef:
                                        ef.write(json.dumps(dict(ts=time.time(), case=case["id"], arm=arm, probe=probe, run=run,
                                                                 judge=judge, vmodel=vmodel, error=msg)) + "\n")
                                if rows:
                                    fh.write("".join(json.dumps(r) + "\n" for r in rows)); fh.flush(); n += 1
                            if progress:
                                progress(step, total, f"{case['id']} · {arm}{'' if judge == '-' else ' @ ' + judge} · {probe} · run {run + 1}")
    return dict(new=n, errors=errors, path=out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", default="A_rules,B_llm,C_llm_plus_rules,E_hybrid,D1_llm_written_rules,D2_llm_written_rules,D3_llm_written_rules")
    ap.add_argument("--probes", default="none")
    ap.add_argument("--runs", type=int, default=3, help="repeats for LLM arms (deterministic arms run once)")
    ap.add_argument("--cases", type=int, default=0, help="limit number of test cases (0 = all)")
    ap.add_argument("--passes", type=int, default=config.VERIFY_PASSES)
    ap.add_argument("--verifier", choices=["cross", "same"], default="cross")
    ap.add_argument("--judge-models", default=config.JUDGE_MODEL, help="comma-separated; each is run and scored separately")
    ap.add_argument("--verifier-model", default=config.VERIFIER_CROSS_MODEL)
    ap.add_argument("--case-set", default=None, help="synthetic | usaa_100 (default: all test cases)")
    ap.add_argument("--mock", action="store_true", help="offline fake LLM to test the pipeline")
    ap.add_argument("--gen-rules", action="store_true", help="have the LLM write rulesets (arms D*), then exit")
    a = ap.parse_args()

    if a.gen_rules:
        t = load_cases("train")[0]
        arms.generate_rules(LLM(mock=a.mock), t["text_a"], t["text_b"])
        return
    r = execute(a.arms.split(","), a.probes.split(","), a.runs, a.cases, a.passes, a.verifier, a.mock,
                judge_models=a.judge_models.split(","), verifier_model=a.verifier_model, case_set=a.case_set)
    print(f"completed {r['new']} new chains ({r['errors']} failed, see errors.jsonl) -> {r['path']}")


if __name__ == "__main__":
    main()
