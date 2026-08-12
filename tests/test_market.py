"""
Verification of the Phase 3A market-data layer (SS.5.5, SS.7.1).

Two things are being verified, and they pull in opposite directions:

  1. A bad price must not become a trusted one. Most assertions are refusals.
  2. A GOOD price must still work. A layer that refuses everything is not safe,
     it is broken -- and it would pass a suite made only of refusals. So the
     positive cases are here too, and they matter just as much.

Every numeric guard below exists because the value passed on first execution.
"""

import datetime
import operator
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "src"))

from _harness import check, check_raises, check_true, section, summary  # noqa: E402

from market.quotes import (ADJUSTMENT_STATUS, DELAY_STATUS,            # noqa: E402
                           MARKET_STATUS, PROVIDERS, Provider, Quote,
                           MarketDataError, VALUE_ORIGINS, WEAK_ORIGINS,
                           assert_provider_usable, enabled_providers,
                           fetch_quote, get_provider, manifest,
                           quote_from_user_input, register_provider)

NOW = datetime.datetime.now(datetime.timezone.utc)


def q(**over):
    """A well-formed provider quote; overrides let each field be broken alone."""
    kw = dict(provider="twelvedata", symbol="AAPL",
              instrument_id="US0378331005", exchange="NASDAQ",
              asset_class="equity", currency="USD", timestamp=NOW,
              timezone="America/New_York", delay_status="REALTIME",
              market_status="OPEN", adjustment_status="ADJUSTED",
              trust_level="EXCHANGE", origin="PROVIDER_API", last=250.10)
    kw.update(over)
    return Quote(**kw)


# ---------------------------------------------------------------------------
section("provider licensing: no provider may be used without a cleared licence")
# ---------------------------------------------------------------------------
# SS.5.5: "Use licensed or otherwise authorized providers for machine-use market
# data." The review (docs/legal/market-data-providers.md, probed 2026-08-12)
# cleared NONE of them, so this is the expected state, not an unfinished one.

check("4 providers reviewed", len(PROVIDERS), 4, 0, "(C)")
check("0 providers enabled", len(enabled_providers()), 0, 0,
      "(C) every candidate is blocked on a question a human must answer")
check_true("every provider is either prohibited or unverified",
           manifest()["n_prohibited"] + manifest()["n_unverified"]
           == len(PROVIDERS), "(C) none is cleared")
check_true("every provider records what its licence says",
           all(p.licence_note for p in PROVIDERS.values()),
           "(C) an unexplained entry is indistinguishable from an unreviewed one")

# The tri-state matters: 'checked and forbidden' needs different follow-up from
# 'could not read the terms'. Collapsing them into False would lose that.
check_true("TradingView is PROHIBITED (False), not merely unknown",
           PROVIDERS["tradingview"].permits_machine_use is False,
           "(V) terms name the prohibition explicitly")
check_true("Twelve Data is UNVERIFIED (None), not permitted",
           PROVIDERS["twelvedata"].permits_machine_use is None,
           "(V) category licensed, tier unverified -- so not True")
check_true("Stooq is UNVERIFIED (None) because terms could not be read",
           PROVIDERS["stooq"].permits_machine_use is None,
           "(V) JS bot gate returned 796 bytes; silence is not permission")

for _key in sorted(PROVIDERS):
    check_raises("assert_provider_usable(%r) refuses" % _key,
                 lambda k=_key: assert_provider_usable(k))
check_raises("an unregistered provider has no reviewed licence",
             lambda: get_provider("bloomberg"))
check_raises("fetch_quote() is not implemented while no licence is cleared",
             lambda: fetch_quote(), NotImplementedError)

# --- a provider cannot be switched on past its own licence -------------------
check_raises("cannot enable a provider whose machine use is PROHIBITED",
             lambda: Provider("x", "X", "u", "t", True, False, "s",
                              "UNVERIFIED", "note"))
check_raises("cannot enable a provider whose machine use is UNVERIFIED",
             lambda: Provider("y", "Y", "u", "t", True, None, "s",
                              "UNVERIFIED", "note"))
check_raises("permits_machine_use must be tri-state, not a truthy string",
             lambda: Provider("z", "Z", "u", "t", False, "yes", "s",
                              "UNVERIFIED", "note"))
