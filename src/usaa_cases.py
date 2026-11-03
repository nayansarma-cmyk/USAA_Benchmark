"""Turns the placeholder cases in USAA_benchmark_cases_100.json into scoreable cases with real policy text.

Each source case lists 5 edits (policy number, a coverage limit, an exclusion, a claims-notice period, a
wording-only change). We write a full policy (same Declarations + numbered-section format as the other cases),
put the OLD wording in the original and the NEW wording in the renewal, and re-point each answer-key entry at its real
location. Source fields are preserved (source_location / source_tier / note) so nothing is lost.

    python -m src.usaa_cases           # writes data/cases/test_2000.json ... test_2099.json
"""
import copy, json, random, re
from . import config, policygen as pg, rules

SRC = config.CASES / "USAA_benchmark_cases_100.json"
CASE_SET = "usaa_100"

# source location -> (real location in the document, forced tier or None = work it out)
LOCATION_MAP = {
    "Declarations": ("Policy Number", "structured"),
    "Coverage Limits": ("Property Damage Liability Limit", "structured"),
    "Exclusions": ("2.2", None),
    "Claims Notice": ("3.1", None),
    "Wording": ("3.4", "cosmetic"),
}


def _money(s):
    return int(re.sub(r"[^\d]", "", s))


def build(src):
    seed = src["seed"]
    rng = random.Random(seed * 7919 + 13)
    spec = pg.make_spec(seed)
    A, B = copy.deepcopy(spec["fields"]), copy.deepcopy(spec["fields"])
    k = {e["location"]: e for e in src["key"]}

    A["policy_number"], B["policy_number"] = k["Declarations"]["old"], k["Declarations"]["new"]
    A["pd_limit"], B["pd_limit"] = _money(k["Coverage Limits"]["old"]), _money(k["Coverage Limits"]["new"])

    clauses = {c["id"]: c for c in pg.clause_library(spec["params"], rng)}
    clauses["2.2"]["text"] = ("Liability Coverage is limited for any vehicle used to carry persons or property for a fee. "
                              f"For purposes of this section: {k['Exclusions']['old']}.")
    clauses["3.1"]["text"] = ("A person seeking coverage must cooperate with us in the investigation and settlement of any claim. "
                              f"In every case the insured must {k['Claims Notice']['old']} of the accident or loss.")
    clauses_a = list(clauses.values())
    clauses_b = copy.deepcopy(clauses_a)
    cb = {c["id"]: c for c in clauses_b}
    for loc, sid in (("Exclusions", "2.2"), ("Claims Notice", "3.1"), ("Wording", "3.4")):
        e = k[loc]
        assert e["old"] in cb[sid]["text"], (src["id"], loc)
        cb[sid]["text"] = cb[sid]["text"].replace(e["old"], e["new"], 1)

    text_a, text_b = pg.render(A, clauses_a, {}), pg.render(B, clauses_b, {})
    material_sections = {m["location"] for m in rules.diff(text_a, text_b)["material"] if m["change_type"] == "clause"}

    key = []
    for e in src["key"]:
        loc, forced = LOCATION_MAP[e["location"]]
        tier = forced or ("lexical" if loc in material_sections else "semantic")
        assert e["old"] in text_a and e["new"] in text_b, (src["id"], e["location"])
        rec = dict(location=loc, kind=e["kind"], tier=tier, expected=e["expected"], old=e["old"], new=e["new"],
                   source_location=e["location"], source_tier=e["tier"])
        if "$comment" in e:
            rec["note"] = e["$comment"]
        key.append(rec)
    return dict(id=f"test_{seed}", split="test", set=CASE_SET, seed=seed, source_id=src["id"], domain=src.get("domain"),
                description=src.get("description"), text_a=text_a, text_b=text_b,
                labels=[l for _, l in pg.FIELDS], key=key)


def main():
    cases = json.load(open(SRC, encoding="utf-8"))
    for src in cases:
        c = build(src)
        (config.CASES / f"{c['id']}.json").write_text(json.dumps(c, indent=1), encoding="utf-8")
    print(f"wrote {len(cases)} cases -> {config.CASES}")


if __name__ == "__main__":
    main()
