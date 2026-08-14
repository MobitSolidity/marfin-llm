"""
Market data layer: the SS.5.5 field set, and why it has no live provider yet.

WHAT SS.5.5 REQUIRES
--------------------
"Separate market data from TradingView display data. Use licensed or otherwise
authorized providers for machine-use market data." Then eighteen fields that must
be preserved: provider, symbol, canonical instrument ID, exchange, asset class,
currency, timestamp, provider timestamp, retrieval timestamp, timezone, delay
status, market status, bid/ask/last, adjustment status, corporate-action status,
data license, trust level.

That list is not bureaucracy. Every field on it is a way a price can be wrong in a
manner that looks right: a delayed quote used as live, an unadjusted close compared
against an adjusted one, a naive timestamp compared across timezones, a price in
the wrong currency, a quote from a closed market treated as current.

WHY THERE IS NO PROVIDER CONNECTOR IN THIS FILE
-----------------------------------------------
Because the licence review (docs/legal/market-data-providers.md, 2026-08-12) did
not clear one:

  - TradingView PROHIBITS non-display use outright.
  - Twelve Data affirmatively licenses non-display use, but "only as permitted by
    your subscription tier" -- and no tier has been verified. UNKNOWN.
  - Alpha Vantage grants personal, non-commercial use and says nothing about
    non-display use; but its exclusion criteria turn on the USER's employment and
    affiliations, which are facts I cannot know.
  - Stooq is behind a JS bot gate; two other candidates 404'd.

So this module defines the shape, the labelling and the refusals -- all of which are
real and tested -- and leaves the fetch absent. Writing a connector against
unverified terms would be a licence violation waiting for an API key, and Phase 3
already proved that a declared-but-unenforced rule drifts.

The user-supplied path (SS.7.1 Level 0) works today and needs no licence at all.

Stdlib only.
"""

import datetime
from types import MappingProxyType
from typing import Any, Dict, Mapping, Optional


# ---------------------------------------------------------------------------
# Labels that must never be guessed.
# ---------------------------------------------------------------------------

#: Is the price current? A delayed quote silently treated as live is the single
#: most consequential market-data error, so there is no default: UNKNOWN is a
#: value, and it is the one you get when nobody said.
DELAY_STATUS = ("REALTIME", "DELAYED", "END_OF_DAY", "UNKNOWN")

#: Was the market open when this printed? A last price from a closed session is
#: stale by definition, however fresh the retrieval timestamp.
MARKET_STATUS = ("OPEN", "CLOSED", "PRE_MARKET", "POST_MARKET", "HALTED",
                 "UNKNOWN")

#: Adjusted for splits/dividends, or not? Comparing an adjusted series against an
#: unadjusted one produces a plausible, wrong answer -- the worst kind.
ADJUSTMENT_STATUS = ("ADJUSTED", "UNADJUSTED", "SPLIT_ADJUSTED_ONLY", "UNKNOWN")

#: Pending corporate action that invalidates naive comparison.
CORPORATE_ACTION_STATUS = ("NONE_KNOWN", "PENDING_SPLIT", "PENDING_DIVIDEND",
                           "PENDING_MERGER", "DELISTED", "UNKNOWN")

#: How the value entered the system. Deliberately separate from trust_level:
#: trust is about the SOURCE's authority, origin is about the PATH the number
#: took. A user typing a Bloomberg figure by hand is a high-authority source
#: reached by a low-reliability path, and both facts matter.
#:
#: VISUALLY_EXTRACTED is required by SS.7.1 Level 3 and carries its own rules
#: (approximate; unsuitable as sole evidence; unsuitable for live orders).
VALUE_ORIGINS = ("PROVIDER_API", "USER_SUPPLIED", "CSV_EXPORT",
                 "VISUALLY_EXTRACTED", "UNKNOWN")

#: Origins that may NOT be the sole basis for a material calculation or an order.
#: SS.7.1 Level 3 says so for screenshots. USER_SUPPLIED is included on the same
#: logic: a hand-typed number has no provenance a machine can check. This is not
#: a refusal to use them -- it is a refusal to let them stand alone.
WEAK_ORIGINS = ("VISUALLY_EXTRACTED", "USER_SUPPLIED", "UNKNOWN")


