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

from market.quotes import (ACTIVATION_BASES, ADJUSTMENT_STATUS,        # noqa: E402
                           DELAY_STATUS,
                           MARKET_STATUS, PROVIDERS, Provider, Quote,
                           MarketDataError, VALUE_ORIGINS, WEAK_ORIGINS,
                           FREE_TIER_LIMITS,
                           assert_provider_usable, assert_tier_supports,
                           enabled_providers,
                           fetch_quote, get_provider, manifest,
                           quote_from_user_input, register_provider,
                           user_accepted_risk_providers)

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
# From 2026-08-12 to 2026-08-14 this read `== 0`, and that was the honest state:
# every candidate was blocked on a question only the user could answer. On
# 2026-08-14 the user answered both -- no institutional affiliation (clearing
# Alpha Vantage criterion iv) and unwilling to pay (closing Twelve Data). So
# exactly one provider is enabled, and the assertion changes SHAPE rather than
# just its number: what must hold now is that anything enabled records WHY.
check("1 provider enabled", len(enabled_providers()), 1, 0,
      "(C) alpha_vantage, on USER_ACCEPTED_RISK -- not on a licence grant")
check_true("every enabled provider records an activation basis",
           all(p.activation_basis in ACTIVATION_BASES
               for p in enabled_providers()),
           "(D) a provider that is on without saying why makes a licence grant "
           "and a human's accepted risk look identical")
check_true("every provider is STILL either prohibited or unverified",
           manifest()["n_prohibited"] + manifest()["n_unverified"]
           == len(PROVIDERS),
           "(C) enabling alpha_vantage did NOT claim its licence was cleared: "
           "permits_machine_use stays None because the terms are silent")
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

# Until 2026-08-14 this loop asserted that ALL FOUR refuse, which was true and
# is now false for exactly one of them. The temptation is to drop the enabled
# provider from the loop, and that would quietly reduce the coverage: the loop
# would then only ever visit providers that were going to refuse anyway. So the
# enabled case is not skipped, it is asserted POSITIVELY -- it must pass this
# gate and be refused at the next one. A provider that passes both would be a
# finding.
for _key in sorted(PROVIDERS):
    if not PROVIDERS[_key].enabled:
        check_raises("assert_provider_usable(%r) refuses" % _key,
                     lambda k=_key: assert_provider_usable(k))
        continue
    check_true("assert_provider_usable(%r) returns the provider itself" % _key,
               assert_provider_usable(_key) is PROVIDERS[_key],
               "(D) enabled BY DESIGN; returning a different object would let "
               "a caller act on settings other than the reviewed ones")
    check_raises("...but %r is still refused for REALTIME data" % _key,
                 lambda k=_key: assert_tier_supports(k, "REALTIME"))
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


# `_mat_why` is defined here, above its first use, rather than beside the other
# `_why` helpers further down: the material_calculation branch now has TWO
# independent guards, and telling them apart requires reading the message from
# this section onward.
def _mat_why(quote):
    try:
        quote.assert_usable_for("material_calculation")
    except MarketDataError as exc:
        return str(exc)
    return "DID NOT RAISE"


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

# MUTATION SURVIVOR (mutate_market.py #42), and this one I CAUSED. On 2026-08-14
# a second guard was added to the material_calculation branch -- the trust-level
# check -- and _vis above carries trust_level=UNVERIFIED, which the new guard
# also refuses. So deleting the `is_weak` guard entirely left the suite green:
# the new neighbour answered in its place, and check_raises could not tell them
# apart. The fix that closed a real defect opened a test gap in the same edit.
#
# MEASURED across all 15 trust x origin combinations: VISUALLY_EXTRACTED with
# trust_level=EXCHANGE (score 80) passes the trust guard and reaches the is_weak
# guard ALONE. That combination is legitimate -- a screenshot OF an exchange
# terminal is exactly SS.7.1 Level 3 -- so it is a fair fixture, not a contrived
# one, and it is the only shape that discriminates.
_vis_high = q(origin="VISUALLY_EXTRACTED", trust_level="EXCHANGE")
check_true("a screenshot of an EXCHANGE terminal is still weak by ORIGIN",
           _vis_high.is_weak and _vis_high.trust_level == "EXCHANGE",
           "(C) how it arrived and how authoritative it is are separate axes")
