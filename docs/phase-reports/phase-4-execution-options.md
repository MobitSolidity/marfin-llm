# Phase 4 — How it could actually be executed

**Status: Phase 4 is NOT started and NOT approved. This document is a decision
aid, not a plan of record.**
**Date: 2026-08-15 · All figures labelled (V)erified / (M)easured / (C)omputed /
(E)stimated / (U)nknown**

---

## 1. What Phase 4 actually demands

From the master prompt, verbatim — seven tasks:

1. Compare plain baseline with RAG and tools.
2. Measure retrieval.
3. Measure citations.
4. Measure unsupported claims.
5. Measure latency and RAM.
6. Separate model vs retrieval failures.
7. Decide whether fine-tuning is justified.

Every one of those verbs is **measure** or **compare**. Phase 4 is not a building
phase — the things being measured are already built and verified. It is the phase
where the project finds out whether what it built actually works when a model is
driving it.

That has one consequence that decides everything below: **Phase 4 cannot be
faked, deferred into design, or satisfied with estimates.** Phases 0–3A could be
completed by construction and verification. This one requires a model to
generate tokens, and every output must come from a real run.

---

## 2. Why it cannot run in this sandbox — MEASURED, not assumed

| Requirement | This sandbox | Verdict |
|---|---|---|
| A model file on disk | `find / -name "*.gguf" -o -name "*.safetensors"` → **none** (M) | BLOCKED |
| An inference runtime | `import llama_cpp` → `ModuleNotFoundError` (M) | BLOCKED |
| RAM for the smallest in-scope artifact | **401 MiB available**, 985 MiB total (M) | BLOCKED |
| Weights footprint, 1.7B Q4_K_M | ~0.85 GiB before KV cache or runtime overhead (C) | — |
| Disk | 20 GiB free (M) | OK |
| Network | available (M) | OK |

The binding constraint is RAM, and it is not close. The **smallest** artifact
still in scope needs roughly **twice the total memory of this machine** and about
**four times what is currently free**, before the KV cache for a 16K context is
allocated. Adding swap does not fix this: decode speed is bounded by memory
bandwidth, and a swapping model produces numbers that are worse than no numbers,
because they look like measurements.

**This is why Phase 4 must not be "started" here.** Any figure this sandbox
produced for tok/s, peak RSS, or latency would be an artifact of the sandbox, and
recording it would violate the project's own first rule: never present ESTIMATED
as MEASURED.

---

## 3. The four routes, honestly compared

### Route A — Run Phase 4 on your own machine (i5-12400, 16 GB, Windows 11)

**This is the recommended route, and it is the only one that measures the machine
the project is actually for.**

The acceptance thresholds already approved (decode ≥ 8 tok/s, peak RSS ≤ 6 GiB,
TTFT ≤ 3 s at 2K) are thresholds *for your hardware*. Measuring anywhere else
answers a question nobody asked.

**What you would do:**

1. Install a runtime: `pip install llama-cpp-python` (CPU wheel, no CUDA).
2. Download the pinned primary model, `Qwen/Qwen3-4B-Instruct-2507`, at the
   recorded SHA `cdbee75f`, quantised **Q4_K_M** (~2.5 GB download).
3. Run `scripts/run_baseline.py`, which already exists in this repo and was
   written for exactly this purpose.
4. Send me the output. I fold the real numbers into the Phase 4 report.

**Cost:** zero. **Time:** an evening, mostly download.
**RAM headroom (C):** ~5.1 GiB estimated total at 16K context against 16 GB
installed — comfortable.
**Risk:** Windows CPU wheels for `llama-cpp-python` occasionally need a C++
build-tools install. Recoverable, and I can guide it.

**What it gives you that nothing else does:** it closes **R10** (Persian
generation quality), **Q8** (the fallback decision, which is *defined* as
depending on measured decode speed), and the entire "not measured" list carried
since Phase 1. Those cannot be closed by any amount of further building.

---

### Route B — Rent a small cloud CPU box for a few hours

A 4-vCPU / 16 GB instance for a few hours costs a few dollars, and mirrors your
target's memory without mirroring its CPU.

**Honest limitation:** it measures *a* machine, not *your* machine. Decode speed
on CPU is dominated by memory bandwidth, and a cloud instance's DDR generation,
channel count, and noisy neighbours are all (U). A result from here is a useful
sanity check on **correctness** metrics (retrieval, citations, unsupported
claims — tasks 2, 3, 4, 6), which are hardware-independent, but its **latency and
RAM** figures (task 5) must be labelled as belonging to that machine and must
**not** be compared against thresholds set for the i5-12400.

