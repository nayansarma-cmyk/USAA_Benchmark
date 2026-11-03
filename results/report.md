# Results

216 scored outputs over 11 test cases (of 180 available).

## 1. Accuracy (pooled TP/FP/FN over all cases and runs)

| arm | verifier | probe | passes | precision | recall | F1 | cosmetic false-alarm rate | structured recall | lexical recall | semantic recall | added/removed recall | cases x runs | tokens/chain |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A_rules | - | authority | 0 | 1.000 | 0.750 | 0.857 | 0.000 | 1.00 | 1.00 | 0.00 | 1.00 | 1 | 0 |
| A_rules | - | none | 0 | 0.984 | 0.768 | 0.863 | 0.018 | 1.00 | 1.00 | 0.05 | 1.00 | 11 | 0 |
| B_llm @ claude-sonnet-5-5 | cross:claude-opus-5-5 | none | 0 | 0.978 | 1.000 | 0.989 | 0.031 | 1.00 | 1.00 | 1.00 | 1.00 | 30 | 3699 |
| B_llm @ claude-sonnet-5-5 | cross:claude-opus-5-5 | none | 1 | 0.996 | 1.000 | 0.998 | 0.006 | 1.00 | 1.00 | 1.00 | 1.00 | 30 | 8510 |
| B_llm @ claude-sonnet-5-5 | cross:claude-opus-5-5 | none | 2 | 1.000 | 1.000 | 1.000 | 0.000 | 1.00 | 1.00 | 1.00 | 1.00 | 6 | 13486 |
| B_llm @ claude-sonnet-5-5 | cross:claude-opus-5-5 | none | 3 | 1.000 | 1.000 | 1.000 | 0.000 | 1.00 | 1.00 | 1.00 | 1.00 | 6 | 18394 |
| C_llm_plus_rules @ claude-sonnet-5-5 | cross:claude-opus-5-5 | none | 0 | 0.983 | 1.000 | 0.991 | 0.025 | 1.00 | 1.00 | 1.00 | 1.00 | 30 | 4239 |
| C_llm_plus_rules @ claude-sonnet-5-5 | cross:claude-opus-5-5 | none | 1 | 0.996 | 1.000 | 0.998 | 0.006 | 1.00 | 1.00 | 1.00 | 1.00 | 30 | 9084 |
| E_hybrid @ claude-sonnet-5-5 | cross:claude-opus-5-5 | none | 0 | 0.962 | 1.000 | 0.980 | 0.057 | 1.00 | 1.00 | 1.00 | 1.00 | 30 | 1582 |
| E_hybrid @ claude-sonnet-5-5 | cross:claude-opus-5-5 | none | 1 | 1.000 | 1.000 | 1.000 | 0.000 | 1.00 | 1.00 | 1.00 | 1.00 | 30 | 6973 |
| E_hybrid @ claude-sonnet-5-5 | cross:claude-opus-5-5 | none | 2 | 1.000 | 1.000 | 1.000 | 0.000 | 1.00 | 1.00 | 1.00 | 1.00 | 6 | 12366 |
| E_hybrid @ claude-sonnet-5-5 | cross:claude-opus-5-5 | none | 3 | 1.000 | 1.000 | 1.000 | 0.000 | 1.00 | 1.00 | 1.00 | 1.00 | 6 | 17758 |

## 2. F1 difference vs deterministic ruleset A (probe=none, paired bootstrap over cases, 95% CI)

| arm | verifier | passes | mean dF1 | 95% CI | verdict |
|---|---|---|---|---|---|
| B_llm @ claude-sonnet-5-5 | cross:claude-opus-5-5 | 0 | +0.130 | [+0.089, +0.180] | AI better |
| B_llm @ claude-sonnet-5-5 | cross:claude-opus-5-5 | 1 | +0.138 | [+0.106, +0.184] | AI better |
| B_llm @ claude-sonnet-5-5 | cross:claude-opus-5-5 | 2 | +0.145 | [+0.125, +0.167] | AI better |
| B_llm @ claude-sonnet-5-5 | cross:claude-opus-5-5 | 3 | +0.145 | [+0.125, +0.167] | AI better |
| C_llm_plus_rules @ claude-sonnet-5-5 | cross:claude-opus-5-5 | 0 | +0.131 | [+0.087, +0.186] | AI better |
| C_llm_plus_rules @ claude-sonnet-5-5 | cross:claude-opus-5-5 | 1 | +0.138 | [+0.106, +0.184] | AI better |
| E_hybrid @ claude-sonnet-5-5 | cross:claude-opus-5-5 | 0 | +0.121 | [+0.082, +0.163] | AI better |
| E_hybrid @ claude-sonnet-5-5 | cross:claude-opus-5-5 | 1 | +0.141 | [+0.106, +0.192] | AI better |
| E_hybrid @ claude-sonnet-5-5 | cross:claude-opus-5-5 | 2 | +0.145 | [+0.125, +0.167] | AI better |
| E_hybrid @ claude-sonnet-5-5 | cross:claude-opus-5-5 | 3 | +0.145 | [+0.125, +0.167] | AI better |

## 3. Run-to-run consistency (mean pairwise Jaccard of flagged locations; 1.0 = identical every run)

| arm | verifier | probe | passes | consistency |
|---|---|---|---|---|
| B_llm @ claude-sonnet-5-5 | cross:claude-opus-5-5 | none | 0 | 0.984 |
| B_llm @ claude-sonnet-5-5 | cross:claude-opus-5-5 | none | 1 | 0.990 |
| B_llm @ claude-sonnet-5-5 | cross:claude-opus-5-5 | none | 2 | 1.000 |
| B_llm @ claude-sonnet-5-5 | cross:claude-opus-5-5 | none | 3 | 1.000 |
| C_llm_plus_rules @ claude-sonnet-5-5 | cross:claude-opus-5-5 | none | 0 | 0.982 |
| C_llm_plus_rules @ claude-sonnet-5-5 | cross:claude-opus-5-5 | none | 1 | 0.990 |
| E_hybrid @ claude-sonnet-5-5 | cross:claude-opus-5-5 | none | 0 | 0.978 |
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
| B_llm @ claude-sonnet-5-5 | cross:claude-opus-5-5 | none | 1 | 0.00 | 0.00 | 0.00 | 0.13 |
| B_llm @ claude-sonnet-5-5 | cross:claude-opus-5-5 | none | 2 | 0.00 | 0.00 | 0.00 | 0.00 |
| B_llm @ claude-sonnet-5-5 | cross:claude-opus-5-5 | none | 3 | 0.00 | 0.00 | 0.00 | 0.00 |
| C_llm_plus_rules @ claude-sonnet-5-5 | cross:claude-opus-5-5 | none | 1 | 0.00 | 0.00 | 0.03 | 0.13 |
| E_hybrid @ claude-sonnet-5-5 | cross:claude-opus-5-5 | none | 1 | 0.00 | 0.00 | 0.00 | 0.30 |
| E_hybrid @ claude-sonnet-5-5 | cross:claude-opus-5-5 | none | 2 | 0.00 | 0.00 | 0.00 | 0.00 |
| E_hybrid @ claude-sonnet-5-5 | cross:claude-opus-5-5 | none | 3 | 0.00 | 0.00 | 0.00 | 0.00 |