check_raises("...and is STILL refused as sole evidence for a material calc",
             lambda: _vis_high.assert_usable_for("material_calculation"))
check_true("...refused BY THE ORIGIN guard, naming the origin, not the trust",
           "is VISUALLY_EXTRACTED and is unsuitable" in _mat_why(_vis_high)
           and "trust_level=" not in _mat_why(_vis_high),
           "(D) if the trust guard answers here, the origin guard is untested "
           "and could be deleted unnoticed")
check_true("...and the reverse case is refused by the TRUST guard alone",
           "trust_level=UNVERIFIED" in _mat_why(
               q(origin="PROVIDER_API", trust_level="UNVERIFIED"))
           and "unsuitable as SOLE evidence" not in _mat_why(
               q(origin="PROVIDER_API", trust_level="UNVERIFIED")),
           "(D) the two guards are now proved independent, in both directions")

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


# Two more of the same shape. Each returns the refusal MESSAGE, because a bare
# check_raises cannot tell one guard from another -- the failure mode that
# produced this whole section. Only MarketDataError is caught: any other
# exception must escape and crash the suite rather than be silently reshaped
# into a string that happens not to contain the expected phrase. A non-raise
# returns the sentinel, which contains no expected phrase and so FAILS loudly
# instead of reading as a pass.

def _tier_why(delay_status, key="alpha_vantage"):
    try:
        assert_tier_supports(key, delay_status)
    except MarketDataError as exc:
        return str(exc)
    return "DID NOT RAISE"


def _prov_why(**over):
    """The refusal message from CONSTRUCTING a provider, not from using one.

    Nine mutations survived this suite on 2026-08-14 for one reason: the
    activation guards were asserted with check_raises only, and five of them
    raise from the same constructor. check_raises cannot tell which one fired,
    so deleting any single guard left a neighbour to raise in its place and the
    suite stayed green. Every assertion built on this helper names the guard by
    its own words.
    """
    kw = dict(key="_probe", name="synthetic probe",
              base_url="https://example.invalid",
              terms_url="https://example.invalid/terms", enabled=True,
              permits_machine_use=None, status="fixture",
              trust_level="UNVERIFIED", licence_note="Synthetic fixture.")
    kw.update(over)
    try:
        Provider(**kw)
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
# alpha_vantage used to be refused here for the same reason as twelvedata. The
# user's 2026-08-14 answer cleared exclusion criterion (iv), so it now passes
# this gate -- and the checks move to what must STILL be impossible.
_av = get_provider("alpha_vantage")
check_true("alpha_vantage now passes the licence gate",
           assert_provider_usable("alpha_vantage") is _av,
           "(D) enabled on USER_ACCEPTED_RISK after the user answered")
check_true("...but its licence position is STILL recorded as unknown",
           _av.permits_machine_use is None,
           "(D) 'non-display' appears 0 times in its terms; silence is not a "
           "grant, and recording True would be a falsehood")
check_true("...and its quotes carry the WEAKEST trust label",
           _av.trust_level == "UNVERIFIED",
           "(D) a source enabled on accepted risk must not outrank one whose "
           "terms were actually read")
check_true("...and what the user accepted is recorded, owned and dated",
           len(_av.accepted_risks) >= 3 and _av.decided_by and _av.decided_on,
           "(D) an accepted risk with no content, owner or date is "
           "indistinguishable from a default")
check_true("the free tier is REFUSED for realtime data",
           "not licensed to supply REALTIME" in _tier_why("REALTIME"),
           "(D) MEASURED: realtime/15-min is exchange-regulated, premium-only")
check_true("the free tier is REFUSED for 15-minute delayed data",
           "not licensed to supply DELAYED" in _tier_why("DELAYED"))
check_true("the free tier IS permitted end-of-day data",
           assert_tier_supports("alpha_vantage", "END_OF_DAY") is None)

