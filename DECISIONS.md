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

---

## D-0013 — Model revisions pinned by commit SHA
**Date:** 2026-08-10 · **Phase:** 2 · **Status:** Active

Baseline is pinned to exact HuggingFace commits, not to `main`:

- `Qwen/Qwen3-4B-Instruct-2507` @ `cdbee75f17c01a7cc42f958dc650907174af0554`
- `Qwen/Qwen3-1.7B` (fallback) @ `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`

**Why:** `main` is mutable. A silent re-upload of weights or a tokenizer fix
would invalidate every measurement taken against it, and the change would be
invisible in our logs. Section 0B's measurement discipline is meaningless if
the measured artifact can change underneath it.
**Trade-off:** Upstream fixes require a deliberate revision bump.
**Reversal:** Bump the pin explicitly and re-run the baseline.

---

## D-0014 — Calculation engine is stdlib-only
**Date:** 2026-08-10 · **Phase:** 2 · **Status:** Active

`src/calc/` uses no third-party packages — no numpy, no scipy, no pandas.

**Why:** The target is a Windows 11 machine with no build toolchain. A
dependency that fails to compile is a broken tool, and the failure would land
at the worst moment. The calculations here are O(n) over small series;
vectorization buys nothing at this scale.
**Trade-off:** Some routines are slower than a numpy equivalent and must be
hand-written. Irrelevant for typical inputs.
**Reversal:** If Phase 3+ needs large matrix work, isolate that in a separate
module with its own dependency, leaving `src/calc/` clean.

---

## D-0015 — Tests must kill seeded defects, not merely pass
**Date:** 2026-08-10 · **Phase:** 2 · **Status:** Active · **Severity:** High

Every calculation test derives its expected value from a closed form, hand
arithmetic, or an implementation-independent invariant — never by re-running
the formula under test. A mutation battery (`tests/mutation_test.sh`) seeds 13
realistic defects; all 13 must fail the suite.

**Why:** The suite passed 53/53 on first run, which is exactly when a test
suite is least trustworthy. Mutation testing found two real gaps:
  1. The Sortino test did **not** catch the downside-count divisor bug — the
     very bug the source comments claim to guard against.
  2. Removing `abs()` from `position_size` went undetected, so a short trade
     (stop above entry) would have returned a **negative** position size.
Both were caught by seeding the defect, not by reading the code.
**Trade-off:** Writing discriminating tests is slower than writing passing ones.
**Reversal:** none — this is standing policy for all future calculation work.

---

## D-0016 — Persian numerals are parsed deterministically, never by the model
**Date:** 2026-08-10 · **Phase:** 2 · **Status:** Active · **Severity:** High

`src/calc/persian_num.py` converts Persian/Arabic-Indic digits and separators
to machine numbers before any calculation. The model never converts a numeral.

**Why:** Phase 1 MEASURED that the selected tokenizer spends 2 tokens per
Persian digit and splits `۱٬۲۳۴٬۵۶۷` into 16 tokens. Digit fragmentation drives
arithmetic error. Worse, U+066B (٫ decimal) and U+066C (٬ thousands) are
visually near-identical: misreading one as the other turns 8.4 into 8400.
**Trade-off:** Genuinely ambiguous input (e.g. `1,5`) is REFUSED rather than
guessed, which will occasionally annoy a user. That is the correct failure
direction for a financial tool.
**Reversal:** none anticipated.

---

## D-0017 — Tool layer is whitelist-only and contains no execution capability
**Date:** 2026-08-10 · **Phase:** 2 · **Status:** Active · **Severity:** Critical

`src/tools/registry.py` dispatches only registered names. There is no `eval`,
no dynamic import, and no order/broker/execution tool of any kind. A test
asserts that none of `place_order`, `submit_order`, `buy`, `sell`,
`execute_trade`, `cancel_order`, `broker_connect`, `enable_live_trading` is
registered.

**Why:** Section 10 requires live trading to be impossible, not merely
disabled. The strongest guarantee is that no code path to an order exists.
A flag can be flipped by a bug or an injection; an absent capability cannot.
**Trade-off:** Phase 11 must add execution behind its own gates rather than
un-commenting something here.
**Reversal:** Only via the Phase 11 gate, with the two-phase preview→commit
protocol, kill switch, and idempotency keys of Section 10.

---

## D-0018 — Tool failures propagate; the model may not substitute a number
**Date:** 2026-08-10 · **Phase:** 2 · **Status:** Active

`call_tool` returns `{"ok": false, "error": ..., "guidance": ...}` on failure.
The guidance string explicitly instructs the model to report the refusal and
NOT to substitute an estimated value.

**Why:** The dangerous failure is not a crash — it is a tool erroring while the
model quietly fills the gap with a plausible-looking number. That converts a
loud failure into a silent fabrication, which Section 0B forbids.
**Trade-off:** More refusals surface to the user.
**Reversal:** none.

## D-0019 — Section 5.3 completed as four separate modules, stdlib only
**Date:** 2026-08-10 · **Phase:** 2a (R14) · **Status:** Active

`valuation.py` (26 fn), `technicals.py` (13), `fixed_income.py` (11),
`derivatives.py` (13) join `returns_risk.py` (21). All import `CalcResult` and
the shared validators from `returns_risk`; the dependency graph is one-way with
no cycles. No third-party numerics.

**Why:** Section 5.3 enumerates five families; only one existed, which was risk R14.
Separate modules keep each family's conventions (day counts, smoothing
constants, Greeks) visible where they apply instead of buried in one file.
Stdlib-only keeps the runtime installable on a Windows CPU box with no
compiler toolchain.
**Trade-off:** Hand-rolled `_norm_cdf` instead of `scipy.stats.norm`; mitigated
by `math.erf`, which is exact to double precision.
**Reversal:** Low cost — modules are independent.

---

## D-0020 — Indicators return the LATEST reading, not the full series
**Date:** 2026-08-10 · **Phase:** 2a (R14) · **Status:** Active

Each indicator has two layers: `_xxx_series()` returning a plain list, and
`xxx()` returning a `CalcResult` holding only the most recent value.

**Why:** A 500-bar RSI array is ~500 numbers the model must re-read on every
turn. At 16K context that is unaffordable, and the model almost always reasons
about the current reading. The series layer still exists so tests can verify
every point, not just the last one.
**Trade-off:** Divergence/crossover analysis over history needs the series
layer, which is not exposed as a tool yet.
**Reversal:** Add a `lookback` argument returning the final N values.

---

## D-0021 — Wilder smoothing (alpha = 1/n) is canonical for RSI, ATR and ADX
**Date:** 2026-08-10 · **Phase:** 2a (R14) · **Status:** Active

These three use `_wilder_smooth` (alpha = 1/n), not EMA (alpha = 2/(n+1)).
`rsi()` is pinned to Wilder's own published dataset: 70.46413502109705.

**Why:** This is the single most common source of "my indicator disagrees with
my platform" disputes. Wilder's convention is what TradingView, MetaTrader and
Bloomberg report, so matching it is what makes our numbers checkable against
the user's screen.
**Trade-off:** Differs from a naive EMA implementation; the discrepancy is
intentional and documented in each function's notes.
**Reversal:** none — changing it would break agreement with every platform.

---

## D-0022 — Bisection (not Newton) for YTM and implied volatility, plus a
## plausibility gate on the solved root
**Date:** 2026-08-10 · **Phase:** 2a (R14) · **Status:** Active · **Severity:** High

`_solve_yield` and `implied_volatility` bisect over a bracketed interval.
`_solve_yield` then REFUSES any root below `MIN_PLAUSIBLE_YIELD = -0.50`.

**Why (method):** Newton needs a derivative that collapses toward zero for deep
ITM/OTM options and can diverge or land on a spurious root. Price is monotonic
in yield, so bisection cannot.
**Why (the gate):** Found while investigating a failing test. A fat-fingered
price of 1e9 IS solvable — at a yield of -99.52%. Bisection returned it with
full confidence. The arithmetic was correct and the answer was meaningless: a
laundered input error, exactly the silent-wrong-number failure this engine
exists to prevent. The test that "failed" was itself wrong; the investigation
still surfaced a real hazard.
**Trade-off:** Genuine deep-negative yields are refused. Verified the gate does
not over-reach: a real -0.4% sovereign yield still computes.
**Reversal:** Raise the constant if a legitimate case appears.

---

## D-0023 — 84 tool schemas cost 8,920 tokens (54.4% of 16K); tool subsetting
## is REQUIRED before Phase 3 adds retrieval
**Date:** 2026-08-10 · **Phase:** 2a (R14) · **Status:** Active · **Severity:** High

> **⚠️ THE NUMBERS IN THIS ENTRY WERE SUPERSEDED ON 2026-08-31 BY D-0088.**
> "The real Qwen3 tokenizer" was `Qwen3-4B-Instruct-2507`'s — a real tokenizer,
> for a model this project does not run. The shipped Qwen3.5-4B figures are
> **9,122 tokens (55.7% of 16K), 108.6 tokens/tool**. The entry is left
> uncorrected below because deleting a wrong record destroys the evidence of how
> it came to be believed. **The decision it reaches is unchanged** — subsetting
> is still required, and by a slightly larger margin.

MEASURED with the real Qwen3 tokenizer against the real chat template: the
rendered tool block costs 8,920 tokens, 106.2 tokens/tool. Two tests in
`test_tools.py` guard this from both sides — it must stay under 70% of context,
and it is asserted to be OVER 25% so the number cannot quietly stop mattering.

**Why:** This is the first hard architectural constraint produced by measurement
rather than estimation. Phase 3 adds retrieved documents to the same 16K window.
Exposing all 84 tools plus RAG context plus conversation history does not fit.
**Consequence for Phase 3:** tools must be selected per query (by family, or by
a routing step) rather than broadcast wholesale. Descriptions may also need
shortening — the five costliest tools are ~160 tokens each.
**Trade-off:** Subsetting risks hiding the right tool from the model; the
selector becomes a correctness-relevant component and needs its own tests.
**Reversal:** Not needed if the context target is raised, but 16K is fixed by
the user's 16 GB RAM (Q2).

---

## D-0024 — Margin and liquidation are labelled ESTIMATED, never COMPUTED
**Date:** 2026-08-10 · **Phase:** 2a (R14) · **Status:** Active

`margin_estimate` and `liquidation_estimate` carry `label="ESTIMATED"`; a test
asserts the label survives the dispatch boundary.

**Why:** Every other function here is exact given its inputs. These two are not:
real margin depends on the broker's schedule, funding, fees and volatility
add-ons. A trader who treats a computed liquidation price as exact gets
liquidated slightly before it. Section 0B forbids presenting an estimate as a
measurement, and the label is the mechanism that enforces it.
**Trade-off:** none.
**Reversal:** Only with a real broker margin schedule, which is Phase 11.

---

## D-0025 — Mutation battery extended to 56 defects across five modules
**Date:** 2026-08-10 · **Phase:** 2a (R14) · **Status:** Active · **Severity:** High

First run: 53/56 killed, 3 survived. After closing the gaps: 56/56, 0 skipped,
all sources restored intact.

All three survivors shared one root cause — **each test happened to use a value
where the missing factor equals 1**:
- `convexity` with `f^2` deleted survived because every convexity test was
  RELATIVE (longer > shorter). A uniform scaling error preserves all orderings.
  Closed with absolute closed-form anchors at TWO different frequencies.
- `delta` with `e^-qT` deleted survived because every delta test used `q=0`.
  Closed with a finite-difference check at `q=0.05` and dividend-delta parity.
- `vega` with `sqrt(T)` replaced by `T` survived because every vega test used
  `T=1.0`. Closed with FD checks at `T=4` and `T=0.25`.

**Why this matters more than the score:** a 100% pass rate on 311 tests told me
nothing; the mutation battery found three formulas that were right but
UNVERIFIED, and would have stayed unverified indefinitely. The lesson is now a
standing rule: never verify a factor at the value where it disappears.
**Trade-off:** ~18 s per full battery run.
**Reversal:** none.

## D-0026 — Q9 RESOLVED: deterministic bilingual family router, recall-first
**Date:** 2026-08-10 · **Phase:** 2b (Q9) · **Status:** Active · **Severity:** High

`src/tools/selector.py` selects tools per query by keyword-scoring five
families. Chosen over the two alternatives I offered, both now ruled out **by
measurement rather than preference**:

> **⚠️ THE TOKEN FIGURES IN THIS TABLE WERE SUPERSEDED ON 2026-08-31 BY
> D-0088**, for **two independent** reasons: they were measured against another
> model's tokenizer, *and* the router's keyword lists grew when R18 was closed
> (`1bd2ff3`). Running the D-0026-era selector with its own constants still
> reproduces **2,552.3 / 15.6% / 4,479 exactly**, so the row below was correct
> when written. Today's equivalent, MEASURED: **mean 3,114 tokens (19.0%) vs
> 9,122**. The verdicts are unchanged.

| Option | Verdict |
|---|---|
| Shorten descriptions | **Rejected.** Descriptions are only 1,199 of 8,920 tokens (13%). Parameters are 5,602 (63%). Deleting every description entirely would not solve it. |
| Model-based router | **Rejected.** Needs a model call and its own context — spending the budget this exists to protect. |
| **Family routing** | **Adopted.** MEASURED mean 2,552 tokens (15.6% of 16K) vs 8,920; worst realistic case 4,479. |

**Recall over precision.** The two errors are not symmetric: an unnecessary tool
costs ~106 tokens and is recoverable; a MISSING tool leaves the model unable to
compute and liable to fabricate — exactly what §0B forbids. So scoring is
additive only, `returns_risk` is always included (§6.3 makes risk checks
mandatory), a no-match query returns the CORE set rather than nothing, and
confidence is reported so the caller can widen or abstain.

Deterministic keyword matching, not embeddings: inspectable, testable offline,
zero token cost, identical treatment for Persian and English.

**Measured result:** 24/24 recall (10 eval cases + 14 held-out paraphrases),
mean saving 6,368 tokens. Estimates verified conservative — they over-predict
actual rendered cost by ≤154 tokens, never under-predict.
**Trade-off:** keyword lists need maintenance as tools are added; the
unclassified-tool net and the eval-drift test both fail loudly if that lapses.
**Reversal:** `select_tools()` is the only entry point; swapping in a different
strategy touches one module.

---

## D-0027 — Held-out testing found three router defects a self-graded suite missed
**Date:** 2026-08-10 · **Phase:** 2b (Q9) · **Status:** Active · **Severity:** High

The router scored 10/10 on the eval set — the same set whose vocabulary
informed the keywords. Against 14 **held-out** paraphrases it scored 11/14.

1. **`"iv"` matched inside "relat-iv-e"**, routing a valuation question to
   derivatives. Bare abbreviations (`iv`, `var`, `par`, `call`) need word
   boundaries. Fixed for Latin script; Persian keeps substring matching because
   its affixes attach to the stem and boundaries would LOSE hits.
2. **Jargon-free phrasing was invisible.** Real users ask "what is this company
   worth", never "compute the enterprise value". Added plain-language terms in
   both languages.
3. **Persian ZWNJ compounds never matched.** `ارزش‌گذاری` normalises to
   `ارزش گذاری`, but the keyword list stored the ZWNJ form — so the query was
   normalised and the keyword was not. **Both sides must be normalised.** Found
   by mutation, not by the passing suite.

**Why this is logged:** grading a router on the data used to build it measures
nothing. The held-out probes are now permanent tests precisely because they
broke it once.
**Reversal:** none.

---

## D-0028 — Selector has its own mutation battery, in Python not bash
**Date:** 2026-08-10 · **Phase:** 2b (Q9) · **Status:** Active

`tests/mutate_selector.py`, 15 seeded defects: 15 killed, 0 survived, 0 skipped.

Python rather than bash because the selector source contains regexes, quotes
and Persian text that shell quoting mangles. A mangled pattern reports SKIP,
which at a glance is indistinguishable from a real result — the first bash
attempt silently "skipped" 6 of 8 mutants and would have overstated coverage.

The first honest run left **3 survivors, all the same blind spot as R14**:
each guard was tested in a state where it never engages.
- the unclassified-tool net was **dormant** (nothing is unclassified), so
  deleting it broke nothing → now tested with a simulated orphan tool
- truncation kept `returns_risk` only because it happened to rank top-2 → now
  tested with a query that has zero risk vocabulary and `max_families=1`
- ZWNJ normalisation was never exercised → now tested across all three Persian
  spellings

**Standing rule reaffirmed:** never verify a guard in a state where it cannot
fire.

---

## D-0029 — Eval/registry name drift is now a test failure
**Date:** 2026-08-10 · **Phase:** 2b (Q9) · **Status:** Active

`evals/bilingual_eval_v1.jsonl` expected `price_to_earnings`; the registry
registers `pe_ratio`. Written in Phase 2 before `valuation.py` existed, and
nothing compared the two, so it sat undetected across three commits.

Renamed the eval entries, and `test_selector.py` now asserts every
`expected_tool` exists in the registry.
**Why:** a benchmark referring to tools that do not exist reports a failure the
model did not cause, or hides one it did.
**Reversal:** none.

---

## D-0030 — "Hybrid retrieval" means lexical + structured, not vectors
**Date:** 2026-08-12 · **Phase:** 3 · **Status:** Active

§5.2 asks for hybrid retrieval. What exists is BM25 lexical search plus
structured identity lookup over facts. There is **no dense vector search**: no
embedding model exists on this machine, and the capability manifest lists
`rag_vector_search` as unavailable.

Documented under its accurate name in the module docstring and the phase report.
**Why:** §0B forbids inventing capabilities. Calling this "hybrid semantic
search" would misrepresent it to the one reader who most needs the truth — the
person deciding whether to trust a retrieved number.
**Reversal:** if an embedding model is ever added, a dense channel joins the
hybrid façade and this decision is superseded, not silently outgrown.

---

## D-0031 — Reranking is feature-based, not a cross-encoder
**Date:** 2026-08-12 · **Phase:** 3 · **Status:** Active

`rerank.py` combines normalized lexical score with source authority, recency,
units presence and table-ness. It is not a learned reranker.

Scores are normalized **divide-by-max**, not min-max. Min-max was a real defect:
it maps the lowest score to 0 and the highest to 1 regardless of how close they
were, which amplified a 0.25% BM25 gap into the maximum possible gap and made
the reranker a no-op.
**Why:** the feature weights are inspectable and explainable per hit
(`.explain()`), which a cross-encoder would not be, and citations must be
defensible.
**Reversal:** none pending.

---

## D-0032 — Citation tolerance is half-ULP of the claim's own precision
**Date:** 2026-08-12 · **Phase:** 3 · **Status:** Active

A fixed 0.5% tolerance accepted "109.5 billion" as support for 109.417 — a wrong
number, admitted with a real citation attached. Tolerance is now half a unit in
the last place of the claim's **own** stated digits: "109.4 billion" ⇒ ±0.05 B,
"109,417 million" ⇒ ±0.5 M.
**Why:** rounding allowance is a property of how precisely the claim was
*stated*, not a percentage someone tuned until the tests passed. There is no
magic constant to drift.
**Reversal:** none.

---

## D-0033 — Unscaled evidence cannot support a scaled claim
**Date:** 2026-08-12 · **Phase:** 3 · **Status:** Active

A bare table number rejected the scaled reading of a claim but **accepted** the
unscaled one, silently assuming base units — exactly the 10⁶ error the citation
layer exists to catch. `verify_claim` now refuses before the match loop when the
evidence declares no scale and the claim states one.
**Why:** MEASURED — EDGAR XBRL returns 109417000000 where the filing text says
109417. The two readings of one fact differ by a million, and guessing between
them is not verification.
**Reversal:** none.

---

## D-0034 — Source access terms are enforceable data, and enforced
**Date:** 2026-08-12 · **Phase:** 3 · **Status:** Active

`sources.py` holds each source's terms as data (`requires_contact_ua`,
`requires_api_key`, `rate_limit_qps`, `licence`, `enabled`) and `check_access()`
**refuses** rather than warns.

Three defects were found on the module's first ever execution:
- terms were **mutable at runtime** — one line re-enabled a descoped source,
  dropped the contact-UA requirement, or set a trust level that made
  `.authority` raise `KeyError` (a crash, not a refusal). Sources are now frozen
  after construction; the registry is a read-only mapping.
- the UA check was a bare `"@"` substring test, so `"@"`, `"me@"` and
  `"@example.com"` passed. A placeholder that satisfies the guard and then earns
  a 403 is worse than no guard.
- **nothing called `check_access()` at all.** The terms were documented, not
  enforced.

`check_access()` now gates every ingestion entry point, and trust level and
licence are read **from** the registry and may not be passed in by a caller.
**Why:** the acceptance criterion is "restricted data handled correctly." A
module that states the rules while nothing calls it satisfies the wording and
none of the intent. Terms a caller can edit at runtime are not terms.
**Reversal:** none.

---

## D-0035 — Descoped sources stay registered as disabled
**Date:** 2026-08-12 · **Phase:** 3 · **Status:** Active

Codal and TSETMC remain in the registry with `enabled=False` and the Phase 0 Q3
descope reason recorded, and a source disabled with no recorded reason is
refused at construction.
**Why:** a descoped source that is silently absent is indistinguishable from one
that was forgotten. A later reader can see it was considered and why it is off.
**Reversal:** if the user re-scopes Iranian market data, terms must be verified
by live probe before `enabled` flips.

---

## D-0036 — A crash is not a refusal (systemic harness fix)
**Date:** 2026-08-12 · **Phase:** 3 · **Status:** Active

`check_raises()` defaulted to `exc=Exception`, so it accepted an incidental
`AttributeError` thrown three frames deeper after a guard was deleted. A
mutation survivor exposed it. **106 of 113 assertions** across all eight suites
were relying on that default.

The default is now `REFUSALS = (ValueError, TypeError, ZeroDivisionError)` —
MEASURED as the only exception types deliberately raised in `src/` (172/13/11) —
and `CRASHES` are reported as failures.
**Why:** a test that cannot distinguish "refused correctly" from "crashed on the
way somewhere" is not verifying the guard it names.
**Reversal:** none. A test that genuinely wants a crash type must say so.

---

## D-0037 — Documents and time series are separate stores
**Date:** 2026-08-12 · **Phase:** 3 · **Status:** Active

`PassageIndex` is searched lexically and has no period-identity query.
`FactStore` is queried by identity only and has **no text search method at
all**. `HybridRetriever` returns them under separate keys, each tagged with its
own `mode`.
**Why:** scoring a numeric fact by text similarity is how a system becomes
confident about the wrong period. MEASURED: one revenue tag returns 117 facts
across four period lengths, and 46 periods are reported by more than one filing.
**Reversal:** none.

---

## D-0038 — A crash is not a refusal; probes name the designed exception
**Date:** 2026-08-14 · **Phase:** 3A · **Status:** Active

Adversarial probes split their accepted outcomes into `REFUSALS` (the pass) and
`CRASHES` (a finding). `AttributeError`, `KeyError`, `IndexError`,
`UnboundLocalError` and friends mean a guard was reached by accident rather than
by design: the input got further than intended and fell over on the way.

One narrow exception is allowed and is implemented as a **second helper**,
`attempt_immutable()`, rather than by widening the crash set: an `AttributeError`
raised by a `mappingproxy`, a tuple, or a `__slots__` object IS the designed
refusal — immutability enforced by type instead of by a written guard. Widening
`attempt()` to accept it would have blinded the probe everywhere else.

**Why:** `check_raises` once defaulted to `Exception` and therefore accepted
crashes as refusals across 106 assertions. The suite was green and was not
testing what it claimed.
**Reversal:** none. A test that genuinely expects a crash must name that type.

---

## D-0039 — `TradingViewLicenceError` is a `RuntimeError`, not a `MarketDataError`
**Date:** 2026-08-14 · **Phase:** 3A · **Status:** Active

The licence wall raises outside the market-data exception hierarchy, so
`except MarketDataError` cannot catch it.

**Why:** routine market-data error handling exists to fall back to another
source. There is no other source for TradingView content and no fallback — the
refusal is legal, not numerical, and it must not be swallowed by a handler
written to be resilient. Callers must name it explicitly.
**Reversal:** none while the terms prohibit non-display machine use.

---

## D-0040 — Alpha Vantage free tier only; no paid provider
**Date:** 2026-08-15 · **Phase:** 3A · **Status:** Active

User instruction (verbatim): «فقط از بخش رایگان استفاده کن و هزینه ای نکن یعنی از
Alpha Vantage استفاده کن». Alpha Vantage free tier is the only registered market
data provider. Twelve Data is **closed**, not deferred.

**Why:** the user is building this project alone with no institutional
affiliation and no budget. A design that assumes a paid feed is a design they
cannot run.
**Reversal:** requires an explicit user decision to spend money.

---

## D-0041 — Market data is non-persistable while its storage terms are UNKNOWN
**Date:** 2026-08-15 · **Phase:** 3A · **Status:** Active

Alpha Vantage responses are used in-memory and are not written to a durable
store. The permitted storage timeframe under the free tier is **UNKNOWN** (U),
not zero and not unlimited.

**Why:** the honest label for an unread term is UNKNOWN, and the safe behaviour
under an unknown retention right is not to retain. Recording it as a risk (R22)
keeps it visible instead of letting a convenient assumption harden into a cache.
**Reversal:** read and record the actual terms, then decide.

---

## D-0042 — Consent is bounded at both ends and its limits are sealed
**Date:** 2026-08-15 · **Phase:** 3A · **Status:** Active

`CaptureApproval` refuses an approval used **before** its `granted_at` as well as
after its TTL, and `DEFAULT_TTL_SECONDS` / `MAX_TTL_SECONDS` / `_FIELDS` cannot be
rebound or deleted on the class (`_SealedLimits` metaclass).

**Why:** both were MEASURED defects, and neither was visible to 162 passing unit
assertions.
  1. `is_expired()` asked only whether the TTL had run out, so an approval
     stamped tomorrow was honoured today. A clock skew produces that without
     anyone forging anything. A one-sided bound is not a window.
  2. Every attempt to widen ONE approval was refused by `__slots__`, but
     `CaptureApproval.MAX_TTL_SECONDS = 999999` succeeded and widened EVERY
     approval granted afterwards — a 138-hour standing consent passed
     validation. Guarding the instances while leaving the limit they are checked
     against writable protects the copies and not the original.
**Reversal:** none.

---

## D-0043 — A survivor is diagnosed by measuring the mutant
**Date:** 2026-08-15 · **Phase:** 3A · **Status:** Active

When a mutant survives, apply it, run it, and read what it actually does before
changing anything. A survivor has three possible causes and this phase produced
all three:

  1. **The tests are too weak** — the common case, and almost always the same
     shape: a second guard answers in place of the one under test, invisible to a
     type-only assertion where several guards raise the same class. Fix by
     asserting on refusal CONTENT plus a negative assertion that the neighbouring
     guard did not answer.
  2. **The mutation is wrong** — "content screened before consent" moved two
     statements but not the `raise`, so consent still answered first and no input
     could distinguish the mutant. A no-op that would have counted as a survivor
     forever.
  3. **The code is wrong** — the real defects listed in D-0042.

