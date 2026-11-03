"""Builds (policy A, policy B, answer key) cases. The key is exact by construction."""
import argparse, copy, json, random
from datetime import timedelta
from . import config, policygen as pg


def _change_structured(key, fields, rng):
    v = fields[key]
    if key == "bi_limit": fields[key] = rng.choice([o for o in pg.BI if o != v])
    elif key == "um_limit": fields[key] = rng.choice([o for o in pg.BI if o != v])
    elif key == "pd_limit": fields[key] = rng.choice([o for o in pg.PD if o != v])
    elif key == "medpay_limit": fields[key] = rng.choice([o for o in pg.MED if o != v])
    elif key == "coll_ded": fields[key] = rng.choice([o for o in pg.COLL if o != v])
    elif key == "comp_ded": fields[key] = rng.choice([o for o in pg.COMP if o != v])
    elif key == "rental": fields[key] = rng.choice([o for o in pg.RENT if o != v])
    elif key == "premium": fields[key] = round(v * (1 + rng.choice([-1, 1]) * rng.uniform(0.05, 0.15)), 2)
    elif key == "policy_period_end": fields[key] = v + timedelta(days=rng.choice([-60, -30, 30, 60]))
    elif key == "continuous_since": fields[key] = v.replace(year=v.year + rng.choice([-2, -1, 1, 2]))
    elif key == "covered_vehicle":
        fields[key] = f"{rng.choice([x for x in pg.VEHICLES if x not in v])}, VIN {pg._vin(rng)}"
    elif key == "named_insured": fields[key] = v + " and " + rng.choice(["Casey Wells", "Alex Rivera", "Dana Brooks"])
    else: raise ValueError(key)


STRUCT_KEYS = ["bi_limit", "um_limit", "pd_limit", "medpay_limit", "coll_ded", "comp_ded", "rental",
               "premium", "policy_period_end", "continuous_since", "covered_vehicle", "named_insured"]
COSMETIC_STYLES = {
    "dates": ({"date": "long"}, pg.DATE_KEYS),
    "cents": ({"cents": True}, pg.MONEY_KEYS),
    "upper": ({"upper": True}, ["named_insured"]),
}


def build_case(seed, split):
    rng = random.Random(seed * 7919 + 13)
    spec = pg.make_spec(seed)
    A_fields = spec["fields"]
    clauses_a = pg.clause_library(spec["params"], rng)
    B_fields = copy.deepcopy(A_fields)
    clauses_b = copy.deepcopy(clauses_a)
    key = []

    # structured changes
    for k in rng.sample(STRUCT_KEYS, rng.randint(3, 4)):
        old = pg.fmt_field(k, B_fields[k], {})
        _change_structured(k, B_fields, rng)
        key.append(dict(location=pg.LABEL[k], kind="structured", tier="structured", expected=True,
                        old=old, new=pg.fmt_field(k, B_fields[k], {})))

    # material clause rewrites + cosmetic rewrites on disjoint clauses
    idxs = list(range(len(clauses_b)))
    rng.shuffle(idxs)
    n_mat, n_cos = rng.randint(3, 4), rng.randint(2, 3)
    removed = None
    if rng.random() < 0.4:
        removed = rng.choice([c for c in pg.REMOVABLE])
        idxs = [i for i in idxs if clauses_b[i]["id"] != removed]
    for i in idxs[:n_mat]:
        c = clauses_b[i]
        old, new, tier = rng.choice(c["mat"])
        assert old in c["text"], (c["id"], old)
        c["text"] = c["text"].replace(old, new, 1)
        key.append(dict(location=c["id"], kind="clause_material", tier=tier, expected=True, old=old, new=new))
    for i in idxs[n_mat:n_mat + n_cos]:
        c = clauses_b[i]
        old, new = rng.choice(c["cos"])
        assert old in c["text"], (c["id"], old)
        c["text"] = c["text"].replace(old, new, 1)
        key.append(dict(location=c["id"], kind="cosmetic", tier="cosmetic", expected=False, old=old, new=new))
    if removed:
        clauses_b = [c for c in clauses_b if c["id"] != removed]
        key.append(dict(location=removed, kind="clause_removed", tier="removed", expected=True, old="(clause)", new="(deleted)"))
    elif rng.random() < 0.4:
        cid, title, text = rng.choice(pg.ADDED_CLAUSES)
        clauses_b.append(dict(id=cid, title=title, text=text))
        key.append(dict(location=cid, kind="clause_added", tier="added", expected=True, old="(none)", new=title))

    # cosmetic formatting-only change on declarations
    style_b = {}
    if rng.random() < 0.8:
        name = rng.choice(list(COSMETIC_STYLES))
        style_b, locs = COSMETIC_STYLES[name]
        for k in locs:
            key.append(dict(location=pg.LABEL[k], kind="cosmetic", tier="cosmetic", expected=False,
                            old="(format)", new=f"({name} format)"))
    # a real change overrides a cosmetic note on the same location
    real = {e["location"] for e in key if e["expected"]}
    key = [e for e in key if e["expected"] or e["location"] not in real]

    return dict(id=f"{split}_{seed}", split=split, seed=seed,
                text_a=pg.render(A_fields, clauses_a, {}),
                text_b=pg.render(B_fields, clauses_b, style_b),
                labels=[l for _, l in pg.FIELDS], key=key)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=config.N_TEST_CASES)
    ap.add_argument("--train", type=int, default=config.N_TRAIN_CASES)
    a = ap.parse_args()
    config.CASES.mkdir(parents=True, exist_ok=True)
    pass  # cases are overwritten in place (same seeds => same files)
    for s in range(a.n):
        c = build_case(s, "test"); (config.CASES / f"{c['id']}.json").write_text(json.dumps(c, indent=1))
    for s in range(a.train):
        c = build_case(1000 + s, "train"); (config.CASES / f"{c['id']}.json").write_text(json.dumps(c, indent=1))
    print(f"wrote {a.n} test + {a.train} train cases to {config.CASES}")


if __name__ == "__main__":
    main()
