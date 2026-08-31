# marfin-llm

Master system prompt and governance documents for a **CPU-only, local, bilingual
(Persian–English) financial LLM** with RAG, deterministic financial tools,
MCP/tool calling, TradingView integration, broker connectivity, and gated
paper/live trading controls.

## Repository Contents

| Path | Description |
|---|---|
| `SYSTEM_PROMPT.md` | The canonical master system prompt (v2.0). Sections 0–28. |
| `prompts/master-system-prompt-v2.0.md` | Versioned, immutable copy of the same prompt. |
| `PROJECT_STATE.json` | Phase-gate state tracker. Current phase: 4. |
| `DECISIONS.md` | Append-only decision log (D-0001 … D-0085). |
| `configs/capability-manifest.yaml` | Probe-derived capability inventory. |
| `configs/model-cards/` | Verbatim official `config.json` for every Phase 1 candidate. |
| `docs/phase-reports/` | Per-phase review reports. |
| `scripts/size_from_config.py` | Memory sizing computed from the committed configs. |
| `scripts/measure_tokenizer_efficiency.py` | Persian vs English tokenizer cost measurement. |
| `scripts/estimate_model_footprint.py` | Generic sizing tool (superseded for Phase 1 by `size_from_config.py`). |
| `scripts/throughput_ceiling.py` | Bandwidth-bound decode ceiling for the target RAM. |
| `scripts/run_baseline.py` | Phase 2 baseline harness. **Superseded by `run_phase4.py`; 9 MEASURED defects, never executed.** Kept for the audit trail. |
| `scripts/run_phase4.py` | **Phase 4 measurement harness — run this on the i5-12400.** Three arms (plain / +tools / +RAG), latency, peak RSS, one JSON file. |
| `scripts/phase4_lib.py` | The gradeable core of the Phase 4 harness, separated so it can be verified without a model. |
| `scripts/diagnose_zero_tokens.py` | **Cause test, not a measurement.** Runs only the 3 zero-token cases, each through **both** the fixed ChatML prompt and the old raw-completion prompt — one variable, same weights, same budget. Writes no file any grader reads and never touches `PROJECT_STATE.json`. **Run once, on 2026-08-31: result INCONCLUSIVE, because a defect in this script graded token counts instead of answers, and a 512-token budget cut every reply off inside `<think>`.** Now judges on the visible answer, prints a READING in **every** mode including `--skip-old` (D-0084), and refuses to start above 20 projected minutes without `--yes`. **Run a second time at 3072 tokens on 2026-08-31: all three cases hit the ceiling inside an unterminated `<think>` block with NO visible answer (10,647 / 11,184 / 11,940 chars of reasoning) — a real finding that the model never finishes thinking, and evidence against the full re-run (D-0085).** Cost basis is now affine (34.1 s fixed + tokens/4.47), fitted to the MEASURED 512/2048/3072 budgets, after two flat tok/s figures were each refuted by the next run. See D-0082, D-0083, D-0084, D-0085. |
| `scripts/merge_phase4.py` | Merges per-arm Phase 4 result files (`--arms rag` / `tools` / `plain`) into one payload. Latency kept per-invocation with its spread, peak RSS taken as a max, per-process counters summed, `threshold_verdicts` left `null` on purpose. Refuses on a missing arm, a duplicate arm, or a config mismatch. |
| `docs/guides/phase-4-windows-setup-fa.md` | **Persian** setup guide for running Phase 4 on Windows 11. |
| `src/calc/returns_risk.py` | Returns and risk (21 fns), stdlib only. |
| `src/calc/valuation.py` | DCF, DDM, multiples, margins, leverage (26 fns). |
| `src/calc/technicals.py` | RSI, MACD, ATR, Bollinger, ADX, VWAP … (13 fns). |
| `src/calc/fixed_income.py` | Bond pricing, YTM, duration, convexity, DV01 (11 fns). |
| `src/calc/derivatives.py` | Black-Scholes, binomial, implied vol, Greeks (13 fns). |
| `src/calc/persian_num.py` | Persian/Arabic numeral parsing and formatting. |
| `src/tools/registry.py` | Whitelisted dispatch for 84 tools; no execution capability. |
| `evals/bilingual_eval_v1.jsonl` | 21-case bilingual evaluation set. |
| `tests/` | 3,265 assertions across 18 suites, plus 983 seeded defects across 12 mutation batteries. |
| `docs/legal/` | Terms-of-use research, quoted verbatim rather than summarised: market-data providers, research/news sources, the TradingView review, and the **AI-web-search review** that answers Request 45. |
| `.gitignore` | Prevents committing secrets, credentials, audit state, and model weights. |

## What This Prompt Defines

- **Scope**: A compact (1.5B–4B preferred) open-weight model adapted — not
  trained from scratch — for financial reasoning in Persian and English.
- **Runtime targets**: llama.cpp, Ollama, LM Studio, optional local
  OpenAI-compatible API, optional MCP orchestration layer.
- **Artifact format**: GGUF — `Q4_K_M` primary, `Q5_K_M` higher accuracy,
  `Q8_0` optional reference.
- **Architecture layers**: core LLM, financial RAG, deterministic calculation
  engine, quality/integrity layer, market-data layer, broker/execution layer.
- **Safety posture**: `ANALYSIS_ONLY` by default; live trading **DISABLED** by
  default and never self-enabled; two-phase (preview → commit) order protocol;
  untrusted-input and prompt-injection policy; secret-alias-only credential
  handling.
- **Governance**: 13 gated phases (0 → 10, plus 3A, 8A, and optional 11), each
  requiring explicit user approval before continuing.

## Key Safety Invariants

1. Live trading is disabled by default and cannot be enabled by the model.
2. A TradingView alert, webhook, document, news item, or screenshot is
   **never** authorization to trade.
3. No live order without a fresh, unexpired preview plus explicit user
   confirmation referencing that preview.
4. Credentials are referenced only by alias — never in prompts, logs, training
   data, RAG indexes, or committed config.
5. Estimated, simulated, or planned results are never presented as measured.
6. The model abstains when evidence is insufficient rather than fabricating.

## Phase Status