#: WHY a provider is switched on. This exists because the user chose to enable
#: Alpha Vantage, and collapsing that into `permits_machine_use=True` would have
#: written a falsehood into the record: the Alpha Vantage terms contain the token
#: `non-display` ZERO times (MEASURED 2026-08-12, re-probed 2026-08-14 --
#: sha256_16 2282b2a77e9fa981, byte-identical, so the analysis still holds).
#: Silence is not a grant. There is a real difference between
#:
#:   LICENCE_EXPLICIT   the terms affirmatively license machine use
#:   USER_ACCEPTED_RISK the terms are SILENT, and a named human decided to
#:                      proceed anyway, having been told what is unknown
#:
#: Both produce a working connector. Only the second one carries a risk the user
#: owns, and a system that cannot tell them apart cannot warn anyone later.
ACTIVATION_BASES = ("LICENCE_EXPLICIT", "USER_ACCEPTED_RISK")


class MarketDataError(ValueError):
    """A quote is unusable, or is being used for something it cannot support."""


def _utc_now():
    return datetime.datetime.now(datetime.timezone.utc)


class Quote(object):
    """
    One market observation, carrying every SS.5.5 field.

    IMMUTABLE, for the reason sources.py established: a quote whose delay_status a
    caller can flip from DELAYED to REALTIME after the fact is not a record of
    anything. Prices are evidence; evidence does not get edited.

    NO DEFAULTS FOR THE DANGEROUS FIELDS. delay_status, market_status,
    adjustment_status and trust_level must be passed explicitly. It is tempting to
    default delay_status="UNKNOWN" for convenience, but then every careless caller
    produces a quote labelled UNKNOWN and the label stops meaning "we checked and
    could not tell". Forcing the argument makes the ignorance deliberate.
    """

    _FIELDS = ("provider", "symbol", "instrument_id", "exchange", "asset_class",
               "currency", "timestamp", "provider_timestamp", "retrieved_at",
               "timezone", "delay_status", "market_status", "bid", "ask", "last",
               "adjustment_status", "corporate_action_status", "licence",
               "trust_level", "origin", "note")

    __slots__ = _FIELDS + ("_frozen",)

    def __init__(self, provider, symbol, instrument_id, exchange, asset_class,
                 currency, timestamp, timezone, delay_status, market_status,
                 adjustment_status, trust_level, origin,
                 provider_timestamp=None, retrieved_at=None,
                 bid=None, ask=None, last=None,
                 corporate_action_status="UNKNOWN", licence="", note=""):
        object.__setattr__(self, "_frozen", False)

        if not provider or not isinstance(provider, str):
            raise MarketDataError("provider must be named: an unattributed price "
                                  "cannot be licence-checked or contradicted")
        if not symbol or not isinstance(symbol, str):
            raise MarketDataError("symbol must be a non-empty string")
        if not exchange:
            # "AAPL" alone is ambiguous across venues, and the ambiguity is
            # invisible until two sources disagree.
            raise MarketDataError(
                "exchange must be recorded for %r: the same ticker trades on "
                "different venues at different prices" % (symbol,))
        if not currency:
            raise MarketDataError(
                "currency must be recorded for %r: a bare number is not a price, "
                "and a cross-currency comparison looks perfectly valid"
                % (symbol,))

        for field, allowed in (("delay_status", DELAY_STATUS),
                               ("market_status", MARKET_STATUS),
                               ("adjustment_status", ADJUSTMENT_STATUS),
                               ("corporate_action_status",
                                CORPORATE_ACTION_STATUS),
                               ("origin", VALUE_ORIGINS)):
            value = {"delay_status": delay_status,
                     "market_status": market_status,
                     "adjustment_status": adjustment_status,
                     "corporate_action_status": corporate_action_status,
                     "origin": origin}[field]
            if value not in allowed:
                raise MarketDataError(
                    "%s must be one of %s, got %r. A value outside the "
                    "vocabulary would be silently ignored by every consumer."
                    % (field, ", ".join(allowed), value))

        # Trust levels are shared with the document layer so that a price and a
        # filing can be ranked against each other at all.
        from rag.documents import TRUST_LEVELS
        if trust_level not in TRUST_LEVELS:
            raise MarketDataError("unknown trust level %r; allowed: %s"
                                  % (trust_level, sorted(TRUST_LEVELS)))

        if timestamp is None:
            raise MarketDataError("timestamp is required: an undated price "
                                  "cannot be shown to be current")
        if not timezone:
            # SS.5.5 lists timezone separately from timestamp precisely because a
            # naive local timestamp is the classic cross-market bug.
            raise MarketDataError(
                "timezone must be recorded for %r: a naive timestamp compared "
                "across venues is wrong in a way nothing detects" % (symbol,))

        if bid is None and ask is None and last is None:
            raise MarketDataError(
                "a quote must carry at least one of bid/ask/last")
        for name, value in (("bid", bid), ("ask", ask), ("last", last)):
            if value is None:
                continue
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise MarketDataError("%s must be a number, got %r"
                                      % (name, value))
            if value != value:            # NaN
                raise MarketDataError("%s is NaN, which compares false against "
                                      "everything and poisons any calculation "
                                      "silently" % (name,))
            # FOUND BY BOUNDARY PROBE, not by the 45-attempt adversarial probe:
            # infinity passed every guard here. `value < 0` is False for inf,
            # `isinstance` is True, and NaN-checking does not catch it. It then
            # propagates through arithmetic as inf or nan and the result LOOKS
            # computed. Checking only the pathologies I thought of first is how
            # this survived a probe that reported 45/45 refused.
            if value in (float("inf"), float("-inf")):
                raise MarketDataError(
                    "%s is infinite, which propagates through every subsequent "
                    "calculation as inf or NaN while still looking like a "
                    "number" % (name,))
            if value < 0:
                raise MarketDataError("%s cannot be negative: %r"
                                      % (name, value))
            # ALSO FOUND BY BOUNDARY PROBE: 0.0 passed `value < 0`. A zero price
            # is not merely implausible, it is arithmetically hostile -- it makes
            # any ratio, return, or position-sizing division either raise
            # ZeroDivisionError deep inside a calculation or produce a silent
            # infinity. A genuinely zero-valued instrument (an expired option) is
            # a case for an explicit note, not a default.
            if value == 0:
                raise MarketDataError(
                    "%s is zero for %r. A zero price divides into every ratio "
                    "and return calculation downstream; if the instrument truly "
                    "prices at zero, record it explicitly rather than as a "
                    "quote." % (name, symbol))
        if (bid is not None and ask is not None) and bid > ask:
            raise MarketDataError(
                "crossed quote: bid %r > ask %r. Either the feed is broken or "
                "the fields are swapped; both are refusals, not warnings."
                % (bid, ask))

        self.provider = provider
        self.symbol = symbol
        self.instrument_id = instrument_id
        self.exchange = exchange
        self.asset_class = asset_class
        self.currency = currency
        self.timestamp = timestamp
        self.provider_timestamp = provider_timestamp
        self.retrieved_at = retrieved_at or _utc_now()
        self.timezone = timezone
        self.delay_status = delay_status
        self.market_status = market_status
        self.bid = bid
        self.ask = ask
        self.last = last
        self.adjustment_status = adjustment_status
        self.corporate_action_status = corporate_action_status
        self.licence = licence
        self.trust_level = trust_level
        self.origin = origin
        self.note = note
        object.__setattr__(self, "_frozen", True)

    def __setattr__(self, name, value):
        if getattr(self, "_frozen", False):
            raise MarketDataError(
                "quotes are immutable: refusing to set %r on %s/%s. A price "
                "whose delay or adjustment status can be edited afterwards is "
                "not evidence of anything."
                % (name, self.provider, self.symbol))
        object.__setattr__(self, name, value)

    def __delattr__(self, name):
        raise MarketDataError("quotes are immutable: refusing to delete %r"
                              % (name,))

    def __repr__(self):
        return ("Quote(%s/%s %s last=%r %s %s)"
                % (self.provider, self.symbol, self.currency, self.last,
                   self.delay_status, self.origin))

    # -- the questions callers actually need answered ------------------------

    @property
    def is_weak(self) -> bool:
        """True if this value may not stand alone (SS.7.1 Level 3)."""
        return self.origin in WEAK_ORIGINS

    @property
    def is_live(self) -> bool:
        """
        True only for a realtime quote from an open market.

        Both conditions, because either alone is misleading: a REALTIME quote
        from a CLOSED market is a stale last price, and an OPEN market says
        nothing about whether THIS number is delayed.
        """
        return self.delay_status == "REALTIME" and self.market_status == "OPEN"

    def assert_usable_for(self, purpose: str) -> None:
        """
        Refuse uses this observation cannot support.

        SS.7.1 Level 3: screenshot values are "unsuitable as sole evidence for
        material calculations" and "unsuitable as authoritative live-order data".
        Encoded here so the label has consequences -- a label nothing checks is
        decoration, which is precisely what Phase 3 found in sources.py.
        """
        if not purpose or not isinstance(purpose, str):
            raise MarketDataError("purpose must be a non-empty string")

        if purpose == "live_order":
            if self.is_weak:
                raise MarketDataError(
                    "%s/%s is %s and may not be authoritative live-order data "
                    "(SS.7.1 Level 3). Obtain the price from the broker at "
                    "order time." % (self.provider, self.symbol, self.origin))
            if not self.is_live:
                raise MarketDataError(
                    "%s/%s is delay_status=%s market_status=%s -- not live. "
                    "Submitting an order against it would price the trade off a "
                    "stale number." % (self.provider, self.symbol,
                                       self.delay_status, self.market_status))
        elif purpose == "material_calculation":
            if self.is_weak:
                raise MarketDataError(
                    "%s/%s is %s and is unsuitable as SOLE evidence for a "
                    "material calculation (SS.7.1 Level 3). Corroborate it with "
                    "a provider or CSV value, or present the result as "
                    "approximate." % (self.provider, self.symbol, self.origin))
            # A LATENT DEFECT, found by enabling the first real provider on
            # 2026-08-14 and MEASURED before being fixed: this branch checked
            # `origin` only, so a quote with origin=PROVIDER_API passed
            # regardless of trust_level -- including trust_level=UNVERIFIED,
            # whose own definition in rag.documents.TRUST_LEVELS reads
            # "never citable as fact". All six trust levels passed. The gate was
            # unreachable while every provider was disabled, which is exactly
            # how it survived: an untaken code path is an untested one.
            #
            # origin and trust are deliberately separate axes (see VALUE_ORIGINS)
            # and a gate that reads one of them enforces half a rule. The Alpha
            # Vantage connector is the concrete case: origin PROVIDER_API, an
            # honest API call, but trust UNVERIFIED because the licence position
            # is UNKNOWN and its timestamp is constructed rather than observed.
            from rag.documents import TRUST_LEVELS
            if TRUST_LEVELS.get(self.trust_level, 0) <= 0:
                raise MarketDataError(
                    "%s/%s carries trust_level=%s (score %d), which "
                    "rag.documents.TRUST_LEVELS defines as 'never citable as "
                    "fact'. It may not be the SOLE evidence for a material "
                    "calculation however it arrived -- origin=%s says the path "
                    "was clean, not that the source is authoritative. "
                    "Corroborate it, or present the result as approximate and "
                    "labelled."
                    % (self.provider, self.symbol, self.trust_level,
                       TRUST_LEVELS.get(self.trust_level, 0), self.origin))
        elif purpose == "display":
            return          # anything may be shown to a human, with its labels
        else:
            raise MarketDataError(
                "unknown purpose %r; allowed: live_order, material_calculation, "
                "display. An unrecognised purpose is not assumed permitted."
                % (purpose,))

    def to_dict(self) -> Dict[str, Any]:
        return {k: getattr(self, k) for k in self._FIELDS}


