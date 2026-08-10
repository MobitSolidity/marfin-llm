# Phase 0 Review — Initialization and Capability Discovery

Project: marfin-llm
Date: 2026-08-10
Prompt version governing this phase: SYSTEM_PROMPT.md v2.0
Active mode: `ANALYSIS_ONLY` · Live trading: `DISABLED` · TV connector level: 0

---

## Status

**CONDITIONAL PASS**

Capability discovery is complete and honest. Phase 0's own acceptance criteria
are met. The condition is that **three user inputs are still missing**, and one
discovered constraint (sandbox RAM) permanently changes *where* later phases can
run. Neither blocks Phase 1, which is research and does not need to load a model.

---

## 1. Project Restatement (Sec 28.1)

Build a compact, local, CPU-only bilingual Persian–English financial LLM plus
its surrounding tool ecosystem: financial RAG, a deterministic calculation
engine, MCP/tool orchestration, gated TradingView integration, and gated broker
connectivity. Ship as GGUF (Q4_K_M primary, Q5_K_M higher-accuracy) runnable via
llama.cpp / Ollama / LM Studio. Adapt an existing open-weight model; do not
train from scratch. Live trading is off by default and is never self-enabled.

---

## 2. Model vs. Runtime Capability Separation (Sec 28.2)

This distinction drives the whole architecture and is the most common source of
false expectations, so it is stated explicitly:

| Belongs to the **model** (the GGUF file) | Belongs to the **runtime** (surrounding code) |
|---|---|
| Persian/English financial fluency | Network access |
| Reasoning, summarization, explanation | Market data and quotes |
| Choosing *which* tool to call | Actually executing the tool |
| Interpreting a verified tool result | Broker access, credentials, order placement |
| Scenario generation, uncertainty language | File I/O, RAG retrieval, exact arithmetic |

A GGUF file contains weights. It has no network, no credentials, no market data,
no execution ability. Every external capability is supplied by the orchestrator
and must be independently verified — which is what this phase did.

---

## 3. Assumptions (Sec 27.1)

| # | Assumption | Label | Basis / how it gets resolved |
|---|---|---|---|
| A1 | End-user deployment target is ~16 GB RAM, modern 6–8 core CPU, no GPU | **ASSUMPTION** | Prompt Sec 2 default fallback. Resolved by user answer Q1. |
| A2 | Target context length 8K | **ASSUMPTION** | Prompt Sec 2 default. Resolved by Q2. |
| A3 | Persian-market data (Codal/TSETMC) is in scope | **ASSUMPTION** | Implied by "bilingual". Contradicted by finding F3. Resolved by Q3. |
| A4 | k-quant bits-per-weight ≈ 4.85 (Q4_K_M), 5.70 (Q5_K_M), 8.50 (Q8_0) | **ESTIMATED** | llama.cpp nominal averages; exact size is per-model. Verified in Phase 7 by producing real artifacts. |
| A5 | GQA layer/kv-head counts used in sizing are typical for the class | **ESTIMATED** | Per-model actuals verified in Phase 1. |
| A6 | No fine-tuning is needed until proven otherwise | **DECISION** | Prompt Sec 16 mandatory policy: baseline → tools → RAG → *only then* consider tuning. |

---

## 4. Capability Discovery — Measured Results (Sec 28.3–28.5)

All rows below are **MEASURED** in this sandbox on 2026-08-10.
Full detail: `configs/capability-manifest.yaml`.

### 4.1 The six capability classes Section 28.5 requires me to report on

| Capability class | Actually available? | Evidence |
|---|---|---|
| **File tools** | ✅ YES | Read/Write/Edit/Glob/Grep + POSIX fs verified |
| **Network tools** | ✅ YES | HTTP 200 from pypi, huggingface, github, tradingview |
| **Search tools** | ✅ YES | `web_search` / `crawler` agent tools present |
| **Market-data tools** | ❌ NO | No licensed adapter; no quotes of any kind |
| **Filing tools** | ⚠️ PARTIAL | SEC EDGAR ✅ (US only); Codal ❌ (TCP blocked) |
| **Macro tools** | ⚠️ DEGRADED | FRED reachable, returns HTTP 400 pending an API key |

### 4.2 Host resources — MEASURED

| Resource | Value |
|---|---|
| OS | Debian GNU/Linux 13 (trixie), kernel 6.1.155, x86_64 |
| CPU | Intel Xeon @ 2.50 GHz, **2 cores** |
| RAM total / available | **0.96 GiB / 0.60 GiB** |
| Swap | 0.12 GiB |
| Disk available | 20 GiB |
| Toolchain | Python 3.13.13, Node 22.23.2, gcc 14.2.0, make 4.4.1 |
| Absent | `cmake`, `sqlite3` |
| Math libs | numpy 2.3.5, pandas 2.2.3, scipy 1.17.1, sklearn 1.6.1 |
| ML libs | torch, transformers, sentence_transformers, faiss, rank_bm25 — **all MISSING** |
| LLM runtimes | ollama, llama-cli, llama-server, llama-cpp-python, lms — **all MISSING** |

