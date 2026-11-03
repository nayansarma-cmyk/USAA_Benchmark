# policy-diff-bench: deterministic rules vs. LLM-as-judge on auto-policy change detection

Extends *Justice or Prejudice? (CALM)* to an insurance task. Question: can an LLM identify
material policy changes better than a deterministic if-then ruleset, and how stable is it?

## Fairness note (read before running)
The goal is to *test* whether AI beats rules, so the design deliberately gives rules a fair shot:
- `src/rules.py` is a good-faith ruleset (normalises dates/currency/case, number diffs, legal lexicon).
  **Edit it to be as good as you can, then freeze it (commit/hash) before any real run.**
- Answer keys come from a mutation script, not from hand-checking or another LLM.
- Each material change has a tier: `structured`, `lexical` (numbers / legal-modifier words), or
  `semantic` (meaning changes with no lexical tell). Expect rules ~100% on the first two; the claim
  "AI is better" lives or dies on the `semantic` tier and on cosmetic false alarms. Report it that way.
- A hybrid arm (E) is included because the likely honest result is "rules for structure, AI for meaning".

## Arms
| Arm | What it is |
|---|---|
| A_rules | Your deterministic ruleset |
| B_llm | LLM sees both versions, asked what changed |
| C_llm_plus_rules | LLM sees both versions + your ruleset as instructions |
| D1-D3_llm_written_rules | LLM writes the rules (from one unlabeled training pair), frozen, executed as code on the test set |
| E_hybrid | Rules do structured fields + added/removed sections; LLM only judges changed clauses |

LLM arms (B, C, E) each get a verification chain: level 0 = first answer, levels 1-3 = after each extra AI check
pass. Every level is logged, so you can see whether more checking helps or hurts.
`--verifier cross` uses a different model to check (default); `--verifier same` tests self-enhancement.

## Bias probes (from CALM)
`swap` (document order), `authority` (fake compliance sign-off), `bandwagon` (fake prior reviewers),
`padding` (long identical boilerplate in both; verbosity/dilution), `distraction` (reordered/reflowed/uppercased B).

## Run in the browser (localhost UI)
```
pip install -r requirements.txt
streamlit run app.py        # opens http://localhost:8501
```
Pick methods, one or more Claude models (or type any model ID), bias tests and case count, press **Start benchmark**,
then read **Scores** and **Process breakdown**. "Demo mode" runs offline with the fake LLM; turn it off and provide
`ANTHROPIC_API_KEY` (env var or sidebar) for real runs. CLI equivalent:
`python -m src.run --judge-models claude-sonnet-5-5,claude-haiku-5-5 --verifier-model claude-opus-5-5`.
Integrity checks for the harness itself: `python -m tests.test_pipeline`.

## Run (command line)
```
pip install -r requirements.txt
set ANTHROPIC_API_KEY=...            (PowerShell: $env:ANTHROPIC_API_KEY="...")
python -m src.mutate --n 20          # cases + exact answer keys -> data/cases
python -m src.run --mock --cases 3   # offline smoke test, no API calls
python -m src.run --gen-rules        # LLM writes rulesets D1-D3
python -m src.run --probes none --runs 3 --cases 5      # small real pilot
python -m src.run --probes none,swap,authority,bandwagon,padding,distraction --runs 5
python -m src.run --probes none --runs 5 --verifier same   # self-enhancement comparison
python -m src.score                  # -> results/report.md
```
Models: set `JUDGE_MODEL`, `VERIFIER_MODEL`, `RULEWRITER_MODEL` env vars (defaults in `src/config.py`).
Runs are cached and resumable. Cost scales as cases x probes x runs x (1 + 3 verifier calls) per LLM arm;
pilot small first.

## Report sections
1 accuracy (precision/recall/F1, per-tier recall, cosmetic false-alarm rate, tokens), 2 paired-bootstrap F1
difference vs rules with 95% CI, 3 run-to-run consistency, 4 probe flip rates vs baseline noise,
5 verification effect per pass (fixed vs broken answers).

## Caveats
- Policies are synthetic (original wording, public-sample structure). To use real state-DOI/NAIC sample
  policies, add a loader that emits the same `A/B text + key` format; keep the injected-mutation approach.
- `D*` arms execute LLM-generated code (via `python -I` subprocess, 20s timeout). Run inside a container/VM.
- `--mock` numbers are meaningless (fake LLM); they only prove the pipeline runs.
- Review and validate results before sharing outside the team.
