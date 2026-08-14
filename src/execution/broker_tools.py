"""
The SS.8.4 / 8.5 / 8.6 broker tool surface: reads, risk, and a preview that
cannot commit.

WHAT THIS MODULE IS FOR
-----------------------
SS.8.4 defines four broker READ tools, SS.8.5 three RISK tools, and SS.8.6 seven
WRITE tools. This module implements the parts that are real on this installation
and refuses the parts that are not -- and the split is not arbitrary:

  - ARGUMENT VALIDATION is real. It needs no broker and no credential, and it is
    where a malformed order is cheapest to stop.
  - DETERMINISTIC ARITHMETIC is real. position_size is a calculation, not a
    network call, and SS.8.5 specifies fields the existing calc.returns_risk
    version does not have (fees, slippage, contract_multiplier).
  - THE PREVIEW ENVELOPE is real: SS.8.6 lists ten fields it must return, and
    each one either has a value or is explicitly UNKNOWN.
  - EVERY NETWORK READ AND EVERY WRITE REFUSES, because no broker adapter is
    VERIFIED. Not one has been authenticated with a credential.

WHY THE READ TOOLS VALIDATE BEFORE THEY REFUSE
----------------------------------------------
It would be shorter to make all four read tools raise NotImplementedError on the
first line. It would also be untestable in the way that matters: when an adapter
IS eventually verified, the validation is the code that stops
broker_positions(account_id="", environment="live") from reaching it. Writing the
refusal first and the validation later means the validation's first execution
happens against a real account. So the argument checks run first, are tested now,
and the refusal comes after them.

The ordering has a second consequence that is the actual reason for it: a caller
who passes environment="live" gets told their argument is unrecognised (SS.8.4
says `paper|live`, and this module accepts those spellings) BEFORE being told the
adapter is unverified. If the refusal came first, a caller would learn only that
the adapter is missing, and would "fix" the wrong problem.

WHY THERE IS NO ORDER SUBMISSION HERE AT ALL
--------------------------------------------
SS.6.2 requires a two-phase protocol: eleven PREVIEW steps, then a COMMIT gated
on a short-lived confirmation token. SS.6.3 requires twenty-one mandatory
controls -- idempotency key, kill switch, notional and daily-loss limits,
stale-quote guard, duplicate detection, tick and lot validation, and the rest.
MEASURED against this repository: the kill switch does not exist, there is no
audit log, there is no idempotency store, and no order-rate limiter.

So `place_order`, `modify_order`, `cancel_order`, `cancel_all_orders` and
`flatten_position` raise NotImplementedError with the specific missing
prerequisites named. A function that looks callable, with only configuration
between it and a live order, is the failure mode SS.6 is written to prevent.

THE ONE DESIGN DECISION IN HERE THAT IS EASY TO GET WRONG
---------------------------------------------------------
`pre_trade_risk_check` must run sixteen named checks (SS.8.5, MEASURED: sixteen
bullets). On this installation most of them CANNOT be evaluated -- buying power,
margin and daily loss all need broker state nobody can read. The tempting
implementation returns "passed: 3, skipped: 13" and an overall PASS.

That would be the worst function in the project. An unevaluable check is not a
passing check, and a risk report whose overall verdict ignores what it could not
examine is worse than no report, because it manufactures the confidence a risk
check exists to withhold. So:

  - Every check returns PASS, FAIL, or UNKNOWN.
  - The overall verdict is REFUSE unless ALL sixteen are PASS.
  - UNKNOWN and FAIL are kept distinct, because they need different follow-up:
    UNKNOWN means "no data" (get the data), FAIL means "measured, and it is bad".
  - The kill switch is FAIL, not UNKNOWN. There is no kill switch to read, and a
    known absence is a determinate fact. Recording it as UNKNOWN would suggest
    that finding the right credential might reveal one.

Stdlib only.
"""

from __future__ import annotations

import datetime
import hashlib
import math
from types import MappingProxyType
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from execution.brokers import (ADAPTERS, BrokerError, assert_adapter_usable,
                               enabled_adapters)
from execution.mode import (ExecutionModeError, current_mode, is_permitted,
                            require, unmet_live_prerequisites)


class BrokerToolError(RuntimeError):
    """
    A broker tool call could not be answered as asked.

    RuntimeError rather than ValueError, and deliberately NOT a subclass of
    BrokerError: this is raised by the tool surface, and a caller that catches
    BrokerError to handle "the adapter is unusable" must not also silently
    swallow "your order fields are contradictory".
    """


# ---------------------------------------------------------------------------
# Vocabularies, quoted from the spec rather than invented.
# ---------------------------------------------------------------------------

#: SS.8.4/8.6 spell the environment `paper|live` in lower case, while
#: execution.brokers.ENVIRONMENTS uses PAPER/LIVE. Both spellings are accepted on
#: input and normalised UPWARD to the broker module's form, so there is exactly
#: one representation in the rest of the system. What is NOT accepted is a
#: default: SS.6.3 requires "paper and live accounts must have unambiguous
#: identifiers", and an omitted environment defaulting to paper is precisely the
#: ambiguity that lets a live order be placed by a caller who thought otherwise.
ENVIRONMENT_INPUT: Mapping[str, str] = MappingProxyType({
    "paper": "PAPER", "PAPER": "PAPER", "live": "LIVE", "LIVE": "LIVE",
})

#: SS.8.6 verbatim: "buy|sell|sell_short|buy_to_cover".
SIDES: Tuple[str, ...] = ("buy", "sell", "sell_short", "buy_to_cover")

#: SS.8.6 verbatim: "market|limit|stop|stop_limit|trailing_stop".
ORDER_TYPES: Tuple[str, ...] = ("market", "limit", "stop", "stop_limit",
                                "trailing_stop")

#: SS.8.6 verbatim: "day|gtc|ioc|fok".
TIME_IN_FORCE: Tuple[str, ...] = ("day", "gtc", "ioc", "fok")

#: Which price fields each order type REQUIRES, and which it forbids. Derived
#: from the order types themselves rather than from a provider's API: a limit
#: order with no limit price is not an order, and a market order carrying a limit
#: price is a caller who thinks they are sending something else. Both are refused
#: rather than normalised, because normalising either one silently changes what
#: the user asked for.
PRICE_FIELDS: Mapping[str, Tuple[Tuple[str, ...], Tuple[str, ...]]] = \
    MappingProxyType({
        # order_type: (required, forbidden)
        "market": ((), ("limit_price", "stop_price")),
        "limit": (("limit_price",), ("stop_price",)),
        "stop": (("stop_price",), ("limit_price",)),
        "stop_limit": (("limit_price", "stop_price"), ()),
        # A trailing stop is parameterised by an OFFSET, which SS.8.6's field list
        # does not carry. Rather than repurpose stop_price to mean "offset" -- two
        # meanings for one field, the exact ambiguity that produces a wrong order
        # -- this is refused as unsupported. See preview_order.
        "trailing_stop": ((), ()),
    })

