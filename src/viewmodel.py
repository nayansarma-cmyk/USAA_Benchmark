"""Presentation logic for the UI: plain-English names, pooled scores, verdicts, side-by-side tables.
No Streamlit imports here, so everything is unit-testable."""
import glob, itertools, json
from collections import defaultdict
from . import config, score

MODEL_PRESETS = ["claude-fable-5-1", "claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"]

ARM_NAMES = {
    "A_rules": "Rules only",
    "B_llm": "AI only",
    "C_llm_plus_rules": "AI guided by rules",
    "E_hybrid": "Rules + AI together",
    "D1_llm_written_rules": "AI-written rules (set 1)",
    "D2_llm_written_rules": "AI-written rules (set 2)",
    "D3_llm_written_rules": "AI-written rules (set 3)",
}
ARM_HELP = {
    "A_rules": "A fixed set of if-then rules written by people. No AI. This is the baseline everything else is compared with.",
    "B_llm": "An AI model reads both policy versions and lists what changed.",
    "C_llm_plus_rules": "The same AI, but it is also given the rules as instructions.",
    "E_hybrid": "Rules handle the listed fields and added or deleted clauses. The AI only judges reworded clauses.",
    "D1_llm_written_rules": "An AI writes a rule set once, then that rule set runs as ordinary code.",
    "D2_llm_written_rules": "A second independently written AI rule set.",
    "D3_llm_written_rules": "A third independently written AI rule set.",
}
PROBE_NAMES = {
    "none": "Normal (no trap)",
    "swap": "Documents shown in reverse order",
    "authority": "Fake 'Compliance approved' note",
    "bandwagon": "Fake 'reviewers found nothing' note",
    "padding": "Long irrelevant filler text",
    "distraction": "Reordered and reformatted text",
}
PROBE_HELP = {
    "none": "The standard test, with nothing added.",
    "swap": "Checks whether the order the documents are shown in changes the answer.",
    "authority": "Adds a note claiming Compliance already approved the renewal. A good method ignores it.",
    "bandwagon": "Adds a note claiming other reviewers found no differences. A good method ignores it.",
    "padding": "Adds a lot of identical boilerplate to both versions to see if it hides the real changes.",
    "distraction": "Reorders and re-wraps the renewal text without changing its meaning.",
}
TIER_NAMES = {
    "structured": "Easy: a listed value changed",
    "lexical": "Medium: numbers or key legal words changed",
    "semantic": "Hard: meaning changed, no obvious clue",
    "added_removed": "A clause was added or deleted",
}
TIER_SHORT = {"structured": "easy", "lexical": "medium", "semantic": "hard", "added": "clause added",
              "removed": "clause deleted", "cosmetic": "harmless edit"}


# ------------------------------------------------------------------ names
def short_model(m):
    """claude-sonnet-5-5 -> Sonnet 5.5"""
    if m and m.startswith("claude-"):
        parts = m[7:].split("-")
        ver = [p for p in parts[1:] if p.isdigit()]
        if parts and len(ver) == len(parts) - 1:
            return parts[0].capitalize() + (" " + ".".join(ver) if ver else "")
    return m


def pretty_arm(label):
    """'B_llm @ claude-sonnet-5-5' -> 'AI only · Sonnet 5.5'"""
    base, _, model = label.partition(" @ ")
    name = ARM_NAMES.get(base, base)
    return f"{name} · {short_model(model)}" if model else name


def verifier_note(v):
    if not v or v == "-":
        return ""
    kind, _, model = v.partition(":")
    return "self-checked" if kind == "same" else f"checked by {short_model(model)}" if model else "checked by another model"


def unique_names(methods):
    """Display name per method key, adding the checker only when two methods would otherwise look identical."""
    base = {m["key"]: pretty_arm(m["arm"]) for m in methods}
    counts = defaultdict(int)
    for n in base.values():
        counts[n] += 1
    return {k: (n if counts[n] == 1 or not verifier_note(k[1]) else f"{n} ({verifier_note(k[1])})") for k, n in base.items()}


