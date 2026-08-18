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
