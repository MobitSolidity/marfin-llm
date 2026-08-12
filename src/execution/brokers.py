"""
Broker adapters: what exists, what cannot be verified without credentials, and
why every one of them is disabled.

WHAT SS.5.6 REQUIRES
--------------------
"Physically and logically separate execution from: the LLM, news retrieval,
TradingView webhooks, RAG documents, screenshots, strategy generation,
backtesting."

That separation is why this module imports NOTHING from rag/, tools/ or
market/tradingview.py. The dependency direction is the enforcement: a webhook
cannot reach an order because there is no path from webhook code to this module,
not because a comment asks it not to. A test asserts the import list, since
"separate" is otherwise a claim that decays the first time somebody needs a
convenience.

WHAT THIS TASK ASKED FOR: "SELECT BROKER ADAPTERS; DOCUMENT WHAT CANNOT BE
VERIFIED WITHOUT CREDENTIALS"
--------------------------------------------------------------------------
The second half is the honest half. For each candidate I can verify from public
documentation: that an API exists, its transport, whether a paper/sandbox
environment is offered, whether idempotency is supported, and whether the user's
jurisdiction is served. I CANNOT verify, without an account and keys: that the
credentials work, that the paper environment actually rejects live orders, that
idempotency keys behave as documented, that rate limits are as published, or that
order-state transitions match SS.6.4. Every one of those is a live-integration
fact.

The distinction matters because a "verified broker adapter" is an SS.6.1
prerequisite for LIVE_TRADING. Reading documentation is not verification, and
recording documentation-reading AS verification would satisfy the prerequisite on
paper while leaving it unmet in fact.

THE IRANIAN-MARKET CONSTRAINT
-----------------------------
Q3 descoped Iranian market data, so no Iranian broker is a candidate here. That
is a scope decision, not a judgement about those brokers. Recorded because a
bilingual Persian-English financial assistant with no Iranian broker adapter is a
surprising outcome that deserves its reason attached.

WHY NO ADAPTER IS IMPLEMENTED
-----------------------------
The same reasoning as market/quotes.py's absent fetch_quote, and it applied there
first: an adapter written now would sit dormant until someone added credentials,
at which point it would place orders through code that no live account had ever
exercised, under a risk engine that does not exist (SS.6.3 lists 21 mandatory
controls) and without the SS.6.2 two-phase preview protocol. The correct artifact
at this stage is a reviewed catalog plus refusals that hold.

Stdlib only. Imports only from execution.mode -- deliberately.
"""

from types import MappingProxyType
from typing import Any, Dict, Mapping, Optional, Tuple

from execution.mode import ExecutionModeError, require


#: How an adapter's readiness was established. The distinction between
#: DOCUMENTED and VERIFIED is the entire point of this module: only the second
#: can satisfy SS.6.1's "verified broker adapter", and only credentials plus a
#: live round-trip can produce it.
VERIFICATION_LEVELS: Tuple[str, ...] = (
    "UNREVIEWED",      # nobody has looked
    "DOCUMENTED",      # public docs read; no credential has ever been used
    "SANDBOX_TESTED",  # a paper/sandbox account round-tripped an order
    "VERIFIED",        # SANDBOX_TESTED plus a reviewed live round-trip
)

#: Environments an adapter may expose. SS.6.3: "Paper and live accounts must have
#: unambiguous identifiers." Kept as separate string constants rather than a
#: boolean is_live, because a boolean inverts silently under a typo and reads the
#: same either way in a log.
ENVIRONMENTS: Tuple[str, ...] = ("PAPER", "LIVE")


class BrokerError(RuntimeError):
    """
    A broker adapter cannot be used as requested.

    RuntimeError for the same reason as ExecutionModeError: this is a statement
    about configuration and verification state, not about malformed arguments, and
    a retry loop written for bad input must not treat it as retryable.
    """


