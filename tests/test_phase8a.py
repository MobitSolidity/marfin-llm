# -*- coding: utf-8 -*-
"""
Phase 8A (D-0126): paper-trading safety validation, SS.24.

One section per SS.24 task (14) and one per release blocker (9). Every test
drives src/execution/paper.py with a deterministic clock and a simulated venue;
nothing reaches a network and no credential exists.

(V) verified invariant, (A) adversarial: the call must be refused, (B) hand
arithmetic.
"""
import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

from _harness import check, check_raises, check_true, section, summary  # noqa: E402
from execution import mode as M                                         # noqa: E402
from execution import paper as P                                        # noqa: E402

_TMP = tempfile.mkdtemp(prefix="p8a_")
_CONF = os.path.join(_TMP, "execution.conf")
with open(_CONF, "w") as _fh:
    _fh.write("mode = PAPER_TRADING\ni_have_enabled_paper_trading = yes\n")
M._reset_cache_for_tests(_CONF)

T0 = datetime.datetime(2026, 10, 20, 14, 30, tzinfo=datetime.timezone.utc)
ACCT = "PAPER-0001"
REF = (P.PaperError,)


def at(s):
    return T0 + datetime.timedelta(seconds=s)


def q(last=100.0, t=0, status="OPEN", spread=0.02, size=1e12, inst="AAPL"):
    return P.QuoteSnapshot(inst, last - spread / 2, last + spread / 2, last, at(t),
                           status, "test-feed", bid_size=size, ask_size=size)


_n = [0]


def engine(**lim):
    _n[0] += 1
    d = os.path.join(_TMP, "eng%d" % _n[0])
    kw = dict(instrument_allowlist=("AAPL", "MSFT"), tick_size={"AAPL": 0.01},
              lot_size={"AAPL": 1})
    kw.update(lim)
    return P.PaperEngine(d, {ACCT: 100_000.0, "PAPER-0002": 50_000.0},
                         P.RiskLimits(**kw)), d


def pv(e, qty=10, side="buy", otype="market", coid=None, quote=None, lp=None,
       acct=ACCT, env="PAPER", t=0, tif="day", inst="AAPL"):
    _n[0] += 1
    return e.preview(acct, env, inst, side, qty, otype, coid or "c%d" % _n[0],
                     quote or q(t=t, inst=inst), limit_price=lp,
                     time_in_force=tif, now=at(t))


def commit(e, p, key=None, principal="HUMAN", quote=None, t=1, token=None):
    return e.commit(p["preview_id"], token if token is not None else p["confirmation_token"],
                    key or ("k-" + p["preview_id"]), principal,
                    quote or q(t=t), now=at(t))


# ===========================================================================
section("1. paper preview")
# ===========================================================================
e, _d = engine()
p = pv(e)
check_true("a valid paper order previews PASS with every check PASS",
           p["verdict"] == "PASS" and all(c["status"] == "PASS" for c in p["risk_checks"].values()),
           "(V) %r" % {k: v for k, v in p["risk_checks"].items() if v["status"] != "PASS"})
check("the preview runs 17 named checks", len(p["risk_checks"]), 17, 0, "(V)")
check_true("the preview shows PAPER in its environment and banner",
           p["environment"] == "PAPER" and "PAPER" in p["banner"], "(V)")
check("notional = 10 x ask 100.01", p["estimated_notional"], 1000.1, 1e-9, "(B)")
check_true("a PASS preview carries a single-use confirmation token and an expiry",
           isinstance(p["confirmation_token"], str) and len(p["confirmation_token"]) >= 16
           and p["preview_expiry"] == "2026-10-20T14:31:00.000000Z", "(V)")
check_true("a preview changes nothing: no order, no cash moved",
           not e.orders and e.cash[ACCT] == 100_000.0, "(V)")