# A user may accept an UNKNOWN. A user may NOT consent past a PROHIBITION: that
# is the line between assuming a risk and breaching someone else's contract.
check_raises("a PROHIBITED provider cannot be enabled on USER_ACCEPTED_RISK",
             lambda: Provider(
                 key="_test_consent_past_prohibition",
                 name="synthetic: tries to consent past a prohibition",
                 base_url="https://example.invalid",
                 terms_url="https://example.invalid/terms",
                 enabled=True, permits_machine_use=False,
                 status="fixture", trust_level="UNVERIFIED",
                 licence_note="Synthetic fixture.",
                 activation_basis="USER_ACCEPTED_RISK",
                 accepted_risks=("a", "b", "c"), decided_by="x",
                 decided_on="2026-08-14"))
check_raises("an enabled provider with NO activation basis is refused",
             lambda: Provider(
                 key="_test_no_basis", name="synthetic",
                 base_url="https://example.invalid",
                 terms_url="https://example.invalid/terms",
                 enabled=True, permits_machine_use=True,
                 status="fixture", trust_level="UNVERIFIED",
                 licence_note="Synthetic fixture."))
check_raises("USER_ACCEPTED_RISK with an EMPTY risk list is refused",
             lambda: Provider(
                 key="_test_empty_risks", name="synthetic",
                 base_url="https://example.invalid",
                 terms_url="https://example.invalid/terms",
                 enabled=True, permits_machine_use=None,
                 status="fixture", trust_level="UNVERIFIED",
                 licence_note="Synthetic fixture.",
                 activation_basis="USER_ACCEPTED_RISK",
                 accepted_risks=(), decided_by="x", decided_on="2026-08-14"))
check_raises("USER_ACCEPTED_RISK with no owner or date is refused",
             lambda: Provider(
                 key="_test_no_owner", name="synthetic",
                 base_url="https://example.invalid",
                 terms_url="https://example.invalid/terms",
                 enabled=True, permits_machine_use=None,
                 status="fixture", trust_level="UNVERIFIED",
                 licence_note="Synthetic fixture.",
                 activation_basis="USER_ACCEPTED_RISK",
                 accepted_risks=("a", "b", "c"), decided_by="",
                 decided_on=""))
check_raises("a DISABLED provider carrying an activation basis is refused",
             lambda: Provider(
                 key="_test_off_with_basis", name="synthetic",
                 base_url="https://example.invalid",
                 terms_url="https://example.invalid/terms",
                 enabled=False, permits_machine_use=None,
                 status="fixture", trust_level="UNVERIFIED",
                 licence_note="Synthetic fixture.",
                 activation_basis="LICENCE_EXPLICIT"))

# --- the guards those five check_raises calls could not tell apart -----------
# MUTATION SURVIVORS (mutate_market.py #50, #55, #56, #57, #58, #60, #62, #65).
# Every one of the activation guards was covered above by check_raises alone,
# and MEASURED: each guard could be deleted individually while the suite stayed
# green, because a neighbouring guard raised from the same constructor. The
# assertions below each name a guard by its message, and the fixtures are chosen
# so that exactly one guard can possibly answer.

# #50: LICENCE_EXPLICIT must NOT unlock a provider whose terms are silent. This
# is the whole point of having two names: if any basis opens the gate, then
# "LICENCE_EXPLICIT" is a phrase someone can type having read nothing. The
# fixture carries a COMPLETE risk record, so the empty-list and owner/date
# guards cannot be the ones refusing.
_wrong_basis = _prov_why(activation_basis="LICENCE_EXPLICIT",
                         accepted_risks=("a", "b", "c"), decided_by="x",
                         decided_on="2026-08-14")
check_true("claiming LICENCE_EXPLICIT over SILENT terms is refused",
           "machine use is UNVERIFIED" in _wrong_basis
           and "activation_basis is 'LICENCE_EXPLICIT'" in _wrong_basis,
           "(D) the refusal names BOTH the licence state and the claimed basis; "
           "only USER_ACCEPTED_RISK covers silence")

