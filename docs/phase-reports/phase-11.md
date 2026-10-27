# Phase 11: Live-Trading Enablement (D-0140)

Started 2026-10-26 on the owner's explicit request. Verdict: **BLOCKED**. Live trading stays
unreachable, and nothing in this phase can switch it on.

Labels: VERIFIED (read from code or an official page today), MEASURED (run here), COMPUTED,
ESTIMATED (my proposal, not checked).

## 1. Prerequisites (SYSTEM_PROMPT section 24)

Source: `python -c "from execution import live_readiness as LR; print(LR.readiness())"`, also
shown on the UI's Phase 11 page. MEASURED 2026-10-26.

| # | Prerequisite | Met | Evidence |
|---|---|---|---|
| 1 | Phase 8A PASS | yes | D-0126: 14/14 tasks, 0 release blockers |
| 2 | No critical execution blockers | yes | Phase 8A release blockers: 0 |
| 3 | Verified broker live environment | **no** | 0 of 3 catalogued adapters VERIFIED; no broker chosen |
| 4 | Independent authorised market data | **no** | Alpha Vantage free tier = END_OF_DAY, enabled on accepted risk, not licensed; Twelve Data declined |
| 5 | Explicit user request | yes | 2026-10-26 |
| 6 | Explicit risk limits | **no** | `configs/live-policy.json` drafted, `human_approved: false` |
| 7 | Audit and monitoring enabled | **no** | hash-chained audit exists for PAPER only; no live path |
| 8 | Emergency response tested | **no** | paper drill PASSED (MEASURED); a live drill needs a live adapter |

3 of 8 met. SS.6.1 (`execution/mode.py`): 10 of 12 unmet, unchanged by this phase.

Approving the live policy would make 4 of 8 (tested in `tests/test_ui.py`). Prerequisites 3, 4, 7
and 8 need a real broker account and licensed real-time data. Code cannot produce either.

## 2. Deliverables

| Deliverable | Status |
|---|---|
| Live-mode activation plan | DRAFTED, section 3 |
| Account allowlist | DRAFTED, EMPTY: no live account exists. Ids must start with `LIVE-` (enforced) |
| Instrument limits | DRAFTED (ESTIMATED): AAPL, MSFT. Must be a subset of the paper allowlist (enforced) |
| Maximum order limits | DRAFTED (ESTIMATED): 1,000 per order, 3,000 per day (paper: 10,000 / 50,000) |
| Maximum daily loss | DRAFTED (ESTIMATED): 200 (paper: 1,000) |
| Kill-switch test | PAPER drill, 10 steps, PASSED (MEASURED). Live drill NOT RUN |
| Per-order confirmation policy | ALWAYS. No automation policy. Weakening it is refused (enforced) |
| Monitoring dashboard | BUILT: `scripts/ui.py` (dashboard, audit, maintenance, Phase 11 pages) |
| Rollback plan | section 4 |

`execution/live_readiness.check_live_policy` refuses any live limit looser than the paper limit,
any instrument outside the paper allowlist, short selling live when paper forbids it, a non-`LIVE-`
account id, and per-order confirmation other than ALWAYS without an approved automation policy.

## 3. Activation plan (what has to happen, in order)

1. **Owner chooses a broker.** UNVERIFIED for every candidate: whether it opens accounts for the
   owner's jurisdiction under sanctions. Only the broker's own written answer settles this.
   Alpaca and Interactive Brokers are catalogued as DOCUMENTED (`execution/brokers.py`), nothing more.
2. **Licensed real-time market data** for the same instruments, with machine use permitted in its terms.
3. **Adapter, paper first.** Write the adapter, then run it against the broker's PAPER environment
   until it passes the Phase 8A suite. Its verification level becomes SANDBOX_TESTED.
4. **Live round-trip under review.** One minimal order, reviewed by the owner. The level becomes VERIFIED.
5. **Owner approves `configs/live-policy.json`** (`human_approved: true`, a real `LIVE-` account id).
6. **Live kill-switch drill** against the adapter, with the result recorded.
7. **SS.6.1 table updated** in `execution/mode.py`, entry by entry, each with its evidence and
   tests. Only then can `live_trading_enabled()` return True, and only for the approved scope.

None of these steps can be done by the assistant alone. Steps 1, 2, 4 and 5 are the owner's.

## 4. Rollback

- **Immediate:** engage the kill switch (UI → paper trading → «توقف اضطراری»). Any principal can
  engage it; only a HUMAN, with the exact phrase and a written reason, can disengage it.
- **Mode:** set `mode = ANALYSIS_ONLY` in `%USERPROFILE%\.marfin\execution.conf`. Live capability
  disappears on the next start.
- **Code:** `python tools/maintain.py --rollback <version>` restores a previous release; the
  release manifests in `releases/` are immutable.
- **After any live incident:** `tools/maintain.py --audit <dir>` verifies the audit chain and
  reconciliation. A broken chain is CRITICAL.

## 5. What this phase did NOT do

It did not enable live trading. It did not write the execution config, register a broker,
or treat documentation reading as verification. It did not relabel END_OF_DAY data as real-time.