check_raises("a provider must record its licence terms",
             lambda: Provider("w", "W", "u", "t", False, None, "s",
                              "UNVERIFIED", ""))

# --- and cannot be edited afterwards -----------------------------------------
check_raises("cannot enable a reviewed provider at runtime",
             lambda: setattr(PROVIDERS["tradingview"], "enabled", True))
check_raises("cannot relabel a prohibited provider as permitted",
             lambda: setattr(PROVIDERS["tradingview"], "permits_machine_use",
                             True))
check_raises("cannot delete a provider's terms",
             lambda: delattr(PROVIDERS["stooq"], "enabled"))
check_raises("cannot inject a provider through PROVIDERS[...]",
             lambda: operator.setitem(PROVIDERS, "new", None), TypeError)
check_raises("cannot overwrite a reviewed provider entry",
             lambda: register_provider(
                 Provider("twelvedata", "TD2", "u", "t", False, None, "s",
                          "UNVERIFIED", "note")))
check_raises("register_provider refuses a non-Provider",
             lambda: register_provider({"key": "fake"}))


# ---------------------------------------------------------------------------
section("quote fields: the SS.5.5 set, and why each one is mandatory")
# ---------------------------------------------------------------------------
# Every field below is a way a price can be wrong while looking right.

check_raises("a price with no exchange is refused",
             lambda: q(exchange=""))
check_raises("a price with no currency is refused",
             lambda: q(currency=""))
check_raises("a price with no timezone is refused",
             lambda: q(timezone=""))
check_raises("a price with no timestamp is refused",
             lambda: q(timestamp=None))
check_raises("an unattributed price is refused",
             lambda: q(provider=""))
check_raises("a price with no symbol is refused", lambda: q(symbol=""))
check_raises("a quote with no bid, ask or last is refused",
             lambda: q(last=None))

# Vocabularies are closed: a value outside them would be silently ignored by
# every consumer, which is worse than a refusal.
check_raises("delay_status outside the vocabulary is refused",
             lambda: q(delay_status="SORTOF"))
check_raises("market_status outside the vocabulary is refused",
             lambda: q(market_status="MAYBE"))
check_raises("adjustment_status outside the vocabulary is refused",
             lambda: q(adjustment_status="PROBABLY"))
check_raises("origin outside the vocabulary is refused",
             lambda: q(origin="TELEPATHY"))
check_raises("trust_level outside the shared vocabulary is refused",
             lambda: q(trust_level="TOTALLY_LEGIT"))
check_true("UNKNOWN is a member of every dangerous vocabulary",
           "UNKNOWN" in DELAY_STATUS and "UNKNOWN" in MARKET_STATUS
           and "UNKNOWN" in ADJUSTMENT_STATUS and "UNKNOWN" in VALUE_ORIGINS,
           "(C) ignorance must be expressible, or it gets guessed")

# --- numeric pathologies: every one of these was ACCEPTED on first execution --
check_raises("NaN price is refused", lambda: q(last=float("nan")))
check_raises("negative price is refused", lambda: q(last=-1.0))
# FOUND BY BOUNDARY PROBE after the adversarial probe reported 45/45 refused.
# inf passes `value < 0`, passes isinstance, and is not NaN.
check_raises("infinite price is refused", lambda: q(last=float("inf")))
check_raises("negative-infinite price is refused",
             lambda: q(last=float("-inf")))
# 0.0 also passes `value < 0`, then divides into every ratio downstream.
check_raises("zero price is refused", lambda: q(last=0.0))
check_raises("zero bid is refused", lambda: q(bid=0.0, ask=5.0, last=None))
check_raises("a bool is not a price", lambda: q(last=True))
check_raises("a string is not a price", lambda: q(last="250.10"))
check_raises("a crossed quote (bid > ask) is refused",
             lambda: q(bid=10.0, ask=9.0, last=None))

# --- and the POSITIVE cases, which matter as much -----------------------------
# A layer that refuses everything would pass every assertion above.
check_true("a well-formed quote constructs", q().last == 250.10, "(C)")
check_true("bid == ask is a valid locked market",
           q(bid=5.0, ask=5.0, last=None).bid == 5.0,
           "(C) not crossed; refusing it would be wrong")
