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
| `PROJECT_STATE.json` | Phase-gate state tracker. Current phase: 2. |
| `DECISIONS.md` | Append-only decision log (D-0001 … D-0018). |
| `configs/capability-manifest.yaml` | Probe-derived capability inventory. |
| `configs/model-cards/` | Verbatim official `config.json` for every Phase 1 candidate. |
| `docs/phase-reports/` | Per-phase review reports. |
| `scripts/size_from_config.py` | Memory sizing computed from the committed configs. |
| `scripts/measure_tokenizer_efficiency.py` | Persian vs English tokenizer cost measurement. |
| `scripts/estimate_model_footprint.py` | Generic sizing tool (superseded for Phase 1 by `size_from_config.py`). |
| `scripts/throughput_ceiling.py` | Bandwidth-bound decode ceiling for the target RAM. |
| `scripts/run_baseline.py` | On-target baseline harness (speed, RSS, eval set). |
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
| Current phase | **3A — Market Data, TradingView, and Broker Design** |
| Status | PASS — **awaiting Phase 4 approval** |
| Next | Phase 4 — RAG and Tool-Enabled Evaluation (**not started; NOT startable in this sandbox**) |
| Active mode | `ANALYSIS_ONLY` |
| Live trading | `DISABLED` — 10 of 12 SS.6.1 prerequisites unmet (MEASURED); unreachable by configuration |
| TradingView connector level | 0 (display only; extraction refused) |
| Market data provider | Alpha Vantage **free tier only** (D-0040) — no paid feed |

**Why Phase 4 cannot start here:** it compares a plain baseline against RAG+tools,
which requires a running model. MEASURED in this sandbox: no model file on disk,
`llama_cpp` absent, **0.96 GiB RAM available** against a 0.85 GiB minimum weights
footprint before any runtime overhead. This is stated rather than silently
skipped; see `docs/phase-reports/phase-3a.md` §7.

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
| Financial RAG pipeline (9 modules) | **VERIFIED** — 194 assertions, 80 mutations, 0 survivors |
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

**2,187 assertions pass across 15 suites. That is not the claim.** A passing
suite proves nothing on its own. The claim is **692 seeded defects across 10
batteries, 0 survivors, 0 skips** — every guard was deliberately broken and the
suite caught it — plus **153 adversarial attempts, 153 refused, 0 allowed,
0 crashed.**

The batteries have repeatedly found tests that could not fail:

- At 311/311 green, three formulas were correct but **unverified** (`convexity`
  `f²`, `delta` `e^-qT`, `vega` `sqrt(T)`) — each tested only at a value where
  the missing factor equals 1.
- `check_raises()` defaulted to `Exception`, accepting a **crash** as a refusal.
  **106 of 113** assertions across all suites relied on that default (D-0036).
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

Reproduce: `./tests/run_all.sh --mutate`
See `docs/phase-reports/phase-2a.md` and `docs/phase-reports/phase-3.md`.

### Running the tests

```bash
./tests/run_all.sh              # 2,187 assertions across 15 suites + 2 probes (~5 s)
./tests/run_all.sh --mutate     # + 692 seeded defects across 10 batteries (~105 s)

python3 tests/test_valuation.py       # or any single suite
python3 tests/probe_broker_tools.py   # adversarial: try to reach a broker write
python3 tests/probe_screenshot.py     # adversarial: try to forge consent / launder a licence
python3 tests/mutate_screenshot.py    # a single battery on its own
```

The token-cost check in `test_tools.py` needs the real tokenizer; without it
that one assertion SKIPs rather than guessing:

```bash
curl -sL https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507/resolve/main/tokenizer.json \
  -o /tmp/qwen3_tokenizer.json
curl -sL https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507/resolve/main/tokenizer_config.json \
  -o /tmp/qwen3_tokcfg.json
```

### Running the baseline (on the target machine, not here)

```bash
pip install llama-cpp-python psutil
python scripts/run_baseline.py --model <path>.gguf --ctx 16384 --threads 6
```

This sandbox has 0.60 GiB available and cannot load any candidate model
(Phase 0 finding F1), so no throughput figure is ever reported from here.

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