# #55: owner and date are required TOGETHER. `or` -> `and` still refuses the
# both-missing case, so a fixture missing both cannot detect it. Each is
# therefore omitted ALONE.
_no_date = _prov_why(activation_basis="USER_ACCEPTED_RISK",
                     accepted_risks=("a", "b", "c"), decided_by="x",
                     decided_on="")
_no_owner = _prov_why(activation_basis="USER_ACCEPTED_RISK",
                      accepted_risks=("a", "b", "c"), decided_by="",
                      decided_on="2026-08-14")
check_true("a risk record with an owner but NO DATE is refused",
           "without decided_by and decided_on" in _no_date, _no_date[:100])
check_true("a risk record with a date but NO OWNER is refused",
           "without decided_by and decided_on" in _no_owner, _no_owner[:100])

# #56: the vocabulary must be closed. permits_machine_use=True is used here on
# purpose: it skips every later guard, so the vocabulary check is the only thing
# that can refuse. With permits=None a neighbour would answer and mask it.
_bad_vocab = _prov_why(permits_machine_use=True, activation_basis="NONSENSE")
check_true("an activation_basis outside the vocabulary is refused",
           "activation_basis must be one of" in _bad_vocab,
           "(D) an open vocabulary lets a typo read as an authorization")

# #57: the accepted record must not be editable after it was approved. A list
# would let a risk be appended later and look original.
_av_risks = get_provider("alpha_vantage").accepted_risks
check_true("the accepted-risk record is a tuple, not a list",
           isinstance(_av_risks, tuple),
           "(D) MEASURED: a list accepts .append(), so what the user agreed to "
           "could be added to afterwards with no trace")
check_raises("the accepted-risk record cannot be appended to",
             lambda: _av_risks.append("smuggled in after approval"),
             AttributeError)

# #58: a report that cannot enumerate the weakly-authorized providers cannot
# warn anyone about them. Asserted by MEMBERSHIP, not by count.
check_true("the weakly-authorized providers can be enumerated",
           [p.key for p in user_accepted_risk_providers()] == ["alpha_vantage"],
           "(D) returning [] would be a silent all-clear")
check_true("...and every provider it lists really is on that basis",
           all(p.activation_basis == "USER_ACCEPTED_RISK" and p.enabled
               for p in user_accepted_risk_providers()),
           "(C) the list must not be a hardcoded name")

# #60: the delay_status vocabulary check runs BEFORE the per-provider lookup, so
# a nonsense label is refused even for a provider with no recorded limits --
# otherwise an unknown provider key would silently permit anything.
check_true("a nonsense delay_status is refused for a LIMITED provider",
           "unknown delay_status" in _tier_why("NONSENSE"),
           "(D) MEASURED phrase")
check_true("...and also for a provider with NO recorded tier limits",
           "unknown delay_status" in _tier_why("NONSENSE", key="twelvedata"),
           "(D) the vocabulary check must precede the lookup, or the absence of "
           "limits would read as the absence of rules")
check_true("...and for a provider that is not registered at all",
           "unknown delay_status" in _tier_why("NONSENSE", key="nosuchprovider"),
           "(D) an unknown key must not be the quiet way past the gate")

# #62: the daily budget is a MEASURED number, quoted from the provider. A
# mutation inflating 25 to 2500 survived, i.e. nothing asserted the figure.
check("the measured free-tier budget is 25 requests per day",
      FREE_TIER_LIMITS["alpha_vantage"]["requests_per_day"], 25, 0,
      "(V) quoted: '25 API requests per day' -- alphavantage.co/support/, "
      "probed 2026-08-14. Not 25 per minute")
check_true("...and it is recorded with the source it was measured from",
           "alphavantage.co" in FREE_TIER_LIMITS["alpha_vantage"]["source"],
           "(D) an unsourced number cannot be re-checked when the tier changes")

