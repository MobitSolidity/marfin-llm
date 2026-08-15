# Phase 3A — Market Data, TradingView, and Broker Design

**Status: COMPLETE — awaiting Phase 4 approval**
**Date: 2026-08-15**
**Label key: (V) VERIFIED · (M) MEASURED · (C) COMPUTED · (E) ESTIMATED · (U) UNKNOWN**

---

## 0. What this phase was, and what it deliberately was not

Phase 3A designs the surface where this project stops reasoning about text and
starts touching money and other people's licensed property. Every module in it
is mostly refusals, which is exactly the code a passing test suite is worst at
verifying: **a refusal that stops refusing looks like nothing at all.**

Nothing in this phase was executed against a live broker, a paid data feed, or a
real credential. That is not a gap to be closed later by trying harder — it is
the design. `live_trading_enabled` is `false`, `active_mode` is `ANALYSIS_ONLY`,
and no code path in the repository can change either.

---

## 1. The twelve tasks

| # | Task | Status | Where |
|---|------|--------|-------|
| 1 | Verify current TradingView terms and official documentation | DONE (V) | `docs/legal/market-data-providers.md`, `src/market/tradingview.py` |
| 2 | Identify available TradingView connector levels | DONE (V) | Levels 0–3 enumerated; **Level 0** is what this runtime has |
| 3 | Separate TradingView display data from licensed machine-use data | DONE (V) | `assert_display_only_use()`, `TradingViewLicenceError` |
| 4 | Select market-data providers | DONE (V) | Alpha Vantage free tier only (D-0040) |
| 5 | Select broker adapters | DONE (V) | Registry exists; **zero live-capable adapters** |
| 6 | Define paper/live separation | DONE (V) | `src/execution/mode.py`, 12 SS.6.1 prerequisites |
| 7 | Design CSV ingestion | DONE (V) | `src/market/csv_import.py`, 14 validated properties |
| 8 | Design screenshot integration | DONE (V) | `src/market/screenshot.py`, SS.7.1 Level 3 |
| 9 | Design webhook validation and queueing | DONE (V) | `src/market/webhooks.py` |
| 10 | Add broker read-only tools | DONE (V) | `src/execution/broker_tools.py` |
| 11 | Add order preview and risk tools | DONE (V) | `preview_order`, `pre_trade_risk_check`, `portfolio_risk` |
| 12 | Keep broker write actions disabled | DONE (V) | Asserted by 62 adversarial attempts, all refused |

---

## 2. The six acceptance criteria

### 2.1 No unsupported Desktop API claimed — **PASS (M)**

`CAPTURE_AVAILABLE = False`, `OCR_AVAILABLE = False`, and the claim is backed by
a 12-entry `CAPABILITY_PROBE` recording exactly what was looked for and not
found: `mss` ABSENT, `pyautogui` ABSENT, `pytesseract` ABSENT, `tesseract` NOT ON
PATH, `easyocr` ABSENT, `paddleocr` ABSENT, `DISPLAY` unset.

The probe asserts structurally that no capture or OCR backend is *imported*, so
that a future capability claim cannot be made without the import changing in the
same commit.

### 2.2 Data use is legally reviewed — **PASS (V)**

TradingView terms reviewed and encoded as enforceable data, not prose.
`TradingViewLicenceError` is deliberately a `RuntimeError` and **NOT** a
`MarketDataError`, so that a caller writing `except MarketDataError` to fall back
to another source cannot swallow the licence wall. There is no other source and
no fallback; callers must name it.

Alpha Vantage free tier selected per the user's instruction to spend nothing
(D-0040). Twelve Data closed by the same decision. Market data is **not
persistable** — the permitted storage timeframe is (U) and is recorded as
unknown rather than guessed.

### 2.3 Broker and market data are separated — **PASS (V)**

Enforced by an AST import check, not by convention: the execution layer may not
import the RAG document layer, and a mutation adding that import is killed.

### 2.4 Paper/live cannot be confused — **PASS (M)**

12 SS.6.1 prerequisites; **10 are unmet**, measured. `require("submit_live_order")`
refuses in every mode. This criterion has a history worth recording: `mode.py`
originally *stated in a docstring* that live trading could not be enabled even by
editing the config, and the first mutation run disproved it outright — a two-line
config file reached `require("submit_live_order")` successfully. The prose was
decoration. The replacement guard is verified by 53 mutations.

### 2.5 Webhooks cannot authorize trades — **PASS (M)**

75 mutations, 74 killed, 1 documented equivalent. A webhook is an untrusted
message; it cannot reach a write path.

### 2.6 Live submission remains disabled — **PASS (M)**

62 adversarial attempts to reach a broker write by any route — escalating a
preview with its own id, constructing a synthetic VERIFIED live-capable adapter,
editing immutable module tables at runtime — **62 refused, 0 allowed, 0 crashed.**

---

## 3. Verification totals

```
TOTAL: 2187 assertions passed across 15 suites
692 mutations across 10 batteries — 0 survived, 0 skipped
2 adversarial probes — 153 attempts, 153 refused, 0 ALLOWED, 0 CRASHED
```