# ---------------------------------------------------------------------------
# Provider registry -- reviewed, and deliberately all disabled.
# ---------------------------------------------------------------------------

class Provider(object):
    """
    A market-data provider and the terms found in its licence.

    `permits_machine_use` is a tri-state (True / False / None=UNKNOWN) rather than
    a bool, because the review produced three genuinely different answers and
    collapsing UNKNOWN into False would lose the distinction between "we checked,
    it is forbidden" (TradingView) and "we could not read the terms" (Stooq). The
    two demand different follow-up.
    """

    _FIELDS = ("key", "name", "base_url", "terms_url", "enabled",
               "permits_machine_use", "status", "trust_level", "licence_note",
               "blocking_question", "reviewed_on", "activation_basis",
               "accepted_risks", "decided_by", "decided_on")
    __slots__ = _FIELDS + ("_frozen",)

    def __init__(self, key, name, base_url, terms_url, enabled,
                 permits_machine_use, status, trust_level, licence_note,
                 blocking_question="", reviewed_on="2026-08-12",
                 activation_basis=None, accepted_risks=(), decided_by="",
                 decided_on=""):
        object.__setattr__(self, "_frozen", False)
        if not key or not isinstance(key, str):
            raise MarketDataError("provider key must be a non-empty string")
        if permits_machine_use not in (True, False, None):
            raise MarketDataError(
                "permits_machine_use must be True, False or None (UNKNOWN), "
                "got %r. Anything else erases the difference between 'checked "
                "and forbidden' and 'could not check'." % (permits_machine_use,))
        if activation_basis is not None and activation_basis not in ACTIVATION_BASES:
            raise MarketDataError(
                "activation_basis must be one of %s or None, got %r"
                % (", ".join(ACTIVATION_BASES), activation_basis))
        if enabled and activation_basis is None:
            raise MarketDataError(
                "refusing to enable provider %r with no activation_basis: an "
                "enabled provider must record WHY it is on, otherwise a licence "
                "grant and a human's accepted risk look identical in the record."
                % (key,))
        if not enabled and activation_basis is not None:
            raise MarketDataError(
                "provider %r is disabled but records activation_basis=%r. A "
                "basis for switching something on that is off is a leftover "
                "from an edit, and the next reader would take it as live."
                % (key, activation_basis))
        # SS.5.5 requires a licensed or OTHERWISE AUTHORIZED provider. The
        # original guard read `permits_machine_use is not True`, which allowed
        # exactly one route in. That was right while nobody had decided anything;
        # it is too narrow now, because the spec's "otherwise authorized" is a
        # real second route and the user has taken it for Alpha Vantage.
        #
        # What must NOT happen is the lazy repair: setting
        # permits_machine_use=True to get past the guard. That would record that
        # the LICENCE permits machine use, which is false and unmeasurable --
        # `non-display` appears 0 times in those terms. So the tri-state keeps
        # telling the truth about the DOCUMENT, and authorization is carried by a
        # separate field that says a human decided.
        if enabled and permits_machine_use is not True:
            if activation_basis != "USER_ACCEPTED_RISK":
                raise MarketDataError(
                    "refusing to enable provider %r: machine use is %s and "
                    "activation_basis is %r. SS.5.5 requires a licensed or "
                    "otherwise authorized provider for machine-use market data. "
                    "See docs/legal/market-data-providers.md."
                    % (key, {False: "PROHIBITED", None: "UNVERIFIED"}[
                        permits_machine_use], activation_basis))
            if permits_machine_use is False:
                # A user may accept an UNKNOWN. A user may not accept a
                # PROHIBITION: TradingView's terms forbid the category outright,
                # so consent does not create a permission. This is the line
                # between assuming a risk and breaching a contract.
                raise MarketDataError(
                    "refusing to enable provider %r: its terms PROHIBIT machine "
                    "use (%s). USER_ACCEPTED_RISK covers terms that are SILENT, "
                    "not terms that forbid. A user cannot consent on the "
                    "counterparty's behalf." % (key, status))
            if not accepted_risks:
                raise MarketDataError(
                    "refusing to enable provider %r on USER_ACCEPTED_RISK with "
                    "no accepted_risks recorded. The whole basis of this route "
                    "is that the user was told what is unknown; an empty list "
                    "means nobody can later check what they were told."
                    % (key,))
            if not decided_by or not decided_on:
                raise MarketDataError(
                    "refusing to enable provider %r on USER_ACCEPTED_RISK "
                    "without decided_by and decided_on. An accepted risk with "
                    "no owner and no date is indistinguishable from a default."
                    % (key,))
        if not enabled and not status:
            raise MarketDataError("provider %r is disabled but records no "
                                  "status" % (key,))
        if not licence_note:
            raise MarketDataError(
                "provider %r must record what its licence says; an unexplained "
                "entry is indistinguishable from an unreviewed one" % (key,))
        self.key = key
        self.name = name
        self.base_url = base_url
        self.terms_url = terms_url
        self.enabled = enabled
        self.permits_machine_use = permits_machine_use
        self.status = status
        self.trust_level = trust_level
        self.licence_note = licence_note
        self.blocking_question = blocking_question
        self.reviewed_on = reviewed_on
        self.activation_basis = activation_basis
        # A tuple, not the caller's list: a mutable accepted-risks list would let
        # the record of what the user was told be edited after the fact, and this
        # object is frozen precisely so that cannot happen.
        self.accepted_risks = tuple(accepted_risks or ())
        self.decided_by = decided_by
        self.decided_on = decided_on
        object.__setattr__(self, "_frozen", True)

    def __setattr__(self, name, value):
        if getattr(self, "_frozen", False):
            raise MarketDataError(
                "provider terms are immutable: refusing to set %r on %r. One "
                "line would otherwise enable a provider whose licence was never "
                "cleared." % (name, self.key))
        object.__setattr__(self, name, value)

    def __delattr__(self, name):
        raise MarketDataError("provider terms are immutable: refusing to delete "
                              "%r on %r" % (name, self.key))

    def __repr__(self):
        return ("Provider(%r, enabled=%s, machine_use=%s)"
                % (self.key, self.enabled, self.permits_machine_use))

    def to_dict(self):
        return {k: getattr(self, k) for k in self._FIELDS}


