# Phase 1 Review — Hardware and Base-Model Selection

Project: marfin-llm
Date: 2026-08-10
Prompt version governing this phase: SYSTEM_PROMPT.md v2.0
Active mode: `ANALYSIS_ONLY` · Live trading: `DISABLED` · TV connector level: 0

---

## Status

**PASS (with one provisional element)**

A baseline model is recommended on VERIFIED licence and architecture data plus
MEASURED tokenizer cost. The recommendation is explicitly **provisional on
Phase 2 Persian generation testing**, which cannot be run here (Phase 0 finding
F1). Nothing in this phase is blocked; the provisional flag is a labelling
requirement, not an unresolved defect.

---

## 1. What Changed The Answer

Phase 0 assumed memory would be the binding constraint. **It is not.** With the
target now fixed at 16 GiB (D-0009), every serious candidate fits at 16K context
with room to spare — the heaviest uses 43% of a conservative budget.

Two other constraints turned out to be decisive instead:

1. **Licensing** removed the single most memory-efficient 3B model (D-0010).
2. **Persian tokenizer cost** varies by up to **135%** between candidates
   (MEASURED) — and, critically, the cheapest tokenizers belong to models that
   do not claim Persian support at all (D-0011).

The selection is therefore driven by *licence* and *Persian capability*, with
memory acting only as a sanity check.

---

## 2. Deployment Target (VERIFIED — user-supplied, D-0009)

| Property | Value | Consequence |
|---|---|---|
| RAM | 16 GiB | Not binding; ~12 GiB usable after Win11 reserve |
| CPU | Intel Core i5-12400 | 6 P-cores / 12 threads, **0 E-cores** |
| OS | Windows 11 | llama.cpp / Ollama / LM Studio all supported |
| GPU | none | CPU-only; **memory bandwidth**, not FLOPs, is the limit |
| Context | 16,384 | Doubles KV cache vs the 8K Phase 0 default |
| Iran market data | descoped (Q3=a) | Resolves Phase 0 blocker F3 |
| Execution ambition | full, through live trading | Raises the licence bar — see §4 |

The i5-12400 is a favourable CPU-inference part: 6 uniform performance cores
with no E-core scheduling asymmetry, so thread pinning is straightforward.

**UNKNOWN — new question Q6.** RAM type and speed were not specified. On a
GPU-less box, decode speed is bandwidth-bound, and the i5-12400 supports both
DDR4-3200 (~51 GB/s) and DDR5-4800 (~76 GB/s) depending on the motherboard. That
is roughly a **1.5× swing in achievable tokens/sec** and it is the single largest
open variable in the throughput budget. Answer noted as required before Phase 2
sets a tok/s acceptance threshold.

---

## 3. Method and Evidence Discipline

Per §3, secondary sources (blogs, aggregator posts, leaderboards) were **not**
used for any load-bearing claim. Every architectural and licence fact below was
pulled from the vendor's own repository:

- `config.json` via `huggingface.co/<repo>/resolve/main/config.json`
- parameter counts from the HuggingFace safetensors index (`total`)
- licence text from each repo's own `LICENSE` file
- language support from each model card's `language` field

The seven configs are committed verbatim to `configs/model-cards/` so every
number in this report is independently recomputable.

One methodological trap was hit and corrected: `huggingface.co/.../raw/main/`
returns **133-byte Git-LFS pointer files**, not content. Four of six tokenizer
downloads were silently pointers. Detected by file-size inspection and re-fetched
via `/resolve/main/`, yielding real 3.5–17.2 MB tokenizers. Had this gone
unnoticed, the tokenizer measurement would have failed or — worse — produced
numbers from the wrong files.

---

## 4. Licence Screening (VERIFIED) — the first filter