class BrokerAdapter(object):
    """
    A catalog record for one broker: what its docs say, and what remains unknown.

    IMMUTABLE. `enabled` cannot be flipped at runtime for the reason established
    in sources.py and repeated in quotes.py: a one-line runtime edit would
    otherwise switch on an adapter whose verification nobody performed.

    The `unverifiable_without_credentials` field is required and must be
    non-empty. An adapter claiming there is nothing left to verify is either
    VERIFIED -- which requires a live round-trip this project has not performed
    for any broker -- or the field was not filled in.
    """

    _FIELDS = ("key", "name", "docs_url", "transport", "verification",
               "environments", "enabled", "supports_idempotency",
               "documented_capabilities", "unverifiable_without_credentials",
               "notes", "reviewed_on")
    __slots__ = _FIELDS + ("_frozen",)

    def __init__(self, key, name, docs_url, transport, verification,
                 environments, enabled, supports_idempotency,
                 documented_capabilities, unverifiable_without_credentials,
                 notes="", reviewed_on="2026-08-12"):
        object.__setattr__(self, "_frozen", False)

        if not key or not isinstance(key, str):
            raise BrokerError("broker key must be a non-empty string")
        if verification not in VERIFICATION_LEVELS:
            raise BrokerError(
                "verification must be one of %s, got %r"
                % (", ".join(VERIFICATION_LEVELS), verification))
        for env in environments:
            if env not in ENVIRONMENTS:
                raise BrokerError(
                    "unknown environment %r for %r; allowed: %s"
                    % (env, key, ", ".join(ENVIRONMENTS)))
        # THE CENTRAL GUARD. SS.6.1 requires a "verified broker adapter" for live
        # trading, and DOCUMENTED is not verified. Enabling an adapter on the
        # strength of having read its documentation is the precise mistake this
        # whole module exists to make impossible.
        if enabled and verification != "VERIFIED":
            raise BrokerError(
                "refusing to enable broker %r at verification level %s. SS.6.1 "
                "requires a VERIFIED broker adapter, which needs a credentialed "
                "round-trip that has not been performed. Reading documentation "
                "is not verification." % (key, verification))
        if not unverifiable_without_credentials:
            raise BrokerError(
                "broker %r must record what cannot be verified without "
                "credentials; an empty list would claim a completeness no "
                "documentation review can establish" % (key,))
        if not documented_capabilities:
            raise BrokerError(
                "broker %r records no documented capabilities" % (key,))

        self.key = key
        self.name = name
        self.docs_url = docs_url
        self.transport = transport
        self.verification = verification
        self.environments = tuple(environments)
        self.enabled = enabled
        self.supports_idempotency = supports_idempotency
        self.documented_capabilities = tuple(documented_capabilities)
        self.unverifiable_without_credentials = tuple(
            unverifiable_without_credentials)
        self.notes = notes
        self.reviewed_on = reviewed_on
        object.__setattr__(self, "_frozen", True)

    def __setattr__(self, name, value):
        if getattr(self, "_frozen", False):
            raise BrokerError(
                "broker adapters are immutable: refusing to set %r on %r. One "
                "line would otherwise enable an unverified adapter."
                % (name, self.key))
        object.__setattr__(self, name, value)

    def __delattr__(self, name):
        raise BrokerError("broker adapters are immutable: refusing to delete %r "
                          "on %r" % (name, self.key))

    def __repr__(self):
        return ("BrokerAdapter(%r, verification=%s, enabled=%s)"
                % (self.key, self.verification, self.enabled))

    def to_dict(self):
        return {k: getattr(self, k) for k in self._FIELDS}


_ADAPTERS: Dict[str, BrokerAdapter] = {}


def register_adapter(a: BrokerAdapter) -> BrokerAdapter:
    if not isinstance(a, BrokerAdapter):
        raise BrokerError("expected a BrokerAdapter, got %r"
                          % (type(a).__name__,))
    if a.key in _ADAPTERS:
        raise BrokerError("broker %r already registered; refusing to overwrite "
                          "a reviewed entry" % (a.key,))
    _ADAPTERS[a.key] = a
    return a


# ---------------------------------------------------------------------------
# The catalog. Everything below is DOCUMENTED: read from public documentation,
# never exercised with a credential. UNKNOWN is recorded as UNKNOWN.
# ---------------------------------------------------------------------------

_COMMON_UNVERIFIABLE = (
    "that supplied credentials authenticate at all",
    "that the paper environment actually refuses live orders",
    "that idempotency keys deduplicate as documented",
    "that published rate limits match enforced ones",
    "that order-state transitions match the SS.6.4 vocabulary",
    "that partial fills are reported incrementally",
    "that a cancel race resolves deterministically",
)

register_adapter(BrokerAdapter(
    key="alpaca",
    name="Alpaca Markets",
    docs_url="https://docs.alpaca.markets/",
    transport="REST + optional streaming",
    verification="DOCUMENTED",
    environments=("PAPER", "LIVE"),
    enabled=False,
    supports_idempotency="DOCUMENTED: client_order_id is documented as unique "
                         "per order; whether it deduplicates on retry is "
                         "UNVERIFIED",
    documented_capabilities=("read account", "read positions", "read orders",
                            "submit order", "cancel order", "paper environment"),
    unverifiable_without_credentials=_COMMON_UNVERIFIABLE + (
        "whether the user's jurisdiction is eligible for an account",),
    notes="Selected as the LEADING CANDIDATE on documentation alone: a "
          "first-class paper environment with a separate base URL makes SS.6.3's "
          "'unambiguous identifiers' requirement structural rather than a naming "
          "convention. Eligibility for an Iran-resident user is UNKNOWN and is "
          "the blocking question."))

register_adapter(BrokerAdapter(
    key="interactive_brokers",
    name="Interactive Brokers",
    docs_url="https://www.interactivebrokers.com/campus/category/ibkr-api-software/",
    transport="local gateway (TWS API) or Client Portal REST",
    verification="DOCUMENTED",
    environments=("PAPER", "LIVE"),
    enabled=False,
    supports_idempotency="UNKNOWN: order IDs are client-assigned integers per "
                         "session; retry semantics are UNVERIFIED",
    documented_capabilities=("read account", "read positions", "read orders",
                            "submit order", "cancel order",
                            "paper environment"),
    unverifiable_without_credentials=_COMMON_UNVERIFIABLE + (
        "that the local gateway process stays authenticated unattended",
        "whether the user's jurisdiction is eligible for an account"),
    notes="Requires a LOCAL GATEWAY PROCESS, which conflicts with this project's "
          "CPU-only local deployment in a way worth stating: the gateway is a "
          "long-running authenticated process that can place live orders, and it "
          "does not distinguish this application from any other client on the "
          "machine. That is an additional attack surface, not merely an "
          "inconvenience."))

