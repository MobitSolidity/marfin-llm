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
| Current phase | **2a — Section 5.3 calculation coverage complete (R14 closed)** |
| Status | PASS (engine verified; model half is a verified plan) |
| Next | Phase 3 — Data Pipeline and Financial RAG (awaiting approval) |
| Active mode | `ANALYSIS_ONLY` |
| Live trading | `DISABLED` (no execution code exists) |
| TradingView connector level | 0 |

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
| Calculation engine (84 fns, 5 families) | **VERIFIED** — 476 assertions, 56/56 mutations killed |
| Persian numeral parsing | **VERIFIED** by execution |
| Chat template + 84 tool schemas | **VERIFIED** by rendering |
| No execution capability | **VERIFIED** by test |
| Tool-schema context cost | **MEASURED** — 8,920 tokens = 54.4% of 16K |
| Decode speed | **ESTIMATED** ~14.7 tok/s — not yet measured |
| Persian generation quality | **UNKNOWN** — risk R10 |
| Tool-selection accuracy over 84 tools | **UNKNOWN** — risk R17 |

The mutation battery matters more than the pass count: the suites were at
311/311 green when it found three formulas that were correct but **unverified**
(`convexity` `f²`, `delta` `e^-qT`, `vega` `sqrt(T)`). Each had been tested only
at a value where the missing factor equals 1. See
`docs/phase-reports/phase-2a.md`.

### Running the tests

```bash
./tests/run_all.sh              # 476 assertions across 6 suites
./tests/run_all.sh --mutate     # + 56 seeded-defect mutation battery (~18 s)

python3 tests/test_valuation.py   # or any single suite
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
- **Q9** — how should tools be subset for Phase 3? All 84 schemas consume 54.4%
  of the 16K window before any user input, and RAG needs the same space.
  By family, by a routing step, or by shortening descriptions? (D-0023)

## Usage

Load `SYSTEM_PROMPT.md` as the system prompt for the orchestrating assistant.
It begins at Phase 0 and will not advance phases without explicit approval
(`Approve Phase N and continue to Phase N+1` / `تایید فاز N و ادامه به فاز N+1`).

## License

No license declared yet. Base-model, dataset, and data-source license
compatibility must be verified per Sections 3, 14, and 16 of the prompt before
any redistribution.