_PROVIDERS: Dict[str, Provider] = {}


def register_provider(p: Provider) -> Provider:
    if not isinstance(p, Provider):
        raise MarketDataError("expected a Provider, got %r"
                              % (type(p).__name__,))
    if p.key in _PROVIDERS:
        raise MarketDataError("provider %r already registered; refusing to "
                              "overwrite a reviewed entry" % (p.key,))
    _PROVIDERS[p.key] = p
    return p


register_provider(Provider(
    key="twelvedata",
    name="Twelve Data",
    base_url="https://api.twelvedata.com",
    terms_url="https://twelvedata.com/terms",
    enabled=False,
    permits_machine_use=None,          # category yes, tier UNVERIFIED
    status="SELECTED CANDIDATE, PROVISIONAL -- not active",
    trust_level="PERMITTED_RESEARCH",
    licence_note="The only candidate that AFFIRMATIVELY licenses machine use: "
                 "'Access, receive, process, and store Data solely for Internal "
                 "Use', 'Create Derived Data', and 'Use Data for Non-Display "
                 "Use only as permitted by your subscription tier'. That last "
                 "clause is why this is None and not True: no tier has been "
                 "verified, so the instance of the permission is UNKNOWN even "
                 "though the category is granted. Also restricts caching "
                 "'beyond permitted timeframes specified in the Documentation' "
                 "-- unread, so market data must be treated as "
                 "non-persistable.",
    blocking_question="Which Twelve Data subscription tier permits non-display "
                      "use, and is the user willing to pay for it?"))