p_bad = pv(e, qty=5000)
check_true("a failing preview is REFUSE and gets NO token",
           p_bad["verdict"] == "REFUSE" and p_bad["confirmation_token"] is None, "(A)")

# ===========================================================================
section("2. duplicate and replay")
# ===========================================================================
e, _d = engine()
p = pv(e, coid="dup-1")
o = commit(e, p, key="idem-1")
check_true("first commit is FILLED at the venue", o["state"] == "FILLED", "(V) %s" % o["state"])
o2 = commit(e, p, key="idem-1")
check_true("the SAME idempotency key returns the SAME order and submits nothing new",
           o2["order_id"] == o["order_id"] and o2.get("idempotent_replay") is True
           and len(e.venue.orders) == 1, "(V)")
check_raises("the same token with a NEW key is refused (single-use)",
             lambda: commit(e, p, key="idem-2"), REF)
p_dup = pv(e, coid="dup-1", t=2)
check_true("a new preview reusing a submitted client_order_id is REFUSE",
           p_dup["verdict"] == "REFUSE"
           and p_dup["risk_checks"]["duplicate_order"]["status"] == "FAIL", "(A)")
e, _d = engine()
pa, pb = pv(e, coid="same"), pv(e, coid="same")
commit(e, pa)
check_raises("two previews of one client_order_id: the second commit is refused",
             lambda: commit(e, pb), REF)
e, _d = engine()
p1 = pv(e, coid="x1")
o1 = commit(e, p1, key="shared")
p2 = pv(e, coid="x2", t=2)
check_raises("an idempotency key reused for a DIFFERENT order is refused",
             lambda: commit(e, p2, key="shared", t=3), REF)
_e2 = P.PaperEngine(_d, {ACCT: 100_000.0, "PAPER-0002": 50_000.0}, e.limits)
check_true("the idempotency store survives a restart",
           _e2.idem.lookup("shared", e._previews[p1["preview_id"]]["content"]) == o1["order_id"],
           "(V)")

# ===========================================================================
section("3. stale quote")
# ===========================================================================
e, _d = engine(max_quote_age_s=5.0)
p = e.preview(ACCT, "PAPER", "AAPL", "buy", 10, "market", "s1", q(t=0), now=at(6))
check_true("a 6 s old quote (max 5 s) previews REFUSE on quote_freshness",
           p["risk_checks"]["quote_freshness"]["status"] == "FAIL" and p["verdict"] == "REFUSE",
           "(A)")
p = pv(e)
check_raises("a quote that goes stale before commit is refused",
             lambda: commit(e, p, quote=q(t=0), t=7), REF)
pf = e.preview(ACCT, "PAPER", "AAPL", "buy", 10, "market", "s9", q(t=10), now=at(5))
check_true("a quote stamped in the FUTURE is not fresh",
           pf["risk_checks"]["quote_freshness"]["status"] == "FAIL", "(A)")

# ===========================================================================
section("4. price deviation")
# ===========================================================================
e, _d = engine(price_deviation_pct=1.0)
p = pv(e, otype="limit", lp=103.0)
check_true("a limit 3 % away from last is REFUSE on price_deviation",
           p["risk_checks"]["price_deviation"]["status"] == "FAIL", "(A)")
p = pv(e)
check_raises("price moved 2 % between preview and commit: refused",
             lambda: commit(e, p, quote=q(last=102.0, t=1)), REF)
p = pv(e, t=5)
o = commit(e, p, quote=q(last=100.5, t=6), t=6)
check_true("a 0.5 % move (within 1 %) commits", o["state"] == "FILLED", "(V)")

# ===========================================================================
section("5. partial fill")
# ===========================================================================
e, _d = engine(max_order_notional=1e5)
p = pv(e, qty=100, quote=q(size=40))
o = commit(e, p, quote=q(size=40, t=1))
check_true("size 40 at the touch fills 40 of 100: PARTIALLY_FILLED",
           o["state"] == "PARTIALLY_FILLED" and o["filled_qty"] == 40.0, "(V) %r" % o["state"])
