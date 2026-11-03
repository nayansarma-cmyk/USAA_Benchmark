"""Complex / edge-case policy cases (case set "usaa_hard"). Answer keys are exact by construction.

What makes these harder than the original synthetic cases
  * SEMANTIC edits with no lexical tell: the meaning flips (and/or, before/after, who decides, per accident vs per person,
    operator vs occupant ...) without changing any number or any word in the rules' legal lexicon. Verified automatically:
    every semantic edit is checked to be invisible to the lexical signature, and `tier` is computed from actual behaviour.
  * COSMETIC TRAPS: same-meaning rewrites that DO change a lexicon word ("may" -> "can", "pay" -> "make payment for",
    "must" -> "is required to"), so naive keyword rules raise false alarms. Clean cosmetic edits are mixed in too.
  * Structured edge cases: one-character VIN change, day/month swap, ~1% premium change, one half of a two-part limit.
  * Dense cases (10+ real edits), zero-change cases (only cosmetic edits; the right answer is "nothing"), added and removed clauses,
    and 26-section documents (long context).
Every key entry carries an `edge` tag so results can be sliced by the kind of difficulty.

    python -m src.hard_cases     # writes data/cases/test_3000.json ... test_3059.json
"""
import copy, json, random
from datetime import date
from . import config, policygen as pg, rules, mutate

CASE_SET = "usaa_hard"
N_CASES = 60
SEED0 = 3000

