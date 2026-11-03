"""Deterministic if-then ruleset (Arm A). THIS IS YOUR FILE: edit/extend it, then
FREEZE it (commit/hash it) before looking at any results, so the baseline is fair.

Rules
 R1  Declarations: normalise dates / currency / case, then flag any field whose value differs.
 R2  Clauses: a section present in only one version is a material add/remove.
 R3  Clauses: after whitespace/case normalisation, if text differs, flag MATERIAL when
     (a) the multiset of numbers differs, or
     (b) the count of any term in LEGAL_LEXICON differs (modals, negations, exclusion /
         priority words, covered perils, geography).
     Otherwise the change is recorded as non-material (rewording).
"""
import re
from datetime import datetime

LEGAL_LEXICON = [
    # modals / obligation
    "must", "may", "shall", "will", "duty", "unless", "only", "except", "excluding", "other than",
    # negation / exclusion
    "not", "no", "exclude", "excludes", "excluded", "exclusion",
    # intent / knowledge
    "knowingly", "intentionally", "willfully",
    # priority / limits
    "excess", "primary", "lesser", "greater", "least", "most", "maximum", "minimum",
    # perils
    "fire", "theft", "vandalism", "flood", "animals", "hail", "windstorm", "glass",
    # geography
    "canada", "mexico", "united states", "territories", "possessions",
    # actions
    "defend", "settle", "cancel", "reimburse", "pay",
]

RULEBOOK = """1. For the Declarations, compare every field. Ignore differences that are only date format, currency formatting (e.g. $500 vs $500.00) or letter case. Any other difference is a material change.
2. A policy section that exists in only one version is a material change (added or removed).
3. For each policy section present in both versions, ignore pure rewording. Flag the section as a material change if ANY of these differ: (a) any number (days, hours, dollars, limits); (b) words of obligation or permission (must, may, shall, will, duty, unless, only, except, other than); (c) negations or exclusions (not, no, exclude/excluded); (d) knowledge/intent words (knowingly, intentionally); (e) priority or limit words (excess, primary, lesser, greater, least, maximum); (f) covered perils (fire, theft, vandalism, flood, animals, hail, windstorm, glass); (g) geography (United States, Canada, Mexico, territories, possessions)."""

HDR = re.compile(r"^SECTION\s+(\d+\.\d+)\s+-\s+(.+)$", re.I)
MONEY = re.compile(r"\$\s?([\d,]+(?:\.\d+)?)")


def _norm_value(v):
    v = " ".join(v.split()).strip()
    for fmt in ("%m/%d/%Y", "%B %d, %Y"):
        try:
            return datetime.strptime(v, fmt).date().isoformat()
        except ValueError:
            pass
    v = MONEY.sub(lambda m: "$" + str(float(m.group(1).replace(",", ""))), v)
    return v.lower()


def parse(text):
    fields, clauses, cur, mode = {}, {}, None, "decl"
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        m = HDR.match(s)
        if m:
            mode, cur = "terms", m.group(1)
            clauses[cur] = [m.group(2).strip(), ""]
        elif mode == "decl" and ":" in s and not s.isupper():
            k, v = s.split(":", 1)
            if k.strip().isupper():  # banner/note lines (e.g. "COMPLIANCE NOTE:"), not Title-Case field labels
                continue
            fields[k.strip()] = v.strip()
        elif mode == "terms" and cur and not s.isupper():
            clauses[cur][1] += (" " if clauses[cur][1] else "") + s
    return fields, clauses


def _count(term, text):
    return len(re.findall(r"\b" + re.escape(term) + r"\b", text))


def _numbers(text):
    return sorted(re.findall(r"\d+(?:\.\d+)?", text.replace(",", "")))


def diff(text_a, text_b):
    fa, ca = parse(text_a)
    fb, cb = parse(text_b)
    mat, non = [], []
    for k in list(dict.fromkeys(list(fa) + list(fb))):
        va, vb = fa.get(k), fb.get(k)
        if va is None or vb is None or _norm_value(va) != _norm_value(vb):
            mat.append(dict(location=k, change_type="structured", description=f"{k} changed", old=va, new=vb))
        elif va != vb:
            non.append(dict(location=k, change_type="structured", description="format only", old=va, new=vb))
    for sid in sorted(set(ca) | set(cb)):
        if sid not in ca or sid not in cb:
            mat.append(dict(location=sid, change_type="clause", description="section added" if sid in cb else "section removed",
                            old=None, new=None))
            continue
        ta, tb = " ".join(ca[sid][1].lower().split()), " ".join(cb[sid][1].lower().split())
        if ta == tb:
            continue
        reasons = []
        if _numbers(ta) != _numbers(tb):
            reasons.append("numbers differ")
        for term in LEGAL_LEXICON:
            if _count(term, ta) != _count(term, tb):
                reasons.append(f"'{term}' count differs")
        item = dict(location=sid, change_type="clause", description="; ".join(reasons) or "rewording only",
                    old=ca[sid][1], new=cb[sid][1])
        (mat if reasons else non).append(item)
    return dict(material=mat, non_material=non)
