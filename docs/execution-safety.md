# Broker and execution safety (Phase 9, D-0126)

**Modes** (`src/execution/mode.py`):
- ANALYSIS_ONLY (the default), BACKTEST, PAPER_TRADING, LIVE_TRADING.
- The mode is read from `~/.marfin/execution.conf` and never from the model.
- PAPER and LIVE each need their own explicit opt-in line.
- LIVE is refused while any SS.6.1 prerequisite is unmet: 10 of 12 are unmet, so it is unreachable today.

**Broker tools** (`src/execution/broker_tools.py`):
- `preview_order` returns all 10 SS.8.6 fields and **no token**.
- `place_order`, `modify_order`, `cancel_order`, `cancel_all_orders` and `flatten_position` all refuse.
- No adapter is VERIFIED.

**Paper engine** (`src/execution/paper.py`, Phase 8A PASS). Each control and the test that proves it:

| Control | Implementation | Test |
|---|---|---|
| Two-phase protocol | preview → single-use token → commit, by a HUMAN only | §1, §2, §12 |
| Preview invalidation | expiry, stale quote, price move, market status, account change, limits change, kill switch | §3, §4, §8, §11 |
| 17 pre-trade checks | deterministic; REFUSE unless all PASS | §1 and the limits section |
| Idempotency | persistent; same key + same order returns the original; same key + different order is refused | §2 |
| Order states | 12 SS.6.4 states; terminal states only from a venue response; UNKNOWN on disconnect; no auto-retry | §5–§7 |
| Kill switch | persistent; fails closed; HUMAN-only disengage with phrase and reason | §11 |
| Audit log | hash-chained; redacted; tokens and keys stored as hashes only | blockers |
| Reconciliation | positions, filled quantity and cash vs the venue; mismatch → audit + kill switch | §14 |
| Separation | imports only stdlib and `execution.mode`; the venue needs an engine-signed ticket | §12 |

**What the LLM may do (SS.5.6):** analyse, draft and preview, and ask the user to confirm. **It may never:**
- commit an order;
- disengage the kill switch;
- choose the mode or the account;
- act on webhook or document instructions.