**Verdict:** a reasonable supplement, a poor substitute. It also costs money,
which contradicts your stated constraint.

---

### Route C — Split Phase 4 by what each metric actually needs

This is the pragmatic hybrid, and worth understanding even if you choose Route A.

| Phase 4 task | Needs your hardware? | Could run elsewhere |
|---|---|---|
| 1. Baseline vs RAG+tools | No — correctness | Anywhere with a model |
| 2. Measure retrieval | **No — no model needed at all** | **Here, today** |
| 3. Measure citations | Partly — the verifier is deterministic | Mostly here |
| 4. Measure unsupported claims | Yes — needs generation | Your machine |
| 5. Measure latency and RAM | **Yes — hardware-specific by definition** | Your machine only |
| 6. Model vs retrieval failures | Yes — needs generation to attribute | Your machine |
| 7. Fine-tuning justified? | Depends on 1–6 | After the above |

**Task 2 is genuinely runnable here right now**, and I have not done it, because
doing it would mean starting Phase 4 without approval. Retrieval quality is a
property of the corpus and the retriever, not of the model: given a set of
questions with known-correct passages, recall@k and MRR are computable with no
generation. The eval set exists (`evals/bilingual_eval_v1.jsonl`, 21 cases (M)),
though it was built for end-to-end evaluation and would need labelled gold
passages added.

**If you want progress before touching your own machine, this is the honest
increment** — and it should be labelled a *partial* Phase 4, not a complete one.

---

### Route D — Substitute a hosted API model for the local model

Technically possible; **I recommend against it**, and the reason is not
squeamishness.

The project's entire thesis (§0, §0B) is a **local, CPU-only, offline** bilingual
financial model. Phase 4 exists to test *that* system. Measuring a hosted
frontier model would produce excellent numbers about a system you are not
building, and every one of them would be misleading:

- Latency and RAM (task 5) would be meaningless.
- Unsupported-claim rate (task 4) would reflect a far larger model's behaviour,
  not the 4B you would actually run.
- The fine-tuning decision (task 7) would be made on evidence from a model that
  cannot be fine-tuned by you.

There is **one narrow legitimate use**: as a *labelling aid* for building the
gold-standard answers that tasks 2–4 grade against. That is tooling, not
measurement, and it must be recorded as such.

---

## 4. What I recommend, and why

**Route A, with Route C's task 2 as an optional warm-up.**

The reasoning is simple. Six of the seven Phase 4 tasks reduce to one question:
*does a 4B model on a CPU, given this project's RAG and tools, produce financial
answers that are supported, cited, and honest about what it does not know?* The
only machine whose answer matters is yours.

Everything else in this project has been built so that this moment is cheap:
`scripts/run_baseline.py` exists, the model SHA is pinned, thresholds were
pre-committed before any measurement (so they cannot be adjusted to fit a
result), and the eval set is written. **The remaining work is downloading a file
and running one script.**

---

## 5. What Phase 4 will likely find — stated in advance, so it cannot be rewritten later

Pre-committing predictions is the only way to keep a measurement honest. These
are (E), and I expect some to be wrong:

1. **Decode speed will land near the threshold, not far above it.** The estimate
   is ~14.7 tok/s (E) at DDR4-3200; real-world CPU inference commonly lands 30–50%
   below back-of-envelope bandwidth figures. If it comes in under 9 tok/s, **Q8
   activates** and the 1.7B fallback becomes the live question.
2. **Persian will be worse than English, by more than the 2% regression
   threshold.** Qwen3's Persian tokenizer ratio is 2.81 (M) — Persian costs
   ~2.8× the tokens of equivalent English, which compresses the effective context
   and raises the cost of every Persian answer. R10 is open for good reason.
3. **RAG will help citations far more than it helps fluency**, and the
   unsupported-claim rate will be the hardest threshold to meet (≤ 3%).
4. **Task 6 will be the most valuable and most annoying task.** Separating "the
   model hallucinated" from "retrieval gave it nothing" requires per-case
   attribution, and this is where a rushed Phase 4 usually goes wrong.
5. **Fine-tuning will probably NOT be justified** (task 7 → Phase 5). D-0008
   already defers it pending demonstrated need, and most failures at this stage
   are retrieval or prompt failures wearing a model's clothes.

---

## 6. The gate — unchanged

**Phase 4 is not approved and has not begun.** Live trading remains `DISABLED`
and unreachable by configuration; `active_mode` is `ANALYSIS_ONLY`.

To proceed, you choose a route. If you choose **A**, the next message you send me
should be the output of `scripts/run_baseline.py` from your own machine — and
Phase 4 starts from real numbers, which is the only way this project has ever
agreed to start anything.
