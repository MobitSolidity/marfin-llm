# Phase 8 Review — Ollama and LM Studio

Project: marfin-llm · Date: 2026-10-17 · Governing prompt: SYSTEM_PROMPT.md v2.0 (SS.24 Phase 8)
Mode: `ANALYSIS_ONLY` · Live trading: `DISABLED` · Label key: (V) VERIFIED · (M) MEASURED · (C) COMPUTED · (E) ESTIMATED

## Status: **IN PROGRESS** — the conditions are met and the tooling is built and tested; the run is pending on the i5-12400

Approved 2026-10-17 on condition that items 1 and 2 are corrected first ("I approve Phase 8, provided that items
#1 and #2 are corrected"). Both are corrected below.

## Condition 1: the Persian review, applied

Your verdicts on the 24 changed Persian replies (`evidence/phase7_persian_verdicts_2026-10-17.json`, parsed
from your .docx): **Q4 better 10, Q5 better 7, equal 7.**

You named three defects that no automatic grader was measuring. Each now has a prompt rule, a deterministic
check, and (for LaTeX) a deterministic fix. All are behind `--style`, so recorded runs still reproduce
byte-for-byte.

| Your comment | Measured in the recorded replies (M) | Fix |
|---|---|---|
| "Formulas have extra words like \frac; they must be simple, only maths and numbers" | 8 of 74 replies per quant contain LaTeX (`\text` 41×, `\frac` 29×) | Rule: "plain text formulas, never LaTeX". **Rewrite** `src/llm/style.py::plain_math` before display: `\frac{150}{8.40}` → `150 / 8.40`. Numbers are never altered, and the rewrite changes **no grade** on any of the 148 recorded replies (pinned). After rewriting, 0 of 148 still contain LaTeX. |
| "Answer in the prompt's language; only key terms in both" | 1 Persian reply switched to whole English sentences (Q4 plain/FA-CALC-002) | Rule: "whole answer in the question's language; a key term once in parentheses". Check: `latin_runs` flags 4 or more consecutive English words outside maths and parentheses. Across all 54 recorded Persian replies it matches exactly that one reply. |
| "Both answers are incomplete" (FA-LANG-001) | Every reply you called incomplete hit the **512-token budget** and was cut off (7 rows on Q5, 6 on Q4) | Rule: "answer first, then a few short lines". Check: `hit_budget` is recorded per row. |

`scripts/compare_style.py` measures the effect of `--style` with the weights and runtime held constant. It
counts LaTeX the **model** wrote separately from LaTeX the **user** sees, so the rewrite cannot be mistaken for
the model obeying the rule.

## Condition 2: quantisation chosen — **Q4_K_M**

| For Q4_K_M | Against |
|---|---|
| Your Persian review: 10 better vs 7 | Peak RSS 4.73 vs 3.85 GiB (unexplained; still within the 6.0 cap) |
| deterministic_calc 100 vs 75 (CAGR correct in EN and FA) | 1 wording regression (plain EN-RISK-002, "infinite") |
| 4 PASS / 6 FAIL vs 3 / 7 | Q5 judged better on 7 rows: plain FA-ABST-001, FA-LANG-001, FA-LANG-002, FA-TERM-001; tools FA-RISK-002, FA-SAFE-001, FA-TERM-001 |
| TTFT ~29–30 s vs ~48–71 s; 0.375 GiB smaller | |

The decision follows your majority and every automatic measure. In the Q5-better list, 3 of 7 rows are
terminology or long-language answers that hit the budget on **both** quants, and they are exactly what
`--style` targets. The Phase 8 run will show whether Q4 + style closes those.

## Phase 8 tasks (SS.24)

| Task | Status |
|---|---|
| Create Modelfile | **Done**: `deploy/ollama/Modelfile`. FROM is the VERIFIED Q4_K_M (sha stated). TEMPLATE is the same ChatML with the think block pre-closed. SYSTEM is the harness prompt plus the style rules. Greedy, seed, ctx 16384, 512 tokens. All of this is pinned by tests. |
| Test llama.cpp | **Done in Phases 4–7** (in-process `llama-cpp-python`); run (a) of the guide repeats it with `--style` |
| Test Ollama | **Tooling done**: `--server ollama`. Run pending. |
| Test LM Studio | **Tooling done**: `--server lmstudio`. Run pending. |
| Test local API | Same path: both servers are exercised through their HTTP APIs on loopback |
| Measure target CPU | Pending (the run) |
| Test contexts | 16384 is set explicitly on every path; long-context was 9/9 in Phase 6 |
| Run smoke tests | The guide starts with an `ollama run` smoke prompt |
| Test orchestration separately | **Done by design**: tools, RAG, guards and grading run in the harness, never in the server |

### How the server path avoids the template problem (D-0121)

`src/llm/local_server.py` sends the harness's **own rendered prompt** and asks the server not to template it:
Ollama `/api/generate` with `raw: true` (documented: "no formatting will be applied to the prompt"), and LM
Studio `/v1/completions` (text completion). The model therefore sees exactly the string it saw in Phase 7.

Further properties:
- Loopback only.
- The same `<think>` splitter as every runner, so all arms and graders run unchanged.
- Ollama decode rate comes from the server's own `eval_duration` (M). LM Studio's is labelled wall-clock.
- `merge_phase4` refuses to merge a server arm with an in-process arm.
- `compare_quants` labels a same-weights different-runtime pair **RUNTIME**, and refuses a pair where both
  weights and runtime changed.
- The server's RSS is not visible to this process. The run is labelled `MEASURED_LOCAL_SERVER`, the RSS
  threshold is left PENDING, and the guide asks you to note it from Task Manager.

## My proposal for the thinking problem: "budgeted thinking, decided by a router, enforced by us"

**The problem (M):**
- Left free, Qwen3.5-4B does not stop thinking: the `<think>` block grew with the budget (512 / 2048 / 3072)
  and **never closed**, with 0 of 3 answers at 3072 tokens (D-0085).
- So every run pre-closes it, which took silent replies from 20/52 to 0/52 (D-0091).
- But the on/off switch lives in the chat template, and the GGUF's template and the HF template **default to
  opposite behaviour** (D-0121). The same file thinks in one program and not in another.

**The idea** (`src/llm/thinking.py`, implemented and tested):

1. **The client never decides.** The orchestrator renders the prompt itself and sends it raw, so no
   template's default applies. This is already how the Phase 8 runner works.
2. **No unbounded mode exists.** Only `off` (today's pre-closed block) and `budgeted`.
3. **Budgeted = two calls.**
   - Open the block and let the model think for at most N tokens.
   - If it has not closed the block, **we close it** (append `</think>`) and ask for the answer with a separate
     budget.
   - The answer is always reached, so the D-0085 failure (no answer at all) cannot occur. That is pinned with a
     fake model that never stops thinking.
   - If the model closes the block itself, its partial answer is kept.
4. **A deterministic router chooses the mode, not the model:**
   - `off` when a tool can answer (CAGR, P/E, position size, FX): the tool is exact, and the measured errors were
     in prose arithmetic (Q5's 20 % CAGR).
   - `off` for refusals, safety and injection: already 100 % with the guard.
   - `off` when RAG evidence is shown: the answer is a lookup.
   - `budgeted` only for open multi-step analysis with no tool.
   - Unknown categories default to `off`: thinking must be earned.
   - Today every category in the eval set routes `off`, so nothing recorded changes.
5. **Reasoning is never shown or graded,** but it is logged for audit.

**What is not known:** whether budgeted thinking makes this model's answers *better* on the open questions.
That needs a measurement (an A/B on the open-reasoning rows on the i5-12400), which I propose as the first
step after the Phase 8 run. I am not claiming the benefit before it is measured.

## Tests

- `tests/test_phase8.py`: 78 assertions.
- `tests/mutate_phase8.py`: 42 mutants, all killed. 2 first-pass survivors are now pinned: `\text` inside
  `\frac`, and unlisted commands.
- Batteries rerun after the wiring changes:
  - phase4: 0 survivors. 6 anchors broken by `--style` / D-0121 were re-anchored and verified killed.
  - red team: 51/51.
  - phase7: 34/34 (1 re-anchored).
- `run_all`: 22 suites, 0 skipped.

## Next step

Run `PHASE8_RUN_FA.md` on the i5-12400:
- (a) Q4_K_M in-process with `--style`, which isolates the style effect;
- (b) the same through Ollama, which isolates the runtime;
- LM Studio, plain arm only.

Send `phase8_style_merged.json`, `phase8_ollama_merged.json` and `p8lm_plain.json`.