# id, title, text, sem=[(old, new, edge)], cos=[(old, new, edge)]   ("trap_*" cosmetic edits change a lexicon word on purpose)
HARD = [
    dict(id="7.1", title="Appraisal",
         text="If we and an insured disagree on the amount of a loss, either party may demand an appraisal. Each party selects a competent appraiser, and the two appraisers select an umpire. A decision agreed by any two of the three is binding on both parties.",
         sem=[("is binding on both parties", "is advisory to both parties", "binding_to_advisory"),
              ("either party may demand", "we alone may demand", "who_may_invoke")],
         cos=[("competent appraiser", "qualified appraiser", "clean_synonym"), ("either party may demand", "either party can demand", "trap_modal_synonym")]),
    dict(id="7.2", title="Loss Payment",
         text="We will pay covered losses within a reasonable time after we receive proof of loss and agree on the amount. Payment will be made to you and any lienholder named in the Declarations, as interests appear.",
         sem=[("proof of loss and agree on the amount", "proof of loss or agree on the amount", "conjunction_flip"),
              ("as interests appear", "as we determine", "who_decides_split")],
         cos=[("within a reasonable time", "within a reasonable period", "clean_synonym"), ("We will pay covered losses", "We will make payment for covered losses", "trap_synonym_pay")]),
    dict(id="7.3", title="Newly Acquired Vehicle",
         text="A vehicle you become the owner of during the policy period is covered if it replaces a covered auto, or if it is an additional vehicle and you ask us to insure it promptly after you acquire it. Coverage for an additional vehicle begins on the date you acquire it.",
         sem=[("replaces a covered auto, or if it is", "replaces a covered auto, and if it is", "or_to_and"),
              ("begins on the date you acquire it", "begins on the date you ask us to insure it", "trigger_date")],
         cos=[("ask us to insure it promptly", "request that we insure it promptly", "clean_synonym")]),
    dict(id="7.4", title="Cooperation and Examination",
         text="An insured must cooperate with us and submit to an examination under oath when we reasonably request it. The examination will take place at a location we reasonably choose.",
         sem=[("when we reasonably request it", "when the insured reasonably requests it", "who_requests"),
              ("at a location we reasonably choose", "at a location the insured reasonably chooses", "who_chooses")],
         cos=[("submit to an examination under oath", "undergo an examination under oath", "clean_synonym"), ("must cooperate", "is required to cooperate", "trap_modal_synonym")]),
    dict(id="7.5", title="Total Loss Settlement",
         text="If the cost to repair a covered auto exceeds its actual cash value, we may treat the loss as a total loss and pay the actual cash value less the deductible. We keep the salvage unless you retain the vehicle, in which case the salvage value is deducted.",
         sem=[("exceeds its actual cash value", "falls below its actual cash value", "threshold_direction"),
              ("less the deductible", "plus the deductible", "sign_flip")],
         cos=[("treat the loss as a total loss", "consider the loss a total loss", "clean_synonym"), ("pay the actual cash value", "settle for the actual cash value", "trap_synonym_pay")]),
    dict(id="7.6", title="Non-Owned Vehicles",
         text="Liability Coverage extends to your use of a non-owned auto that is not furnished or available for your regular use. It does not extend to a vehicle used in a business you operate.",
         sem=[("your use of a non-owned auto", "any person's use of a non-owned auto", "who_is_covered"),
              ("a vehicle used in a business you operate", "a vehicle used in any business", "exclusion_widened")],
         cos=[("It does not extend to", "It does not apply to", "clean_synonym"), ("is not furnished or available", "is neither furnished nor available", "trap_negation_form")]),
    dict(id="7.7", title="Custom Equipment",
         text="We cover custom parts and equipment permanently installed in your covered auto up to the amount shown in the Declarations. You must be able to document the installation date and original cost.",
         sem=[("permanently installed", "temporarily installed", "permanence_flip"),
              ("up to the amount shown in the Declarations", "up to the original cost of the equipment", "limit_basis")],
         cos=[("document the installation date and original cost", "provide records of the installation date and original cost", "clean_synonym"),
              ("You must be able to", "You are required to be able to", "trap_modal_synonym")]),
    dict(id="7.8", title="Rental Vehicle Class",
         text="Rental reimbursement applies to a rental vehicle of comparable class to your covered auto. If a comparable vehicle is not available locally, we pay for the closest available class.",
         sem=[("of comparable class to your covered auto", "of the economy class regardless of your covered auto", "class_basis"),
              ("the closest available class", "the lowest available class", "class_fallback")],
         cos=[("available locally", "available in your area", "clean_synonym"), ("we pay for", "we cover the cost of", "trap_synonym_pay")]),
    dict(id="7.9", title="Transport Between Ports",
         text="Coverage also applies while a covered auto is transported between ports of the places listed in the Policy Territory section, provided the transport is arranged by you or by a carrier you hire.",
         sem=[("arranged by you or by a carrier you hire", "arranged by a carrier we select", "arranger"),
              ("between ports of the places", "between any ports", "scope_widened")],
         cos=[("is transported", "is carried", "clean_synonym"), ("provided the transport", "as long as the transport", "clean_synonym")]),
    dict(id="7.10", title="Medical Payments Eligibility",
         text="Medical expenses are covered for an insured who is injured while occupying a covered auto. Expenses must be incurred within the period shown in the Declarations and must be reasonable and necessary.",
         sem=[("while occupying a covered auto", "while operating a covered auto", "occupant_vs_operator"),
              ("reasonable and necessary", "reasonable or necessary", "and_or")],
         cos=[("are covered for", "are payable for", "clean_synonym"), ("must be reasonable and necessary", "need to be reasonable and necessary", "trap_modal_synonym")]),
    dict(id="7.11", title="Uninsured Motorist Property Damage",
         text="We pay for damage to your covered auto caused by an uninsured motorist, after the deductible shown in the Declarations is applied. The at-fault motorist must be identified.",
         sem=[("after the deductible shown in the Declarations is applied", "without the deductible shown in the Declarations being applied", "deductible_waived"),
              ("caused by an uninsured motorist", "caused by an underinsured motorist", "uninsured_vs_under")],
         cos=[("at-fault motorist", "responsible motorist", "clean_synonym"), ("We pay for damage", "We provide payment for damage", "trap_synonym_pay")]),
    dict(id="7.12", title="Subrogation Detail",
         text="If we make a payment under this policy, we may recover it from any person or organization responsible for the loss. An insured must do nothing after a loss to impair these rights and must help us enforce them.",
         sem=[("responsible for the loss", "solely responsible for the loss", "solely_responsible"),
              ("must do nothing after a loss", "must do nothing before a loss", "temporal_scope")],
         cos=[("we may recover it from", "we may recoup it from", "clean_synonym"), ("must help us enforce them", "is required to help us enforce them", "trap_modal_synonym")]),
    dict(id="7.13", title="Notice Delivery",
         text="Notice of cancellation or non-renewal is delivered when mailed to the address shown in the Declarations. Proof of mailing is sufficient proof of notice.",
         sem=[("when mailed to", "when received at", "delivery_event"),
              ("is sufficient proof of notice", "is merely evidence of notice", "proof_standard")],
         cos=[("shown in the Declarations", "listed in the Declarations", "clean_synonym")]),
    dict(id="7.14", title="Limit Aggregation",
         text="The limit of liability shown in the Declarations is the most we will pay for all damages resulting from any one accident, regardless of the number of insureds, claims made, or vehicles involved.",
         sem=[("any one accident", "any one person", "per_accident_vs_person"),
              ("regardless of the number of insureds, claims made, or vehicles involved", "regardless of the number of insureds or claims made", "aggregation_scope")],
         cos=[("resulting from", "arising out of", "clean_synonym"), ("is the most we will pay", "is the highest amount we will pay", "trap_synonym_most")]),
]
HARD_ADDED = [
    ("7.20", "Delivery Use Endorsement", "Coverage under this policy does not apply while a covered auto is used to deliver goods for compensation."),
    ("7.21", "Named Driver Restriction", "Coverage applies only while a covered auto is driven by a driver listed in the Declarations."),
    ("7.22", "Rental Class Cap", "Rental reimbursement is limited to the economy class regardless of the class of your covered auto."),
]
REMOVABLE = ["2.2", "3.4", "4.2", "5.2", "7.6", "7.9", "7.13"]


