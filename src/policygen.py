"""Synthetic personal-auto policies (original wording, modeled on the structure of
public state-DOI / NAIC sample policies). Swap in real public policies later by
producing the same `spec` dict."""
import random
from datetime import date

FIELDS = [
    ("policy_number", "Policy Number"),
    ("named_insured", "Named Insured"),
    ("policy_period_start", "Policy Period Start"),
    ("policy_period_end", "Policy Period End"),
    ("continuous_since", "Continuous Coverage Since"),
    ("covered_vehicle", "Covered Vehicle"),
    ("bi_limit", "Bodily Injury Liability Limit"),
    ("pd_limit", "Property Damage Liability Limit"),
    ("um_limit", "Uninsured/Underinsured Motorist Limit"),
    ("medpay_limit", "Medical Payments Limit"),
    ("coll_ded", "Collision Deductible"),
    ("comp_ded", "Comprehensive Deductible"),
    ("rental", "Rental Reimbursement"),
    ("premium", "Total Policy Premium"),
]
LABEL = dict(FIELDS)
MONEY_KEYS = ["bi_limit", "pd_limit", "um_limit", "medpay_limit", "coll_ded", "comp_ded", "rental"]
DATE_KEYS = ["policy_period_start", "policy_period_end", "continuous_since"]

NAMES = ["Jordan A. Wells", "Priya Nair", "Marcus T. Hale", "Elena Ruiz", "Samuel O. Baker", "Mei Lin Chou"]
VEHICLES = ["2021 Honda Civic LX", "2019 Toyota Camry SE", "2022 Ford Escape SE", "2018 Subaru Outback",
            "2020 Chevrolet Equinox LT", "2023 Hyundai Elantra SEL", "2017 Nissan Altima SV"]
BI = [(25000, 50000), (50000, 100000), (100000, 300000), (250000, 500000)]
PD = [25000, 50000, 100000]
MED = [1000, 2500, 5000, 10000]
COLL = [250, 500, 1000, 2000]
COMP = [100, 250, 500, 1000]
RENT = [(30, 900), (40, 1200), (50, 1500)]


def _vin(rng):
    chars = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"
    return "".join(rng.choice(chars) for _ in range(17))


def make_spec(seed):
    rng = random.Random(seed)
    year = rng.choice([2025, 2026])
    start = date(year, rng.randint(1, 12), rng.randint(1, 28))
    end = date(start.year + 1, start.month, start.day)
    fields = {
        "policy_number": f"PA-{rng.randint(100000, 999999)}",
        "named_insured": rng.choice(NAMES),
        "policy_period_start": start,
        "policy_period_end": end,
        "continuous_since": date(rng.randint(2008, 2022), rng.randint(1, 12), rng.randint(1, 28)),
        "covered_vehicle": f"{rng.choice(VEHICLES)}, VIN {_vin(rng)}",
        "bi_limit": rng.choice(BI),
        "pd_limit": rng.choice(PD),
        "um_limit": rng.choice(BI),
        "medpay_limit": rng.choice(MED),
        "coll_ded": rng.choice(COLL),
        "comp_ded": rng.choice(COMP),
        "rental": rng.choice(RENT),
        "premium": round(rng.uniform(780, 2400), 2),
    }
    params = {
        "notice_days": rng.choice([14, 30, 60]),
        "wait_hours": rng.choice([24, 48]),
        "cancel_days": rng.choice([10, 20, 30]),
        "nonpay_days": rng.choice([10, 15]),
    }
    return {"fields": fields, "params": params}


