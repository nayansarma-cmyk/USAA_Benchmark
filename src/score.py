"""Scores runs against the exact answer key and writes results/report.md."""
import argparse, glob, itertools, json, random, re, statistics as st
from collections import defaultdict
from . import config

SEC = re.compile(r"(\d+\.\d+)")
alnum = lambda s: re.sub(r"[^a-z0-9]", "", str(s).lower())


def canon(loc, labels):
    m = SEC.search(str(loc))
    if m and not any(alnum(l) in alnum(loc) for l in labels):
        return m.group(1)
    n = alnum(loc)
    for l in labels:
        ln = alnum(l)
        if n == ln or (len(n) >= 6 and (n in ln or ln in n)):
            return ln
    return n


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 1.0
    r = tp / (tp + fn) if tp + fn else 1.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def score_one(pred, case):
    labels = case["labels"]
    exp = {canon(e["location"], labels): e for e in case["key"] if e["expected"]}
    cos = {canon(e["location"], labels) for e in case["key"] if not e["expected"]} - set(exp)
    P = {canon(c.get("location", ""), labels) for c in pred}
    tp, fp, fn = len(P & set(exp)), len(P - set(exp)), len(set(exp) - P)
    by_tier = defaultdict(lambda: [0, 0])
    for loc, e in exp.items():
        by_tier[e["tier"]][1] += 1
        by_tier[e["tier"]][0] += loc in P
    return dict(tp=tp, fp=fp, fn=fn, cos_fp=len(P & cos), n_cos=len(cos), tiers=by_tier, P=frozenset(P), TP=frozenset(P & set(exp)),
                FP=frozenset(P - set(exp)))


def explain(pred, case):
    """Row-per-item breakdown of one prediction vs the answer key (used by the UI's process view).
    status: HIT (real change found) | MISSED (real change not flagged) | FALSE ALARM (flagged, not a real change)
            | COSMETIC FALSE ALARM (flagged a wording/format-only edit)."""
    labels = case["labels"]
    exp = {canon(e["location"], labels): e for e in case["key"] if e["expected"]}
    cos = {canon(e["location"], labels): e for e in case["key"] if not e["expected"]}
    seen, out = {}, []
    for c in pred:
        loc = canon(c.get("location", ""), labels)
        seen.setdefault(loc, c)
    for loc, e in exp.items():
        p = seen.get(loc)
        out.append(dict(status="HIT" if p else "MISSED", location=e["location"], tier=e["tier"], truth=f"{e['old']} -> {e['new']}",
                        model_said=(p or {}).get("description", "") if p else ""))
    for loc, p in seen.items():
        if loc in exp:
            continue
        status = "COSMETIC FALSE ALARM" if loc in cos else "FALSE ALARM"
        out.append(dict(status=status, location=p.get("location", ""), tier=cos[loc]["tier"] if loc in cos else "-",
                        truth=f"{cos[loc]['old']} -> {cos[loc]['new']}" if loc in cos else "not a change in the answer key",
                        model_said=p.get("description", "")))
    return out


def label_row(r):
    """Make model identity part of the arm label so different models are scored as different arms."""
    if r.get("judge") and r["judge"] != "-":
        r["arm"] = f"{r['arm']} @ {r['judge']}"
        r["verifier"] = f"{r['verifier']}:{r.get('vmodel', '?')}"
    return r


def mean(x): return sum(x) / len(x) if x else float("nan")