A fourth, related rule: never adjust an assertion to make it pass. Measure the
real wording and correct the test.
**Why:** "strengthen the tests" applied reflexively to case 2 produces tests that
chase a difference that does not exist, and applied to case 3 hides a defect.
**Reversal:** none.

---

## D-0044 — Route A: the agent builds the instrument, the user takes the measurement
**Date:** 2026-08-16 · **Phase:** 4 · **Status:** Active

The user chose Route A from `docs/phase-reports/phase-4-execution-options.md`,
verbatim: *«طبق راه الف یعنی استفاده از ماشین خودم پیش میریم»* — "we proceed
according to Route A, i.e. using my own machine."

This changes what the agent's job **is** for Phase 4. Phase 4 asks for
measurements, and no measurement can be produced in this sandbox. MEASURED
2026-08-16: `pip install llama-cpp-python` fails with `[Errno 28] No space left
on device` while fetching cmake/ninja, and the machine has 985 MiB total RAM
against 2.33 GiB of weights. So the deliverable is not numbers — it is the
instrument that produces them on the i5-12400, plus a guide in Persian, so that
"the remaining work is downloading a file and running one script" (the promise
made in §4 of the options document) is literally true.

**Consequence for phase state:** `phase_status` is
`TOOLING_COMPLETE_AWAITING_USER_MEASUREMENT`, and `phase_4.measurements_recorded`
is `null` **on purpose**. Phase 4 is not complete, not in progress, and not
partially measured. It is built and waiting.
**Why:** the alternative — recording sandbox-derived or estimated figures for
tok/s, peak RSS and citation rate — would violate the project's first rule.
Numbers that look like measurements are worse than no numbers.
**Reversal:** if the user later prefers a rented machine (Route B/C), the harness
is unchanged; only the guide is.

---

## D-0045 — The available GGUF is not the pinned model, and the results file says so
**Date:** 2026-08-16 · **Phase:** 4 · **Status:** Active

Phase 2 pinned `Qwen/Qwen3-4B-Instruct-2507` at sha
`cdbee75f17c01a7cc42f958dc650907174af0554`. VERIFIED 2026-08-16 against the
Hugging Face API: **that repo publishes no GGUF.** The obvious companion repo
`…-2507-GGUF` returns HTTP 401 — but a repo name invented for the test
(`Qwen/definitely-does-not-exist-xyz123`) returns 401 as well, so **401 cannot
distinguish absent from gated.** Its existence is UNKNOWN, not negative. That
distinction is recorded rather than collapsed into "it doesn't exist."

What the user can actually download is `Qwen/Qwen3-4B-GGUF` →
`Qwen3-4B-Q4_K_M.gguf`, 2,497,280,256 bytes (2.33 GiB), which is the **original
Qwen3-4B**, a different model.

Decision: run against it, and make the substitution **visible in the data**.
`phase4_lib.identify_model()` hashes the file and records
`is_pinned_revision: false` with a note that speed and RAM figures transfer
(same architecture and parameter count, COMPUTED) while Persian fluency,
instruction following and tool selection do **not**. An unrecognised file is
labelled `UNKNOWN` — never assumed to be the pinned model.
**Why:** a basename cannot establish provenance; a filename is whatever someone
typed. Without a content hash in the file, a Persian-fluency verdict measured on
Qwen3-4B would later be read as a verdict on Qwen3-4B-Instruct-2507.
**Reversal:** if a 2507 GGUF appears, add its digest to `KNOWN_MODEL_FILES` and
re-run; nothing else changes.

---

## D-0046 — A published checksum is verified by downloading, not by copying an API field
**Date:** 2026-08-16 · **Phase:** 4 · **Status:** Active

`docs/guides/phase-4-windows-setup-fa.md` instructs the user to **abort** if the
model's SHA-256 does not match the value printed in the guide. That makes the
checksum a safety control, so it was established the only way that justifies the
instruction: the full 2,497,280,256-byte file was downloaded and hashed with
`sha256sum`, and `phase4_lib.sha256_file()` was run against the same file. All
three agree on
`7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5`, the download
served exactly the advertised byte count, and the first four bytes are `GGUF`.
**Why:** the digest was first read from the API's LFS `oid` field. Git LFS
defines that as the SHA-256 of content, so copying it would probably have been
right — and "probably right" turns an abort-on-mismatch check into a coin toss
that fails safe-looking. Publishing an unverified checksum also teaches the user
to ignore a mismatch when it eventually happens.
**Reversal:** none. Any future artefact added to `KNOWN_MODEL_FILES` gets the
same treatment.

---

## D-0047 — A constant that documents a rule it does not enforce is decoration
**Date:** 2026-08-16 · **Phase:** 4 · **Status:** Active

MEASURED: `_DECIMAL_SEPARATORS` in `scripts/phase4_lib.py` carried a careful
comment distinguishing U+066B (Arabic decimal separator) from U+066C (Arabic
thousands separator) — three orders of magnitude apart in a financial figure —
and **was never read.** Both `extract_numbers` and `extract_magnitudes`
hard-coded the replacement, in duplicate. Deleting U+066B from the table changed
no behaviour, which is how the mutation battery found it.

Fix: a single `_normalise_separators()` that iterates the tables, plus tests
asserting that *every declared separator is actually honoured* and that the two
tables do not overlap.
**Why:** the danger is not the dead line; it is that the comment makes a reader
believe the rule is enforced. Duplicated logic with a decorative table is how the
two copies silently drift apart.
**Reversal:** none.

---

## D-0048 — A test that derives its expectation from the code under test asserts nothing
**Date:** 2026-08-16 · **Phase:** 4 · **Status:** Active

MEASURED: the threshold-direction check read `THRESHOLD_DIRECTION`, then chose a
probe value that would breach *whatever direction it had just read*. Flipping an
entry therefore selected the matching probe and passed. The mutation
`fabricated_financial_data_count_max: max -> min` — which inverts the meaning of
a zero-tolerance fabrication ceiling — **survived a 322-assertion suite.**

Fix: an independently written `_EXPECTED_DIRECTION` dict, compared to the table
as a whole, with probes derived from the independent copy.
**Why:** a loop over the thing under test proves only that the code equals
itself. This is the sharpest instance of the project's recurring lesson that a
passing suite proves nothing on its own.
**Reversal:** none.

---

## D-0049 — The instrument must not be able to lie about its own subject
**Date:** 2026-08-16 · **Phase:** 4 · **Status:** Active

The mutation battery reported `source restored and oracle green: False` for a
source that was intact. Diagnosis by measurement: the suite created two
`mkdtemp()` directories per run and deleted neither, one holding a 3 MiB
stand-in `.gguf`. Across 81 mutation runs that left 288 directories and filled
`/tmp` — a 493 MiB tmpfs — to 100%. Python then exited 120 while flushing
stdout, and the battery read that as a source-integrity failure. Minimal repro:
exit 120 deterministically on redirect, 0 on a pipe, and
`cat: write error: No space left on device`.

Fix: a `_TEMP_DIRS` registry with cleanup before `sys.exit(summary())`, and a
section asserting the suite does not leak. **The leak detector was then wrong
too** — it scanned all of `/tmp` for `phase4_test_*` and tripped on the
battery's own aborted runs, since a killed mutation exits before cleanup. Scoped
to this process only.
**Why:** the battery is this project's decisive instrument. A false integrity
alarm is worse than a missing one, because the natural response is to distrust
the source rather than the tool.
**Reversal:** none.

---

## D-0050 — The report the user reads is part of the deliverable, and is asserted
**Date:** 2026-08-16 · **Phase:** 4 · **Status:** Active

Two related findings, both MEASURED.

**1. The suite reported phantom failures.** `main()` prints a verdict table in
which five thresholds legitimately read `FAIL` against the deliberately-bad fake
model. Those lines went to the test suite's own stdout, where
`tests/run_all.sh` greps `^  FAIL` to detect a failing test — so a *healthy*
harness would have printed five phantom failures on every regression run. Fixed
by capturing stdout during the two `main()` calls.

**2. Capturing revealed the report was entirely unasserted.** It is the first
thing the user sees when the run ends on their own machine, and not one character
of it was checked. Six seeded mutations that broke the report while leaving the
JSON perfect — dropping the verdict column, printing no table, counting FAIL or
PENDING verdicts as passes, hiding the passing rows, removing the "a human has
not graded this" notice — would all have survived. Now asserted, including that
the tally line agrees with the table it summarises.
**Why:** a runner that prints non-failures as FAIL trains the reader to skip FAIL
lines, which is the one habit this project cannot afford. And an unasserted
human-facing report is exactly the "harness that cannot fail is decoration"
problem, one layer out from the graders.
**Reversal:** none.

---

## D-0051 — The install failure is fixed with a prebuilt wheel, and I retract a wrong finding I made twenty minutes earlier
**Date:** 2026-08-17 · **Phase:** 4 · **Status:** Active

**Context:** the user ran the guide's §3 command on the target machine and hit
`No CMAKE_C_COMPILER could be found` / `Failed building wheel for
llama-cpp-python`. Guide §3 and §7 had both flagged this exact outcome as an
UNKNOWN and asked for the full traceback, so the guide worked as designed.

**Decision:** recommend the maintainer's CPU wheel index rather than telling the
user to install Visual Studio Build Tools:

```
pip install llama-cpp-python psutil \
  --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
```

**Diagnosis (V):** CMake found the *Visual Studio 16 2019 generator* but no C
or C++ compiler, i.e. Visual Studio is installed without the C++ workload. The
reason pip attempted a compile at all is that PyPI publishes **only an sdist**
for `llama-cpp-python` — there is no wheel to fall back to.

**What I measured before recommending it (all M, 2026-08-17):**

| claim | evidence |
|---|---|
| index reachable | HTTP 200, 1,719,578-byte listing |
| pip picks a wheel with no version pin | `llama_cpp_python-0.3.35-py3-none-win_amd64.whl`, 7,086,788 bytes |
| pip prefers it over the sdist without `--only-binary` | yes; sdist never fetched |
| works for 3.10 / 3.12 / 3.13 | identical file resolved for all three |
| Python-ABI-independent | tag `py3-none`, zero `.pyd`, binds via `ctypes` |
| real native code inside | `llama.dll`, `ggml-cpu.dll` are `PE32+ x86-64` |
| reproducible bytes | sha256 `31590ea0...80bb` on two independent downloads |
| no dependency needs a compiler | `psutil`, `numpy`, `markupsafe` etc. all wheels |

Because the wheel is `py3-none`, **I did not need the user's Python version** —
I had been about to ask for it, and the measurement made the question moot.

**A retraction, recorded because getting this wrong in public is the point.**
While checking the index I ran `curl -I -L` and a `curl -r 0-0` byte-range
request against a release asset URL and got **404**, and I told the user: *"the
index advertises wheels whose download URLs are dead."* That was false. I then
queried the GitHub releases API, found the asset listed with a
`browser_download_url` byte-identical to the URL I had just called dead, and a
plain `GET` returned **200 with the complete, valid wheel**. GitHub release
assets can reject `HEAD` and range requests for files that exist.

**Why this matters beyond one wrong sentence:** the failing probe was cheaper
than the real one, and I let cheapness substitute for correctness — the same
error shape as reading a checksum out of an API field instead of hashing the
file (D-0046). A negative result from a weaker instrument is not a negative
result. Had I stopped at the 404 I would have sent the user to install several
gigabytes of Visual Studio Build Tools to solve a problem that one `--extra-index-url`
flag solves.

**Not claimed:** that `import llama_cpp` succeeds on Windows 11. This sandbox is
Linux; it cannot execute the DLLs. `honest_gaps.llama_cpp_import_succeeds_on_target`
stays UNKNOWN until the user's run says otherwise.

**Reversal:** if the index is unreachable from the user's network, fall back to
Visual Studio Build Tools with the "Desktop development with C++" workload
(guide §3.4), or I hand over the verified wheel directly.

---

## D-0052 — The chosen model thinks out loud, and that turned a trade instruction into a passing safety score
**Date:** 2026-08-18 · **Phase:** 4 · **Status:** Active

**Context:** the user said they will run `Qwen3.5-4B-Q5_K_M.gguf`. The file is
real and its provenance is now VERIFIED — all 3,143,656,608 bytes were
downloaded and hashed three ways (`sha256sum`, the project's own
`sha256_file()`, and the leading `GGUF` magic bytes), giving
`8814232b…ad39`. A byte-range parse of the GGUF header reports architecture
`qwen35`: a hybrid of 24 SSM (Gated DeltaNet) layers and 8 full-attention
layers, `full_attention_interval=4`, which is why the KV cache is only 0.500 GiB
at 16K context (COMPUTED) despite a declared 262,144 context length. At 2.928
GiB it is under the approved 4.0 GiB ceiling.

The consequential fact is elsewhere: **this model thinks by default and cannot
be told not to.** The `/think` and `/nothink` switches that worked on Qwen3 are
unsupported in this release (VERIFIED from the official model card). Every reply
arrives as `<think>…</think>` followed by the answer.

**What I did instead of assuming:** I ran the existing graders against realistic
thinking output. Two defects, both MEASURED, not predicted:

| # | Input | Old grade | Why it matters |
|---|---|---|---|
| 1 | reasoning: *"I cannot provide investment advice"* · answer: *"Buy 500 shares of AAPL right now."* | `is_abstention() == True` | A **trade instruction scored as a clean refusal**, on the `correct_abstention_pct_min` **safety** threshold |
| 2 | 256-token budget consumed entirely inside `<think>` | wrong answer | A **harness budget limit charged to the model** |
| 3 | number appearing only in the reasoning | `value_matches() == True` | A guess made while thinking counted as an answer |
| 4 | `<tool_call>` merely *considered* in reasoning | counted as issued | Intent scored as action |

Defect 1 is the serious one. The single most dangerous output this project can
produce was being recorded as evidence of safety. A suite of 346 assertions had
been green over it, because nothing in the suite had ever shown the graders a
reasoning block.

**Decision:** keep Qwen3.5-4B and fix the instrument (the user chose option
الف), with five specific commitments:

1. **The split happens in `ModelRunner.generate()`, not at each call site.**
   Every grader consumes that function's output, so one line there covers all of
   them. Splitting per-site would leave the safety defect one forgotten line
   away from returning, in a codebase whose failure mode is silence.
2. **An unterminated `<think>` yields an empty answer** — not the reasoning, not
   the partial prefix that preceded it. Half a sentence is not an answer, and
   returning the reasoning *is* defect 1. It is counted and reported separately
   as a **budget** failure.
3. **The latency probe's counters are snapshotted and restored.** Its 1-token
   TTFT probe necessarily leaves `<think>` unterminated; counting that would
   fabricate lost answers that no eval case produced. A speed probe must not
   manufacture correctness failures.
4. **The default budget rises 256 → 768.** The guide already tells the user to
   pass it, but the default is the number that will actually be used at 1 a.m.
5. **The reasoning tally prints unconditionally, including zero.** A counter
   that only appears when it fires teaches the reader that its absence means
   nothing — and absence is precisely the case they need to trust.

**Verification:** 35 new mutations reopen each defect; all 35 killed. Battery
now **131 seeded / 131 killed / 0 survived / 0 skipped**; full regression
**2,596 assertions / 823 seeded / 818 killed / 5 equivalents / 0 survivors / 0
skips**, ALL GREEN.

Two mutations survived the first run, and **both were weak tests, not wrong
code** — diagnosed by measuring the mutant rather than by reasoning about it:

- A type-guard test that passed only `123` proves nothing, because `"<think>" in
  123` raises `TypeError` all by itself. A **list** separates them: `"<think>"
  in []` is legal and returns `False`, so the guardless version falls through to
  `[].strip()`. The test now covers a list, a dict, and the message text.
- A counter-restoration test whose counters were already zero cannot distinguish
  *restoring a snapshot* from *resetting to zero*. It now seeds non-zero counts
  first, so a reset would delete five measured harness failures and be seen.

**Collateral finding, and the more instructive one:** two **pre-existing**
mutations were silently broken by my edits to `phase4_lib.py`. They would have
become **SKIPs** — and a skip is worse than a survivor, because it reports
nothing while the summary still reads clean. Every find-string in the battery is
now `str.count`-verified `== 1` *and* checked for no-ops before the battery is
believed.

**What I did NOT do:**

- I did not widen the Persian refusal vocabulary to make an assertion pass. It
  is MEASURED that `_ABSTAIN_FA` misses the natural phrasing «من این اطلاعات را
  ندارم». Grading vocabulary must be set from observed model output, not
  invented to turn a test green. The gap is recorded; the error runs in the safe
  direction (understating correct abstention), but it is still an error.
- I did not rename `model_file_size_q4km_gib_max`, even though the user runs
  Q5_K_M and the name no longer matches. Those twelve thresholds were approved
  on 2026-08-10; the ceiling of 4.0 GiB and the verdict are both still correct,
  so the mismatch is recorded rather than quietly edited.
- I did not record any RAM figure as measured. 3.8–4.2 GiB is ESTIMATED.
- I did not claim the runtime supports `qwen35`. The string is present in
  `llama.dll` of the verified wheel (MEASURED), but a string is not a load.

**Reversal:** if the run reports a non-zero `answers LOST to truncation` even at
768, raise the budget rather than concluding anything about quality. If `qwen35`
will not load at all, upgrade `llama-cpp-python` — do not switch models, since
the size and memory case for this file is sound. Option ب (reverting to Qwen3-4B
Q4_K_M) remains available and needs no code change: both artefacts are
registered, and the harness now handles thinking and non-thinking models alike.

## D-0053 — The first real measurement mostly measured my own bugs; six defects closed before any re-run

**Date:** 2026-08-18 · **Phase:** 4 · **Status:** Active

**Context:** the user ran the Phase 4 harness on their i5-12400 and returned
`phase4_run.json` — the first on-target measurement this project has ever had.
It cost 52 model calls, 6,115 s of generation and 103.9 minutes of wall clock,
and the user reported «فقط یک نکته در هنگام اجرای کد فشار زیادی به cpu می امد»
(heavy CPU load). The results file showed seven of twelve approved thresholds
FAILING, including `citation_correctness_pct 0.0` and
`unsupported_claim_rate_pct 100.0`.

Read at face value, that file says the model is unusable. Read properly, it
mostly says **my grader is broken.** Six defects, **five of them in code I
wrote**:

1. **The TTFT prompt overshot its target.** A 2048-token target produced 4,433
   prompt tokens (2.16×) because the repetition count was a character-based
   guess. The run still recorded `ttft_measured_at_2k: true`, because that flag
   was `ptok >= target * 0.8` — a **floor with no ceiling**. So the reported
   118.68 s is not the quantity the approved threshold names, and nothing in the
   harness said so. I had also earlier told the user this flag was a constant;
   that was wrong, and correcting it was the first thing I did.
2. **The tools arm computed every calculation correctly and was scored 25%.**
   All 8 calc cases had `tool_value_ok` true — the executed tool returned the
   right number — but only the prose was graded, and `tool_value_ok` never
   reached the summary at all.
3. **Years were graded as financial claims.** `verify_claim` returns early on
   the first number it cannot locate, and the first number in a financial answer
   is almost always a year. So all three graded RAG cases were decided by "2023
   does not appear in the evidence" — true of every filing ever written, and
   meaningless. The 0.0% and the 100.0% were the same artefact seen twice.
4. **Markdown emphasis hid the scale word.** `**$383,285** million` did not
   match, because the `**` sat between the number and `million`. That was the
   **one correct RAG answer in the entire run**, scored MODEL_FAILURE.
5. **The Persian refusal vocabulary was incomplete.** The model refused a trade
   instruction correctly — «امکان خرید سهام را ندارم و دسترسی به قیمت لحظه‌ای
   بازار یا امکان معامله ندارم» — and scored `abstained=False`. This gap was
   recorded as an honest_gap in D-0052 and deliberately left unfilled; the run
   supplied the observed text that fills it.
6. **A dangling `</think>` was treated as ordinary text.** MEASURED consequence:
   a reply whose visible answer was "Buy 500 shares of AAPL right now" scored as
   a clean abstention, because the refusal sat in the discarded reasoning. **That
   is the D-0052 safety false pass, reopened through a different door.**

**Decision:** fix all six, guard each with mutations, and **run nothing on the
user's machine** until the instrument is trustworthy. Fixing the grader costs the
user no CPU; re-running with a broken grader costs hours and produces another
unusable file.

**Direction of each error, checked explicitly.** Defects 1–5 manufactured
FAILURES, so fixing them cannot manufacture a pass on its own — each surviving
claim still has to match its evidence. Defect 6 manufactured a **PASS on a
safety threshold**, which is why it is the serious one. Every fix was also tested
in its dangerous direction: the bare unscaled `383,285` must still FAIL; a
positive Persian verb must not read as a refusal; a bare trade instruction must
still not be an abstention.

**On the approved threshold (defect 2).** The obvious "fix" is to let
`deterministic_calc_correctness_pct` count tool results, turning 25.0 into 100.0.
I did not do that. That metric's name and meaning were approved by the user on
2026-08-10, and **redefining an approved threshold to convert a FAIL into a PASS
is the worst thing this file could do.** A second metric,
`deterministic_calc_with_tool_correctness_pct`, is reported alongside it. The
user can see both numbers and decide what the threshold should mean.

**The measurement that condemned one of my own assertions.** In D-0052 I
asserted that a stray closing tag is *not* treated as a reasoning block, and it
passed for a day. Defect 6 is that assertion's belief, measured: it was wrong,
and it silently reopened a safety hole I had closed the day before. **A passing
assertion is not evidence that the belief behind it is right.** The assertion is
reversed, with the measurement recorded next to it.

**What mutation testing actually found.** The first battery run over the six
fixes left **14 survivors** — every fix written, none of them guarded. Two are
worth recording:

- *"the tail tokens are not subtracted from the target"* survived an assertion I
  had pinned at target 400 — where integer division absorbs the tail and the
  mutant produces the identical result. My assertion was **true of the mutant**.
  Replaced by a measured bound over targets 60–3000: worst built/target ratio
  1.0086 now, 1.1333 mutated.
- *"the results file stops recording how the prompt length was obtained"*
  survived because I asserted the field was one of `("tokenized","estimated")` —
  which a hardcoded constant satisfies. **A field that does not discriminate is
  not evidence.** Both branches are now exercised on models that differ.

The pre-flight count check caught four more mutations that would have printed
**SKIP**: three whose find-strings my own fixes had invalidated, one made
ambiguous by a second identical `isinstance` guard. A skip reports an untested
branch as a clean run. One of those four had also carried a **description that
misdescribed what it did** since the day it was written — it claimed to swap in
the gold passage, while actually disabling citation grading entirely. Corrected,
because a mislabelled mutation misleads whoever reads the battery next even while
it kills correctly.

I also **extracted `report_latency_block` from `main()`**. Silencing either of
its two warnings with `if False:` had passed the entire suite. Those warnings are
the only mechanism by which the user learns that a printed number does not
measure what its threshold names — untested, they were decoration.

**Verification:** Phase 4 harness 509 assertions (was 409), 182 mutations (was
131), 0 survivors, 0 skips. Project-wide `./tests/run_all.sh --mutate`: 2,696
assertions, 874 seeded, 869 killed, 5 documented equivalents, **0 survived, 0
skipped, ALL GREEN**. Commit `b6e6cc1`.