register_provider(Provider(
    key="alpha_vantage",
    name="Alpha Vantage",
    base_url="https://www.alphavantage.co",
    terms_url="https://www.alphavantage.co/terms_of_service/",
    enabled=True,
    # STILL None, and that is the point. The terms are SILENT on machine use:
    # the token `non-display` appears 0 times. Setting this True to unlock the
    # enable guard would have recorded a permission no document grants. The
    # authorization comes from activation_basis instead.
    permits_machine_use=None,
    status="ENABLED on USER_ACCEPTED_RISK -- terms silent on machine use; "
           "free tier only; NOT licensed for realtime or 15-min delayed data",
    # Not PERMITTED_RESEARCH. A source whose licence position is unverified must
    # not outrank one whose position was actually read, so it sits at the bottom
    # of the ladder and cannot be cited as fact on its own.
    trust_level="UNVERIFIED",
    licence_note="Grants use 'for personal, non-commercial use'. Contains NO "
                 "non-display clause (searched: non-display, redistribut, "
                 "cache, store, derived -- 0 occurrences each), so machine "
                 "processing is not prohibited -- but silence is not a grant, "
                 "hence permits_machine_use stays None. Exclusion criterion "
                 "(iv) -- 'employed or have an active affiliation with a "
                 "financial planning advisor, insurance company, investment "
                 "advisor, investment bank' -- was ANSWERED by the user on "
                 "2026-08-14: no affiliation with any institution or person, "
                 "building this project alone. That clears (iv) and the "
                 "'on behalf of a corporation' exclusion. Terms re-probed "
                 "2026-08-14: HTTP 200, 127,102 bytes, sha256_16 "
                 "2282b2a77e9fa981 -- byte-identical to the 2026-08-12 review, "
                 "so that analysis still applies.",
    blocking_question="",
    activation_basis="USER_ACCEPTED_RISK",
    accepted_risks=(
        "The terms are SILENT on non-display/machine use (0 occurrences of "
        "'non-display'); absence of a prohibition is not an affirmative grant, "
        "so machine processing is UNKNOWN-leaning-permitted, not permitted.",
        "MEASURED 2026-08-14 from alphavantage.co/support/: the free tier is "
        "'25 API requests per day'. Not 25 per minute. This is a hard design "
        "constraint, not a footnote.",
        "MEASURED 2026-08-14, quoted: 'Realtime and 15-minute delayed US "
        "market data is regulated by the stock exchanges, FINRA, and the SEC' "
        "and is premium-only. The free tier therefore CANNOT supply realtime "
        "or 15-minute-delayed quotes -- a regulatory limit, not a paywall to "
        "be worked around.",
        "Whether a local analytical assistant counts as 'personal, "
        "non-commercial use' if its output were ever sold or published is a "
        "lawyer's question and is NOT resolved. If this project stops being "
        "personal, this activation must be revisited.",
        "Cache/storage timeframes: UNKNOWN for this provider too. Market data "
        "remains non-persistable until read.",
    ),
    decided_by="project owner (sole individual, no institutional affiliation)",
    decided_on="2026-08-14"))