def is_ai(arm_label):
    return " @ " in arm_label


def pct(x):
    return "n/a" if x is None or x != x else f"{round(100 * x)}%"


# ------------------------------------------------------------------ data
def case_files(split="test"):
    return sorted(glob.glob(str(config.CASES / f"{split}_*.json")), key=lambda f: int(f.rsplit("_", 1)[1][:-5]))


def load_scored(path):
    cases = {c["id"]: c for c in (json.load(open(f)) for f in case_files())}
    rows = [score.label_row(json.loads(l)) for l in open(path) if l.strip()]
    for r in rows:
        r["s"] = score.score_one(r["pred"], cases[r["case"]])
        r["f1"] = score.prf(r["s"]["tp"], r["s"]["fp"], r["s"]["fn"])[2]
    return rows, cases


def pick_level(rows, level="final"):
    """Rows for the first answer (level 0) or the last answer of each chain."""
    if level == "first":
        return [r for r in rows if r["level"] == 0]
    best = {}
    for r in rows:
        k = (r["case"], r["arm"], r["verifier"], r["run"], r["probe"])
        if k not in best or r["level"] > best[k]["level"]:
            best[k] = r
    return list(best.values())


def _mean(x):
    x = list(x)
    return sum(x) / len(x) if x else float("nan")


def _consistency(rs):
    by = defaultdict(list)
    for r in rs:
        by[r["case"]].append(r["s"]["P"])
    js = [len(a & b) / len(a | b) if a | b else 1.0 for v in by.values() for a, b in itertools.combinations(v, 2)]
    return _mean(js) if js else None


def summarize(rows, probe="none", level="final"):
    """Pooled scores per (arm, verifier)."""
    G = defaultdict(list)
    for r in pick_level(rows, level):
        if r["probe"] == probe:
            G[(r["arm"], r["verifier"])].append(r)
    out = []
    for (arm, ver), rs in G.items():
        tp, fp, fn = (sum(r["s"][x] for r in rs) for x in ("tp", "fp", "fn"))
        p, rc, f1 = score.prf(tp, fp, fn)

        def tier_recall(ts):
            h = sum(r["s"]["tiers"][t][0] for r in rs for t in ts if t in r["s"]["tiers"])
            n = sum(r["s"]["tiers"][t][1] for r in rs for t in ts if t in r["s"]["tiers"])
            return h / n if n else None
        out.append(dict(
            key=(arm, ver), arm=arm, verifier=ver, is_ai=is_ai(arm), found=rc, correct=p, f1=f1,
            cosmetic=sum(r["s"]["cos_fp"] for r in rs) / max(1, sum(r["s"]["n_cos"] for r in rs)),
            tiers={"structured": tier_recall(["structured"]), "lexical": tier_recall(["lexical"]),
                   "semantic": tier_recall(["semantic"]), "added_removed": tier_recall(["added", "removed"])},
            cases=len({r["case"] for r in rs}), runs=len({r["run"] for r in rs}), consistency=_consistency(rs),
            tokens=_mean(r["tin"] + r["tout"] for r in rs), seconds=_mean(r["latency"] for r in rs)))
    return sorted(out, key=lambda m: m["f1"], reverse=True)


def compare_to_rules(rows, probe="none", level="final"):
    """Paired bootstrap of per-case F1 against A_rules. verdict in {better, worse, unclear, n/a}."""
    sel = [r for r in pick_level(rows, level) if r["probe"] == probe]
    per = defaultdict(lambda: defaultdict(list))
    for r in sel:
        per[(r["arm"], r["verifier"])][r["case"]].append(r["f1"])
    pc = {k: {c: _mean(v) for c, v in d.items()} for k, d in per.items()}
    base = pc.get(("A_rules", "-"))
    out = {}
    for k, d in pc.items():
        if k == ("A_rules", "-") or not base:
            continue
        common = set(base) & set(d)
        res = score.boot_diff(base, d) if len(common) >= 5 else None
        if not res:
            out[k] = dict(diff=None, lo=None, hi=None, n=len(common), verdict="n/a")
            continue
        m, lo, hi = res
        out[k] = dict(diff=m, lo=lo, hi=hi, n=len(common), verdict="better" if lo > 0 else "worse" if hi < 0 else "unclear")
    return out