#: The sixteen SS.8.5 pre-trade checks, in the order the spec lists them.
#: MEASURED: sixteen bullets. The count is asserted in the test suite, because a
#: risk check that quietly runs fifteen of sixteen is the failure this list
#: exists to prevent.
RISK_CHECKS: Tuple[str, ...] = (
    "buying_power", "margin", "concentration", "leverage", "daily_loss",
    "notional", "price_deviation", "quote_freshness", "liquidity", "tick_size",
    "lot_size", "trading_session", "duplicate_order",
    "short_sale_restrictions", "user_limits", "kill_switch_status",
)

#: A check outcome. Three values, not two, and not a bool: see the module
#: docstring on why UNKNOWN may never collapse into either PASS or FAIL.
CHECK_STATUS: Tuple[str, ...] = ("PASS", "FAIL", "UNKNOWN")

#: SS.6.2 Phase A, MEASURED: eleven numbered steps. Recorded so the preview can
#: report which of them it actually performed, rather than implying all eleven.
PREVIEW_STEPS: Tuple[str, ...] = (
    "resolve instrument identity",
    "verify exchange and asset class",
    "verify account and environment",
    "verify market status",
    "retrieve a fresh authorized quote",
    "validate quantity, side, order type, price, currency, time-in-force",
    "calculate notional, fees, slippage, margin, leverage, risk",
    "run deterministic pre-trade checks",
    "generate an immutable preview",
    "generate a short-lived confirmation token",
    "present the complete preview to the user",
)

#: SS.8.6, MEASURED: ten fields preview_order must return.
PREVIEW_FIELDS: Tuple[str, ...] = (
    "preview_id", "environment", "estimated_notional", "fees", "margin_impact",
    "slippage", "risk_check", "quote_timestamp", "preview_expiry",
    "confirmation_challenge",
)

#: SS.6.3, MEASURED: twenty-one mandatory controls for write-capable tools, each
#: mapped to whether THIS repository provides it. Every False is a fact about the
#: code, checkable by looking; none is pessimism.
MANDATORY_CONTROLS: Mapping[str, Tuple[bool, str]] = MappingProxyType({
    "idempotency key": (False, "no idempotency store exists"),
    "paper/live environment": (
        True, "execution.brokers.ENVIRONMENTS, required and never defaulted"),
    "account allowlist": (False, "no account has been registered or verified"),
    "instrument allowlist or denylist": (False, "not built"),
    "maximum order notional": (False, "no user limits are configured"),
    "maximum daily notional": (
        False, "would require durable cross-session state; none exists"),
    "maximum position size": (False, "no user limits are configured"),
    "maximum portfolio leverage": (
        False, "requires broker portfolio state, which cannot be read"),
    "maximum daily loss": (
        False, "requires realised P&L for the day; no audit log exists"),
    "maximum concentration": (
        False, "requires the full position set, which cannot be read"),
    "order-rate limit": (False, "not built"),
    "price-deviation guard": (
        True, "implemented in pre_trade_risk_check when a reference price is "
              "supplied; UNKNOWN when it is not"),
    "stale-quote guard": (
        True, "implemented in pre_trade_risk_check from the quote's own "
              "timestamp"),
    "duplicate-order detection": (
        False, "requires a record of submitted orders; none exists"),
    "trading-hours validation": (
        False, "requires an authoritative market calendar; the free market-data "
               "tier reports market_status=UNKNOWN"),
    "tick-size validation": (
        False, "requires instrument reference data; no source is licensed"),
    "lot-size validation": (
        False, "requires instrument reference data; no source is licensed"),
    "short-sale validation": (
        False, "requires borrow/locate data; no source"),
    "margin validation": (
        False, "requires broker margin state, which cannot be read"),
    "audit event ID": (False, "no audit log exists"),
    "kill-switch status": (False, "NO KILL SWITCH EXISTS -- a known absence"),
})


def unmet_controls() -> Tuple[str, ...]:
    """
    The SS.6.3 controls this installation does not provide.

    Non-empty means no write-capable broker tool may be implemented, regardless
    of mode or configuration.
    """
    return tuple(n for n, (ok, _) in MANDATORY_CONTROLS.items() if not ok)


# ---------------------------------------------------------------------------
# Argument validation. Shared by every tool below, tested on its own.
# ---------------------------------------------------------------------------

def _normalise_environment(environment: Any) -> str:
    """PAPER or LIVE, or a refusal. There is no default."""
    if environment is None or environment == "":
        raise BrokerToolError(
            "environment is required and has no default. SS.6.3: 'Paper and "
            "live accounts must have unambiguous identifiers'. A default would "
            "let a caller who omitted the field discover which one they got "
            "from the fill.")
    if not isinstance(environment, str):
        raise BrokerToolError(
            "environment must be a string, got %s" % type(environment).__name__)
    if environment not in ENVIRONMENT_INPUT:
        raise BrokerToolError(
            "unknown environment %r; SS.8.4 spells it paper|live (PAPER/LIVE "
            "also accepted). Refusing rather than guessing: the two differ by "
            "whether real money moves." % (environment,))
    return ENVIRONMENT_INPUT[environment]


def _validate_account_id(account_id: Any) -> str:
    """A non-empty account identifier, with no whitespace surprises."""
    if not isinstance(account_id, str) or not account_id.strip():
        raise BrokerToolError(
            "account_id must be a non-empty string; got %r. SS.6.3 requires "
            "unambiguous account identifiers, and an empty one would let a "
            "broker adapter choose a default account."
            % (account_id,))
    if account_id != account_id.strip():
        raise BrokerToolError(
            "account_id %r has leading or trailing whitespace. Refusing rather "
            "than trimming: ' 123' and '123' may be different accounts at the "
            "broker, and silently equating them is how an order reaches the "
            "wrong one." % (account_id,))
    return account_id


def _finite_number(value: Any, field: str) -> float:
    """
    A real, finite number. Bools are refused explicitly.

    `isinstance(True, int)` is True in Python, so a bool reaches arithmetic as
    1 or 0 without complaint -- quantity=True would become one share. That is a
    caller error worth refusing rather than interpreting.
    """
    if isinstance(value, bool):
        raise BrokerToolError(
            "%s must be a number, got a bool (%r). Python would treat it as %d "
            "and the order would be accepted." % (field, value, int(value)))
    if not isinstance(value, (int, float)):
        raise BrokerToolError("%s must be a number, got %s"
                             % (field, type(value).__name__))
    f = float(value)
    if f != f:
        raise BrokerToolError(
            "%s is NaN. Every comparison against NaN is False, so a NaN "
            "quantity passes a max-size check silently." % field)
    if f in (float("inf"), float("-inf")):
        raise BrokerToolError("%s is %r; a non-finite value cannot size an "
                             "order" % (field, f))
    return f


