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
| `src/calc/returns_risk.py` | Deterministic returns/risk engine, stdlib only. |
| `src/calc/persian_num.py` | Persian/Arabic numeral parsing and formatting. |
| `src/tools/registry.py` | Whitelisted tool dispatch; no execution capability. |
| `evals/bilingual_eval_v1.jsonl` | 21-case bilingual evaluation set. |
| `tests/` | 99 tests plus a mutation battery. |
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
| Current phase | **2 — Baseline and Deterministic Tools** |
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
| Calculation engine (21 fns) | **VERIFIED** — 99 tests, 13/13 mutations killed |
| Persian numeral parsing | **VERIFIED** by execution |
| Chat template + tool schemas | **VERIFIED** by rendering |
| No execution capability | **VERIFIED** by test |
| Decode speed | **ESTIMATED** ~14.7 tok/s — not yet measured |
| Persian generation quality | **UNKNOWN** — risk R10 |

### Running the tests

```bash
./tests/run_all.sh              # 99 unit tests
./tests/run_all.sh --mutate     # + 13 seeded-defect mutation battery
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

## Usage

Load `SYSTEM_PROMPT.md` as the system prompt for the orchestrating assistant.
It begins at Phase 0 and will not advance phases without explicit approval
(`Approve Phase N and continue to Phase N+1` / `تایید فاز N و ادامه به فاز N+1`).

## License

No license declared yet. Base-model, dataset, and data-source license
compatibility must be verified per Sections 3, 14, and 16 of the prompt before
any redistribution.