register_provider(Provider(
    key="tradingview",
    name="TradingView",
    base_url="https://www.tradingview.com",
    terms_url="https://www.tradingview.com/policies/",
    enabled=False,
    permits_machine_use=False,         # checked, and forbidden
    status="PROHIBITED -- display only, permanently unusable as a data source",
    trust_level="UNVERIFIED",
    licence_note="Terms of Use s3: content licensed for 'exclusive display-only "
                 "use'; 'explicitly prohibits any form of non-display usage', "
                 "naming automated trading, price referencing, order "
                 "verification, algorithmic decision-making, smart order "
                 "routing and risk management programs. See "
                 "docs/legal/tradingview-terms-review.md and "
                 "src/market/tradingview.py, which refuses at the API level.",
    blocking_question="None. This is not a pending question -- it is settled."))

register_provider(Provider(
    key="stooq",
    name="Stooq",
    base_url="https://stooq.com",
    terms_url="https://stooq.com/db/h/",
    enabled=False,
    permits_machine_use=None,
    status="UNVERIFIED -- terms could not be read",
    trust_level="UNVERIFIED",
    licence_note="Probe returned 796 bytes: 'This site requires JavaScript to "
                 "verify your browser.' No terms were read. Recorded as UNKNOWN "
                 "rather than unrestricted: a page I could not fetch is not a "
                 "page that grants permission.",
    blocking_question="Can the terms be obtained at all?"))