def _positive_number(value: Any, field: str) -> float:
    f = _finite_number(value, field)
    if f <= 0:
        raise BrokerToolError(
            "%s must be greater than zero, got %r. A zero or negative %s is "
            "not a smaller order; it is a different instruction expressed by "
            "accident." % (field, f, field))
    return f


def _iso_utc(when: Optional[datetime.datetime] = None) -> str:
    if when is None:
        when = datetime.datetime.now(datetime.timezone.utc)
    if when.tzinfo is None:
        raise BrokerToolError(
            "refusing a naive datetime: it would silently take the reader's "
            "local zone, and this project's user is at +03:30 while the venue "
            "is in US/Eastern")
    return when.astimezone(datetime.timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# SS.8.4 -- broker read-only tools.
# ---------------------------------------------------------------------------

def _read_tool(name: str, account_id: Any, environment: Any,
               extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    The shared body of all four SS.8.4 read tools.

    Validation runs FIRST and is real. The adapter gate runs second and currently
    always refuses, because no adapter is VERIFIED -- but the refusal comes from
    execution.brokers.assert_adapter_usable rather than from a hardcoded raise
    here, so that when an adapter is eventually verified this code path does not
    need editing to start working.
    """
    account_id = _validate_account_id(account_id)
    env = _normalise_environment(environment)

    # The mode gate is checked separately from and in addition to the adapter
    # gate. A read of a LIVE account is a live-broker capability even though it
    # writes nothing: it requires a live credential, which is exactly the thing
    # SS.5.6 says must not be reachable from an unconfigured installation.
    require("read_broker_account")

    usable = [a.key for a in enabled_adapters()]
    if not usable:
        raise BrokerToolError(
            "%s cannot be answered: no broker adapter is enabled. All %d "
            "registered adapters are at verification level DOCUMENTED -- read "
            "from public documentation, never exercised with a credential -- and "
            "execution.brokers refuses to enable an adapter that is not "
            "VERIFIED. Reading documentation is not verification. "
            "(account_id=%s environment=%s)"
            % (name, len(ADAPTERS), account_id, env))

    # Unreachable today, and deliberately written anyway: this is the line that
    # will run first when an adapter is verified, and it must go through the same
    # gate as everything else rather than trusting `usable` above.
    adapter = assert_adapter_usable(usable[0], env)
    raise BrokerToolError(
        "%s: adapter %r is usable but this tool has no transport implementation "
        "yet. Refusing rather than returning an empty result, which would read "
        "as 'no positions' and is the most dangerous possible answer to "
        "broker_positions." % (name, adapter.key))


def broker_account_snapshot(account_id: Any, environment: Any) -> Dict[str, Any]:
    """SS.8.4 `broker_account_snapshot`. Refuses: no adapter is VERIFIED."""
    return _read_tool("broker_account_snapshot", account_id, environment)


def broker_positions(account_id: Any, environment: Any) -> Dict[str, Any]:
    """
    SS.8.4 `broker_positions`. Refuses: no adapter is VERIFIED.

    Note the refusal rather than an empty list. An empty position set is a
    meaningful answer -- "you hold nothing" -- and returning it when the truth is
    "nothing could be read" would invite a caller to conclude they are flat.
    """
    return _read_tool("broker_positions", account_id, environment)


def broker_open_orders(account_id: Any, environment: Any) -> Dict[str, Any]:
    """
    SS.8.4 `broker_open_orders`. Refuses: no adapter is VERIFIED.

    Same reasoning as broker_positions, and sharper: an empty open-order list
    read as fact could lead a caller to place a duplicate.
    """
    return _read_tool("broker_open_orders", account_id, environment)


def broker_executions(account_id: Any, environment: Any,
                      start: Any = None, end: Any = None) -> Dict[str, Any]:
    """
    SS.8.4 `broker_executions`. Refuses: no adapter is VERIFIED.

    `start` and `end` are validated before the refusal, because a reversed window
    is a caller error that will otherwise be discovered against a live account.
    """
    if start is not None and not isinstance(start, str):
        raise BrokerToolError("start must be an ISO-8601 string or None")
    if end is not None and not isinstance(end, str):
        raise BrokerToolError("end must be an ISO-8601 string or None")
    parsed = {}
    for label, raw in (("start", start), ("end", end)):
        if raw is None:
            continue
        try:
            parsed[label] = datetime.datetime.fromisoformat(raw)
        except ValueError as exc:
            raise BrokerToolError("%s is not ISO-8601: %r (%s)"
                                  % (label, raw, exc))
    if "start" in parsed and "end" in parsed:
        a, b = parsed["start"], parsed["end"]
        if (a.tzinfo is None) != (b.tzinfo is None):
            raise BrokerToolError(
                "start and end must both be timezone-aware or both naive; "
                "comparing one of each raises in Python and mixing them "
                "silently would shift the window by the local offset")
        if a > b:
            raise BrokerToolError(
                "start (%s) is after end (%s); an inverted window would return "
                "nothing and read as 'no executions'" % (start, end))
    return _read_tool("broker_executions", account_id, environment,
                      extra=parsed)


# ---------------------------------------------------------------------------
# SS.8.5 -- risk tools.
# ---------------------------------------------------------------------------

def position_size(account_equity: Any, risk_budget: Any, entry: Any, stop: Any,
                  fees: Any = 0.0, slippage: Any = 0.0,
                  contract_multiplier: Any = 1.0,
                  currency: str = "USD") -> Dict[str, Any]:
    """
    SS.8.5 `position_size`: quantity such that being stopped out costs at most
    `risk_budget`, INCLUDING fees, slippage and the contract multiplier.

    WHY THIS IS NOT calc.returns_risk.position_size
    -----------------------------------------------
    That function exists, is tested, and is deliberately left alone. It takes
    `risk_pct` (a fraction of equity) and its own docstring states it "ignores
    slippage, gaps, and fees". SS.8.5 specifies a DIFFERENT signature --
    `risk_budget` as an absolute amount, plus `fees`, `slippage` and
    `contract_multiplier` -- and those three are not decoration: on a futures
    contract with a multiplier of 50 they change the answer by a factor of fifty.

    Two functions with the same name computing different things is a real hazard,
    so this one lives in a different module, is named for its spec section, and
    reports which inputs it consumed. It does NOT delegate to the calc version,
    because delegating and then adjusting would produce a number whose derivation
    no reader could follow.

    THE DIRECTION OF THE ADJUSTMENTS
    Fees and slippage make the loss per unit LARGER, so they REDUCE the size.
    Getting the sign wrong here produces a position bigger than the risk budget
    allows, which is the one error worth being careful about, so the arithmetic is
    written out in the returned `formula` and the per-unit loss is returned
    alongside for a reader to check by hand.
    """
    equity = _positive_number(account_equity, "account_equity")
    budget = _positive_number(risk_budget, "risk_budget")
    entry_p = _positive_number(entry, "entry")
    # A stop of exactly zero is refused rather than treated as "no stop": a stop
    # at zero implies risking the entire position value, which is a legitimate
    # thing to want and an illegitimate thing to express by omission.
    stop_p = _finite_number(stop, "stop")
    if stop_p < 0:
        raise BrokerToolError("stop must not be negative, got %r" % (stop_p,))
    fee = _finite_number(fees, "fees")
    slip = _finite_number(slippage, "slippage")
    if fee < 0 or slip < 0:
        raise BrokerToolError(
            "fees and slippage must be zero or positive (got fees=%r "
            "slippage=%r). A negative cost would INCREASE the position size, "
            "which is the one direction this calculation must never be wrong in."
            % (fee, slip))
    mult = _positive_number(contract_multiplier, "contract_multiplier")
    if not isinstance(currency, str) or not currency.strip():
        raise BrokerToolError("currency must be a non-empty string")

    if budget > equity:
        raise BrokerToolError(
            "risk_budget (%r) exceeds account_equity (%r). Refusing rather than "
            "capping: a caller who passed a percentage where an absolute amount "
            "was expected (0.02 vs 2%% of 100000) needs to know, and silently "
            "capping would size the whole account." % (budget, equity))

    price_risk = abs(entry_p - stop_p)
    if price_risk == 0:
        raise BrokerToolError(
            "stop equals entry (%r), so the risk per unit is zero and the "
            "position size is unbounded. Refusing rather than returning a very "
            "large number." % (entry_p,))

    # Per-unit loss if stopped out: the price move, scaled by the contract
    # multiplier, plus the round-trip costs.
    loss_per_unit = price_risk * mult + fee + slip
    if loss_per_unit <= 0:
        raise BrokerToolError(
            "computed a non-positive loss per unit (%r); refusing"
            % (loss_per_unit,))
    quantity = budget / loss_per_unit

    return {
        "tool": "position_size",
        "quantity": quantity,
        "currency": currency.strip(),
        "formula": "risk_budget / (|entry - stop| * contract_multiplier "
                   "+ fees + slippage)",
        "inputs": {"account_equity": equity, "risk_budget": budget,
                   "entry": entry_p, "stop": stop_p, "fees": fee,
                   "slippage": slip, "contract_multiplier": mult},
        "intermediates": {"price_risk_per_unit": price_risk,
                          "loss_per_unit": loss_per_unit,
                          "risk_budget_as_pct_of_equity": budget / equity},
        "status": "COMPUTED",
        "caveats": (
            "A stop is not a guarantee of the fill price. If the market gaps "
            "through the stop the realised loss exceeds risk_budget, and no "
            "position size prevents that.",
            "fees and slippage are the caller's ESTIMATES unless a broker "
            "supplied them; this installation has no broker connection, so "
            "they cannot be verified here.",
            "The result is not rounded to a tradeable lot: no instrument "
            "reference data is licensed, so the tick and lot sizes are UNKNOWN. "
            "Rounding to a whole number here would silently change the risk.",
        ),
    }


def portfolio_risk(positions: Any, prices: Any, base_currency: str = "USD",
                   method: str = "historical", confidence_level: Any = 0.95,
                   horizon_days: Any = 1, lookback: str = "") -> Dict[str, Any]:
    """
    SS.8.5 `portfolio_risk`. Validates its arguments, then refuses.

    WHY THIS REFUSES RATHER THAN COMPUTING
    The deterministic VaR machinery exists in calc.returns_risk and is tested.
    What is missing is not the arithmetic; it is the INPUT. A portfolio VaR needs
    a price history per instrument, and:

      - No broker connection exists, so the position set cannot be read.
      - The only enabled market-data provider is Alpha Vantage's free tier: 25
        requests per DAY, END_OF_DAY only, and quotes stamped
        trust_level=UNVERIFIED, which assert_usable_for("material_calculation")
        refuses outright.
      - Its permitted storage timeframes are UNKNOWN, so a price history cannot
        be accumulated across days.

    A VaR number computed from a caller-supplied dict would be arithmetic on
    unverified inputs presented as a risk measurement. The arguments are still
    validated, because that validation is what will guard the real thing.
    """
    if not isinstance(positions, (list, tuple)):
        raise BrokerToolError("positions must be a list, got %s"
                             % type(positions).__name__)
    if not isinstance(prices, dict):
        raise BrokerToolError("prices must be an object keyed by instrument, "
                             "got %s" % type(prices).__name__)
    if method not in ("historical", "parametric", "monte_carlo"):
        raise BrokerToolError(
            "unknown method %r; SS.8.5 allows historical|parametric|"
            "monte_carlo" % (method,))
    conf = _finite_number(confidence_level, "confidence_level")
    if not 0.0 < conf < 1.0:
        raise BrokerToolError(
            "confidence_level must be a fraction strictly between 0 and 1, got "
            "%r. 95 is not 0.95, and accepting both would make a 95%% VaR "
            "indistinguishable from a 9500%% one." % (conf,))
    horizon = _finite_number(horizon_days, "horizon_days")
    if horizon <= 0 or horizon != int(horizon):
        raise BrokerToolError(
            "horizon_days must be a positive whole number, got %r" % (horizon,))
    if not isinstance(base_currency, str) or not base_currency.strip():
        raise BrokerToolError("base_currency must be a non-empty string")
    if not isinstance(lookback, str):
        raise BrokerToolError("lookback must be a string")

    raise BrokerToolError(
        "portfolio_risk cannot be computed on this installation. The VaR and "
        "expected-shortfall arithmetic exists in calc.returns_risk; what is "
        "missing is trustworthy INPUT. No broker connection exists so the "
        "position set cannot be read; the only enabled market-data provider is "
        "a free tier limited to 25 requests per DAY and END_OF_DAY prices whose "
        "trust_level is UNVERIFIED (refused for material calculations); and its "
        "permitted storage timeframes are UNKNOWN, so a price history cannot be "
        "accumulated. Arguments were validated (method=%s confidence=%r "
        "horizon=%d base=%s, %d positions, %d priced instruments), and a number "
        "computed from unverified inputs would be a risk measurement in name "
        "only." % (method, conf, int(horizon), base_currency.strip(),
                   len(positions), len(prices)))


def pre_trade_risk_check(account_id: Any, environment: Any,
                         order_draft: Any = None, quote_id: Any = None,
                         risk_policy_version: str = "",
                         reference_price: Any = None,
                         quote_timestamp: Any = None,
                         now: Optional[datetime.datetime] = None,
                         max_quote_age_seconds: int = 60) -> Dict[str, Any]:
    """
    SS.8.5 `pre_trade_risk_check`: run all sixteen checks and report honestly.

    THE RULE THIS FUNCTION EXISTS TO ENFORCE
    An unevaluable check is NOT a passing check. Most of the sixteen need broker
    state that cannot be read here, so they return UNKNOWN -- and the overall
    verdict is REFUSE unless every one of the sixteen is PASS. A function that
    reported "3 passed, 13 skipped, overall PASS" would manufacture exactly the
    confidence a pre-trade check is supposed to withhold.

    FAIL AND UNKNOWN ARE KEPT APART ON PURPOSE
    UNKNOWN means "no data; go and get it". FAIL means "measured, and it is bad".
    kill_switch_status is FAIL, not UNKNOWN: there is no kill switch in this
    repository, and a known absence is determinate. Calling it UNKNOWN would
    suggest that the right credential might reveal one.

    The two checks that CAN be evaluated here -- price_deviation and
    quote_freshness -- are evaluated from data the caller supplies, and they
    return UNKNOWN when it is absent rather than PASS.
    """
    account_id = _validate_account_id(account_id)
    env = _normalise_environment(environment)
    if order_draft is None:
        order_draft = {}
    if not isinstance(order_draft, dict):
        raise BrokerToolError("order_draft must be an object, got %s"
                             % type(order_draft).__name__)
    if not isinstance(risk_policy_version, str):
        raise BrokerToolError("risk_policy_version must be a string")

    results: Dict[str, Dict[str, str]] = {}

    def record(name: str, status: str, detail: str) -> None:
        if name not in RISK_CHECKS:
            raise BrokerToolError("unknown risk check %r" % (name,))
        if status not in CHECK_STATUS:
            raise BrokerToolError("unknown check status %r" % (status,))
        results[name] = {"status": status, "detail": detail}

    # -- the thirteen that need broker or reference state ------------------
    _no_broker = ("no broker adapter is VERIFIED, so this cannot be read from "
                  "the account")
    record("buying_power", "UNKNOWN", _no_broker)
    record("margin", "UNKNOWN", _no_broker)
    record("leverage", "UNKNOWN", _no_broker)
    record("concentration", "UNKNOWN",
           "requires the full position set; " + _no_broker)
    record("daily_loss", "UNKNOWN",
           "requires realised P&L for the session; no audit log exists")
    record("duplicate_order", "UNKNOWN",
           "requires a record of orders already submitted; none is kept")
    record("liquidity", "UNKNOWN",
           "requires order-book or average-volume data; no licensed source")
    record("tick_size", "UNKNOWN",
           "requires instrument reference data; no licensed source")
    record("lot_size", "UNKNOWN",
           "requires instrument reference data; no licensed source")
    record("short_sale_restrictions", "UNKNOWN",
           "requires borrow/locate and restricted-list data; no source")
    record("trading_session", "UNKNOWN",
           "requires an authoritative market calendar. The enabled free tier "
           "reports market_status=UNKNOWN, which is honest and unusable here")
    record("user_limits", "UNKNOWN",
           "no user limits are configured; an absent limit is not a satisfied "
           "one")

    # -- notional: computable only if the draft carries the numbers ---------
    qty = order_draft.get("quantity")
    px = order_draft.get("limit_price", order_draft.get("price"))
    if qty is None or px is None:
        record("notional", "UNKNOWN",
               "order_draft lacks quantity and/or a price, so the notional "
               "cannot be computed; a market order has no price until it fills")
    else:
        try:
            notional = _positive_number(qty, "quantity") * _positive_number(
                px, "price")
        except BrokerToolError as exc:
            record("notional", "FAIL", "notional is not computable: %s" % exc)
        else:
            record("notional", "UNKNOWN",
                   "notional computes to %.4f, but no maximum-order-notional "
                   "limit is configured, so there is nothing to check it "
                   "against" % notional)

    # -- price_deviation: evaluable when a reference price is supplied ------
    if reference_price is None or px is None:
        record("price_deviation", "UNKNOWN",
               "needs both an order price and a reference price; %s missing"
               % ("reference_price" if reference_price is None else "order price"))
    else:
        ref = _positive_number(reference_price, "reference_price")
        order_px = _positive_number(px, "order price")
        dev = abs(order_px - ref) / ref
        if dev > 0.05:
            record("price_deviation", "FAIL",
                   "order price %.4f deviates %.2f%% from the reference %.4f, "
                   "beyond the 5%% tolerance. A fat-fingered price is the "
                   "cheapest large loss available." % (order_px, dev * 100, ref))
        else:
            record("price_deviation", "PASS",
                   "order price %.4f is %.2f%% from the reference %.4f, within "
                   "the 5%% tolerance" % (order_px, dev * 100, ref))

    # -- quote_freshness: evaluable from the quote's own timestamp ---------
    if quote_timestamp is None:
        record("quote_freshness", "UNKNOWN",
               "no quote timestamp supplied. Note that the enabled provider is "
               "END_OF_DAY only, so a fresh quote is not obtainable here at all")
    else:
        if not isinstance(quote_timestamp, datetime.datetime):
            raise BrokerToolError(
                "quote_timestamp must be a datetime, got %s"
                % type(quote_timestamp).__name__)
        if quote_timestamp.tzinfo is None:
            raise BrokerToolError(
                "quote_timestamp is naive; refusing to guess a zone, because "
                "the error would be silent and the size of it would equal the "
                "offset between the reader and the venue")
        ref_now = now or datetime.datetime.now(datetime.timezone.utc)
        if ref_now.tzinfo is None:
            raise BrokerToolError("now must be timezone-aware")
        age = (ref_now - quote_timestamp).total_seconds()
        if age < 0:
            record("quote_freshness", "FAIL",
                   "the quote is timestamped %.1f seconds in the FUTURE, which "
                   "means a clock or timezone error somewhere; treating it as "
                   "fresh would be trusting the error" % (-age,))
        elif age > max_quote_age_seconds:
            record("quote_freshness", "FAIL",
                   "the quote is %.1f seconds old, over the %d second limit"
                   % (age, max_quote_age_seconds))
        else:
            record("quote_freshness", "PASS",
                   "the quote is %.1f seconds old, within the %d second limit"
                   % (age, max_quote_age_seconds))

    # -- the kill switch: a KNOWN absence, so FAIL rather than UNKNOWN -----
    record("kill_switch_status", "FAIL",
           "NO KILL SWITCH EXISTS in this repository. SS.6.3 requires one for "
           "any write-capable tool. This is a determinate fact about the code, "
           "not missing data, so it is FAIL and not UNKNOWN -- no credential "
           "will reveal a kill switch that was never written.")

    missing = [c for c in RISK_CHECKS if c not in results]
    if missing:
        raise BrokerToolError(
            "internal error: %d of the %d SS.8.5 checks were not evaluated "
            "(%s). A risk report missing a check is the failure this function "
            "exists to prevent." % (len(missing), len(RISK_CHECKS),
                                    ", ".join(missing)))

    n_pass = sum(1 for r in results.values() if r["status"] == "PASS")
    n_fail = sum(1 for r in results.values() if r["status"] == "FAIL")
    n_unknown = sum(1 for r in results.values() if r["status"] == "UNKNOWN")
    verdict = "PASS" if n_pass == len(RISK_CHECKS) else "REFUSE"

    return {
        "tool": "pre_trade_risk_check",
        "account_id": account_id,
        "environment": env,
        "quote_id": quote_id,
        "risk_policy_version": risk_policy_version or "NONE CONFIGURED",
        "checks": results,
        "n_checks": len(RISK_CHECKS),
        "n_pass": n_pass,
        "n_fail": n_fail,
        "n_unknown": n_unknown,
        "verdict": verdict,
        "verdict_reason": (
            "all %d checks passed" % len(RISK_CHECKS) if verdict == "PASS" else
            "%d of %d checks did not pass (%d FAIL, %d UNKNOWN). An unevaluable "
            "check is not a passing check, so the verdict is REFUSE."
            % (n_fail + n_unknown, len(RISK_CHECKS), n_fail, n_unknown)),
        "evaluated_at": _iso_utc(now),
    }


# ---------------------------------------------------------------------------
# SS.8.6 -- broker write tools. One preview, and five refusals.
# ---------------------------------------------------------------------------

def _validate_order_fields(instrument_id: Any, side: Any, quantity: Any,
                           order_type: Any, limit_price: Any, stop_price: Any,
                           time_in_force: Any, extended_hours: Any,
                           client_order_id: Any) -> Dict[str, Any]:
    """
    SS.6.2 Phase A step 6: "Validate quantity, side, order type, price,
    currency, and time-in-force."

    Every refusal here is cheaper than the same mistake reaching a broker, and all
    of it runs with no credential and no network. This is the part of the order
    path that is fully real on this installation.
    """
    if not isinstance(instrument_id, str) or not instrument_id.strip():
        raise BrokerToolError("instrument_id must be a non-empty string")
    if side not in SIDES:
        raise BrokerToolError(
            "unknown side %r; SS.8.6 allows %s. Note that sell and sell_short "
            "are different instructions with different margin and borrow "
            "consequences, so neither is a synonym for the other."
            % (side, "|".join(SIDES)))
    qty = _positive_number(quantity, "quantity")
    if order_type not in ORDER_TYPES:
        raise BrokerToolError("unknown order_type %r; SS.8.6 allows %s"
                             % (order_type, "|".join(ORDER_TYPES)))
    if time_in_force not in TIME_IN_FORCE:
        raise BrokerToolError("unknown time_in_force %r; SS.8.6 allows %s"
                             % (time_in_force, "|".join(TIME_IN_FORCE)))
    if not isinstance(extended_hours, bool):
        raise BrokerToolError(
            "extended_hours must be a bool, got %s. A truthy string like "
            "'false' would enable extended-hours trading."
            % type(extended_hours).__name__)
    if not isinstance(client_order_id, str) or not client_order_id.strip():
        raise BrokerToolError(
            "client_order_id must be a non-empty string: it is how a duplicate "
            "submission is recognised, and an absent one makes duplicate "
            "detection impossible")

    # A trailing stop needs an offset, and SS.8.6's field list has nowhere to put
    # one. Refused rather than reinterpreting stop_price as an offset.
    if order_type == "trailing_stop":
        raise BrokerToolError(
            "trailing_stop is not supported here. It is parameterised by a "
            "trailing OFFSET (amount or percent), and the SS.8.6 field list "
            "carries only limit_price and stop_price. Reusing stop_price to mean "
            "'offset' would give one field two meanings, and the resulting order "
            "would differ from the one the caller described.")

    required, forbidden = PRICE_FIELDS[order_type]
    supplied = {"limit_price": limit_price, "stop_price": stop_price}
    prices: Dict[str, float] = {}
    for field in required:
        if supplied[field] is None:
            raise BrokerToolError(
                "a %s order requires %s; without it the order is not fully "
                "specified and a broker would either reject it or fill it at a "
                "price nobody chose" % (order_type, field))
        prices[field] = _positive_number(supplied[field], field)
    for field in forbidden:
        if supplied[field] is not None:
            raise BrokerToolError(
                "a %s order must not carry %s (got %r). Refusing rather than "
                "ignoring it: a caller who supplied it believes it will be "
                "honoured, and silently dropping it changes their order."
                % (order_type, field, supplied[field]))

    # A stop_limit whose limit is on the wrong side of its stop is a common and
    # expensive error, but which side is "wrong" depends on the direction.
    if order_type == "stop_limit":
        lp, sp = prices["limit_price"], prices["stop_price"]
        buying = side in ("buy", "buy_to_cover")
        if buying and lp < sp:
            raise BrokerToolError(
                "a %s stop_limit with limit_price %.4f below stop_price %.4f "
                "can never fill: the stop triggers at or above %.4f and the "
                "limit refuses to pay it." % (side, lp, sp, sp))
        if not buying and lp > sp:
            raise BrokerToolError(
                "a %s stop_limit with limit_price %.4f above stop_price %.4f "
                "can never fill: the stop triggers at or below %.4f and the "
                "limit refuses to sell there." % (side, lp, sp, sp))

    return {"instrument_id": instrument_id.strip(), "side": side,
            "quantity": qty, "order_type": order_type,
            "limit_price": prices.get("limit_price"),
            "stop_price": prices.get("stop_price"),
            "time_in_force": time_in_force,
            "extended_hours": extended_hours,
            "client_order_id": client_order_id.strip()}


def preview_order(account_id: Any, environment: Any, instrument_id: Any,
                  side: Any, quantity: Any, order_type: Any,
                  time_in_force: str = "day", limit_price: Any = None,
                  stop_price: Any = None, extended_hours: Any = False,
                  client_order_id: str = "", reference_price: Any = None,
                  quote_timestamp: Any = None,
                  now: Optional[datetime.datetime] = None) -> Dict[str, Any]:
    """
    SS.8.6 `preview_order`: return all ten required fields, honestly labelled.

    WHY A PREVIEW IS ALLOWED HERE AT ALL
    `preview_order` is the one order-path capability granted in ANALYSIS_ONLY
    (execution.mode.CAPABILITIES), and that is right: a preview changes nothing.
    Its value is precisely that it can be produced and read before anything is
    committed.

    WHAT THE PREVIEW MAY NOT DO, AND HOW THAT IS ENFORCED
    A preview that returned a confirmation TOKEN would be one string away from a
    commit. So the `confirmation_challenge` field carries an explanation of why no
    token was issued -- not a token, and not a placeholder that looks like one.
    `place_order` refuses unconditionally and does not read this structure at all,
    so no value returned here can authorise anything.

    HONEST FIELDS, NOT EMPTY ONES
    Of the ten fields SS.8.6 requires, five cannot be valued on this
    installation: fees, margin_impact and slippage need broker or venue data, and
    the estimated notional needs a price a market order does not have. Each is
    returned as an explicit UNKNOWN with the reason, because a fee of 0.0 would
    read as free.
    """
    account_id = _validate_account_id(account_id)
    env = _normalise_environment(environment)
    if not client_order_id:
        raise BrokerToolError(
            "client_order_id is required. SS.6.3 requires duplicate-order "
            "detection, which is impossible if orders do not carry a "
            "caller-chosen identity.")
    fields = _validate_order_fields(instrument_id, side, quantity, order_type,
                                    limit_price, stop_price, time_in_force,
                                    extended_hours, client_order_id)

    # preview_order is permitted in every mode, but the check is performed rather
    # than assumed: if the capability table ever changes, this must refuse.
    require("preview_order")

    created = now or datetime.datetime.now(datetime.timezone.utc)
    if created.tzinfo is None:
        raise BrokerToolError("now must be timezone-aware")

    risk = pre_trade_risk_check(
        account_id=account_id, environment=env,
        order_draft=dict(fields, price=fields.get("limit_price")),
        quote_id=None, risk_policy_version="",
        reference_price=reference_price, quote_timestamp=quote_timestamp,
        now=created)

    # The preview ID is a content hash, so two previews of the same order at the
    # same instant are the same ID, and any changed field yields a different one.
    # SS.8.6 requires it to be IMMUTABLE; deriving it from the content means a
    # mutated preview cannot keep its identifier.
    material = "|".join([
        account_id, env, fields["instrument_id"], fields["side"],
        repr(fields["quantity"]), fields["order_type"],
        repr(fields["limit_price"]), repr(fields["stop_price"]),
        fields["time_in_force"], repr(fields["extended_hours"]),
        fields["client_order_id"], _iso_utc(created)])
    preview_id = "prv_" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]

    notional: Any
    if fields["limit_price"] is not None:
        notional = fields["quantity"] * fields["limit_price"]
        notional_note = ("quantity * limit_price. This is the notional AT THE "
                         "LIMIT; a fill at a better price makes it smaller, and "
                         "no fill makes it zero.")
    else:
        notional = None
        notional_note = ("UNKNOWN: a %s order has no price until it fills, and "
                         "no licensed live quote is available to estimate one "
                         "(the enabled provider is END_OF_DAY only)."
                         % fields["order_type"])

    preview = {
        # -- the ten SS.8.6 fields, in the order the spec lists them --------
        "preview_id": preview_id,
        "environment": env,
        "estimated_notional": notional,
        "fees": None,
        "margin_impact": None,
        "slippage": None,
        "risk_check": risk,
        "quote_timestamp": (_iso_utc(quote_timestamp)
                            if quote_timestamp is not None else None),
        "preview_expiry": _iso_utc(created + datetime.timedelta(seconds=60)),
        "confirmation_challenge": None,

        # -- everything else is context, and is named as such ---------------
        "tool": "preview_order",
        "account_id": account_id,
        "order": fields,
        "created_at": _iso_utc(created),
        "committable": False,
        "field_notes": {
            "estimated_notional": notional_note,
            "fees": "UNKNOWN: fees are a broker fact. No adapter is VERIFIED, "
                    "so none can be quoted. Returning 0.0 would read as free.",
            "margin_impact": "UNKNOWN: requires the account's margin state, "
                             "which cannot be read.",
            "slippage": "UNKNOWN: requires order-book depth or a measured fill "
                        "distribution. Neither is available, and a made-up "
                        "figure would flatter the trade.",
            "quote_timestamp": ("UNKNOWN: no quote was supplied and none can be "
                                "obtained fresh; the enabled provider is "
                                "END_OF_DAY only"
                                if quote_timestamp is None else
                                "as supplied by the caller"),
            "preview_expiry": "60 seconds from creation. Advisory only: nothing "
                              "consumes this preview, because there is no "
                              "commit path.",
            "confirmation_challenge": (
                "NO TOKEN ISSUED, deliberately. SS.6.2 Phase B allows a commit "
                "only against a valid short-lived token, and issuing one here "
                "would put a live order one string away. place_order() refuses "
                "unconditionally and never reads this structure."),
        },
        "steps_performed": PREVIEW_STEPS[5:9],
        "steps_not_performed": {
            PREVIEW_STEPS[0]: "no instrument reference data is licensed, so an "
                              "identity cannot be resolved -- the string is "
                              "passed through as given",
            PREVIEW_STEPS[1]: "exchange and asset class cannot be verified for "
                              "the same reason",
            PREVIEW_STEPS[2]: "the account cannot be verified: no broker "
                              "adapter is VERIFIED",
            PREVIEW_STEPS[3]: "market status is UNKNOWN; no authoritative "
                              "calendar is available",
            PREVIEW_STEPS[4]: "no fresh authorized quote is obtainable on the "
                              "enabled free tier",
            PREVIEW_STEPS[9]: "no confirmation token is issued, on purpose",
            PREVIEW_STEPS[10]: "presentation is the caller's responsibility",
        },
        "why_not_committable": (
            "SS.6.2 requires a two-phase preview/commit protocol and SS.6.3 "
            "requires 21 mandatory controls, of which %d are absent here "
            "(including the kill switch). The pre-trade check returned %s."
            % (len(unmet_controls()), risk["verdict"])),
    }
    missing = [f for f in PREVIEW_FIELDS if f not in preview]
    if missing:
        raise BrokerToolError(
            "internal error: the preview omits %d of the %d SS.8.6 required "
            "fields (%s)" % (len(missing), len(PREVIEW_FIELDS),
                             ", ".join(missing)))
    return preview


def _refuse_write(tool: str, spec: str, extra: str = "") -> None:
    """
    The shared refusal for every SS.8.6 write tool.

    One function so that no individual tool can drift into a softer refusal, and
    so the list of missing controls is MEASURED at call time rather than copied
    into five docstrings that would then disagree with each other.
    """
    unmet = unmet_controls()
    prereq = unmet_live_prerequisites()
    raise NotImplementedError(
        "%s is not implemented, and this is a design decision rather than an "
        "omission. %s SS.6.3 requires 21 mandatory controls for any "
        "write-capable broker tool; %d are absent here, including: %s. SS.6.1 "
        "lists prerequisites for live trading; %d are unmet. No broker adapter "
        "is VERIFIED, so there is nothing to submit to, and no market-data "
        "provider is licensed for machine use, so there is nothing to price "
        "against. A function that looked callable, with only configuration "
        "between it and a live order, is the failure SS.6 exists to prevent.%s"
        % (tool, spec, len(unmet), "; ".join(unmet[:6]), len(prereq),
           (" " + extra) if extra else ""))


def place_order(preview_id: Any = None, confirmation_token: Any = None,
                idempotency_key: Any = None) -> None:
    """SS.8.6 `place_order`. Refuses unconditionally."""
    _refuse_write(
        "place_order",
        "SS.8.6 requires explicit user confirmation, a valid unexpired preview, "
        "a displayed environment, no implicit retry, and a verified broker "
        "result.",
        "Note that no preview_id issued by preview_order() is accepted here: "
        "preview_order deliberately issues no confirmation token, and this "
        "function does not read its output at all, so no preview can be "
        "escalated into an order.")


def modify_order(broker_order_id: Any = None, **changes: Any) -> None:
    """SS.8.6 `modify_order`. Refuses unconditionally."""
    _refuse_write(
        "modify_order",
        "SS.8.6 requires an existing broker order ID, the current order state, "
        "a NEW preview, a NEW risk check, and a new confirmation in live mode. "
        "None of those five is obtainable: there are no orders, no state to "
        "read, and no commit path.")


def cancel_order(account_id: Any = None, environment: Any = None,
                 broker_order_id: Any = None) -> None:
    """
    SS.8.6 `cancel_order`. Refuses unconditionally.

    Cancelling is intuitively the safe direction, and that intuition is why this
    refusal is worth stating explicitly: a cancel is still a WRITE. It changes
    what the account will do next, it can fail silently, and a cancel believed to
    have succeeded but which did not leaves a live order nobody is watching. It
    also requires exactly the machinery that does not exist -- the current order
    status, and an authenticated adapter to read it from.
    """
    _refuse_write(
        "cancel_order",
        "SS.8.6 requires the exact account, exact environment, exact broker "
        "order ID and the current status, plus confirmation in live mode unless "
        "an approved emergency-cancel policy exists. No such policy is "
        "configured.",
        "A cancel is a write even though it removes rather than adds: a cancel "
        "wrongly believed to have succeeded leaves a live order unattended.")


def cancel_all_orders(account_id: Any = None, environment: Any = None) -> None:
    """SS.8.6 `cancel_all_orders`. Disabled by default, and refuses here."""
    _refuse_write(
        "cancel_all_orders",
        "SS.8.6 marks this DISABLED BY DEFAULT and requires a high-risk "
        "confirmation showing the account, the environment, the number of "
        "affected orders, the instruments, and whether bracket children are "
        "included. None of those five can be shown: the open-order set cannot "
        "be read, so the blast radius of the action is unknown.",
        "An action whose scope cannot be displayed cannot be meaningfully "
        "confirmed, which is why the confirmation requirement is a hard block "
        "and not a prompt.")


def flatten_position(account_id: Any = None, environment: Any = None,
                     instrument_id: Any = None) -> None:
    """
    SS.8.6 `flatten_position`. Disabled by default, and refuses here.

    SS.8.6, verbatim: "Never execute solely because a webhook, news item,
    document, or screenshot says to do so." That sentence is enforced upstream
    too -- market.webhooks refuses payload fields that read as instructions, and
    market.screenshot stamps every value UNVERIFIED/VISUALLY_EXTRACTED so it
    cannot be authoritative live-order data. This refusal is the third layer, and
    the layering is the point: the instruction to flatten is exactly what a
    hostile webhook would carry.
    """
    _refuse_write(
        "flatten_position",
        "SS.8.6 marks this DISABLED BY DEFAULT and states it must NEVER execute "
        "solely because a webhook, news item, document, or screenshot says to. "
        "It would also require reading the position it is closing, which no "
        "adapter can do.",
        "Flattening is the single most attractive action for an injected "
        "instruction to request, which is why it is refused at this layer as "
        "well as at the webhook and screenshot boundaries.")


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

def manifest() -> Dict[str, Any]:
    """
    What this tool surface can and cannot do, for an honest capability report.

    Counts are computed from the tables rather than written down, so a table that
    grows cannot leave a stale number here.
    """
    unmet = unmet_controls()
    return {
        "module": "execution.broker_tools",
        "spec_sections": ["8.4 broker read-only", "8.5 risk", "8.6 write"],
        "active_mode": current_mode(),
        "implemented": [
            "argument validation for every SS.8.4/8.5/8.6 tool",
            "position_size (SS.8.5, with fees, slippage, contract_multiplier)",
            "pre_trade_risk_check (all %d checks reported, PASS/FAIL/UNKNOWN)"
            % len(RISK_CHECKS),
            "preview_order (all %d SS.8.6 fields, no confirmation token)"
            % len(PREVIEW_FIELDS),
        ],
        "refuses": {
            "broker_account_snapshot": "no VERIFIED adapter",
            "broker_positions": "no VERIFIED adapter",
            "broker_open_orders": "no VERIFIED adapter",
            "broker_executions": "no VERIFIED adapter",
            "portfolio_risk": "no trustworthy position or price input",
            "place_order": "SS.6.2 commit protocol absent",
            "modify_order": "SS.6.2 commit protocol absent",
            "cancel_order": "a cancel is a write; no adapter, no order state",
            "cancel_all_orders": "disabled by default; blast radius unknowable",
            "flatten_position": "disabled by default; never on an instruction "
                                "from a webhook, news item, document or "
                                "screenshot",
        },
        "n_risk_checks": len(RISK_CHECKS),
        "n_preview_fields": len(PREVIEW_FIELDS),
        "n_mandatory_controls": len(MANDATORY_CONTROLS),
        "n_controls_unmet": len(unmet),
        "controls_unmet": list(unmet),
        "n_live_prerequisites_unmet": len(unmet_live_prerequisites()),
        "kill_switch_exists": False,
        "can_submit_an_order": False,
        "why_not": (
            "%d of %d SS.6.3 mandatory controls are absent, no broker adapter is "
            "VERIFIED, and the SS.6.2 two-phase commit protocol is not built. "
            "None of these is reachable by configuration."
            % (len(unmet), len(MANDATORY_CONTROLS))),
    }
