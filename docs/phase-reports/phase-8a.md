# Phase 8A Review — Paper-Trading Safety Validation

Project: marfin-llm · Date: 2026-10-20 · Governing prompt: SYSTEM_PROMPT.md v2.0 (SS.24 Phase 8A, SS.5.6, SS.6.1–6.5, SS.8.6, SS.8.11)
Mode: `ANALYSIS_ONLY` by default · Live trading: `DISABLED` (unreachable) · Labels: (V) VERIFIED · (M) MEASURED · (C) COMPUTED · (E) ESTIMATED

## Status: **PASS (local paper engine, simulated venue)**: all 14 SS.24 tasks tested, none of the 9 release blockers present

The user delegated the decision ("Make all decisions yourself … proceed with developing the subsequent phases", D-0126).

### What was built
`src/execution/paper.py` is a local paper engine plus a simulated venue. It imports only the standard library and
`execution.mode`.

- **Order protocol (SS.6.2):** a two-phase flow — preview, then a single-use confirmation token, then commit. A
  preview is invalidated by expiry, a stale quote, price movement, a market-status change, a changed account,
  changed limits, or the kill switch.
- **Pre-trade checks (SS.6.3):** 17 deterministic checks:
  - kill switch, instrument allowlist, quote freshness (future-dated quotes refused), trading session;
  - price deviation, tick size, lot size;
  - order notional, daily notional, position size, short sale, buying power, leverage, concentration, daily loss;
  - order rate, duplicate client_order_id.
- **Order states (SS.6.4):**
  - The state machine has all 12 states and an explicit transition table.
  - SUBMITTED, ACKNOWLEDGED, PARTIALLY_FILLED, FILLED, CANCELLED and REJECTED can be set **only from a venue response**.
  - A disconnect leaves the order **UNKNOWN**; it is never guessed. There is no automatic retry.
- **Audit log (SS.8.11):** append-only and hash-chained. Edits, deletions and reordering are detected, and a new
  engine refuses to append to a broken chain. Secrets are redacted; tokens and idempotency keys are stored only as
  hashes.
- **Kill switch:** persistent and fail-closed (an unreadable file reads as engaged). Any principal may engage it.
  Only a **HUMAN** may disengage it, and only with the exact phrase and a written reason.
- **Idempotency:** a persistent store. The same key with the same order returns the original order; the same key
  with a different order is refused.
- **Who can commit:** only a **HUMAN** principal. LLM, WEBHOOK and AUTOMATION principals can draft and preview, never
  commit (SS.5.6, SS.6.5).
- **Venue access:** the venue accepts only engine-signed commit tickets, so the order book cannot be reached without
  passing through `commit`.
- **Reconciliation:**
  - UNKNOWN orders are resolved from the venue.
  - Positions, filled quantities and cash are compared against the venue.
  - Any mismatch is audited **and engages the kill switch**.

### SS.24 tasks → tests (`tests/test_phase8a.py`, 120 assertions; `tests/mutate_phase8a.py`, 60/60 killed)
| Task | Result (V) |
|---|---|
| Paper preview | PASS: 17 checks, PAPER banner, token issued only on PASS, no state change |
| Duplicate and replay | PASS: idempotent replay returns the same order; token single-use; duplicate client_order_id refused at preview **and** commit; key reuse for another order refused; store survives restart |
| Stale quote | PASS: refused at preview and at commit; a future-dated quote is not fresh |
| Price deviation | PASS: refused at preview (limit 3 % away) and at commit (2 % move); a 0.5 % move is accepted |
| Partial fill | PASS: 40 of 100 filled, then completed on the next quote (fee charged once); IOC cancels the remainder; FOK fills nothing; cancelling a partial keeps the filled part |
| Rejection | PASS: REJECTED with the venue's reason; no retry through the same preview |
| Disconnection | PASS: UNKNOWN (never guessed); reconciled to REJECTED when the venue has no record, or FILLED when the response was lost; the fill is counted exactly once; no auto-retry |
| Market closed | PASS: CLOSED, HALTED, PRE_MARKET and UNKNOWN refused; a close between preview and commit refused |
| Wrong account | PASS: off-allowlist, LIVE- and non-PAPER ids refused, including a LIVE- id smuggled onto the allowlist |
| Paper/live confusion | PASS: only the exact string `PAPER` is accepted; ANALYSIS_ONLY previews but cannot commit; `submit_live_order` is refused even in PAPER_TRADING |
| Kill switch | PASS: blocks commit and preview; LLM, WEBHOOK and AUTOMATION cannot disengage; phrase and reason required; persistent; fails closed |
| Webhook injection | PASS: a WEBHOOK, LLM or AUTOMATION principal cannot commit even holding the real token; a forged venue ticket is refused; import graph: paper.py ↛ market/rag/tools/llm, and webhooks ↛ execution |
| Concurrent orders | PASS: 16 threads on one preview produce one venue order; 8 previews from one state produce one commit, the other 7 refused as "changed since the preview"; order-rate limit holds |
| Account reconciliation | PASS: clean after trading; a 50.00 cash or filled-quantity discrepancy is reported, audited, and engages the kill switch |

### Release blockers (SS.24)
| Blocker | Present? |
|---|---|
| Paper/live ambiguity | No |
| Missing idempotency | No |
| Missing audit log | No |
| Missing kill switch | No |
| Webhook directly submitting orders | No |
| Preview bypass | No (unknown preview, wrong token, expired preview and changed limits are all refused; the venue needs a signed ticket) |
| Reconciliation failure | No (detected and fails closed) |
| Plaintext secret exposure | No (token and key never logged) |
| Stale quote accepted | No |

### Defects found by the tests and the battery (M), all fixed
1. **Two identical previews at the same instant got the same id**, so the second overwrote the first and silently
   voided its token. The preview id now carries a random nonce, and a collision is refused.
2. **First battery: 6 survivors.** In each case another control refused first, so the control under test was never
   exercised. Each control now has a test that isolates it.
3. **The race test could not see a missing engine lock.** The idempotency store's own lock, and the commit-time
   duplicate check, each also stop a racing second commit, which hid it. The race test now uses a different key per
   thread and a widened check-then-act window. The mutant removes **both** the lock and the duplicate check, and the
   test still requires one venue order.

### What this does NOT establish
- No broker paper account was exercised: no adapter exists or is VERIFIED.
- The SS.6.1 rows in `execution.mode.LIVE_PREREQUISITES` therefore stay **False**, now with reasons that name the
  paper engine. `test_execution` still requires them unmet.
- Live trading remains unreachable: `submit_live_order` is refused regardless of configuration (SS.24: "Live trading
  remains disabled after this phase unless separately approved").