check("cash = 100000 - 40 x 100.01 - fee 1", e.cash[ACCT], 100000 - 4000.4 - 1.0, 1e-6, "(B)")
e.on_quote(q(size=1e6, t=2), now=at(2))
oo = e.orders[o["order_id"]]
check_true("the next quote completes it: FILLED, 100 shares, fee charged once",
           oo["state"] == "FILLED" and oo["filled_qty"] == 100.0 and oo["fees"] == 1.0, "(V)")
check_true("history is the SS.6.4 path, every step legal",
           oo["history"] == ["DRAFT", "PREVIEWED", "WAITING_FOR_CONFIRMATION", "SUBMITTED",
                             "ACKNOWLEDGED", "PARTIALLY_FILLED", "FILLED"], "(V) %r" % oo["history"])
e, _d = engine(max_order_notional=1e5)
o = commit(e, pv(e, qty=100, quote=q(size=40), tif="ioc"), quote=q(size=40, t=1))
check_true("IOC: the unfilled remainder is CANCELLED, 40 filled",
           o["state"] == "CANCELLED" and o["filled_qty"] == 40.0, "(V)")
e, _d = engine(max_order_notional=1e5)
o = commit(e, pv(e, qty=100, quote=q(size=40), tif="fok"), quote=q(size=40, t=1))
check_true("FOK: insufficient size fills nothing and is CANCELLED",
           o["state"] == "CANCELLED" and o["filled_qty"] == 0.0 and e.cash[ACCT] == 100000.0, "(V)")
e, _d = engine(max_order_notional=1e5)
o = commit(e, pv(e, qty=100, quote=q(size=40)), quote=q(size=40, t=1))
c = e.cancel(o["order_id"], "HUMAN", now=at(2))
check_true("cancelling a partial keeps the 40 filled and ends CANCELLED",
           c["state"] == "CANCELLED" and c["filled_qty"] == 40.0, "(V)")

# ===========================================================================
section("6. rejection")
# ===========================================================================
e, _d = engine()
e.venue.reject_instruments.add("MSFT")
p = pv(e, inst="MSFT", quote=q(inst="MSFT"))
o = commit(e, p, quote=q(inst="MSFT", t=1))
check_true("a venue rejection is REJECTED, with the venue's reason, nothing filled",
           o["state"] == "REJECTED" and o["venue_reason"] and o["filled_qty"] == 0.0, "(V)")
check_raises("a rejected order is not retried by re-using its preview",
             lambda: commit(e, p, key="other", quote=q(inst="MSFT", t=2), t=2), REF)
check_raises("a rejected order cannot be cancelled",
             lambda: e.cancel(o["order_id"], "HUMAN", now=at(3)), REF)

# ===========================================================================
section("7. disconnection")
# ===========================================================================
e, _d = engine()
e.venue.connected = False
o = commit(e, pv(e, coid="dc-1"))
check_true("venue unreachable at submit: UNKNOWN, never FILLED or REJECTED by guess",
           o["state"] == "UNKNOWN" and not e.venue.orders, "(V)")
r = e.reconcile(now=at(2))
check_true("reconcile while still unreachable leaves it UNKNOWN and engages the kill switch",
           e.orders[o["order_id"]]["state"] == "UNKNOWN" and not r["ok"]
           and e.kill.engaged(), "(V)")
e.venue.connected = True
r = e.reconcile(now=at(3))
check_true("once reachable, a venue with no record resolves it to REJECTED",
           e.orders[o["order_id"]]["state"] == "REJECTED" and r["ok"], "(V) %r" % r["problems"])
e, _d = engine()
e.venue.drop_after_accept = True
o = commit(e, pv(e, coid="dc-2"))
check_true("venue accepted but the response was lost: UNKNOWN (not a failure)",
           o["state"] == "UNKNOWN" and len(e.venue.orders) == 1, "(V)")