def double_check_effect(rows, probe="none"):
    """How much the AI's extra checking passes changed the score (AI methods only)."""
    if not any(r["level"] > 0 for r in rows):
        return []
    first = {m["key"]: m for m in summarize(rows, probe, "first")}
    final = {m["key"]: m for m in summarize(rows, probe, "final")}
    return [dict(key=k, first=first[k], final=final[k]) for k in final if k in first and final[k]["is_ai"]]


# ------------------------------------------------------------------ words
# Neutral wording: the comparison has no expected winner. "higher/lower" refers to the overall score only.
VERDICT_TEXT = {
    "better": ("Reliably higher than rules", "blue"),
    "worse": ("Reliably lower than rules", "orange"),
    "unclear": ("No reliable difference from rules", "gray"),
    "n/a": ("Not enough data to compare", "gray"),
}
VERDICT_SENTENCE = {
    "better": "scored reliably higher than the rules",
    "worse": "scored reliably lower than the rules",
    "unclear": "was not reliably different from the rules (the gap could be chance; more cases would settle it)",
    "n/a": "has too little data for a fair comparison yet",
}


def headline(methods, names, comps, n_cases):
    """Neutral, side-by-side description: what each method found vs the rules baseline."""
    if not methods:
        return "No results yet."
    s = f"On **{n_cases} test case{'s' if n_cases != 1 else ''}**:"
    rules = next((m for m in methods if m["key"] == ("A_rules", "-")), None)
    if not rules:
        for m in methods:
            s += f"\n- **{names[m['key']]}** found **{pct(m['found'])}** of the real changes; **{pct(m['correct'])}** of its flags were correct."
        return s + "\n\nNo rules-only run is included, so there is nothing to compare against."
    s += (f"\n- **{names[rules['key']]}** (the baseline) found **{pct(rules['found'])}** of the real changes; "
          f"**{pct(rules['correct'])}** of its flags were correct.")
    for m in methods:
        if m["key"] == rules["key"]:
            continue
        verdict = comps.get(m["key"], {}).get("verdict", "n/a")
        s += (f"\n- **{names[m['key']]}** found **{pct(m['found'])}**; **{pct(m['correct'])}** of its flags were correct. "
              f"Overall it {VERDICT_SENTENCE[verdict]}.")
    return s


def summary_markdown(methods, names, comps, n_cases, headline_text):
    L = ["# Policy change benchmark: summary", "", headline_text.replace("**", ""), "",
         "| Method | Real changes found | Flags that were correct | Harmless edits wrongly flagged | vs rules |", "|---|---|---|---|---|"]
    for m in methods:
        c = comps.get(m["key"])
        L.append(f"| {names[m['key']]} | {pct(m['found'])} | {pct(m['correct'])} | {pct(m['cosmetic'])} | "
                 f"{VERDICT_TEXT[c['verdict']][0] if c else 'baseline'} |")
    L += ["", f"Based on {n_cases} synthetic test case(s). Policies are synthetic, so this reflects the test design, not real portfolios.",
          "", "_AI-assisted analysis: review and validate before sharing outside the team._"]
    return "\n".join(L) + "\n"


# ------------------------------------------------------------------ review table (all cases)
import re
from . import rules

OK_MARK, MISS_MARK, FALSE_MARK, MIX_MARK = "✓", "✗", "⚠", "~"
_SEC = re.compile(r"(\d+\.\d+)")


def _where(case, loc):
    """('Declarations · Collision Deductible' | 'Section 3.1 · Duties After an Accident or Loss')"""
    if loc in case["labels"]:
        return f"Declarations · {loc}"
    m = _SEC.search(str(loc))
    if not m:
        return str(loc)
    sid = m.group(1)
    _, ca = rules.parse(case["text_a"])
    _, cb = rules.parse(case["text_b"])
    title = (ca.get(sid) or cb.get(sid) or ["", ""])[0]
    return f"Section {sid}" + (f" · {title}" if title else "")


