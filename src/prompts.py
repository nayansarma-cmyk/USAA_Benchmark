import json
from .rules import RULEBOOK

TASK = """You are reviewing two versions of a personal auto insurance policy: the ORIGINAL term and the RENEWAL term.
List every MATERIAL change between them. A change is material if it alters coverage, limits, deductibles, premium, dates, vehicles, insureds, conditions, exclusions, duties or obligations.
NOT material: rewording that keeps the same meaning, date or currency formatting, letter case, whitespace, or ordering of lines/sections.
Use the exact Declarations field label as the location for Declarations changes, and the section number (e.g. 3.1) for policy-term changes.
Respond with ONLY JSON:
{"changes":[{"location":"<field label or section number>","change_type":"structured|clause","description":"...","old":"...","new":"..."}]}
If there are no material changes return {"changes":[]}."""


def docs(a, b, swap=False):
    o, r = f"<ORIGINAL>\n{a}</ORIGINAL>", f"<RENEWAL>\n{b}</RENEWAL>"
    return r + "\n\n" + o if swap else o + "\n\n" + r


def judge(a, b, swap, with_rules):
    sys = TASK
    if with_rules:
        sys += "\n\nApply this review ruleset when deciding what is material:\n" + RULEBOOK
    return sys, "[[TASK:judge]]\n" + docs(a, b, swap)


def verify(a, b, swap, proposed):
    sys = TASK + "\n\nYou are now a VERIFIER. You are given a proposed list of material changes. Check every item against the documents, remove incorrect items (including non-material rewording), add any material changes that were missed, and return the full corrected list in the same JSON format."
    return sys, "[[TASK:verify]]\n" + docs(a, b, swap) + "\n\n<PROPOSED>\n" + json.dumps({"changes": proposed}, indent=1) + "\n</PROPOSED>"


def clause_review(items):
    sys = ("You are reviewing wording changes between two versions of an auto policy section. For each section decide whether the "
           "change is MATERIAL (alters coverage, conditions, exclusions, duties or obligations) or merely rewording with the same meaning. "
           'Respond with ONLY JSON: {"results":[{"location":"<section number>","material":true|false,"description":"..."}]}')
    body = "\n".join(f'<SECTION id="{i["location"]}">\nOLD: {i["old"]}\nNEW: {i["new"]}\n</SECTION>' for i in items)
    return sys, "[[TASK:clause_review]]\n" + body


def rulegen(a, b):
    sys = ("You write deterministic Python rules for comparing two versions of a personal auto policy and flagging MATERIAL changes "
           "(coverage, limits, deductibles, premium, dates, vehicles, insureds, conditions, exclusions, duties). Rewording with the same "
           "meaning, formatting, case and ordering must NOT be flagged.")
    user = ("[[TASK:rulegen]]\nWrite a single Python 3 file (standard library only, no file/network/process access) defining:\n"
            "def detect_changes(text_a: str, text_b: str) -> list[dict]\n"
            "returning dicts with keys location (exact Declarations field label, or section number like '3.1'), change_type ('structured' or 'clause'), description.\n"
            "It must generalise to other policies in the same format, not just this example. Return ONLY the code in one ```python block.\n\n"
            "Example pair (for format only; no answer is provided):\n" + docs(a, b))
    return sys, user
