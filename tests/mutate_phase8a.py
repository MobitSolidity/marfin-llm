# -*- coding: utf-8 -*-
"""
Mutation battery for Phase 8A (D-0126): src/execution/paper.py.
Each mutation removes or weakens ONE safety control; tests/test_phase8a.py must
fail for every one. Committed tree only; restore by rewrite.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ORACLE = os.path.join(HERE, "test_phase8a.py")
PP = "src/execution/paper.py"

MUTATIONS = [
    (PP, "human-only commit removed", '        if principal != "HUMAN":\n            raise PaperError("a commit must', '        if False:\n            raise PaperError("a commit must'),
    (PP, "mode gate on commit removed", '            require("submit_paper_order")', '            pass'),
    (PP, "idempotency key not required", '        if not isinstance(idem_key, str) or not idem_key.strip():', '        if False:'),
    (PP, "idempotent replay disabled", '        existing = self.idem.lookup(idem_key, pv["content"])', '        existing = None'),
    (PP, "key reuse for another order allowed", '        if hit[0] != content:', '        if False:'),
    (PP, "REFUSE preview committable", '        if not pv["ok"]:\n            raise', '        if False:\n            raise'),
    (PP, "token reusable", '        if pv["used"]:', '        if False:'),
    (PP, "token not checked", '                not hmac.compare_digest(_sha(token), pv["token_hash"]):', '                False:'),
    (PP, "preview expiry ignored", '        if now > pv["expiry"]:', '        if False:'),
    (PP, "kill switch ignored at commit", '        if self.kill.engaged():\n            raise PaperError("kill switch is engaged")', '        if False:\n            raise PaperError("kill switch is engaged")'),
    (PP, "limits change ignored", '        if pv["limits_version"] != self.limits.version:', '        if False:'),
    (PP, "position/open-order change ignored", '        if pv["account_version"] != self._account_version[acct] or \\\n                pv["open_orders"] != self._open_orders(acct):', '        if False:'),
    (PP, "stale quote at commit accepted", '        if (now - quote.timestamp).total_seconds() > self.limits.max_quote_age_s:', '        if False:'),
    (PP, "market change at commit ignored", '        if quote.market_status != pv["quote"].market_status or quote.market_status != "OPEN":', '        if False:'),
    (PP, "price move at commit ignored", '        if moved > self.limits.price_deviation_pct:', '        if False:'),
    (PP, "commit-time duplicate check removed", '        if any(x["client_order_id"] == coid and x["account_id"] == acct\n               for x in self.orders.values()):', '        if False:'),
    (PP, "venue ticket not checked", '        if not isinstance(ticket, str) or not hmac.compare_digest(good, ticket):', '        if False:'),
    (PP, "environment check removed", '        if environment != ENVIRONMENT:', '        if False:'),
    (PP, "LIVE- prefix accepted", '        if not isinstance(account_id, str) or account_id.startswith(LIVE_ACCOUNT_PREFIX):', '        if not isinstance(account_id, str):'),
    (PP, "account allowlist removed", '        if account_id not in self.cash:', '        if False:'),
    (PP, "non-PAPER account ids accepted at construction", '            if not isinstance(acct, str) or not acct.startswith(PAPER_ACCOUNT_PREFIX):', '            if False:'),
    (PP, "venue-only states settable by the engine", '        if new in VENUE_ONLY_STATES and not venue_response:', '        if False:'),
    (PP, "illegal transitions allowed", '        if new not in TRANSITIONS[old]:', '        if False:'),
    (PP, "disconnect read as filled", '            self._set_state(order, "UNKNOWN")\n            self.audit.write("submit_unknown"', '            self._set_state(order, "REJECTED", venue_response=True)\n            self.audit.write("submit_unknown"'),
    (PP, "reconcile mismatch does not engage kill switch", '            if not ok:\n                self.kill.engage("AUTOMATION", "reconciliation failure", now)', '            pass'),
    (PP, "cash not reconciled", '                if abs(exp - self.cash[acct]) > 1e-6:', '                if False:'),
    (PP, "filled qty not reconciled", '                    if v and abs(v["filled_qty"] - o["filled_qty"]) > 1e-9:', '                    if False:'),
    (PP, "fills double-counted", '        for f in self.venue.fills[self._fills_seen:]:', '        for f in self.venue.fills[0:]:'),
    (PP, "non-human may disengage the kill switch", '        if principal != "HUMAN":\n            self.audit.write("kill_switch_disengage_refused"', '        if False:\n            self.audit.write("kill_switch_disengage_refused"'),
    (PP, "disengage phrase not checked", '        if confirmation_phrase != self.PHRASE:', '        if False:'),
    (PP, "disengage reason not required", '        if not str(reason or "").strip():\n            raise PaperError("disengaging requires a written reason")', '        if False:\n            pass'),
    (PP, "unreadable kill switch reads as off", '        except (OSError, ValueError):\n            return True', '        except (OSError, ValueError):\n            return False'),
    (PP, "audit chain not verified", '                if rec.get("prev") != prev:', '                if False:'),
    (PP, "audit hash not verified", '                if _sha(json.dumps(rec, sort_keys=True, ensure_ascii=False)) != h:', '                if False:'),
    (PP, "corrupt audit log appended to", '            if not ok:\n                raise PaperError("audit log %s is corrupt', '            if False:\n                raise PaperError("audit log %s is corrupt'),
    (PP, "secrets not redacted", '                out[str(k)] = "[REDACTED]"', '                out[str(k)] = v'),
    (PP, "idempotency key logged in clear", 'idempotency_key_hash=_sha(idem_key)[:16])\n        return dict(order)', 'idempotency_key_hash=idem_key)\n        return dict(order)'),
    (PP, "commit refusals not audited", '                self.audit.write("commit_refused", now,', '                (lambda *a, **k: None)("commit_refused", now,'),
    # The engine lock and the commit-time duplicate check BOTH stop a racing
    # second commit of one preview (MEASURED: removing either alone is caught by
    # the other), so the race test removes both: it must still see one order.
    (PP, "commit not locked AND no commit-time duplicate check (race)", '        with self._lock:\n            try:\n                return self._commit(', '        if True:\n            try:\n                return self._commit('),
    (PP, "kill switch check removed", '        put("kill_switch", not self.kill.engaged(),', '        put("kill_switch", True,'),
    (PP, "allowlist check removed", '        put("instrument_allowlist", inst in L.instrument_allowlist, inst)', '        put("instrument_allowlist", True, inst)'),
    (PP, "future-dated quote counts as fresh", '        put("quote_freshness", 0 <= age <= L.max_quote_age_s,', '        put("quote_freshness", age <= L.max_quote_age_s,'),
    (PP, "session check removed", '        put("trading_session", q.market_status == "OPEN",', '        put("trading_session", True,'),
    (PP, "price deviation removed", '        put("price_deviation", dev <= L.price_deviation_pct,', '        put("price_deviation", True,'),
    (PP, "tick size removed", '        put("tick_size", otype != "limit" or tick is None', '        put("tick_size", True or tick is None'),
    (PP, "lot size removed", '        put("lot_size", lot is None or', '        put("lot_size", True or'),
    (PP, "order notional removed", '        put("order_notional", notional <= L.max_order_notional,', '        put("order_notional", True,'),
    (PP, "daily notional removed", '        put("daily_notional", used + notional <= L.max_daily_notional,', '        put("daily_notional", True,'),
    (PP, "position size removed", '        put("position_size", abs(new_pos) <= L.max_position_qty,', '        put("position_size", True,'),
    (PP, "short sale removed", '        put("short_sale", L.allow_short or not short,', '        put("short_sale", True,'),
    (PP, "buying power removed", '        put("buying_power", not buying or notional + self.venue.fee_per_order <= self.cash[acct],', '        put("buying_power", True,'),
    (PP, "daily loss removed", '        put("daily_loss", loss < L.max_daily_loss,', '        put("daily_loss", True,'),
    (PP, "order rate removed", '        put("order_rate", len(recent) < L.max_orders_per_minute,', '        put("order_rate", True,'),
    (PP, "preview duplicate removed", '        put("duplicate_order", not dup,', '        put("duplicate_order", True,'),
    (PP, "REFUSE preview still gets a token", '            token = secrets.token_urlsafe(16) if ok else None', '            token = secrets.token_urlsafe(16)'),
    (PP, "crossed quote accepted", '        if self.bid > self.ask:', '        if False:'),
    (PP, "fok fills partially", '        if rec["time_in_force"] == "fok" and size < remaining:', '        if False:'),
    (PP, "ioc remainder rests", '        elif rec["time_in_force"] == "ioc":', '        elif False:'),
    (PP, "partial fill reported as filled", '        if rec["filled_qty"] >= rec["quantity"]:', '        if True:'),
    (PP, "UNKNOWN never resolved", '                if o["state"] != "UNKNOWN":\n                    continue', '                if True:\n                    continue'),
]

#: Mutations that change TWO places at once (desc -> (find, repl)).
COMPOUND = {
    "commit not locked AND no commit-time duplicate check (race)": (
        '        if any(x["client_order_id"] == coid and x["account_id"] == acct\n'
        '               for x in self.orders.values()):', '        if False:'),
}


def oracle():
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    try:
        p = subprocess.run([sys.executable, ORACLE], cwd=ROOT, env=env,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=90)
    except subprocess.TimeoutExpired:
        return False
    return p.returncode == 0


def main():
    if not oracle():
        print("ABORT: oracle fails before mutation")
        return 1
    killed = survived = skipped = 0
    surv, skips = [], []
    for i, (f, desc, find, repl) in enumerate(MUTATIONS, 1):
        path = os.path.join(ROOT, f)
        orig = open(path, encoding="utf-8").read()
        extra = COMPOUND.get(desc)
        if extra and orig.count(extra[0]) != 1:
            skipped += 1
            skips.append("%s: %s (compound part missing)" % (f, desc))
            print("  %2d. SKIP     %s" % (i, desc))
            continue
        if orig.count(find) != 1:
            skipped += 1
            skips.append("%s: %s (count=%d)" % (f, desc, orig.count(find)))
            print("  %2d. SKIP     %s" % (i, desc))
            continue
        try:
            mutated = orig.replace(find, repl, 1)
            if extra:
                mutated = mutated.replace(extra[0], extra[1], 1)
            open(path, "w", encoding="utf-8").write(mutated)
            ok = oracle()
        finally:
            open(path, "w", encoding="utf-8").write(orig)
        if ok:
            survived += 1
            surv.append("%s: %s" % (f, desc))
            print("  %2d. SURVIVED %s" % (i, desc))
        else:
            killed += 1
            print("  %2d. killed   %s" % (i, desc))
    intact = oracle()
    print("=" * 70)
    print("  seeded %d  killed %d  survived %d  skipped %d  restored+green %s"
          % (len(MUTATIONS), killed, survived, skipped, intact))
    for s in surv:
        print("  SURVIVOR:", s)
    for s in skips:
        print("  SKIPPED: ", s)
    return 0 if (survived == 0 and skipped == 0 and intact) else 1


if __name__ == "__main__":
    sys.exit(main())