e.venue.drop_after_accept = False
r = e.reconcile(now=at(2))
oo = e.orders[o["order_id"]]
check_true("reconcile resolves it from the venue: FILLED, and the fill lands exactly once",
           oo["state"] == "FILLED" and oo["filled_qty"] == 10.0 and r["ok"], "(V) %r" % r)
check("cash after the reconciled fill", e.cash[ACCT], 100000 - 1000.1 - 1.0, 1e-6, "(B)")
check_true("no automatic retry: the venue saw exactly one order",
           len(e.venue.orders) == 1, "(A)")

# ===========================================================================
section("8. market closed")
# ===========================================================================
e, _d = engine()
for st in ("CLOSED", "HALTED", "PRE_MARKET", "UNKNOWN"):
    p = pv(e, quote=q(status=st))
    check_true("market %s previews REFUSE on trading_session" % st,
               p["risk_checks"]["trading_session"]["status"] == "FAIL", "(A)")
p = pv(e)
check_raises("market closes between preview and commit: refused",
             lambda: commit(e, p, quote=q(status="CLOSED", t=1)), REF)

# ===========================================================================
section("9. wrong account")
# ===========================================================================
e, _d = engine()
check_raises("an account not on the allowlist is refused",
             lambda: pv(e, acct="PAPER-9999"), REF)
check_raises("a LIVE- account is refused in paper",
             lambda: pv(e, acct="LIVE-0001"), REF)
check_raises("an engine cannot be built over a non-PAPER account id",
             lambda: P.PaperEngine(os.path.join(_TMP, "bad"), {"0001": 1.0},
                                   P.RiskLimits(("AAPL",))), REF)
check_raises("a non-string account id is refused", lambda: pv(e, acct=1), REF)

# ===========================================================================
section("10. paper/live confusion")
# ===========================================================================
for env in ("LIVE", "live", "paper", "", None, "PAPER ", "Paper"):
    check_raises("environment %r is refused (only exactly 'PAPER')" % (env,),
                 lambda env=env: pv(e, env=env), REF)
check_true("the manifest says live submission is impossible, with 4 independent reasons",
           e.manifest()["can_submit_live"] is False and len(e.manifest()["live_refused_by"]) == 4,
           "(V)")
check_raises("submit_live_order stays refused even in PAPER_TRADING (SS.6.1 unmet)",
             lambda: M.require("submit_live_order"), (M.ExecutionModeError,))
check_true("SS.6.1 is still unmet (no verified adapter, no licensed data)",
           not M.live_trading_enabled() and len(M.unmet_live_prerequisites()) >= 2, "(V)")
with open(_CONF, "w") as _fh:
    _fh.write("mode = ANALYSIS_ONLY\n")
M._reset_cache_for_tests(_CONF)
e, _d = engine()
p = pv(e)
check_raises("in ANALYSIS_ONLY a preview works but a commit is refused (mode gate)",
             lambda: commit(e, p), REF)
with open(_CONF, "w") as _fh:
    _fh.write("mode = PAPER_TRADING\ni_have_enabled_paper_trading = yes\n")
M._reset_cache_for_tests(_CONF)

# ===========================================================================
section("11. kill switch")
# ===========================================================================
e, _d = engine()
p = pv(e)
e.kill.engage("LLM", "model asked to stop", now=at(0))
check_raises("engaged after preview: the commit is refused", lambda: commit(e, p), REF)
check_true("engaged: every new preview is REFUSE",
           pv(e)["risk_checks"]["kill_switch"]["status"] == "FAIL", "(A)")
for who in ("LLM", "WEBHOOK", "AUTOMATION"):
    check_raises("%s cannot disengage the kill switch" % who,
                 lambda who=who: e.kill.disengage(who, P.KillSwitch.PHRASE, "x"), REF)