**What is genuinely the model's fault**, and survives every fix: it fabricated an
Iran Khodro revenue figure on an unanswerable question (reusing Apple's 383,285);
it computed `1.61051^0.2` as 1.1026, giving CAGR 10.26% instead of 10%; it
emitted `position_size` with `entry: 50, stop: 50` — a divide by zero — instead
of refusing; it issued 26 tool calls for one question, 25 of them identical; it
answered a Persian question with a bare English tool call; and two cases returned
zero tokens after 12–13 s, cause **UNKNOWN**.

**What is still not recorded.** `measurements_recorded` stays `null`. The run has
**two** independent contaminations — the six grader defects, and 20 of 52 answers
lost to reasoning truncation, every one at exactly 768 completion tokens (budget
exhaustion, not model silence; 62.5% of all generated tokens were discarded).
The sound figures — 2.928 GiB file, 3.901 GiB peak RSS, 100% tool-call schema
validity, 0 paper/live confusions, 4.12 tok/s median — are held in
`phase_4.first_run_2026_08_18.figures_believed_sound`, explicitly **not**
promoted. The user's CPU observation is fully explained: roughly 64 of those 104
minutes were wasted by my own `max_tokens` configuration.

**What I did NOT do:**

- I did not start a re-run. It costs the user hours; it is their decision.
- I did not widen the P/E fixture tolerance to accept 17.86 for 17.857142857.
  That is a question for the user (Q10), not a number for me to adjust.
- I did not rename `model_file_size_q4km_gib_max`, still pending user consent.
- I did not modify `src/rag/citations.py`. Its early return is correct behaviour
  for a single claim; the defect was in my Phase 4 framing of it.
- I did not promote any figure from the contaminated run to a measurement.

**Reversal:** if the corrected re-run shows citation correctness still near zero
with years properly masked, then the finding is real and belongs to the model —
at which point Q8 (fallback model vs accept-and-lean-on-RAG) becomes the live
decision rather than a hypothetical. If a fix proves too aggressive in practice —
for example if `_SCALE_LEAD` attaches a scale word that was never written — the
correct response is to narrow the character class, never to relax the assertion
that caught it.

---

## D-0054 — A regression reported FAILURES PRESENT; the cause was my own killed mutation run, not the code

**Date:** 2026-08-18
**Status:** Accepted
**Supersedes:** nothing
**Related:** D-0053, R23

### Context

After finishing the D-0053 fixes and updating the documentation, I re-ran every
gate before committing. The Phase 4 harness gave `509 passed, 0 failed` and the
Phase 4 battery gave `182 seeded, 182 killed, 0 survived, 0 skipped`. The full
project regression `./tests/run_all.sh --mutate` then printed:

```
FAILURES PRESENT
```

Immediately afterwards, the same command on the same working tree printed:

```
ALL GREEN
```

A gate that returns two different verdicts for the same tree is worth more of my
attention than a gate that simply fails. A failing gate tells you where to look.
A flaky one tells you that you cannot believe any of its verdicts, including the
green ones I was about to commit on the strength of.

### What I did NOT do

I did not re-run until it went green and commit that. Two green runs after a red
one is not evidence the red one was spurious — it is exactly what an
intermittent, real defect looks like. I also did not write the red run off as
"probably the sandbox".

### The measurement

The first regression attempt had been killed by the tool's own 120-second
ceiling, not by any test. The mutation driver works by **rewriting the source
file in place**, running the oracle, and restoring the original in a `finally:`
block (`tests/mutate_phase4.py`, the `try/finally` around the mutation loop plus
an outer `finally:` that copies every module back from a `phase4_orig_*` backup
directory).

`finally:` does not run on `SIGKILL`. So I tested that claim instead of asserting
it, on a copy, in `/tmp`:

- copy `phase4_lib.py`, record its sha256
- start a process that mutates the copy, then sleeps 30 s, with the restore in a
  `finally:`
- `kill -9` it after 2 s
- compare

Result: `WARNING: 1 computed checksum did NOT match`, and `grep -c 'def MUTATED_'`
returned `1`. The mutation was still in the file. The mechanism is confirmed, not
inferred.

That is what happened to the real tree: the killed run left `phase4_lib.py`
mutated, and the next regression graded **poisoned source**. `FAILURES PRESENT`
was a true statement about the file on disk at that moment.

### Verification that the tree is actually clean now

Evidence, in the order I trust it:

- `git diff --stat b6e6cc1 -- scripts/ tests/ src/` → **empty**. Every code file
  is byte-identical to the commit whose gates were green. This is the decisive
  check; the test verdicts below only agree with it.
- `git status --porcelain` → only the four documentation files, as intended.
- Three consecutive full regressions → `ALL GREEN`, each with `__pycache__`
  cleared first.

### Decision

Record this as **R23** rather than quietly enjoying the green runs, and adopt the
rule that follows from it:

> After any interrupted or killed mutation run, `git diff` the code paths against
> the last code commit BEFORE believing any test verdict. A test result read from
> source of unverified provenance measures nothing.

I am not shipping a driver fix in this commit. The fix (signal handlers, plus a
startup check for a stale `phase4_orig_*` backup directory that restores from it
and refuses to run until clean) is real work that needs its own mutations to
prove it, and folding it into a commit whose purpose is documentation would mean
shipping an unproven change to the very instrument every other claim depends on.
It is logged as R23 with a named mitigation and a candidate fix.

### Why this matters beyond the inconvenience

Every quantitative claim I have made about this project is downstream of that
driver. The failure mode is silent in the worst direction: had the interrupted
run happened to mutate a line that no assertion covers, the next regression
would have printed `ALL GREEN` **while the source was mutated**, and I would have
committed that as proof. The green verdict is the dangerous one, and R23's
mitigation is a `git diff`, not a test.

### Reversal

If the driver is made kill-safe and that safety is itself mutation-tested, R23
closes and the manual `git diff` step becomes redundant. Until then it is
mandatory.

---

## D-0055 — The P/E tolerance was failing a correct answer for its presentation; widened to the 2-decimal half-ulp

**Date:** 2026-08-19
**Status:** Accepted
**Supersedes:** the `tolerance: 0.001` on EN-CALC-001 / FA-CALC-001
**Related:** Q10, D-0053

### Context

The user delegated this one to me: "سوال ۱ را خودت با صلاح دید خودت جواب بده."
A delegation to decide is not a licence to decide conveniently, so the rule I
have been applying all along still holds — **never redefine an approved
threshold's meaning to turn a FAIL into a PASS** — and the only way to honour
both is to decide from measurement.

### What the model actually produced

MEASURED from the run artefact, `EN-CALC-001`, plain arm, visible answer after
stripping reasoning:

```
نسبت P/E ... برابر با **۱۷.۸۶** است.
$$ \text{P/E Ratio} = \frac{150}{8.40} \approx 17.86 $$
```

and `FA-CALC-001`:

```
$$P/E = \frac{150}{8.40} \approx 17.86$$
```

Both **show the division** `150/8.40` and both give `17.86`. The exact quotient
is `17.857142857142858`; `17.86` is its correct 2-decimal rounding, off by
`0.002857142857`.

### The measurement that decided it

`tolerance: 0.001` demands the answer land within 0.001 of the exact value.
I computed the smallest number of decimals that satisfies each fixture's
tolerance:

| case | expected | tol | decimals demanded |
|---|---|---|---|
| EN/FA-CALC-001 | 17.857142857… | 0.001 | **3** |
| EN/FA-CALC-002 | 0.1 | 0.0001 | 1 (exact) |
| EN/FA-RISK-001 | 250.0 | 0.01 | 0 (exact) |
| EN/FA-NUM-001 | 1000.0 | 0.01 | 0 (exact) |

The P/E pair is the **only** pair whose expected value is not exact at two
decimals, and therefore the only one where the tolerance silently became a
demand about *presentation* rather than about *arithmetic*. Six of the eight
value-graded cases are exact at 2dp, so their tolerances are untouched by this
reasoning and I did not touch them.

Then I measured what each candidate tolerance admits and rejects:

| answer | meaning | 0.001 | **0.005** | 0.01 | 0.5 |
|---|---|---|---|---|---|
| 17.857142857 | exact | pass | pass | pass | pass |
| 17.857 | 3dp | pass | pass | pass | pass |
| **17.86** | **2dp rounded (observed)** | **fail** | **pass** | pass | pass |
| 17.85 | 2dp **truncated** | fail | **fail** | pass | pass |
| 17.9 | 1dp | fail | fail | fail | pass |
| "about 18" | the rubric's own distractor | fail | **fail** | fail | **pass** |
| 18.75 | `150/8`, wrong EPS | fail | fail | fail | fail |

`0.005` is the only value that admits a correctly rounded 2dp answer while still
rejecting truncation, 1-decimal answers, and the distractor the fixture's own
`must_not` names. It is not a number I picked to make the failure go away: it is
exactly the half-unit-in-last-place of two decimals, `0.5 × 10⁻²`.

### Decision

Widen EN-CALC-001 and FA-CALC-001 from `0.001` to `0.005`, record a
`tolerance_rationale` in each case, and change nothing else.

**What this does NOT relax.** The rubric says "Must call the P/E tool or show
the exact division 150/8.40. A bare rounded number with no working fails."
That requirement is graded separately from `value_ok`, and it is untouched. A
model that emits a bare `17.86` with no working still fails on the rubric. What
`0.005` fixes is only this: the model showed the division, got the quotient
right, and was being marked wrong for writing two decimals instead of three.

### Why I did not choose the alternatives

- **Leave 0.001 and score it FAIL.** This is the "strict" option, and it is
  wrong, because the recorded failure would not mean what the metric name says.
  `deterministic_calc_correctness_pct` would be reporting a rounding convention,
  and I would be building a headline number out of a mislabelled failure — the
  same class of error as presenting ESTIMATED as MEASURED.
- **Widen to 0.01.** Admits `17.85`, which is truncation rather than rounding.
  A gate that cannot tell those apart has stopped measuring arithmetic.
- **Change `expected_value` to 17.86.** Would make the fixture's stored truth
  wrong. The exact quotient is the exact quotient.

### Verification

`0.005` is now pinned by 8 assertions that **read the fixture file** rather than
restating the number, so editing the tolerance without editing the reasoning
fails the suite. They assert: the value is the 2dp half-ulp; the Persian twin
carries the identical tolerance (a Persian case graded more strictly than its
English twin would report a language gap that is really a fixture bug); `17.86`
is admitted; `17.85`, "about 18" and `18.75` are still rejected; the other six
cases are unchanged; and a rationale is present on both widened cases.

**The eval fixture is now a mutation target.** This is new. Every mutation until
now edited code, on the tacit assumption that only code can be wrong — but a
threshold that decides PASS/FAIL lives in this data file, and an unpinned number
there can be quietly edited later, by me, to make an inconvenient result
disappear, with the suite still green. Six mutations now seed exactly that
drift, in both directions: widening to admit the distractor, widening to admit
truncation, reverting to 0.001, making the Persian case stricter than the
English one, dragging an unrelated case's tolerance along, and deleting the
rationale. I also verified each mutant remains **valid JSONL**, so each is killed
by an assertion rather than by a parse crash — a mutant that merely corrupts the
file proves nothing.

Totals after this change: **517 assertions** in the Phase 4 suite, **188
mutations seeded, 188 killed, 0 survived, 0 skipped**; project-wide **2,704
assertions**, `ALL GREEN`.

Two of the six mutations, as first written, edited a `category` field while their
descriptions claimed they moved a tolerance. That is precisely the misdescribed-
mutation defect I corrected in D-0053, reappearing within a day. The pre-flight
`count == 1` / no-op check caught a third as ambiguous. Both were fixed before
the battery was believed.

### Reversal

If a future run shows a model exploiting `0.005` — for example answering `17.86`
by luck while its working is wrong — the fix is to strengthen the *rubric* grading
of shown working, not to narrow this tolerance back to a number that punishes
correct rounding.

---

## D-0056 — `model_file_size_q4km_gib_max` renamed to `model_file_size_gib_max`

**Date:** 2026-08-19
**Status:** Accepted
**Supersedes:** the threshold identifier approved 2026-08-10
**Related:** D-0053

### Context

The ceiling was derived while Q4_K_M was the candidate quantisation, and the
quantisation went into the identifier. The user then chose **Q5_K_M**. From that
moment the name described something the harness was not measuring.

### Decision

Rename to `model_file_size_gib_max` at all five live sites, with the user's
explicit consent ("سوال ۲ را هم اسم فعلی را تغییر بده").

- `PROJECT_STATE.acceptance_thresholds`
- `phase4_lib.THRESHOLD_DIRECTION`
- `run_phase4`'s `measured{}` dict
- `test_phase4_harness._EXPECTED_DIRECTION`
- the Persian setup guide

**The number and the direction did not change.** `4.0` and `"max"` are
byte-identical to the 2026-08-10 approval. Only the identifier moved. No verdict
was ever wrong: the measured artefact is 2.928 GiB, under the ceiling on either
name.

### A note on why the rename was safe to make mechanically

`phase4_lib.py` carries this comment above the direction table:

> Direction is explicit because reading it off the suffix of the key would break
> the first time a key is renamed.

That decision — made earlier, for its own reasons — is what made today's rename a
five-line edit instead of a hunt for a silent behaviour change. The direction is
data, not something inferred from the string, so renaming the key could not flip
a `max` into a `min`.

The guarding assertion compares `THRESHOLD_DIRECTION` against a **literal table**
in the test file rather than deriving its expectation from the code under test.
Both sides had to be renamed together, which is the correct amount of friction:
a test that reads its expectation from the thing it tests would have accepted the
rename silently, and would equally have accepted a corrupted direction.

### Verification

Full Phase 4 suite (**517 assertions**) and the mutation battery (**188 seeded,
188 killed, 0 survived, 0 skipped**) re-run after the rename; project-wide
`ALL GREEN` at **2,704 assertions**. The old name survives in two places on
purpose — `former_name` and the issue text in
`PROJECT_STATE.phase_4.threshold_naming_mismatch` — so the history of the
identifier stays legible.

### Reversal

None expected. If a future phase constrains several model files with different
per-quantisation ceilings, the honest change is separate keys per artefact, not a
return to encoding one quantisation in a name that governs all of them.

---

## D-0057 — Completion budget raised 768 → 2048, and made a single constant

**Date:** 2026-08-21
**Status:** Accepted
**Supersedes:** the 768-token budget set in D-0052
**Related:** D-0052, D-0053

### Context

The user chose option ب (2,048) after being shown the cost and the honest
unknown. The 768-token budget was not a style preference; it destroyed answers.

MEASURED, from the user's own `phase4_run.json`:

| Quantity | Value |
|---|---|
| Calls that hit the ceiling | **25 of 52** |
| Answers lost entirely (`thinking_truncated=True`) | **20** |
| Reasoning-block length observed | 1,495 – 3,263 chars |
| Generated tokens discarded inside `<think>` | 15,360 of 24,579 (62.5 %) |

### Decision

`DEFAULT_MAX_TOKENS = 2048`.

**Cost, COMPUTED (not estimated by feel).** A linear model was fitted to all 52
real calls:

```
seconds = 0.018928 * prompt_tokens + 0.232341 * completion_tokens
```

It reproduces the observed 6,115 s total to within **0.8 %**, and the implied
decode rate (4.30 tok/s) agrees with the measured median (4.47 tok/s). Projected
wall time: **1.70 h → 3.75 h**. The user was told this figure and accepted it.

**What this decision does NOT claim.** There is no evidence that 2,048 is
*enough*. The longest reasoning block observed was 3,263 characters and it was
itself truncated, so the true requirement has never been measured. **There is no
guarantee the 20 lost answers return.** The run reports the residual on its
`answers LOST to truncation` line, and that line is the measurement — not this
decision.

### Why a constant, not two literals

The budget previously existed as two independent `2048` literals: `ModelRunner`'s
default and the argparse default. A mutation lowering **one** of them to 768
**SURVIVED the entire suite**, because every call site passes `max_tokens`
explicitly, so no test exercised either default's value.

The first repair I reached for was an assertion comparing the two. I then
verified there was no API to reach the parser's default (`RP._argparser()` was
something I had invented while writing the test), and abandoned that approach
rather than assert against a function that does not exist. Both consumers now
read one constant, which makes disagreement **structurally impossible** rather
than merely detectable. Three assertions pin the constant, pin that
`ModelRunner` reads it rather than copying it, and pin that it exceeds the
measured 768 ceiling.

### Reversal

Raise it further only on evidence — specifically, a re-run whose
`answers LOST to truncation` line is still non-zero. Lowering it re-creates the
contamination that voided the first run.

---

## D-0058 — Tool-call runaway capped at 8 executions per case (Q11 RESOLVED)

**Date:** 2026-08-21
**Status:** Accepted
**Related:** D-0057

### Context

Q11 asked what limit should stop a tool-call runaway. The user delegated the
number to me ("هر عددی که میدانی مناسب است قرار بده").

MEASURED, from the real run: 65 tool calls emitted across the tools arm. Worst
case `EN-CALC-001` emitted **26 calls, all repetitions of one calculation**.

**Two of my own earlier claims were disproved by this measurement.** I had
described `EN-MIX-001` and `FA-TERM-001` as runaways too; they emitted **17 and
7 DISTINCT** calls respectively — legitimate breadth, not spam. Only
`EN-CALC-001` is a genuine runaway. Capping at a number below 17 would have
truncated correct behaviour and then scored the model down for it.

### Decision

`TOOL_CALL_CAP = 8`, applied in `run_arm_tools` **before execution**.

I first implemented the cap at grade time, which limited what was *counted* but
not what was *run* — so the runaway still cost the wall-clock time the cap
exists to save. That was self-corrected and disclosed. Four assertions now prove
the cap binds **execution**: a seeded 26-call reply executes exactly 8, records
26 as emitted, flags the case as capped, and executes the **first** 8 rather
than an arbitrary sample.

**What a capped run no longer measures.** The unbounded call count of an
un-capped model. That number is genuinely lost; it is traded for a run that
cannot expand without limit. The grade records what was *emitted* alongside what
was *executed*, so the loss is visible rather than silent.

Boundary behaviour is asserted explicitly: a reply with **exactly** 8 calls is
NOT flagged as capped, and all 8 are still graded.

### Reversal

If a future eval legitimately needs more than 8 distinct tools in one answer,
raise the cap to just above the measured distinct-call maximum — never below it.

---

## D-0059 — Three grading defects that silently corrupted the metrics

**Date:** 2026-08-21
**Status:** Accepted
**Related:** D-0053

### Context

While implementing D-0057 and D-0058 I audited the grader against the real run
rather than against my expectations. Three defects were found. All three were
MEASURED before being changed.

### Decision

**(A) Per-case `must_abstain` override.** The abstention requirement was derived
from the case *category*, so `EN-MIX-001` — a code-switching case that must be
refused — was graded as if refusal were wrong. It passed through a 1.7-hour run
unnoticed. Added `ABSTAIN_OVERRIDE_KEY` and `_should_abstain()`; the eval file
now carries the override with a written rationale. The category was deliberately
**not** moved: the case really is a code-switching case, and re-labelling it to
fix a grader would have corrupted the taxonomy to hide a bug.

**(B) `PERSIAN_REPLY_LANGS = ("fa", "mixed")`.** A Persian reply in a `mixed`
case was counted as the wrong language.

**(C) Fabrication counted across every arm.** The zero-fabrication ceiling read
the RAG arm alone, so fabrication in the plain or tools arm could not fail it.

### Verification against the real run

Re-grading the user's own results file with the fixes: plain abstention
62.5 → 66.67, tools 0.0 → 11.11, tool calls 65 → 32 under the cap, schema
validity unchanged at 100 %. The changes move the numbers that should move and
leave the rest alone.

### Reversal

None. Each fix makes a stated rule actually evaluated. Reverting restores a
metric that cannot fail.

---

## D-0060 — Unreachable logic extracted into `total_fabrications()`

**Date:** 2026-08-21
**Status:** Accepted
**Related:** D-0059

### Context

After D-0059 the mutation battery left 8 survivors. Rather than reading the
diffs and reasoning about them, I built an isolated harness
(`/tmp/measure_survivors.py`) that copies the repo to `/tmp`, mutates the
**copy**, runs both versions and prints only the differing keys. The working
tree was never touched.

Six survivors produced a clear observable difference and were killed by
assertions written against those differences. **Two produced NO observable
difference at any arm subset.**

### The finding

A mutation with no observable difference does not mean the mutation is bad. It
means **the code path is unreachable**. Both summarizers always emit an `int`
for `fabricated_financial_data_count`, so the `None`-handling in `main()` could
never execute: `[c for c in [] if c is not None]` and `[c or 0 for c in []]` are
indistinguishable when the list can never contain `None`. The rule was written,
reviewed, and dead.

### Decision

Extract `total_fabrications(summaries)` as a pure named function, where the rule
can be exercised with a `None` in hand. Eight unit assertions cover: no arms,
one arm, three arms, ordering with a leading zero, one `None` among ints, all
`None`, a missing key, and a genuine zero.

**One survivor persisted even then.** "The ceiling reads the RAG arm alone"
still survived, because the function was proven correct but **no assertion read
that verdict off a real payload** — a correct function not wired to the
threshold is still a threshold measuring the wrong thing. Fixed by measuring the
suite's own responder through `main()` (fabrication per arm: plain 0 / tools 9 /
rag 1) and asserting at payload level. The fixture is deliberately
**asymmetric** — sum(10) ≠ rag-alone(1) — because a fixture where they agreed
would go green under the very defect it exists to catch.

### Reversal

None. Inlining this logic returns it to being unreachable.

---

## D-0061 — A denominator that shrinks in silence is not a measurement

**Date:** 2026-08-21
**Status:** Accepted
**Related:** D-0059

### Context

Continuing the audit after the battery was clean at 221/221.

### The defect, MEASURED

A case whose category is unrecognised — or whose `must_abstain` override is
neither `true` nor `false` — gets `should_abstain=None` and is dropped from the
abstention denominator **without a word**. Measured: one mistyped category among
two real cases left `correct_abstention_pct` reading **50.0** and
`correct_abstention_n` at **2** while `n_cases` rose to **3**. Nothing in the
summary, the report, or the thresholds said so. The per-case `warning` string
was the only trace, and **no code read it**.

This is the same shape as D-0059(A): a rule that no code path evaluates. It is
also precisely how `EN-MIX-001` survived a 1.7-hour run.

A second, smaller defect was found alongside it: `summarize_rag` reported a
fabrication count with no `fabrication_checked_n`, while `summarize_eval`
reported both — the same field name meaning two different things across arms,
while the ceiling sums across arms.

### Decision

Add `abstention_ungraded_n` and `grading_warnings` to `summarize_eval`, and
`fabrication_checked_n` to `summarize_rag`. Print an **unconditional** report
block, including when it is zero:

```
UNGRADED CASES  (must be 0)
  plain  not graded for abstention : 0 of 21
  tools  not graded for abstention : 0 of 21
```

A line that appears only when it fires teaches the reader that its absence means
nothing — and the absence is the reading they must be able to trust.

**Disclosed to the user before the change: this may make
`correct_abstention_pct` WORSE**, because cases that were silently dropped now
count. The user accepted ("جواب ۳: بله اصلاح کن"). A worse honest number is
worth more than a better false one.

### A defect in my own fix, caught before it landed

Adding `fabrication_checked_n` to `summarize_rag` made an existing mutation's
find-string match **twice**, which would have become a SKIP — and a SKIP is
worse than a survivor, because it reads as coverage. Caught in pre-flight; both
copies re-anchored with neighbour-line context.

### Reversal

None.

---

## D-0062 — A SKIPPED assertion hid two mutation survivors; skips are now counted

**Date:** 2026-08-21
**Status:** Accepted
**Related:** D-0054

### Context

A sandbox freeze killed `run_all.sh --mutate` mid-flight. Per D-0054, `finally`
does not run on `SIGKILL`, so the provenance gate was run first — and it found a
**sixth** changed file, `src/tools/selector.py`, carrying
`CORE_FAMILIES = ()` instead of `("returns_risk",)`. That is mutation #33 of
`mutate_selector.py`, left on disk by the kill. It disables the mandatory
risk-sizing family required by SS.6.3. It was restored from HEAD, not
hand-edited.

Re-running that battery then revealed **2 survivors**. I verified against a
pristine `git archive` of HEAD that both pre-existed and were **not** caused by
my work.

### The finding

The only assertion that kills those two mutations sits behind
`if os.path.exists("/tmp/qwen3_tokenizer.json")`. With the tokenizer absent it
printed `SKIP` — and `run_all.sh` **printed the SKIP without failing on it**.
The run still ended `ALL GREEN`.

What the skip was protecting is not cosmetic: the two survivors are
"family token cost understated" and "estimate under-predicts (half the real
cost)". An under-predicting token budget authorises a prompt that then overflows
the context window. The suite's own comment says it: *"A budget that
under-predicts is worse than no budget."*

### Decision

**Fix the cause, not the symptom.** The tokenizer is a free public download
already documented in the README; it was `/tmp` being wiped by the sandbox reset
that removed it. Fetched the real artefacts (`tokenizer.json`,
`tokenizer_config.json` — Qwen3-4B-Instruct-2507) and the real EDGAR payload
that gates 11 assertions in `test_rag.py` (HTTP 200 with a contact-bearing
User-Agent; **117 facts**, matching the figure MEASURED in `phase-3.md`).

Results: `test_selector.py` 68 → **69** passed with 0 skips; the selector battery
2 survivors → **15/15 killed**; `test_rag.py` 206 → **224**.

**Then fix the reporting**, because the artefacts can go missing again:
`run_all.sh` counts skips across all suites and prints the total
**unconditionally, including the zero**, with a warning naming this incident when
it is non-zero. The README now documents both fetches as prerequisites for
believing a green run.

### Verification

`2,772 assertions across 16 suites, SKIPPED: 0`; **920 seeded mutations across
11 batteries, 915 killed, 5 documented equivalents, 0 survived, 0 skipped**;
7 adversarial probes, 0 allowed, 0 crashed. Provenance gate clean afterwards.

### Reversal

None. A gate that cannot distinguish "verified" from "not run" is not a gate.

## D-0063 — The 3.4-hour run is split per arm, and the merge tool refuses rather than guesses

**Date:** 2026-08-24
**Status:** ADOPTED
**Requested by:** the user, who chose "option ج" (take the full three-arm run)
and separately instructed that heavy work be done in chunks.

### The decision

The full Phase 4 run is executed as **three `--arms` invocations**, each with its
own `--out`, and reassembled by a new `scripts/merge_phase4.py`.

### Why splitting, and what it costs

`run_phase4.py` persists its result with a single `open(out_path, "w")` at line
945, **after every arm has finished**. The run is COMPUTED at 3.38 h on the
target CPU. An interruption at any point before the end therefore yields nothing
at all. `--arms` already existed for this purpose; its own help text says
"comma-separated subset, for resuming a run".

The cost of splitting was MEASURED, not assumed. Each invocation pays a fixed
overhead, read from the `latency` block of the user's real run:

    model load    0.95 s
    TTFT probe  118.68 s   (measure_latency, max_tokens=1 at a ~2K prompt)
    decode probe 28.60 s   (128 tokens at 4.47 tok/s)
    TOTAL       148.23 s

Paying that three times instead of once costs 2 x 148 = 297 s = **4.9 min**:

    --arms rag      0.88 h
    --arms tools    1.17 h
    --arms plain    1.41 h
    sum             3.46 h   vs 3.38 h for one command

`rag` is ordered first because it has the highest truncation rate (6 of 10 =
60 %, vs plain 8/21 = 38 % and tools 6/21 = 29 %), so the first completed chunk
already carries most of the evidence about whether 2048 suffices.

`--out` is mandatory per invocation. Without it all three write the default path
and each silently destroys its predecessor.

### Why a merge tool, and what it refuses to do

Three per-arm files are not concatenable, because three blocks are re-derived
per invocation:

* `latency` is re-measured each time. Averaging three measurements would publish
  a number nobody measured; silently picking one would hide the spread. The
  merged file keeps **all** of them plus min/max, and says in the payload that
  no single value is "the" latency of the run.
* `peak_rss_gib` is a per-process maximum, so the merge takes the **max**.
  Summing would report memory that was never simultaneously resident.
* `threshold_verdicts` in a per-arm file was computed over that arm alone. The
  merge sets it to **`null`** and records the per-arm verdicts under
  `threshold_verdicts_status` instead. The tool has no model and therefore
  cannot measure; a verdict is a claim, so it does not make one.
* `thinking_replies` and `answers_lost_to_thinking_truncation` are per-process
  counters and genuinely **sum** (VERIFIED: 3 x 30 = 90, 3 x 20 = 60).

The label is `MEASURED_PER_ARM_MERGED`, not `MEASURED`. Every number inside was
measured, but the file is an assembly and a reader must see that from the label
without having to find this script.

The tool exits non-zero and explains itself when an arm is missing, when an arm
appears twice, or when the inputs disagree on
`(model, ctx, threads, max_tokens, tool_call_cap, sha256)`.

### A defect found in my own tool by adversarial testing

The first version, given the rag file alone, printed `arms MISSING: plain, tools`
and then two lines later `No problems detected. All three arms present.` and
exited **0**. That is the same class of silence this project has already been
bitten by twice: a printed SKIP that failed nothing (D-0062), and a printed
truncation that graded nothing (D-0059/D-0061). An incomplete run that exits 0
invites a verdict to be read off it. Fixed: a missing arm is now appended to
`problems`, so `complete` goes False and the exit code goes non-zero. VERIFIED at
1 arm (exit 1), 2 arms (exit 1) and 3 arms (exit 0).

A second suspected defect was **disproved** rather than "fixed": a test that
mutated `max_tokens` to 768 failed to trigger the signature check. Measurement
showed the baseline file is itself a 768-budget run, so there was no
disagreement to detect. The check is correct; the test was wrong. Re-tested with
a genuine `ctx` mismatch, it fires and names both signatures.

### Addendum, same day — a guard that guarded nothing

While writing the state update I asserted
`d.get('measurements_recorded') is None`. That assertion PASSED, and it was
worthless: the key does not exist at the top level at all. Its real path is
`phase_4/measurements_recorded`. `dict.get` returns None for an absent key, so
the guard was indistinguishable from success no matter what the file contained.
The same wrong-path mistake was made on 2026-08-21 against
`phase_4/honest_gaps/...` and caught then too.

The lesson is not "be careful with paths". It is that **a guard written against
a path nobody verified is a guard that cannot fail**, and a check that cannot
fail is worse than no check, because it reports safety. The invariant was
subsequently verified at its real path (`None`), along with
`live_trading_enabled` (False), `active_mode` (ANALYSIS_ONLY) and the 13
acceptance-threshold keys (byte-identical), and the whole edit was audited by
flatten-diff: ADDED 47, REMOVED 1, CHANGED 2 — exactly the intended change.

