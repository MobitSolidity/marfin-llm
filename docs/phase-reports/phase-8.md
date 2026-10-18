# Phase 8 Review — Ollama and LM Studio

Project: marfin-llm · Date: 2026-10-17 · Governing prompt: SYSTEM_PROMPT.md v2.0 (SS.24 Phase 8)
Mode: `ANALYSIS_ONLY` · Live trading: `DISABLED` · Label key: (V) VERIFIED · (M) MEASURED · (C) COMPUTED · (E) ESTIMATED

## Status: **IN PROGRESS** — first run graded 2026-10-18 (D-0124); defects found and fixed; rerun pending (`PHASE8_RERUN_FA.md`)

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


---

## First run, graded (2026-10-18, D-0124)

The three files you sent are stored as `evidence/phase8_{style_merged,ollama_merged,lmstudio_plain}_2026-10-18.json`,
along with the smoke-test output. They were graded with the D-0122 pipeline: `regrade_eval`, `regrade_citations`,
`grade_merged` and `attribute_failures`, all with the model not re-run.

### Threshold tally (worst arm decides)

| Threshold | Phase 7 Q4 (no style) | Phase 8 in-process + style | Phase 8 Ollama + style |
|---|---|---|---|
| citation_correctness (≥95) | 90.48 | 76.19 | **95.24 PASS** |
| unsupported_claim_rate (≤3) | 7.69 | 17.24 | 8.0 |
| correct_abstention (≥90) | 88.89 | 66.67 | 77.78 |
| deterministic_calc (100) | **100** | 87.5 | 50.0 |
| fabricated (0) | 1 | 1 | 3 |
| decode tok/s (≥8) | 4.10 | 3.96 | 3.71 |
| TTFT @2K (≤3 s) | 30.1 | 32.9 | 130.2 (at 4433 tokens, not 2K: invalid) |
| peak RSS (≤6.0 GiB) | 4.73 | 4.71 | **UNMEASURED** (the harness saw 0.05 GiB, its own process) |
| tally | 4 PASS / 6 FAIL / 2 UNM | 3 / 7 / 2 | 3 / 6 / 3 |

**Your Task Manager readings (M, read by eye):**

| Run | RAM | CPU |
|---|---|---|
| `ollama run` | 4.2 GB | 81.5 % |
| in-process | 2.1 GB | 98 % |
| **Ollama evaluation run** | **6.2 GB** | 80 % |
| LM Studio | 2.7 GB | 53 % |

- 6.2 GB is above the 6.0 cap if it is GiB, and just below it (5.77 GiB) if Task Manager meant 10⁹ bytes.
- The in-process value of 2.1 GB is lower than the 4.71 GiB peak that psutil recorded. Task Manager's default
  column is the private working set, which excludes the memory-mapped weights. The rerun guide asks you to name the
  column you read.

### Your three defects: fixed (`compare_style`, Phase 7 → Phase 8 in-process)

| | before | after |
|---|---|---|
| LaTeX shown to you | 8 | **0** |
| LaTeX the model itself wrote | 8 | 3 (the rewrite caught all 3) |
| English sentences in a Persian answer | 1 | **0** |
| answers cut off at 512 tokens | 6 | **0** |

### But the style rules caused 12 row regressions, for three reasons (all M)

1. **The model stopped calling the calculator.**
   - Measurement: where a tool was expected, calls fell from 8/10 to 2/10 in-process, and 0/10 through Ollama.
   - Six `tool_value_ok` regressions follow from that. The answers were mostly still right, but the tool was skipped.
   - Cause: "give the answer first" was read as covering the tool call too.
   - Fix: `STYLE_TOOLS_NOTE`, tools arm only: "style rules apply to your final answer only; call the tool first".
2. **My example leaked an answer.**
   - The rule's example, `P/E = 150 / 8.40 = 17.86`, is exactly the answer to EN/FA-CALC-001, and the in-process
     reply reproduced it verbatim.
   - Fix: the example is now `240 / 12 = 20`. Neither 240 nor that formula appears in any eval file (pinned by a test).
3. **English questions were answered in Persian.**
   - 3 rows: tools EN-ABST-002, EN-SAFE-001 and EN-SAFE-002, which cost 1 abstention and 1 fabrication.
   - Cause: "the language of the question" was read as Persian.
   - Fix: the rule now spells out both directions.

**Citations (in-process):** 3 of the 5 new CONTRADICTED claims are the model's added explanatory sentence, e.g.
'This figure is explicitly stated in passage [4], which reports "Total net sales | 383,285"'. The value in each is
correct, but the sentence has no scale word next to the bare number, so the verifier correctly refuses it (the
D-0103 design). This is what "a few short lines of explanation" invited. Fix 2 removes the leaked example; whether
the explanatory sentence persists is for the rerun to show.

### Runtimes: not identical, and why (`evidence/phase8_runtime_compare_2026-10-18.json`)

**Result:**
- **0 of 74** in-process vs Ollama replies are byte-identical, and 0/21 in-process vs LM Studio.
- Prompt token counts are equal on every comparable row, so the prompt was the same.
- The difference is therefore in decoding.
- **Cause (INFERRED):** `repeat_penalty`. llama-cpp-python's default is 1.0 (VERIFIED in its signature). Ollama and
  LM Studio default to 1.1, and the D-0123 runner did not send it. A repeat penalty changes the greedy argmax even
  at temperature 0.
- **Fix:** 1.0 is now sent to both servers and pinned in the Modelfile. The rerun will confirm or rule out this cause.

**Four more instrument defects in my Phase 8 tooling, all fixed and pinned:**

| Defect | Effect | Fix |
|---|---|---|
| The server path had no token counter | The TTFT prompt fell back to the character estimate: 4433 tokens, not ~2048 | `ServerRunner.count_tokens` uses the server's prompt_eval_count |
| The same TTFT prompt was sent 3 times | Invocations 2 and 3 were KV-cache hits (1.04 s and 1.07 s vs 130 s) | Every server probe gets a unique first line |
| `merge_phase4` dropped the `server` block | The merged Ollama file looked in-process, and `compare_quants` refused it | The block is carried through |
| `grade_merged` graded the harness's 0.05 GiB as peak RSS | A false PASS | Harness-only RSS is now UNMEASURED |

**Smoke test (`ollama run`):** a "Thinking Process" block was printed, so the Modelfile's pre-closed TEMPLATE was not
what Ollama used interactively. The measured path (raw `/api/generate`) is unaffected: 0 thinking replies. The
Modelfile now documents that interactive use needs `--think=false`. The LaTeX rewrite lives in the orchestrator, so
raw `ollama run` text can still contain LaTeX.

### Phase 8 acceptance (SS.24): status after the first run

| Criterion | Status |
|---|---|
| Runs within RAM | In-process 4.71 GiB PASS. Ollama 6.2 GB (your reading): over the cap if GiB. **Re-measure.** |
| Meets or approaches speed target | No: 3.7–4.2 tok/s vs 8 (hardware-bound, as in Phase 4) |
| Persian and English valid | Persian defects fixed. 3 EN→FA language swaps, now fixed in the rule |
| Tool integration works through orchestrator | Schema validity 100 %, but tool use collapsed under `--style`; fix applied |

**Next step:** `PHASE8_RERUN_FA.md`, about 2 h (ESTIMATED).