| Battery | Seeded | Killed | Survived | Skipped |
|---|---|---|---|---|
| calculations | 56 | 56 | 0 | 0 |
| tool selector | 15 | 15 | 0 | 0 |
| RAG | 99 | 99 | 0 | 0 |
| market/quotes | 66 | 66 | 0 | 0 |
| execution mode/brokers | 53 | 53 | 0 | 0 |
| CSV ingestion | 94 | 94 | 0 | 0 |
| webhooks | 75 | 74 | 0 (1 equiv) | 0 |
| Alpha Vantage | 59 | 59 | 0 | 0 |
| broker tools | 86 | 86 | 0 | 0 |
| **Level 3 visual surface** | **89** | **89** | **0** | **0** |

---

## 4. Defects this phase FOUND (the reason it was worth doing)

A passing suite proves nothing. These were all found by mutation or adversarial
probing, and none was visible to a green test run.

### 4.1 In the source — real defects, now fixed

1. **The TradingView licence wall was unreachable.** The docstring claimed
   extraction was refused, `assert_tradingview_extraction_refused()` existed, and
   **nothing called it**. MEASURED: a TradingView window returned a usable
   `Quote`. A wall reachable only by a caller who already knows to invoke it
   protects nothing.
2. **Live trading was reachable by editing a config**, despite a docstring saying
   it was not (§2.4 above).
3. **The consent window was bounded at one end only.** `is_expired()` asked
   whether the TTL had run out; nothing asked whether the approval had *begun*.
   MEASURED: an approval stamped tomorrow was honoured today. A clock skew
   produces this without anyone forging anything. Fixed by `is_not_yet_valid()`.
4. **The consent TTL ceiling was writable.** Every attempt to widen *one*
   approval was refused by `__slots__`, but
   `CaptureApproval.MAX_TTL_SECONDS = 999999` succeeded and widened **every**
   approval granted afterwards — MEASURED at a 138-hour standing consent passing
   validation. Guarding the instances while leaving the limit they are checked
   against writable protects the copies and not the original. Fixed by a
   `_SealedLimits` metaclass.
5. **A `stop_p == 0` division guard** in the broker risk tools.
6. **Three declared forbidden capture targets had no enforcement at all** —
   indistinguishable from having forgotten them. Two are genuinely not
   enforceable by title and are now documented as structurally prevented, with a
   test asserting that every declared target is either enforced or explained.

### 4.2 In the tests — the dominant pattern

**A second guard answers in place of the one under test.** Nine of this phase's
eleven survivors were this shape. A type-only assertion
(`check_raises(..., SomeError)`) cannot see it when several guards raise the same
class. The fix is always the same: assert on refusal **content**, and add a
negative assertion that the *neighbouring* guard did **not** answer.

### 4.3 In the verification tooling itself

Recorded because the alternative is a battery that lies about the one number it
exists to produce:

- A mutation I wrote was a **no-op**: "content screened before consent" moved two
  statements but not the `raise`, so consent still answered first and no input
  could distinguish the mutant. It would have counted as a survivor forever.
- A probe check read the docstring sentence *"There is no `approve_all` … and no
  `remember=True`"* as evidence that those shortcuts **existed**. A probe that
  fires on prose trains its reader to ignore it.
- Stale `__pycache__` silently invalidated a mutation run; the harness now clears
  it on every pass.
- `check_raises` defaulted to `Exception`, accepting **crashes as refusals**
  across 106 assertions. **A crash is not a refusal.**

**Three lessons, one rule:** when a mutant survives, measure the mutant. "The
tests are too weak" is only one of the possible answers — the others are "the
mutation is wrong" and "the code is wrong", and this phase produced all three.

---

## 5. Honest gaps — what Phase 3A did NOT establish

- **No live HTTP fetch was ever performed against Alpha Vantage.** The connector
  is verified by 59 mutations against constructed responses. Its behaviour
  against the real API is (U).
- **Market data is not persistable.** The permitted storage timeframe is (U).
- **No broker adapter is live-capable.** Ten of twelve SS.6.1 prerequisites are
  unmet (M).
- **Screenshot capture and OCR do not exist in this runtime** (M). The entire
  Level 3 surface is verified refusal behaviour for a capability that is absent.
- **Persian handling was tested with constructed text**, not real Iranian
  filings — Codal and TSETMC are descoped (Phase 0, Q3).
- **Nothing in this phase has been run against a live model** (R10, R21 remain
  open).

---

## 6. Risks carried into Phase 4

| ID | Risk | Status |
|---|---|---|
| R10 | Persian generation quality untested | OPEN — needs the user's i5-12400 |
| R17 | Model-side tool selection unmeasured | OPEN |
| R18 | Router keyword lists need maintenance | OPEN |
| R20 | No source for permitted research/news | OPEN |
| R21 | RAG never run against a live model | OPEN |
| R22 | AV storage timeframe unknown → data non-persistable | OPEN (new) |
| Q8 | Fallback choice if decode < 9 tok/s | Deferred until measured |

---

## 7. Gate status

**Live trading: DISABLED and unreachable by configuration.**
**Active mode: ANALYSIS_ONLY.**
**Phase 4 is NOT started and NOT approved.**

Phase 4 (RAG and Tool-Enabled Evaluation) requires a running model. It is
**unstartable in this sandbox** — no model file, no `llama_cpp`, and 0.96 GiB
available RAM against a 0.85 GiB minimum weights footprint plus runtime overhead.
This is stated plainly rather than silently skipped. The approaches for executing
Phase 4 are set out separately for the user's decision.