def _sig(t):
    t = " ".join(t.lower().split())
    return rules._numbers(t), tuple(rules._count(w, t) for w in rules.LEGAL_LEXICON)


def selfcheck():
    """Fail loudly if the library does not behave as documented (so a typo cannot silently mislabel a tier)."""
    for h in HARD:
        for old, new, edge in h["sem"]:
            assert old in h["text"], (h["id"], old)
            assert _sig(h["text"]) == _sig(h["text"].replace(old, new, 1)), f"semantic edit is not lexically blind: {h['id']} {edge}"
        for old, new, edge in h["cos"]:
            assert old in h["text"], (h["id"], old)
            same = _sig(h["text"]) == _sig(h["text"].replace(old, new, 1))
            assert same != edge.startswith("trap_"), f"cosmetic edit '{edge}' in {h['id']} should {'change' if edge.startswith('trap_') else 'not change'} the lexical signature"
    return True


def _struct_edit(key, fields, rng):
    """Structured edits, including edge cases. Returns (edge tag) or None if the edit isn't possible."""
    v = fields[key]
    if key == "covered_vehicle" and rng.random() < .5:                       # one-character VIN change
        head, vin = v.rsplit("VIN ", 1)
        i = rng.randrange(len(vin)); alt = rng.choice([c for c in "ABCDEFGHJKLMNPRSTUVWXYZ0123456789" if c != vin[i]])
        fields[key] = head + "VIN " + vin[:i] + alt + vin[i + 1:]
        return "vin_one_char"
    if key == "policy_period_start":                                          # day/month swap
        if v.day <= 12 and v.day != v.month:
            fields[key] = date(v.year, v.day, v.month); return "date_day_month_swap"
        return None
    if key == "premium":
        fields[key] = round(v * (1 + rng.choice([-1, 1]) * rng.uniform(0.008, 0.02)), 2); return "premium_small_change"
    if key == "bi_limit" and rng.random() < .6:                               # only the second half of a two-part limit
        fields[key] = (v[0], int(v[1] * 1.5)); return "limit_half_changed"
    mutate._change_structured(key, fields, rng)
    return "structured"


STRUCT_KEYS = ["bi_limit", "um_limit", "pd_limit", "medpay_limit", "coll_ded", "comp_ded", "rental", "premium", "policy_period_start",
               "policy_period_end", "continuous_since", "covered_vehicle", "named_insured"]