check_true("a bid-only quote is valid", q(bid=5.0, last=None).bid == 5.0, "(C)")
check_true("retrieved_at is stamped when not supplied",
           q().retrieved_at is not None, "(C) SS.5.5 requires it")
check_true("all 21 SS.5.5 fields are present on the record",
           len(q().to_dict()) == 21, "(C) 18 spec fields + origin/note/id")


# ---------------------------------------------------------------------------
section("quotes are evidence: labels cannot be edited after the fact")
# ---------------------------------------------------------------------------
_delayed = q(delay_status="DELAYED")
check_raises("cannot relabel a DELAYED quote as REALTIME",
             lambda: setattr(_delayed, "delay_status", "REALTIME"))
check_raises("cannot relabel a screenshot value as a provider value",
             lambda: setattr(q(origin="VISUALLY_EXTRACTED"), "origin",
                             "PROVIDER_API"))
check_raises("cannot delete a quote's adjustment status",
             lambda: delattr(_delayed, "adjustment_status"))


# ---------------------------------------------------------------------------
section("weak origins: SS.7.1 Level 3 labels have consequences")
# ---------------------------------------------------------------------------
# "Screenshot-derived values must be labeled ... Unsuitable as sole evidence for
# material calculations ... Unsuitable as authoritative live-order data."
# A label nothing checks is decoration -- exactly what Phase 3 found in
# sources.py -- so these assert the label is ENFORCED.

check_true("VISUALLY_EXTRACTED is a weak origin",
           "VISUALLY_EXTRACTED" in WEAK_ORIGINS, "(C) SS.7.1 Level 3")
check_true("USER_SUPPLIED is a weak origin",
           "USER_SUPPLIED" in WEAK_ORIGINS,
           "(C) a hand-typed number has no provenance a machine can check")

_vis = q(origin="VISUALLY_EXTRACTED", trust_level="UNVERIFIED")
check_true("a screenshot value is weak", _vis.is_weak, "(C)")
check_raises("a screenshot value cannot price a live order",
             lambda: _vis.assert_usable_for("live_order"))
check_raises("a screenshot value cannot be sole evidence for a material calc",
             lambda: _vis.assert_usable_for("material_calculation"))
check_true("a screenshot value MAY still be displayed to a human",
           _vis.assert_usable_for("display") is None,
           "(C) SS.7.1 Level 3 restricts reliance, not visibility")

_user = quote_from_user_input("AAPL", "NASDAQ", "USD", NOW,
                              "America/New_York", last=250.10)
check_true("a user-supplied price gets no unearned credibility",
           _user.origin == "USER_SUPPLIED" and _user.trust_level == "UNVERIFIED"
           and _user.is_weak, "(C) SS.7.1 Level 0 needs no licence, and earns no trust")
check_raises("a user-supplied price cannot price a live order",
             lambda: _user.assert_usable_for("live_order"))

# MUTATION SURVIVOR (mutate_market.py #45): changing the user-input defaults from
# UNKNOWN to REALTIME/OPEN left this suite green, because every assertion above
# refuses the quote via is_weak and never looks at its freshness labels. A caller
# who supplied a bid/ask from a provider CSV by hand would then get a quote
# claiming to be realtime from an open market on no evidence at all. The labels
# must be asserted directly, not inferred from a refusal that happens for an
# unrelated reason.
check_true("a hand-typed price claims nothing about freshness",
           _user.delay_status == "UNKNOWN" and _user.market_status == "UNKNOWN",
           "(C) the user said a number, not that the market was open")
check_true("a hand-typed price is therefore never live",
           not _user.is_live,
           "(C) is_live must not be reachable by omission")
check_raises("an unrecognised purpose is not assumed permitted",
             lambda: q().assert_usable_for("whatever"))
check_raises("purpose must be stated", lambda: q().assert_usable_for(""))


# ---------------------------------------------------------------------------
section("staleness: a live order needs a live price")
# ---------------------------------------------------------------------------
# is_live requires BOTH conditions, because either alone misleads: a REALTIME
# quote from a CLOSED market is a stale last price, and an OPEN market says
# nothing about whether THIS number is delayed.

