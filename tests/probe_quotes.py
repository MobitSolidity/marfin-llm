"""
Adversarial probe of the market-data layer.

First execution of quotes.py. Phase 3 found three live exploits on sources.py's
first run, so the assumption here is that this module is broken until proven
otherwise. I am looking for the ways a bad price becomes a trusted one:

  - a provider switched on whose licence was never cleared
  - a weak value (screenshot, hand-typed) used to price a live order
  - a delayed quote relabelled as realtime after the fact
  - a NaN or crossed quote entering a calculation
  - a price with no currency, exchange, or timezone

Run:  python3 tests/probe_quotes.py
"""

import datetime
import operator
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from market import quotes as q

# The project's refusal convention (tests/_harness.py). A crash is not a refusal.
REFUSALS = (ValueError, TypeError, ZeroDivisionError)
NOW = datetime.datetime.now(datetime.timezone.utc)


def attempt(label, fn):
    try:
        result = fn()
    except NotImplementedError as exc:
        print("  REFUSED (NotImpl)  %-50s %s" % (label, str(exc)[:60]))
        return "refused"
    except REFUSALS as exc:
        print("  REFUSED (%-9s %-50s %s"
              % (type(exc).__name__ + ")", label, str(exc).split("\n")[0][:62]))
        return "refused"
    except Exception as exc:
        print("  !! CRASHED         %-50s %s: %s"
              % (label, type(exc).__name__, str(exc)[:55]))
        return "crashed"
    print("  ** ALLOWED         %-50s -> %r" % (label, result))
    return "allowed"


def good(**over):
    """A well-formed provider quote, so mutations are tested one at a time."""
    kw = dict(provider="p", symbol="AAPL", instrument_id="US0378331005",
              exchange="NASDAQ", asset_class="equity", currency="USD",
              timestamp=NOW, timezone="America/New_York",
              delay_status="REALTIME", market_status="OPEN",
              adjustment_status="ADJUSTED", trust_level="EXCHANGE",
              origin="PROVIDER_API", last=250.10)
    kw.update(over)
    return q.Quote(**kw)


