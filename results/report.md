# Results

44 scored outputs over 3 test cases (of 20 available).

## 1. Accuracy (pooled TP/FP/FN over all cases and runs)

| arm | verifier | probe | passes | precision | recall | F1 | cosmetic false-alarm rate | structured recall | lexical recall | semantic recall | added/removed recall | cases x runs | tokens/chain |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A_rules | - | authority | 0 | 1.000 | 0.750 | 0.857 | 0.000 | 1.00 | 1.00 | 0.00 | 1.00 | 1 | 0 |
| A_rules | - | none | 0 | 1.000 | 0.750 | 0.857 | 0.000 | 1.00 | 1.00 | 0.00 | 1.00 | 3 | 0 |
| B_llm @ claude-sonnet-5-5 | cross:claude-opus-5-5 | none | 0 | 1.000 | 1.000 | 1.000 | 0.000 | 1.00 | 1.00 | 1.00 | 1.00 | 6 | 3735 |
| B_llm @ claude-sonnet-5-5 | cross:claude-opus-5-5 | none | 1 | 1.000 | 1.000 | 1.000 | 0.000 | 1.00 | 1.00 | 1.00 | 1.00 | 6 | 8617 |
| B_llm @ claude-sonnet-5-5 | cross:claude-opus-5-5 | none | 2 | 1.000 | 1.000 | 1.000 | 0.000 | 1.00 | 1.00 | 1.00 | 1.00 | 6 | 13486 |
| B_llm @ claude-sonnet-5-5 | cross:claude-opus-5-5 | none | 3 | 1.000 | 1.000 | 1.000 | 0.000 | 1.00 | 1.00 | 1.00 | 1.00 | 6 | 18394 |
| E_hybrid @ claude-sonnet-5-5 | cross:claude-opus-5-5 | none | 0 | 1.000 | 1.000 | 1.000 | 0.000 | 1.00 | 1.00 | 1.00 | 1.00 | 4 | 1684 |
| E_hybrid @ claude-sonnet-5-5 | cross:claude-opus-5-5 | none | 1 | 1.000 | 1.000 | 1.000 | 0.000 | 1.00 | 1.00 | 1.00 | 1.00 | 4 | 7111 |
| E_hybrid @ claude-sonnet-5-5 | cross:claude-opus-5-5 | none | 2 | 1.000 | 1.000 | 1.000 | 0.000 | 1.00 | 1.00 | 1.00 | 1.00 | 4 | 12556 |
| E_hybrid @ claude-sonnet-5-5 | cross:claude-opus-5-5 | none | 3 | 1.000 | 1.000 | 1.000 | 0.000 | 1.00 | 1.00 | 1.00 | 1.00 | 4 | 17977 |

## 2. F1 difference vs deterministic ruleset A (probe=none, paired bootstrap over cases, 95% CI)

| arm | verifier | passes | mean dF1 | 95% CI | verdict |
|---|---|---|---|---|---|
| B_llm @ claude-sonnet-5-5 | cross:claude-opus-5-5 | 0 | +0.145 | [+0.125, +0.167] | AI better |
| B_llm @ claude-sonnet-5-5 | cross:claude-opus-5-5 | 1 | +0.145 | [+0.125, +0.167] | AI better |
| B_llm @ claude-sonnet-5-5 | cross:claude-opus-5-5 | 2 | +0.145 | [+0.125, +0.167] | AI better |
| B_llm @ claude-sonnet-5-5 | cross:claude-opus-5-5 | 3 | +0.145 | [+0.125, +0.167] | AI better |
| E_hybrid @ claude-sonnet-5-5 | cross:claude-opus-5-5 | 0 | +0.134 | [+0.125, +0.143] | AI better |
| E_hybrid @ claude-sonnet-5-5 | cross:claude-opus-5-5 | 1 | +0.134 | [+0.125, +0.143] | AI better |
| E_hybrid @ claude-sonnet-5-5 | cross:claude-opus-5-5 | 2 | +0.134 | [+0.125, +0.143] | AI better |
| E_hybrid @ claude-sonnet-5-5 | cross:claude-opus-5-5 | 3 | +0.134 | [+0.125, +0.143] | AI better |

## 3. Run-to-run consistency (mean pairwise Jaccard of flagged locations; 1.0 = identical every run)

| arm | verifier | probe | passes | consistency |
|---|---|---|---|---|
| B_llm @ claude-sonnet-5-5 | cross:claude-opus-5-5 | none | 0 | 1.000 |
| B_llm @ claude-sonnet-5-5 | cross:claude-opus-5-5 | none | 1 | 1.000 |
| B_llm @ claude-sonnet-5-5 | cross:claude-opus-5-5 | none | 2 | 1.000 |
| B_llm @ claude-sonnet-5-5 | cross:claude-opus-5-5 | none | 3 | 1.000 |
| E_hybrid @ claude-sonnet-5-5 | cross:claude-opus-5-5 | none | 0 | 1.000 |
| E_hybrid @ claude-sonnet-5-5 | cross:claude-opus-5-5 | none | 1 | 1.000 |
| E_hybrid @ claude-sonnet-5-5 | cross:claude-opus-5-5 | none | 2 | 1.000 |
| E_hybrid @ claude-sonnet-5-5 | cross:claude-opus-5-5 | none | 3 | 1.000 |

## 4. Bias probes: change vs probe=none (same arm / verifier / passes)

`flip rate` = share of (case, run) whose flagged set differs from the same run under probe=none. Compare with the `baseline flip` (run i vs run j under none) to separate bias from sampling noise.

| arm | verifier | passes | probe | flip rate | baseline flip | dRecall | dFP rate |
|---|---|---|---|---|---|---|---|
| A_rules | - | 0 | authority | 0.000 | nan | +0.000 | +0.00 |

## 5. Verification effect per extra AI check pass (mean per case-run)

| arm | verifier | probe | pass | true positives gained | true positives lost | false positives added | false positives removed |
|---|---|---|---|---|---|---|---|
| B_llm @ claude-sonnet-5-5 | cross:claude-opus-5-5 | none | 1 | 0.00 | 0.00 | 0.00 | 0.00 |
| B_llm @ claude-sonnet-5-5 | cross:claude-opus-5-5 | none | 2 | 0.00 | 0.00 | 0.00 | 0.00 |
| B_llm @ claude-sonnet-5-5 | cross:claude-opus-5-5 | none | 3 | 0.00 | 0.00 | 0.00 | 0.00 |
| E_hybrid @ claude-sonnet-5-5 | cross:claude-opus-5-5 | none | 1 | 0.00 | 0.00 | 0.00 | 0.00 |
| E_hybrid @ claude-sonnet-5-5 | cross:claude-opus-5-5 | none | 2 | 0.00 | 0.00 | 0.00 | 0.00 |
| E_hybrid @ claude-sonnet-5-5 | cross:claude-opus-5-5 | none | 3 | 0.00 | 0.00 | 0.00 | 0.00 |