register_adapter(BrokerAdapter(
    key="tradingview",
    name="TradingView (NOT a broker; listed to close the door)",
    docs_url="https://www.tradingview.com/broker-api-docs/",
    transport="n/a",
    verification="DOCUMENTED",
    environments=(),
    enabled=False,
    supports_idempotency="n/a",
    documented_capabilities=("none -- this is not an execution venue",),
    unverifiable_without_credentials=(
        "nothing; the finding is settled and negative",),
    notes="TradingView publishes a 'REST API Specification for Brokers', which "
          "is INBOUND: it specifies what a broker must implement so TradingView "
          "can display and route through it. It is not an API this application "
          "may call to trade. Registered as an explicit dead end because the "
          "existence of a document with 'Broker' and 'REST API' in its title is "
          "otherwise an invitation to a wrong conclusion. Separately, "
          "TradingView's terms PROHIBIT non-display machine use of its data "
          "(docs/legal/tradingview-terms-review.md), and its desktop app "
          "documents no local API."))

ADAPTERS: Mapping[str, BrokerAdapter] = MappingProxyType(_ADAPTERS)


def get_adapter(key: str) -> BrokerAdapter:
    try:
        return ADAPTERS[key]
    except KeyError:
        raise BrokerError(
            "unknown broker %r. Known: %s. An unregistered broker has not been "
            "reviewed, so it cannot be used."
            % (key, ", ".join(sorted(ADAPTERS))))


def enabled_adapters():
    """
    Returns [] as of 2026-08-12, deliberately.

    No adapter is VERIFIED, because verification requires credentials and a live
    round-trip. This is the SS.6.1 "verified broker adapter" prerequisite being
    unmet, reported by the code rather than asserted in a document.
    """
    return [a for a in ADAPTERS.values() if a.enabled]


def assert_adapter_usable(key: str, environment: str) -> BrokerAdapter:
    """
    Refuse any use of an adapter that is not verified, enabled, and mode-legal.

    Order of checks is deliberate: verification first, because an unverified
    adapter is unusable in EVERY mode, and reporting the mode problem first would
    invite someone to change the mode.
    """
    a = get_adapter(key)
    if environment not in ENVIRONMENTS:
        raise BrokerError(
            "unknown environment %r; allowed: %s. SS.6.3 requires paper and live "
            "accounts to have unambiguous identifiers, so there is no default."
            % (environment, ", ".join(ENVIRONMENTS)))
    if a.verification != "VERIFIED":
        raise BrokerError(
            "broker %r is at verification level %s, not VERIFIED. Unverifiable "
            "without credentials: %s"
            % (key, a.verification,
               "; ".join(a.unverifiable_without_credentials[:3])))
    if not a.enabled:
        raise BrokerError("broker %r is registered but not enabled" % (key,))
    if environment not in a.environments:
        raise BrokerError("broker %r does not offer a %s environment"
                          % (key, environment))
    # The mode gate is separate from and additional to the broker gate. Both must
    # pass; neither implies the other.
    require("submit_live_order" if environment == "LIVE"
            else "submit_paper_order")
    return a


def submit_order(*args, **kwargs):
    """
    Not implemented, on purpose.

    SS.6.2 requires a two-phase PREVIEW/COMMIT protocol with eleven preview steps
    and a short-lived confirmation token; SS.6.3 requires 21 mandatory controls
    including a kill switch, idempotency, and daily-loss limits. None of those
    exist yet. A submit path written before them would be a function that looks
    callable, and the only thing standing between it and a live order would be
    configuration.
    """
    raise NotImplementedError(
        "order submission is not implemented. SS.6.2 requires a two-phase "
        "preview/commit protocol and SS.6.3 requires 21 mandatory controls "
        "(idempotency key, kill switch, notional and loss limits, stale-quote "
        "guard, duplicate detection, tick and lot validation, ...); none are "
        "built. No broker adapter is VERIFIED and no market-data provider is "
        "licensed, so there is also nothing to price an order against.")


def read_account(*args, **kwargs):
    """
    Not implemented. Read-only, but still requires a working credential and an
    adapter nobody has authenticated, so implementing it now would produce a
    function whose first successful call happens in production.
    """
    raise NotImplementedError(
        "broker account reads are not implemented: no adapter has been "
        "authenticated. See assert_adapter_usable() for the gate they will pass "
        "through.")


def manifest() -> Dict[str, Any]:
    return {"adapters": [a.to_dict() for a in ADAPTERS.values()],
            "n_enabled": len(enabled_adapters()),
            "n_verified": sum(1 for a in ADAPTERS.values()
                              if a.verification == "VERIFIED"),
            "verification_levels": list(VERIFICATION_LEVELS),
            "environments": list(ENVIRONMENTS)}