def main():
    print("=" * 78)
    print("PROBE: market data layer -- can a bad price become a trusted one?")
    print("=" * 78)
    out = []

    print("\n1. Provider licensing: can an uncleared provider be used?")
    print("   registered=%d enabled=%d" % (len(q.PROVIDERS), len(q.enabled_providers())))
    # Until 2026-08-14 every provider was disabled, so this loop could demand
    # that ALL of them be refused. Alpha Vantage is now enabled on
    # USER_ACCEPTED_RISK, and weakening the loop to "some may pass" would have
    # thrown away the check. Instead the two cases are separated and each is
    # asserted on its own terms: a DISABLED provider must be refused, and an
    # ENABLED one must be refused for everything its tier cannot lawfully do.
    for key in sorted(q.PROVIDERS):
        p = q.get_provider(key)
        if not p.enabled:
            out.append(attempt("assert_provider_usable(%r)" % key,
                               lambda k=key: q.assert_provider_usable(k)))
            continue
        # An enabled provider is allowed through this gate BY DESIGN. What must
        # still be impossible is using it beyond its licence, so the attack
        # moves to the tier boundary -- which is where the real risk now lives.
        for bad in ("REALTIME", "DELAYED"):
            out.append(attempt(
                "%s tier asked for %s data" % (key, bad),
                lambda k=key, d=bad: q.assert_tier_supports(k, d)))
    out.append(attempt("get_provider('bloomberg') (unregistered)",
                       lambda: q.get_provider("bloomberg")))
    out.append(attempt("fetch_quote()", lambda: q.fetch_quote()))

    print("\n2. Can a provider be ENABLED without a cleared licence?")
    out.append(attempt("Provider(enabled=True, machine_use=False)",
                       lambda: q.Provider("x", "X", "u", "t", True, False,
                                          "s", "UNVERIFIED", "note")))
    out.append(attempt("Provider(enabled=True, machine_use=None)",
                       lambda: q.Provider("y", "Y", "u", "t", True, None,
                                          "s", "UNVERIFIED", "note")))
    out.append(attempt("Provider(machine_use='yes') (not tri-state)",
                       lambda: q.Provider("z", "Z", "u", "t", False, "yes",
                                          "s", "UNVERIFIED", "note")))
    out.append(attempt("Provider(licence_note='') unexplained",
                       lambda: q.Provider("w", "W", "u", "t", False, None,
                                          "s", "UNVERIFIED", "")))

    print("\n3. Can a reviewed provider be edited at runtime?")
    out.append(attempt("PROVIDERS['tradingview'].enabled = True",
                       lambda: setattr(q.PROVIDERS["tradingview"], "enabled", True)))
    out.append(attempt("PROVIDERS['tradingview'].permits_machine_use = True",
                       lambda: setattr(q.PROVIDERS["tradingview"],
                                       "permits_machine_use", True)))
    out.append(attempt("del PROVIDERS['stooq'].enabled",
                       lambda: delattr(q.PROVIDERS["stooq"], "enabled")))
    out.append(attempt("PROVIDERS['new'] = ... (mappingproxy)",
                       lambda: operator.setitem(q.PROVIDERS, "new", None)))
    out.append(attempt("register_provider re-registers 'twelvedata'",
                       lambda: q.register_provider(
                           q.Provider("twelvedata", "TD2", "u", "t", False,
                                      None, "s", "UNVERIFIED", "note"))))
    out.append(attempt("register_provider({}) non-Provider",
                       lambda: q.register_provider({"key": "fake"})))

    print("\n4. A weak value used where it must not be.")
    user_q = q.quote_from_user_input("AAPL", "NASDAQ", "USD", NOW,
                                     "America/New_York", last=250.10)
    print("   user quote: is_weak=%s is_live=%s origin=%s trust=%s"
          % (user_q.is_weak, user_q.is_live, user_q.origin, user_q.trust_level))
    out.append(attempt("user-supplied price -> live_order",
                       lambda: user_q.assert_usable_for("live_order")))
    out.append(attempt("user-supplied price -> material_calculation",
                       lambda: user_q.assert_usable_for("material_calculation")))
    vis = good(origin="VISUALLY_EXTRACTED", trust_level="UNVERIFIED")
    out.append(attempt("screenshot price -> live_order",
                       lambda: vis.assert_usable_for("live_order")))
    out.append(attempt("screenshot price -> material_calculation",
                       lambda: vis.assert_usable_for("material_calculation")))
    out.append(attempt("unknown purpose is not assumed permitted",
                       lambda: good().assert_usable_for("whatever")))

    print("\n5. A stale price used for a live order.")
    for delay, mkt in (("DELAYED", "OPEN"), ("REALTIME", "CLOSED"),
                       ("END_OF_DAY", "CLOSED"), ("UNKNOWN", "UNKNOWN")):
        out.append(attempt("delay=%s market=%s -> live_order" % (delay, mkt),
                           lambda d=delay, m=mkt: good(
                               delay_status=d, market_status=m
                           ).assert_usable_for("live_order")))

    print("\n6. Can a quote's labels be edited after the fact?")
    fixed = good(delay_status="DELAYED", market_status="OPEN")
    out.append(attempt("quote.delay_status = 'REALTIME'",
                       lambda: setattr(fixed, "delay_status", "REALTIME")))
    out.append(attempt("quote.origin = 'PROVIDER_API'",
                       lambda: setattr(vis, "origin", "PROVIDER_API")))
    out.append(attempt("del quote.adjustment_status",
                       lambda: delattr(fixed, "adjustment_status")))

    print("\n7. Malformed prices that must never construct.")
    cases = [
        ("crossed quote (bid > ask)", dict(bid=10.0, ask=9.0, last=None)),
        ("NaN last", dict(last=float("nan"))),
        ("negative last", dict(last=-1.0)),
        # These two were ACCEPTED on first execution, after this probe had
        # already reported 45/45 refused. inf passes `value < 0`, passes
        # isinstance, and is not NaN; 0.0 passes `value < 0` too. Both then
        # propagate through arithmetic producing results that look computed.
        # Probing only the pathologies I thought of first is how they survived.
        ("infinite last", dict(last=float("inf"))),
        ("negative-infinite last", dict(last=float("-inf"))),
        ("zero last", dict(last=0.0)),
        ("zero bid", dict(bid=0.0, ask=5.0, last=None)),
        ("bool as price", dict(last=True)),
        ("string as price", dict(last="250.10")),
        ("no bid/ask/last at all", dict(last=None)),
        ("no exchange", dict(exchange="")),
        ("no currency", dict(currency="")),
        ("no timezone", dict(timezone="")),
        ("no timestamp", dict(timestamp=None)),
        ("no provider", dict(provider="")),
        ("no symbol", dict(symbol="")),
        ("bad delay_status", dict(delay_status="SORTOF")),
        ("bad market_status", dict(market_status="MAYBE")),
        ("bad adjustment_status", dict(adjustment_status="PROBABLY")),
        ("bad origin", dict(origin="TELEPATHY")),
        ("bad trust_level", dict(trust_level="TOTALLY_LEGIT")),
    ]
    for label, over in cases:
        out.append(attempt(label, lambda o=over: good(**o)))

    print("\n8. Invariants.")
    ok = True
    # This invariant used to be "enabled == 0", which was true and meaningful
    # while every candidate was blocked. It is now the wrong shape rather than
    # merely the wrong number, so it is replaced by the property that actually
    # matters: every ENABLED provider must record WHY, and anything enabled
    # without a licence must carry the weakest trust label plus an owned,
    # dated, non-empty list of what the user accepted.
    n_enabled = len(q.enabled_providers())
    risk_based = q.user_accepted_risk_providers()
    print("   enabled_providers()          -> %d (%d on USER_ACCEPTED_RISK)"
          % (n_enabled, len(risk_based)))
    for p in q.enabled_providers():
        ok = ok and p.activation_basis in q.ACTIVATION_BASES
        if p.activation_basis == "USER_ACCEPTED_RISK":
            # permits_machine_use must stay None. Flipping it to True to unlock
            # the enable guard would record a permission no document grants.
            good_record = (p.permits_machine_use is None
                           and p.trust_level == "UNVERIFIED"
                           and len(p.accepted_risks) >= 3
                           and bool(p.decided_by) and bool(p.decided_on))
            print("   %-14s basis=%s machine_use=%s trust=%s risks=%d "
                  "owner=%s -> %s"
                  % (p.key, p.activation_basis, p.permits_machine_use,
                     p.trust_level, len(p.accepted_risks),
                     bool(p.decided_by), "ok" if good_record else "BROKEN"))
            ok = ok and good_record
    m = q.manifest()
    print("   prohibited=%d unverified=%d of %d"
          % (m["n_prohibited"], m["n_unverified"], len(q.PROVIDERS)))
    # No provider may claim a cleared licence unless one was actually read.
    ok = ok and m["n_prohibited"] + m["n_unverified"] == len(q.PROVIDERS)
    gq = good()
    print("   good quote is_live=%s is_weak=%s" % (gq.is_live, gq.is_weak))
    ok = ok and gq.is_live is True and gq.is_weak is False
    try:
        gq.assert_usable_for("live_order")
        print("   a REALTIME/OPEN provider quote IS usable for a live order: yes")
    except Exception as exc:
        print("   !! a valid live quote was refused: %s" % exc)
        ok = False

    print("\n" + "=" * 78)
    allowed, crashed = out.count("allowed"), out.count("crashed")
    print("attempts=%d refused=%d ALLOWED=%d CRASHED=%d invariants=%s"
          % (len(out), out.count("refused"), allowed, crashed,
             "OK" if ok else "BROKEN"))
    if allowed or crashed or not ok:
        print("RESULT: defects present. Fix before proceeding.")
        return 1
    print("RESULT: all refused as refusals; a valid live quote still works.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
