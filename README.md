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
| `DECISIONS.md` | Append-only decision log (D-0001 … D-0050). |
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
| `docs/guides/phase-4-windows-setup-fa.md` | **Persian** setup guide for running Phase 4 on Windows 11. |
| `src/calc/returns_risk.py` | Returns and risk (21 fns), stdlib only. |
| `src/calc/valuation.py` | DCF, DDM, multiples, margins, leverage (26 fns). |
| `src/calc/technicals.py` | RSI, MACD, ATR, Bollinger, ADX, VWAP … (13 fns). |
| `src/calc/fixed_income.py` | Bond pricing, YTM, duration, convexity, DV01 (11 fns). |
| `src/calc/derivatives.py` | Black-Scholes, binomial, implied vol, Greeks (13 fns). |
| `src/calc/persian_num.py` | Persian/Arabic numeral parsing and formatting. |
| `src/tools/registry.py` | Whitelisted dispatch for 84 tools; no execution capability. |
| `evals/bilingual_eval_v1.jsonl` | 21-case bilingual evaluation set. |
| `tests/` | 476 assertions across 6 suites, plus a 56-defect mutation battery. |
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
| Status | **TOOLING COMPLETE — awaiting the user's measurement.** Not complete, not partially measured. |
| Route | **A — the user's own machine** (approved 2026-08-16) |
| Next | The user runs `scripts/run_phase4.py` on the i5-12400 and returns `evals/results/phase4_run.json` |
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
| Financial RAG pipeline (9 modules) | **VERIFIED** — 224 assertions, 99 mutations, 0 survivors |
| Source access terms | **ENFORCED** — `check_access()` gates every ingestion entry point |
| EDGAR period-mixing / restatement hazards | **MEASURED** on live data (117 facts, 46 restated) |
| Persian numeral parsing | **VERIFIED** by execution |
| Chat template + 84 tool schemas | **VERIFIED** by rendering |
| No execution capability | **VERIFIED** by test |
| Tool-schema context cost | **MEASURED** — 8,920 tokens = 54.4% of 16K |
| Decode speed | **ESTIMATED** ~14.7 tok/s — not yet measured |
| Persian generation quality | **UNKNOWN** — risk R10 |
| Tool-selection accuracy over 84 tools | **UNKNOWN** — risk R17 |
| Dense vector retrieval | **DOES NOT EXIST** — lexical + structured only (D-0030) |
| RAG behaviour with a live model | **UNKNOWN** — risk R21 |
| Market data layer (quotes, CSV, webhooks, AV) | **VERIFIED** — 294 mutations, 0 survivors |
| Execution layer (mode, brokers, broker tools) | **VERIFIED** — 139 mutations, 0 survivors |
| Level 3 visual surface (screenshot) | **VERIFIED** — 89 mutations, 0 survivors |
| Live broker write reachable by any route | **NO** — 62 adversarial attempts, 62 refused |
| Screen capture / OCR in this runtime | **DOES NOT EXIST** — 12-entry capability probe |
| Alpha Vantage against the real API | **UNKNOWN** — no live fetch was ever performed |
| Permitted market-data storage timeframe | **UNKNOWN** — risk R22; data treated as non-persistable |

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

**2,772 assertions pass across 16 suites, and 0 are SKIPPED. That is not the
claim.** A passing suite proves nothing on its own. The claim is **920 seeded
defects across 11 batteries, 915 killed, 5 documented equivalents, 0 survivors,
0 skips** — every guard was deliberately broken and the
suite caught it — plus **153 adversarial attempts, 153 refused, 0 allowed,
0 crashed.**

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
./tests/run_all.sh              # 2,772 assertions across 16 suites + 7 probes (~6 s)
./tests/run_all.sh --mutate     # + 920 seeded defects across 11 batteries (~205 s)

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
  slower output and lean on RAG, or re-quantize? Deferred until measured.
- **Q9** — **RESOLVED** (D-0026): a deterministic bilingual family router,
  recall-first. MEASURED — mean subset 2,552 tokens (15.6% of 16K) versus 8,920
  for all 84 schemas; recall 24/24 across the eval and held-out sets.

## Usage

Load `SYSTEM_PROMPT.md` as the system prompt for the orchestrating assistant.
It begins at Phase 0 and will not advance phases without explicit approval
(`Approve Phase N and continue to Phase N+1` / `تایید فاز N و ادامه به فاز N+1`).

## License

No license declared yet. Base-model, dataset, and data-source license
compatibility must be verified per Sections 3, 14, and 16 of the prompt before
any redistribution.