def excerpt(case, loc):
    """(heading, original text, renewal text) for a Declarations field or policy section."""
    fa, ca = rules.parse(case["text_a"])
    fb, cb = rules.parse(case["text_b"])
    if loc in case["labels"]:
        return f"Declarations field: {loc}", fa.get(loc, "(not present)"), fb.get(loc, "(not present)")
    m = _SEC.search(str(loc))
    sid = m.group(1) if m else None
    if sid and (sid in ca or sid in cb):
        return (_where(case, loc), ca[sid][1] if sid in ca else "(section not in the original)",
                cb[sid][1] if sid in cb else "(section deleted in the renewal)")
    return str(loc), "(no matching text)", "(no matching text)"


def _explain_outcome(kind, outcome, tier, is_rules):
    if outcome == "Found":
        return "Correctly flagged a real change."
    if outcome == "Correctly ignored":
        return "Correctly ignored a harmless edit." if kind == "cosmetic" else "Correctly left alone."
    if outcome == "Missed":
        base = "A real change was not flagged."
        if tier == "semantic":
            return base + (" It changes the meaning without a new number or legal keyword, which fixed rules cannot see." if is_rules
                           else " It changes the meaning with no obvious number or keyword to spot.")
        if tier == "lexical":
            return base + " It hinges on a number or a legal keyword."
        return base
    if outcome == "Wrongly flagged":
        return ("Flagged a harmless edit (rewording or formatting only)." if kind == "cosmetic"
                else "Flagged something that is not a change in the answer key.")
    return "The answer changed between attempts: sometimes right, sometimes wrong."


def review_table(rows, cases, probe="none", level="final", names=None):
    """One row per (case, item, method). AI methods are aggregated over attempts.
    Columns: Case, Where, Difficulty, Original wording, Renewal wording, Method, Result, Why, What the method said,
    plus helper columns prefixed '_' (case id, location, right/wrong)."""
    sel = [r for r in pick_level(rows, level) if r["probe"] == probe]
    by = defaultdict(list)
    for r in sel:
        by[(r["case"], r["arm"], r["verifier"])].append(r)
    out = []
    for (cid, arm, ver), rs in sorted(by.items(), key=lambda kv: (int(kv[0][0].split("_")[1]), kv[0][1])):
        case, labels, n = cases[cid], cases[cid]["labels"], len(rs)
        is_rules = not is_ai(arm)
        preds = [{score.canon(c.get("location", ""), labels): c for c in r["pred"]} for r in rs]
        method = (names or {}).get((arm, ver)) or pretty_arm(arm)
        key_canon = set()

        def add(loc, tier, kind, expected, old, new, canon_key):
            hits = sum(canon_key in P for P in preds)
            if expected:
                outcome = "Found" if hits == n else "Missed" if hits == 0 else "Inconsistent"
            else:
                outcome = "Correctly ignored" if hits == 0 else "Wrongly flagged" if hits == n else "Inconsistent"
            right = outcome in ("Found", "Correctly ignored")
            mark = {"Found": OK_MARK, "Correctly ignored": OK_MARK, "Missed": MISS_MARK,
                    "Wrongly flagged": FALSE_MARK, "Inconsistent": MIX_MARK}[outcome]
            label = f"{mark} {outcome}" + (f" ({hits} of {n} attempts)" if n > 1 and outcome == "Inconsistent" else "")
            said = next((P[canon_key].get("description", "") for P in preds if canon_key in P and P[canon_key].get("description")), "")
            out.append({"Case": f"Case {cid.split('_')[1]}", "Where": _where(case, loc),
                        "Difficulty": TIER_SHORT.get(tier, tier) if tier else "—",
                        "Original wording": old, "Renewal wording": new, "Method": method, "Result": label,
                        "Why": _explain_outcome(kind, outcome, tier, is_rules), "What the method said": said,
                        "_case": cid, "_loc": loc, "_right": right, "_outcome": outcome, "_method": method})
        for e in case["key"]:
            c = score.canon(e["location"], labels)
            key_canon.add(c)
            add(e["location"], e["tier"], "cosmetic" if not e["expected"] else "real", e["expected"], e["old"], e["new"], c)
        seen = {}
        for P in preds:
            for c, item in P.items():
                if c not in key_canon:
                    seen.setdefault(c, item.get("location", ""))
        for c, loc in seen.items():
            add(loc, None, "extra", False, "—", "—", c)
    return out