def clause_library(P, rng):
    alt = lambda cur, opts: rng.choice([o for o in opts if o != cur])
    nd, wh, cd, npd = P["notice_days"], P["wait_hours"], P["cancel_days"], P["nonpay_days"]
    # cos = cosmetic (meaning-preserving) rewrites; mat = (old, new, tier) material rewrites.
    # tier "lexical": detectable via numbers / legal-modifier / peril lexicons.
    # tier "semantic": meaning changes with no lexical tell.
    return [
        dict(id="2.1", title="Liability Coverage",
             text="We will pay damages for bodily injury or property damage for which an insured is legally responsible because of an auto accident. We will settle or defend, as we consider appropriate, any claim or suit asking for these damages. Our duty to settle or defend ends when our limit of liability has been paid.",
             cos=[("is legally responsible", "is held legally liable"), ("asking for these damages", "seeking these damages")],
             mat=[("We will settle or defend, as we consider appropriate,", "We will settle, but have no duty to defend,", "lexical"),
                  ("has been paid", "has been offered", "semantic")]),
        dict(id="2.2", title="Liability Exclusions",
             text="We do not provide Liability Coverage for any person for bodily injury or property damage arising from the ownership or use of a vehicle while it is being used to carry persons or property for a fee. This does not apply to a share-the-expense car pool.",
             cos=[("arising from", "resulting from"), ("carry persons or property for a fee", "transport people or goods for compensation")],
             mat=[(" This does not apply to a share-the-expense car pool.", "", "lexical"),
                  ("ownership or use", "ownership, maintenance or use", "semantic")]),
        dict(id="2.3", title="Uninsured Motorist Coverage",
             text="We will pay compensatory damages which an insured is legally entitled to recover from the owner or operator of an uninsured motor vehicle because of bodily injury sustained by the insured, up to the limit shown in the Declarations.",
             cos=[("because of", "as a result of"), ("legally entitled to recover", "entitled by law to recover")],
             mat=[("uninsured motor vehicle because", "uninsured motor vehicle, other than a hit-and-run vehicle, because", "lexical"),
                  ("bodily injury sustained by the insured", "bodily injury sustained by the named insured", "semantic")]),
        dict(id="3.1", title="Duties After an Accident or Loss",
             text=f"A person seeking coverage must notify us promptly of an accident or loss, and in any event within {nd} days. The person must also cooperate with us in the investigation and settlement of any claim.",
             cos=[("promptly", "without delay"), ("cooperate with us", "assist us")],
             mat=[(f"within {nd} days", f"within {alt(nd, [14, 30, 60, 90])} days", "lexical"),
                  ("notify us promptly", "notify our agent promptly", "semantic")]),
        dict(id="3.2", title="Collision Coverage",
             text="We will pay for direct and accidental loss to your covered auto caused by collision, less the applicable deductible shown in the Declarations. Payment will not exceed the lesser of the actual cash value of the damaged property or the amount necessary to repair or replace it.",
             cos=[("less the applicable deductible", "minus the applicable deductible"), ("necessary to repair or replace it", "needed to repair or replace it")],
             mat=[("the lesser of", "the greater of", "lexical"),
                  ("caused by collision", "caused by collision with another vehicle", "semantic")]),
        dict(id="3.3", title="Comprehensive Coverage",
             text="We will pay for direct and accidental loss to your covered auto not caused by collision, including fire, theft, vandalism, flood, and contact with animals, less the applicable deductible shown in the Declarations.",
             cos=[("including", "such as"), ("less the applicable deductible", "minus the applicable deductible")],
             mat=[("vandalism, flood, and contact", "vandalism, and contact", "lexical"),
                  ("theft, vandalism", "theft of the entire vehicle, vandalism", "semantic")]),
        dict(id="3.4", title="Rental Reimbursement",
             text=f"If your covered auto is withdrawn from use for more than {wh} hours because of a covered loss, we will reimburse transportation expenses up to the daily and maximum amounts shown in the Declarations.",
             cos=[("withdrawn from use", "out of service"), ("we will reimburse", "we will repay")],
             mat=[(f"more than {wh} hours", f"more than {alt(wh, [24, 48, 72])} hours", "lexical"),
                  ("because of a covered loss", "because of a covered theft loss", "semantic")]),
        dict(id="4.1", title="Policy Territory",
             text="Coverage applies only to accidents and losses occurring within the United States, its territories and possessions, or Canada.",
             cos=[("occurring within", "that take place within")],
             mat=[("possessions, or Canada", "possessions", "lexical"),
                  ("losses occurring within", "losses occurring and reported within", "semantic")]),
        dict(id="4.2", title="Other Insurance",
             text="If there is other applicable insurance, we will pay only our share of the loss. Our share is the proportion that our limit bears to the total of all applicable limits. Any insurance we provide for a vehicle you do not own is excess over any other collectible insurance.",
             cos=[("If there is other applicable insurance", "Where other applicable insurance exists"), ("the proportion that", "the proportion which")],
             mat=[("is excess over", "is primary over", "lexical"),
                  ("a vehicle you do not own", "a vehicle you do not own or regularly use", "semantic")]),
        dict(id="5.1", title="Cancellation",
             text=f"You may cancel this policy at any time by notifying us. We may cancel by mailing notice to the named insured at the address shown in the Declarations at least {cd} days before the effective date of cancellation, or {npd} days if cancellation is for nonpayment of premium.",
             cos=[("by mailing notice to", "by sending written notice to"), ("effective date of cancellation", "date cancellation takes effect")],
             mat=[(f"at least {cd} days", f"at least {alt(cd, [10, 20, 30, 45])} days", "lexical"),
                  ("by notifying us", "by notifying us in writing", "semantic")]),
        dict(id="5.2", title="Fraud and Misrepresentation",
             text="We do not provide coverage for any insured who has knowingly concealed or misrepresented any material fact or circumstance in connection with this policy or a claim.",
             cos=[("in connection with", "relating to"), ("any material fact or circumstance", "any material fact or situation")],
             mat=[("knowingly concealed or misrepresented", "intentionally misrepresented", "lexical"),
                  ("in connection with this policy or a claim", "in connection with a claim", "semantic")]),
        dict(id="5.3", title="Changes to This Policy",
             text="This policy contains all the agreements between you and us. Its terms may be changed only by an endorsement issued by us.",
             cos=[("contains all the agreements", "contains the entire agreement"), ("Its terms", "The terms of this policy")],
             mat=[("only by an endorsement issued by us", "by an endorsement issued by us or by our agent", "lexical"),
                  ("between you and us", "between you, us and any lienholder", "semantic")]),
    ]