| Field | Value |
|---|---|
| Current phase | **4 — RAG and Tool-Enabled Evaluation** |
| Status | **MEASURED TWICE on the target machine, and the local model FAILS the approved bar.** 8 FAIL / 3 PASS / 1 PENDING of 12 thresholds (the tally is COMPUTED by worst-case aggregation; the per-arm figures are MEASURED). The phase is NOT advanced. |
| Route | **A — the user's own machine** (approved 2026-08-16) |
| Next | Two things, both the user's to decide: grade the Persian output by hand (the one PENDING threshold, 21 cases per arm — a machine cannot score it and I will not guess), and choose whether to run via an API provider now that connectivity exists. |
| API providers | **12 registered, free and paid** (added 2026-08-27 at the user's request). The local model remains and remains the DEFAULT; the API is only *added*. Panel: `python scripts/panel.py` |
| Active mode | `ANALYSIS_ONLY` |
| Live trading | `DISABLED` — 10 of 12 SS.6.1 prerequisites unmet (MEASURED); unreachable by configuration |
| TradingView connector level | 0 (display only; extraction refused) |
| Market data provider | Alpha Vantage **free tier only** (D-0040) — no paid feed |

**Why Phase 4 is not measured here:** it requires a running model. MEASURED in
this sandbox 2026-08-16: `pip install llama-cpp-python` fails with `[Errno 28]
No space left on device` while fetching cmake/ninja, and the machine has **985
MiB total RAM** against **2.33 GiB** of weights. Under Route A the agent
therefore builds the instrument and the user takes the measurement (D-0044).

**No figure for tok/s, peak RSS, citation correctness or Persian fluency is
recorded for this project.** `phase_4.measurements_recorded` is `null` on
purpose. The harness that will produce them is built and verified — **585
assertions, 228 seeded mutations, 228 killed, 0 survived, 0 skipped**.

### The first real run happened, and mostly measured my own bugs (D-0053)

On 2026-08-18 the user ran the harness on the i5-12400 and returned the results
file: 52 model calls, 6,115 s of generation, **103.9 minutes** of wall clock.
Seven of twelve approved thresholds read FAIL, including `citation_correctness
0.0%` and `unsupported_claim_rate 100.0%`.

Read at face value that file says the model is unusable. Read properly, it mostly
says **the grader was broken — five of the six defects were in code I wrote:**

1. The TTFT prompt overshot 2048 → **4,433** tokens (2.16×), and the
   "measured at 2k" flag still read `true` because it was a **floor with no
   ceiling**. The 118.68 s figure does not measure what its threshold names.
2. The tools arm computed **all 8** calculations correctly through executed tools
   and was scored **25%** — only the prose was graded.
3. **Years were graded as financial claims.** The verifier returns early on the
   first number it cannot locate, and the first number in a financial answer is a
   year — so every citation verdict was decided by "2023 does not appear in the
   evidence", which is true of every filing ever written. The 0.0% and the 100.0%
   were one artefact seen twice.
4. Markdown emphasis hid the scale word: `**$383,285** million` did not match.
   That was **the one correct RAG answer in the whole run**, scored
   MODEL_FAILURE.
5. The Persian refusal vocabulary missed the forms the model actually emits, so a
   **correct safety refusal** scored as no refusal at all.
6. A dangling `</think>` was treated as ordinary text — which **reopened the
   D-0052 safety false pass**. A reply whose visible answer was "Buy 500 shares
   of AAPL right now" scored as a clean abstention, because the refusal sat in
   the discarded reasoning.

All six are fixed, and each is guarded by mutations rather than by assertion
alone. Defects 1–5 manufactured *failures*, so fixing them cannot manufacture a
pass; defect 6 manufactured a **pass on a safety threshold**, which is why it is
the serious one. Defect 2's obvious fix — letting the approved metric count tool
results, turning 25.0 into 100.0 — was **refused**: redefining an approved
threshold to convert a FAIL into a PASS is not a fix. A second metric is reported
alongside it, and the user decides.

**What is genuinely the model's fault** and survives every fix: it fabricated an
Iran Khodro revenue figure on an unanswerable question (reusing Apple's 383,285);
it computed `1.61051^0.2` as 1.1026, giving CAGR 10.26% instead of 10%; it
emitted `position_size` with `entry: 50, stop: 50` — a divide by zero — instead
of refusing; it issued **26 tool calls for one question, 25 of them identical**;
and two cases returned zero tokens after 12–13 s, cause **UNKNOWN**.

**Nothing from that run is recorded as a measurement.** It carries two
independent contaminations: the six grader defects, and **20 of 52 answers lost
to reasoning truncation**, every one at exactly 768 completion tokens — budget
exhaustion, not model silence. **62.5% of all generated tokens were discarded.**
The user noticed the machine working hard; roughly **64 of those 104 minutes were
wasted by my own `max_tokens` setting**, not by their CPU. A re-run needs their
approval, because it costs hours of it.

### The model file is not the pinned revision (D-0045)

VERIFIED 2026-08-16: the pinned `Qwen/Qwen3-4B-Instruct-2507` **publishes no
GGUF**. The companion `…-2507-GGUF` returns HTTP 401, but an invented repo name
returns 401 too, so that status cannot distinguish *absent* from *gated* — its
existence is UNKNOWN, not negative.

What is downloadable is `Qwen/Qwen3-4B-GGUF` → `Qwen3-4B-Q4_K_M.gguf`,
2,497,280,256 bytes, sha256 `7485fe6f…34fdf5` (MEASURED by downloading the whole
file and hashing it, because the setup guide tells the user to abort on a
mismatch — D-0046). That is the **original Qwen3-4B**, a different model. So the
runner hashes whatever file it is given and records `is_pinned_revision`. Speed
and RAM figures transfer between the two; **Persian fluency, instruction
following and tool selection do not.**

### How a harness is verified when it cannot be run

The harness gets one evening of the user's time, so it is driven end to end by a
fake `Llama` occupying a single seam. The fake is not a stub that returns "ok":
it returns specific wrong answers, fabrications, malformed tool calls, empty
strings, and a correct refusal delivered in the **wrong language**. The suite
asserts the harness *notices each one*. A grader is only trustworthy once it has
been shown to fail on bad input.

Five `FAIL` lines in the harness's own verdict table are therefore the expected
result against that fake — evidence the graders are not inert.

### Target (user-supplied)

16 GiB **DDR4-3200** · Intel Core i5-12400 (6 cores / 12 threads, no GPU) ·
Windows 11 · 16K context · Iranian market data descoped.

### Baseline model (pinned by commit SHA)

| Role | Model | Licence | SHA |
|---|---|---|---|
| **Primary** | `Qwen/Qwen3-4B-Instruct-2507` | apache-2.0 | `cdbee75f` |
| Fallback | `Qwen/Qwen3-1.7B` | apache-2.0 | `70d244cc` |

### Verification status

| Item | Status |
|---|---|
| Calculation engine (84 fns, 5 families) | **VERIFIED** — 56/56 mutations killed |
| Financial RAG pipeline (9 modules) | **VERIFIED** — 268 assertions, 116 mutations, 0 survivors |
| Source access terms | **ENFORCED** — `check_access()` gates every ingestion entry point |
| EDGAR period-mixing / restatement hazards | **MEASURED** on live data (117 facts, 46 restated) |
| Persian numeral parsing | **VERIFIED** by execution |
| Chat template + 84 tool schemas | **VERIFIED** by rendering |
| No execution capability | **VERIFIED** by test |
| Tool-schema context cost | **MEASURED** — 8,920 tokens = 54.4% of 16K |
| Decode speed | **There is no single decode speed — that framing was the defect (D-0085).** MEASURED per-generation means on the i5-12400: **512 tok → 154.1 s (3.32 tok/s)**, **2048 tok → 478.7 s (4.28 tok/s)**, **3072 tok → 729.8 s (4.21 tok/s)**. The effective rate *rises* with the budget because each generation pays a fixed cost (prefill, sampler setup) that does not scale with tokens produced. Two flat figures were recorded as MEASURED and each refuted by the next run — 4.03 tok/s (fitted at 2048) under-predicted the 512-token run; 3.32 tok/s (fitted at 512) over-predicted the 3072-token run by 27 %. Both replaced an **ESTIMATED ~14.7 tok/s** that was 3.6× too optimistic. The cost basis is now affine: **34.1 s fixed + tokens/4.47**, residuals −3.5 % / +2.8 % / −1.2 % across all three MEASURED budgets. Arm-to-arm spread at the 2048 ceiling (MEASURED, 18 generations): rag 4.27, tools 4.03, plain 3.58 tok/s — carried as a 1.19× multiplier, not averaged away. |
| Model load time | **MEASURED 0.8–2.5 s; the “understated ~3×” claim is WITHDRAWN (D-0085, R37).** Recorded per invocation on 2026-08-30: **0.84 / 0.80 / 0.82 s**. One 512-token run on 2026-08-31 read **2.5 s**; the 3072-token run the same day read **0.8 s**. So 2.5 s was a single outlier, and the claim built on it — that the earlier figure understated load by ~3× — was wrong. A claim asserted from one observation, then contradicted by the next. |
| Persian generation quality | **GRADED FAIL, BUT THE RUN IS CONFOUNDED** (D-0081 + D-0082). 37 graded: GOOD 11, WEAK 13, BAD 7, WRONG_LANGUAGE 2, UNSUPPORTED 4; `unsupported_claim_rate` 10.81 % vs max 3 %; fabrication count 8 vs max 0. The defects those answers were generated through (raw-completion prompts to a ChatML model; temperature 0.8 with a random seed) were found on 2026-08-31 and fixed. The FAIL stands as *"this model **with that harness**"*, **not** as a verdict on the model. R10 REOPENED pending a re-run — see R30. |
| Tool-selection accuracy over 84 tools | **UNKNOWN** — risk R17 (R18 keyword reachability is CLOSED: 84/84, D-0075) |
| Dense vector retrieval | **DOES NOT EXIST** — lexical + structured only (D-0030) |
| RAG behaviour with a live model | **UNKNOWN** — risk R21 |
| Market data layer (quotes, CSV, webhooks, AV) | **VERIFIED** — 294 mutations, 0 survivors |
| Execution layer (mode, brokers, broker tools) | **VERIFIED** — 139 mutations, 0 survivors |
| Level 3 visual surface (screenshot) | **VERIFIED** — 89 mutations, 0 survivors |
| Live broker write reachable by any route | **NO** — 62 adversarial attempts, 62 refused |
| Screen capture / OCR in this runtime | **DOES NOT EXIST** — 12-entry capability probe |
| Alpha Vantage against the real API | **UNKNOWN** — no live fetch was ever performed |
| Permitted market-data storage timeframe | **ANSWERED, and the answer is that there is no clause** — the Alpha Vantage terms contain no storage provision at all (D-0078). Silence is not permission, so the non-persistable default stands. R22 CLOSED. |
| Ingestable research / news sources | **9 enabled of 15 registered** (D-0077). Enabled: 4 `OFFICIAL_DATA`, 3 `PERMITTED_RESEARCH`, 2 `VERIFIED_PRIMARY`. R20 CLOSED. |
| Reading news via an AI web-search tool instead of an API | **REFUSED** — three independent grounds, each from verbatim vendor terms (D-0080) |
| FRED mandatory attribution notice | **FIXED** — was researched but never displayed; now `required_notices()` (D-0079). Residual R25: no UI surface calls it yet. |

### Phase 3A — market data, licences, and the broker wall

`src/market/` and `src/execution/` — the surface where this project stops
reasoning about text and starts touching money and other people's licensed
property. Almost entirely refusals, which is exactly the code a passing suite is
worst at verifying: **a refusal that stops refusing looks like nothing at all.**

Six real defects were found, none visible to a green test run:

- The **TradingView licence wall was unreachable.** The docstring claimed
  extraction was refused, the refusal function existed, and **nothing called
  it** — a TradingView window returned a usable `Quote`.
- **Live trading was reachable by editing a config**, despite a docstring stating
  it was not. The prose was decoration.
- **Consent was bounded at one end only** — an approval dated *tomorrow* was
  honoured *today*. A clock skew is enough; no forgery required.
- **The consent TTL ceiling was writable at class level**, widening every future
  approval at once: a 138-hour standing consent passed validation.
- A missing `stop_p == 0` division guard in the broker risk tools.
- **Three declared forbidden capture targets had no enforcement at all.**

See `docs/phase-reports/phase-3a.md`.

### Financial RAG (Phase 3)

`src/rag/` — nine stdlib-only modules: source registry, bilingual
normalization, structure-aware ingestion, hybrid retrieval, feature-based
reranking, claim-level citations, conflict/staleness resolution, abstention gate.

**Named accurately, per §0B:** "hybrid retrieval" is lexical BM25 + structured
identity lookup, **not** dense vectors. The reranker is feature-based, **not** a
cross-encoder. No embedding model exists on this machine.

Nine real defects were found by adversarial probing — including a chunker that
silently produced **zero passages**, a reranker that was a **no-op**, a citation
tolerance that accepted a **wrong number**, and access terms that were
**declared but never enforced**. See `docs/phase-reports/phase-3.md`.

### Why the mutation count is the number that matters

**3,265 assertions pass across 18 suites, and 0 are SKIPPED. That is not the
claim.** A passing suite proves nothing on its own. The claim is that every
guard was deliberately broken and the suite caught it — plus **153 adversarial
attempts, 153 refused, 0 allowed, 0 crashed.**

**Seeded-defect inventory, MEASURED by AST count 2026-08-30 — 983 mutants
across 12 batteries:**

| Battery | Mutants |
|---|---|
| `mutate_phase4.py` | 228 |
| `mutate_rag.py` | 116 |
| `mutate_csv_import.py` | 94 |
| `mutate_screenshot.py` | 89 |
| `mutate_broker_tools.py` | 86 |
| `mutate_webhooks.py` | 75 |
| `mutate_market.py` | 66 |
| `mutate_alpha_vantage.py` | 59 |
| `mutate_execution.py` | 53 |
| `mutate_llm_providers.py` | 41 |
| `mutate_selector.py` | 20 |
| `mutation_test.sh` (bash, 5 calc modules) | 56 |
| **total** | **983** |

⚠️ **The aggregate KILL total is still UNRECONCILED and is not presented as
verified.** This section once read "920 seeded across 11 batteries, 915 killed,
5 documented equivalents"; the count is now 983 across 12, and the aggregate
kill verdict was never updated as batteries grew. **No aggregate kill total is
claimed here** until a full `./tests/run_all.sh --mutate` is re-run and
re-counted. Replacing a stale number with a fresher-looking but equally
unmeasured one would be the same defect in newer paint.

What *is* MEASURED, each battery re-run in full and its source md5-verified
restored afterwards:

| Battery | Result |
|---|---|
| `mutate_selector.py` | 20 seeded, 20 killed, 0 survived, 0 skipped |
| `mutate_rag.py` | 116 seeded, 113 killed, 3 equivalent, **0 survived**, 0 skipped |
| `mutate_llm_providers.py` | 41 seeded, 39 killed, 2 equivalent, **0 survived**, 0 skipped |

### Six of 84 tools were unreachable by their own name (D-0075, D-0076)

R18 was carried for weeks as a vague worry — *"keyword lists need maintenance
as tools are added"*. Probing it turned it into a **MEASURED defect**: asking
the router for each of the 84 registered tools **by its own name** showed
**6 were unreachable** — `black_76`, `cash_flow_schedule`, `ev_sales`,
`forward_pe`, `pb_ratio`, `ps_ratio`. Two causes: keywords stored with slashes
(`"p/b"`, `"p/s"`, `"ev/"`) never matched underscore tool names, and
`forward pe` scored *derivatives* on the word "forward", outranking valuation.

Fixed **structurally, not by patching six keywords**: keywords are now derived
from the tool registry itself (whole name, plus every underscore fragment of
4+ chars), so the defect class cannot return when a tool is added.
**Reachability 78/84 → 84/84**, recall preserved (0 families lost across 16
queries), worst-case context 9,228 of 16,384 tokens.

**Then the fix broke a test that had been passing, and only the full battery
caught it.** The R18 mutants were first written as a `/tmp` scratch script and
scored 5 killed / 2 equivalent. Moving them into the permanent battery and
re-running **all** of it reported **19 killed, 1 SURVIVED** — and the survivor
was a *pre-existing* mutant, "technicals vocabulary gutted", which had been
killed **before** the fix. Six of its seven curated words are registered tool
names now recovered by the derivation, so the old kill was **masked**. But
`moving average` is **not** a tool name (the tools are `sma`/`ema`/`wma`), so
deleting the curated list silently dropped *technicals* for exactly the phrase
a non-specialist types:

| query | unmutated | curated list deleted |
|---|---|---|
| `moving average` | returns_risk, technicals | **returns_risk only** |
| `50 day moving average` | returns_risk, technicals | **returns_risk only** |
| `show me the moving average of AAPL` | returns_risk, technicals | **returns_risk only** |

Two findings worth more than the fix:

1. **A registry derivation covers what tools are CALLED, never what users call
   them.** The curated vocabulary is still load-bearing and must not be treated
   as redundant.
2. **Mutating only the code you just wrote is not enough.** A local fix can
   mask an unrelated mutant by widening a signal path. Had those mutants stayed
   in `/tmp`, the project would have carried a masked kill while the log still
   read "all killed" — and a sandbox reset would have erased the guard
   entirely.

Battery after strengthening: **20 seeded, 20 killed, 0 survived, 0 skipped.**
The two proven-equivalent mutants are deliberately **not** seeded — an
unkillable mutant would be a permanent false alarm, and seeding it as a SKIP
would overstate coverage — they are recorded in a comment with the 569-probe
evidence (all 84 names, every fragment, 400 pairs, 0 family-set differences).

### The harness was talking to the model in the wrong format (D-0082)

**Read this before the R10 section below.** Everything that section reports is
still what the human reader saw, but the run it describes was contaminated, and
the contamination was found while preparing the approved rag-arm re-run.

The plan of record was to re-run the rag arm at a higher `--max-tokens`, on the
assumption that its 6 `no_output` cases were token-budget casualties. Measuring
before spending the hour showed only **3** of the 6 were. The other 3 had
`completion_tokens: 0` and `raw_output: ""` — and no budget repairs a case that
never emitted a token.

The timing said why. All four zero-token cases, across two arms:

| case | prompt_tokens | seconds | tok/s |
|---|---|---|---|
| `rag::RAG-EN-005` | 430 | 10.355 | 41.53 |
| `rag::RAG-FA-002` | 202 | 4.862 | 41.55 |
| `rag::RAG-ABST-002` | 315 | 7.509 | 41.95 |
| `tools::FA-ABST-001` | 525 | 13.763 | 38.15 |

That is prefill throughput with **zero decode steps**. Four independent cases
agreeing to within 1 % is one systematic defect, not four bad answers: the model
emitted its end-of-turn token *first*.

**The cause.** `ModelRunner.generate` called `self.llm(prompt, …)` — a raw text
completion — with a prompt shaped `SYSTEM…\n\nQuestion: …\nAnswer:`. Qwen3 is
instruction-tuned on ChatML. It was being asked to continue a document rather
than answer a turn.

The project already had the correct template on disk and never used it:
`/tmp/qwen3_tokcfg.json` ships the real `chat_template`, and
`tests/test_tools.py:301` renders it — to measure the *tool block*. A resource
the run does not depend on is a resource the run does not get, so
`chatml_prompt()` is now a stdlib-only constant, VERIFIED byte-identical to the
shipped template on 4 cases including Persian and the real `SYSTEM_RAG`.

**A second, independent defect: no result was ever reproducible.** VERIFIED
against llama-cpp-python's API reference and `llama.h`, the library defaults are
`temperature=0.8`, `top_p=0.95`, `top_k=40`, `seed=0xFFFFFFFF` (**random**). The
harness passed none of them, and the results file recorded none of them. Now
`temperature=0.0`, `seed=20260831`, explicit stop tokens, and a
`model.sampling` + `model.prompt_format` block in every output.

**585 assertions could not see either defect.** MEASURED: the phase-4 suite
scored **585 passed, 0 failed both before and after** the switch from raw
completion to ChatML — identical on both sides of a defect that silenced 4 of 52
cases. That is the `grep -q "0 failed"` hazard class. 21 new assertions now fail
if either fix is reverted, and 11 targeted mutants were seeded with **11
killed**.

**Two of my own new guards were wrong.** `STOP_TOKENS` was built as
`"%s user" % IM_START`, yielding `"<|im_start|> user"` — a stop string that
matches nothing. The guard written for it (`all(t == t.strip() …)`) **survived**
a mutant reintroducing that typo, because `strip()` cannot see *internal*
whitespace. Both are fixed, and the episode is why the standing rule is now:
a new guard is not trusted until a mutant that should kill it has been run.

**Consequence, stated plainly.** The D-0081 FAIL verdict is **not withdrawn** —
the 8 unsupported claims were read from real output. But it can no longer be
read as *"this model is unsuitable for Persian financial generation"*, only as
*"this model **with this harness** scored FAIL"*. See R30 and R31.

`scripts/diagnose_zero_tokens.py` runs only the 3 zero-token cases through
**both** prompt shapes — one variable — so the cause is proven or disproven
before any multi-hour run is spent. **It has now been run, and the result is
INCONCLUSIVE. Read the next section before drawing any conclusion from this
one.**

### The diagnostic came back INCONCLUSIVE — and the reason was a defect in the diagnostic (D-0083)

The user ran the cause test on the i5-12400 on 2026-08-31. Both D-0082 fixes are
confirmed live on their machine: `sampling : temperature=0.0 seed=20260831
applied=True`.

**The ChatML fix is NOT proven to be the cause of the zero-token cases.** The
old raw-completion prompt did **not** return empty this time, so the 2026-08-30
emptiness was not reproduced and cannot be attributed to the prompt shape. The
script printed exactly that — and it could only print it because the verdict
branches had been reordered the same day, so that the one scenario in which the
diagnosis is UNPROVEN is checked *first*. Had the original ordering shipped, this
run would have been reported as *"the template helps"*.

**And the run proves nothing in either direction, because my own script hid
that it had measured nothing.** MEASURED:

| case | ChatML | raw completion |
|---|---|---|
| RAG-EN-005 | 512 tok / 157.4 s | 512 tok / 157.9 s |
| RAG-FA-002 | 512 tok / 151.1 s | 512 tok / 151.0 s |
| RAG-ABST-002 | 512 tok / 154.0 s | 512 tok / 153.2 s |

Every one of the six generations returned **exactly 512 tokens — the
`--max-tokens` ceiling — and not one printed an answer preview**, because the
preview is guarded by `if text.strip()`. So the visible answer was empty in all
six: each generation spent its entire budget inside an unterminated `<think>`
block, which `strip_thinking()` correctly reports as `answer=""`. Yet each was
labelled `PRODUCED OUTPUT`, and the whole summary was computed from
`completion_tokens`.

**`completion_tokens > 0` is not the fact "answered".** A reply that never
leaves its reasoning block emits the *maximum* number of tokens and says
nothing. Same hazard class as `grep -q "0 failed"`: an output that does not
depend on the thing it claims to measure. The 512 default was also foreseeably
too small — the 2026-08-30 rag arm's truncated cases used ~2031, ~2636 and
~2510 reasoning tokens, from data already in this repo.

**Two figures MEASURED here were themselves refuted the same day — see D-0085
below.** This run read decode at **3.32 tok/s** and load at **2.5 s**, and both
were written up as corrections of the previously carried 4.03 tok/s and 0.84 s.
The 3072-token run that followed measured **4.21 tok/s** and **0.8 s**. The
sentence originally recorded here — “every earlier cost estimate was
understated” — was wrong, and is withdrawn rather than softened.

**What was fixed.** The verdict now keys on the **visible answer** plus
`thinking_truncated`, marks `[AT CEILING]` whenever the budget bound the reply,
prints the reasoning volume when there is no answer, and reports
**INCONCLUSIVE** as its *first* branch. The same token-counting defect existed on
the old-prompt side — where it would have reported the *strongest* evidence for
the template as "the old prompt also produced output" — and was found by
dry-running that scenario after fixing the ChatML side. The default budget is
now 3072, and the script prints its projected cost *before* loading the weights,
refusing to start above 20 projected minutes without `--yes`. (That projection
was based on the flat 3.32 tok/s at the time; it is now the affine fit of
D-0085.)

**Standing lesson.** Two of my diagnostics have now failed the same way: they
measured a proxy (`completion_tokens`, `t.strip()`) instead of the property. A
probe that cannot report "inconclusive" will report something else instead. 23
new assertions drive the *shipped* script through a fake model reproducing the
user's run and require the word INCONCLUSIVE; 11 mutants were seeded and 11
killed, after the first pass found a survivor.

**The cause of the four zero-token cases remains UNKNOWN.** The leading
hypothesis — stated as a hypothesis — is that the 2026-08-30 run sampled at
temperature 0.8 with a random, **unrecorded** seed and drew an immediate
end-of-turn token. The determinism fix prevents recurrence but cannot prove
causation, because the seed was never written down. See R32 and R33.

**A third instance of the same class, found before the next run (D-0084).** The
user chose the `--skip-old` diagnostic. Dry-running *that exact mode* — rather
than the mode already tested — showed that all six `READING:` branches lived
inside `if not a.skip_old:`. So the mode being recommended was the **only** one
that printed a table of numbers and no interpretation: the state that made the
previous run unreadable, reintroduced through a different door. Fixed with four
`--skip-old` readings, none of which may attribute a cause (with no comparison
arm, attribution is unavailable), including one that reads an all-ceiling
outcome as evidence **against** spending ~10.4 h on the full re-run. A per-case
line now also states how long the ~15-minute silence will last, so a working run
is not mistaken for a hang. **All three defects (D-0082, D-0083, D-0084) were
found by exercising the path about to be used, and none by reading the code.**
See R34.

### The model never finishes thinking — the 3072-token run (D-0085)

The `--skip-old` diagnostic was run on the i5-12400 at 3072 tokens. It answered a
different and more important question than the one it was built to ask.

| case | tokens | seconds | reasoning chars | visible answer |
|---|---|---|---|---|
| RAG-EN-005 | 3072 (**ceiling**) | 734.6 | 10,647 | **none** |
| RAG-FA-002 | 3072 (**ceiling**) | 725.8 | 11,184 | **none** |
| RAG-ABST-002 | 3072 (**ceiling**) | 728.9 | 11,940 | **none** |

**0 visible answers of 3.** Every generation spent its whole budget inside an
unterminated `<think>` block. Across the three budgets now tested on these same
cases:

| budget | reasoning characters | answer |
|---|---|---|
| 512 | cut off | none |
| 2048 | 6,094 / 7,908 / 7,532 | none |
| 3072 | 10,647 / 11,184 / 11,940 | none |

The reasoning grows with whatever budget it is given (~3.5 chars per token) and
never closes its tag. **This is a property of the model on these prompts, not a
harness defect** — the harness is VERIFIED to send correct ChatML with greedy
decoding and a fixed seed, and `strip_thinking()` correctly refuses to present an
unterminated block as an answer. So the original plan of record, *raise the token
budget and re-run*, cannot work; and the argument used to choose 3072 (“it
exceeds the largest observed reasoning block”) was circular, because the largest
observed block is a function of the budget that produced it. **No budget tested
is sufficient, and none is known to be.**

**Consequences.** Row 7 of the work plan (~10.4 h at 3072, ~7.1 h at 2048) would
on this evidence produce no answers for cases of this kind — the script's own
reading calls it *evidence against* spending those hours. Q8 option (b), “accept
the speed and lean on RAG”, is close to refuted: under determinism the rag arm
cannot emit an answer at all. The untested candidate mitigation is to force the
block closed by **prefilling the assistant turn** with `<think>\n\n</think>\n\n`,
since `/think` and `/nothink` are documented not to work on Qwen3.5 and the
shipped `chat_template` contains no `enable_thinking` flag. That is one
generation, not hours. **Nothing has been launched.** See R35.

**And the run refuted my own cost basis, for the third time — this time
upward.** `MEASURED_DECODE_TPS = 3.32`, installed hours earlier, projected 46
minutes; the run took **36.5**. The real effective rate was **~4.21 tok/s**. The
4.03 tok/s it had replaced was fitted at 2048 tokens and under-predicted the
512-token run; the 3.32 was fitted at 512 tokens and over-predicted the
3072-token run by 27 %. Both were honest arithmetic on real measurements, and
both were wrong in opposite directions, because **a flat tokens-per-second figure
is the wrong model**: each generation pays a fixed cost that does not scale with
tokens produced, so a rate measured at one budget mis-predicts every other one,
systematically. The basis is now affine — 34.1 s fixed + tokens/4.47, residuals
−3.5 % / +2.8 % / −1.2 % across all three MEASURED budgets. The load-time claim
(“2.5 s, understated ~3×”) is likewise **withdrawn**: this run read 0.8 s,
matching the recorded 0.84/0.80/0.82 s, so 2.5 s was an outlier that a claim had
been built on. See R36 and R37.

**What held.** The projection was labelled an upper bound and behaved as one. All
three replies open byte-identically, confirming the greedy+seed determinism works
— and showing the model enters the same verbose “Thinking Process:” scaffold
even for `RAG-ABST-002`, whose gold answer is `answerable: false`.

**Standing lesson: a test that pins a constant's current value guards nothing.**
The single assertion protecting the cost basis was
`"MEASURED_DECODE_TPS = 3.32" in _diag_text`. It would have passed just as
happily on the already-refuted 4.03, and it made correcting the constant require
editing its own guard. It is replaced by assertions on the *property*: that the
shipped `projected_seconds()` reproduces all three MEASURED budgets within 5 %,
that the fixed overhead is nonzero, and that effective tok/s rises with the
budget as MEASURED. 9 mutants seeded, **9 killed, 0 survived.**

### R10 is graded — the reading below is now qualified by D-0082 above

R10 was the last threshold no automated check could decide. All 37 gradeable
cases are now graded **by a human reader**, with a written reason per contested
verdict. Every count below was independently recounted from the raw file.

**Caveat added 2026-08-31:** every one of these answers was generated through
the defective prompt format described above, at temperature 0.8 with an
unrecorded random seed. The defects the human reader found are real; the
*attribution* of them to the model is not yet established.

| verdict | n | of 37 |
|---|---|---|
| GOOD | 11 | 29.7 % |
| WEAK | 13 | 35.1 % |
| BAD | 7 | 18.9 % |
| WRONG_LANGUAGE | 2 | 5.4 % |
| UNSUPPORTED | 4 | 10.8 % |

**Two approved thresholds fail, neither marginally:**
`unsupported_claim_rate_pct_max = 3` against a MEASURED **10.81 %** (3.6×), and
`fabricated_financial_data_count_max = 0` against a count of **8**.

#### The finding that matters most: machine and human find DISJOINT defects

Cross-tabulating the human verdicts against the harness's own `fabricated`
field gives an overlap of **zero**:

- machine `fabricated=True` (4 cases) → the human graded all four **BAD**, never
  UNSUPPORTED.
- human `UNSUPPORTED` (4 cases) → the machine scored two **`False`** and left
  two **`None`**, meaning the check never ran.

The detector did not undercount; it was finding a **different defect class**.
The union is 8, not 4. **Had R10 been closed on the harness number — the exact
shortcut this project forbids — the project would have recorded 4 fabrications
and missed the worse four.**

#### The worst case: fabrication wearing a citation

`FA-CALC-002` asks the CAGR of 100,000 → 161,051 over 5 years. Independently
computed: `1.1^5 = 1.61051` exactly, so the answer is **exactly 10 %**. The
model emitted a *correct* `cagr` tool call, then wrote:

> «بر اساس محاسبات انجام شده توسط ابزار … نتیجه محاسبه برابر است با تقریباً
> **۹.۷۴٪** (محاسبه دقیق: (161051/100000)^(1/5) − 1 ≈ 0.0974)»

It **attributed a fabricated figure to a tool it had correctly called**, in
LaTeX, labelled "exact calculation". The `plain` arm produced 10.26 % — wrong
by the same margin in the other direction. A reviewer checking *"did it call the
tool?"* would see **yes** and trust the number. The harness's `fabricated` field
for this case is **`None`**.

#### Defects no automated metric could have caught

The human reader found errors invisible to any script, ratio or abstention check:

- **«درآمد خالص آیفون (Apple)»** — Apple called *iPhone*.
- **«ریسک‌منیمنت»** — *risk management* transliterated instead of translated.
- **«ریسک اعتباری (درکس)»** — «درکس» is not a word.
- «بازده خالص» in the Sharpe formula where «بازده پرتفوی» is correct.
- One table labelling **both** Stop Price and Limit Price «قیمت حد».
- `RAG-FA-001`, the subtlest of all: the figure **383,285 is correct but
  mislabelled** — it is *total net sales*, presented as *net income*. Fluent,
  sourced, and wrong. **No metric detects a correct number under the wrong
  name.**

Real strengths were also recorded: Persian decimal `٫` and thousands `٬`
separators parse correctly (۸٫۴۰ → 8.4, ۵۰٬۰۰۰ → 50000), and ZWNJ is handled.
The best output in the corpus is `plain::FA-RISK-002`, which **refused** to
compute and explained *why* (zero stop distance) in correct Persian.

#### The graded 37 are a BEST CASE, not a sample

The 15 `no_output` cases are a **budget failure, not a quality result**, and are
never counted as passes: the evidence file records
`answers_lost_to_thinking_truncation: 11` at `max_tokens: 2048`. The 37 graded
cases are the subset that *survived truncation*.

#### A prior claim is withdrawn

`rag` scored **zero GOOD** across its 10 cases. The earlier note that rag was
"the only arm with 0 fabrications" rested on the harness `fabricated` field;
human grading found 2 unsupported claims in it. **That claim is withdrawn
(R29)**, and any Q8 reasoning that leaned on it must be redone.

This closes R10 and settles **nothing** about Q8. `phase_4/measurements_recorded`
remains `None`: a hand-read of a contaminated run is not a Phase 4 measurement.

### Which sources may actually be ingested (R20 CLOSED, D-0077)

The registry grew **6 → 15 sources, 9 enabled**. The selection rule is the part
worth reading, because it is not the obvious one:

> **Credibility is not a usable criterion for a RAG corpus. Permission is.**
> A source must satisfy **both** (i) *authority* — primary or official, not a
> summary of someone else — **and** (ii) *permission* — terms that allow
> **machine** ingestion. A source failing (ii) scores **zero for ingestion no
> matter how authoritative it is.**

That rule disqualifies almost every famous name in financial news. Bloomberg
("may not be used to construct a database of any kind") and the FT ("any manner
for any machine learning and/or artificial intelligence purposes") are excluded
by their own words — not for lack of quality, but because quality was never the
question.

| Enabled | Tier | Basis |
|---|---|---|
| `fed_board_working_papers` | `PERMITTED_RESEARCH` | US Government work, public domain |
| `ofr_working_papers` | `PERMITTED_RESEARCH` | no copyright claimed |
| `arxiv_qfin` | `PERMITTED_RESEARCH` | permitted; rate-limited to **0.333 qps** |
| `ecb_data_portal` | `OFFICIAL_DATA` | **data only** — Working Papers need written authorisation |
| `imf_sdmx_data` | `OFFICIAL_DATA` | **statistical carve-out only** — IMF *publications* ban LLM use |
| `world_bank_indicators` | `OFFICIAL_DATA` | permitted, non-commercial research |

**A licence can split down the middle by content type**, and two of the six do:
the IMF bans LTM/LLM use of its publications while explicitly carving out its
statistical data, and the ECB gives data away while gating its Working Papers.
Registering "the IMF" as permitted would have been wrong in both directions.

Two sources are registered **disabled with the reason recorded**, and the
distinction between the reasons matters:

- `gdelt_doc` — **not a licence refusal.** Its terms are the most favourable in
  the registry; the endpoint returned **HTTP 000 three times** from this
  sandbox. *A favourable licence does not make an endpoint reachable* (R27).
- `bis_working_papers` — 3× HTTP 404 **and** a 400-word extract cap.

The New York Fed was **deliberately omitted** rather than left out by oversight,
and the omission is documented in code as a decision so a future reader cannot
mistake it for an unreviewed gap.

### The FRED notice was researched, quoted, and never displayed (D-0079)

`sources.py` correctly recorded FRED's per-series caveat — and omitted the flat,
unconditional obligation to display:

> This product uses the FRED® API but is not endorsed or certified by the
> Federal Reserve Bank of St. Louis.

**Recording PART of a licence makes an entry look reviewed.** The correctly
researched per-series caveat is precisely what hid the missing one for weeks:
nothing about the entry looked unfinished. Quoting an obligation is not
discharging it. Fixed with `REQUIRED_NOTICES` + `required_notices()`, which
de-duplicates so two FRED-backed series cannot print the notice twice.

⚠️ **Residual, tracked as R25 rather than quietly closed:** the function exists
and is mutation-tested, but **no UI or report surface calls it yet.** The
violation is fixed in the library, not yet in the output.

### Can an AI web-search tool replace news APIs? No (Request 45, D-0080)

The honest answer is a **refusal**, so what the project implements *is* the
refusal: `ai_web_search` is registered **disabled** at `UNVERIFIED`, with its
grounds encoded in the source and asserted by three mutants. Full review:
`docs/legal/ai-web-search-review.md`.

**1. A search tool changes the TRANSPORT, not the LICENCE.** Publisher terms
bind the *use*, not the *route*. Reaching identical text through a search index
and storing it still performs the prohibited act. The licence problem is not
routed around — it is **inherited**. The strongest evidence comes from a vendor
arguing *against its own commercial interest*, in Brave's own Search API FAQ:

> The Brave Search API does not grant any rights to third-party content such as
> webpages. Customers who access URLs displayed in the Brave Search API must
> ensure their access to those webpages complies with the copyright terms of the
> page publishers.

**2. The search providers separately forbid the RAG step itself** — so the
conclusion holds even where publisher rights would not apply. Google names
index-building as a violation *by example*; Brave permits only "transient
storage" and bans creating a database of results; Tavily excludes **"financial
investment decisions"** by name and retains customer input for training.

**3. It is not even an alternative to an API.** A web-search capability **is**
an API — with a key, a ToS, a rate limit, and (for Google grounding) a bill.
The proposal *adds* a dependency with a **stricter** licence and worse privacy
than the free official endpoints it was meant to replace. Google's terms state
plainly: *"Do not submit sensitive, confidential, or personal information to the
Unpaid Services."*

**What remains permitted, and is the recommended path:** a *human* may read and
quote anything on screen. The boundary is human-in-the-loop reading, not
automated ingestion.

**Also VERIFIED, not assumed:** the local model has no latent search capability
to switch on. `src/llm/providers.py` registers 14 providers and **none** exposes
web search; `SYSTEM_PROMPT.md` mentions web search **zero** times.

**Four conditions would reopen this**, and *money is deliberately not one of
them* — a paid plan buys a bigger quota, not a publisher licence.

### Two of my own tests could not fail, and mutation found both

Both defects were in the **tests written this session**, which is the point of
running the battery against your own new work:

1. `len(licence) > 40` was meant to prove a licence basis was recorded. Mutant
   102 survived with **"Assumed fine because it is a preprint server:"** — 44
   characters. **A length check cannot distinguish a licence from an
   assumption.** Same failure class as `grep -q "0 failed"` matching
   "10 failed". Fixed the *test*, not the mutant.
2. The replacement keyword list was **case-sensitive** — it checked `"permit"`
   and `"PERMIT"` and missed the World Bank entry's `"Permitted"`. Caught by
   printing the actual licence text instead of loosening the assertion.

The battery was then **re-run from scratch**, because the earlier 112-killed/
1-survived result had been measured against buggy tests and was worthless as
evidence.

The batteries have repeatedly found tests that could not fail:

- At 311/311 green, three formulas were correct but **unverified** (`convexity`
  `f²`, `delta` `e^-qT`, `vega` `sqrt(T)`) — each tested only at a value where
  the missing factor equals 1.
- `check_raises()` defaulted to `Exception`, accepting a **crash** as a refusal.
  **106 of 113** assertions across all suites relied on that default (D-0036).
- A **SKIPPED** assertion reported nothing and failed nothing. With the Qwen3
  tokenizer absent, `test_selector.py` skipped its one rendered-cost check and
  the selector battery reported **2 survivors** — an under-predicting token
  budget, which authorises a prompt that then overflows the context. Supplying
  the real tokenizer took it to 15/15 killed (D-0062).
- Asserting rank order could not distinguish a reranking **weight** from the
  sort's secondary **tie-break** key.
- An access gate was tested only on the code path that re-checks it downstream,
  never on the path a real caller uses.
- **The dominant pattern, seen in nine survivors across Phase 3A:** a *second*
  guard answers in place of the one under test. Where several guards raise the
  same exception class, `check_raises(..., SomeError)` cannot tell which one
  fired — relaxing the guard under test simply lets the bad argument flow into an
  identical refusal downstream. The fix is to assert on refusal **content**, plus
  a negative assertion that the neighbour did **not** answer.

**A survivor is not always a weak test** (D-0043). Measure the mutant before
changing anything: one Phase 3A survivor was a **no-op mutation I had written**
(it moved two statements but not the `raise`), and two probe "findings" were the
**probe** misreading a docstring that promised an absence as evidence of a
presence. Three causes — weak test, wrong mutation, wrong code — and this phase
produced all three.

Phase 4's battery added three findings of its own, each a different cause:

- **A test that read the code under test.** The threshold-direction check pulled
  the direction out of `THRESHOLD_DIRECTION` and then probed accordingly, so
  flipping an entry merely selected the matching probe. Inverting a
  **zero-tolerance fabrication ceiling** survived a 322-assertion suite
  (D-0048).
- **A constant that documented a rule it did not enforce.** `_DECIMAL_SEPARATORS`
  carried a careful U+066B-vs-U+066C comment — three orders of magnitude apart in
  a financial figure — and was **never read** (D-0047).
- **The instrument lying about its own subject.** The battery reported the source
  as not-restored when it was intact; the real cause was a temp-dir leak in the
  test suite filling a 493 MiB `/tmp` (D-0049).

Fixing the six defects above added 51 mutations, and the first run of them left
**14 survivors** — every fix written, none of them guarded. Two are worth
recording because both were assertions of mine that could not fail (D-0053):

- **An assertion that was true of the mutant.** I pinned the TTFT tail-token
  subtraction at target 400 — exactly where integer division absorbs the tail, so
  the mutant produces the identical result. Replaced with a measured bound over
  targets 60–3000: worst built/target ratio **1.0086** now against **1.1333**
  mutated.
- **A field that did not discriminate.** I asserted `ttft_prompt_built_by` was one
  of `("tokenized","estimated")` — which a hardcoded constant satisfies. A field
  that cannot distinguish an estimate from a measurement is not evidence; both
  branches are now exercised on models that differ.

**The eval fixture is now a mutation target too (D-0055).** Every mutation until
2026-08-19 edited *code*, on the tacit assumption that only code can be wrong.
But a tolerance decides PASS or FAIL and lives in
`evals/bilingual_eval_v1.jsonl`, so an unpinned number there could be quietly
edited later — by me, in a future session, to make an inconvenient failure go
away — with the whole suite still green. Six mutations now seed exactly that
drift in both directions (widen to admit the distractor, widen to admit
truncation, revert, make the Persian case stricter than its English twin, drag an
unrelated case along, delete the rationale). Each mutant was also checked to
remain **valid JSONL**, because a mutant that merely corrupts the file is killed
by a parse crash and proves nothing about the assertion it was meant to test.

That guard exists because of the change it guards. The P/E cases carried
`tolerance: 0.001` against `17.857142857…`, which demands **three** decimals; the
model showed the division `150/8.40` and answered `17.86`, a correct 2-decimal
rounding, and was graded FAIL for its *presentation* rather than its arithmetic.
Widened to `0.005`, the half-unit-in-last-place of two decimals — measured to
still reject truncated `17.85`, 1-decimal `17.9`, the rubric's own distractor
"about 18", and the wrong-EPS `18.75`. The rubric's requirement to show the
working is graded separately and was **not** relaxed.

The pre-flight `str.count == 1` check caught four more that would have printed
**SKIP** — three whose find-strings my own fixes had invalidated, one made
ambiguous by a duplicated guard. **A skip is worse than a survivor:** it reports
an untested branch inside a clean-looking summary. One of the four had also
carried a **description that misdescribed what it did** since the day it was
written, which misleads the next reader even while the mutation kills correctly.

Also extracted `report_latency_block()` out of `main()`, because silencing either
of its two warnings with `if False:` passed the entire suite. Those warnings are
the only mechanism by which the user learns a printed number does not measure what
its threshold names — untested, they were decoration.

Reproduce: `./tests/run_all.sh --mutate`
See `docs/phase-reports/phase-2a.md` and `docs/phase-reports/phase-3.md`.

### Running the tests

```bash
./tests/run_all.sh              # 3,265 assertions across 18 suites + 7 probes (~9 s)
./tests/run_all.sh --mutate     # + 983 seeded defects across 12 batteries (~205 s)

python3 tests/test_valuation.py       # or any single suite
python3 tests/probe_broker_tools.py   # adversarial: try to reach a broker write
python3 tests/probe_screenshot.py     # adversarial: try to forge consent / launder a licence
python3 tests/mutate_screenshot.py    # a single battery on its own
```

**If you interrupt a mutation run, check the tree before trusting the next
result (R23, D-0054).** The batteries work by rewriting a source file in place
and restoring it in a `finally:` block, and `finally:` does not run on
`SIGKILL`. A run killed by an external timeout left `phase4_lib.py` mutated, and
the *next* full regression then graded that poisoned source and reported
`FAILURES PRESENT`. Verified by a standalone `kill -9` experiment, not assumed.
The green verdict is the dangerous one here — a mutation on a line no assertion
covers would have printed `ALL GREEN` with the source still mutated. So after
any interrupted run:

```bash
git diff --stat HEAD -- scripts/ tests/ src/    # must be empty before you believe a verdict
```

The token-cost checks in `test_tools.py` and `test_selector.py` need the real
tokenizer; without it they SKIP rather than guessing. **Fetch these before you
believe a green run** — a skipped assertion protects nothing, and this exact
skip was measured hiding two mutation survivors (D-0062):

```bash
curl -sL https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507/resolve/main/tokenizer.json \
  -o /tmp/qwen3_tokenizer.json
curl -sL https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507/resolve/main/tokenizer_config.json \
  -o /tmp/qwen3_tokcfg.json
```

`test_rag.py` likewise gates 11 assertions on a live EDGAR payload. Public, free,
and it requires a contact-bearing User-Agent (403 without one):

```bash
curl -sS -H "User-Agent: marfin-llm/0.1 (contact@example.com)" \
  "https://data.sec.gov/api/xbrl/companyconcept/CIK0000320193/us-gaap/RevenueFromContractWithCustomerExcludingAssessedTax.json" \
  -o /tmp/xbrl.json
```

`run_all.sh` now counts skips and prints the total unconditionally, including the
zero. If it is not zero, the run is not green no matter what the last line says.

### Running Phase 4 (on the target machine, not here)

**Persian step-by-step guide: `docs/guides/phase-4-windows-setup-fa.md`.**

```bash
# The --extra-index-url is REQUIRED on Windows. PyPI publishes only an sdist
# for llama-cpp-python (VERIFIED), so a plain `pip install` compiles C++ and
# fails without the MSVC C++ toolset -- which is exactly what happened on the
# target machine 2026-08-17 ("No CMAKE_C_COMPILER could be found").
pip install llama-cpp-python psutil \
  --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
python scripts/run_phase4.py --model <path>Qwen3.5-4B-Q5_K_M.gguf
```

The run is ~3.4 h on the target CPU and `run_phase4.py` writes its output file
only **once, at the very end**, so an interruption in hour three loses
everything. RECOMMENDED: split it with `--arms`, which exists for exactly this
("comma-separated subset, for resuming a run"), and give each invocation its own
`--out` — otherwise each command overwrites the previous one's file.

```bash
python scripts/run_phase4.py --model <path> --arms rag   --out evals/results/p4_rag.json    # 0.88 h
python scripts/run_phase4.py --model <path> --arms tools --out evals/results/p4_tools.json  # 1.17 h
python scripts/run_phase4.py --model <path> --arms plain --out evals/results/p4_plain.json  # 1.41 h
python scripts/merge_phase4.py evals/results/p4_*.json --out evals/results/phase4_merged.json
```

Splitting costs **5 extra minutes**, not more: MEASURED per-invocation fixed
overhead is 148 s (model load 0.95 s + TTFT probe 118.68 s + decode probe 28.6 s,
read from the `latency` block of the user's own run), paid 3x instead of 1x.
`rag` runs first because it had the highest truncation rate (6 of 10 = 60 %, vs
plain 38 % and tools 29 %), so a single completed chunk already carries most of
the information about whether the 2048 budget suffices.

MEASURED 2026-08-17: that index serves `llama_cpp_python-0.3.35-py3-none-win_amd64.whl`
(7,086,788 bytes, sha256 `31590ea0...80bb`), which pip selects with no version
pin. The wheel is tagged `py3-none`, contains zero `.pyd` files and binds via
`ctypes`, so it is Python-ABI-independent — the same file resolves for 3.10,
3.12 and 3.13. Visual Studio is **not** required.

Defaults are already correct for the target (`--ctx 16384`, `--threads 6` for the
i5-12400's six physical cores, `--max-tokens 2048`). It writes
`evals/results/phase4_run.json`; that file is the deliverable.

### The chosen model thinks by default, and that broke the safety grader (D-0052)

The user runs `Qwen3.5-4B-Q5_K_M.gguf` (VERIFIED 2026-08-17 by downloading all
3,143,656,608 bytes and hashing them three ways: `sha256sum`, the project's own
`sha256_file()`, and the `GGUF` magic bytes; digest
`8814232b...ad39`). Its GGUF header reports architecture `qwen35` — a hybrid of
24 SSM (Gated DeltaNet) layers and 8 full-attention layers, which is why the KV
cache is only 0.500 GiB at 16K context (COMPUTED) despite a 262,144 declared
context length. Total RSS is ESTIMATED at 3.8–4.2 GiB and is **not** recorded as
measured.

It **thinks by default and cannot be told not to** — the `/think` and `/nothink`
switches of Qwen3 do not work in this release (VERIFIED from the model card).
Rather than assume the harness tolerated that, the graders were run against
realistic thinking output. Two defects were MEASURED:

1. **A safety false pass.** A reply whose reasoning said *"I cannot provide
   investment advice"* and whose visible answer said *"Buy 500 shares of AAPL
   right now"* scored `is_abstention() == True`. The most dangerous output this
   project can emit was being recorded as a clean refusal, on a *safety*
   threshold.
2. **A false quality failure.** A 256-token budget spent entirely inside
   `<think>` produced no answer at all, and was graded as a wrong answer —
   charging a harness budget limit to the model.

The fix splits reasoning from the answer inside `ModelRunner.generate()`, not at
each grading call site, so no consumer can forget it; an **unterminated**
`<think>` returns an empty answer rather than the reasoning or a half sentence,
and is counted and reported separately as a budget failure. The raw text is kept
in `raw_output` so a human can audit the split. The default budget rose 256 →
768 → **2048** (D-0057; the 768 run lost 20 of 52 answers). It lives in a single
`DEFAULT_MAX_TOKENS` constant that both `ModelRunner` and the argparse default
read, because lowering one of the two former copies SURVIVED the entire suite.
The run always prints the tally, including when it is zero:

```
REASONING MODE  (thinking)
  replies containing <think>      : 31 of 31
  answers LOST to truncation      : 0
```

35 new mutations reopen each defect — reasoning left in the graded answer, a
truncated block graded as an answer, the counters not restored around the
latency probe, the default budget reverted to 256, the tally printed only when
non-zero. All 35 were killed. Two of them survived the first battery run and
both were *weak tests, not wrong code*: an `int`-only type-guard test passes
against a guardless function because `"<think>" in 123` raises `TypeError` by
itself (a **list** is the case that separates them), and a counter-restoration
test whose counters were already zero cannot distinguish restoring from zeroing.

Do **not** use `scripts/run_baseline.py`. It has 9 MEASURED defects — among them
grading peak RSS against **12.0 GiB when the approved ceiling is 6.0** (it would
have printed PASS at twice the approved limit), ignoring `expected_value`,
`expected_tool` and `tolerance` entirely, and crashing on Persian output on a
`cp1252` console *after* the model had already been loaded. It is retained only
for the audit trail.

This sandbox cannot load any candidate model (Phase 0 finding F1; and MEASURED
2026-08-16, `pip install llama-cpp-python` itself fails here for lack of disk),
so no throughput figure is ever reported from here.

### Reproducing the estimates

```bash
python3 scripts/size_from_config.py --dir configs/model-cards --ram 16 --ctx 16384
python3 scripts/throughput_ceiling.py --mem DDR4-3200
python3 scripts/measure_tokenizer_efficiency.py --dir /tmp/tok
```

### Open questions

- **Q8** — if measured decode is below 9 tok/s: fall back to Qwen3-1.7B, accept
  slower output and lean on RAG, or re-quantize? **The trigger has MEASURED true
  at every budget tested — 3.32 tok/s at 512, 4.28 at 2048, 4.21 at 3072 — all
  far below the floor of 9.** (Earlier versions of this entry read "twice and
  downward"; that was wrong, and the direction was never the point: no reading
  has come close to 9.) The decision is still open, but option (b), *"lean on
  RAG"*, is now **close to refuted** — not on grading evidence but on a harder
  fact: at 3072 tokens the rag cases produced **no visible answer at all**,
  because the model never finishes thinking (D-0085, R35). An arm that cannot
  emit an answer cannot be leaned on. Row 7 of the work plan was the intended
  route to answering Q8; on current evidence it would spend ~10.4 h reproducing
  that same outcome, so the **forced-closed-`<think>` test (one generation) comes
  first**. See R35.
- **Q9** — **RESOLVED** (D-0026): a deterministic bilingual family router,
  recall-first. MEASURED — mean subset 2,552 tokens (15.6% of 16K) versus 8,920
  for all 84 schemas; recall 24/24 across the eval and held-out sets.

## API Providers and the Project Panel

Added 2026-08-27 because running a 4B model on six CPU cores measurably does not
meet the approved bar: **3.62–4.38 tok/s against a floor of 8**, and **48.6–49.9 s
to first token against a ceiling of 3.0 s**. No prompt change fixes that.

**The local model was not replaced.** `--provider` defaults to `local`
everywhere, nothing was removed, and the panel lists the local model *above* the
providers with its real MEASURED numbers — including the failures.

### The fourteen

| Provider | Env var | Cost class |
|---|---|---|
| `local` | — | free, default |
| `agentrouter` | `AGENTROUTER_API_KEY` | UNKNOWN → billable (OpenAI dialect) |
| `agentrouter-anthropic` | `AGENTROUTER_API_KEY` | UNKNOWN → billable (Anthropic dialect) |
| `groq` | `GROQ_API_KEY` | documented free tier |
| `google` | `GEMINI_API_KEY` | documented free tier |
| `cerebras` | `CEREBRAS_API_KEY` | documented free tier |
| `openai` | `OPENAI_API_KEY` | paid |
| `anthropic` | `ANTHROPIC_API_KEY` | paid |
| `xai` | `XAI_API_KEY` | paid |
| `openrouter` | `OPENROUTER_API_KEY` | UNKNOWN |
| `mistral` | `MISTRAL_API_KEY` | UNKNOWN |
| `deepseek` | `DEEPSEEK_API_KEY` | UNKNOWN |
| `together` | `TOGETHER_API_KEY` | UNKNOWN |
| `custom` | `CUSTOM_API_KEY` | UNKNOWN (needs `--base-url`) |

`free_tier` is **tri-state**: `True`, `False`, or `None` for UNKNOWN. The spend
gate treats UNKNOWN as **billable** — an unknown cost is not a free cost.

**AgentRouter is registered twice on purpose.** Its own portal FAQ states,
VERBATIM: *"Anthropic compatible (Claude family): https://co.agentrouter.org, no
/v1. OpenAI compatible (GPT etc.): https://co.agentrouter.org/v1, /v1 required.
Do not mix them."* One entry would leave you one wrong base URL away from a
silent failure; two entries make the mistake unreachable. Both share one key.

The circulating **"$200 free credits"** claim is **not** recorded as a free tier.
It traces to a gist carrying referral links (`?aff=...`) and a *different host*
than the portal documents, so `free_tier` is `None` and the spend gate refuses
both entries without `--allow-paid`.

**No quota is recorded anywhere in this project.** A search on 2026-08-27
returned figures that contradict each other for the same provider on the same
day, so the registry records the disagreement and points at the provider's own
limits page instead of manufacturing a number.

### Panel

```
python scripts/panel.py                 # auto-detects the console
python scripts/panel.py --ascii --no-colour
python scripts/panel.py --check groq    # one provider, in detail
python scripts/panel.py --json          # machine-readable
```

Three tiers, selected by **trial-encoding** box-drawing characters rather than
by pattern-matching the code page name. Honours `NO_COLOR` and `FORCE_COLOR`.
It reads only — no socket, no quota, no file written — and is deliberately
**not** a launcher: a panel one keystroke from a 3.6-hour CPU burn is a trap.

### Guardrails on remote use

- `spend_gate()` refuses paid/UNKNOWN providers unless `--allow-paid` is passed,
  **before** anything is spent. Loopback base URLs are exempt so it never cries
  wolf on the user's own llama server.
- `--model-id` is **mandatory** for remote providers. A guessed model name burns
  a free-tier request to discover it was wrong.
- For any remote provider, four hardware thresholds are forced to `PENDING`, the
  label becomes `MEASURED_REMOTE_API`, and `measures_local_hardware` is `False`.
  **An API run can never be laundered into evidence about the i5-12400.**
- Keys come from environment variables only — never a file, never a CLI argument
  that lands in shell history. All error text passes through `redact()`, verified
  against 11 realistically-shaped keys including prefix-less ones.

### Verification

- `tests/test_llm_providers.py` — 248 assertions.
- `tests/mutate_llm_providers.py` — 41 mutants: **39 killed, 2 proved
  equivalent, 0 survived, 0 skipped** (re-measured 2026-08-30; this line
  previously read "31 mutants: 29 killed", which had drifted as the battery
  grew — the same staleness class as the aggregate above, found only because
  the battery was actually re-run rather than quoted). The first run killed only 21 and let ten
  survive *against a suite printing "195 passed, 0 failed"* — including a mutant
  that relabelled the user's MEASURED hardware failure as `PASS`, and one that
  shortened a border by one column, the exact defect that had already shipped.
- Full regression: **18 suites, 3,265 assertions, 0 failed, 0 skipped.**

## Project Analysis Tools

### `tools/graph_project.py` — structure and dependency graph

```
python3 tools/graph_project.py                      # report to stdout
python3 tools/graph_project.py --json graph.json    # raw graph, MEASURED_STATIC_AST
```

Built for Request 40, which asked that
[graphify](https://github.com/Graphify-Labs/graphify) inform our understanding of
this project. graphify was cloned and read, then **measured**:
`graphify.extract.extract()` raises `ImportError: tree-sitter is not installed`,
and its dependency set is numpy, rapidfuzz and ~27 tree-sitter grammars.
marfin-llm is 89 `.py` files and nothing else that is source, and stdlib `ast`
parses all of `src/` with **zero** failures.

graphify's value is breadth — one tool that reads 27 languages. This project
needs exactly one of them. So the tool borrows graphify's **ideas** (the
detect → extract → build → cluster → analyze → report pipeline, its node schema,
and its `EXTRACTED` / `INFERRED` / `AMBIGUOUS` edge-confidence labels, which
parallel this project's own VERIFIED/MEASURED/COMPUTED/ESTIMATED/UNKNOWN
discipline) and implements them against `ast`.

Current output (see `docs/analysis/structure-analysis-2026-08-27.md`):

| Quantity | Value |
|---|---|
| modules / nodes / edges | 91 / 728 / 7,724 |
| parse errors | **0** |
| import cycles | **none** |
| edge confidence | 24.6 % EXTRACTED, 25.3 % INFERRED, **50.0 % AMBIGUOUS** |

The 50 % AMBIGUOUS figure is honest, not a defect: a name defined in more than
one module cannot be resolved statically, and a graph that hid which edges were
guesses would be worse than no graph.

**The tool found a real problem on its first run — in itself.** It reported
`tests._harness` as having no internal edges, which is false (16 suites import
it). 17 import edges were being discarded because `from _harness import x` names
the module `_harness` while the tool ids the file as `tests._harness`. Fixed, and
every recovered edge is labelled `INFERRED` because it rests on a `sys.path`
assumption rather than on the AST.

That finding led to probing `tests/_harness.py`, the highest-fan-in module in the
tree, which had no test and no mutation battery. **No false-pass mode exists**:
`check(nan, nan)` fails, and `check_raises` on a non-raising function fails. The
3,265-assertion base is trustworthy.

### `tools/grade_persian.py` — R10 human grading

**Both arguments are mandatory**; running the script bare prints an argparse
usage error, which is the tool working, not a defect. Run it from the **repo
root** so the relative paths below resolve:

```bash
# start / resume interactive grading
python3 tools/grade_persian.py --input evidence/phase4_merged.json --output grades.json

# progress report only, no prompts
python3 tools/grade_persian.py --input evidence/phase4_merged.json --output grades.json --report

# one arm at a time
# (NOTE: an earlier version of this line called rag "the only arm with 0
#  fabrications". That rested on the harness `fabricated` field and is
#  WITHDRAWN -- human grading found 2 UNSUPPORTED cases in rag, which scored
#  ZERO GOOD across its 10 cases. See D-0081 / R29.)
python3 tools/grade_persian.py --input evidence/phase4_merged.json --output grades.json --arm rag
```

Windows PowerShell, from the repo root, is identical apart from `python`:

```powershell
python tools\grade_persian.py --input evidence\phase4_merged.json --output grades.json
```

The evidence file lives at **`evidence/phase4_merged.json`** and is committed,
because it was previously only an out-of-tree upload: the tool shipped in the
repo while the one file it cannot run without did not, so a fresh clone or
backup could not use it. *A tool is not usable until its input travels with it.*

MEASURED end-to-end before documenting: 52 cases load (rag 10 / tools 21 /
plain 21), 15 pre-marked `no_output`, **37 awaiting a human verdict**; grading
two cases and quitting leaves 17 recorded / 35 remaining on resume.

R10 (Persian generation quality) is the one Phase 4 threshold no automated check
can decide. **This tool grades nothing.** It shows each case's question, rubric
and actual output, records a *human* verdict, and reports counts. A heuristic
fluency score would be indistinguishable from a measurement in any later summary,
and R10 would drift from UNKNOWN to a fabricated PASS.

- Input is opened **read-only**; grades go to a separate file.
- Saved after **every** verdict, and resumable.
- Grades are keyed `arm::id`, because the `tools` and `plain` arms ask the **same
  21 questions** — 52 cases hold only 31 distinct ids, so keying by `id` alone
  let one arm's verdict silently overwrite another's.
- The 15 cases with empty output are marked `no_output`, counted separately and
  **never as passes**.
- It does **not** set the R10 verdict, and never touches
  `phase_4/measurements_recorded`.

## Usage

Load `SYSTEM_PROMPT.md` as the system prompt for the orchestrating assistant.
It begins at Phase 0 and will not advance phases without explicit approval
(`Approve Phase N and continue to Phase N+1` / `تایید فاز N و ادامه به فاز N+1`).

## License

No license declared yet. Base-model, dataset, and data-source license
compatibility must be verified per Sections 3, 14, and 16 of the prompt before
any redistribution.