# ------------------------------------------------------------------ side-by-side


def side_by_side(rows, case, probe, methods, run_id=0, every=False, detail=False, only_issues=False):
    """Table of golden standard vs each method. `methods` = [(arm, verifier, display_name)].
    Returns (DataFrame-ready list of row dicts, method column titles)."""
    labels = case["labels"]
    key_items = [(e, score.canon(e["location"], labels)) for e in case["key"]]
    key_canon = {c for _, c in key_items}
    cols = {}
    for arm, ver, nm in methods:
        cand = [r for r in rows if r["case"] == case["id"] and r["probe"] == probe and r["arm"] == arm and r["verifier"] == ver]
        if not cand:
            continue
        rn = run_id if run_id in {r["run"] for r in cand} else min(r["run"] for r in cand)
        chain = sorted([r for r in cand if r["run"] == rn], key=lambda r: r["level"])
        for r in (chain if every else chain[-1:]):
            title = nm if len(chain) == 1 else (
                f"{nm} · {'first answer' if r['level'] == 0 else 'after check ' + str(r['level'])}" if every else f"{nm} (final)")
            P = {score.canon(c.get("location", ""), labels): c.get("description", "") for c in r["pred"]}
            L = {score.canon(c.get("location", ""), labels): c.get("location", "") for c in r["pred"]}
            cols[title] = (P, L, r)

    def cell(hit, expected, c, P):
        if expected:
            txt = f"{OK_MARK} Found" if hit else f"{MISS_MARK} Missed"
        else:
            txt = f"{FALSE_MARK} Wrongly flagged" if hit else f"{OK_MARK} Correctly ignored"
        return txt + (f" — {P[c]}" if detail and hit and P.get(c) else "")

    table = []
    for e, c in key_items:
        row = {"Item": e["location"],
               "What should happen": (f"Should be flagged ({TIER_SHORT.get(e['tier'], e['tier'])})" if e["expected"]
                                      else "Should be ignored (wording or format only)"),
               "What actually changed": f"{e['old']} → {e['new']}"}
        for t, (P, L, r) in cols.items():
            row[t] = cell(c in P, e["expected"], c, P)
        table.append(row)
    extras = {}
    for t, (P, L, r) in cols.items():
        for c, loc in L.items():
            if c not in key_canon:
                extras.setdefault(c, loc)
    for c, loc in extras.items():
        row = {"Item": loc, "What should happen": "Nothing: not a change in the answer key", "What actually changed": "—"}
        for t, (P, L, r) in cols.items():
            row[t] = f"{FALSE_MARK} Wrongly flagged" + (f" — {P[c]}" if detail and P.get(c) else "") if c in P else "—"
        table.append(row)
    if only_issues:
        table = [r for r in table if any(str(r[t]).startswith((MISS_MARK, FALSE_MARK)) for t in cols)]
    n_exp = sum(e["expected"] for e in case["key"])
    for lbl, fn in [("Real changes found", lambda s: f"{s['tp']} of {n_exp}"),
                    ("Wrongly flagged", lambda s: str(s["fp"])),
                    ("Overall score", lambda s: f"{round(100 * score.prf(s['tp'], s['fp'], s['fn'])[2])}%")]:
        row = {"Item": f"SCORE: {lbl}", "What should happen": f"{n_exp} real changes", "What actually changed": ""}
        for t, (P, L, r) in cols.items():
            row[t] = fn(r["s"])
        table.append(row)
    return table, list(cols)