check_raises("a HUMAN without the exact phrase cannot disengage",
             lambda: e.kill.disengage("HUMAN", "yes", "x"), REF)
check_raises("a HUMAN without a reason cannot disengage",
             lambda: e.kill.disengage("HUMAN", P.KillSwitch.PHRASE, " "), REF)
_e3 = P.PaperEngine(_d, {ACCT: 1.0}, e.limits)
check_true("the kill switch survives a restart", _e3.kill.engaged(), "(V)")
with open(os.path.join(_d, "kill_switch.json"), "w") as _fh:
    _fh.write("{not json")
check_true("an unreadable kill-switch file reads as ENGAGED (fail closed)", e.kill.engaged(), "(A)")
e.kill.disengage("HUMAN", P.KillSwitch.PHRASE, "test complete", now=at(5))
check_true("a HUMAN with phrase and reason disengages it, and that is audited",
           not e.kill.engaged()
           and e.audit.records()[-1]["event"] == "kill_switch_disengaged", "(V)")

# ===========================================================================
section("12. webhook injection")
# ===========================================================================
e, _d = engine()
p = pv(e)
for who in ("WEBHOOK", "LLM", "AUTOMATION"):
    check_raises("a %s principal cannot commit, even holding the real token" % who,
                 lambda who=who: commit(e, p, principal=who), REF)
check_true("those refusals are audited", sum(r["event"] == "commit_refused"
                                             for r in e.audit.records()) == 3, "(V)")
check_raises("an order cannot reach the venue without the engine's commit ticket",
             lambda: e.venue.submit(dict(p["order"]), "forged", q(), at(1)), REF)
import ast                                                                  # noqa: E402
_tree = ast.parse(open(os.path.join(ROOT, "src", "execution", "paper.py")).read())
_mods = {n.module for n in ast.walk(_tree) if isinstance(n, ast.ImportFrom) and n.module} | \
        {a.name for n in ast.walk(_tree) if isinstance(n, ast.Import) for a in n.names}
check_true("paper.py imports nothing from market/, rag/, tools/ or llm/ (SS.5.6)",
           not any(m.split(".")[0] in ("market", "rag", "tools", "llm") for m in _mods),
           "(V) %r" % sorted(_mods))
_wh_tree = ast.parse(open(os.path.join(ROOT, "src", "market", "webhooks.py")).read())
_wh_mods = {n.module for n in ast.walk(_wh_tree) if isinstance(n, ast.ImportFrom) and n.module}
check_true("the webhook receiver imports nothing from execution/",
           not any(m.startswith("execution") for m in _wh_mods), "(V)")

# ===========================================================================
section("13. concurrent orders")
# ===========================================================================
e, _d = engine(max_orders_per_minute=50)
p = pv(e, coid="race")
results, errors = [], []


def _go(i):
    try:
        results.append(commit(e, p, key="race-key"))
    except P.PaperError as exc:
        errors.append(str(exc))


ths = [threading.Thread(target=_go, args=(i,)) for i in range(16)]
for t in ths:
    t.start()
for t in ths:
    t.join()
check_true("16 threads committing one preview with one key: the venue sees ONE order",
           len(e.venue.orders) == 1 and len({r["order_id"] for r in results}) == 1, "(V)")
e, _d = engine(max_orders_per_minute=50)
ps = [pv(e, coid="par-%d" % i, qty=1) for i in range(8)]
errs = []


def _go2(pp):
    try:
        commit(e, pp)
    except P.PaperError as exc:
        errs.append(str(exc))


ths = [threading.Thread(target=_go2, args=(pp,)) for pp in ps]
for t in ths:
    t.start()
for t in ths:
    t.join()
check_true("8 previews from one state: only the first commits; the rest see changed positions",
           len(e.venue.orders) == 1 and len(errs) == 7
           and all("changed since the preview" in x for x in errs), "(V) %r" % errs[:1])
