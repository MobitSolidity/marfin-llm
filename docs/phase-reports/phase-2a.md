# Phase 2a — Completing Section 5.3: Valuation, Technicals, Fixed Income, Derivatives

**Date:** 2026-08-10
**Trigger:** User instruction "build out R14" — close the open risk rather than
advance to Phase 3.
**Status:** PASS
**Gate:** Phase 3 still awaits explicit approval. No auto-advance.

---

## 1. What R14 was

Recorded at the end of Phase 2:

> R14 — Section 5.3 calculation coverage incomplete (OPEN)

Section 5.3 of the master prompt enumerates five families of deterministic
calculation. Phase 2 built one of them (returns/risk, 21 functions) and left
four unbuilt. Until they existed, the model had no verified way to answer a
valuation, charting, bond or options question, and would have had to reason
about the arithmetic in-context — which is precisely the fabrication surface
this architecture is designed to remove.

---

## 2. What was built

| Module | Functions | Family |
|---|---|---|
| `src/calc/valuation.py` | 26 | DCF, DDM, multiples, returns on capital, margins, leverage, working capital |
| `src/calc/technicals.py` | 13 | SMA/EMA/WMA, RSI, MACD, ROC, stochastic, ATR, Bollinger, ADX, Donchian, VWAP, OBV |
| `src/calc/fixed_income.py` | 11 | Cash-flow schedule, clean/dirty price, accrued, YTM, YTC, duration, convexity, DV01 |
| `src/calc/derivatives.py` | 13 | Black-Scholes, Black-76, binomial, implied vol, five Greeks, payoff, margin |

All four import `CalcResult` and the shared validators from the existing
`returns_risk.py`. Dependencies are one-way, no cycles, standard library only
(D-0019).

Registry: **21 → 84 tools**.

---

## 3. Verification

| Suite | Assertions |
|---|---|
| `test_returns_risk.py` | 57 |
| `test_valuation.py` | 78 |
| `test_technicals.py` | 81 |
| `test_fixed_income.py` | 69 |
| `test_derivatives.py` | 92 |
| `test_tools.py` | 99 |
| **Total** | **476** |

Mutation battery: **56 seeded defects, 56 killed, 0 survived, 0 skipped**, all
sources restored intact.

Every test uses one of four methods, and none re-runs the formula under test:

- **(A) closed form** — par bonds price exactly at par; zero-coupon Macaulay
  duration exactly equals maturity; zero-coupon convexity = n(n+1)/(f²(1+y/f)²)
- **(B) hand arithmetic / published reference** — RSI pinned to Wilder's own
  dataset (70.46413502109705)
- **(C) invariant / cross-model** — put-call parity; 2000-step binomial
  converging to Black-Scholes; Black-76 at the forward equalling Black-Scholes;
  analytic Greeks vs central finite differences
- **(D) must-raise** — silence on bad input counts as a defect

---

## 4. The three real defects mutation testing found

The suites passed 311/311 before the battery ran. That told me nothing. The
battery found three formulas that were **correct but unverified** — and all
three failed for the same reason:

> **Each test happened to use a value where the missing factor equals 1.**

| Mutation | Why it survived | How it was closed |
|---|---|---|
| `convexity`: drop `f²` | Every convexity test was *relative* (longer > shorter). A uniform scaling error preserves every ordering. | Absolute closed-form anchors at **two different frequencies** (99.9405 semiannual, 99.7732 annual). A wrong `f²` cannot satisfy both. |
| `delta`: drop `e^-qT` | Every delta test used `q=0`, where the factor is exactly 1. | Finite-difference check at `q=0.05` plus dividend-delta parity. |
| `vega`: `sqrt(T)` → `T` | Every vega test used `T=1.0`, where `sqrt(1)=1`. | FD checks at `T=4` (2× divergence up) and `T=0.25` (2× down). |

This is now a standing rule: **never verify a factor at the value where it
disappears, and never rely solely on relative comparisons for a quantity that
could be uniformly mis-scaled.**

---

## 5. A failing test that was itself wrong — and the real hazard behind it

`test_fixed_income.py` asserted that a bond priced at 1e9 was unsolvable. It
did not raise, so the test failed. Investigating rather than assuming showed
**the test was wrong**: 1e9 *is* mathematically solvable, at a yield of
−99.52%.

But the investigation surfaced a genuine hazard. A fat-fingered price produced
a confident, arithmetically correct, economically meaningless number — an input
error laundered into an authoritative-looking answer. Added
`MIN_PLAUSIBLE_YIELD = -0.50` and a plausibility gate on the solved root, plus
a second test proving the gate does **not** over-reach (a genuine −0.4%
sovereign yield still computes). See D-0022.

---

## 6. The measured finding that constrains Phase 3

Tokenized with **Qwen/Qwen3.5-4B's own tokenizer** against **its own chat
template** — i.e. the model this project actually runs.