---

## 5. Four Findings That Change the Plan

### F1 — This sandbox cannot run any in-scope model *(severity: HIGH, structural)*

Deterministic sizing (`scripts/estimate_model_footprint.py`), formula
`bytes = params × bpw / 8`:

| Class | Q4_K_M | Q5_K_M | Q8_0 | vs. 0.60 GiB available |
|---|---|---|---|---|
| ~1.5B | 0.85 GiB | 1.00 GiB | 1.48 GiB | ❌ does not fit |
| ~3B | 1.69 GiB | 1.99 GiB | 2.97 GiB | ❌ does not fit |
| ~4B | 2.26 GiB | 2.65 GiB | 3.96 GiB | ❌ does not fit |
| ~7B | 3.95 GiB | 4.64 GiB | 6.93 GiB | ❌ does not fit |

Even the smallest artifact's *weights alone* exceed available RAM, before KV
cache or activations. **Consequence:** this environment is an *authoring* box,
not an *execution* box. Phases 2, 7, 8, and 8A require real target hardware or a
larger machine. I will not fabricate benchmark numbers here — per Sec 20.4,
estimated performance must never be presented as measured.

**Good news:** the same math shows the *user's* assumed 16 GB target is
comfortable. A 4B model at Q4_K_M with a 32K context lands ≈ 7.36 GiB resident
(2.26 weights + 4.50 KV + 0.6 runtime), leaving substantial headroom. The
project premise is sound; only this sandbox is undersized.

### F2 — SEC EDGAR works, but only with a compliant User-Agent *(severity: LOW, actionable)*

The first probe returned HTTP 403 and would naively be logged as "blocked."
Re-probing `data.sec.gov` with a contact-bearing User-Agent returned **HTTP 200**.
SEC policy mandates a declared UA and ≤10 req/sec. The adapter must hardcode
both. Recording this as "blocked" would have wrongly eliminated the single best
primary-source filing feed in the project.

### F3 — Persian market/filing data is network-blocked *(severity: HIGH, scope-defining)*

`codal.ir` and `tsetmc.com` both resolve in DNS (185.117.205.17 / 94.182.113.115)
but TCP:443 is unreachable — an egress block, not a naming failure.

The important distinction, which I want to be precise about rather than
alarmist: this blocks Persian **data ingestion**. It does **not** block Persian
**language quality**, which is a property of the base model and evaluation set,
and is unaffected. Conflating the two would misdiagnose the project. So the
bilingual mandate survives; the Iranian-market-data ambition is what is at risk,
and Q3 below asks you to decide its priority.

### F4 — Everything execution-adjacent is correctly unavailable *(severity: NONE — by design)*

No broker adapter, no credentials, no market feed, no TradingView connector
(level 0), no secret vault. This is the intended Section 6.1 posture, recorded
so it cannot later be mistaken for an oversight. Note that `tradingview.com`
returning HTTP 200 means *the website is reachable* — it is **not** a connector
and is not logged as one.

---

## 6. Risk Register

| ID | Risk | Sev | Likelihood | Mitigation |
|---|---|---|---|---|
| R1 | Sandbox RAM prevents all measurement | High | **Certain** | Phases 2/7/8/8A run on target HW or a larger builder. Label everything else ESTIMATED. |
| R2 | Persian market data unobtainable | High | Certain here | Q3: descope, user-supplied exports, or a permitted intermediary. |
| R3 | Estimated figures mistaken for measured | High | Medium | Mandatory VERIFIED/MEASURED/COMPUTED/ESTIMATED labels on every number. |
| R4 | Base-model license blocks commercial use or redistribution | High | Medium | Phase 1 license gate before any adoption. |
| R5 | Persian tokenizer inefficiency inflates effective context cost | Medium | Medium | Phase 1 explicit Persian tokenization test per Sec 3.27–3.28. |
| R6 | Credential introduced before a vault exists | **Critical** | Low | Hard rule: no secret enters this repo/sandbox until Sec 11 vault exists. |
| R7 | Quantization degrades Persian more than English | Medium | Medium | Phase 7 requires per-language comparison, not a single aggregate score. |
| R8 | Scope creep toward live trading | High | Medium | Phase gates 3A → 8A → 11; write tools stay disabled. |
| R9 | Benchmark license/contamination issues (FinQA etc.) | Medium | Medium | Phase 1/6 license verification + private time-separated eval set. |

---

## 7. Acceptance Criteria (Sec 24, Phase 0)