e, _d = engine(max_orders_per_minute=3)
for i in range(3):
    commit(e, pv(e, coid="r%d" % i, qty=1, t=i), t=i)
p = pv(e, coid="r3", qty=1, t=4)
check_true("order-rate limit: the 4th order within a minute is REFUSE",
           p["risk_checks"]["order_rate"]["status"] == "FAIL", "(A)")

# ===========================================================================
section("14. account reconciliation")
# ===========================================================================
e, _d = engine()
commit(e, pv(e, qty=10))
r = e.reconcile(now=at(5))
check_true("after normal trading the ledger reconciles", r["ok"], "(V) %r" % r["problems"])
e.cash[ACCT] += 50.0
r = e.reconcile(now=at(6))
check_true("a 50.00 cash discrepancy is reported and engages the kill switch",
           not r["ok"] and any("cash" in x for x in r["problems"]) and e.kill.engaged(), "(A)")
e, _d = engine()
o = commit(e, pv(e, qty=10))
e.orders[o["order_id"]]["filled_qty"] = 9.0
r = e.reconcile(now=at(5))
check_true("a filled-quantity mismatch is reported",
           not r["ok"] and any("filled" in x for x in r["problems"]), "(A)")
check_true("the failed reconciliation is audited",
           e.audit.records()[-2]["event"] == "reconcile"
           and e.audit.records()[-2]["ok"] is False, "(V)")

# ===========================================================================
section("blockers: none of the nine SS.24 release blockers is present")
# ===========================================================================
e, _d = engine()
p = pv(e, coid="aud-1")
commit(e, p, key="secret-key-should-not-appear")
recs = e.audit.records()
check_true("[audit log] every preview and commit is audited, hash-chained, verifiable",
           [r["event"] for r in recs] == ["preview", "submitted"] and e.audit.verify()[0], "(V)")
with open(os.path.join(_d, "audit.jsonl")) as _fh:
    _lines = _fh.readlines()
_tampered = _lines[0].replace('"quantity": 10.0', '"quantity": 11.0')
with open(os.path.join(_d, "audit.jsonl"), "w") as _fh:
    _fh.writelines([_tampered] + _lines[1:])
check_true("[audit log] an edited record breaks the chain", not e.audit.verify()[0], "(A)")
check_raises("[audit log] a new engine refuses to append to a broken chain",
             lambda: P.PaperEngine(_d, {ACCT: 1.0}, e.limits), REF)
_raw = "".join(_lines)
check_true("[plaintext secrets] neither the token nor the idempotency key is in the log",
           p["confirmation_token"] not in _raw and "secret-key-should-not-appear" not in _raw,
           "(V)")
check_true("[plaintext secrets] redact() hides secret-named fields at any depth",
           P.redact({"a": {"api_key": "x", "list": [{"Password": "y"}]}, "ok": 1})
           == {"a": {"api_key": "[REDACTED]", "list": [{"Password": "[REDACTED]"}]}, "ok": 1},
           "(V)")
e, _d = engine()
p = pv(e)
check_raises("[preview bypass] commit with an unknown preview id",
             lambda: e.commit("prv_forged", "t", "k", "HUMAN", q(t=1), now=at(1)), REF)
check_raises("[preview bypass] commit with a wrong token",
             lambda: commit(e, p, token="wrong"), REF)
check_raises("[preview bypass] commit after the 60 s preview expiry",
             lambda: commit(e, p, t=61, quote=q(t=61)), REF)
check_raises("[preview bypass] commit after the limits changed",
             lambda: (setattr(e, "limits", P.RiskLimits(("AAPL", "MSFT"), max_order_notional=5e3)),
                      commit(e, p)), REF)
check_raises("[idempotency] a commit without an idempotency key",
             lambda: commit(e, pv(e), key=" "), REF)