> **⚠️ CORRECTED 2026-08-31 (D-0088).** This table originally read 34 / 8,954 /
> **8,920** / 54.4% / 106.2, labelled MEASURED against "the real Qwen3
> tokenizer". Those numbers were measured correctly against
> `Qwen3-4B-Instruct-2507`'s tokenizer, which D-0087 established is **not** the
> shipped model's. Both columns are shown below so the size of the error is
> visible rather than quietly overwritten. **The conclusion did not change** —
> more than half the window is still consumed before the user speaks, and tool
> subsetting is still mandatory.

| Quantity | Qwen3.5-4B (shipped) | was recorded | Label |
|---|---|---|---|
| Prompt without tools | 36 tokens | 34 | MEASURED |
| Prompt with 84 tools | 9,158 tokens | 8,954 | MEASURED |
| **Tool block cost** | **9,122 tokens** | 8,920 | **MEASURED** |
| Share of 16K context | **55.7%** | 54.4% | MEASURED |
| Mean per tool | 108.6 tokens | 106.2 | MEASURED |
| Costliest schema bodies | `binomial_price` 164, `black_scholes` 163, `contract_payoff` 150 | unchanged | MEASURED |

**Why the cost rose, MEASURED rather than assumed.** It is not vocabulary
drift. The raw JSON of all 84 schemas costs **8,961** tokens under the old
tokenizer and **8,959** under the shipped one — and the three costliest schema
bodies above tokenize to *identical* counts in both. The entire +202 difference
is Qwen3.5's **longer tool-calling preamble in the template itself** (2,630 →
7,756 template chars; wrapper + one tool costs 145 tokens over bare on the old
template, **266** on the new). That is why every family rose by a near-constant
~130–146 tokens regardless of how many tools it holds.

**More than half the context window is consumed before the user says
anything.** Phase 3 adds retrieved documents to that same window. All 84 tools
plus RAG context plus conversation history does not fit.

Consequence, recorded as **D-0023**: tool subsetting is now a *requirement* for
Phase 3, not an optimization. Two tests guard the number from both sides — it
must stay under 70% of context, and it is asserted to be *over* 25% so this
constraint cannot quietly stop mattering if descriptions are trimmed later.

---

## 7. Convention hazards handled explicitly

Each of these is a real analyst error that now produces a refusal, not a wrong
number:

- **PEG** expects percentage points, not fractions — a 100× error
- **Capex** arrives negative on cash-flow statements — a 2× error if signed
- **Volatility** as `25` rather than `0.25` — refused as implausible
- **Theta** disclosed as annual with `per_day` supplied separately — a 365× trap
- **Negative EPS** — P/E is undefined, not "cheap"
- **Terminal growth ≥ discount rate** — Gordon divides by ≤ 0
- **Zero interest expense** — coverage is undefined, not infinite
- **Inconsistent OHLC** (high < low) — refused before computing
- **Insufficient warm-up** — refused rather than silently shortened
- **Wilder vs EMA smoothing** — the classic RSI/ATR discrepancy (D-0021)

---

## 8. Tool-layer integrity

- **84 tools, zero execution capability.** Asserted against a forbidden list
  (`place_order`, `submit_order`, `buy`, `sell`, `execute_trade`,
  `cancel_order`, `broker_connect`, `enable_live_trading`) and a substring check
  for `order`/`trade`/`broker`/`execute`.
- **Type coercion hardened.** The new schemas introduced `integer` and
  `boolean`, which `_coerce` did not recognize — it would have passed them
  through **unvalidated**. A model emitting `period: 2.5` would have been
  silently truncated. Now refused as `invalid_argument`.
- **Persian numerals reach every family**, including inside array arguments and
  as integer arguments (`۱۵۰` / `۸٫۴۰` → 17.857).
- **`ESTIMATED` survives dispatch** for `margin_estimate` and
  `liquidation_estimate` (D-0024).
- **Every refusal carries guidance** telling the model not to substitute a
  value.

---

## 9. What is still NOT verified

Stated plainly, because the master prompt forbids presenting estimates as
measurements:

- **Persian generation quality** — untested; needs the user's machine (R10)
- **Decode throughput** — the 14.7 tok/s figure remains ESTIMATED, not MEASURED
- **Tool-calling accuracy by the model** — the *plumbing* is verified; whether
  Qwen3-4B *chooses* the right tool from 84 options is unmeasured, and D-0023
  makes it likely that subsetting will change the answer
- **Numerical behaviour at extremes** — very long-dated bonds, near-zero
  volatility, deep ITM American options are bounded by guards, not characterized

---

## 10. Risk register changes

- **R14 — Section 5.3 coverage incomplete → CLOSED.** All five families built,
  tested, mutation-verified, registered.
- **R13 — tests may not discriminate → MITIGATED (strengthened).** Battery grew
  13 → 56 defects across five modules and found three real gaps.
- **R16 — NEW (High):** tool-schema context cost is 54.4% of the 16K window;
  Phase 3 must implement subsetting (D-0023).
- **R17 — NEW (Medium):** tool-selection accuracy across 84 options is
  unmeasured and cannot be measured in this sandbox.

---

## 11. Verdict

**PASS.** R14 is closed. 63 new tools, 476 assertions, 56/56 mutants killed,
three real defects found and fixed, one measured constraint that changes the
Phase 3 design.

**Awaiting explicit approval before beginning Phase 3. No auto-advance.**