# #65: `.get(label, 0)` vs `.get(label, 100)` -- what an UNRECOGNISED trust
# level scores. The constructor refuses 7 different bad labels (MEASURED), so
# the only route to the gate is object.__setattr__, which bypasses the
# immutability guard. That route is used here deliberately: it is the one way
# the fail-open default is reachable, and an unreachable branch cannot be
# claimed as tested.
_forged = Quote(provider="alpha_vantage", symbol="IBM", instrument_id=None,
                exchange="NYSE", asset_class=None, currency="USD",
                timestamp=datetime.datetime(2026, 8, 13, 16, 0,
                                            tzinfo=datetime.timezone.utc),
                timezone="US/Eastern", delay_status="END_OF_DAY",
                market_status="UNKNOWN", adjustment_status="UNADJUSTED",
                trust_level="UNVERIFIED", origin="PROVIDER_API", last=237.14)
check_raises("a forged trust level cannot be set the normal way",
             lambda: setattr(_forged, "trust_level", "MADE_UP"))
object.__setattr__(_forged, "trust_level", "MADE_UP")
check_raises("an UNRECOGNISED trust level is treated as untrusted, not trusted",
             lambda: _forged.assert_usable_for("material_calculation"))
check_true("...and the refusal names the unrecognised label and a score of 0",
           "trust_level=MADE_UP" in _mat_why(_forged)
           and "score 0" in _mat_why(_forged),
           "(D) defaulting an unknown label to a HIGH score would make a typo "
           "in a trust label the most trusted value in the system")

# The latent defect this activation exposed. Until a provider was enabled, no
# quote in the project had origin=PROVIDER_API with trust_level=UNVERIFIED, so
# the material-calculation gate was never exercised on that combination --
# and MEASURED, it let ALL SIX trust levels through, including UNVERIFIED,
# which rag.documents defines as "never citable as fact".
_unv = Quote(provider="alpha_vantage", symbol="IBM", instrument_id=None,
             exchange="NYSE", asset_class=None, currency="USD",
             timestamp=datetime.datetime(2026, 8, 13, 16, 0,
                                         tzinfo=datetime.timezone.utc),
             timezone="US/Eastern", delay_status="END_OF_DAY",
             market_status="UNKNOWN", adjustment_status="UNADJUSTED",
             trust_level="UNVERIFIED", origin="PROVIDER_API", last=237.14)
check_true("a PROVIDER_API quote is not 'weak' by origin",
           _unv.is_weak is False,
           "(C) the path was clean; that is a separate axis from authority")
check_raises("...but an UNVERIFIED quote still cannot be SOLE evidence for a "
             "material calculation",
             lambda: _unv.assert_usable_for("material_calculation"))
check_true("...and the refusal names the trust level, not the origin",
           "trust_level=UNVERIFIED" in _mat_why(_unv),
           "(D) origin says how it arrived, trust says whether it counts")
check_raises("an END_OF_DAY quote cannot price a live order",
             lambda: _unv.assert_usable_for("live_order"))
check_true("an UNVERIFIED quote may still be DISPLAYED with its labels",
           _unv.assert_usable_for("display") is None,
           "(D) refusing to show it would train the user to bypass the layer")

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
# This read `len(enabled_providers()) == 0` while nothing was enabled, and that
# number was doing two jobs at once: it happened to be true, but it did not
# actually name the fixture it was about. Now that one real provider IS enabled,
# the count alone can no longer express the property, which is a good thing --
# the property was never the count. It is: a provider whose LICENCE is cleared
# but whose FLAG is off is absent from enabled_providers(). Asserted by
# membership, so it stays meaningful however many providers are on.
_enabled_keys = [p.key for p in enabled_providers()]
check_true("a cleared-but-disabled provider still does not count as enabled",
           "_test_cleared_but_off" not in _enabled_keys,
           "(C) enabled_providers() reflects the flag, not the licence -- the "
           "fixture has permits_machine_use=True and is still absent")
check_true("...and registering it did not silently enable anything else",
           _enabled_keys == ["alpha_vantage"],
           "(D) MEASURED list, not a count: a count of 1 would also pass if the "
           "wrong provider were the one switched on")
check_true("...while it IS in the reviewed registry, so it was really added",
           "_test_cleared_but_off" in PROVIDERS,
           "(D) otherwise the two assertions above would pass on a fixture that "
           "never registered, proving nothing")

sys.exit(summary())