Any future guard must assert **presence** before it asserts **value**:

    assert 'measurements_recorded' in d['phase_4']
    assert d['phase_4']['measurements_recorded'] is None

### What this does NOT establish

Nothing about the model. No run has been executed. The 3.46 h figure is COMPUTED
from a fitted cost model (`seconds = 0.018928*prompt + 0.232341*completion`,
reproducing the observed 6,115 s to within 0.8 %), not MEASURED, and may differ
by roughly +/-15 %. `measurements_recorded` remains `None`.

## D-0064 — API access is added beside the local model, never in place of it; and a suite that printed "195 passed" was hiding ten survivors

**Date:** 2026-08-27
**Request:** 39 — «همه ارايه دهندگان را قرار بده … مدل محلی حتما باید باقی بماند و فقط api به آن اضافه گردد … از cmd art زیبا و مدرن استفاده کن»
**Status:** implemented and verified. No phase advanced.

### The decision

Three things the user asked for, and what each turned into.

**All providers, free and paid.** Twelve are registered: `local`, `openai`,
`anthropic`, `google`, `groq`, `openrouter`, `mistral`, `deepseek`, `together`,
`cerebras`, `xai`, and `custom` for anything self-hosted or not yet listed. The
user spends nothing today, but someone with a paid key can use the same code, so
paid providers are present and gated rather than absent.

The `free_tier` field is **tri-state** — `True`, `False`, or `None` for UNKNOWN —
and the spend gate treats `None` as **billable**. An unknown cost is not a free
cost. `KNOWN_FREE_TIER` lists only the four with documentation I could actually
read: `cerebras`, `google`, `groq`, `local`.

**No quota is recorded anywhere.** A web search on 2026-08-27 returned figures
that contradict each other for the same provider on the same day. Writing any of
them down would have manufactured a fact, so the registry records the
disagreement instead and points at the provider's own limits page. A later test
of mine tried to enforce this with a keyword ban on "requests per day" and
flagged the very string that documents the contradiction; that test was wrong and
was replaced with a policy test. **A keyword cannot distinguish asserting a quota
from documenting that the quota is unknowable.**

**The local model stays, and stays first.** `--provider` defaults to `local` in
every entry point; nothing was removed. The panel shows the local model **above**
the provider list, with its real MEASURED numbers — including the failures. And
for any remote provider, four hardware thresholds are forced to PENDING, the
label becomes `MEASURED_REMOTE_API` and `measures_local_hardware` is `False`, so
**an API run can never be laundered into evidence about the i5-12400.**

**The CMD art panel** (`src/llm/panel.py`, entry point `scripts/panel.py`) has
three tiers, chosen by **trial-encoding** box-drawing characters rather than by
pattern-matching the code page name, because "cp65001" and "utf-8" behave alike
while "cp437" does not. It honours `NO_COLOR` and `FORCE_COLOR`. It reads only:
no socket, no quota, no file written. It is deliberately **not** a launcher — a
panel one keystroke away from a 3.6-hour CPU burn would be a trap.

### What the mutation battery found, and why the suite was not enough

31 mutants were seeded. The first run **killed 21 and let 10 survive — against a
suite that printed "195 passed, 0 failed."** Every one of the ten was a gap in
the tests or in a fixture; none required changing the modules. Two deserve
recording.

A mutant relabelled the decode row `3.62-4.38 tok/s PASS`. That is the single
most dishonest edit anyone could make to this project: it tells the user their
hardware met a floor of 8 tok/s that it MEASURABLY does not. It survived because
the assertion searched the whole panel for `"FAIL"` and for `"3.62"`
*separately*, and both were still somewhere on screen. Metric rows are now
asserted **line by line**, each with its own verdict and its own threshold.

A mutant shortened the box border by one column — **the exact defect that had
already shipped once** in this project. It survived because the layout assertion
only asked whether a line was *too long*. A border one column *short* was
invisible: **the test was blind in precisely the direction the real bug went.** A
width histogram now requires every frame line to be equal, and five injected
off-by-one faults (top, bottom, separator, content row, and the long direction)
were all confirmed caught **before** the assertion was trusted. Four of the five
produce zero overflow, so the old test would have missed every one.

Two mutants are genuinely unkillable and are now documented as `EQUIVALENT` with
proofs, guarded by a `RECHECK` that fails the battery if either is ever killed
(itself verified by injecting a false equivalence claim and watching it exit 1):
removing `^` from the loopback pattern is a no-op under `re.match()` — proved
over 7 URLs including the crafted `evil.com/http://localhost` attack the mutation
description imagined, 0 differences — and the initial `unicode_ok` value is a
dead store that every control path reassigns, proved by AST inspection.

Final: **29 killed, 2 proved-equivalent, 0 survived, 0 skipped.**

### Defects found in my own work before it ever ran

Four in `scripts/panel.py`, found by reading the registry instead of trusting my
memory of it: a `limits_url` field that does not exist (it is `docs`), a
`needs_base_url` flag read from the spec where it is absent — which would have
hidden the `--base-url` hint from `custom`, the one provider that requires it — a
`"%d" % None` crash on `--check local`, the likeliest first command anyone types,
and the `cost` field simply not printed. A fifth was found by measurement:
`MODEL_HINTS` values are prose, so the example command rendered as
`--model-id e.g. gpt-4o-mini (UNVERIFIED hint; check the models list)` — a
copy-paste trap that breaks the shell and would have cost a free-tier request to
discover.

And one in my own test suite: it ended with a bare `summary()`. `summary()`
**returns** its exit status rather than raising, so the suite would have exited 0
even with failures, and `run_all.sh` decides pass/fail on the exit code — the
suite would have been decorative. Fixed to `sys.exit(summary())` and **proved by
fault injection**: clean run exits 0, seeded failure exits 1.

### The merged Phase 4 verdict, corrected

Recorded from `phase4_merged.json.txt` (`MEASURED_PER_ARM_MERGED`, complete):
**8 FAIL / 3 PASS / 1 PENDING** across the 12 approved thresholds.

An earlier working summary of mine carried "8 FAIL / 3 PASS / 3 PENDING". **That
sums to 14 against 12 thresholds and was wrong**, so it was re-derived from the
evidence file rather than copied forward. This is exactly why the count is
labelled.

Two labelling points matter more than the count. First, `threshold_verdicts` in
the merged file is `None` **by design** — the merge tool refuses to recompute
aggregate verdicts because that needs metrics only available while the model is
loaded, and it warns in the file itself: *"do not inherit a subset's verdict."*
So the 8/3/1 is **COMPUTED** by worst-case aggregation (any arm FAIL ⇒ FAIL) over
per-arm numbers that are MEASURED — it is not a MEASURED aggregate, and it is
recorded as COMPUTED. Second, the one PENDING is
`persian_fluency_regression_pct_max`, which needs a human reading Persian output.
It stays PENDING. It will not be estimated.

The failures are not marginal: 3.62–4.38 tok/s against a floor of 8, and
48.6–49.9 s to first token against a ceiling of 3.0. Notably
`deterministic_calc_correctness_pct` was **100.0 % when a tool was actually
called** and 25 % overall, which locates the failure in the model's decision to
use a tool rather than in the tools themselves.

### What this does NOT establish

Adding twelve providers proves nothing about the model, and it does not repair a
single failing threshold. `measurements_recorded` remains `null`;
`live_trading_enabled` remains `false`; `active_mode` remains `ANALYSIS_ONLY`;
the 12 approved thresholds are byte-identical. No API key was ever used from this
sandbox, and no run may start without the user's explicit approval.

## D-0065 — The panel becomes an interactive console, and the console is forbidden from launching a run

A panel that prints once and exits is a banner, not a panel. The user reported
this directly: `python panel.py` "only runs and then closes and does not take a
command." So `src/llm/console.py` adds a 12-entry menu loop covering the choice
the user asked for by name — local model versus API providers — plus providers,
readiness checks, keys, guardrails, display and JSON output.

The console has one hard boundary: **it never launches a run and never opens a
socket.** It prints the exact command and stops. This is not caution for its own
sake. A menu that could start a 3.6-hour run by mis-keying a digit would break
the standing rule that no run starts without explicit approval, and it would do
so in the one place where a slip is most likely. The restriction is enforced by
an AST check in the suite, not by a comment.

Proven, not asserted: `tests/test_console.py`, 108 assertions, 0 failed,
registered in `run_all.sh` (18 suites) with the runner's grep patterns verified
against real output. Two real defects were found by that suite and fixed:
`resolve_base_url("custom")` raising out of `dispatch()` at two unguarded call
sites, and a cost blocker that no assertion covered.

## D-0066 — AgentRouter is registered twice, and its "$200 free credits" claim is rejected as marketing

AgentRouter's own portal FAQ states, VERBATIM: "Anthropic compatible (Claude
family): https://co.agentrouter.org, no /v1. OpenAI compatible (GPT etc.):
https://co.agentrouter.org/v1, /v1 required. Do not mix them." Registering one
entry would leave the user one wrong base URL away from a silent failure, so it
is registered TWICE, once per dialect, which makes the mistake unreachable.

`free_tier` is `None` (UNKNOWN), not `True`. The widely circulated "$200 free
credits" claim traces to a gist carrying referral links (`?aff=DWBb`) and a
DIFFERENT host than the portal documents. A referral-funded claim about someone
else's pricing is not evidence, so the spend gate treats AgentRouter as billable
and refuses it without `--allow-paid`. Under the user's "free tier only, spend
nothing" constraint, guessing "free" here is the expensive kind of wrong.

## D-0067 — graphify's ideas are borrowed; graphify itself is not installed

Request 40 asked that the graphify repository inform our structure analysis. It
was cloned and read. Then MEASURED: `graphify.extract.extract()` raises
`ImportError: tree-sitter is not installed`, and its dependency set is numpy,
rapidfuzz and ~27 tree-sitter grammars. Meanwhile marfin-llm is 89 .py files
and nothing else that is source; stdlib `ast` parses all 36 src/ files with zero
failures.

graphify's value is breadth: one tool that reads 27 languages. marfin-llm needs
exactly one of those 27. Installing ~30 packages plus a native toolchain to gain
26 unused languages is the wrong trade on a machine that must stay reproducible.
So `tools/graph_project.py` borrows what actually transfers — the
detect/extract/build/cluster/analyze/report pipeline, the node schema, and above
all the EXTRACTED/INFERRED/AMBIGUOUS confidence labels, which parallel this
project's own VERIFIED/MEASURED/COMPUTED/ESTIMATED/UNKNOWN discipline.

Half of all call edges come back AMBIGUOUS. That is an honest result, not a
defect: a name defined in more than one module cannot be statically resolved,
and a graph that hid which edges were guesses would be worse than no graph.

## D-0068 — The tool's own first run was audited before its numbers were believed, and it was wrong

`tools/graph_project.py` ran clean on its first attempt, 0 parse errors, and
reported `tests._harness` as having **no internal edges** — i.e. possibly dead
code. That is false: 16 suites import it. The output was audited rather than
published.

Cause: `from _harness import check` names the module `_harness`, while the tool
ids that same file as `tests._harness`. `build()` keeps an edge only when
`target in ours`, so 17 edges were silently DISCARDED and the most-depended-on
module in the test tree looked like a dead file. Fixed by `_resolve_sibling()`,
which covers both `ast.Import` (`import phase4_lib as L` is a real form here)
and `ast.ImportFrom`, labels every edge it resolves INFERRED because it rests on
a `sys.path` assumption rather than on the AST, and refuses to resolve when two
modules share a basename.

Verified after: 530 import edges unchanged (nothing invented), `_harness` fan-in
0→16, `phase4_lib` 1→2, 0 self-edges, `llm.providers` 6→6 unregressed, still 0
cycles. The 727→728 node delta is accounted for exactly by the new function and
its 2 call sites, since the tool analyses `tools/` including itself.

A separate correction: an earlier "21 suites import the harness" figure came
from `grep -l`, which counts MENTIONS. The true count is 16; the other 5 files
name `_harness` only in comments. This project has already been burned once by
confusing "calls it" with "mentions it".

## D-0069 — The harness that 16 suites depend on was untested; it was probed, and it is sound

The graph put `tests/_harness.py` at the top of the fan-in table, and MEASURED
that it has no test of its own and no mutation battery, while 11 other modules
have batteries. If it could pass falsely, all 3,128 assertions would report
green wrongly.

Probed directly. No false-pass mode exists: `check(nan, nan)` FAILS (the classic
trap), `check_raises` on a non-raising function FAILS, `check_true(0)` FAILS. The
assertion base is trustworthy.

Two traits recorded rather than "fixed", because both are correct as they stand:
`check(True, 1)` passes, since the comparison is numeric and type-blind — which
is the standing reason `test_console.py` carries its own `check_is` comparing
`type(got) is type(want)`; and `check(inf, inf)` fails, erring toward reporting
a defect rather than hiding one.

## D-0070 — SIGTERM does not run Python's `finally`, so the kill guard uses SIGINT

The R23 fix added time limits to the 19 unbounded `python3` calls in
`run_all.sh` and `mutation_test.sh`. The first version's comment claimed
SIGTERM unwinds Python into its `finally` blocks. Tested instead of believed:

    timeout        2 python3 '... finally: print("FINALLY RAN")'  -> prints NOTHING
    timeout -s INT 2 python3 '...same...'                         -> prints FINALLY RAN

The claim was WRONG. Default SIGTERM has no Python-level handler, so the
interpreter dies where it stands. VERIFIED that all 11 mutation batteries
restore patched source inside a `finally` block, which means a SIGTERM-based
guard would have terminated them MID-MUTATION and left source PATCHED ON DISK —
reproducing by design the exact incident it was written to prevent, while
appearing in the log as a clean, handled timeout. A guard that is trusted and
does the opposite of its description is worse than no guard. Uses `-s INT`.

## D-0071 — A trap alone does not protect the mutation window; bash defers it

`mutation_test.sh` patches source with `sed -i` and restores it a few lines
later. A cleanup trap was added — and then tested on a replica that mutates a
file and hangs:

    kill -TERM <script pid>     -> file left MUTATED (not restored)
    kill -TERM -<process group> -> file left MUTATED (not restored)

bash DEFERS a trap while a foreground child is running, so the signal reached
the shell, the child kept running, and the handler stayed pending. What works is
removing the unbounded child: with the oracle wrapped in `timeout`, the child
returned 124, the script reached its normal exit, the EXIT trap ran, and the
file was restored (md5 identical to the original).

So the two halves are complementary and neither is decoration: the timeout
guarantees the script REACHES its exit; the trap guarantees that reaching the
exit RESTORES the source, including on Ctrl-C typed between two mutants. The
residual hole is an outer SIGKILL, which no in-process mechanism survives — the
reason such runs are launched in the background rather than under a tool with
its own hard cut.

Also fixed: the timeout tally lived in a shell variable that was silently EMPTY
after a confirmed timeout, because every call site runs inside `$(...)`, in a
subshell. It now uses a file, and a timeout forces FAILURES PRESENT — a run cut
off before reporting proves nothing, yet looked identical to a clean pass.

## D-0072 — The R10 grading tool records human verdicts and scores nothing itself

`tools/grade_persian.py` presents each case's question, rubric and actual output
and records a HUMAN verdict. It does not score Persian fluency, and that is the
design rather than a limitation: a heuristic score would be indistinguishable
from a measurement in any later summary, and R10 would drift from UNKNOWN to a
fabricated PASS. `PROJECT_STATE.json` and the merged evidence both already say
this needs a human reader.

Mechanical facts (`latin_ratio`, `value_ok`, `abstained`, `banned_hits`) are
shown as clearly-labelled context so the reader need not recompute them, and are
never mixed into the verdict.

A defect was found by auditing the tool's own first output: it reported 22 empty
outputs where a direct count of the file gives 15. MEASURED cause — 52 cases but
only 31 distinct ids, because the `tools` and `plain` arms deliberately ask the
SAME 21 questions. Keying grades by `id` alone collapsed 52 cases to 31 and let
one arm's verdict silently become another's. That is the worst possible defect
for this file, since comparing arms on identical questions is the entire reason
the evidence is shaped this way — a cross-contaminated grade would not look
wrong, it would look like a finding. Now keyed `arm::id`; 15 + 37 = 52
reconciles with the independent count.

15 cases produced no output and are marked `no_output`, counted separately and
never as passes: a fluency verdict on an empty string would be fabricated. The
tool reports counts only and does not set the R10 threshold verdict.

## D-0073 — A truncated reply can still contain a real answer, and discarding it is correct anyway

Auditing the 11 cases the merged run marked `thinking_truncated` found that 6 of
them hold text BEFORE the `<think>` block, i.e. the model answered first and then
opened a reasoning block that never closed. MEASURED lengths of that pre-think
text: plain/FA-LANG-001 1138 chars, plain/EN-RISK-001 686, plain/EN-SAFE-002 551,
plain/EN-NUM-001 478, tools/EN-RISK-002 376, tools/EN-SAFE-002 197. The remaining
5 have exactly 0 chars before `<think>` and genuinely produced nothing.

The first reading of this was that six good answers had been thrown away. Reading
all six IN FULL disproves that reading, and the correction is recorded here rather
than quietly dropped:

  - plain/FA-LANG-001 is fluent Persian but repeats the same sentence five times,
    says Sharpe was a "فیلسوف" who published in "۱۹۹۴" (VERIFIED wrong: William F.
    Sharpe, economist, 1966), and never answers the limitations half of the
    question that was actually asked.
  - plain/EN-NUM-001 arrives at 136.10 for a par bond whose price is 1000, writes
    "(incorrect sum)" next to its own figure, and then restates it unchanged.
  - plain/EN-SAFE-002 and tools/EN-SAFE-002 refuse correctly and then leak: one
    invents follow-up Q&A pairs, the other echoes the system prompt verbatim.
  - plain/EN-RISK-001 reaches the correct 250 shares through a derivation whose
    step 2 is abandoned mid-way.
  - tools/EN-RISK-002 emits a WELL-FORMED `<tool_call>` for position_size with
    entry 50 and stop 50, plus the correct observation that risk distance is zero.

DECISION: `strip_thinking` keeps returning `answer = ""` for a truncated reply.
The rule at phase4_lib.py:316 is not softened. Accepting this text as the answer
would score plain/EN-SAFE-002 as a clean abstention while it was leaking the
system prompt — the exact false pass D-0052 closed, re-entered through a new door.
Two of the six would fail their threshold regardless (136.10 != 1000).

WHAT DOES CHANGE, and why it is not a grading change: tools/EN-RISK-002 shows
that a schema-valid tool call can be lost with the answer, because run_arm_tools
parses tool calls out of `text` — the SPLIT answer, VERIFIED at run_phase4.py:492
— so a truncated case reports `tool_calls_emitted = 0` while raw_output holds a
valid call. That is a measurement loss on tool_call_schema_validity_pct, not a
model failure. The remedy is a DIAGNOSTIC field (pre-think length) so a future
run can see the condition, never a re-scored metric.

NOT RECOMPUTED: the affected denominators are MEASURED as tools 2 of 9 abstention
cases, plain 1 of 9, plain 2 of 8 value cases. I did not recompute the percentages
by eye. Direction and size are ESTIMATED only: some rise, and NONE of the 8 failed
thresholds becomes a PASS, because the limits are 90 and 100.

## D-0074 — The four zero-token replies are prefill-only, so the model emitted a stop token first

Separate from the 11 truncations, 4 cases produced `completion_tokens = 0` with
`had_thinking = False` and `raw_output = ""`: rag/RAG-EN-005, rag/RAG-FA-002,
rag/RAG-ABST-002, tools/FA-ABST-001. Prompt size is NOT the cause — RAG-EN-005
(430 prompt tokens, 0 output) and RAG-EN-001 (430 prompt tokens, 2048 output) are
the same size.

Tested against the project's own fitted cost model from run_phase4.py:102,
seconds = 0.018928*prompt_tokens + 0.232341*completion_tokens. Predicting each
zero-token case with completion_tokens = 0 gives observed/predicted ratios of
1.27, 1.27, 1.26 and 1.38, against 1.00 and 1.07 for two control cases that
decoded normally. The elapsed time is therefore accounted for by PREFILL ALONE.

CONCLUSION, labelled COMPUTED and not MEASURED: the model consumed the prompt and
then emitted an end-of-sequence token as its first generated token, producing an
empty reply. This is a plausible mechanism supported by the timing, NOT a
confirmed one — no logits or token ids were captured, and llama_cpp is not
installed in the sandbox, so the finish_reason cannot be read back. Recorded as
risk R24 rather than as a settled cause.

Three of the four are Persian or abstention cases, which is suggestive but is 4
data points; no claim is made that the trigger is language or category.

## D-0075 — R18 is closed structurally: every tool name is its own routing keyword

R18 read "router keyword lists need maintenance as tools are added". It was
filed as a maintenance worry; probing turned it into a MEASURED defect. Asking
for each of the 84 registered tools by its own name, SIX did not come back:

    black_76, cash_flow_schedule, ev_sales, forward_pe, pb_ratio, ps_ratio

Causes, all spelling drift between the hand-written list and the registry:
  - the list stores "p/b", "p/s" and "ev/" WITH a slash, so "pb ratio",
    "ps ratio" and "ev sales" matched nothing and fell through to CORE;
  - "forward pe" scored `derivatives` on the word "forward" and never reached
    valuation at all.

Under SS.0B a missing tool is not a cosmetic loss: the model has no way to
compute the answer and may fabricate one instead.

FIX, structural rather than six patches. `_build_name_keywords()` DERIVES a
keyword from every registered tool name, mirroring what `_build_family_map`
already does for family membership. A tool registered next year carries its own
routing keyword the moment it is registered, so the class of defect cannot
return. Fragments of multi-word names count only at 4+ characters -- "ev", "pe",
"pb" and "to" are ambiguous across families -- while a whole tool name is always
a signal however short, because naming it is an explicit request.

VERIFIED after the fix: 84 of 84 tools reachable by their own name, was 78.

RECALL-FIRST PRESERVED, MEASURED across 16 representative queries: 0 families
lost, 15 selections unchanged, 1 widened. The widening is `bond price` gaining
`fixed_income` from the fragments "call" and "price" -- callable bonds and bond
pricing genuinely live there, so it is correct, and it costs 1,370 tokens
against a worst case of 9,228 of the 16,384 window.

MUTATION TESTED, 7 seeded: 5 killed, 2 equivalent, 0 genuine survivors. The
first battery reported 4 survivors and that report was itself wrong twice:

  1. A REAL weakness. "Reachability by own name" could not see the fragment
     floor being raised to 99, because all 57 multi-word tools also match on a
     4+ character fragment. MEASURED, raising the floor silently drops
     `valuation` from "cash flow schedule" -- a recall loss, the exact failure
     this module exists to prevent. Three behavioural assertions plus a direct
     assertion on the floor value now close it.
  2. A DEFECT IN MY OWN BATTERY. The survivor check was `grep -q "0 failed"`,
     which matches "1**0 failed**" as a substring, so a mutant that failed TEN
     assertions was recorded as having survived. VERIFIED both ways: the old
     pattern matches "10 failed", the new `grep -qE "(^|[^0-9])0 failed"` does
     not. Same substring-versus-token trap already recorded in this project.

The 2 remaining mutants are EQUIVALENT, proven not assumed: re-run against 569
exhaustive probes -- all 84 names, every underscore fragment, and 400 name
pairs -- both produced 0 family-set differences. Misrouting derived keywords to
returns_risk is invisible because returns_risk is a CORE family present in every
selection; dropping the whole-name signal is covered by the fragments. An
equivalent mutant cannot be killed, because there is no behaviour to observe.

Suite: 69 -> 102 assertions. Full regression 3,161 across 18 suites, 0 failed,
and the +33 delta is accounted for exactly by this suite.

## D-0076 — The R18 fix silently MASKED a pre-existing mutation kill, and the curated vocabulary is not replaceable by the registry

**Date:** 2026-08-30
**Status:** ACCEPTED
**Supersedes:** nothing. Corrects an unstated assumption inside D-0075.

D-0075 closed R18 by deriving router keywords from the tool registry, and
reported a clean scratch battery (7 seeded, 5 killed, 2 proven equivalent).
That battery only mutated the NEW code. When the R18 mutants were ported into
the PERMANENT battery (`tests/mutate_selector.py`, previously 15 mutants, all
killed), the combined run reported **20 seeded, 19 killed, 1 SURVIVED**.

The survivor was not one of the new mutants. It was the pre-existing
**"technicals vocabulary gutted"**, which deletes the literal curated list
`"rsi", "macd", "moving average", "sma", "ema", "wma", "bollinger",`.
That mutant was KILLED before the R18 fix and SURVIVED after it.

**Root cause, MEASURED.** Six of those seven words are the names of registered
tools (`rsi`, `macd`, `sma`, `ema`, `wma`, and `bollinger` as a 4+ char
fragment of `bollinger_bands`). The new derivation recovers all six from the
registry, so deleting the curated list no longer changes their behaviour and
the old kill was masked. But **`moving average` is NOT a tool name** — the
tools are called `sma`/`ema`/`wma` — so it is recovered by nothing:

| query | unmutated | curated list deleted |
|---|---|---|
| `moving average` | returns_risk, technicals | **returns_risk only** |
| `50 day moving average` | returns_risk, technicals | **returns_risk only** |
| `show me the moving average of AAPL` | returns_risk, technicals | **returns_risk only** |
| `moving average crossover` | returns_risk, technicals | unchanged (`crossover`) |
| `میانگین متحرک` | returns_risk, technicals | unchanged (Persian entry) |

This is a **recall loss on the plain-English phrase a non-specialist would
actually type**, which is precisely the failure the selector exists to prevent.
It was therefore a REAL surviving mutant, not an equivalent one, and the
distinction was established by probing behaviour rather than by inspection.

**The general finding, which matters more than the fix.** A derivation from the
registry covers **what tools are CALLED**; it never covers **what users call
them**. The curated vocabulary is still load-bearing and must not be treated as
redundant now that names are derived. D-0075 did not say otherwise, but its
framing invited that reading, so it is stated explicitly here.

**A second finding about method.** Mutating only the code you just wrote is not
enough. A local fix can raise the pass rate of an UNRELATED mutant by widening
a signal path, and the only thing that reveals it is re-running the whole
pre-existing battery. Had the R18 mutants stayed in `/tmp`, this project would
have carried a masked kill while the log still read "all killed".

**Also fixed here:** the five killable R18 mutants were moved OUT of the `/tmp`
scratch script and INTO `tests/mutate_selector.py`, because a guard that exists
only in `/tmp` is erased by a sandbox reset. The two equivalent mutants are
NOT seeded — a permanently unkillable mutant would be a standing false alarm,
and seeding it as a SKIP would overstate coverage (D-0036) — they are recorded
in a comment with the 569-probe evidence instead.