PROVIDERS: Mapping[str, Provider] = MappingProxyType(_PROVIDERS)


def get_provider(key: str) -> Provider:
    try:
        return PROVIDERS[key]
    except KeyError:
        raise MarketDataError(
            "unknown market-data provider %r. Known: %s. An unregistered "
            "provider has no reviewed licence, so it cannot be used."
            % (key, ", ".join(sorted(PROVIDERS))))


def enabled_providers():
    """
    Returned [] from 2026-08-12 to 2026-08-14; now returns [alpha_vantage].

    That history matters, so it is recorded rather than overwritten. The empty
    list was the honest state while both candidates were blocked on questions a
    human had to answer. On 2026-08-14 the user answered both:

      - not employed by or affiliated with any advisor, bank or insurer, and
        building the project alone      -> clears Alpha Vantage criterion (iv)
      - unwilling to pay for a tier     -> closes Twelve Data, which sells
                                           non-display use by tier

    So Alpha Vantage is enabled on USER_ACCEPTED_RISK, not on a licence grant:
    its terms are SILENT on machine use. It is trust_level UNVERIFIED and its
    free tier is limited to 25 requests/day with NO realtime or 15-minute data
    (both MEASURED). Levels 0 and 2 therefore remain first-class paths rather
    than fallbacks -- for anything intraday they are the ONLY paths.
    """
    return [p for p in PROVIDERS.values() if p.enabled]


def user_accepted_risk_providers():
    """
    The enabled providers whose authorization is a human decision, not a licence.

    Exists so a report can say so out loud. A provider on this list produces
    usable data whose legal basis is weaker than a licence, and a system that
    cannot enumerate them cannot warn anyone.
    """
    return [p for p in PROVIDERS.values()
            if p.enabled and p.activation_basis == "USER_ACCEPTED_RISK"]


def assert_provider_usable(key: str) -> Provider:
    """
    Refuse a fetch from a provider whose licence is not cleared.

    The ORDER of these checks is the design. A PROHIBITION is checked first and
    is absolute: no amount of user consent reaches past it, because the user is
    not the party granting the licence. Only then is the UNKNOWN case
    considered, and it is where USER_ACCEPTED_RISK applies -- a human may decide
    to proceed under silent terms, having been told what is unknown.

    Reversing these two would let a documented prohibition be consented away,
    which is the difference between assuming a risk and breaching a contract.
    """
    p = get_provider(key)
    if p.permits_machine_use is False:
        raise MarketDataError(
            "provider %r PROHIBITS machine use: %s" % (key, p.status))
    if p.permits_machine_use is None \
            and p.activation_basis != "USER_ACCEPTED_RISK":
        raise MarketDataError(
            "provider %r has UNVERIFIED licence status for machine use (%s). "
            "Blocking question: %s" % (key, p.status, p.blocking_question))
    if not p.enabled:
        raise MarketDataError("provider %r is registered but not enabled: %s"
                              % (key, p.status))
    return p


