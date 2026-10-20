# Architecture (Phase 9, D-0126)

```
 user ──► orchestrator (scripts/run_phase4.py today; src/llm/*)
            │  renders the ChatML prompt itself (think block pre-closed, D-0091)
            │  sends it raw: in-process llama.cpp | Ollama raw | LM Studio completions
            ▼
         model (Qwen3.5-4B Q4_K_M) ──► reply
            │
            ├─ tool calls ──► src/tools/registry.py ──► src/calc/*   (deterministic; executed by the
            │                  (selector picks ≤ ~50 of 85 schemas)    orchestrator, result handed back)
            ├─ RAG ─────────► src/rag/{retrieval,rerank,citations}.py (evidence shown, claims verified)
            ├─ guards ──────► src/safety/untrusted.py (injection defang), execution guard (F1)
            └─ display ─────► src/llm/style.py plain_math (LaTeX → plain text), continuation on cut-off
                                  
 market data ─► src/market/{quotes,csv_import,webhooks,screenshot,alpha_vantage}.py
                 (labelled, immutable; webhooks are notifications only)

 execution  ─► src/execution/mode.py      (4 modes from a config FILE, never from the model)
              src/execution/broker_tools.py (preview only; every live write refuses)
              src/execution/paper.py     (Phase 8A paper engine + simulated venue)

 maintenance ─► src/maintenance/{monitor,release}.py, tools/maintain.py
                 (Phase 10: offline checks, release manifests, rollback; reads the paper audit log only)
```

**Separation (SS.5.6) is enforced by the import graph, and tests assert it:**
- `src/execution/` imports nothing from `market`, `rag`, `tools` or `llm`.
- `src/market/webhooks.py` imports nothing from `execution`.

**Trust boundaries:**
- The mode comes only from `~/.marfin/execution.conf`.
- A commit needs a HUMAN principal plus a single-use token.
- The venue accepts only engine-signed tickets.
- Live trading is refused while any SS.6.1 prerequisite is unmet. 10 of the 12 are unmet; the two met ones are
  configuration lines.

**Evaluation pipeline:**
```
run_phase4 (per arm) → merge_phase4 → regrade_eval / regrade_citations → grade_merged
→ attribute_failures
```
`compare_quants`, `compare_style` and `apply_display_layer` compare or post-process runs without re-running the
model.