check_true("[stale quote] covered in section 3", True, "(V)")
check_true("[kill switch] covered in section 11", True, "(V)")
check_true("[webhook] covered in section 12", True, "(V)")
check_true("[reconciliation] covered in section 14", True, "(V)")
check_true("[paper/live] covered in sections 9-10", True, "(V)")

# ===========================================================================
section("state machine and limits")
# ===========================================================================
e, _d = engine()
o = commit(e, pv(e, otype="limit", lp=99.5, qty=5))
check_true("a non-marketable limit rests ACKNOWLEDGED", o["state"] == "ACKNOWLEDGED", "(V)")
oo = e.orders[o["order_id"]]
check_raises("FILLED cannot be set without a venue response",
             lambda: e._set_state(oo, "FILLED"), REF)
check_raises("an illegal transition is refused", lambda: e._set_state(oo, "DRAFT"), REF)
check_true("every state is in SS.6.4 and every transition target is a state",
           set(P.TRANSITIONS) == set(P.ORDER_STATES)
           and all(t in P.ORDER_STATES for v in P.TRANSITIONS.values() for t in v), "(V)")
check_true("terminal states have no exits",
           all(not P.TRANSITIONS[s] for s in P.TERMINAL_STATES), "(V)")
e, _d = engine()
for name, kw, chk in (("order notional", dict(qty=200), "order_notional"),
                      ("position size", dict(qty=1500), "position_size"),
                      ("buying power", dict(qty=999, inst="MSFT", quote=q(inst="MSFT")), "buying_power"),
                      ("tick size", dict(otype="limit", lp=100.005), "tick_size"),
                      ("lot size", dict(qty=1.5), "lot_size"),
                      ("short sale", dict(side="sell_short"), "short_sale"),
                      ("instrument allowlist", dict(inst="TSLA", quote=q(inst="TSLA")), "instrument_allowlist")):
    if chk == "buying_power":
        e2, _ = engine(max_order_notional=1e9, max_position_qty=1e9, max_concentration_pct=1e9,
                       max_leverage=100.0, max_daily_notional=1e12)
        r = pv(e2, acct="PAPER-0002", qty=600)
    else:
        r = pv(e, **kw)
    check_true("%s limit: REFUSE on %s" % (name, chk),
               r["risk_checks"][chk]["status"] == "FAIL" and r["verdict"] == "REFUSE",
               "(A) %r" % r["risk_checks"][chk])
e, _d = engine(max_daily_notional=2500.0, max_orders_per_minute=50)
commit(e, pv(e, qty=20))
r = pv(e, qty=10, t=2)
check_true("daily notional: 2000.2 used + 1000.1 > 2500 is REFUSE",
           r["risk_checks"]["daily_notional"]["status"] == "FAIL", "(B)")
e, _d = engine(max_daily_loss=100.0, max_orders_per_minute=50, max_order_notional=1e6, max_daily_notional=1e6,
               max_concentration_pct=100.0)
commit(e, pv(e, qty=500, quote=q(last=100.0)), quote=q(last=100.0, t=1))
r = e.preview(ACCT, "PAPER", "AAPL", "buy", 1, "market", "dl", q(last=99.7, t=3), now=at(3))
check_true("daily loss: a 0.3 drop on 500 shares (~ -156) breaches max_daily_loss 100",
           r["risk_checks"]["daily_loss"]["status"] == "FAIL", "(B) %r" % r["risk_checks"]["daily_loss"])
check_raises("a crossed quote is refused", lambda: P.QuoteSnapshot(
    "AAPL", 101, 100, 100, at(0), "OPEN", "x"), REF)
check_raises("a quote is immutable", lambda: setattr(q(), "last", 1.0), (AttributeError,))
check_raises("limits require an instrument allowlist", lambda: P.RiskLimits(()), REF)
check_raises("naive timestamps are refused", lambda: e.preview(
    ACCT, "PAPER", "AAPL", "buy", 1, "market", "n", q(), now=datetime.datetime(2026, 1, 1)), REF)