check_true("REALTIME + OPEN is live", q().is_live, "(C)")
check_true("REALTIME + CLOSED is NOT live",
           not q(market_status="CLOSED").is_live,
           "(C) a realtime feed of a closed market is a stale last price")
check_true("DELAYED + OPEN is NOT live",
           not q(delay_status="DELAYED").is_live,
           "(C) an open market says nothing about this number's freshness")

for _d, _m in (("DELAYED", "OPEN"), ("REALTIME", "CLOSED"),
               ("END_OF_DAY", "CLOSED"), ("UNKNOWN", "UNKNOWN"),
               ("REALTIME", "HALTED")):
    check_raises("delay=%s market=%s cannot price a live order" % (_d, _m),
                 lambda d=_d, m=_m: q(delay_status=d, market_status=m
                                      ).assert_usable_for("live_order"))

# The positive case: a genuinely live provider quote IS usable. Without this,
# every assertion above would pass on a function that always raised.
check_true("a REALTIME/OPEN provider quote CAN price a live order",
           q().assert_usable_for("live_order") is None,
           "(C) the layer discriminates rather than refusing everything")
check_true("a delayed quote is still fine for a material calculation",
           q(delay_status="DELAYED", market_status="CLOSED"
             ).assert_usable_for("material_calculation") is None,
           "(C) staleness bars orders, not analysis; the origin is what matters")


# ---------------------------------------------------------------------------
section("the licence gate refuses for the RIGHT reason")
# ---------------------------------------------------------------------------
# MUTATION SURVIVORS (mutate_market.py #2, #3, #4). assert_provider_usable has
# three independent guards -- PROHIBITED, UNVERIFIED, and not-enabled -- and the
# loop above asserted only THAT each of the four providers raises. Deleting any
# one guard left the suite green, because the next guard raised instead and
# check_raises cannot tell two different refusals apart.
#
# That is not a cosmetic gap. Guard 3 is the one that stops a provider whose
# licence HAS been cleared from being queried before someone deliberately
# switches it on, and no registered provider currently reaches it: all four trip
# guard 1 or 2 first, so guard 3 was entirely unexecuted code. A future
# maintainer who clears Twelve Data's tier would be relying on it immediately.
#
# So: assert the message names the actual reason, and construct the one provider
# state that reaches the third guard.

def _why(key):
    try:
        assert_provider_usable(key)
    except MarketDataError as exc:
        return str(exc)
    return "DID NOT RAISE"


check_true("tradingview is refused as PROHIBITED, not as merely disabled",
           "PROHIBITS machine use" in _why("tradingview"),
           "(D) the reason is the finding; a generic refusal hides it")
check_true("twelvedata is refused as UNVERIFIED, naming the blocking question",
           "UNVERIFIED" in _why("twelvedata")
           and "subscription tier" in _why("twelvedata"),
           "(D) an unverified licence is a question, not a prohibition")
check_true("alpha_vantage is refused as UNVERIFIED, naming its own question",
           "UNVERIFIED" in _why("alpha_vantage")
           and "affiliated" in _why("alpha_vantage"),
           "(D) the exclusion turns on a fact about the user")

# The third guard: licence cleared, but not switched on. Registered last so the
# provider counts asserted at the top of this suite are unaffected.
register_provider(Provider(
    key="_test_cleared_but_off",
    name="synthetic fixture: licence cleared, deliberately not enabled",
    base_url="https://example.invalid",
    terms_url="https://example.invalid/terms",
    enabled=False,
    permits_machine_use=True,
    status="fixture for the not-enabled guard; not a real provider",
    trust_level="UNVERIFIED",
    licence_note="Synthetic. Exists so that the third guard of "
                 "assert_provider_usable is executed by the suite at all."))
check_raises("a provider whose licence IS cleared still refuses until enabled",
             lambda: assert_provider_usable("_test_cleared_but_off"))
check_true("...and it refuses for being disabled, not for its licence",
           "not enabled" in _why("_test_cleared_but_off"),
           "(D) permission to use data is not permission to have switched it on")
check_true("a cleared-but-disabled provider still does not count as enabled",
           len(enabled_providers()) == 0,
           "(C) enabled_providers() reflects the flag, not the licence")

sys.exit(summary())
