# Decision Log

Per SYSTEM_PROMPT.md Section 27.11. Append-only. Each entry records what was
decided, why, what it costs, and what would reverse it.

---

## D-0001 — Master prompt v2.0 is the canonical governing document
**Date:** 2026-08-10 · **Phase:** pre-0 · **Status:** Active

Committed verbatim as `SYSTEM_PROMPT.md` with an immutable copy at
`prompts/master-system-prompt-v2.0.md`.

**Why:** Every later phase is judged against it; it must be versioned and
diffable.
**Trade-off:** Prompt changes now require a commit and version bump.
**Reversal:** Supersede with a v2.1 file; never edit the pinned copy.

---

## D-0002 — Capability manifest is probe-derived only
**Date:** 2026-08-10 · **Phase:** 0 · **Status:** Active

`configs/capability-manifest.yaml` lists only capabilities confirmed by
executing a probe. The semantic catalog in prompt Section 8 is treated as a
*design target*, not an inventory.

**Why:** Section 4 forbids inventing capabilities. The gap between "the prompt
names this tool" and "this tool exists" is where fabricated results originate.
**Trade-off:** The manifest is much shorter than Section 8 and may read as
under-delivering. That is the accurate picture.
**Reversal:** None. This is a standing rule for every phase.

---

## D-0003 — Sandbox classified as authoring-only; measurement deferred
**Date:** 2026-08-10 · **Phase:** 0 · **Status:** Active · **Blocks:** 2, 7, 8, 8A

MEASURED: 0.60 GiB RAM available, 2 cores. COMPUTED: the smallest in-scope
artifact (~1.5B @ Q4_K_M) needs 0.85 GiB for weights alone. No in-scope model
can load here.

**Decision:** Use this sandbox for code, docs, research, and deterministic math.
Defer every performance/quality measurement to hardware that can hold a model.
**Why:** Section 20.4 forbids reporting estimated performance as measured. The
alternative — plausible-sounding invented tok/s figures — is exactly the failure
mode the prompt exists to prevent.
**Trade-off:** Phases 2/7/8/8A cannot complete here. Phase 1 is unaffected
(research loads nothing).
**Reversal:** A larger builder or user-run benchmarks on target hardware.

---

## D-0004 — Acceptance thresholds pre-committed in Phase 0
**Date:** 2026-08-10 · **Phase:** 0 · **Status:** Proposed, awaiting approval

Twelve thresholds defined in `docs/phase-reports/phase-0.md` §8, including two
hard blockers: zero fabricated prices/filings/orders in release tests, and zero
paper/live environment confusion.

**Why:** Thresholds set *after* seeing results get rationalized to whatever the
results were. Pre-committing removes that freedom.
**Trade-off:** Numbers are chosen without empirical grounding and may prove
mis-calibrated.
**Reversal:** User may revise before approving Phase 0; changes after that need
an explicit new entry here.

---

## D-0005 — SEC EDGAR retained as a primary source after UA re-probe
**Date:** 2026-08-10 · **Phase:** 0 · **Status:** Active

First probe: HTTP 403. Re-probe of `data.sec.gov` with a contact-bearing
User-Agent: HTTP 200.

**Why:** The 403 was SEC's UA policy, not a block. Logging the first result
would have wrongly discarded the project's best primary filing source.
**Obligation:** Any adapter must send a contact UA and respect ≤10 req/sec.
**Trade-off:** None. Public-domain US government data.
**General lesson:** A negative probe gets one disambiguating retry before being
recorded as unavailable.

---

## D-0006 — Persian *data access* separated from Persian *language capability*
**Date:** 2026-08-10 · **Phase:** 0 · **Status:** Active · **Needs:** user answer Q3

MEASURED: codal.ir and tsetmc.com resolve in DNS but TCP:443 is unreachable.

**Decision:** Record this as blocking Iranian *market-data ingestion* only. It
does not degrade Persian *language* quality, which is a base-model and
evaluation-set property.
**Why:** Conflating the two would misdiagnose the project — either abandoning
the bilingual mandate unnecessarily, or claiming Persian coverage the data layer
cannot support.
**Trade-off:** Quantitative Iranian-market analysis is unavailable pending Q3.
**Reversal:** Q3 option (b) user-supplied exports, or (c) a legally reviewed
access path per Sections 7/14.

---

## D-0007 — No credentials enter this environment until a vault exists
**Date:** 2026-08-10 · **Phase:** 0 · **Status:** Active · **Severity:** Critical

No OS keychain or encrypted vault is present (manifest: `cap.security.secret_store`
UNAVAILABLE). No API key, token, or broker credential may be introduced —
including the FRED key that would activate macro data.

