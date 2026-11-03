import json, re, subprocess, sys
from pathlib import Path
from . import config, prompts, rules
from .llm import parse_json

SANDBOX = str(Path(__file__).with_name("sandbox_runner.py"))


def _changes(text):
    ch = parse_json(text).get("changes", [])
    return [c for c in ch if isinstance(c, dict) and "location" in c]


def _verify_chain(llm, a, b, swap, initial, nonce, verifier_model, passes, usage):
    """Yield (level, changes). level 0 = initial answer; 1..passes = after each verifier pass."""
    cur = initial
    yield 0, cur
    for k in range(1, passes + 1):
        s, u = prompts.verify(a, b, swap, cur)
        r = llm.complete(verifier_model, s, u, f"{nonce}|v{k}")
        usage.append(r)
        new = _changes(r["text"])
        cur = new if parse_json(r["text"]) else cur  # keep prior answer if output unparseable
        yield k, cur


def rules_arm(a, b, **kw):
    yield 0, rules.diff(a, b)["material"]


def judge_arm(with_rules):
    def run(llm, a, b, swap, nonce, verifier_model, passes, usage, judge_model=None, **kw):
        s, u = prompts.judge(a, b, swap, with_rules)
        r = llm.complete(judge_model or config.JUDGE_MODEL, s, u, nonce)
        usage.append(r)
        yield from _verify_chain(llm, a, b, swap, _changes(r["text"]), nonce, verifier_model, passes, usage)
    return run


def hybrid_arm(llm, a, b, swap, nonce, verifier_model, passes, usage, judge_model=None, **kw):
    """Rules do structured fields + added/removed sections; the LLM only decides materiality of changed clauses."""
    d = rules.diff(a, b)
    keep = [m for m in d["material"] if m["change_type"] == "structured" or m["description"].startswith("section ")]
    changed = [m for m in d["material"] + d["non_material"] if m["change_type"] == "clause" and m["old"] is not None]
    if changed:
        s, u = prompts.clause_review(changed)
        r = llm.complete(judge_model or config.JUDGE_MODEL, s, u, nonce)
        usage.append(r)
        res ={x.get("location"): x for x in parse_json(r["text"]).get("results", []) if isinstance(x, dict)}
        for m in changed:
            if res.get(m["location"], {}).get("material"):
                keep.append(m)
    yield from _verify_chain(llm, a, b, swap, keep, nonce, verifier_model, passes, usage)


def gen_rules_arm(i):
    def run(a, b, **kw):
        p = config.GEN_RULES / f"rules_{i}.py"
        if not p.exists():
            return
        try:
            r = subprocess.run([sys.executable, "-I", SANDBOX, str(p)], input=json.dumps(dict(text_a=a, text_b=b)),
                               capture_output=True, text=True, timeout=20)
            out = json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else []
        except Exception:
            out = []
        yield 0, out
    return run


def generate_rules(llm, train_a, train_b):
    config.GEN_RULES.mkdir(parents=True, exist_ok=True)
    for i in range(1, config.GEN_RULE_SAMPLES + 1):
        s, u = prompts.rulegen(train_a, train_b)
        r = llm.complete(config.RULEWRITER_MODEL, s, u, nonce=f"rulegen{i}")
        m = re.search(r"```python\n(.*?)```", r["text"], re.S)
        (config.GEN_RULES / f"rules_{i}.py").write_text(m.group(1) if m else r["text"])
    print(f"wrote {config.GEN_RULE_SAMPLES} LLM-written rulesets to {config.GEN_RULES}")


# name -> (fn, is_llm)
ARMS = {
    "A_rules": (rules_arm, False),
    "B_llm": (judge_arm(False), True),
    "C_llm_plus_rules": (judge_arm(True), True),
    "E_hybrid": (hybrid_arm, True),
}
for _i in range(1, config.GEN_RULE_SAMPLES + 1):
    ARMS[f"D{_i}_llm_written_rules"] = (gen_rules_arm(_i), False)