| Model | Licence | Gated | Verdict |
|---|---|---|---|
| Qwen/Qwen3-4B-Instruct-2507 | apache-2.0 | no | **eligible** |
| Qwen/Qwen3-1.7B | apache-2.0 | no | **eligible** |
| Qwen/Qwen2.5-1.5B-Instruct | apache-2.0 | no | **eligible** |
| HuggingFaceTB/SmolLM3-3B | apache-2.0 | no | **eligible** |
| ibm-granite/granite-3.3-2b-instruct | apache-2.0 | no | **eligible** |
| microsoft/Phi-4-mini-instruct | mit | no | **eligible** |
| **Qwen/Qwen2.5-3B-Instruct** | **qwen-research** | no | **DISQUALIFIED** |
| meta-llama/Llama-3.2-3B-Instruct | llama3.2 | **manual** | excluded — gated |
| google/gemma-3-4b-it | gemma | **manual** | excluded — gated |

**Qwen2.5-3B-Instruct is disqualified (D-0010).** Its LICENSE defines
*"Non-Commercial ... for research or evaluation purposes only"* and grants rights
**"FOR NON-COMMERCIAL PURPOSES ONLY"**. This matters more than it first appears:
that model has `num_key_value_heads: 2`, giving it a **0.56 GiB** KV cache at 16K
against 2.25 GiB for Qwen3-4B — it was the most memory-efficient 3B candidate by
a wide margin, and it is unusable.

Because Q4 puts live trading in scope, this project is a plausible commercial
artifact. A research-only licence at the foundation would be a latent legal
defect surfacing at the worst possible time. Note this restriction is
**size-specific**, not a Qwen-wide policy — Qwen3-4B and Qwen3-1.7B are Apache-2.0.

Llama-3.2 and Gemma-3 are excluded for a practical reason rather than a legal
one: both require manual access approval, which cannot be automated and would
stall a reproducible build.

---

## 5. Memory Sizing (COMPUTED from VERIFIED configs)

Reproduce with:
`python3 scripts/size_from_config.py --ram 16 --ctx 16384`

Budget: 12.0 GiB usable = 16 GiB − 4 GiB Windows 11 + applications reserve.
Quantization Q4_K_M @ 4.85 bpw (ESTIMATED), fp16 KV cache, +0.6 GiB runtime
overhead (ESTIMATED).

| Model | Params | L | kv | hd | Weights | KV @16K | Total | % budget |
|---|---|---|---|---|---|---|---|---|
| Qwen3-4B-Instruct-2507 | 4.02B | 36 | 8 | 128 | 2.27 | 2.25 | **5.12** | 43% |
| Phi-4-mini-instruct | 3.84B | 32 | 8 | 128 | 2.17 | 2.00 | 4.77 | 40% |
| SmolLM3-3B | 3.08B | 36 | 4 | 128 | 1.74 | 1.12 | 3.46 | 29% |
| granite-3.3-2b-instruct | 2.53B | 40 | 8 | 64 | 1.43 | 1.25 | 3.28 | 27% |
| Qwen3-1.7B | 2.03B | 28 | 8 | 128 | 1.15 | 1.75 | 3.50 | 29% |
| Qwen2.5-1.5B-Instruct | 1.54B | 28 | 2 | 128 | 0.87 | 0.44 | 1.91 | 16% |
| ~~Qwen2.5-3B-Instruct~~ | 3.09B | 36 | 2 | 128 | 1.74 | 0.56 | 2.90 | 24% (disqualified) |

**Every eligible candidate fits comfortably.** Memory does not decide this.

Two observations worth carrying forward:

- **GQA dominates KV cache, and it is not proportional to model size.** Qwen3-1.7B
  (1.75 GiB KV) has a *larger* cache than SmolLM3-3B (1.12 GiB), despite being
  ~34% smaller, because it uses 8 kv-heads against SmolLM3's 4. Choosing the
  smaller model would *cost* memory here — the opposite of the intuitive result.
- **granite-3.3-2b** achieves a small cache via `head_dim: 64` rather than few
  kv-heads. Note its config omits `head_dim`; the value is derived as
  `hidden_size / num_attention_heads = 2048 / 32 = 64`. The script marks derived
  values explicitly rather than silently assuming the common 128.

Headroom check: even Qwen3-4B at 43% leaves ~6.9 GiB free, which comfortably
absorbs a Q5_K_M upgrade (+0.6 GiB) should Phase 2 quality testing justify it.