def build_case(seed, kind="normal"):
    rng = random.Random(seed * 104729 + 7)
    spec = pg.make_spec(seed)
    A, B = spec["fields"], copy.deepcopy(spec["fields"])
    std = pg.clause_library(spec["params"], rng)
    hard = sorted(rng.sample(HARD, rng.randint(9, 12)), key=lambda h: float(h["id"]))
    clauses_a = std + [dict(id=h["id"], title=h["title"], text=h["text"]) for h in hard]
    clauses_b = copy.deepcopy(clauses_a)
    cb = {c["id"]: c for c in clauses_b}
    H = {h["id"]: h for h in hard}
    S = {c["id"]: c for c in std}
    n = dict(normal=(rng.randint(2, 3), rng.randint(1, 2), rng.randint(3, 4), rng.randint(3, 5)),
             zero=(0, 0, 0, rng.randint(5, 8)), dense=(rng.randint(4, 5), rng.randint(3, 4), rng.randint(4, 5), rng.randint(2, 3)))[kind]
    n_struct, n_std_mat, n_hard_sem, n_cos = n
    key, used = [], set()

    for k in rng.sample(STRUCT_KEYS, len(STRUCT_KEYS)):                        # structured edits
        if len([e for e in key if e["kind"] == "structured"]) >= n_struct:
            break
        old = pg.fmt_field(k, B[k], {})
        edge = _struct_edit(k, B, rng)
        if edge is None or pg.fmt_field(k, B[k], {}) == old:
            continue
        key.append(dict(location=pg.LABEL[k], kind="structured", tier="structured", expected=True, old=old, new=pg.fmt_field(k, B[k], {}), edge=edge))

    std_ids, hard_ids = rng.sample(list(S), len(S)), rng.sample(list(H), len(H))
    for sid in std_ids[:n_std_mat]:                                            # standard material edits (tier computed later)
        old, new, _ = rng.choice(S[sid]["mat"])
        assert old in cb[sid]["text"]
        cb[sid]["text"] = cb[sid]["text"].replace(old, new, 1); used.add(sid)
        key.append(dict(location=sid, kind="clause_material", tier=None, expected=True, old=old, new=new, edge="standard_edit"))
    for hid in hard_ids[:n_hard_sem]:                                          # hard semantic edits
        old, new, edge = rng.choice(H[hid]["sem"])
        cb[hid]["text"] = cb[hid]["text"].replace(old, new, 1); used.add(hid)
        key.append(dict(location=hid, kind="clause_material", tier=None, expected=True, old=old, new=new, edge=edge))

    pool = [i for i in std_ids[n_std_mat:] if i not in used] + [i for i in hard_ids[n_hard_sem:] if i not in used]
    rng.shuffle(pool)
    removed = None
    if kind != "zero" and rng.random() < .4:                                   # removed clause
        cand = [i for i in pool if i in REMOVABLE]
        if cand:
            removed = cand[0]; pool.remove(removed)
    for cid in pool:                                                           # cosmetic edits (clean + traps)
        if len([e for e in key if e["kind"] == "cosmetic"]) >= n_cos:
            break
        opts = [(o, nw, ed) for o, nw, ed in ([(a, b, "clean_synonym") for a, b in S[cid]["cos"]] if cid in S else H[cid]["cos"])]
        old, new, edge = rng.choice(opts)
        assert old in cb[cid]["text"]
        cb[cid]["text"] = cb[cid]["text"].replace(old, new, 1)
        key.append(dict(location=cid, kind="cosmetic", tier="cosmetic", expected=False, old=old, new=new, edge=edge))
    if removed:
        clauses_b = [c for c in clauses_b if c["id"] != removed]
        key.append(dict(location=removed, kind="clause_removed", tier="removed", expected=True, old="(clause)", new="(deleted)", edge="clause_removed"))
    elif kind != "zero" and rng.random() < .4:
        cid, title, text = rng.choice(HARD_ADDED)
        clauses_b.append(dict(id=cid, title=title, text=text))
        key.append(dict(location=cid, kind="clause_added", tier="added", expected=True, old="(none)", new=title, edge="clause_added_restriction"))

    style_b = {}
    if rng.random() < .5:                                                      # formatting-only change on Declarations
        name = rng.choice(list(mutate.COSMETIC_STYLES))
        style_b, locs = mutate.COSMETIC_STYLES[name]
        real = {e["location"] for e in key if e["expected"]}
        for lk in locs:
            if pg.LABEL[lk] not in real:
                key.append(dict(location=pg.LABEL[lk], kind="cosmetic", tier="cosmetic", expected=False, old="(format)", new=f"({name} format)", edge="format_only"))

    text_a, text_b = pg.render(A, clauses_a, {}), pg.render(B, clauses_b, style_b)
    flagged = {m["location"] for m in rules.diff(text_a, text_b)["material"]}
    for e in key:                                                              # tiers from actual behaviour, frozen here
        if e["kind"] == "clause_material":
            e["tier"] = "lexical" if e["location"] in flagged else "semantic"
        if e["kind"] == "cosmetic":
            e["rules_false_alarm"] = e["location"] in flagged
    return dict(id=f"test_{seed}", split="test", set=CASE_SET, seed=seed, kind=kind, text_a=text_a, text_b=text_b,
                labels=[l for _, l in pg.FIELDS], key=key)


def kind_of(i):
    return "zero" if i % 12 == 11 else "dense" if i % 12 == 5 else "normal"


def main():
    selfcheck()
    for i in range(N_CASES):
        c = build_case(SEED0 + i, kind_of(i))
        (config.CASES / f"{c['id']}.json").write_text(json.dumps(c, indent=1), encoding="utf-8")
    print(f"wrote {N_CASES} cases ({SEED0}-{SEED0 + N_CASES - 1}) -> {config.CASES}")


if __name__ == "__main__":
    main()
