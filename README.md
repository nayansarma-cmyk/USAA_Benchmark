# policy-diff-bench: deterministic rules vs. LLM-as-judge on auto-policy change detection

Extends *Justice or Prejudice? (CALM)* to an insurance task. Question: how does an LLM compare with a
deterministic if-then ruleset at identifying material policy changes, and how stable is it? The study has no
assumed winner; the aim is to see where each approach is strong or weak.

## Fairness note (read before running)
The design deliberately gives rules a fair shot, so the comparison is honest in either direction:
- `src/rules.py` is a good-faith ruleset (normalises dates/currency/case, number diffs, legal lexicon).
  **Edit it to be as good as you can, then freeze it (commit/hash) before any real run.**
- Answer keys come from a mutation script, not from hand-checking or another LLM.
- Each material change has a tier: `structured`, `lexical` (numbers / legal-modifier words), or
  `semantic` (meaning changes with no lexical tell). Rules are expected to do well on the first two, so
  the tiers and the cosmetic false-alarm rate are where methods are most likely to differ. Report results per tier.
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

## Two tasks, one neutral comparison
The study has no assumed winner: it measures where each approach is strong or weak.

**1. Policy change detection** (`src/run.py`). Three case sets, never pooled in results:
| Set | Cases | What it is |
|---|---|---|
| synthetic | 20 | Original generated cases |
| usaa_100 | `test_2000`-`test_2099` | Built by `python -m src.usaa_cases` from `USAA_benchmark_cases_100.json` (source labels kept in `source_location` / `source_tier`). The source's "semantic" items (an exclusion wording, a 30 to 10 day notice) are *lexical* by this harness's definition, so rules score ~100% recall on them; the real tier is in `tier`. |
| usaa_hard | `test_3000`-`test_3059` | `python -m src.hard_cases`. 26-section documents; meaning-only edits with no keyword or number change (verified automatically); cosmetic traps that change a keyword but not the meaning; one-character VIN changes, day/month swaps, ~1% premium changes; dense cases (up to 14 real edits); zero-change cases. Every key entry has an `edge` tag. |

Note: in `usaa_hard`, keyword rules score 0% on the semantic tier *by definition* (no lexical tell). Compare methods per tier and per edge case, not on the pooled score.

**2. Customer-query routing** (`src/routing.py`, `src/convos.py`): send each customer message to the right department.
- *Single messages* (192, `python -m src.routing --gen`) and *multi-turn conversations* (134 conversations, 350 customer turns, up to 6 per
  conversation, `python -m src.convos`) with follow-ups, clarifying questions, topic switches, corrections that use a misleading keyword,
  escalation, fraud pivots, returns to an earlier topic, and attempts to steer the router. 132 turns only make sense with the conversation.
- Methods: keyword rules; keyword rules with topic memory; AI router (sees the conversation); AI router (latest message only); hybrid.
- Metrics: accuracy overall / by type / by department, turns that need context, whole-conversation success, urgent requests dropped into
  General inquiries, consistency, speed and tokens. Gold labels come from the generators.
- **Do not load real customer messages without the Data Privacy Officer.** The rules and templates share an author, so rules likely score higher
  here than on independent or real traffic; add independently written messages before concluding.

## Run in the browser (localhost UI)
```
pip install -r requirements.txt
streamlit run app.py        # opens http://localhost:8501
```
The **Review table** tab lists every item in every case for every method (case, where in the policy, original vs renewal
wording, result, and why), filterable to mistakes only; click a row to see the actual policy text.
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