---

## 6. Persian Tokenizer Efficiency (MEASURED)

This is the project's **first measured result**. Reproduce with:
`python3 scripts/measure_tokenizer_efficiency.py --dir /tmp/tok`

Corpus: 5 parallel Persian/English financial sentences (445 Persian chars,
522 English chars), encoded with each model's real `tokenizer.json`.
`ratio` = Persian tokens/char ÷ English tokens/char; 1.00 would mean Persian
costs the same as English.

| Tokenizer | Vocab | fa tok | en tok | ratio | Verdict |
|---|---|---|---|---|---|
| Phi-4-mini-instruct | 200,029 | 147 | 108 | **1.60** | acceptable |
| SmolLM3-3B | 128,256 | 150 | 109 | **1.61** | acceptable |
| Qwen2.5 / Qwen3 (shared) | ~151,667 | 278 | 116 | **2.81** | costly |
| granite-3.3-2b | 49,159 | 345 | 128 | **3.16** | costly |

Persian-specific edge cases (token count — lower is better):

| Case | Phi-4-mini | Qwen3 | SmolLM3 | granite |
|---|---|---|---|---|
| ZWNJ compound `می‌شود سه‌ماهه پیش‌بینی` | 9 | 18 | 9 | 20 |
| Persian digits `۱۲۳۴۵۶۷۸۹۰` (10 chars) | 9 | 20 | 9 | 20 |
| Persian decimal `۸٫۴ درصد` | 4 | 7 | 4 | 9 |
| Thousands sep `۱٬۲۳۴٬۵۶۷` | 9 | 16 | 8 | 18 |
| Mixed script `سهام AAPL در NASDAQ` | 7 | 7 | 7 | 11 |

The digits row is the most diagnostic and has a direct financial consequence:
Qwen and granite spend **2 tokens per Persian digit**. Every Persian-numeral
figure in a financial document costs double, and digit-level fragmentation is a
known contributor to arithmetic errors. This reinforces the §7 requirement that
**all arithmetic route to the deterministic calculation engine** rather than
being trusted to the model — a design decision this measurement now supports
with evidence rather than assumption.

Effective 16K context capacity, by language:

| Model | Persian chars @16K | English chars @16K |
|---|---|---|
| Phi-4-mini-instruct | 49,597 | 79,189 |
| SmolLM3-3B | 48,605 | 78,462 |
| Qwen3 family | 26,226 | 73,728 |
| granite-3.3-2b | 21,132 | 66,816 |

A Qwen3 user gets roughly **half** the Persian document capacity of a Phi-4-mini
user at identical context settings. Materially, ~26K Persian characters is still
about 8–12 pages of financial prose per turn — adequate for the RAG-chunked
design in §8, where whole filings are never loaded at once.

---

## 7. The Trap In That Data (VERIFIED — and why the ranking inverts)

Read alone, §6 says: pick Phi-4-mini or SmolLM3.

**That would be the wrong conclusion.** Checking each vendor's declared language
support:

| Model | Vendor `language` field | Persian (`fa`)? |
|---|---|---|
| Phi-4-mini-instruct | `ar, zh, cs, da, nl, en, fi, fr, de, he, hu, it, ja, ko, no, pl, pt, ru, es, sv, th, tr, uk` | **absent** |
| SmolLM3-3B | `en, fr, es, it, pt, zh, ar, ru` | **absent** |
| Qwen2.5-1.5B-Instruct | `en` | **absent** |
| granite-3.3-2b | not declared | unstated |
| Qwen3-4B-Instruct-2507 | not declared on card; Qwen3 family card claims **"100+ languages and dialects"** with strong multilingual instruction-following | **claimed at family level** |

Phi-4-mini enumerates 23 languages, including Arabic and Hebrew — and omits
Persian. That list is specific enough that the omission reads as deliberate
rather than incidental. Microsoft's own card further warns that Phi models are
*"trained primarily on English text and some additional multilingual text"* and
that other languages *"will experience worse performance."*