**Why:** Section 11 forbids credentials in prompts, logs, RAG indexes, or
committed config. Without a vault there is nowhere safe to put one.
**Trade-off:** FRED stays DEGRADED and market/broker work stays blocked. That is
the correct ordering: build the vault before handling secrets.
**Reversal:** Implement `src/security/secrets/` per Section 11, then load keys
by alias only.

---

## D-0008 — Fine-tuning deferred pending demonstrated need
**Date:** 2026-08-10 · **Phase:** 0 · **Status:** Active

Sequence enforced: baseline → deterministic tools → RAG → re-evaluate → tune
only if material model-level failures remain.

**Why:** Section 16 mandatory policy. Most perceived "model weakness" in
financial QA is actually retrieval or arithmetic failure, which tuning does not
fix and can mask.
**Trade-off:** Delays any custom-model work by several phases.
**Reversal:** Phase 4 evidence of failures that tools and RAG demonstrably
cannot address.

---

## D-0009 — Deployment target fixed: i5-12400 / 16 GiB / Win11 / no GPU, 16K context
**Date:** 2026-08-10 · **Phase:** 1 · **Status:** Active

User-supplied answers to Phase 0 questions Q1–Q4 are now binding constraints:
16 GiB RAM, Intel Core i5-12400 (Alder Lake, 6 P-cores / 12 threads, no
E-cores), Windows 11, no GPU; 16K context; Iranian market data descoped;
execution ambition extends through live trading (Phase 11).

**Why:** Sizing, quantization, and model-size choices are meaningless without a
fixed target. 6 real cores with no E-core scheduling noise is a favourable
CPU-inference profile; the absence of a GPU makes memory bandwidth, not FLOPs,
the limiting factor.
**Trade-off:** 16K context costs materially more KV cache than 8K, which is why
`num_key_value_heads` became a first-order selection criterion.
**Reversal:** User changes hardware or context requirement.

---

## D-0010 — Qwen2.5-3B-Instruct disqualified on licence, not on merit
**Date:** 2026-08-10 · **Phase:** 1 · **Status:** Active · **Severity:** High

`Qwen/Qwen2.5-3B-Instruct` is removed from candidacy. Its licence is
`qwen-research`, whose LICENSE file states: *"Non-Commercial shall mean for
research or evaluation purposes only"* and grants rights **"FOR NON-COMMERCIAL
PURPOSES ONLY"** (VERIFIED, clauses 1.i and 2.a of the vendor's own LICENSE).

**Why:** It was otherwise a strong fit — uniquely, `num_key_value_heads: 2`
gives it the smallest KV cache of any 3B-class candidate (0.56 GiB at 16K vs
2.25 GiB for Qwen3-4B). A financial assistant is a plausible commercial artifact
and the project cannot rest on a research-only licence.
**Trade-off:** Loses the most memory-efficient 3B option.
**Reversal:** User confirms in writing that use is permanently non-commercial
research/evaluation, or Alibaba relicenses.

Note: every other Qwen candidate examined (Qwen3-4B-Instruct-2507, Qwen3-1.7B,
Qwen2.5-1.5B-Instruct) is Apache-2.0. This restriction is specific to certain
Qwen2.5 sizes, not to Qwen generally.

---

## D-0011 — Tokenizer efficiency must not be selected on in isolation
**Date:** 2026-08-10 · **Phase:** 1 · **Status:** Active · **Severity:** High

Persian tokenizer efficiency was MEASURED and the spread is large (best 1.60,
worst 3.16). The two most efficient tokenizers — Phi-4-mini (1.60) and SmolLM3
(1.61) — belong to models that **do not list Persian as a supported language**
(VERIFIED from each vendor's `language` card field). Tokenizer efficiency will
therefore be treated as a *cost* metric, never as a proxy for Persian
*competence*.

**Why:** A model that encodes Persian cheaply but generates it poorly is worse
than one that encodes it expensively and generates it well. Selecting on the
measured number alone would have chosen a model with no declared Persian
support — precisely the "measured but wrong metric" failure the prompt's
labelling discipline exists to prevent.
**Trade-off:** The stronger-Persian candidate carries ~76% higher Persian token
cost, reducing effective 16K context from ~48.7K to ~27.8K Persian characters.
**Reversal:** Phase 2 generation-quality testing shows a low-ratio model in fact
produces competent Persian.

---

## D-0012 — Persian generation quality is a Phase 2 gate, not a Phase 1 assumption
**Date:** 2026-08-10 · **Phase:** 1 · **Status:** Active

No Persian *generation* quality claim is made in Phase 1. Selection rests on
VERIFIED vendor language declarations plus MEASURED tokenizer cost. Actual
Persian financial fluency must be tested on the target machine before the
baseline is locked.

**Why:** This sandbox cannot load any candidate (Phase 0 finding F1: 0.60 GiB
available). Asserting quality here would be fabrication.
**Trade-off:** The Phase 1 recommendation is provisional and may be overturned.
**Reversal:** n/a — this is the correct standing policy.