ADDED_CLAUSES = [
    ("6.1", "Ride-Sharing Endorsement", "We do not provide coverage under this policy while a covered auto is logged into a ride-sharing or delivery network."),
    ("6.1", "Diminished Value", "Payment for loss to your covered auto does not include compensation for diminished value after repair."),
    ("6.1", "Temporary Foreign Travel", "Coverage is extended to include temporary visits to Mexico of up to 10 days."),
]
REMOVABLE = ["2.2", "3.4", "4.2", "5.2"]

FILLER = [
    ("8.1", "Headings", "Headings in this policy are for convenience only and do not affect the meaning of any provision."),
    ("8.2", "Severability", "If any provision of this policy is found to be unenforceable, the remaining provisions stay in effect."),
    ("8.3", "Notices", "Notices to us under this policy must be sent to the address shown on your most recent billing statement."),
    ("8.4", "Transfer of Rights", "Your rights and duties under this policy may not be transferred without our written consent."),
    ("8.5", "Legal Action", "No legal action may be brought against us until there has been full compliance with all terms of this policy."),
    ("8.6", "Premium Payment", "Premium is due on the dates shown on your billing statement and may be paid in installments if offered."),
    ("8.7", "Policy Period", "This policy applies only to accidents and losses that occur during the policy period shown in the Declarations."),
    ("8.8", "Definitions", "Words in bold type have the meanings given in the Definitions section of this policy booklet."),
    ("8.9", "Subrogation", "If we make a payment, we are entitled to recover it from any person responsible for the loss."),
    ("8.10", "Joint and Individual Interests", "If there are two or more named insureds, any one of them may act for all in matters under this policy."),
]


def _money(n, cents):
    return f"${n:,}.00" if cents else f"${n:,}"


def fmt_field(key, val, style):
    c = style.get("cents", False)
    if key in ("policy_period_start", "policy_period_end", "continuous_since"):
        return f"{val:%B} {val.day}, {val.year}" if style.get("date") == "long" else f"{val:%m/%d/%Y}"
    if key == "named_insured":
        return val.upper() if style.get("upper") else val
    if key in ("bi_limit", "um_limit"):
        return f"{_money(val[0], c)} each person / {_money(val[1], c)} each accident"
    if key == "pd_limit":
        return f"{_money(val, c)} each accident"
    if key == "medpay_limit":
        return f"{_money(val, c)} each person"
    if key in ("coll_ded", "comp_ded"):
        return _money(val, c)
    if key == "rental":
        return f"{_money(val[0], c)} per day / {_money(val[1], c)} maximum"
    if key == "premium":
        return f"${val:,.2f}"
    return str(val)


def render(fields, clauses, style):
    out = ["PERSONAL AUTO POLICY - DECLARATIONS"]
    for key, label in FIELDS:
        out.append(f"{label}: {fmt_field(key, fields[key], style)}")
    out += ["", "POLICY TERMS", ""]
    for c in clauses:
        out += [f"SECTION {c['id']} - {c['title']}", c["text"], ""]
    return "\n".join(out).rstrip() + "\n"