Its low token ratio is explained by its tokenizer lineage — Phi-4-mini uses the
GPT-4o tokenizer (`AutoTokenizer: Xenova/gpt-4o`, 200K vocab), which encodes
Arabic script efficiently because of broad multilingual *tokenizer* training.
**An efficient tokenizer is a property of the encoder, not evidence of model
competence in the language.** Conflating the two is exactly the failure mode
D-0011 now guards against: a genuinely measured number, applied to the wrong
question.

Qwen3 is the inverse case — it pays ~76% more per Persian character but is the
only eligible family making an explicit broad multilingual claim, and it reports
multilingual benchmark results (MultiIF 70.8, MMLU-ProX 65.1, INCLUDE 67.8) that
Phi-4-mini and SmolLM3 do not match at comparable size.

Given the choice between *cheap-but-probably-can't* and *expensive-but-designed-
for-it*, a bilingual Persian–English product must take the latter. Context cost
can be mitigated with chunking and retrieval; absent language competence cannot
be mitigated at all.

---

## 8. Recommendation

### Primary — `Qwen/Qwen3-4B-Instruct-2507`

| Criterion | Assessment |
|---|---|
| Licence | Apache-2.0, ungated — commercial-safe (VERIFIED) |
| Persian | Only eligible family claiming broad multilingual coverage (VERIFIED) |
| Memory | 5.12 GiB @16K = 43% of budget (COMPUTED) |
| Tool use | Strongest agentic scores of candidates: BFCL-v3 61.9, TAU1-Retail 48.7 |
| Context | Native 262,144 — 16K needs no RoPE scaling |
| Tokenizer cost | ratio 2.81 — the accepted trade-off (MEASURED) |

Native long context matters more than it appears: 16K sits far inside Qwen3's
trained window, so no RoPE extension is required and no associated quality
degradation is incurred. Tool-calling strength is directly relevant, since §7
routes all arithmetic and market data through tools — the model's job is to
*choose* tools correctly, and BFCL-v3 measures precisely that.

### Alternative 1 — `microsoft/Phi-4-mini-instruct`
MIT, 4.77 GiB, best Persian token economy (1.60). Promote **only if** Phase 2
shows acceptable Persian generation despite the undeclared support. Highest
upside if that gamble pays: near-double Persian context at lower memory.

### Alternative 2 — `HuggingFaceTB/SmolLM3-3B`
Apache-2.0, 3.46 GiB, ratio 1.61, and notably efficient KV (4 kv-heads). Same
Persian caveat as Phi-4-mini. Attractive if memory pressure appears once RAG and
the tool layer are resident.

### Fallback — `Qwen/Qwen3-1.7B`
Apache-2.0, 3.50 GiB, **identical tokenizer to the primary** (ratio 2.81) and
same family lineage. This is the deliberate value of the choice: if the 4B proves
too slow on the i5-12400, dropping to 1.7B changes speed without changing
tokenizer behaviour, prompt formatting, or Persian handling — so prior Phase 2
measurements remain comparable and only quality is re-tested.

### GGUF conversion path
All four are `llama.cpp`-supported architectures (`qwen3`, `phi3`, `smollm3`).
Standard route: `convert_hf_to_gguf.py` → F16 GGUF → `llama-quantize` to Q4_K_M.
Pre-built community GGUFs exist but must be checksum-verified before use rather
than trusted, per §11's untrusted-input policy.

---

## 9. What Is NOT Established

Stated plainly, because §0B forbids presenting inference as evidence:

| Claim | Status |
|---|---|
| Tokens/sec on the i5-12400 | **UNKNOWN** — not measurable here (F1) |
| Persian *generation* quality, any candidate | **UNKNOWN** — requires loading weights |
| Persian financial-terminology accuracy | **UNKNOWN** |
| Real GGUF file sizes | **ESTIMATED** — bpw constants, ±few % |
| Runtime overhead 0.6 GiB | **ESTIMATED** — rule of thumb |
| Qwen3 Persian competence | **VENDOR-CLAIMED**, not independently verified |
| Phi-4-mini Persian incompetence | **INFERRED from omission** — not tested |

The last two are the load-bearing uncertainties. Both resolve the same way: load
the models on the target machine and test. That is Phase 2.