#: MEASURED free-tier limits, enforced rather than documented.
#:
#: Phase 3's finding was that a declared rule which nothing checks drifts from
#: reality. So these are not comments: assert_tier_supports() refuses, and the
#: numbers came from alphavantage.co/support/ on 2026-08-14, quoted in
#: docs/legal/market-data-providers.md.
FREE_TIER_LIMITS: Mapping[str, Any] = MappingProxyType({
    "alpha_vantage": MappingProxyType({
        "requests_per_day": 25,
        # Quoted: "Realtime and 15-minute delayed US market data is regulated by
        # the stock exchanges, FINRA, and the SEC" -- premium-only. So the free
        # tier can supply END_OF_DAY only. This is a REGULATORY boundary; there
        # is no clever request that gets around it, and pretending otherwise
        # would produce a quote labelled REALTIME that is nothing of the kind.
        "permitted_delay_status": ("END_OF_DAY", "UNKNOWN"),
        "source": "alphavantage.co/support/ probed 2026-08-14, HTTP 200",
    }),
})


def assert_tier_supports(key: str, delay_status: str) -> None:
    """
    Refuse a request for data the user's tier is not licensed to receive.

    This runs BEFORE any fetch, because the failure it prevents is not a network
    error: it is a quote that arrives labelled REALTIME from a tier that cannot
    lawfully supply realtime data. That value would look better than the
    END_OF_DAY it really is, and every downstream calculation would inherit the
    mislabelling silently.
    """
    if delay_status not in DELAY_STATUS:
        raise MarketDataError("unknown delay_status %r; allowed: %s"
                              % (delay_status, ", ".join(DELAY_STATUS)))
    limits = FREE_TIER_LIMITS.get(key)
    if limits is None:
        return
    allowed = limits["permitted_delay_status"]
    if delay_status not in allowed:
        raise MarketDataError(
            "provider %r on its free tier is not licensed to supply %s data "
            "(permitted: %s). Quoted from %s: 'Realtime and 15-minute delayed "
            "US market data is regulated by the stock exchanges, FINRA, and the "
            "SEC' and is premium-only. This is a regulatory limit, not a rate "
            "limit -- requesting it anyway would either fail or return a value "
            "whose label is wrong."
            % (key, delay_status, ", ".join(allowed), limits["source"]))


def fetch_quote(*args, **kwargs):
    """
    Not implemented, on purpose, and this docstring is the design decision.

    No provider's licence has been cleared (see enabled_providers()). A connector
    written now would sit dormant until someone added an API key, at which point
    it would make requests under terms nobody verified. Phase 3 established that
    declarations drift from enforcement whenever nothing checks; an unused
    connector is the purest case.

    When a tier is confirmed, implement it behind assert_provider_usable() and
    return a Quote carrying all eighteen SS.5.5 fields.
    """
    raise NotImplementedError(
        "no market-data provider is licensed for machine use yet. "
        "Use quote_from_user_input() (SS.7.1 Level 0) or the CSV path "
        "(Level 2). See docs/legal/market-data-providers.md for the two "
        "questions blocking activation.")


def quote_from_user_input(symbol, exchange, currency, timestamp, timezone,
                          last=None, bid=None, ask=None,
                          delay_status="UNKNOWN", market_status="UNKNOWN",
                          adjustment_status="UNKNOWN", note=""):
    """
    A price the user supplied (SS.7.1 Level 0). Needs no licence -- and gets no
    unearned credibility: origin USER_SUPPLIED, trust UNVERIFIED, so is_weak is
    True and assert_usable_for('live_order') refuses it.
    """
    return Quote(
        provider="user", symbol=symbol, instrument_id=None, exchange=exchange,
        asset_class=None, currency=currency, timestamp=timestamp,
        timezone=timezone, delay_status=delay_status,
        market_status=market_status, adjustment_status=adjustment_status,
        corporate_action_status="UNKNOWN", trust_level="UNVERIFIED",
        origin="USER_SUPPLIED", bid=bid, ask=ask, last=last,
        licence="n/a -- supplied by the user", note=note)


def manifest() -> Dict[str, Any]:
    return {"providers": [p.to_dict() for p in PROVIDERS.values()],
            "n_enabled": len(enabled_providers()),
            "n_prohibited": sum(1 for p in PROVIDERS.values()
                                if p.permits_machine_use is False),
            "n_unverified": sum(1 for p in PROVIDERS.values()
                                if p.permits_machine_use is None)}
