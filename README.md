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
| `PROJECT_STATE.json` | Phase-gate state tracker. Current phase: 1. |
| `DECISIONS.md` | Append-only decision log (D-0001 … D-0012). |
| `configs/capability-manifest.yaml` | Probe-derived capability inventory. |
| `configs/model-cards/` | Verbatim official `config.json` for every Phase 1 candidate. |
| `docs/phase-reports/` | Per-phase review reports. |
| `scripts/size_from_config.py` | Memory sizing computed from the committed configs. |
| `scripts/measure_tokenizer_efficiency.py` | Persian vs English tokenizer cost measurement. |
| `scripts/estimate_model_footprint.py` | Generic sizing tool (superseded for Phase 1 by `size_from_config.py`). |
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
| Current phase | **1 — Hardware and Base-Model Selection** |
| Status | PASS (provisional on Phase 2 Persian generation test) |
| Next | Phase 2 — Environment and Runtime Setup (awaiting approval) |
| Active mode | `ANALYSIS_ONLY` |
| Live trading | `DISABLED` |
| TradingView connector level | 0 |

### Target (user-supplied)

16 GiB RAM · Intel Core i5-12400 (6 cores / 12 threads, no GPU) · Windows 11 ·
16K context · Iranian market data descoped · execution ambition through live
trading (Phase 11).

### Selected baseline

| Role | Model | Licence | Total @16K |
|---|---|---|---|
| **Primary** | `Qwen/Qwen3-4B-Instruct-2507` | apache-2.0 | 5.12 GiB (43% of budget) |
| Alternative 1 | `microsoft/Phi-4-mini-instruct` | mit | 4.77 GiB |
| Alternative 2 | `HuggingFaceTB/SmolLM3-3B` | apache-2.0 | 3.46 GiB |
| Fallback | `Qwen/Qwen3-1.7B` | apache-2.0 | 3.50 GiB |

`Qwen/Qwen2.5-3B-Instruct` was **disqualified**: its `qwen-research` licence is
non-commercial only (D-0010). Llama-3.2 and Gemma-3 were excluded as
manual-access gated.

Full reasoning: `docs/phase-reports/phase-1.md`.

### Reproducing the Phase 1 numbers

```bash
python3 scripts/size_from_config.py --dir configs/model-cards --ram 16 --ctx 16384
python3 scripts/measure_tokenizer_efficiency.py --dir /tmp/tok
```

### Open questions

- **Q6** — RAM type/speed (DDR4-3200 vs DDR5-4800)? ~1.5× tokens/sec swing on a
  GPU-less box; blocks a defensible Phase 2 speed threshold.
- **Q7** — Test Phi-4-mini's Persian in Phase 2 despite its undeclared support?

## Usage

Load `SYSTEM_PROMPT.md` as the system prompt for the orchestrating assistant.
It begins at Phase 0 and will not advance phases without explicit approval
(`Approve Phase N and continue to Phase N+1` / `تایید فاز N و ادامه به فاز N+1`).

## License

No license declared yet. Base-model, dataset, and data-source license
compatibility must be verified per Sections 3, 14, and 16 of the prompt before
any redistribution.