---

## 10. Q5 Reconciliation — "in my machine and in this environment"

The answer to Q5 asked for measurement in both places. Half of it is
**not achievable**, and this needs saying rather than quietly working around.

Phase 0 finding F1 MEASURED **0.60 GiB available RAM** in this sandbox. The
smallest candidate's weights alone are 0.87 GiB. No candidate can be loaded here
— not slowly, not at reduced context; the allocation fails outright.

The workable split:

| Runs in this sandbox | Runs only on your machine |
|---|---|
| Tokenizer measurement (done — §6) | Model loading |
| Sizing arithmetic (done — §5) | Tokens/sec |
| Licence/config verification (done — §4) | Persian generation quality |
| Script authoring, RAG code, tool engine | Memory-under-load |
| Backtest logic, deterministic calculators | End-to-end latency |

So: this environment does everything that does not require model weights in
memory, and it produced a genuine measured result today. Anything requiring
weights runs on the i5-12400, with scripts prepared here so you run one command
rather than assemble a harness. No throughput number will be reported from this
sandbox at any phase — it would be fabricated.

---

## 11. Risk Register Update

| ID | Risk | Change |
|---|---|---|
| R5 | Persian tokenizer inefficiency | **QUANTIFIED** — 2.81 for primary; ~26K Persian chars @16K. Mitigation: chunking; digits→tool. Downgraded from unknown to managed. |
| R10 | **NEW** — primary's Persian is vendor-claimed, untested | High. Gate in Phase 2 before locking baseline. |
| R11 | **NEW** — licence audit needed for every future model | Medium. Qwen2.5-3B proves size-level variation within a family; never infer a licence from a sibling. |
| R12 | **NEW** — memory bandwidth unknown (Q6) | Medium. DDR4-3200 vs DDR5-4800 ≈ 1.5× tok/s swing; blocks a defensible Phase 2 threshold. |
| R3 | Model too slow on CPU | Unchanged; fallback path defined (Qwen3-1.7B, same tokenizer). |

---

## 12. Phase 1 Acceptance Criteria

| Criterion | Result |
|---|---|
| Model cards and licences verified from primary sources | **PASS** — vendor repos only |
| Primary + 2 alternatives + 1 fallback identified | **PASS** — §8 |
| GGUF size and RAM estimated | **PASS** — §5, reproducible script |
| ESTIMATED separated from MEASURED | **PASS** — §5, §6, §9 |
| Sizing uses real architecture, not generic classes | **PASS** — committed configs |
| No fabricated benchmarks | **PASS** — no tok/s claimed |
| Live trading still disabled | **PASS** — `ANALYSIS_ONLY` |

---

## 13. Open Questions

**Q6 (new, blocks a Phase 2 threshold).** What RAM is installed — DDR4-3200 or
DDR5-4800? On Windows: Task Manager → Performance → Memory shows both speed and
type. CPU-only decode is bandwidth-bound, so this determines the achievable
tok/s ceiling; without it, any Phase 2 speed threshold would be arbitrary.

**Q7 (affects Alternative 1).** Should Phase 2 spend time testing Phi-4-mini's
Persian despite its undeclared support? It offers near-double Persian context at
lower memory — a real prize if the omission turns out to be conservative
labelling. Costs perhaps one extra test cycle. My recommendation: yes, test it
alongside the primary, since the harness is the same and only the weights differ.

---

## 14. Recommendation to Proceed

Phase 1 is complete. Recommended Phase 2 (Environment and Runtime Setup):

1. Install llama.cpp or Ollama on the i5-12400.
2. Acquire/convert Qwen3-4B-Instruct-2507 → Q4_K_M GGUF; verify checksums.
3. Measure — on your machine — tok/s (prompt + decode), peak RAM @16K, load time.
4. Run the Persian generation gate (R10) on financial prompts.
5. Optionally test Phi-4-mini in the same harness (Q7).
6. Set the Phase 2 tok/s threshold once Q6 is answered.

**Awaiting explicit approval before beginning Phase 2. No auto-advance.**