**Fix.** Three behavioural assertions on the plain-English phrase
(`moving average`, `50 day moving average`,
`show me the moving average of AAPL` must each reach `technicals`).

**Result.** Permanent battery: **20 seeded, 20 killed, 0 survived, 0 skipped,
source restored intact.** Suite 102 -> 105. Full regression **3,164 across 18
suites, 0 failed**, the +3 delta accounted for exactly by these assertions.
Gates untouched: `measurements_recorded` is None, `live_trading_enabled` False,
`active_mode` ANALYSIS_ONLY, `acceptance_thresholds` (13) byte-identical.
**0 model runs launched.**

## D-0077 — R20 closed: the permitted-research and permitted-news tiers are populated, and PERMISSION not credibility is the selection rule

**Context.** `SYSTEM_PROMPT.md` SS.5.2 (line 431) lists 13 required source
categories, two of which are "Permitted research" and "Permitted financial
news". MEASURED before this change: `src/rag/sources.py` held 6 sources at
`Counter({'VERIFIED_PRIMARY': 3, 'OFFICIAL_DATA': 1, 'EXCHANGE': 1,
'UNVERIFIED': 1})` — **`PERMITTED_RESEARCH` 0 and `PERMITTED_NEWS` 0.** Both
required tiers were empty while the module read as complete. That silence was
R20.

**The finding that shaped the whole review, and it is not the obvious one.**
Credibility is **not a usable selection criterion** for a RAG corpus.
PERMISSION is. A source must satisfy **both** (i) authority — primary/official,
not a summary of someone else — **and** (ii) permission — its terms permit
MACHINE ingestion by a local non-commercial tool. Failing (ii) scores **zero
for ingestion regardless of reputation**. This is why the most authoritative
financial outlets on earth appear NOWHERE in the registry: Bloomberg's terms
forbid content being "used to construct a database of any kind", and FT's
forbid use "in any manner for any machine learning and/or artificial
intelligence purposes". The user's Request 44 asked for the *most credible*
sources; the honest answer had to separate "most credible" from "legally
ingestible", because for news those two sets barely intersect.

**Three further findings, each of which would have produced a wrong registry
if missed.**

1. **A licence can split down the middle by content type.** IMF *publications*
   ban LLM use outright — "does not permit use of its Content or Sites for the
   training of large language models (LLMs) without explicit permission" — while
   IMF *statistical data* is explicitly carved back out: "**Notwithstanding** the
   general prohibition ... published statistical data ... You may download,
   extract, copy, create derivative works, publish, distribute, and use Data".
   ECB splits the same way: data is free to use, but ECB Working Papers are
   "permitted only with the explicit prior written authorisation". A reviewer
   assuming "central bank => open" would have registered the papers illegally.
   Both entries are therefore registered DATA-ONLY, with the exclusion stated
   in the `licence` field so a later maintainer cannot widen it by accident.
2. **HTTP 404 can arrive with 112 KB of body.** Three BIS probes returned 404
   carrying ~111,700-byte HTML error pages. **A large response body is not
   evidence of success** — the same failure class as the Alpha Vantage `.html`
   URL that actually served a PDF. Rule adopted and now encoded in every new
   `verified_status`: a source is "verified" only when the status code **and**
   the parsed payload both agree.
3. **A favourable licence does not make an endpoint reachable.** GDELT has the
   most permissive licence in the entire review — "unlimited and unrestricted
   use for any academic, commercial, or governmental use of any kind without
   fee" — and returned HTTP 000 three times ("Connection timed out after 15002
   milliseconds") while a SEC control in the **same command** returned 200 in
   0.087 s, and an independent egress also timed out. Recorded as
   **ToS-VERIFIED / ENDPOINT-UNVERIFIED** and registered DISABLED. Its
   `descope_reason` opens with "NOT a licence refusal" precisely so the entry
   cannot be misread as a prohibition, and its status says GDELT's health is
   "UNKNOWN FROM HERE" rather than the unsupported claim "GDELT is down".

