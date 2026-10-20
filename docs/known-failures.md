# Known failures and limitations (Phase 9, D-0126)

Each row is MEASURED unless labelled otherwise, with its evidence.

| # | Failure | Evidence | Mitigation | Residual |
|---|---|---|---|---|
| 1 | Below the speed targets: 4.1–5.1 tok/s (target 8); TTFT ~30 s (target 3) | phase7 Q4 verdict | none possible in software on this CPU; accepted (D-0116) | permanent on this hardware |
| 2 | Prose arithmetic errors when no tool is used (CAGR 20 % vs 10 %; under brevity rules P/E 17.85, CAGR 10.5 %, 125 vs 250 shares) | D-0122, D-0125 | tools for every calculation; prompt style rules dropped (D-0126) | calc 100 % on the tool path; prose still unreliable |
| 3 | Correct abstention 88.89 % (target 90); 1 fabricated figure | phase7 Q4 verdict | refusal-language rule, execution guard, min-trust 80 | 1–2 rows per arm |
| 4 | Citation correctness 90.48 % (target 95); unsupported claims 7.69 % (target 3) | phase7 Q4 citations | strict per-claim verifier; UNSUPPORTED never passes | correct values restated without a scale word stay unconfirmable |
| 5 | 6 of 74 replies cut off at 512 tokens | phase7 Q4 merged | `--continue-budget 256` | **effect unmeasured** (PHASE8_CONFIRM_RUN_FA.md) |
| 6 | LaTeX in formulas (8 of 74 replies) | D-0123 | `--display` rewrite (0 left, 0 correctness changes) | the model still writes it; only the display is fixed |
| 7 | Mixed language (1 Persian reply in English sentences) | D-0123 | detected by `latin_runs` | not rewritten |
| 8 | Runtime-dependent replies: Ollama 2/74 and LM Studio 7/21 identical to in-process | D-0125 | measure the runtime you deploy | INFERRED decoder/build difference |
| 9 | Ollama peak RAM 6762 MB (over the 6.0 GiB cap if MiB) | user Task Manager, D-0125 | in-process runtime recommended | — |
| 10 | Interactive `ollama run` shows a thinking block | user smoke test, D-0124 | `--think=false` | — |
| 11 | No licensed real-time market data; no verified broker | registries, D-0126 | END_OF_DAY data only; paper simulator | live trading unreachable |
| 12 | Persian fluency regression threshold unmeasured | grade_merged | human review (D-0123) | automatic metric absent |