| Criterion | Result | Evidence |
|---|---|---|
| Assumptions labeled | **PASS** | §3, six labeled entries |
| No invented capabilities | **PASS** | Manifest built from probes only; F2/F4 show negatives kept as negatives |
| Tools identified | **PASS** | `configs/capability-manifest.yaml`, all six Sec 28.5 classes reported |
| Live trading disabled | **PASS** | `live_trading_enabled: false` in state + manifest; no broker capability exists |
| Ready for model research | **PASS** | HuggingFace + web search + fetch reachable; sizing model built |
| Decision log created | **PASS** | `DECISIONS.md` |
| Acceptance thresholds defined | **PASS** | §8 below |
| Risk register | **PASS** | §6, nine entries |

---

## 8. Proposed Acceptance Thresholds

Proposed now so later phases are judged against pre-committed numbers rather
than post-hoc rationalization. **These are proposals — adjust before approving.**

| Metric | Threshold | Verified in |
|---|---|---|
| Model file size (Q4_K_M) | ≤ 4.0 GiB | Phase 7 |
| Peak RSS @ 8K context | ≤ 6.0 GiB | Phase 8 |
| Generation speed on target CPU | ≥ 8 tok/s | Phase 8 |
| Time to first token @ 2K | ≤ 3.0 s | Phase 8 |
| Deterministic-calc correctness | 100% vs. reference | Phase 2 |
| Unsupported-claim rate (RAG on) | ≤ 3% | Phase 4/6 |
| Citation correctness | ≥ 95% | Phase 4/6 |
| Correct abstention when evidence absent | ≥ 90% | Phase 6 |
| Fabricated price/filing/order in release tests | **0 — hard blocker** | Phase 6 |
| Persian fluency regression vs. base | ≤ 2% | Phase 5/7 |
| Tool-call schema validity | ≥ 98% | Phase 2/8 |
| Paper/live environment confusion | **0 — hard blocker** | Phase 8A |

---

## 9. Artifacts Produced

| Path | Purpose |
|---|---|
| `configs/capability-manifest.yaml` | Sec 4 manifest, probe-derived |
| `docs/phase-reports/phase-0.md` | This review |
| `scripts/estimate_model_footprint.py` | Reproducible sizing tool |
| `DECISIONS.md` | Decision log |
| `PROJECT_STATE.json` | Updated to Phase 0 CONDITIONAL PASS |

## 10. Tools Used

| Tool | Purpose | Trust level |
|---|---|---|
| Bash (`uname`,`lscpu`,`free`,`df`) | Host inventory | MEASURED |
| Bash + `curl` | Network egress probes | MEASURED |
| `python3` + importlib | Library availability | MEASURED |
| `python3` | Footprint arithmetic | COMPUTED |
| `git` | Version control | MEASURED |

---

## 11. Decisions Required from You

**Q1 — Target hardware.** RAM, CPU model/cores, OS of the machine that will
actually *run* the model. Drives model-size selection in Phase 1.
*Default if unanswered: 16 GB / 8-core x86-64 / no GPU.*

**Q2 — Context length.** 8K, 16K, or 32K? Costs ≈1.12 / 2.25 / 4.50 GiB of KV
cache for a 4B model. *Default: 8K.*

**Q3 — Persian-market data (most consequential).** Given F3, choose:
- **(a) Descope** Iranian market data. Persian stays a *language* capability;
  quantitative coverage is US/global via SEC + FRED. Lowest risk, fully
  deliverable, and my recommendation.
- **(b) User-supplied exports.** You provide Codal/TSETMC data manually; the
  system ingests files rather than calling blocked endpoints.
- **(c) Investigate a permitted access path** — requires legal review of Codal
  terms per Sec 7/14 before any implementation.

**Q4 — Execution ambition.** Confirm the intended end state:
analysis-only · +backtesting · +paper trading · +live trading (Phase 11).
This determines how much of Sections 6/19 gets built. Nothing changes today
either way — live trading stays disabled regardless.

**Q5 — Where should measurement phases run?** Phases 2/7/8/8A need >0.6 GiB RAM.
Options: your target machine, a larger sandbox, or accept ESTIMATED-only
figures through Phase 7 (not recommended — Sec 26 release criteria require
measured results).

---

## 12. Recommended Next Action

Answer Q1–Q3 (Q4/Q5 can follow), then approve Phase 1 — hardware profiling and
base-model selection. Phase 1 is pure research (HuggingFace + license review +
sizing) and runs fine in this sandbox despite F1, because it loads nothing.

If you answer nothing, I will proceed on defaults A1/A2 and **option (a)** for
Q3, and will label every resulting figure ESTIMATED.

---

## Approval Gate

Phase 0 is complete. I will not continue automatically.

Reply with:
- `Approve Phase 0 and continue to Phase 1` (optionally with Q1–Q5 answers)

or:
- Provide requested revisions.