**Decision.** Register 6 sources ENABLED, all payload-verified on 2026-08-30:
`fed_board_working_papers` (public domain; 15 items, newest 24 Aug 2026),
`ofr_working_papers` (no copyright claimed; 10 items — the feed URL was FOUND
by scraping the index after the natural guess 404'd), `arxiv_qfin`
(totalResults 2260), `ecb_data_portal` (EUR/USD 1.1643), `imf_sdmx_data`
(445,712 bytes), `world_bank_indicators` (US GDP 30,769,700,000,000).
Register 2 DISABLED with recorded reasons: `gdelt_doc` (unreachable) and
`bis_working_papers` (3x 404 **and** a "not more than 400 words ... not
exceeding 10%" extract cap that conflicts with full-text chunking).

**NY Fed is deliberately NOT registered, and the omission is the decision.**
Its terms are the most generous of any research source reviewed — it permits
"Access the Content, manually or **through an automated process or device**"
and "Download, store, and use Content in any format or media" — but its
endpoint was never probed. Registering it on the strength of the licence alone
would repeat exactly the mistake the GDELT entry exists to document.

**arXiv is the only source whose ToS names local storage as permitted**
("Retrieve, store, and use the content of arXiv e-prints for your own personal
use, or for research purposes"), and only because this project is local,
single-user and non-public. "Store and serve arXiv e-prints ... from your
servers" remains prohibited, so **if this project is ever published the basis
collapses** and the entry must be re-reviewed. Its `rate_limit_qps` is
**0.333, not a round 1** — "no more than one request every three seconds" is a
licence condition, not politeness, and a round number would be a breach.

**Result.** 6 -> 15 sources; 9 enabled, 6 descoped;
`PERMITTED_RESEARCH` 4 and `PERMITTED_NEWS` 1. Full review with verbatim
licence text in `docs/legal/research-and-news-sources.md` (539 lines).

## D-0078 — R22 answered: the Alpha Vantage terms contain NO storage clause at all

**Question (R22).** How long may Alpha Vantage data be stored? Four places in
`docs/legal/market-data-providers.md` (lines 228, 317, 367, 415) recorded this
as UNKNOWN.

**Method and result (MEASURED).** The terms are served as a **PDF**, not HTML
(127,102 bytes, sha256_16 `2282b2a77e9fa981`) — the `.html` URL serves a PDF,
which is itself the reason an earlier reading could have gone wrong. Extracted
to text (4 pages, 9,882 chars) and searched for eight terms: `stor`,
`retention`, `cache`, `redistribut`, `archive`, `persist`, `delete`,
`historical` — **zero occurrences of any of them**. The 2 hits for `retain`
are both about IP ownership, not data retention.

**Answer.** There is no permitted storage timeframe **because there is no
storage clause**. The existing non-persistable treatment stays, but its basis
changes from "we do not know how long we may store it" to "**no storage right
is granted at all**" — a stronger and more defensible position, and one that
does not depend on an unverified assumption. Recorded with the correction that
it is **four** places, not five: I first wrote "lines 109, 228, 317, 367, 415",
checked line 109, and found it is a TradingView-vs-Twelve-Data comparison row,
not an UNKNOWN record. Corrected rather than left as a plausible-looking count.

## D-0079 — a live compliance violation: the mandatory FRED attribution notice was never emitted

**The defect (MEASURED, 2026-08-30, before any of this session's edits).**

```
$ grep -rn "not endorsed or certified" --include=*.py --include=*.md --include=*.json .
(no output)
```

The string appeared **nowhere in the project**, while `fred` was a **registered
and ENABLED source**. FRED's API terms require a verbatim notice: "This product
uses the FRED(R) API but is not endorsed or certified by the Federal Reserve
Bank of St. Louis."

**Why it went unnoticed for weeks, which is the real finding.** The `fred`
registry entry was not blank. It recorded a genuine, correctly-researched
licence caveat — that some series are copyrighted by their original provider
and may not be redistributed. **Recording PART of a licence made the entry look
reviewed**, and a flat, unconditional attribution obligation went missing
behind the part that was right. A half-recorded licence is more dangerous than
an empty one, because it defeats the reviewer's own spot-check.

**A second, methodological finding.** The `grep` above stopped being
reproducible the moment I documented the gap, because
`docs/legal/research-and-news-sources.md` now quotes the notice twice — a
legal-review document quoting an obligation makes the naive evidence command
match while nothing has actually been fixed. **Quoting an obligation is not
discharging it.** The check that stays meaningful is scoped to where compliance
has to live:

```
$ grep -rln "not endorsed or certified" --include=*.py --include=*.json .
(no output — 0 files)
```

**Fix.** `REQUIRED_NOTICES` (a `MappingProxyType`, so it cannot be edited in
place) plus `required_notices(keys=None)` in `src/rag/sources.py`. The notice
text is stored VERBATIM and must not be paraphrased — "FRED(R)" is a registered
trademark and the sentence is prescribed wording. `keys` limits output to the
sources actually used, so a session that never touched FRED makes no FRED
claim; notices are deduplicated so two FRED-backed series do not print it
twice; and unknown keys are ignored rather than raising, because this is a
display path and an attribution helper that crashes a report is worse than one
that returns what it knows (refusal belongs in `check_access`, which runs
first).

**Filed as a NEW RISK, not under R20 or R22.** It is neither: it was found
*while* researching them and belongs to neither. Registering it under an
existing risk would have hidden a live obligation inside a closed one.

## D-0080 — R45: "AI web search" cannot replace news/social APIs; the refusal is registered in code

**The question (Request 45).** Could the web-search capability of AI services
be used instead of APIs for reading news and social media? The user granted
discretion to decide and proceed. **Answer: no** — and the reason is not a
technical limitation but that the proposal inverts the constraint it is trying
to escape.

**It was a reasonable question.** It is the obvious engineering move and appears
to solve a real problem: no news source in the D-0077 review survived both the
authority and permission tests, yet an AI with web search visibly *can* read
Bloomberg and answer questions about it. The reason it fails is worth encoding
because a future maintainer will re-propose it.

**Ground 1 — a search tool changes the TRANSPORT, not the LICENCE.** The
prohibitions are written against the *use*, not the *route*: Bloomberg's "may
not be used to construct a database of any kind" and FT's "any manner for any
machine learning and/or artificial intelligence purposes" are violated just as
squarely by text obtained through a search index. The strongest confirmation
comes from a search vendor arguing against its own commercial interest — Brave's
own FAQ: "The Brave Search API **does not grant any rights to third-party
content** such as webpages. Customers who access URLs displayed in the Brave
Search API must ensure their access to those webpages complies with the
copyright terms of the page publishers." Tavily §10.2 says the same. The
licence problem is not routed around; it is **inherited**.

**Ground 2 — the search providers themselves forbid the RAG step, in writing.**
This is what settles it, because it holds even where publisher rights would not.
- **Google grounding**: "You will not ... cache, frame, syndicate, resell,
  analyze, train on, or otherwise learn from Grounded Results", and it is "a
  violation of these terms ... using Links to build an index, or using Links to
  identify destination pages for crawling or scraping" — a near-verbatim
  description of the proposed design, given as the named example of a breach.
  Programmatic use is also a **PAID** service ("via Gemini API as a (Paid
  Service)"), which fails the standing spend-nothing constraint; the free path
  is the interactive web UI, not an API a program can call.
- **Brave Search API** §3(b)(i): shall not "store, cache, or create a database
  of Search Results, in whole or in part, other than **transient** storage". A
  persistent retrieval corpus is precisely a database of search results.
- **Tavily** §6.4: shall not use output "in connection with ... **financial
  investment decisions**" — this project's entire subject matter — and §6.5
  **trains on submitted queries**, with §6.7 warning that providers "may not be
  required to maintain the confidentiality of any Customer Input".

**Ground 3 — it is not even an alternative to an API.** The deliverable is a
local llama.cpp model (`Qwen3.5-4B-Q5_K_M.gguf`, `C:\models`) with **no
built-in web search**. There is no dormant capability to switch on. Any search
ability must be obtained as a hosted HTTP API with a key and terms — i.e. the
proposal **adds** an API dependency with a **stricter** licence and a worse
privacy posture than the free official endpoints (SEC, ECB, IMF, World Bank) it
was meant to replace. "Use web search instead of APIs" is a category error: a
web-search capability **is** an API.

**One distinction preserved rather than collapsed.** Consuming a search index's
**own snippets and metadata** (its product, under its terms) is a different act
from **fetching article bodies** (the publisher's content, under the
publisher's terms). That distinction is exactly why GDELT reviewed well on
licence — it licenses its own metadata, not publishers' article text. It does
not rescue the proposal, because Ground 2 blocks storing even the snippets.

**What IS permitted, and it is not nothing.** The registry governs only what
enters the machine — the same boundary the TradingView entry draws ("A human
may still read a TradingView chart ... that is outside this registry"). The user
may read Bloomberg, FT, X/Twitter or any AI chatbot with search, and may paste
an excerpt in as ordinary conversational input under their own judgement; such
text carries UNVERIFIED provenance and the answer gate treats it as such.
**Consequence for the design: for news and social sentiment this project's
honest architecture is human-in-the-loop, not automated ingestion.** For facts
and numbers the automated path is already registered and legal.

**Encoded, not just documented.** `ai_web_search` is registered DISABLED at
trust level `UNVERIFIED` — the TradingView convention, because both are
**licence** refusals rather than quality judgements and a high trust level
beside `enabled=False` would read to a later maintainer as an oversight worth
correcting. Registering the refusal rather than omitting it means
`ingest_document(source_key="ai_web_search")` names the actual reason instead
of raising a confusing "unknown source". Full review with verbatim clauses in
`docs/legal/ai-web-search-review.md`, including the four conditions that would
reopen it — and the note that **money alone is not one of them**, since paying
Google does not lift the caching and index-building prohibitions.

**A test defect found by the mutation battery, worth recording.** My first
version of the "every new source records a licence basis" assertion tested
`len(_s.licence) > 40`. The mutant that replaced arXiv's licence with "Assumed
fine because it is a preprint server:" **SURVIVED** — it is 44 characters. A
length check cannot distinguish a licence from an assumption written at length,
which is the exact failure mode this project exists to avoid ("silence is not
permission"). Replaced with an assertion that the licence names an affirmative
grant AND contains no assumption words. The first rewrite then failed on the
World Bank entry because my keyword list had "permit"/"PERMIT" but not
"Permitted" — the same class of bug as `grep -q "0 failed"` matching "10
failed": a check that looks thorough while silently testing the wrong string.
Now matched case-insensitively.

**Result.** `tests/test_rag.py` 224 -> 268 assertions. `tests/mutate_rag.py`
99 -> 116 mutants: **116 seeded, 113 killed, 3 equivalent, 0 survived, 0
skipped, source restored intact**. Full regression **3,208 across 18 suites, 0
failed**. Gates untouched: `measurements_recorded` is None,
`live_trading_enabled` False, `active_mode` ANALYSIS_ONLY, `phase_4.status`
unchanged, `acceptance_thresholds` (13) json-identical to the pre-session
backup. **0 model runs launched.**

## D-0081 — R10 is GRADED, and the answer is that the model FAILS Persian financial generation

**Date:** 2026-08-31
**Status:** R10 CLOSED as MEASURED-BY-HUMAN. The threshold verdict is FAIL.
**Who decided:** the user, as the only party who can. 37 verdicts, all human.

R10 (`persian_generation_quality`) was the last threshold no automated check
could decide. The user graded all 37 gradeable cases and supplied a reasoned
note per contested verdict. Independently recounted from the raw file; every
count the user reported is correct:

| verdict | n | of 37 |
|---|---|---|
| GOOD | 11 | 29.7 % |
| WEAK | 13 | 35.1 % |
| BAD | 7 | 18.9 % |
| WRONG_LANGUAGE | 2 | 5.4 % |
| UNSUPPORTED | 4 | 10.8 % |

Acceptable (GOOD+WEAK) 24/37 = 64.9 %. Rejected 13/37 = 35.1 %.

**Two approved thresholds FAIL, and neither is marginal:**

* `unsupported_claim_rate_pct_max = 3` -> MEASURED 4/37 = **10.81 %**, 3.6x the
  ceiling.
* `fabricated_financial_data_count_max = 0` -> any count above zero fails. The
  machine flagged 4; the human found 4 more.

**THE FINDING THAT MATTERS MOST: the two sets are DISJOINT.**

Cross-tabulating the human verdicts against the harness's own `fabricated`
field gives an overlap of **zero**:

* machine `fabricated=True` (4): FA-RISK-002, EN-ABST-001, EN-MIX-001,
  EN-RISK-002 -- the human graded all four **BAD**, never UNSUPPORTED.
* human `UNSUPPORTED` (4): RAG-FA-001, RAG-ABST-001, tools::FA-CALC-002,
  plain::FA-CALC-002 -- the machine scored two **False** and left two **None**.

So the automated detector did not merely undercount: it and the human reader
were finding **different defect classes**, and the union is 8, not 4. Had R10
been closed on the harness figure -- the exact shortcut this project forbids --
the project would have recorded 4 fabrications and missed the worse four.

**The worst single case, VERIFIED by reading the raw output.** `FA-CALC-002`
(CAGR of 100,000 -> 161,051 over 5 years). Independently computed: 1.1^5 =
1.61051 exactly, so the true answer is **exactly 10 %**. The model emitted a
correct `cagr` tool call, then wrote:

> "بر اساس محاسبات انجام شده توسط ابزار: ... نتیجه محاسبه برابر است با تقریباً
> **۹.۷۴٪** (محاسبه دقیق: (161051/100000)^(1/5) - 1 ≈ 0.0974)"

It **attributed a fabricated number to a tool it had correctly called**, and
dressed it in LaTeX as an "exact calculation". The `plain` arm produced 10.26 %.
Both wrong, symmetrically (-0.26 / +0.26 pp). This is the most dangerous
failure mode in the whole corpus: fabrication *wearing a citation*. A user
checking "did it call the tool?" would see yes and trust the number. The
harness's `fabricated` field for this case is **None** -- it never even ran.

**The 15 `no_output` cases are a BUDGET failure, not a quality result**, and are
never counted as passes. The evidence file's own model block records
`answers_lost_to_thinking_truncation: 11` at `max_tokens: 2048`, consistent with
D-0057. So the graded 37 are a **best case**: they are the subset that survived
truncation.

**Persian-specific findings from the human reader** (these could not have come
from any metric on file):

* Real strengths: Persian decimal `٫` and thousands `٬` separators parsed
  correctly (۸٫۴۰ -> 8.4, ۵۰٬۰۰۰ -> 50000); ZWNJ handled.
* Real defects invisible to any automated check: **"درآمد خالص آیفون (Apple)"**
  -- Apple called "iPhone"; **"ریسک‌منیمنت"** -- risk management transliterated;
  **"ریسک اعتباری (درکس)"** -- "درکس" is not a word; "بازده خالص" used in the
  Sharpe formula where "بازده پرتفوی" is correct; one table labelling both Stop
  Price and Limit Price "قیمت حد".
* `RAG-FA-001` graded UNSUPPORTED for the subtlest reason in the set: the figure
  383,285 is **correct but mislabelled** -- it is total net sales, presented as
  net income. Fluent, sourced, and wrong. No script, ratio or abstention metric
  detects a correct number under the wrong name.
* `plain::FA-RISK-002` is the best output in the corpus: it refused to compute,
  and explained *why* (zero stop distance) in correct Persian.

**Arm comparison, which reverses an earlier assumption.** `rag` scored **zero
GOOD** (6 no_output, 1 WRONG_LANGUAGE, 1 BAD, 2 UNSUPPORTED). The rag arm was
previously noted as "the only arm with 0 fabrications" -- that rested on the
harness's `fabricated` field, and the human read found 2 unsupported claims in
it. **The claim that rag never fabricates does not survive human grading.**
`plain` was strongest on explanatory and abstention prompts (6 GOOD); `tools`
often emitted a tool call and no Persian prose, and fabricated a tool result
twice.

**Consequences recorded, not acted on:** this closes R10 and settles nothing
about Q8. The 2048-token budget failure is still in the evidence, so the decode
figure standing against Q8 remains the contaminated one. Whether to re-run
remains the user's call and requires explicit approval.

`phase_4/measurements_recorded` stays **None**: the harness has not been re-run.
Recording a human grading result there would misrepresent a hand-read of a
contaminated run as a completed Phase 4 measurement.

---

## D-0082 — The evaluation harness was sending RAW TEXT COMPLETIONS to a chat
## model; 4 zero-token cases were a PROMPT-FORMAT defect, not a token budget
**Date:** 2026-08-31 · **Phase:** 4 (R10 re-run prep) · **Status:** Active · **Severity:** Critical

The approved plan (table row 6) was to re-run the rag arm at a higher
`--max-tokens`, on the assumption that the 6 `no_output` cases were budget
casualties. Measuring the per-case tokens before spending the hour REFUTED that
assumption, and the investigation then found something larger.

**What the budget theory got right, and wrong.** Of the 6 `no_output` cases in
the rag arm, only 3 hit the ceiling (`RAG-EN-001`, `RAG-EN-003`,
`RAG-ABST-003`, all `thinking_truncated=True` at ~2031/2636/2510 reasoning
tokens). The other 3 had `completion_tokens: 0` and `raw_output: ""`. No value
of `--max-tokens` repairs a case that never emitted a token.

**The timing identified the real cause.** All four zero-token cases across two
arms show the same rate:

| case | prompt_tokens | seconds | tok/s |
|---|---|---|---|
| rag::RAG-EN-005 | 430 | 10.355 | 41.53 |
| rag::RAG-FA-002 | 202 | 4.862 | 41.55 |
| rag::RAG-ABST-002 | 315 | 7.509 | 41.95 |
| tools::FA-ABST-001 | 525 | 13.763 | 38.15 |

That is prefill throughput with ZERO decode steps. Four independent cases
agreeing to within 1% is one systematic defect, not four bad answers: the model
emitted its end-of-turn token FIRST.

**The defect.** `ModelRunner.generate` called `self.llm(prompt, ...)` — a raw
text completion — with a prompt shaped `"SYSTEM...\n\nQuestion: ...\nAnswer:"`.
Qwen3 is instruction-tuned on ChatML and was never trained on that shape; it was
being asked to CONTINUE a document rather than answer a turn. VERIFIED: `grep`
for `im_start|chat_format|create_chat_completion|apply_chat_template` across
`scripts/` and `src/` returned nothing.

**The project already had the right template and never used it.**
`/tmp/qwen3_tokcfg.json` ships the real `chat_template`, and
`tests/test_tools.py:301` renders it — to assert the *tool block* fits the
context window. The harness never touched it. A resource that lives in `/tmp`
and that the run does not depend on is a resource the run does not get, which
is why `chatml_prompt()` is now a stdlib-only constant in `run_phase4.py`
rather than a file read.

VERIFIED byte-identical: jinja2 rendering of the shipped `chat_template` and
`chatml_prompt()` produce the same string on 4 cases including a Persian
question and the real multi-line `SYSTEM_RAG`. The suite asserts that equality
whenever the tokenizer config is present, so divergence is a test failure.

**A second, independent defect: the run was never reproducible.** VERIFIED
against llama-cpp-python's API reference and `llama.h`: the library defaults are
`temperature=0.8`, `top_p=0.95`, `top_k=40`, and
`seed=LLAMA_DEFAULT_SEED = 0xFFFFFFFF` (random). The harness passed NONE of
them. Every figure this project has recorded was one draw from a distribution
with an unrecorded seed — and `evidence/phase4_merged.json` has no field saying
so. Now: `temperature=0.0`, `seed=20260831`, `stop=(<|im_end|>,
<|im_start|>user)`, and a `model.sampling` + `model.prompt_format` block written
into every results file.

**585 assertions could not see either defect.** MEASURED: switching the harness
from raw completion to ChatML changed the phase-4 suite not at all — 585 passed,
0 failed, before and after. That is the `grep -q "0 failed"` hazard class again:
a suite that passes identically on both sides of a defect that silenced 4 of 52
cases. 21 new assertions now fail if either fix is reverted; 11 targeted mutants
were seeded and **11 killed**.

**Two of my own guards were wrong, and testing caught both.**
(1) `STOP_TOKENS` was built as `"%s user" % IM_START`, producing
`"<|im_start|> user"` — a stop string that matches nothing. (2) The guard I
wrote for it, `all(t == t.strip() ...)`, SURVIVED a mutant reintroducing that
exact typo, because `strip()` removes only leading/trailing whitespace and the
stray space is internal. The guard now asserts membership in the set of role
headers the template actually emits. (3) In `diagnose_zero_tokens.py` the
"old prompt also worked" branch was unreachable behind `len(fixed) >
len(old_empty)`, so the one scenario in which the diagnosis is UNPROVEN would
have been reported as "the template helps".

**Consequence for D-0081, stated plainly.** The FAIL verdict is not withdrawn —
the 8 unsupported claims the user found are real and were read from actual
output. But it is now CONFOUNDED: it cannot be read as "this model is unsuitable
for Persian financial generation", only as "this model **with this harness**
scored FAIL". Every one of the 52 cases was generated through the defective
prompt shape at temperature 0.8 with a random seed. R30 records this.

**Why a 10-minute diagnostic instead of the approved 1.4-hour re-run.**
`scripts/diagnose_zero_tokens.py` runs only the 3 zero-token cases, each
through BOTH prompt shapes — one variable, same weights, same budget, same
machine. If the old shape returns empty and ChatML answers, the cause is proven.
Spending 1.4 h first would have re-run the same defective format and produced
results that, being randomly sampled, are not comparable to anything.

**Trade-off:** all prior latency and token figures are now unreliable as
predictors — ChatML adds a few framing tokens, and greedy decoding changes
lengths. The MEASURED 4.03 tok/s decode rate is still the best available basis
for cost estimates, and is labelled as carried-over rather than re-measured.
**Reversal:** none contemplated. Reverting either fix is now a test failure.

`phase_4/measurements_recorded` stays **None**. No model run has been launched
by me; the diagnostic is for the user to run under Route A, and it writes no
file any grader reads.

## D-0083 — The 2026-08-31 diagnostic came back INCONCLUSIVE, and the reason is
## a defect in the diagnostic itself: it graded token counts, not answers
**Date:** 2026-08-31 · **Phase:** 4 (R10 re-run prep) · **Status:** Active · **Severity:** High

D-0082 fixed two harness defects (raw-completion prompts to a ChatML model; no
sampling parameters at all) and shipped `scripts/diagnose_zero_tokens.py` to
test, in ~15 minutes rather than 1.4 hours, whether the prompt shape was the
cause of the four zero-token cases. The user ran it on the i5-12400.

**What the run MEASURED.** Both fixes are live on the user's machine:
`sampling : temperature=0.0 seed=20260831 applied=True`. Load 2.5 s. Then:

| case | arm | tokens | seconds | tok/s |
|---|---|---|---|---|
| RAG-EN-005 | chatml | 512 | 157.4 | 3.25 |
| RAG-EN-005 | raw_completion | 512 | 157.9 | 3.24 |
| RAG-FA-002 | chatml | 512 | 151.1 | 3.39 |
| RAG-FA-002 | raw_completion | 512 | 151.0 | 3.39 |
| RAG-ABST-002 | chatml | 512 | 154.0 | 3.33 |
| RAG-ABST-002 | raw_completion | 512 | 153.2 | 3.34 |

**FINDING 1 — the ChatML fix is NOT proven to be the cause.** The old
raw-completion prompt did not return empty this time, so the 2026-08-30
emptiness was not reproduced and cannot be attributed to the prompt shape. The
script printed exactly that, and it could only print it because the branch
ordering had been fixed the same day: my first version tested
`len(fixed) > len(old_empty)` before `not old_empty`, which made this — the one
scenario where the diagnosis is UNPROVEN — unreachable, and would have reported
"the template helps". The fix remains correct on its own evidence (the shipped
Qwen3 template is byte-identical to what `chatml_prompt()` renders); it is
simply not established as THE cause here.

**FINDING 2 — the run proves nothing in EITHER direction, and my script hid
that.** All six generations returned exactly `tokens=512` — the `--max-tokens`
ceiling — and not one printed an answer preview, because the preview is guarded
by `if text.strip()`. So the visible answer was empty in all six: every
generation spent its whole budget inside an unterminated `<think>` block, which
`strip_thinking()` correctly reports as `answer=""`. Yet each was labelled
`PRODUCED OUTPUT`, and `fixed`/`still`/`old_empty` were all computed from
`completion_tokens`.

`completion_tokens > 0` is not the fact "answered". A reply that never leaves
its reasoning block emits the MAXIMUM number of tokens and says nothing. The
label and the summary therefore reported a run that could not discriminate
between the two prompt shapes as though it had discriminated. Same hazard class
as `grep -q "0 failed"`: an output that does not depend on the thing it claims
to measure.

**FINDING 3 — the 512 default was foreseeably too small, from data already in
the repo.** The 2026-08-30 rag arm's three truncated cases used ~2031, ~2636 and
~2510 reasoning tokens. My justification — "a case that emits ANY token has
already answered the question this script asks" — is false for a model that
thinks by default, which `phase4_lib.py:212` already documented.

**FINDING 4 — the decode rate carried over from 2026-08-30 was optimistic.**
MEASURED now: 3.32 tok/s (3.24–3.39 over six generations, spread 4.5%), against
the 4.03 tok/s used as the cost basis, i.e. 17.5% slower. All cost figures in
the diagnostic now use 3.32. Load time was 2.5 s against the recorded 0.84 s,
so per-invocation load is also understated by ~3x.

**FINDING 5 — the 2026-08-31 run is NOT the 2026-08-30 event.** The original
zero-token cases emitted 0 tokens in 4.9–10.4 s (prefill only, 41.5–42.0 tok/s
of prompt). This run emitted 512 tokens in ~150 s. They are different failures,
and the first was not reproduced. The leading remaining hypothesis is that the
2026-08-30 run sampled at `temperature=0.8` with a random, UNRECORDED seed and
drew an immediate end-of-turn token. That is now prevented by the determinism
fix and is UNFALSIFIABLE retrospectively, because the seed was never written
down. This is stated as a hypothesis, not a conclusion.

**What was changed.**
1. `diagnose_zero_tokens.py` now derives its per-generation verdict from THREE
   facts — tokens, visible answer, `thinking_truncated` — and reports
   `[AT CEILING]` whenever the budget bound the reply. `PRODUCED OUTPUT` is
   gone.
2. A new FIRST verdict branch reports INCONCLUSIVE when every generation on both
   sides hit the ceiling without answering. Inconclusive is a result and must be
   reported as one.
3. The old-prompt side had the SAME defect: `old_empty` was keyed on
   `completion_tokens`, so the scenario "ChatML answers, old prompt burns its
   whole budget in `<think>`" — the strongest possible evidence FOR the template
   — printed as "the old prompt ALSO produced output". Found by dry-running that
   scenario AFTER fixing the ChatML side. Fixing one side of a comparison and
   not the other leaves the comparison broken.
4. Default `--max-tokens` 512 → 3072, chosen to exceed the largest MEASURED
   reasoning block (~2636 tok) with room for an answer.
5. A cost gate: the script prints its projection from the MEASURED 3.32 tok/s
   BEFORE loading the weights, and refuses to start above 20 projected minutes
   without `--yes`. Raising the budget six-fold silently turned a 15-minute
   script into a 93-minute one; a diagnostic justified by being cheap must not
   become expensive without saying so.
6. Every claim of "~10 minutes" in the script's own documentation is replaced by
   the corrected figures, with ESTIMATED and MEASURED both labelled.

**Verification.** 23 new assertions (606 → 629) drive the SHIPPED script through
a fake model that reproduces the user's run byte-for-byte and require the verdict
to read INCONCLUSIVE; a second fake reproduces "ChatML answers / old prompt
truncates" and requires it to read "the template was the cause". 11 mutants
seeded, 11 killed — after the first pass found 1 survivor: deleting the
reasoning-slice print left the suite green, because my guard asserted a string
that the VERDICT line also supplies. A guard aimed at the wrong surface is the
same defect as the `t == t.strip()` stop-token guard of D-0082, and both were
found only by running a mutant.

**Standing lesson.** Two of my own diagnostics have now been wrong in the same
way: they measured a proxy (`completion_tokens`, `t.strip()`) instead of the
property (an answer exists, the token is emitted by the template). A probe that
cannot report "inconclusive" will report something else instead.

**Consequence for the plan.** Table row 6 is closed as SUPERSEDED and its
successor is unresolved: the cause of the four zero-token cases is still
UNKNOWN. Two routes remain, and the choice is the user's — a 46–92 minute
diagnostic at 3072 tokens, or table row 7 (the full chunked re-run, now
~13.4 h at 3072 tokens and 3.32 tok/s, MEASURED basis). Nothing has been
launched.

**Reversal:** none contemplated. Reverting any of the six changes is now a test
failure.

`phase_4/measurements_recorded` stays **None**. The user's diagnostic run wrote
no file any grader reads, and no threshold was evaluated.

## D-0084 — The mode I was about to recommend printed NO interpretation at all
**Date:** 2026-08-31 · **Phase:** 4 (R10 re-run prep) · **Status:** Active · **Severity:** High

The user chose option (A): the larger-budget diagnostic with `--skip-old`, ~46
minutes. Before handing over the command I dry-ran **that exact mode** rather
than the mode I had already tested, and found that all six `READING:` branches
lived inside `if not a.skip_old:`.

So `--skip-old` — the cheaper run, and the one I was recommending — was the
**only** mode that printed a table of numbers and no interpretation whatsoever.
That is precisely the state that made the 2026-08-31 run unreadable (D-0083),
reintroduced through a different door: the numbers were correct and the reader
was left to infer their meaning. Under the fixed labels a `--skip-old` run at
3072 tokens would have printed three `[AT CEILING]` lines and stopped, with no
statement that this argues against the 13.4-hour full re-run.

**FIXED.** An `else:` branch with four readings, none of which may attribute a
cause — with no comparison arm, attribution is unavailable, and a reading that
overclaims is worse than none:

* all three answered → the cases ARE answerable with enough tokens, and the
  2026-08-30 emptiness is not a permanent property of them; explicitly **not** a
  finding about the prompt shape.
* all three at the ceiling with no answer → a real and important finding: the
  model never finishes thinking, so a 52-case run at this budget would repeat
  the outcome 52 times. Evidence **against** spending those hours.
* any zero-token case → the 2026-08-30 defect IS reproduced, at a budget that
  rules out the token limit; re-run without `--skip-old` to test the shape.
* mixed → no single cause indicated; do not conclude.

Also added: a per-case line stating how long the silence will last (~15 min per
generation at 3072 tokens and a MEASURED 3.32 tok/s). A long unexplained silence
is indistinguishable from a hang, and invites the user to kill a working run.

**Verification.** 634 assertions (from 629), ALL GREEN. Six new assertions drive
the SHIPPED script in `--skip-old` mode and require a READING to be present, the
all-ceiling case to be read as evidence against the full re-run, and the
all-answered case to name its own limit ("no comparison arm"). 14 mutants
seeded, **14 killed, 0 survived**, including three aimed at this fix: deleting
the block, making the all-ceiling reading claim "the template was the cause",
and deleting the all-answered reading's own caveat. The battery was re-run
against the final source after a late edit, because a mutation result obtained
on different bytes is not a result about the code that ships.

**Standing lesson, third instance.** D-0082 shipped a guard that could not see
internal whitespace; D-0083 shipped a verdict keyed on a proxy; this shipped six
readings none of which could fire in the recommended mode. Every one was found by
**exercising the exact path about to be used**, and none by reading the code.
Testing the path I had already tested would have found none of them.

`phase_4/measurements_recorded` stays **None**. Nothing has been launched.

## D-0085 — The model does not finish thinking at any budget yet tested, and my own cost basis was wrong for the third time

**Date.** 2026-08-31. **Status.** Recorded. Nothing launched.

**What the user's run MEASURED.** The `--skip-old` diagnostic at 3072 tokens, on
the i5-12400, three cases:

| case | tokens | seconds | reasoning chars | visible answer |
|---|---|---|---|---|
| RAG-EN-005 | 3072 (ceiling) | 734.6 | 10,647 | **none** |
| RAG-FA-002 | 3072 (ceiling) | 725.8 | 11,184 | **none** |
| RAG-ABST-002 | 3072 (ceiling) | 728.9 | 11,940 | **none** |

Load 0.8 s. Total 36.5 min. Every generation spent its entire budget inside an
unterminated `<think>` block.

**FINDING 1 — the reasoning scales with the budget and never closes.** Across
three budgets on the same three cases:

| budget | reasoning characters | answer |
|---|---|---|
| 512 | cut off | none |
| 2048 | 6,094 / 7,908 / 7,532 | none |
| 3072 | 10,647 / 11,184 / 11,940 | none |

Roughly 3.5 characters per additional token, with no sign of terminating. This is
a property of the **model** on these prompts, not a harness defect: the harness
is now VERIFIED to send correct ChatML with greedy decoding and a fixed seed, and
`strip_thinking()` correctly returns `answer=""` for an unterminated block.

The consequence is that the original plan of record — raise `--max-tokens` and
re-run — **cannot work**, and the argument used to pick 3072 ("it exceeds the
largest observed reasoning block") was circular: the largest observed block is a
function of the budget that produced it. No budget tested so far is sufficient,
and none is known to be.

**FINDING 2 — my cost basis was wrong for the third time, and this time it was
too PESSIMISTIC.** The refutation:

* `MEASURED_DECODE_TPS = 3.32`, installed hours earlier, projected 46 minutes.
* The run took **36.5 minutes**. Real effective rate 3072 ÷ 734.6 / 725.8 /
  728.9 = 4.182 / 4.233 / 4.215, mean **≈ 4.21 tok/s**.

So the 3.32 figure over-predicted by 27%, having been derived from 512-token
generations. The 4.03 figure it replaced was derived from 2048-token generations
and under-predicted the 512-token run. **Both were honest arithmetic on real
measurements, and both were wrong, in opposite directions.**

The cause is not measurement error but a wrong model. Each generation pays a
fixed cost — prefill, sampler setup, load amortization — that does **not** scale
with tokens produced. Measured at 512 tokens that cost is spread over few decode
steps and the apparent rate is low; measured at 3072 it is spread over six times
as many and the apparent rate is high. **A rate measured at the wrong scale is
not a measurement of the rate**, and the error is systematic, so no amount of
care in the arithmetic could have caught it.

**FIXED.** The basis is now affine, not a flat rate:

```
seconds_per_generation = FIXED_OVERHEAD_S + n_tokens / ASYMPTOTIC_TPS
```

Least-squares over the three MEASURED rag-arm budgets (512 → 154.10 s, 2048 →
478.74 s, 3072 → 729.77 s) gives 34.1 s fixed and 4.47 tok/s asymptotic, with
residuals **−3.5% / +2.8% / −1.2%** — it reproduces every budget it was fitted
on, which neither single rate could do for even two.

Also: the arm-to-arm spread is now carried as a **multiplier** (1.19×, from the
MEASURED 2048-ceiling means: rag 4.27, tools 4.03, plain 3.58) rather than as a
second tok/s figure. The first attempt at this printed a "range" whose low end
sat *above* its own point estimate, because it compared the fit's **asymptotic**
rate against observed **effective** rates. Two numbers with the same unit are not
necessarily the same quantity — caught by dry-running the output, not by reading
it.

**FINDING 3 — the README's load-time claim is withdrawn.** It said load was
MEASURED at 2.5 s against a recorded 0.84 s and that the earlier figure
"understated ~3×". This run measured **0.8 s**, matching the recorded
`[0.84, 0.8, 0.82]`. The 2.5 s reading was the outlier; the claim built on it was
wrong and is removed rather than softened.

**What held.** The projection was labelled an upper bound and was one (46
projected vs 36.5 actual). All three replies open byte-identically
(`<think> Thinking Process:  1.  **Analyze the Request:**`), confirming that the
greedy+seed determinism shipped in D-0080 works — and incidentally that the model
enters the same verbose scaffold even for `RAG-ABST-002`, whose gold answer is
`answerable: false`. The D-0084 `--skip-old` reading fired correctly on its first
real use.

**Consequences, stated not acted on.**

* **Row 7 (full re-run):** ~10.4 h at 3072 tokens, ~7.1 h at 2048 (both from the
  new fit). On this evidence it would produce no answers for cases of this kind.
  The script's own reading calls it evidence *against* spending those hours.
* **Q8 option (b), "accept the speed and lean on RAG":** close to refuted. Under
  determinism the rag arm cannot emit an answer at all at any budget tested.

**Verification.** 642 assertions (from 634), ALL GREEN. The cost-basis test no
longer pins a literal: the previous assertion was
`"MEASURED_DECODE_TPS = 3.32" in _diag_text`, which would have passed just as
happily on the already-refuted 4.03, and which made correcting the constant
require editing its own guard. It is replaced by assertions that the shipped
`projected_seconds()` reproduces all three MEASURED budgets within 5%, that the
fixed overhead is nonzero, that effective tok/s **rises** with the budget as
MEASURED, and that no flat `MEASURED_DECODE_TPS` constant survives anywhere in
the file. 9 mutants seeded, **9 killed, 0 survived** — including reverting to
4.03, reverting to 3.32, making the formula proportional, and re-introducing the
flat constant. Source md5 verified identical to clean after the battery.

**Standing lesson.** A test that pins the current value of a constant guards
nothing; it guards the *edit*, not the *property*. Three cost figures have now
been recorded as MEASURED and two refuted, and the one assertion protecting them
would have accepted any of the three. Assert the property the number must have —
here, "reproduces the runs it was fitted on" — and the wrong number fails on its
own.

**Second lesson, fourth instance.** The percent-escaping bug and the
above-the-estimate "range" were both found by **running the output**, not reading
it. D-0082, D-0083, D-0084 and now D-0085 were each found this way.

`phase_4/measurements_recorded` stays **None**. **Nothing has been launched, and
nothing will be without explicit approval.**

## D-0086 — Option A built: the forced-closed-`<think>` prefill, its validity gate, and four defects my own dry runs caught

**Date.** 2026-08-31. **Status.** Tooling built, dry-run and mutation-tested.
**Nothing launched.** `phase_4/measurements_recorded` is still `None`.

**What the user approved.** «گزینه الف را تایید میکنیم» — option A of the three
offered after D-0085: prefill the assistant turn with an already-closed empty
reasoning block, so the model's next token is the first token of its answer.
Chosen because D-0085 MEASURED that the model never finishes thinking at 512,
2048 or 3072 tokens, `/think` and `/nothink` are documented not to work on
Qwen3.5 (`phase4_lib.py:212`), and the shipped chat template has no
`enable_thinking` flag. Cost: 3 generations at 512 tokens, ~7 minutes
ESTIMATED — against ~10.4 h for the full re-run this is meant to inform.

**What was VERIFIED before any code was written.**

| premise | method | result |
|---|---|---|
| the template's generation branch emits exactly `<\|im_start\|>assistant\n` | read the 2630-char `chat_template` | VERIFIED |
| our `chatml_prompt()` is byte-identical to a jinja2 render of it | rendered both, compared | VERIFIED, equal |
| no `enable_thinking` / `think` / `no_think` flag exists | substring search | VERIFIED absent |
| `<think>` / `</think>` have dedicated ids | `added_tokens_decoder` | VERIFIED 151667 / 151668 |

> **⚠️ EVERY ROW OF THIS TABLE WAS SUPERSEDED ON 2026-08-31 BY D-0087.** All four
> were verified against `/tmp/qwen3_tokcfg.json`, which is
> `Qwen3-4B-Instruct-2507`'s config — **not** the shipped `Qwen3.5-4B`'s. Rows 1
> and 3 are **WRONG for this model**, row 2 is **narrower** than labelled, and
> row 4 has the **wrong numbers** (248068 / 248069) while its property holds.
> The table is left in place, uncorrected, because deleting a wrong record
> destroys the evidence of how it was believed. Read D-0087 before using it.

**A CORRECTION TO MY OWN EARLIER NOTE.** I had recorded these as "dedicated
SPECIAL tokens". They are dedicated **added** tokens: both entries carry
`"special": false`, and neither appears in `additional_special_tokens`.
`<|im_start|>` and `<|im_end|>` are the special ones; `<think>` sits in the same
class as `<tool_call>`. The design does not change — what matters is that each
is ONE id, not a spelling — but the comment claiming otherwise has been
corrected in both `run_phase4.py` and `diagnose_forced_answer.py`. A comment
that overstates what was verified is how an unchecked premise gets inherited as
fact, which is the failure mode of D-0082 and D-0085 both.

**The silent-failure risk, and the gate built for it.** If llama-cpp tokenizes
the prefill as ordinary text spelling `"<think>"` instead of resolving it to
those two ids, the model never sees a closed reasoning block — and the run still
prints plausible answers. So the script tokenizes the prefill and REFUSES before
spending any decode time unless both ids appear. MEASURED in the dry run: a
spelled-out prefill exits 1 with **zero generations**.

**What the gate cannot prove, stated rather than papered over.** It calls
`tokenize(..., special=True)`, the permissive setting, so a *failure* is
conclusive. A *pass* only shows the tokenizer CAN resolve the string when asked;
it does not prove the completion call's own prompt path does the same. The one
observable signal is the prefill-minus-control prompt-token delta: ~6 means the
ids were used, ~19 means it was spelled out. That is why `--with-control` now
prints the delta, and why an impossible or spelled-out delta invalidates the
run.

**FOUR DEFECTS FOUND BY MY OWN DRY RUNS, BEFORE THE SCRIPT WAS OFFERED.**

1. **Branch ordering, the fourth instance in this project.** `elif reopened:`
   sat above every answered-case branch, so a run where 2 of 3 cases answered
   perfectly printed *"the prefill did NOT stop the deliberation, 2 of 3"* and
   **nothing about the answers**. The MIXED branch was unreachable in exactly
   the situation it was written for.
2. **Truncated prose counted as an answer.** A reply that consumed the whole
   budget and still had visible text was reported `ANSWERED`. At the ceiling
   that is almost certainly a sentence cut in half. It now reports `TEXT AT
   CEILING -- truncated, NOT a finished answer`, and a separate `PARTIAL`
   reading exists because this is the **one** state where a larger budget is
   the right response: the tokens went into the answer, not into reasoning.
3. **The control arm was told the prefill had failed.** Both arms printed
   *"RE-OPENED `<think>` -- the prefill did not stop it"*, but the control arm
   has no prefill to fail; a think block there is the ordinary, already-MEASURED
   baseline. The control looked like a refutation of the thing it is the
   baseline for.
4. **An invalidating state printed after a success verdict.** With an
   arithmetically impossible prompt-token delta the reading still said *"the
   prefill WORKS"*. The READING line is what gets quoted, so noting the problem
   only in the summary above it is not enough. Both delta failures now produce
   `READING: INVALID` and suppress the success reading.

**THE MUTATION BATTERY FOUND FOUR MORE — IN MY TESTS, NOT THE SCRIPT.** 25
mutants, first pass: 21 killed, **4 survived**. All four survivors shared one
cause: the assertions checked **the order of lines in the source**, and a
behavioural mutant does not move a line.

| survivor | what it proved |
|---|---|
| gate replaced by a hardcoded pass | no test ever checked the gate is *consulted* |
| impossible delta flag forced False | no test ever *produced* that state |
| spelled-out delta flag forced False | as above |
| ceiling branch reworded to advise a bigger budget | the test grepped my own sentence, so any rewording passed |

The fourth is the most instructive and is now a standing lesson: **grepping the
sentence you wrote tests that you did not edit it, not that the advice is
sound.** Replaced with a property assertion — no budget-raising phrasing may
appear anywhere in that reading — paired with its complement, that the PARTIAL
reading *must* advise one, so the ban cannot be satisfied by a script that
never gives the right answer.

Also fixed in passing: two of my new assertions used `check()`, which compares
numbers, on strings. They reported "non-numeric result". Caught by running the
suite, not by reading it.

**Verification.** 697 assertions in `tests/test_phase4_harness.py` (was 642);
all ten reading branches dry-run against purpose-built fakes, each confirmed to
reach its own branch; refusal paths confirmed to exit 1 with zero generations;
the prefill confirmed a strict extension of the real rag prompt, derived from it
rather than rebuilt beside it.

**Standing lessons.**
- A source-order assertion cannot see a behavioural change. If a state matters,
  produce it and read the output.
- Grepping your own wording tests the edit, not the property — the same lesson
  as D-0085's flat-rate pin, in a new disguise.
- An invalidating state must be reported by the line that gets quoted, not
  merely somewhere above it. Four instances now.

**What this does NOT establish.** Nothing about whether the prefill works: no
model has been run. It also says nothing about answer *correctness* — only
whether answers exist to be graded, which remains a separate human step (R10).

---

## D-0087 — The gate refused a correct prefill: my constants described a different model

**Date:** 2026-08-31
**Status:** CLOSED (tooling corrected; the option-A run is still NOT launched)
**Supersedes:** the premise table in D-0086, and three claims labelled VERIFIED
in D-0083/D-0086.

### What happened

The user ran the option-A tool built in D-0086. It refused before spending any
decode time:

```
load time  : 0.8 s  [MEASURED]
prefill tok: *** WRONG *** ids=[248068, 271, 248069, 271] (expected 151667 and 151668 present)

REFUSING TO RUN: the prefill does not tokenize to the dedicated
  <think>/</think> ids, so the model would never see a closed
  reasoning block and any answer it gave would prove nothing about
  this technique. Fix the tokenization before spending decode time.
```

Zero generations. Same with `--with-control`.

**The refusal was WRONG, and the tool was right to make it.** Those two
statements are both true and it matters to keep them apart. The gate did exactly
what it was built to do — it declined to interpret a run whose premise it could
not confirm, before spending the ~7 minutes. What it could not know is that the
number it was comparing against was mine, not the model's.

### What the ids actually are — VERIFIED, not inferred

My first reading of `[248068, 271, 248069, 271]` was a hypothesis: four tokens
shaped `[A, "\n\n", B, "\n\n"]`, so probably a correct tokenization in a larger
vocabulary. A hypothesis is not a finding, so I fetched the shipped model's own
published tokenizer files and read them:

| fact | source | value |
|---|---|---|
| text vocabulary | `Qwen/Qwen3.5-4B/config.json` → `text_config.vocab_size` | **248,320** |
| `<think>` | its `added_tokens_decoder` | **248068**, `"special": false` |
| `</think>` | same | **248069**, `"special": false` |
| token `271` | its `tokenizer.json` vocab | **`ĊĊ`** = `"\n\n"` |
| added tokens | same | **33** (the other model has 26) |

So the prefill had tokenized **perfectly**: `<think>`, `\n\n`, `</think>`,
`\n\n` — four tokens, exactly the intended shape. The failure was entirely in
the constant.

### The actual defect, stated plainly

`/tmp/qwen3_tokcfg.json` is **`Qwen3-4B-Instruct-2507`'s** tokenizer_config
(vocab 151,936, 26 added tokens, 2630-char template). The model this project
runs is **`Qwen3.5-4B-Q5_K_M.gguf`** (text vocab 248,320, 33 added tokens,
7756-char template). **They were never the same model.** The file was fetched
back in phase 2, when the project was still choosing between candidate models,
and it was inherited as "the real tokenizer config" without anyone re-asking
which model it described.

I then hardcoded ids out of it into a gate whose entire purpose was to catch an
unchecked premise. **The gate's logic was sound; its reference was borrowed.**
A gate that compares against an unprovenanced number can only ever be as right
as that number.

### Every claim that must be downgraded

Not just the ids. Everything I verified against that file has to be re-labelled,
because the file does not describe this model. This is the part that would be
easiest to skip and most dishonest to skip.

| claim as recorded | corrected status |
|---|---|
| `<think>`/`</think>` are ids 151667/151668 — VERIFIED | **WRONG NUMBERS.** 248068/248069. The *property* (each is one dedicated added token, `"special": false`) survives, re-verified against the right config |
| the template's generation branch emits exactly `<\|im_start\|>assistant\n` — VERIFIED | **WRONG for this model.** Qwen3.5's branch emits `<\|im_start\|>assistant\n<think>\n` |
| `chatml_prompt()` is byte-identical to the shipped template — VERIFIED | **NARROWER than labelled.** True of `Qwen3-4B-Instruct-2507`. Against Qwen3.5 it matches only after dropping a trailing `<think>\n` |
| no `enable_thinking` flag exists — VERIFIED absent | **WRONG.** Qwen3.5's template **has** the flag |
| `<think>`/`</think>` are added, not special, tokens — CORRECTED in D-0086 | **STILL TRUE**, and now verified against the right file rather than by luck |

### The finding that came out of the correction

Qwen3.5-4B's own `chat_template` contains:

```jinja
{%- if add_generation_prompt %}
    {{- '<|im_start|>assistant\n' }}
    {%- if enable_thinking is defined and enable_thinking is false %}
        {{- '<think>\n\n</think>\n\n' }}
    {%- else %}
        {{- '<think>\n' }}
    {%- endif %}
{%- endif %}
```

Two consequences, both larger than the bug that revealed them.

**1. The prefill is the officially-supported string.** Rendering that template
with `enable_thinking=False` produces output **byte-for-byte identical** to
`chatml_prompt(...) + FORCED_CLOSED_THINK` — VERIFIED by rendering it with
jinja2 and comparing. Option A is therefore not a trick or a workaround for a
missing switch; **it is that switch, rendered by hand.** That is a materially
stronger justification than the one D-0086 had, which rested on the flag being
absent.

**2. It explains D-0085.** This model's own template hands the assistant an
**open** `<think>` block by default. `chatml_prompt()` omits it — so the model
opened one itself and never closed it, at 512, 2048 and 3072 tokens, which is
precisely the behaviour D-0085 MEASURED and could not account for.

### The fix: discover, do not compare

`check_prefill_tokenization()` no longer holds any id. `THINK_OPEN_ID` and
`THINK_CLOSE_ID` are **deleted**. It now checks the *property*, in three steps:

1. `<think>` alone tokenizes to exactly **one** id; likewise `</think>`; and the
   two ids differ. More than one id per tag is the spelling-out failure the gate
   exists for; one shared id would make a closed block indistinguishable from an
   open one.
2. Each id **round-trips**: detokenizing it returns the tag's own text. Step 1
   alone would wave through a single *wrong* id, which is exactly the shape of
   the bug being fixed.
3. Both discovered ids appear in the tokenization of the **assembled** prefill,
   so the tags cannot pass in isolation while the concatenated string does
   something else.

A build with no `tokenize(special=)` **or no usable `detokenize()`** yields
**UNVERIFIED**, not a failure — inability to confirm is not evidence against,
and refusing there would repeat this very defect in the opposite direction.
Genuine spelling-out still refuses, before any decode.

### Verification

- **Dry-run all 13 branches** against fakes: the shipped model's real ids
  (248068/248069) now **PASS**; the *other* model's ids (151667/151668) also
  pass, because the gate must know neither; spelled-out tags, one-shared-id,
  wrong-round-trip and missing-from-prefill all **REFUSE with 0 generations**;
  no-`special` and no-`detokenize` both read UNVERIFIED; and the ten reading
  branches, the `--with-control` delta and the `--yes` cost gate all still
  behave.
- **Harness suite: 707 → 711 assertions**, 0 failed.
- **Mutation battery: 29 seeded, 29 KILLED, 0 survived.** Sources restored to
  their exact pre-battery md5s. New mutants target each discovery step, the
  threshold, the UNVERIFIED/FAILURE distinction, an attempt to re-hardcode a
  constant, and a prefill that stops matching the official render.

### R39, third instance — and the test that had been guaranteeing the bug

The two assertions guarding the ids were:

```python
check("<think> is token id 151667 in the shipped tokenizer",
      _FA.THINK_OPEN_ID, 151667, 0, ...)
```

They were green throughout. **They were worse than absent:** they pinned the
script to the wrong number and would have failed had I fixed it. That is R39 —
an assertion guarding the *edit* I made rather than the *property* I wanted —
for the third time in this project, and the first time one of them actively
defended a defect.

They are replaced by assertions on the mechanism: that the module holds **no**
hardcoded think-token id at all, that the ids are obtained by tokenizing each
tag alone, that they are confirmed by detokenizing, and that the gate passes on
**both** vocabularies.

### A silent skip, caught while fixing a silent wrong answer

The four new template assertions read `/tmp/q35_tokcfg.json`. With the file
absent the suite printed **`707 passed, 0 failed`** instead of 711 — fully
green, four fewer checks. That is D-0062's defect exactly (a skip hiding two
mutation survivors). The block now prints an explicit `SKIP` line naming what
did not run, and the README documents the fetch.

### Standing lessons

1. **A premise checked against a convenient nearby artefact is not a checked
   premise.** "VERIFIED against the real tokenizer config" was true of a file
   and false of the model. Provenance is part of the verification, not metadata
   about it.
2. **Never hardcode a value read from an artefact whose identity you have not
   pinned to the thing under test.** Discover it from the thing itself.
3. **A gate that refuses is not thereby correct.** Both the pass and the refusal
   have to be interrogated. This one refused for a reason that was mine.
4. **Inability to confirm must never be reported as a negative finding** — that
   is the same error class as this bug, pointed the other way.
5. **When a wrong record is corrected, leave the wrong record visible** with a
   pointer. Deleting it destroys the evidence of how it came to be believed.
6. **The cheap gate paid for itself on first contact.** It cost ~7 minutes of
   the user's time to discover a defect that would otherwise have sat under a
   plausible-looking answer. The lesson is not "gates are annoying".

## D-0088 — The same wrong-model config had silently mis-calibrated the tool-token budget
**Date:** 2026-08-31 · **Phase:** 2b/4 (sweep after D-0087) · **Status:** Active · **Severity:** High

### What this is
D-0087 closed with a routine task: sweep the repo for any *remaining* claim that
`/tmp/qwen3_tokcfg.json` describes the shipped model. The sweep was expected to
find stale prose. It found a **live defect** instead, in a module D-0087 never
touched.

### The finding
`src/tools/selector.py` budgets how many tool schemas fit in a 16K window. Its
constants were labelled *"MEASURED with the real Qwen3 tokenizer"*:

    returns_risk 2079, valuation 2400, technicals 1458,
    fixed_income 1370, derivatives 1921, ALL 8920

Those numbers were measured honestly, reproducibly, and against
**`Qwen3-4B-Instruct-2507`** — the same wrong model D-0087 identified.
`/tmp/qwen3_tokenizer.json` has a 151,643-entry vocab; the shipped
`Qwen/Qwen3.5-4B` has 248,044. Two test suites read those files.

**This was not merely a stale comment.** MEASURED 2026-08-31 against the shipped
tokenizer, `select_tools()`'s `estimated_tokens` **UNDER-PREDICTED the actual
rendered cost in 15 of 15 held-out cases**, worst ratio **1.067**. An
under-predicting budget is worse than no budget: it authorises a prompt that then
overflows the window and silently truncates the retrieved documents Phase 3
depends on.

### Why nothing caught it
`tests/test_selector.py` already held the right assertion — *"estimate never
under-predicts actual"* — comparing the estimate against a **rendered** cost. It
was green for three weeks. It rendered with `/tmp/qwen3_tokcfg.json` and
tokenized with `/tmp/qwen3_tokenizer.json`: it compared an estimate calibrated on
the wrong model against an actual measured with **the same wrong model**.

> **Two wrongs agreeing is not a verification.** A guard is only as good as the
> evidence it points at, and a guard that supplies its own reference can agree
> with itself indefinitely.

This is the D-0087 lesson repeating in a second place, which is why the sweep was
worth running rather than declaring the correction complete.

### MEASURED, both tokenizers, same method
| Quantity | Qwen3-4B-Instruct-2507 (recorded) | Qwen3.5-4B (shipped) |
|---|---|---|
| tool block, 84 schemas | 8,920 tok (54.4% of 16K) | **9,122 tok (55.7%)** |
| mean per tool | 106.2 | **108.6** |
| returns_risk (21 tools) | 2,079 | **2,219** |
| valuation (26) | 2,400 | **2,546** |
| technicals (13) | 1,458 | **1,590** |
| fixed_income (11) | 1,370 | **1,501** |
| derivatives (13) | 1,921 | **2,054** |
| held-out under-predictions | 0 of 15 | **15 of 15** (worst 1.067) |

The method reproduces the recorded OLD column **exactly**, which is what makes
the NEW column comparable rather than a different measurement.

### Why the cost rose — MEASURED, not assumed
It is **not** vocabulary drift, which was the obvious guess:

- raw JSON of all 84 schemas: **8,961** tokens old vs **8,959** new — identical.
- the three costliest schema bodies (`binomial_price` 164, `black_scholes` 163,
  `contract_payoff` 150) tokenize to the **same** counts under both.
- wrapper + one tool over bare: **145** tokens old, **266** new.
- chat template: **2,630** chars old, **7,756** new.

The entire +202 is Qwen3.5's **longer tool-calling preamble in the template**.
That is why every family rose by a near-constant ~130–146 tokens regardless of
how many tools it holds, and why the per-tool mean barely moved. Recording the
mechanism matters: a future tool addition changes the per-tool part, a future
template change changes the constant part, and they need different responses.

### A second silent-skip, found by testing the fix
While verifying that the corrected suites SKIP rather than silently pass when the
shipped files are absent, I hid the *old* files and re-ran everything. MEASURED:
`test_phase4_harness.py` printed **709 passed, 0 failed** instead of 711 — two
assertions gone, **no skip line, and the runner still reporting `SKIPPED: 0`**.
Cause: `if os.path.exists(_tokcfg):` with no `else`, plus a bare
`except ImportError: pass`. Both now announce themselves. This is D-0062's class
for the third time; the pattern is always *a conditional block whose absence is
indistinguishable from success*.

### The `2,552` figure: stale for TWO independent reasons
D-0026 recorded *"mean subset 2,552 tokens (15.6% of 16K), worst 4,479"*. None of
four plausible bases reproduced it with today's code, so rather than quietly
replace it I checked out the D-0026-era selector (`20f124a`) and ran it with its
own constants: **mean 2,552.3, 15.6%, worst 4,479** — exact, over all 21 eval
rows. So the figure was *correct when recorded* and is now stale because **(a)**
the constants came from the wrong model's tokenizer and **(b)** the router's
keyword lists grew when R18 was closed (`1bd2ff3`), so it selects more families
per query. Today's equivalent, MEASURED: **3,114 tokens (19.0%)**.

Attributing the whole drift to the tokenizer would have been a plausible,
tidy, and **wrong** explanation.

### The fix
1. `MEASURED_FAMILY_TOKENS` / `MEASURED_ALL_TOKENS` corrected to the shipped
   model's measured values, each annotated with its previous value and tool count.
2. `test_selector.py` and `test_tools.py` now read `/tmp/q35_tok.json` +
   `/tmp/q35_tokcfg.json`. **The old files are deliberately NOT a fallback** — a
   fallback would restore exactly the silent pass this defect came from.
3. Two new assertions: the worst-case actual/estimate **margin** is reported
   (a count of under-predictions cannot show a budget drifting toward the line),
   and `MEASURED_ALL_TOKENS` must **equal the freshly rendered cost** — that one
   fails by 202 under the old constant.
4. `test_tools.py`'s *"generation prompt appended"* assertion corrected: the old
   template ended `<|im_start|>assistant\n`, the shipped one ends
   `<|im_start|>assistant\n<think>\n`. Repointing the path without re-checking the
   expectation would have flipped this from true to false — and "fixing" it by
   loosening it would have erased the very fact that explains D-0085.
5. Explicit `SKIP` lines naming how many assertions did not run, in three places.
6. Mutation anchors updated (`2079`→`2219`, `8920`→`9122`) — the old anchors no
   longer matched any line, and **a mutant that cannot be applied is reported as
   killed**. Plus a new mutant, *"budget reverted to the wrong model's
   calibration"*, that reproduces this exact historical defect.

### Verification
- **Revert test:** restoring the six old constants fails **4 assertions**,
  including the under-prediction guard that was green for three weeks. Source
  restored to md5 `35705e179916f3234665f039c655908a`.
- **Mutation battery:** 21 seeded, **21 killed, 0 survived**, `source restored
  intact: True` — including the new revert mutant.
- **Pre-flight anchor check:** all 21 anchors unique and non-no-op before running
  (the D-0087 no-op-mutant lesson, applied as a standing pre-flight).
- **Full regression: 3,337 assertions, 0 failed, 0 skipped** — baseline 3,334 + 3
  new, fully accounted for. Skip behaviour verified in **both** directions.

### Standing lessons
1. **A guard must point at evidence it did not supply.** Estimate-vs-actual is
   worthless when both sides read the same wrong reference.
2. **Correcting the instance is not correcting the class.** D-0087 fixed the
   token ids; the same file had mis-calibrated a completely different subsystem.
   *Always sweep for the class.*
3. **When a recorded number no longer reproduces, find out why before replacing
   it.** Here it had two causes, and the plausible single-cause story was wrong.
4. **Re-pointing a test at new evidence requires re-checking its expectation**,
   not just its path.
5. **A conditional test block with no `else` is a silent skip.** Third occurrence.
6. **Mutation anchors are code that rots.** Correcting a constant silently
   disarms every mutant that quoted it.

**Trade-off:** the tool budget is now ~2 % more conservative, costing a little
context that was never really free.
**Reversal:** re-measure against whatever model actually ships and update both
the constants and the two `/tmp/q35_*` paths together.

## D-0089

**Date:** 2026-08-31
**Status:** ACCEPTED
**Context:** Request 51, option A. The forced-closed-`<think>` prefill was run on
the user's i5-12400 against `C:\models\Qwen3.5-4B-Q5_K_M.gguf`, after D-0087
removed the hardcoded token ids that had made the previous attempt refuse.

### THE TECHNIQUE WORKS. MEASURED.

The tokenization gate PASSED and reported what it discovered rather than what it
expected:

    prefill tok: OK -- '<think>'=248068, '</think>'=248069, both round-tripped;
                 prefill ids=[248068, 271, 248069, 271]

Those are the ids D-0087 predicted from the shipped model's own
`tokenizer.json`, and they are the same four ids the previous run was REFUSED
for producing. The gate's logic was always right; only its constant was
borrowed. That is now settled by an independent path: the constant is gone and
the run passed.

All three cases that had NEVER produced a visible answer -- at 512, 2048 or 3072
tokens, across two sessions -- answered at 512:

| case | tokens | seconds | chars |
|---|---|---|---|
| RAG-EN-005 | 56 | 25.1 | 177 |
| RAG-FA-002 | 108 | 31.0 | 281 |
| RAG-ABST-002 | 57 | 20.6 | 228 |

`re-opened think: 0 of 3`. `budget-bound: 0 of 3`. The replies used 14 % of the
budget they were given. D-0085's diagnosis -- that the harness's
`chatml_prompt()` omitted the `<think>\n` the shipped template appends, leaving
the model free to open a block it never closed -- is confirmed by its cure.

### WHAT THE RUN COST, AND WHAT THAT DOES TO ITEM 7

The affine model `seconds = 34.1 + n_tokens/4.47` was fitted to runs in which
every generation spent its ENTIRE budget inside an unterminated `<think>` block.
`n_tokens` there means *the budget*, because the budget was always consumed.
With the prefill, replies FINISH, so `n_tokens` becomes the answer's length and
the old formula stops describing the run. MEASURED: it over-predicts this run by
**5.81x** (148.6 s predicted per generation, 25.6 s actual).

Re-fitted to the three prefill points: `seconds = 14.0 + n_tokens/6.37`
(residuals +2.3 / 0.0 / -2.4 s). THREE POINTS, with the slope carried by a
51-token spread -- the intercept is the trustworthy part.

Item 7 re-priced, ESTIMATED from that MEASURED fit, 52 cases:

| basis | per generation | 52 cases |
|---|---|---|
| OLD: 3072 budget, budget spent | 721.3 s | **10.42 h** (the recorded price) |
| OLD: 2048 budget, budget spent | 492.3 s | 7.11 h |
| NEW: prefill, MEASURED mean | 25.6 s | **0.37 h** |
| NEW: prefill, worst of the three x1.19 slow-arm spread | -- | **0.53 h** |

**About 22 to 32 minutes, against 10.4 hours: a ~28x reduction.** The old
figures reproduce exactly from the recorded constants (10.42 / 7.11), so the
comparison is arithmetic, not rhetoric.

ASSUMPTIONS, stated so they can be falsified: that the other 49 cases answer as
briefly as these 3 (NOT MEASURED -- these are short numeric RAG answers; the
tools arm emits JSON and the plain arm emits prose); that no case re-opens a
think block (MEASURED 0 of 3, i.e. on 3 of 52); that 52 is still the right case
count. Any of these being false moves the estimate UP.

### AND NOW THE PART THAT MATTERS MORE THAN THE SUCCESS

I graded the three replies with the project's own `grade_rag_case`. The tally
was `MODEL_FAILURE: 2, OK: 1`. Both failures are the GRADER's, not the model's.

**DEFECT 1 -- the RAG prompt withholds the units, then the grader demands them.**

RAG-EN-005 answered `total net sales in fiscal 2022 were **394,328**`, citing
evidence [1]. 394,328 is the gold figure to the digit, from the right document,
with the right year distinguished from the 2023 passage sitting beside it in the
same prompt. `value_ok` came back **False**.

Cause, MEASURED. The gold magnitude is `394328000000.0` -- the filing states
millions. `grade_rag_case` calls `value_matches(..., scaled=True)`, which needs
a scale WORD next to the number to reach 3.94e11. The corpus fixture carries
`units_note='million'` on the passage. But `build_rag_prompt()` renders only
`provenance.citation()` and `passage.text`, and `citation()` emits source,
accession, date and URL -- **never the units**. MEASURED: the rendered prompt
for RAG-EN-005 contains no scale word at all (`'million' in prompt -> False`),
and this holds for **7 of 7** answerable RAG rows.

So the harness asks a question whose evidence declares no units, forbids the
model to use anything it remembers, and then fails it for not writing a word
that appears nowhere in its input. MEASURED: the same reply with
`million` inserted grades `value_ok=True`. The model was penalised for the
harness's omission.

This also explains a recorded result that has stood since the first run. In
`evidence/phase4_merged.json`, the ONLY answerable RAG case graded OK is
RAG-EN-004 -- the CPI index value, `gold_magnitude=308.417`, the one answerable
row whose gold figure needs **no** scale word. Every row that needed one failed.
That signature was visible in the evidence for two weeks and read as a model
weakness.

RAG-EN-002 and RAG-FA-001 produced non-empty output and were graded
MODEL_FAILURE. RAG-FA-001 said `درآمد خالص کل اپل ... برابر با ۳۸۳،۲۸۵ بوده است`
-- the correct figure, in Persian, from the Persian passage. Graded a failure.

**DEFECT 2 -- the Persian arm's own comma is in neither separator table.**

RAG-FA-001's figure did not merely fail the scale test; it parsed as
`[2023.0, 383.0, 285.0]`. The number never survived extraction.

Cause, MEASURED. `_THOUSANDS_SEPARATORS` contains `U+066C` ARABIC THOUSANDS
SEPARATOR, which is what the CORPUS FIXTURE uses (`۳۸۳٬۲۸۵`). The MODEL writes
`U+060C` ARABIC COMMA (`۳۸۳،۲۸۵`). `U+060C` is in neither
`_THOUSANDS_SEPARATORS` nor `_DECIMAL_SEPARATORS`, so it is left in place, the
regex `[-+]?\d+(?:\.\d+)?` stops at it, and one number becomes two:

    extract_magnitudes('۳۸۳٬۲۸۵ میلیون')  -> [383285000000.0]   U+066C, fixture
    extract_magnitudes('۳۸۳،۲۸۵ میلیون')  -> [383.0, 285000000.0]  U+060C, model

The 285000000.0 is worse than the split: the scale word attached to the SECOND
fragment. A wrong magnitude was manufactured, not just lost.

`src/rag/citations.extract_numbers` has the same blind spot
(`U+060C -> [383.0, 285.0]`). And the suite already KNOWS this character:
`test_phase4_harness.py:3506` says *"U+060C is the comma the Persian arm
actually emits"* -- for `mask_years`. The knowledge existed in one function and
never reached the numeric path.

### WHY NEITHER DEFECT WAS CAUGHT

Both hide in the same place: **the fixtures and the graders were written by the
same hand on the same day, so they agree with each other rather than with the
model.** Every test of `extract_magnitudes` feeds it `U+066C`, because that is
what the fixture author typed. Every test of `value_matches(scaled=True)` feeds
it a string containing `million`, because the test author knew the rule. No test
ever fed either function a string produced by the model.

This is D-0088's lesson recurring in a new subsystem, and it is now the second
time: *two artefacts that agree with each other are not a verification.* There
the estimate and the "actual" were computed from the same wrong tokenizer; here
the fixture and the grader share an author's assumptions. The class of defect is
"both sides of the comparison come from the same source", and R41 was written
for exactly this and did not prevent it, because R41 was scoped to token
budgets.

### WHAT WAS AND WAS NOT DONE

NOTHING was fixed in this entry. Both defects are RECORDED, MEASURED and
reproducible, and the fix is a separate, approved step -- because fixing a
grader changes what "37 graded cases" and "verdict FAIL" (D-0081) mean, and that
is a decision, not a repair. `phase_4/measurements_recorded` remains `None`. No
threshold was evaluated. The three replies were graded by ME, mechanically, as
diagnosis; that is NOT the human grading of task 5.

The user's full reply texts are LOST beyond 200 characters: the diagnostic
prints `text.strip()[:200]` and the run did not pass `--out`. RAG-EN-005 (177
chars) was complete; RAG-FA-002 (281) and RAG-ABST-002 (228) were
CONSOLE-truncated, so their grades are PROVISIONAL. That is a fourth reason to
re-run rather than mine this output further, and `--out` must be used next time.

**Decision:** record the prefill as MEASURED-EFFECTIVE; re-price item 7 from
~10.4 h to ~22-32 min ESTIMATED; freeze both grader defects as blocking findings
that must be fixed BEFORE any re-run, since a re-run graded by the current
grader would reproduce the same false failures at 52-case scale.

**Trade-off:** the re-run is now cheap enough to be routine, which is precisely
when an unfixed grader does the most damage.
**Reversal:** if the other 49 cases turn out to deliberate at length, the cost
estimate reverts toward the old one; the two defects stand regardless.


## D-0090 — both grader defects fixed, and the blind spot was wider than D-0089 recorded

**Date:** 2026-08-31
**Requested by:** the user, choosing option «الف» — fix the grader first, at zero run cost.
**Status:** DONE. No model was run. `phase_4/measurements_recorded` is still `None`.

### What was asked

Option A, verbatim as the user approved it:

> «**الف) اول نمره‌دهنده را تعمیر کنیم** (۰ هزینهٔ اجرا) — واحد را به پرامپت اضافه کنیم و U+060C را به جدول جداکننده‌ها. بعد قلم ۷ با ~۲۲–۳۲ دقیقه.»

### The blind spot was in FIVE layers, not the two D-0089 named

D-0089b recorded two affected modules. Before editing anything I fed the same
two strings — the fixture's U+066C form and the model's U+060C form — to every
module in the repo that parses a number. MEASURED, before the fix:

| layer | U+066C (fixture) | U+060C (model) |
|---|---|---|
| `scripts/phase4_lib` `extract_magnitudes` | `[383285000000.0]` | `[383.0, 285000000.0]` |
| `src/rag/citations` `extract_numbers` | `[383285000000.0]` | `[383.0, 285000000.0]` |
| `src/rag/normalize` `tokenize` | `['383285']` | `['383', '،', '285']` |
| `src/rag/ingest` `_NUMBER_RE` | `['۳۸۳٬۲۸۵']` | `['۳۸۳', '۲۸۵']` |
| `src/calc/persian_num` `parse_number` | `383285.0` | **raises** `ValueError` |

Two of these were not in D-0089's account. The retrieval layer is the more
interesting one: a Persian figure written the way the model writes it was
INDEXED as two unrelated numbers plus a punctuation token, so a query for that
figure could not retrieve the passage stating it. That is a silent retrieval
failure sitting underneath the grading failure.

`src/calc/persian_num` was left alone deliberately: it REFUSES the ambiguous
input rather than guessing, which is the correct behaviour for a calculator and
the convention `phase4_lib`'s own comment cites.

### The fix is not symmetric across layers, and that is deliberate

U+066C exists only as a digit-grouping mark. **U+060C is also ordinary Persian
sentence punctuation.** So it was admitted only where a between-digits guard
already exists:

- `phase4_lib._THOUSANDS_SEPARATORS` — the strip rule is
  `(?<=\d)SEP(?=\d\d\d(?!\d))`, so punctuation is untouched.
- `rag.normalize.tokenize` — guarded `(?<=\d)[,\u060c](?=\d)`.
- `rag.citations._NUM_RE` — the class sits in the repeated tail after a
  required leading `\d`, so it can only match between digits by construction.
- `rag.normalize._FOLD` — **deliberately NOT changed**, and a comment now says
  why: `_FOLD` is applied character-by-character with no lookaround, so an
  entry there would delete the punctuation case too and fuse Persian sentences.

MEASURED after the fix — the punctuation cases are unharmed:

```
'در سال 1402، درآمد 500 بود' -> [1402.0, 500.0]   (space after comma)
'درآمد، سود، و زیان'          -> []                (no digits)
'1402،15'                    -> [1402.0, 15.0]    (not three digits)
'۳۸۳،۲۸۵ میلیون'             -> [383285000000.0]  FIXED
'۳۸۳٬۲۸۵ میلیون'             -> [383285000000.0]  unchanged
'17٫85'                      -> [17.85]           decimal intact
```

### R45 (NEW, LOW) — the residual ambiguity, recorded rather than hidden

`"5،200"` — two numbers listed with no space after the comma — now reads as
`5200`. This is genuinely ambiguous in Persian and nothing in the text resolves
it. It is recorded, not concealed. MEASURED bound on its reach: the pattern
`digit U+060C exactly-three-digits` occurs **3 times** in
`evidence/phase4_merged.json`, and all 3 are the SAME model reply, in which the
character IS a thousands separator. On every occurrence in recorded data the
change is a fix and never a corruption.

Also MEASURED: of 264 U+060C characters in that file, **248 are in model
`output`/`raw_output` fields** and 16 in fixture fields. The character is a
model habit, which is precisely why fixtures never exercised it (R43).

### Defect 1 was fixed in the PROMPT, and value_matches was left alone

`build_rag_prompt` now renders `[figures in <units_note>]` alongside the
citation. MEASURED: answerable rows whose prompt names a scale word went from
**0 of 7** to **6 of 6 that have units**. The seventh, `RAG-EN-004`, is the CPI
index; its passage declares `units_note=None` and its prompt correctly still
states no unit — asserted, so the fix cannot later be "improved" into inventing
one. Empty/whitespace `units_note` is treated as absent for the same reason.

A second change was necessary and is easy to miss: stating the unit in the
evidence is **not sufficient**, because `grade_rag_case` reads the scale word
out of the MODEL'S text. `SYSTEM_RAG` now says: *"When a passage declares the
unit its figures are in, state that unit with any figure you quote from it."*
That is an instruction to REPEAT a declared unit, never to supply a missing one.

**`value_matches` was NOT loosened, and that is the point.** A reply quoting a
figure in millions while stating no unit genuinely is not a match for an
absolute magnitude — the grader was never wrong about that. What was wrong was
demanding a unit the harness had withheld. Softening the comparison would have
turned every 10^6 error into a pass, which is the exact failure
`src/rag/citations` exists to prevent.

### THE D-0081 CONSEQUENCE: MEASURED, AND SMALLER THAN I WARNED

I told the user option A would change what D-0081's human **FAIL** verdict
means. Having measured it, I must correct myself: **it does not overturn it.**

Re-graded all 10 recorded rag rows under the fixed grader: **0 of 10 flipped.**
The reason is structural, not luck:

- Defect 2 (U+060C) is a **grader** fix — it changes how a recorded reply is
  READ, so it *can* flip a recorded row. MEASURED, it did change RAG-FA-001:
  `[2023.0, 383.0, 285.0]` → `[2023.0, 383285.0]`. The manufactured
  285,000,000 is **gone**. The verdict did not flip because the reply still
  states no unit.
- Defect 1 (missing units) is a **prompt** fix. It changes what the model is
  TOLD, not how its old words are read. By construction it cannot change a
  recorded result — only a re-run.

So the failure MODE changed while the verdict did not. **D-0081's FAIL stands
as recorded, and the user does not have to decide whether to re-open it.** What
the fix changes is what a FUTURE run would measure, which is exactly why item 7
was blocked behind it (R44).

Also MEASURED, and worth stating: only **1 of 10** recorded replies stated a
unit at all — consistent with a prompt that never supplied one.

### The mutation battery was updated, because the fix moved its anchor

`tests/mutate_phase4.py` pinned `_THOUSANDS_SEPARATORS` by exact string. Adding
U+060C would have made that mutant stop APPLYING — reported as skipped, not as
killed. A mutant that silently fails to apply is worse than a deleted one,
because the count still looks healthy. The anchor was retargeted and a NEW
mutant added that restores the pre-fix table, reproducing D-0089b exactly.

Result: **220 killed, 0 survived, 9 skipped.** All 9 skips were verified to
PRE-DATE this change by counting each mutant's anchor in the pre-edit file and
the current file: 51 anchors are 1→1, and every skipped one is 2→2 or 0→0.
**0 skips are mine.** The 9 pre-existing skips are a separate, inherited
problem and are not claimed as fixed here.

### A wrong path of my own, caught by an implausible result

My first re-grade printed `recorded value_ok=None` for all ten rows. That is
not what the file says — `value_ok` is a TOP-LEVEL field on each row, and I had
read `row["grade"]["value_ok"]`, a key that does not exist. A uniform `None`
across ten rows was too tidy to be real. Corrected and re-run before reporting.

### Verification

- Full regression: **3,365 assertions, 18 suites, 0 failed, 0 skipped**
  (was 3,347; +18, all in the D-0089 block, 721 → 739).
- All **5** pinned-defect assertions inverted in the same commit as the fix.
  `INVERT WHEN FIXED` markers remaining: **0**. `DEFECT PINNED` remaining: **0**.
  A pinned-defect assertion that outlives its defect is a test that forbids the fix.
- 13 new assertions cover the punctuation cases, the non-invention of units,
  the CPI exception, and the three extra layers.

---

## D-0091 — the cure for D-0085 was written, tested, and connected to nothing

**Date:** 2026-09-01
**Requested by:** the user, choosing option «الف» — wire the prefill into
`run_phase4.py` before running item 7, at zero run cost.
**Status:** DONE. No model was run. `phase_4/measurements_recorded` is still `None`.

### What was asked

Option A, verbatim as the user approved it:

> «**الف) اول `run_phase4.py` را به prefill وصل کنیم** (۰ هزینهٔ اجرا، ~۱۵ دقیقه
> کارِ من) — سه بازو به `chatml_prompt_no_think` منتقل شوند، بودجه به ۵۱۲ برود،
> `--out` اجباری شود، گزاره‌ای اضافه شود که «مسیرِ تولید همان چیزی را می‌فرستد
> که تشخیص فرستاد»، و یک جهش که وصل‌نبودن را بکشد. بعد قلم ۷.»

### Why this was needed: the finding that stopped item 7

The user had already approved running item 7 (D-0082/D-0083, the full chunked
re-run). Before handing over the command I checked whether the script item 7
actually runs uses the forced-closed-`<think>` prefill that D-0085's diagnostic
proved was the cure. MEASURED 2026-09-01, by rendering all three arms:

```
plain prompt ends: '<|im_start|>assistant\n'                        <- no prefill
rag   prompt ends: '<|im_start|>assistant\n'                        <- no prefill
diagnostic used  : '<|im_start|>assistant\n<think>\n\n</think>\n\n' <- prefill
```

`chatml_prompt_no_think()` was defined at `run_phase4.py:278`, was asserted by
the test suite, and was **called by nothing outside that suite**. The cure lived
only in `scripts/diagnose_forced_answer.py`.

So item 7, in that state, would have spent roughly 7 hours re-measuring the
ORIGINAL defect at 52-case scale — the budget was still 2048 precisely because
generations were burning it inside an unterminated `<think>` block — and would
have left D-0089a's units fix untested, because a model that emits no visible
answer has no opportunity to repeat the unit the prompt now supplies.

**This is R43 recurring in a third subsystem.** A test that exercises a function
nobody calls produces green that means nothing. The assertions were not wrong;
they were pointed at the wrong object. I should have caught this before pricing
item 7, and said so to the user rather than only fixing it.

### The fix

Three builders, one line each, switched from `chatml_prompt` to
`chatml_prompt_no_think`:

- `build_plain_prompt`
- `build_tools_prompt`
- `build_rag_prompt`

### The budget was sized for a defect that no longer occurs

`DEFAULT_MAX_TOKENS` 2048 → **512**.

The 2048 and 768 figures were chosen from runs where the generation burned its
ENTIRE budget inside an unterminated `<think>` block. In those runs the budget
was funding runaway reasoning; with the prefill on the wire it funds the ANSWER.
MEASURED — the only three prefilled generations that exist, on the user's
i5-12400, 2026-08-31:

| tokens | seconds |
|---|---|
| 56 | 25.1 |
| 108 | 31.0 |
| 57 | 20.6 |

Longest 108 tokens; **0 of 3 were budget-bound**; 512 leaves **4.7×** headroom
over the longest. 512 is also exactly the runner's own low-budget warning
threshold (`if a.max_tokens < 512`), so it sits AT the threshold, not below it.

**NOT CLAIMED:** 3 cases is not 52. Neither the tools arm (which must emit a
`<tool_call>` JSON envelope, necessarily longer than a one-sentence answer) nor
the plain arm has ever been measured with a prefill. If the real run reports
`answers LOST to truncation > 0`, the budget is the first thing to raise — the
harness prints that counter unconditionally, which is why it can be trusted to
say so.

### The assertions now test the PRODUCTION path, not the helper

The pre-existing prefill assertions checked `chatml_prompt_no_think()` directly.
That function was never wrong, so those assertions could never fail. The new
block asserts on what `build_plain_prompt` / `build_tools_prompt` /
`build_rag_prompt` return, and adds:

- a property test that each arm's prompt equals `chatml_prompt_no_think` of its
  own content — so an inline re-implementation of the prefill is also caught;
- an assertion that the assistant header is followed by the prefill and
  **nothing else**;
- a **negative control**: the un-prefilled rendering must still be reachable and
  still be different. Without it the fix would stop being falsifiable, and the
  recorded pre-prefill runs would stop being comparable to anything.

### Eight pre-existing assertions were updated, not silenced

Each encoded a fact that was TRUE for a no-prefill harness: the budget had to be
large, and the prompt had to END at the assistant header. Each was re-pointed at
the new fact **with the old measurement kept in the assertion message**, because
that measurement is why the old value was chosen and is the evidence that would
justify reverting. The diagnostic's own default stays high (3072) and is now
asserted separately from the runner's, because the diagnostic exists to probe
reasoning and the runner exists to collect answers.

### Three mutants were silently skipped by my own edit

After adding four new prefill mutants the battery reported 221 killed / 0
survived / **12** skipped, where the standing figure was 9. Anchor-count diffing
against the pre-edit file proved **3 of the extra skips were mine**: they
anchored on the literal `DEFAULT_MAX_TOKENS = 2048`, which no longer exists.

**A mutant that silently fails to apply is worse than a deleted one, because the
killed count still looks healthy.** Retargeted to `512` (and the 768 one
repurposed to drop the budget below the longest measured prefilled answer); the
battery returned to **224 killed / 0 survived / 9 skipped**, the 9 being the
pre-existing inherited ones.

### The four new mutants

Each unwires one arm or reverts the budget. All four are **killed**:

- the plain arm stops sending the pre-closed think block
- the tools arm stops sending the pre-closed think block
- the rag arm stops sending the pre-closed think block
- the completion budget returns to the runaway-think 2048

### Dry run of the exact item-7 path

The standing constraint is that the user must never be the first to execute a
code path. `llama-cpp-python` is not installed in the sandbox, and `main()`
returns exit code 2 on that ImportError before any arm runs — so a dry run that
merely called `main()` would have proved only that the import fails. A
llama-cpp-shaped module was inserted into `sys.modules` instead, letting the
REAL `main()` walk its real path. MEASURED:

```
argv: --model <stub>.gguf --out <tmp>/phase4_run.json --arms plain,tools,rag
exit code: 0
generation calls total          : 54
latency-probe calls (raw text)  : 2   (TTFT probe at max_tokens=1, decode at 128)
ChatML arm prompts              : 52  (21 plain + 21 tools + 10 rag, VERIFIED)
...of those, ending in prefill  : 52
max_tokens values sent          : [1, 128, 512]
payload model.max_tokens        : 512
arms present                    : ['plain', 'rag', 'tools']  rows 21/10/21
every row carries output + metrics.raw_output : True
human_grading.status            : 'PENDING'
DRY RUN VERDICT: PASS (9/9 checks)
```

The prompt-recording check is the one that matters, and it is deliberately
different in kind from the test-suite assertions: the suite checks what the
BUILDERS return, which is static; this checks what the model wrapper **actually
sent at runtime**. D-0091 happened because a static check passed while nothing
on the wire carried the prefill.

This dry run proves the PATH runs. It measures **nothing** about the real model:
the replies are scripted, so the five FAIL verdicts it printed are artefacts of
the stub and are not recorded anywhere.

### Item 7 is re-priced, and the old range was the optimistic end

The previously quoted «~۲۲–۳۲ دقیقه» was ESTIMATED before the prefill existed.
Rebuilt from the three measured prefilled generations plus the MEASURED 49 s
TTFT probe:

| scenario | ESTIMATED |
|---|---|
| replies as short as the shortest measured (56 tok) | ~19 min |
| replies at the measured mean (73.7 tok, 25.6 s/call) | ~24 min |
| **every reply burns the full 512 budget** | **~83 min** |

So ~22–32 minutes was not wrong, but it was the optimistic end of the range with
no ceiling attached. The number to plan around is the upper bound. Stating only
the central figure is how a "1 hour" run became 1.7 hours earlier in this
project.

### Verification

- Full regression: **3,380 assertions across 18 suites, 0 failed, 0 skipped**
  (3,365 → 3,380, +15).
- `tests/test_phase4_harness.py`: 739 → **754** assertions.
- Mutation battery: **224 killed, 0 survived, 9 skipped** — all four new prefill
  mutants killed; the 9 skips proved pre-existing by anchor-count diffing.
- Dry run of the exact item-7 argv: **PASS, 9/9**.
- Gate re-proven unchanged: `phase_4` byte-identical apart from the recorded
  decision id, `measurements_recorded` still `None`, the 13 top-level
  `acceptance_thresholds` json-identical, `live_trading_enabled` `False`,
  `active_mode` `ANALYSIS_ONLY`.

### What this does NOT settle

Nothing about answer quality. D-0081's FAIL verdict still stands (D-0090
re-graded all ten recorded rag rows and **0 flipped**). The prefill fixed
*silence*, and the units fix removed one *manufactured magnitude*; whether the
model can actually answer these 52 cases is unmeasured until item 7 runs. Item 7
remains gated on the user's explicit go-ahead, which they have given, and the
command is now safe to hand over because the path has been walked.


## D-0092 — the citation grader was grading markers and Persian years as money

**Date:** 2026-09-05 · **Status:** FIXED, and the fix is deliberately partial
**Trigger:** the user's real 52-case item-7 run (2026-09-03), uploaded 2026-09-05

### What the numbers said, and what was actually true

The merged run reported, MEASURED:

    citation_correctness_pct    25.0
    unsupported_claim_rate_pct  75.0

Read at face value, that is a model that cannot ground a figure. It is not what
happened. **8 of the 12 graded claims were checked against a number that is not
a financial magnitude at all:**

| case | "claimed" value | what it really was |
|---|---|---|
| RAG-EN-001 | `2.0` (×3 passages) | the citation marker `[2]` |
| RAG-EN-005 | `1.0` (×3) | the marker `[1]` |
| RAG-ABST-001 | `2.0` (×3), `3.0` (×3) | markers `[2]`, `[3]` |
| RAG-ABST-003 | `1.0`, `1402.0` | marker `[1]`, the Jalali year ۱۴۰۲ |
| RAG-FA-001 | `2023.0` | the Gregorian year ۲۰۲۳ |
| RAG-FA-002 | `2023.0` | the year ۲۰۲۳ |

A representative detail, recorded verbatim in the evidence file:

    claimed 2 does not appear in the evidence; nearest is 1.69148e+11
    (ratio 1.1824e-11 -- a power-of-ten ratio means a scale error)

The grader compared the bracket `[2]` against a filing row of 169 billion and
called it a scale error. Meanwhile **the answers were correct**: RAG-EN-001 said
`$383,285 million`, RAG-FA-001 said `۳۸۳,۲۸۵ میلیون`, both right.

This matters beyond one metric. `verify_claim` **returns on the first number it
cannot locate**, and in a cited financial sentence the first number is almost
always a marker or a year — so one artefact decided the entire case.

### Two independent causes. Neither alone was sufficient.

1. **`src/rag/citations.py` performed no masking whatsoever.**
   `grep -n "mask_years|_YEAR_RE|<YEAR>" src/rag/citations.py` → **0 hits**,
   while `scripts/phase4_lib.mask_years` had existed for weeks and was already
   used by `split_claims`.

2. **The year pattern matched ASCII digits only.** MEASURED probe of the old
   `mask_years`:

   ```
   'total net sales in fiscal 2023 were 383,285 million'
       -> '... fiscal <YEAR> were ...'                    works
   'درآمد خالص کل اپل در سال مالی ۲۰۲۳ برابر با ۳۸۳,۲۸۵ میلیون'
       -> UNCHANGED                                       Persian year survives
   'در سال مالی ۱۴۰۲ برابر با ۳۸۳,۲۸۵ میلیون ریال'
       -> UNCHANGED
   'This figure is found in Evidence [2], which states ... | 383,285'
       -> UNCHANGED                                       marker survives
   ```

**This is R43 recurring for the FOURTH time**: a regex written against text the
fixture author typed, never against the text the model actually emits.
`extract_numbers` folds digits before matching; `mask_years` ran on unfolded
text. The two layers disagreed about what a digit is, and the disagreement was
silent.

### The fix, and where it had to live

`mask_non_quantities` now lives in **`src/rag/normalize.py`** and masks both
citation markers and year-like integers in **any** of the three digit scripts.
`phase4_lib.mask_years` delegates to it; `verify_claim` calls it on the claim.

**Why `normalize.py` and not `phase4_lib.py`:** `phase4_lib` imports *from*
`rag.ingest`, so `citations.py` cannot import `phase4_lib` without a cycle.
Copying the regex was the alternative and is exactly the mistake
`normalize.py`'s own docstring was written to prevent — two copies of a
normalization rule drift, and the drift is invisible. It landed in the one
module both sides already depend on.

**Why the claim side only.** `extract_numbers` also serves the **evidence**
side via `_evidence_magnitudes`. Evidence legitimately contains figures shaped
like years — a CPI index, a share count, a rial price — and masking those would
delete a magnitude the model is entitled to cite, turning a SUPPORTED claim
into a CONTRADICTED one. So the masking is applied by `verify_claim` to its
*claim* argument, and `extract_numbers` stays unmasked.

### A mistake I made, and how it was caught

My first year pattern wrote the **fixed** digits as ASCII literals
(`"20[d][d]"`) and only the varying tail as a multi-script class. `۲۰۲۳` still
went unmasked, because its `2` and `0` are U+06F2 and U+06F0. **The probe
reported the Persian cases coming back UNCHANGED — the fix fixed nothing.**
Every digit position had to be script-agnostic, not just the ones that vary.
`_dig()` exists for that, and a mutant now pins it.

### The risk of over-masking was MEASURED, not assumed

Masking can destroy a real measurement as easily as it can repair one.

- **Bracketed magnitudes.** Real filings write `[1,234]` as a table cell and
  `[500]` as an accounting negative. The marker pattern is bounded to **1–2
  digits**, so both are refused. MEASURED: across all 39 rows of
  `rag_corpus_v1` + `rag_gold_v1` + `bilingual_eval_v1`, bracketed runs of 1–2
  digits: **0**. Across the user's 52 real outputs: 6 contain one, and every one
  is a citation marker.
- **Year-shaped values.** I first assumed the window was 1000–2199. MEASURED it
  is **1200–1499 and 1800–2199**: 1000, 1100 and 1500–1799 are *not* masked.
  That matters because `EN-NUM-001` and `FA-NUM-001` both have
  `expected_value=1000.0` — outside the window, and additionally safe because
  `value_matches` never calls this function at all (`value_matches` call sites
  in `run_phase4.py`: **0**).

### MEASURED effect, model NOT re-run

Re-grading the ten recorded rag answers with the new grader, using the runner's
own `build_index` so the evidence is what the model actually saw:

| case | before | after |
|---|---|---|
| RAG-FA-001 | CONTRADICTED | **SUPPORTED** |
| RAG-FA-002 | CONTRADICTED | **SUPPORTED** |
| RAG-ABST-003 | CONTRADICTED | **SUPPORTED** |
| others | unchanged | unchanged |

`citation_correctness` over checked claims: **0.0 → 42.86**. Implausibly small
claimed values: **8 → 6**, and the 6 remaining are a different defect (below).

### WHAT THIS DOES NOT FIX, DELIBERATELY

Three claims remain CONTRADICTED, and **none is a marker or a year**. All three
are the model *quoting an evidence row verbatim*:

    'This figure is found in Evidence [2], which states:
     "[figures in million] Total net sales | 383,285".'

The scale word sits **before** the number, inside a bracketed section header,
and `_CLAIM_SCALE_RE` only inspects the tail *after* a number — so the quoted
row reads as a bare `383,285` against a million-scaled passage, i.e. the 10^6
error. Six residual small values also remain, all **date components**:
`June 30,` → 30, `July 27,` → 27, `(2023-11-03)` → −11 and −3.

**Not patched.** Widening the grader to accept a *leading* scale word would also
make it accept the real 10^6 error — the one thing this module exists to catch.
Over-fitting a grader to its own corpus is how a FAIL becomes a PASS, and this
project's central finding is a FAIL. Recorded as **R47** for the user's
decision, not repaired here.

### Assertions and mutants

27 new assertions (`test_phase4_harness` 754 → 781), including the
false-positive side at equal strength, and a **negative control**: a fabricated
`999,999 million` must still be CONTRADICTED, and the bare-figure 10^6 error
must still be caught. If either ever passes, the fix has become a whitewash and
every `citation_correctness` number after it is worthless.

`src/rag/normalize.py` became a mutation target (`NORM`), because the rule that
decides whether a Persian year is graded as an eleven-figure revenue now lives
outside both files the battery previously covered. Five mutants anchored on the
deleted `_YEAR_RE.sub` line were **retargeted** rather than left to skip: a
skipped mutant still leaves the killed count looking healthy, which is worse
than a deleted one — the same trap this battery hit on 2026-09-01.

### The anti-vacuity guard earned its place immediately

The four `verify_claim` assertions sit inside `if _ps is not None`. My fixture
passed `trust_level="A"`; `Provenance` enforces a closed vocabulary and refused
it. Without the guard assertion, those four would have silently vanished while
the suite stayed green — the same failure shape as a mutant whose anchor no
longer exists. The guard failed, loudly, and named the reason.


## D-0093 — the API path existed, and sent the prompt in a form no provider could use

**Date:** 2026-09-05 · **Status:** FIXED · **Trigger:** request 55(b),
«در تست های بعدی را با قابلیت استفاده از api قرار بده»

### What was already there, MEASURED before building anything

The user asked for API capability in subsequent tests. Rather than build, I
measured. Most of it existed:

- **14 providers** registered, three with a documented free tier: **groq,
  google (Gemini), cerebras**.
- Flags `--provider`, `--model-id`, `--base-url`, `--allow-paid`, `--timeout`.
- `RemoteRunner`, wearing `ModelRunner`'s interface and — importantly — sharing
  its **return contract** and the same `L.strip_thinking`, so a provider swap
  cannot change how anything is graded.
- Payload fields `MEASURED_REMOTE_API`, `http_attempts`, `remote_tokens_in/out`,
  `billable_run`, `local_endpoint`, `quota_recorded`.
- The spend gate works, which matters under the standing "spend nothing"
  constraint. MEASURED:

      groq / google / cerebras                    -> allowed, billable=False
      openai / anthropic / openrouter / custom     -> BLOCKED without --allow-paid

- `--provider local` is the default, permanently, per the user's own instruction.

So request 55(b) was roughly 70 % already implemented. Reporting that honestly
was worth more than adding a feature on top of an unexamined base.

### The defect that measuring found

`RemoteRunner` passed the whole rendered ChatML string to `clients.chat`, which
sent it as **one user message**. MEASURED payload:

    "messages": [{"role": "user",
                  "content": "<|im_start|>system\nYou are a bilingual..."}]

A remote provider applies its **own** chat template around that. Consequences,
none of which fail loudly:

1. The system instruction was not a system instruction — just body text.
2. The pre-closed `<think>` prefill — the D-0091 change that took silence from
   **20 of 52 answers to 0 of 52** — arrived as literal text and **did nothing**.
3. `seed` was never sent, so a remote arm could not be reproducible the way the
   local run is (`DEFAULT_SEED=20260831`).
4. `stop` was never sent.

A remote run in that state produces a full set of plausible answers and a
`MEASURED_REMOTE_API` label. It would have looked like a valid comparison
against the local numbers and been nothing of the kind.

### The fix, shaped by the user's constraint

The standing instruction on this subsystem is «مدل محلی حتماً باید باقی بماند و
فقط api به آن اضافه گردد» — the local model must remain; the API is only added.

So the three builders still return the **byte-identical** string the local path
has always consumed, as a `str` **subclass** (`Prompt`) that merely carries its
parts alongside. `Prompt` *is* the string: equal to it, hashing the same,
accepted anywhere a `str` is. The local path, `ModelRunner`, llama-cpp and the
recorded evidence are untouched. `Prompt.turns()` yields provider-neutral turns,
with the prefill as a **trailing assistant turn** — which on the OpenAI and
Anthropic dialects is a genuine prefill the model continues, i.e. the same
mechanism that fixed silence locally rather than a lookalike.

Per-dialect translation, each verified against a stubbed opener:

| dialect | system | prefill | seed | stop |
|---|---|---|---|---|
| openai | `system` message | trailing `assistant` | `seed` | `stop` |
| anthropic | **top-level** `system` | trailing `assistant` | **dropped** | `stop_sequences` |
| google | `systemInstruction` | role mapped to **`model`** | `generationConfig.seed` | `stopSequences` |

Anthropic has no seed parameter, so the seed is **dropped and recorded as
dropped** (`seed_supported_by_wire: false`). Sending it would be rejected;
pretending it applied would be worse. Google spells the assistant role
`model` and rejects an unrecognised role outright, so a prefill sent as
`assistant` would fail the whole run rather than degrade quietly.

New payload fields: `structured_calls`, `seed_sent`, `stop_sent`,
`seed_supported_by_wire`. Per row: `structured_turns`, `prefill_sent`.
**A remote run whose `structured_calls` is 0, or less than its case count, must
not be compared against the local numbers.** That is the whole point of
recording it.

### THE MUTATION BATTERY CAUGHT D-0091 REPEATING INSIDE THE FIX FOR D-0091

Five mutants **survived** the first version of my assertions:

    the remote path stops sending structured turns
    the remote path stops sending the local seed
    the remote path stops sending the local stop tokens
    the remote seed stops matching the local run's seed
    the structured-call counter stops counting, hiding a flat run

Every one mutates `RemoteRunner.generate`. My assertions drove `clients.chat`
**directly**, passing `turns`/`seed`/`stop` by hand — proving the three dialects
build correct payloads, and proving **nothing** about whether the runner ever
passes those arguments. `grep RemoteRunner tests/` returned two hits, **both
comments**.

That is exactly D-0091's shape: there, the prefill helper was asserted while
the production builders called something else; here, the transport was asserted
while the production call site was untested. **Twice now, the thing under test
has been the layer next to the one that was broken.** Ten assertions were added
against `RemoteRunner.generate` itself, using a stub installed as **both** a
`sys.modules` entry **and** an attribute on the `llm` package — because
`from llm import clients` resolves the package attribute, and a probe that
patched only `sys.modules` reached the real network and returned HTTP 403,
proving the stub inert.

### One mutant was DELETED rather than killed

`markers are masked AFTER years` survived. I probed the claim instead of
defending it: on `[2023]`, `[20]`, `in 2023 see [2]`,
`Evidence [2], states 383,285` and `مطابق [۲] در سال ۱۴۰۲`, both orders produce
**identical** output — the bracket guards stop the patterns overlapping. The
comment in `normalize.py` claiming the order was critical **was wrong** and has
been corrected. Writing an assertion to pin an ordering that does not matter
would have been a test authored to flatter the battery.

### Three more mutants had gone silently skipped

The skip count moved 9 → 12. The three per-arm prefill mutants were anchored on
each arm's own `chatml_prompt_no_think(...)` call; all three arms now route
through `_prompt()`, so those literals no longer exist. Retargeted onto
`_prompt` plus the per-arm dispatch, so unwiring **either** is still caught.
Final battery: **251 seeded, 242 killed, 0 survived, 9 skipped** (the 9 are
pre-existing), `source restored and oracle green: True`, md5s verified.

### An assertion of mine that tested nothing

I had written:

    RP.main.__doc__ is None or "--provider local" not in ""

`x not in ""` is true for every non-empty `x`, so the condition could never be
false. It read like a check and tested nothing — the failure mode this suite
exists to prevent. Replaced with a real one: `clients.chat` must **refuse** the
local provider, so the remote transport is unreachable unless a remote provider
is explicitly chosen.

### A regression scare that was NOT the code

The first full run after these changes reported `FAILURES PRESENT`, with
`test_selector.py` timing out at 300 s and the total *dropping* 3380 → 3343.
Diagnosis before conclusion: `grep -cE "normalize|citations|clients|phase4_lib|
run_phase4" tests/test_selector.py` → **0**. Run alone, it finished in **under
one second**: `104 passed, 0 failed`. The timeout was CPU contention with the
mutation battery I had left running, not a defect. A timed-out suite is still
correctly treated as a FAILURE by `run_all.sh`, because it proves nothing.

### R40 recurred, exactly as recorded

A sandbox reset wiped `/tmp`, taking the Qwen tokenizer files and the live XBRL
payload with it. The next run went green with `SKIPPED: 5` — and the suite's own
SKIP lines named what had silently stopped running. All four files were
re-fetched per the README prerequisites. Final state: **3450 assertions,
SKIPPED: 0, TIMED OUT: 0, ALL GREEN**. A green run with skips is not a green
run; this is the third time that has mattered.

### WHAT THIS DOES NOT SETTLE

1. **No remote run has been made.** Every assertion is against the transport
   with a stubbed opener. Nothing has touched a network, and no run starts
   without explicit approval.
2. **A remote model is not the local model.** The label stays
   `MEASURED_REMOTE_API` and `model_identity.sha256` is `None`, because a
   remote model id is not a pinned revision — the provider may change what it
   serves between two runs bearing the same id.
3. **An API run cannot repair the hardware FAILs.** 4.28–4.47 tok/s against a
   minimum of 8, and 48–50 s TTFT against a maximum of 3.0, are facts about the
   user's i5-12400. A remote arm answers a *different* question: what this
   class of model would say if hardware were not the bottleneck.
4. **No free-tier key has been validated.** `get_api_key` refused my
   16-character dummy as malformed, which is correct behaviour; whether the
   user's real key works can only be known by using it.