# ===========================================================================
section("defence in depth: each control holds on its own (mutation survivors)")
# ===========================================================================
# Each of these was a mutation SURVIVOR on the first battery: another control
# refused first, so the one under test was never exercised. Each test now
# isolates the control so its removal is visible.
e, _d = engine()
p = pv(e, qty=5000)
_pvrec = e._previews[p["preview_id"]]
_pvrec["token_hash"] = P._sha("forced")
check_raises("a REFUSE preview is not committable even if a token somehow exists",
             lambda: commit(e, p, token="forced"), REF)
e, _d = engine(max_orders_per_minute=50)
p = pv(e, coid="once")
commit(e, p, key="a1")
e.orders.clear()                     # isolate: no duplicate/position evidence left
e._account_version[ACCT] = e._previews[p["preview_id"]]["account_version"]
check_raises("a used token is refused on its own (single-use flag)",
             lambda: commit(e, p, key="a2", t=2), REF)
e, _d = engine(max_orders_per_minute=50)
pa, pb = pv(e, coid="dd", qty=1), pv(e, coid="dd", qty=1)
commit(e, pa)
_pb = e._previews[pb["preview_id"]]
_pb["account_version"] = e._account_version[ACCT]
_pb["open_orders"] = e._open_orders(ACCT)
check_raises("commit-time duplicate client_order_id check holds on its own",
             lambda: commit(e, pb, t=2), REF)
_dl = os.path.join(_TMP, "live_on_list")
_el = P.PaperEngine(_dl, {ACCT: 1e5}, P.RiskLimits(("AAPL",)))
_el.cash["LIVE-0001"] = 1e5          # a LIVE id smuggled onto the allowlist
check_raises("a LIVE- account is refused even if it is on the allowlist",
             lambda: pv(_el, acct="LIVE-0001"), REF)
e, _d = engine()
commit(e, pv(e, coid="ch1"))
commit(e, pv(e, coid="ch2", qty=1, t=2), t=2)
_ap = os.path.join(_d, "audit.jsonl")
_ls = open(_ap).readlines()
open(_ap, "w").writelines(_ls[:1] + _ls[2:])     # delete one record, no edits
check_true("deleting an audit record (no edit) breaks the chain",
           not e.audit.verify()[0] and "chain" in e.audit.verify()[2], "(A) %r" % (e.audit.verify(),))


class _SlowVenue(P.PaperVenue):
    def submit(self, *a, **k):
        import time
        time.sleep(0.05)
        return P.PaperVenue.submit(self, *a, **k)


_ds = os.path.join(_TMP, "slow")
_es = P.PaperEngine(_ds, {ACCT: 1e5}, P.RiskLimits(("AAPL",), max_orders_per_minute=50),
                    venue=_SlowVenue(b""))
_ps = pv(_es, coid="slow")
# Widen the check-then-act window: the kill-switch read sits between the
# single-use check and the flag being set, so a slow read exposes a missing lock.
_real_engaged = _es.kill.engaged


def _slow_engaged():
    import time
    time.sleep(0.02)
    return _real_engaged()


_es.kill.engaged = _slow_engaged
_res = []
# A DIFFERENT idempotency key per thread, so the idempotency store cannot be
# what serialises them: only the engine lock can (measured: with one shared key
# the store's own lock hid a missing engine lock).


def _try(i):
    try:
        _res.append(commit(_es, _ps, key="slow-k%d" % i))
    except P.PaperError:
        pass


_th = [threading.Thread(target=_try, args=(i,)) for i in range(6)]
for t in _th:
    t.start()
for t in _th:
    t.join()
check_true("a slow venue + 6 concurrent commits of one preview: exactly ONE venue order",
           len(_es.venue.orders) == 1, "(A) %d" % len(_es.venue.orders))

shutil.rmtree(_TMP, ignore_errors=True)
print("")
sys.exit(summary())