def boot_diff(a_scores, b_scores, n=2000, seed=0):
    """paired bootstrap over cases of mean(b) - mean(a)."""
    ids = sorted(set(a_scores) & set(b_scores))
    if not ids: return None
    rng = random.Random(seed)
    d = [b_scores[i] - a_scores[i] for i in ids]
    ms = sorted(mean([rng.choice(d) for _ in d]) for _ in range(n))
    return mean(d), ms[int(0.025 * n)], ms[int(0.975 * n)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=str(config.RESULTS / "runs.jsonl"))
    a = ap.parse_args()
    cases = {c["id"]: c for c in (json.load(open(f)) for f in glob.glob(str(config.CASES / "test_*.json")))}
    rows = [label_row(json.loads(l)) for l in open(a.file) if l.strip()]
    for r in rows:
        r["s"] = score_one(r["pred"], cases[r["case"]])
    G = defaultdict(list)
    for r in rows:
        G[(r["arm"], r["verifier"], r["probe"], r["level"])].append(r)
    L = ["# Results\n", f"{len(rows)} scored outputs over {len({r['case'] for r in rows})} test cases (of {len(cases)} available).\n"]

    # 1. headline table
    L += ["## 1. Accuracy (pooled TP/FP/FN over all cases and runs)\n",
          "| arm | verifier | probe | passes | precision | recall | F1 | cosmetic false-alarm rate | structured recall | lexical recall | semantic recall | added/removed recall | cases x runs | tokens/chain |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for k in sorted(G):
        rs = G[k]
        tp, fp, fn = (sum(r["s"][x] for r in rs) for x in ("tp", "fp", "fn"))
        p, rc, f1 = prf(tp, fp, fn)
        cf = sum(r["s"]["cos_fp"] for r in rs) / max(1, sum(r["s"]["n_cos"] for r in rs))
        def tr(t):
            h = sum(r["s"]["tiers"][t][0] for r in rs if t in r["s"]["tiers"]); n = sum(r["s"]["tiers"][t][1] for r in rs if t in r["s"]["tiers"])
            return f"{h / n:.2f}" if n else "-"
        ar = [r["s"]["tiers"] for r in rs]
        ah = sum(t["added"][0] + t["removed"][0] for t in ar); an = sum(t["added"][1] + t["removed"][1] for t in ar)
        tok = mean([r["tin"] + r["tout"] for r in rs])
        L.append(f"| {k[0]} | {k[1]} | {k[2]} | {k[3]} | {p:.3f} | {rc:.3f} | {f1:.3f} | {cf:.3f} | {tr('structured')} | {tr('lexical')} | {tr('semantic')} | {ah / an if an else float('nan'):.2f} | {len(rs)} | {tok:.0f} |")

    # 2. paired bootstrap vs deterministic baseline (probe none, level 0)
    def per_case_f1(key):
        by = defaultdict(list)
        for r in G.get(key, []):
            by[r["case"]].append(prf(r["s"]["tp"], r["s"]["fp"], r["s"]["fn"])[2])
        return {c: mean(v) for c, v in by.items()}
    base = per_case_f1(("A_rules", "-", "none", 0))
    L += ["\n## 2. F1 difference vs deterministic ruleset A (probe=none, paired bootstrap over cases, 95% CI)\n",
          "| arm | verifier | passes | mean dF1 | 95% CI | verdict |", "|---|---|---|---|---|---|"]
    for k in sorted(G):
        if k[2] != "none" or k[0] == "A_rules": continue
        res = boot_diff(base, per_case_f1(k))
        if res:
            m, lo, hi = res
            L.append(f"| {k[0]} | {k[1]} | {k[3]} | {m:+.3f} | [{lo:+.3f}, {hi:+.3f}] | {'AI better' if lo > 0 else 'rules better' if hi < 0 else 'inconclusive'} |")

    # 3. consistency
    L += ["\n## 3. Run-to-run consistency (mean pairwise Jaccard of flagged locations; 1.0 = identical every run)\n",
          "| arm | verifier | probe | passes | consistency |", "|---|---|---|---|---|"]
    for k in sorted(G):
        by = defaultdict(list)
        for r in G[k]: by[r["case"]].append(r["s"]["P"])
        js = [len(x & y) / len(x | y) if x | y else 1.0 for v in by.values() for x, y in itertools.combinations(v, 2)]
        if js: L.append(f"| {k[0]} | {k[1]} | {k[2]} | {k[3]} | {mean(js):.3f} |")

    # 4. bias probes
    L += ["\n## 4. Bias probes: change vs probe=none (same arm / verifier / passes)\n",
          "`flip rate` = share of (case, run) whose flagged set differs from the same run under probe=none. Compare with the `baseline flip` (run i vs run j under none) to separate bias from sampling noise.\n",
          "| arm | verifier | passes | probe | flip rate | baseline flip | dRecall | dFP rate |", "|---|---|---|---|---|---|---|---|"]
    for k in sorted(G):
        if k[2] == "none": continue
        nk = (k[0], k[1], "none", k[3])
        if nk not in G: continue
        nm = {(r["case"], r["run"]): r["s"] for r in G[nk]}
        flips, rd, fd = [], [], []
        for r in G[k]:
            b = nm.get((r["case"], r["run"]))
            if not b: continue
            flips.append(r["s"]["P"] != b["P"])
            rd.append(prf(r["s"]["tp"], 0, r["s"]["fn"])[1] - prf(b["tp"], 0, b["fn"])[1])
            fd.append(r["s"]["fp"] - b["fp"])
        by = defaultdict(list)
        for r in G[nk]: by[r["case"]].append(r["s"]["P"])
        bf = [x != y for v in by.values() for x, y in itertools.combinations(v, 2)]
        if flips: L.append(f"| {k[0]} | {k[1]} | {k[3]} | {k[2]} | {mean(flips):.3f} | {mean(bf) if bf else float('nan'):.3f} | {mean(rd):+.3f} | {mean(fd):+.2f} |")

    # 5. verification effect
    L += ["\n## 5. Verification effect per extra AI check pass (mean per case-run)\n",
          "| arm | verifier | probe | pass | true positives gained | true positives lost | false positives added | false positives removed |", "|---|---|---|---|---|---|---|---|"]
    chain = {(r["case"], r["arm"], r["probe"], r["run"], r["verifier"], r["level"]): r["s"] for r in rows}
    agg = defaultdict(lambda: [[], [], [], []])
    for (c, arm, pr, run, v, lv), s in chain.items():
        prev = chain.get((c, arm, pr, run, v, lv - 1))
        if lv == 0 or prev is None: continue
        g = agg[(arm, v, pr, lv)]
        g[0].append(len(s["TP"] - prev["TP"])); g[1].append(len(prev["TP"] - s["TP"]))
        g[2].append(len(s["FP"] - prev["FP"])); g[3].append(len(prev["FP"] - s["FP"]))
    for k in sorted(agg):
        g = agg[k]
        L.append(f"| {k[0]} | {k[1]} | {k[2]} | {k[3]} | {mean(g[0]):.2f} | {mean(g[1]):.2f} | {mean(g[2]):.2f} | {mean(g[3]):.2f} |")

    out = config.RESULTS / ("report_mock.md" if "mock" in a.file else "report.md")
    out.write_text("\n".join(L) + "\n")
    print("\n".join(L[:30])); print(f"\nfull report -> {out}")


if __name__ == "__main__":
    main()
