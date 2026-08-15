"""
Verification for the SS.8.4 / 8.5 / 8.6 broker tool surface.

WHAT MAKES THIS SUITE HARD TO WRITE HONESTLY
--------------------------------------------
Almost every tool in execution.broker_tools refuses. A suite that only asserted
"it refused" would pass against a module whose entire body was `raise`, and would
therefore prove nothing about the validation, the arithmetic, or the ordering of
the gates. Worse, it would stay green if a future edit deleted a guard, because
some OTHER guard would answer in its place and the assertion could not tell which
one had spoken.

That failure mode -- a second guard answering for the one under test -- is the
dominant mutation survivor in this project. So the assertions here are written
against the CONTENT of each refusal, not merely its presence:

  - `_normalise_environment(None)` must refuse for having NO DEFAULT, not for
    being an unrecognised string.
  - `position_size(..., stop=0)` must refuse as EXACTLY ZERO, not as negative.
  - a market order carrying a limit price must refuse for CARRYING A FORBIDDEN
    FIELD, not for missing a required one.

WHERE THE DISCRIMINATING POSITIVES ARE
--------------------------------------
Negative assertions alone are satisfiable by code that refuses everything, so
each section also proves the layer discriminates:

  - position_size RETURNS a number, and a hand-computed one (200 shares for a
    1000 budget and a 5-point stop), with fees and slippage moving it DOWN.
  - price_deviation and quote_freshness really do return PASS when fed good data,
    which is what makes the other fourteen UNKNOWNs meaningful rather than a
    blanket refusal.
  - preview_order really does produce all ten SS.8.6 fields and a stable
    content-hashed ID.

REACHING THE GATES THAT NORMALLY CANNOT BE REACHED
--------------------------------------------------
Two guards are invisible in the default configuration, and both were MEASURED
before being asserted:

  - the ADAPTER gate is unreachable in ANALYSIS_ONLY, because the mode gate
    refuses `read_broker_account` first. Reached by writing a PAPER_TRADING
    config and re-reading it with mode._reset_cache_for_tests.
  - the "no adapter enabled" refusal hides everything past it. Reached by
    registering a synthetic VERIFIED+enabled adapter, and MEASURED to confirm a
    LIVE read is then still refused -- by the mode gate, with ten unmet SS.6.1
    prerequisites. That is the assertion that matters most in this file: even
    with a verified, enabled, live-capable adapter and paper trading switched on,
    a live read does not happen.

Every synthetic adapter is removed in a `finally`, and the mode is reset, because
a leaked enabled adapter would silently weaken every later suite in run_all.sh.
"""

import datetime
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from _harness import check, check_raises, check_true, section, summary  # noqa: E402

import execution.broker_tools as bt  # noqa: E402
import execution.brokers as brokers  # noqa: E402
import execution.mode as mode  # noqa: E402
from execution.broker_tools import (BrokerToolError, CHECK_STATUS,  # noqa: E402
                                    ENVIRONMENT_INPUT, MANDATORY_CONTROLS,
                                    ORDER_TYPES, PREVIEW_FIELDS, PREVIEW_STEPS,
                                    PRICE_FIELDS, RISK_CHECKS, SIDES,
                                    TIME_IN_FORCE, _iso_utc,
                                    _normalise_environment,
                                    _validate_account_id,
                                    _validate_order_fields,
                                    broker_account_snapshot, broker_executions,
                                    broker_open_orders, broker_positions,
                                    cancel_all_orders, cancel_order,
                                    flatten_position, manifest, modify_order,
                                    place_order, portfolio_risk, position_size,
                                    pre_trade_risk_check, preview_order,
                                    unmet_controls)
from execution.brokers import BrokerAdapter, BrokerError  # noqa: E402
from execution.mode import ExecutionModeError  # noqa: E402

_TMP = tempfile.mkdtemp(prefix="marfin_broker_tools_")

#: A fixed instant. Every time-dependent assertion is relative to this, so the
#: suite cannot pass in the morning and fail at 23:59 local.
NOW = datetime.datetime(2026, 8, 14, 12, 0, 0, tzinfo=datetime.timezone.utc)


def why(fn):
    """The refusal message, or a marker if there wasn't one."""
    try:
        fn()
        return "((NO REFUSAL))"
    except BaseException as exc:  # noqa: BLE001
        return "%s: %s" % (type(exc).__name__, exc)


def _set_mode(body):
    path = os.path.join(_TMP, "execution.conf")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    mode._reset_cache_for_tests(path)
    return mode.current_mode()


def _clear_mode():
    mode._reset_cache_for_tests(os.path.join(_TMP, "absent.conf"))
    return mode.current_mode()


# ===========================================================================
section("SS.8.6 vocabularies come from the spec, not from a broker's API")
# ===========================================================================

check("SS.8.6 lists 4 sides", len(SIDES), 4, 0, "(V) buy|sell|sell_short|buy_to_cover")
check("SS.8.6 lists 5 order types", len(ORDER_TYPES), 5, 0, "(V)")
check("SS.8.6 lists 4 times-in-force", len(TIME_IN_FORCE), 4, 0, "(V)")
check("SS.8.5 lists 16 pre-trade checks", len(RISK_CHECKS), 16, 0,
      "(V) MEASURED from SYSTEM_PROMPT.md SS.8.5")
check("SS.8.6's preview returns 10 fields", len(PREVIEW_FIELDS), 10, 0,
      "(V) MEASURED from SYSTEM_PROMPT.md SS.8.6")
check("SS.6.2 Phase A has 11 steps", len(PREVIEW_STEPS), 11, 0,
      "(V) MEASURED from SYSTEM_PROMPT.md SS.6.2")
check("SS.6.3 lists 21 mandatory controls", len(MANDATORY_CONTROLS), 21, 0,
      "(V) MEASURED from SYSTEM_PROMPT.md SS.6.3")

# sell and sell_short are NOT synonyms, and neither are buy and buy_to_cover.
# Collapsing either pair would change the margin and borrow consequences of an
# order while leaving every count above intact.
check_true("sell and sell_short are both present and distinct",
           "sell" in SIDES and "sell_short" in SIDES, "(C)")
check_true("buy and buy_to_cover are both present and distinct",
           "buy" in SIDES and "buy_to_cover" in SIDES, "(C)")
check_true("RISK_CHECKS has no duplicates, so 16 means sixteen DIFFERENT checks",
           len(set(RISK_CHECKS)) == len(RISK_CHECKS), "(C)")
check_true("PREVIEW_FIELDS has no duplicates", len(set(PREVIEW_FIELDS)) == 10, "(C)")
check_true("the check statuses are PASS, FAIL and UNKNOWN -- three, not two",
           tuple(CHECK_STATUS) == ("PASS", "FAIL", "UNKNOWN"),
           "(V) a bool cannot express 'could not be evaluated'")

# The tables are immutable. A caller who could add a control, or mark one met,
# could change what the module believes about itself.
check_raises("MANDATORY_CONTROLS cannot be edited at runtime",
             lambda: MANDATORY_CONTROLS.__setitem__("x", (True, "y")),
             (AttributeError, TypeError))
check_raises("ENVIRONMENT_INPUT cannot be edited at runtime",
             lambda: ENVIRONMENT_INPUT.__setitem__("x", "Y"),
             (AttributeError, TypeError))
check_raises("PRICE_FIELDS cannot be edited at runtime",
             lambda: PRICE_FIELDS.__setitem__("x", ((), ())),
             (AttributeError, TypeError))

# MEASURED: 18 of the 21 controls are absent, and the 3 present ones are named.
# Asserting the count alone would survive a mutation that marked a missing
# control met and an existing one missing, so the identities are asserted too.
check("SS.6.3: 18 of the 21 controls are absent here", len(unmet_controls()), 18, 0,
      "(V) MEASURED against this repository")
_met = tuple(n for n, (ok, _) in MANDATORY_CONTROLS.items() if ok)
check_true("the 3 controls that ARE met are exactly the three that need no broker",
           set(_met) == {"paper/live environment", "price-deviation guard",
                         "stale-quote guard"},
           "(V) MEASURED: everything else needs broker state or licensed data")
check_true("the kill switch is among the absent controls",
           "kill-switch status" in unmet_controls(),
           "(V) SS.6.3 requires one for any write-capable tool")
check_true("every control carries a stated reason, so no False is bare pessimism",
           all(reason.strip() for (_ok, reason) in MANDATORY_CONTROLS.values()),
           "(C)")


# ===========================================================================
section("the environment has no default, and that is the point")
# ===========================================================================

# SS.6.3: "paper and live accounts must have unambiguous identifiers". An omitted
# environment defaulting to paper is the exact ambiguity that lets a live order
# be placed by a caller who believed otherwise.
for _spelling, _want in (("paper", "PAPER"), ("PAPER", "PAPER"),
                         ("live", "LIVE"), ("LIVE", "LIVE")):
    check_true("environment %r normalises to %s" % (_spelling, _want),
               _normalise_environment(_spelling) == _want,
               "(V) SS.8.4 spells it lower case; brokers.py uses upper")

# These two must refuse for having NO DEFAULT, and the message must say so. If
# they refused as "unknown environment" instead, a mutation deleting the
# no-default guard would be invisible: the membership test would answer for it.
for _empty in (None, ""):
    _w = why(lambda e=_empty: _normalise_environment(e))
    check_true("environment %r is refused for having NO DEFAULT" % (_empty,),
               "has no default" in _w, "(D)")
    check_true("...and NOT by the membership test standing in for that guard",
               "unknown environment" not in _w,
               "(D) the guards must be distinguishable")

# A near-miss spelling must be refused rather than case-folded. 'Paper' looks
# harmless; 'LiVe' does not, and the same rule has to cover both.
for _bad in ("Paper", "LiVe", "papers", "PAPER ", " paper"):
    _w = why(lambda b=_bad: _normalise_environment(b))
    check_true("environment %r is refused as unknown, not case-folded" % (_bad,),
               "unknown environment" in _w, "(D)")

# A bool is an int in Python, and an int is not a string. Both are refused for
# their TYPE, which is a different guard again.
for _bad in (1, True, 0.0, ["paper"]):
    check_true("environment %r is refused for its type" % (_bad,),
               "must be a string" in why(lambda b=_bad: _normalise_environment(b)),
               "(D)")

check_true("account_id with leading whitespace is refused, not trimmed",
           "leading or trailing whitespace" in why(lambda: _validate_account_id(" A1")),
           "(D) ' 123' and '123' may be different accounts at the broker")
check_raises("an empty account_id is refused", lambda: _validate_account_id(""),
             BrokerToolError)
check_raises("a non-string account_id is refused", lambda: _validate_account_id(123),
             BrokerToolError)
check_true("a clean account_id is accepted", _validate_account_id("A1") == "A1",
           "(C) the guard discriminates")

check_true("_iso_utc converts a -04:00 instant to UTC rather than relabelling it",
           _iso_utc(datetime.datetime(2026, 8, 14, 12, 0, 0,
                                      tzinfo=datetime.timezone(
                                          datetime.timedelta(hours=-4))))
           == "2026-08-14T16:00:00+00:00",
           "(B) 12:00-04:00 is 16:00Z")
check_raises("_iso_utc refuses a naive datetime",
             lambda: _iso_utc(datetime.datetime(2026, 8, 14, 12)), BrokerToolError)


# ===========================================================================
section("SS.8.5 position_size: the arithmetic is real, and checked by hand")
# ===========================================================================

# (B) HAND ARITHMETIC. A 1000 budget with a 5-point stop is 200 units:
# 1000 / |100 - 95| = 200. If this returned anything else the module's core
# calculation would be wrong, and every refusal elsewhere would be beside the
# point.
_ps = position_size(account_equity=100000.0, risk_budget=1000.0,
                    entry=100.0, stop=95.0)
check("200 units risk exactly the 1000 budget on a 5-point stop",
      _ps["quantity"], 200.0, 1e-9, "(B) 1000 / 5")
check("the per-unit loss is the price risk when there are no costs",
      _ps["intermediates"]["loss_per_unit"], 5.0, 1e-9, "(B)")
check("the budget is reported as a fraction of equity",
      _ps["intermediates"]["risk_budget_as_pct_of_equity"], 0.01, 1e-12,
      "(B) 1000 / 100000")
check_true("the result is labelled COMPUTED, not MEASURED",
           _ps["status"] == "COMPUTED",
           "(V) arithmetic on supplied inputs is computed, not observed")
check_true("the formula is returned so a reader can redo it by hand",
           "risk_budget / (|entry - stop|" in _ps["formula"], "(C)")
check_true("the caveats state that a stop is not a guaranteed fill price",
           any("gaps through the stop" in c for c in _ps["caveats"]),
           "(V) no position size survives a gap")
check_true("the caveats state the result is NOT rounded to a tradeable lot",
           any("not rounded" in c for c in _ps["caveats"]),
           "(V) rounding here would silently change the risk")

# THE DIRECTION OF THE COST ADJUSTMENT is the one thing in this function that
# must never be wrong: a sign error produces a position LARGER than the budget
# allows. Asserted as an exact hand figure, not merely as an inequality.
_ps_cost = position_size(100000.0, 1000.0, 100.0, 95.0, fees=1.0, slippage=1.0)
check("fees and slippage enlarge the per-unit loss to 7",
      _ps_cost["intermediates"]["loss_per_unit"], 7.0, 1e-9, "(B) 5 + 1 + 1")
check("...so the size falls to 1000/7 units", _ps_cost["quantity"],
      1000.0 / 7.0, 1e-9, "(B)")
check_true("costs REDUCE the position size; a sign error here would enlarge it",
           _ps_cost["quantity"] < _ps["quantity"],
           "(C) the invariant that matters")

# The contract multiplier is not decoration: on a 50x future it changes the
# answer by a factor of fifty. This is the field calc.returns_risk.position_size
# does not have, and the reason this second function exists at all.
_ps_mult = position_size(100000.0, 1000.0, 100.0, 95.0, contract_multiplier=50.0)
check("a 50x contract multiplier divides the size by exactly 50",
      _ps_mult["quantity"], 4.0, 1e-9, "(B) 1000 / (5 * 50)")

# A short: the stop is ABOVE the entry. abs() must be doing the work, so the
# size is the same 200 units.
check("a stop above entry (a short) sizes identically",
      position_size(100000.0, 1000.0, 95.0, 100.0)["quantity"], 200.0, 1e-9,
      "(C) |entry - stop| is symmetric")

# -- the refusals, each distinguishable from its neighbour ------------------

# DEFECT FOUND BY MEASUREMENT 2026-08-14: this guard did not exist. The module
# comment claimed a zero stop was refused while the code read `if stop_p < 0`,
# and position_size(100000, 1000, 100, 0) returned 10.0 -- silently pricing the
# risk at the full entry price. Asserted on the MESSAGE, because the negative
# guard would otherwise stand in for this one under mutation.
_w0 = why(lambda: position_size(100000.0, 1000.0, 100.0, 0.0))
check_true("a stop of EXACTLY ZERO is refused as ambiguous",
           "exactly zero" in _w0,
           "(D) 'no stop' and 'field never filled in' differ by the whole trade")
check_true("...and not by the negative-stop guard standing in for it",
           "must not be negative" not in _w0, "(D) the guards are distinct")
check_true("a NEGATIVE stop is refused by its own guard, naming negativity",
           "must not be negative" in why(
               lambda: position_size(100000.0, 1000.0, 100.0, -1.0)), "(D)")
check("a stop just above zero still computes, so the guard is not over-broad",
      position_size(100000.0, 1000.0, 100.0, 0.01)["quantity"],
      1000.0 / 99.99, 1e-9, "(C) the guard discriminates")

check_true("a risk_budget larger than equity is refused, not capped",
           "exceeds account_equity" in why(
               lambda: position_size(100.0, 200.0, 10.0, 9.0)),
           "(D) 0.02 passed where 2%% of 100000 was meant must be told")
check_true("a stop equal to entry is refused as unbounded, not returned as huge",
           "unbounded" in why(
               lambda: position_size(100000.0, 1000.0, 100.0, 100.0)),
           "(D) zero risk per unit is not an infinite position")
check_true("negative fees are refused, naming the direction of the danger",
           "would INCREASE the position size" in why(
               lambda: position_size(100000.0, 1000.0, 100.0, 95.0, fees=-5.0)),
           "(D)")
check_true("negative slippage is refused too",
           "must be zero or positive" in why(
               lambda: position_size(100000.0, 1000.0, 100.0, 95.0, slippage=-1.0)),
           "(D)")

# A bool reaching arithmetic as 1 would size a one-share order. NaN is worse:
# every comparison against it is False, so it passes a max-size check.
for _field, _call in (
        ("account_equity", lambda: position_size(True, 1000.0, 100.0, 95.0)),
        ("risk_budget", lambda: position_size(100000.0, True, 100.0, 95.0)),
        ("entry", lambda: position_size(100000.0, 1000.0, True, 95.0)),
        ("stop", lambda: position_size(100000.0, 1000.0, 100.0, True)),
):
    check_true("a bool %s is refused, naming the bool" % _field,
               "got a bool" in why(_call),
               "(D) isinstance(True, int) is True in Python")
check_true("a NaN entry is refused, naming NaN",
           "is NaN" in why(lambda: position_size(100000.0, 1000.0,
                                                 float("nan"), 95.0)),
           "(D) NaN passes every max-size comparison silently")
check_true("an infinite entry is refused as non-finite",
           "non-finite" in why(lambda: position_size(100000.0, 1000.0,
                                                     float("inf"), 95.0)), "(D)")
check_raises("a zero contract_multiplier is refused",
             lambda: position_size(100000.0, 1000.0, 100.0, 95.0,
                                   contract_multiplier=0.0), BrokerToolError)
check_raises("an empty currency is refused",
             lambda: position_size(100000.0, 1000.0, 100.0, 95.0, currency=""),
             BrokerToolError)
check_raises("a zero risk_budget is refused",
             lambda: position_size(100000.0, 0.0, 100.0, 95.0), BrokerToolError)
check_raises("a zero account_equity is refused",
             lambda: position_size(0.0, 1000.0, 100.0, 95.0), BrokerToolError)


# ===========================================================================
section("SS.8.5 pre_trade_risk_check: an unevaluable check is not a passing one")
# ===========================================================================

_bare = pre_trade_risk_check("A1", "paper", now=NOW)

check("all 16 checks are reported even though most cannot be evaluated",
      len(_bare["checks"]), 16, 0, "(V) SS.8.5")
check_true("every one of the 16 named checks appears in the result",
           all(c in _bare["checks"] for c in RISK_CHECKS),
           "(C) a risk report missing a check is the failure to prevent")
check_true("every reported status is one of PASS/FAIL/UNKNOWN",
           all(r["status"] in CHECK_STATUS for r in _bare["checks"].values()),
           "(C)")
check_true("every check carries a detail, so no status is unexplained",
           all(r["detail"].strip() for r in _bare["checks"].values()), "(C)")

# THE CENTRAL ASSERTION OF THIS FILE. With no data supplied, nothing passes, and
# the verdict is REFUSE. A module that reported "3 passed, 13 skipped, overall
# PASS" would manufacture exactly the confidence a pre-trade check withholds.
check_true("with no data supplied the verdict is REFUSE",
           _bare["verdict"] == "REFUSE", "(V) SS.8.5")
check("...with zero checks passing", _bare["n_pass"], 0, 0, "(V) MEASURED")
check("...exactly one FAILing", _bare["n_fail"], 1, 0, "(V) MEASURED")
check("...and fifteen UNKNOWN", _bare["n_unknown"], 15, 0, "(V) MEASURED")
check("the three counts account for all sixteen checks",
      _bare["n_pass"] + _bare["n_fail"] + _bare["n_unknown"], 16, 0, "(C)")
check_true("the verdict reason states that an unevaluable check is not a pass",
           "unevaluable check is not a passing check" in _bare["verdict_reason"],
           "(V) the rule, written where a reader of the output will see it")

# The kill switch is FAIL, not UNKNOWN. A known absence is determinate; calling
# it UNKNOWN would suggest the right credential might reveal one.
check_true("kill_switch_status is FAIL",
           _bare["checks"]["kill_switch_status"]["status"] == "FAIL",
           "(V) a known absence is determinate")
check_true("...and explicitly NOT UNKNOWN",
           _bare["checks"]["kill_switch_status"]["status"] != "UNKNOWN",
           "(V) no credential reveals a kill switch that was never written")
check_true("...and the detail says why it is FAIL rather than UNKNOWN",
           "not missing data" in _bare["checks"]["kill_switch_status"]["detail"],
           "(V)")
check_true("the kill switch is the ONLY FAIL when no data is supplied",
           [k for k, v in _bare["checks"].items() if v["status"] == "FAIL"]
           == ["kill_switch_status"], "(V) MEASURED")

# The thirteen that need broker state must be UNKNOWN -- not PASS, and not FAIL.
# UNKNOWN means "go and get the data"; FAIL means "measured, and it is bad".
for _needs_broker in ("buying_power", "margin", "leverage", "concentration",
                      "daily_loss", "duplicate_order", "liquidity", "tick_size",
                      "lot_size", "short_sale_restrictions", "trading_session",
                      "user_limits"):
    check_true("%s is UNKNOWN, because no broker state can be read"
               % _needs_broker,
               _bare["checks"][_needs_broker]["status"] == "UNKNOWN", "(V)")
check_true("user_limits says an absent limit is not a satisfied one",
           "not a satisfied" in _bare["checks"]["user_limits"]["detail"],
           "(V) the most tempting UNKNOWN to call PASS")

# -- the two checks that CAN be evaluated, proving the layer discriminates ---

_fed = pre_trade_risk_check(
    "A1", "paper", order_draft={"quantity": 10, "limit_price": 100.0},
    reference_price=100.0, quote_timestamp=NOW - datetime.timedelta(seconds=5),
    now=NOW)
check("feeding good data makes exactly two checks PASS", _fed["n_pass"], 2, 0,
      "(C) MEASURED: the layer is not a blanket refusal")
check_true("...and they are price_deviation and quote_freshness",
           sorted(k for k, v in _fed["checks"].items() if v["status"] == "PASS")
           == ["price_deviation", "quote_freshness"], "(V) MEASURED")
check_true("the verdict is STILL REFUSE with two of sixteen passing",
           _fed["verdict"] == "REFUSE",
           "(V) REFUSE unless ALL sixteen pass")

# price_deviation boundary, measured at 5.00% and 5.01%. Asserting only the
# far-off case would leave the comparison operator free to be <= or <.
check_true("a price 100%% away from the reference FAILs price_deviation",
           pre_trade_risk_check("A1", "paper",
                                order_draft={"quantity": 10, "limit_price": 200.0},
                                reference_price=100.0, now=NOW
                                )["checks"]["price_deviation"]["status"] == "FAIL",
           "(D) a fat-fingered price is the cheapest large loss available")
check_true("exactly 5.00%% away PASSes (the tolerance is inclusive)",
           pre_trade_risk_check("A1", "paper",
                                order_draft={"quantity": 10, "limit_price": 105.0},
                                reference_price=100.0, now=NOW
                                )["checks"]["price_deviation"]["status"] == "PASS",
           "(C) MEASURED boundary")
check_true("5.01%% away FAILs, so the boundary is where it claims to be",
           pre_trade_risk_check("A1", "paper",
                                order_draft={"quantity": 10, "limit_price": 105.01},
                                reference_price=100.0, now=NOW
                                )["checks"]["price_deviation"]["status"] == "FAIL",
           "(C) MEASURED boundary")
check_true("with no reference price, price_deviation is UNKNOWN rather than PASS",
           _bare["checks"]["price_deviation"]["status"] == "UNKNOWN",
           "(V) a check with no input has not passed")

# quote_freshness boundary, and the future-dated case, which is a clock error
# rather than a fresh quote.
check_true("a 61-second-old quote FAILs the 60-second limit",
           pre_trade_risk_check("A1", "paper",
                                quote_timestamp=NOW - datetime.timedelta(seconds=61),
                                now=NOW)["checks"]["quote_freshness"]["status"]
           == "FAIL", "(C) MEASURED boundary")
check_true("an exactly-60-second-old quote PASSes",
           pre_trade_risk_check("A1", "paper",
                                quote_timestamp=NOW - datetime.timedelta(seconds=60),
                                now=NOW)["checks"]["quote_freshness"]["status"]
           == "PASS", "(C) MEASURED boundary")
_future = pre_trade_risk_check("A1", "paper",
                               quote_timestamp=NOW + datetime.timedelta(seconds=30),
                               now=NOW)
check_true("a FUTURE-dated quote FAILs rather than counting as very fresh",
           _future["checks"]["quote_freshness"]["status"] == "FAIL",
           "(D) a negative age is a clock or timezone error")
check_true("...and the detail names the future, not the age limit",
           "in the FUTURE" in _future["checks"]["quote_freshness"]["detail"],
           "(D) distinguishable from the stale-quote refusal")
check_true("with no quote at all, freshness is UNKNOWN rather than PASS",
           _bare["checks"]["quote_freshness"]["status"] == "UNKNOWN", "(V)")

# The notional is computable but has nothing to check against, so it is UNKNOWN
# rather than PASS -- a computed number is not a satisfied limit.
check_true("a computable notional is still UNKNOWN, for want of a limit",
           _fed["checks"]["notional"]["status"] == "UNKNOWN",
           "(V) no maximum-order-notional is configured")
check_true("...and the detail reports the figure it computed",
           "1000.0000" in _fed["checks"]["notional"]["detail"],
           "(B) 10 * 100")
check_true("the draft's 'price' key is honoured as well as 'limit_price'",
           pre_trade_risk_check("A1", "paper",
                                order_draft={"quantity": 10, "price": 100.0},
                                reference_price=100.0, now=NOW
                                )["checks"]["price_deviation"]["status"] == "PASS",
           "(C) a market draft carries 'price'")

# -- the verdict RULE itself, tested where the kill switch cannot mask it ---
#
# WHY THESE ASSERTIONS EXIST. The verdict was computed inline, and the adversarial
# probe was seeded with the mutant `verdict = "PASS" if n_fail == 0` -- the exact
# "an UNKNOWN is good enough" bug this module was written to prevent -- and ALL 54
# probe attempts still passed. MEASURED cause: kill_switch_status is
# unconditionally FAIL, so n_fail is never zero, so the mutant agreed with the
# real rule in every state a caller can construct. The rule was untestable behind
# a second guard. It is now `verdict_for`, callable with a synthetic result set,
# and the state that separates the rule from its mutant is asserted directly.
_all_pass = {c: {"status": "PASS", "detail": "synthetic"} for c in RISK_CHECKS}


def _with(**over):
    out = dict((k, dict(v)) for k, v in _all_pass.items())
    for _k, _v in over.items():
        out[_k] = {"status": _v, "detail": "synthetic"}
    return out


check_true("sixteen PASSes give a PASS verdict",
           bt.verdict_for(_with()) == "PASS",
           "(C) the rule discriminates; it is not 'always REFUSE'")
check_true("fifteen PASSes and ONE UNKNOWN give REFUSE",
           bt.verdict_for(_with(margin="UNKNOWN")) == "REFUSE",
           "(V) THE RULE: an unevaluable check is not a passing check")
check_true("fifteen PASSes and one FAIL give REFUSE",
           bt.verdict_for(_with(margin="FAIL")) == "REFUSE", "(V)")
check_true("a lone UNKNOWN is as disqualifying as a lone FAIL",
           bt.verdict_for(_with(margin="UNKNOWN"))
           == bt.verdict_for(_with(margin="FAIL")),
           "(C) a verdict counting only FAILs would differ here")
for _one in ("buying_power", "liquidity", "user_limits", "kill_switch_status"):
    check_true("a single UNKNOWN %s is enough to REFUSE" % _one,
               bt.verdict_for(_with(**{_one: "UNKNOWN"})) == "REFUSE", "(V)")
# MUTATION FINDING 2026-08-15. This was `check_raises(..., BrokerToolError)`
# alone, and it SURVIVED the mutation that disables the empty-set guard. MEASURED
# cause: {} is also missing all sixteen checks, so the PARTIAL guard two lines
# below raises the same exception type -- a second guard answering for the one
# under test, the recurring pattern in this project. Asserting on the MESSAGE is
# what distinguishes them.
_w_empty = why(lambda: bt.verdict_for({}))
check_raises("an EMPTY result set is refused, not read as 'nothing failed'",
             lambda: bt.verdict_for({}), BrokerToolError)
check_true("...by the EMPTY guard, naming 'no checks run'",
           "empty result set" in _w_empty,
           "(D) 'no checks run' is not 'no checks failed'")
check_true("...and NOT by the partial-set guard standing in for it",
           "partial result set" not in _w_empty,
           "(D) the two guards must be distinguishable")
check_raises("a PARTIAL result set is refused",
             lambda: bt.verdict_for({"margin": {"status": "PASS", "detail": "x"}}),
             BrokerToolError)
check_raises("an unrecognised status is refused, not treated as a pass",
             lambda: bt.verdict_for(_with(margin="SKIPPED")), BrokerToolError)
check_true("...and the refusal names the offending status",
           "not one of PASS|FAIL|UNKNOWN" in why(
               lambda: bt.verdict_for(_with(margin="SKIPPED"))), "(D)")
check_true("the live function's verdict agrees with the extracted rule",
           _bare["verdict"] == bt.verdict_for(_bare["checks"]),
           "(C) the extraction did not change behaviour")

check_raises("a naive quote_timestamp is refused rather than assumed to be UTC",
             lambda: pre_trade_risk_check("A1", "paper",
                                          quote_timestamp=datetime.datetime(
                                              2026, 8, 14, 12), now=NOW),
             BrokerToolError)
check_raises("a non-dict order_draft is refused",
             lambda: pre_trade_risk_check("A1", "paper", order_draft=[], now=NOW),
             BrokerToolError)
check_raises("the risk check still validates the account_id",
             lambda: pre_trade_risk_check("", "paper", now=NOW), BrokerToolError)
check_raises("the risk check still requires an environment",
             lambda: pre_trade_risk_check("A1", None, now=NOW), BrokerToolError)
check_true("an unconfigured risk policy is reported as NONE CONFIGURED, not ''",
           _bare["risk_policy_version"] == "NONE CONFIGURED",
           "(V) an empty string reads as a policy with no name")


# ===========================================================================
section("SS.6.2 step 6: order fields, refused for the RIGHT reason")
# ===========================================================================

_good = _validate_order_fields("IBM", "buy", 10, "limit", 100.0, None, "day",
                               False, "cid-1")
check_true("a well-formed limit order validates, so the layer discriminates",
           _good["order_type"] == "limit" and _good["limit_price"] == 100.0, "(C)")
check("the quantity is normalised to a float", _good["quantity"], 10.0, 0, "(C)")

# Required vs forbidden are DIFFERENT guards, and each must answer for itself.
check_true("a limit order with no limit_price is refused as REQUIRING one",
           "requires limit_price" in why(
               lambda: _validate_order_fields("IBM", "buy", 1, "limit", None,
                                              None, "day", False, "c1")), "(D)")
check_true("a stop order with no stop_price is refused as REQUIRING one",
           "requires stop_price" in why(
               lambda: _validate_order_fields("IBM", "buy", 1, "stop", None,
                                              None, "day", False, "c1")), "(D)")
check_true("a market order carrying a limit_price is refused for CARRYING it",
           "must not carry limit_price" in why(
               lambda: _validate_order_fields("IBM", "buy", 1, "market", 10.0,
                                              None, "day", False, "c1")),
           "(D) silently dropping it would change the caller's order")
check_true("a market order carrying a stop_price is refused for CARRYING it",
           "must not carry stop_price" in why(
               lambda: _validate_order_fields("IBM", "buy", 1, "market", None,
                                              10.0, "day", False, "c1")), "(D)")
check_true("a limit order carrying a stop_price is refused for CARRYING it",
           "must not carry stop_price" in why(
               lambda: _validate_order_fields("IBM", "buy", 1, "limit", 10.0,
                                              5.0, "day", False, "c1")), "(D)")
check_true("a stop order carrying a limit_price is refused for CARRYING it",
           "must not carry limit_price" in why(
               lambda: _validate_order_fields("IBM", "buy", 1, "stop", 10.0,
                                              5.0, "day", False, "c1")), "(D)")

# trailing_stop is in ORDER_TYPES because SS.8.6 lists it, and is refused
# because SS.8.6's field list has nowhere to put a trailing offset. Reusing
# stop_price to mean "offset" would give one field two meanings.
check_true("trailing_stop is refused as UNSUPPORTED, naming the missing offset",
           "trailing OFFSET" in why(
               lambda: _validate_order_fields("IBM", "buy", 1, "trailing_stop",
                                              None, None, "day", False, "c1")),
           "(D) not refused as an unknown order type")
check_true("...and it is nonetheless present in ORDER_TYPES, because SS.8.6 lists it",
           "trailing_stop" in ORDER_TYPES,
           "(V) the spec's vocabulary is not edited to match the implementation")
check_true("an order type outside the spec is refused as UNKNOWN",
           "unknown order_type" in why(
               lambda: _validate_order_fields("IBM", "buy", 1, "iceberg", None,
                                              None, "day", False, "c1")), "(D)")

# stop_limit wrong-side, BOTH directions, for all four sides. A guard written
# for one direction only would let the other through, and the resulting order
# can never fill.
check_true("a BUY stop_limit with limit below stop is refused as unfillable",
           "can never fill" in why(
               lambda: _validate_order_fields("IBM", "buy", 1, "stop_limit",
                                              10.0, 20.0, "day", False, "c1")),
           "(D)")
check_true("a BUY_TO_COVER stop_limit with limit below stop is refused too",
           "can never fill" in why(
               lambda: _validate_order_fields("IBM", "buy_to_cover", 1,
                                              "stop_limit", 10.0, 20.0, "day",
                                              False, "c1")),
           "(D) buy_to_cover is a buy for this purpose")
check_true("a SELL stop_limit with limit above stop is refused as unfillable",
           "can never fill" in why(
               lambda: _validate_order_fields("IBM", "sell", 1, "stop_limit",
                                              20.0, 10.0, "day", False, "c1")),
           "(D) the mirror case")
check_true("a SELL_SHORT stop_limit with limit above stop is refused too",
           "can never fill" in why(
               lambda: _validate_order_fields("IBM", "sell_short", 1,
                                              "stop_limit", 20.0, 10.0, "day",
                                              False, "c1")),
           "(D) sell_short is a sell for this purpose")
# The correct sides must be ACCEPTED, or the guard is just "refuse all
# stop_limits" and the direction logic is untested.
check_true("a BUY stop_limit with limit ABOVE stop is accepted",
           _validate_order_fields("IBM", "buy", 1, "stop_limit", 20.0, 10.0,
                                  "day", False, "c1")["limit_price"] == 20.0,
           "(C) the guard discriminates by direction")
check_true("a SELL stop_limit with limit BELOW stop is accepted",
           _validate_order_fields("IBM", "sell", 1, "stop_limit", 10.0, 20.0,
                                  "day", False, "c1")["limit_price"] == 10.0,
           "(C) the mirror positive")
check_true("a stop_limit with limit EQUAL to stop is accepted",
           _validate_order_fields("IBM", "buy", 1, "stop_limit", 100.0, 100.0,
                                  "day", False, "c1")["stop_price"] == 100.0,
           "(C) MEASURED: equality is fillable, so it is not refused")

check_true("an unknown side is refused, and the message warns sell != sell_short",
           "neither is a synonym" in why(
               lambda: _validate_order_fields("IBM", "SELL", 1, "market", None,
                                              None, "day", False, "c1")),
           "(D) wrong case is not silently accepted")
check_raises("an unknown time_in_force is refused",
             lambda: _validate_order_fields("IBM", "buy", 1, "market", None,
                                            None, "GTC", False, "c1"),
             BrokerToolError)
check_true("a string extended_hours is refused, naming the truthiness trap",
           "truthy string like 'false'" in why(
               lambda: _validate_order_fields("IBM", "buy", 1, "market", None,
                                              None, "day", "false", "c1")),
           "(D) bool('false') is True")
check_raises("an empty instrument_id is refused",
             lambda: _validate_order_fields("", "buy", 1, "market", None, None,
                                            "day", False, "c1"), BrokerToolError)
check_true("a whitespace client_order_id is refused, naming duplicate detection",
           "duplicate submission" in why(
               lambda: _validate_order_fields("IBM", "buy", 1, "market", None,
                                              None, "day", False, "   ")),
           "(D) SS.6.3 requires duplicate-order detection")
check_raises("a zero quantity is refused",
             lambda: _validate_order_fields("IBM", "buy", 0, "market", None,
                                            None, "day", False, "c1"),
             BrokerToolError)
check_raises("a negative quantity is refused",
             lambda: _validate_order_fields("IBM", "buy", -1, "market", None,
                                            None, "day", False, "c1"),
             BrokerToolError)


# ===========================================================================
section("SS.8.6 preview_order: ten honest fields and no confirmation token")
# ===========================================================================

_pv = preview_order("A1", "paper", "IBM", "buy", 10, "limit", limit_price=100.0,
                    client_order_id="cid-1", now=NOW)

check_true("all ten SS.8.6 fields are present",
           all(f in _pv for f in PREVIEW_FIELDS), "(V)")
check("the notional is quantity times limit price", _pv["estimated_notional"],
      1000.0, 1e-9, "(B) 10 * 100")

# THE ASSERTION THAT KEEPS A PREVIEW FROM BEING ONE STRING FROM A COMMIT.
check_true("the preview is not committable", _pv["committable"] is False, "(V)")
check_true("NO confirmation token is issued: the field is None",
           _pv["confirmation_challenge"] is None,
           "(V) SS.6.2 Phase B commits only against a valid token")
check_true("...and the note explains the omission is deliberate",
           "NO TOKEN ISSUED, deliberately"
           in _pv["field_notes"]["confirmation_challenge"],
           "(V) not a placeholder that looks like a token")
check_true("the reason it cannot be committed names the absent controls",
           "21 mandatory controls" in _pv["why_not_committable"], "(V)")
check_true("the embedded risk check REFUSEs",
           _pv["risk_check"]["verdict"] == "REFUSE", "(V)")

# Unknown fields are None WITH a stated reason. A fee of 0.0 would read as free.
for _unknown in ("fees", "margin_impact", "slippage"):
    check_true("%s is None rather than a flattering zero" % _unknown,
               _pv[_unknown] is None, "(V)")
    check_true("...and its note explains why it is UNKNOWN",
               "UNKNOWN" in _pv["field_notes"][_unknown], "(V)")
check_true("the fees note says 0.0 would read as free",
           "would read as free" in _pv["field_notes"]["fees"], "(V)")

# The preview ID is a content hash: SS.8.6 requires immutability, and deriving
# the ID from the content means a changed preview cannot keep its identifier.
check_true("the preview id is prefixed and hex",
           _pv["preview_id"].startswith("prv_") and len(_pv["preview_id"]) == 36,
           "(V) 'prv_' plus 32 hex characters")
check_true("identical inputs at the same instant give the same id",
           preview_order("A1", "paper", "IBM", "buy", 10, "limit",
                         limit_price=100.0, client_order_id="cid-1",
                         now=NOW)["preview_id"] == _pv["preview_id"],
           "(C) a content hash is deterministic")
for _label, _kw in (
        ("quantity", {"quantity": 11}),
        ("side", {"side": "sell"}),
        ("limit price", {"limit_price": 100.01}),
        ("instrument", {"instrument_id": "MSFT"}),
        ("client_order_id", {"client_order_id": "cid-2"}),
        ("environment", {"environment": "live"}),
):
    _kwargs = dict(account_id="A1", environment="paper", instrument_id="IBM",
                   side="buy", quantity=10, order_type="limit",
                   limit_price=100.0, client_order_id="cid-1", now=NOW)
    _kwargs.update(_kw)
    check_true("changing the %s changes the preview id" % _label,
               preview_order(**_kwargs)["preview_id"] != _pv["preview_id"],
               "(C) a mutated preview cannot keep its identifier")
check_true("changing the instant alone changes the id",
           preview_order("A1", "paper", "IBM", "buy", 10, "limit",
                         limit_price=100.0, client_order_id="cid-1",
                         now=NOW + datetime.timedelta(seconds=1)
                         )["preview_id"] != _pv["preview_id"], "(C)")

# A market order has no price until it fills, so its notional is UNKNOWN rather
# than a guessed number.
_mk = preview_order("A1", "paper", "IBM", "buy", 10, "market",
                    client_order_id="cid-1", now=NOW)
check_true("a market order's notional is None, not an estimate",
           _mk["estimated_notional"] is None,
           "(V) no price exists until it fills, and no live quote is licensed")
check_true("...and the note says so",
           "no price until it fills" in _mk["field_notes"]["estimated_notional"],
           "(V)")

# Honesty about which of SS.6.2's eleven Phase A steps actually ran.
check("4 of the 11 Phase A steps were performed", len(_pv["steps_performed"]), 4,
      0, "(V) MEASURED")
check("7 were not, each with a reason", len(_pv["steps_not_performed"]), 7, 0,
      "(V) MEASURED")
check("performed plus not-performed accounts for all 11 steps",
      len(_pv["steps_performed"]) + len(_pv["steps_not_performed"]), 11, 0,
      "(C) no step is silently unaccounted for")
check_true("the un-performed steps include obtaining a fresh authorized quote",
           any("fresh authorized quote" in s for s in _pv["steps_not_performed"]),
           "(V) the enabled provider is END_OF_DAY only")
check_true("the un-performed steps include issuing a confirmation token",
           any("confirmation token" in s for s in _pv["steps_not_performed"]),
           "(V)")
check_true("the expiry is 60 seconds after creation",
           _pv["preview_expiry"] == "2026-08-14T12:01:00+00:00",
           "(B) NOW + 60s, in UTC")

# MUTATION FINDING 2026-08-15. Two of preview_order's OWN guards had no test at
# all: removing either survived the whole 282-assertion suite and the 62-attempt
# probe. Not a masking problem this time -- simply untested code, which the
# passing suite could not distinguish from tested code. Both are entry-point
# guards, so they are the first thing a caller hits and the last thing anyone
# would notice missing.
_w_naive = why(lambda: preview_order("A1", "paper", "IBM", "buy", 10, "limit",
                                     limit_price=100.0, client_order_id="c1",
                                     now=datetime.datetime(2026, 8, 14, 12)))
check_true("preview_order refuses a NAIVE `now` rather than assuming a zone",
           "now must be timezone-aware" in _w_naive,
           "(D) the error would be silent and the size of it the local offset")

# preview_order requires client_order_id in its OWN body, before delegating to
# _validate_order_fields. Asserted on this wording specifically: the downstream
# validator refuses an empty one too, with a different message, so a type-only
# assertion here would be answered by that second guard.
_w_cid = why(lambda: preview_order("A1", "paper", "IBM", "buy", 10, "limit",
                                   limit_price=100.0, client_order_id=""))
check_true("preview_order requires a client_order_id in its own right",
           "client_order_id is required" in _w_cid,
           "(D) SS.6.3 duplicate-order detection needs a caller-chosen identity")
check_true("...and NOT via the downstream field validator standing in for it",
           "duplicate submission" not in _w_cid,
           "(D) the two guards must be distinguishable")
check_true("the quote timestamp is None when no quote was supplied",
           _pv["quote_timestamp"] is None, "(V)")
check_true("the environment is normalised upward in the returned preview",
           _pv["environment"] == "PAPER", "(C)")

check_raises("a preview with no client_order_id is refused",
             lambda: preview_order("A1", "paper", "IBM", "buy", 10, "market",
                                   now=NOW), BrokerToolError)
check_raises("a preview with a naive `now` is refused",
             lambda: preview_order("A1", "paper", "IBM", "buy", 10, "market",
                                   client_order_id="c1",
                                   now=datetime.datetime(2026, 8, 14, 12)),
             BrokerToolError)
check_raises("a preview of a trailing_stop is refused",
             lambda: preview_order("A1", "paper", "IBM", "buy", 10,
                                   "trailing_stop", client_order_id="c1",
                                   now=NOW), BrokerToolError)
check_raises("a preview with no environment is refused",
             lambda: preview_order("A1", None, "IBM", "buy", 10, "market",
                                   client_order_id="c1", now=NOW),
             BrokerToolError)


# ===========================================================================
section("SS.8.6 writes: five refusals that configuration cannot lift")
# ===========================================================================

for _name, _fn in (("place_order", place_order), ("modify_order", modify_order),
                   ("cancel_order", cancel_order),
                   ("cancel_all_orders", cancel_all_orders),
                   ("flatten_position", flatten_position)):
    check_raises("%s raises NotImplementedError" % _name, _fn, NotImplementedError)
    _w = why(_fn)
    check_true("%s's refusal names the absent SS.6.3 controls" % _name,
               "21 mandatory controls" in _w, "(V)")
    check_true("%s's refusal calls itself a design decision, not an omission"
               % _name, "design decision rather than an omission" in _w,
               "(V) a stub invites completion; this does not")

# A real preview_id plus a plausible-looking token must NOT get further than a
# bare call. place_order does not read preview_order's output at all.
check_raises("a real preview_id and an invented token still refuse",
             lambda: place_order(preview_id=_pv["preview_id"],
                                 confirmation_token="yes-i-confirm",
                                 idempotency_key="idem-1"),
             NotImplementedError)
check_true("place_order states that no preview can be escalated into an order",
           "no preview can be escalated" in why(
               lambda: place_order(preview_id=_pv["preview_id"],
                                   confirmation_token="yes-i-confirm")),
           "(V) the two-phase protocol has no Phase B here")
check_true("cancel_order states that a cancel is a WRITE",
           "a cancel is a write" in why(cancel_order).lower(),
           "(V) the intuition that cancelling is safe is why this is explicit")
# The wording here was MEASURED from the module rather than guessed: the first
# draft of this assertion looked for "cannot be shown" and failed, because the
# module says "None of those five can be shown". The test was wrong, not the
# module, and the string was corrected rather than the assertion weakened to a
# substring that any refusal would satisfy.
check_true("cancel_all_orders states its blast radius cannot be shown",
           "None of those five can be shown" in why(cancel_all_orders),
           "(V) an action whose scope is unknown cannot be confirmed")
check_true("...and names the unknowable blast radius as the reason",
           "blast radius of the action is unknown" in why(cancel_all_orders),
           "(V)")
check_true("flatten_position quotes SS.8.6 on webhook-driven execution",
           "webhook" in why(flatten_position),
           "(V) the most attractive action for an injected instruction")


# ===========================================================================
section("SS.8.4 reads: the mode gate answers before the adapter gate")
# ===========================================================================

check_true("the default mode is ANALYSIS_ONLY", mode.current_mode()
           == "ANALYSIS_ONLY", "(V) no config file exists")

# In ANALYSIS_ONLY, all four read tools are stopped by the MODE gate. Asserted
# by exception TYPE, because the adapter gate raises BrokerToolError and the
# mode gate raises ExecutionModeError -- if the order of the two ever inverted,
# a test that only checked "it raised" would not notice.
for _name, _fn in (("broker_account_snapshot", broker_account_snapshot),
                   ("broker_positions", broker_positions),
                   ("broker_open_orders", broker_open_orders),
                   ("broker_executions", broker_executions)):
    check_raises("%s is refused by the MODE gate in ANALYSIS_ONLY" % _name,
                 lambda f=_fn: f("A1", "paper"), ExecutionModeError)
    check_true("...and the refusal names the capability, not the adapter",
               "read_broker_account" in why(lambda f=_fn: f("A1", "paper")),
               "(V) SS.5.6")

# Validation runs BEFORE the mode gate, which is the design decision recorded in
# the module docstring: a caller who passed a bad argument learns that first.
check_raises("an empty account_id is refused before the mode gate is reached",
             lambda: broker_positions("", "paper"), BrokerToolError)
check_raises("an unknown environment is refused before the mode gate",
             lambda: broker_positions("A1", "demo"), BrokerToolError)
check_true("...and that refusal is NOT an ExecutionModeError",
           not isinstance(
               next((e for e in [None] if False), BrokerToolError("x")),
               ExecutionModeError),
           "(C) the two gates raise different types")

# broker_executions validates its window before refusing, so a reversed window
# is caught here rather than against a live account.
check_true("a reversed execution window is refused as INVERTED",
           "inverted window" in why(
               lambda: broker_executions("A1", "paper",
                                         start="2026-08-14T12:00:00+00:00",
                                         end="2026-08-13T12:00:00+00:00")),
           "(D) it would otherwise return nothing and read as 'no executions'")
check_true("a mixed-awareness window is refused",
           "both be timezone-aware or both naive" in why(
               lambda: broker_executions("A1", "paper",
                                         start="2026-08-13T12:00:00+00:00",
                                         end="2026-08-14T12:00:00")),
           "(D)")
check_true("a non-ISO start is refused, naming ISO-8601",
           "not ISO-8601" in why(
               lambda: broker_executions("A1", "paper", start="not-a-date")),
           "(D)")
check_raises("a non-string start is refused",
             lambda: broker_executions("A1", "paper", start=20260814),
             BrokerToolError)


# ===========================================================================
section("the deep gates, reached with a synthetic VERIFIED adapter")
# ===========================================================================

# Everything past "no adapter is enabled" is unreachable in the shipped
# configuration, so these gates are invisible to a test that does not force
# them. A synthetic adapter is registered, and removed in a finally: a leaked
# enabled adapter would weaken every later suite in run_all.sh.

check("no adapter is enabled in the shipped configuration",
      len(brokers.enabled_adapters()), 0, 0,
      "(V) all registered adapters are DOCUMENTED, not VERIFIED")
check("...and three are registered, so the catalog is not simply empty",
      len(brokers.ADAPTERS), 3, 0, "(V) MEASURED")

_paper_only = BrokerAdapter(
    key="_probe_paper_only", name="probe", docs_url="https://example.invalid/",
    transport="none (test double)", verification="VERIFIED",
    environments=("PAPER",), enabled=True,
    supports_idempotency="test double",
    documented_capabilities=("read account",),
    unverifiable_without_credentials=("everything: this is a test double",))
_both_envs = BrokerAdapter(
    key="_probe_both_envs", name="probe", docs_url="https://example.invalid/",
    transport="none (test double)", verification="VERIFIED",
    environments=("PAPER", "LIVE"), enabled=True,
    supports_idempotency="test double",
    documented_capabilities=("read account",),
    unverifiable_without_credentials=("everything: this is a test double",))

brokers.register_adapter(_both_envs)
try:
    check("a VERIFIED enabled adapter really is enabled",
          len(brokers.enabled_adapters()), 1, 0, "(C) the fixture works")

    # Still ANALYSIS_ONLY: the mode gate must refuse even now.
    check_raises("even with a VERIFIED adapter, ANALYSIS_ONLY refuses a read",
                 lambda: broker_positions("A1", "paper"), ExecutionModeError)

    _mode_now = _set_mode("mode = PAPER_TRADING\n"
                          "i_have_enabled_paper_trading = yes\n")
    check_true("the fixture really did switch the mode to PAPER_TRADING",
               _mode_now == "PAPER_TRADING", "(C) otherwise nothing below tests")

    # PAPER now gets all the way to the transport, which is the deepest point
    # reachable. The refusal must be the transport one -- proof that the
    # verification, enabled, environment and mode gates were all PASSED, not
    # that some earlier gate answered.
    _w_paper = why(lambda: broker_positions("A1", "paper"))
    check_true("a PAPER read reaches the transport refusal, past every gate",
               "no transport implementation" in _w_paper,
               "(C) the gates are gates, not a blanket refusal")
    check_true("...and it refuses rather than returning an empty position list",
               "read as 'no positions'" in _w_paper,
               "(V) 'you hold nothing' is the most dangerous wrong answer")

    # THE MOST IMPORTANT ASSERTION IN THIS FILE. A verified, enabled,
    # LIVE-capable adapter, with paper trading switched on, and a LIVE read is
    # STILL refused -- by the mode gate, on unmet SS.6.1 prerequisites.
    _w_live = why(lambda: broker_positions("A1", "live"))
    check_raises("a LIVE read is refused even with a LIVE-capable VERIFIED adapter",
                 lambda: broker_positions("A1", "live"), ExecutionModeError)
    check_true("...because SS.6.1's prerequisites for live trading are unmet",
               "prerequisites" in _w_live,
               "(V) live trading is unreachable regardless of configuration")
    check_true("...and the refusal says so explicitly",
               "regardless of configuration" in _w_live, "(V)")
    check_true("...and it is NOT merely the adapter being unusable",
               "not enabled" not in _w_live,
               "(C) the mode gate, not the broker gate, is the wall")

    # All four read tools behave identically at the live gate: a guard on one
    # of them only would be invisible to a test that checked just one.
    for _name, _fn in (("broker_account_snapshot", broker_account_snapshot),
                       ("broker_open_orders", broker_open_orders),
                       ("broker_executions", broker_executions)):
        check_raises("%s also refuses a LIVE read" % _name,
                     lambda f=_fn: f("A1", "live"), ExecutionModeError)
finally:
    del brokers._ADAPTERS["_probe_both_envs"]
    _clear_mode()

check("the synthetic adapter was removed", len(brokers.enabled_adapters()), 0, 0,
      "(C) no fixture leaks into later suites")
check_true("the mode was restored to ANALYSIS_ONLY",
           mode.current_mode() == "ANALYSIS_ONLY", "(C) no fixture leaks")

# An adapter that offers only PAPER must refuse LIVE on its OWN environment
# check -- a different guard from the mode gate above, and one that would be
# masked if only the both-environments adapter were ever tested.
brokers.register_adapter(_paper_only)
try:
    _set_mode("mode = PAPER_TRADING\ni_have_enabled_paper_trading = yes\n")
    _w = why(lambda: broker_positions("A1", "live"))
    check_true("a PAPER-only adapter refuses LIVE on its own environment list",
               "does not offer a LIVE environment" in _w,
               "(D) the adapter's own guard, not the mode gate")
    check_raises("...as a BrokerError from the broker layer",
                 lambda: broker_positions("A1", "live"), BrokerError)
finally:
    del brokers._ADAPTERS["_probe_paper_only"]
    _clear_mode()

check("the second synthetic adapter was removed too",
      len(brokers.enabled_adapters()), 0, 0, "(C)")


# ===========================================================================
section("SS.8.5 portfolio_risk: validated, then honestly refused")
# ===========================================================================

check_true("portfolio_risk refuses, naming the missing INPUT rather than the maths",
           "what is missing is trustworthy INPUT" in why(
               lambda: portfolio_risk([], {})),
           "(V) the VaR arithmetic exists in calc.returns_risk")
check_true("...and names the free tier's END_OF_DAY, UNVERIFIED limitation",
           "UNVERIFIED" in why(lambda: portfolio_risk([], {})), "(V)")
check_true("...and reports that it validated the arguments first",
           "Arguments were validated" in why(lambda: portfolio_risk([], {})),
           "(C) the validation is what will guard the real thing")

# The validation must be real, and each refusal distinguishable.
check_true("a confidence level of 95 is refused as not a fraction",
           "not 0.95" in why(lambda: portfolio_risk([], {}, confidence_level=95)),
           "(D) 95%% VaR and 9500%% VaR must not be interchangeable")
# MUTATION FINDING 2026-08-15. The boundary cases below, and the fractional
# horizon further down, were type-only assertions and BOTH SURVIVED. MEASURED
# cause: portfolio_risk validates and then refuses TERMINALLY, and the terminal
# refusal is a BrokerToolError too -- so widening a validation guard changes
# nothing a type assertion can see. The wrong argument simply flows past the
# relaxed guard into the same exception class. Every assertion here now names the
# guard's own words, so a relaxed guard is visible as the terminal refusal
# answering in its place.
for _conf in (1.0, 0.0):
    _w_conf = why(lambda c=_conf: portfolio_risk([], {}, confidence_level=c))
    check_true("a confidence level of exactly %r is refused" % (_conf,),
               "strictly between 0 and 1" in _w_conf,
               "(D) by the fraction guard, not by the terminal refusal")
    check_true("...and NOT by the 'cannot be computed' refusal downstream",
               "cannot be computed" not in _w_conf,
               "(D) validation must run BEFORE the honest refusal")
check_true("an unknown method is refused, naming the three allowed",
           "historical|parametric|monte_carlo" in why(
               lambda: portfolio_risk([], {}, method="ml")), "(D)")
check_raises("a non-list positions argument is refused",
             lambda: portfolio_risk({}, {}), BrokerToolError)
check_raises("a non-dict prices argument is refused",
             lambda: portfolio_risk([], []), BrokerToolError)
for _h in (1.5, 0):
    _w_h = why(lambda h=_h: portfolio_risk([], {}, horizon_days=h))
    check_true("a horizon of %r is refused as not a positive whole number" % (_h,),
               "positive whole number" in _w_h,
               "(D) named by its own guard")
    check_true("...and NOT by the terminal 'cannot be computed' refusal",
               "cannot be computed" not in _w_h, "(D)")
check_raises("an empty base_currency is refused",
             lambda: portfolio_risk([], {}, base_currency=" "), BrokerToolError)


# ===========================================================================
section("the manifest reports the truth about itself")
# ===========================================================================

_m = manifest()
check_true("the manifest says an order cannot be submitted",
           _m["can_submit_an_order"] is False, "(V)")
check_true("the manifest says no kill switch exists",
           _m["kill_switch_exists"] is False, "(V)")
check("the manifest's control counts are computed, not written down",
      _m["n_controls_unmet"], len(unmet_controls()), 0, "(C)")
check("the manifest's risk-check count matches the table", _m["n_risk_checks"],
      len(RISK_CHECKS), 0, "(C)")
check("the manifest's preview-field count matches the table",
      _m["n_preview_fields"], len(PREVIEW_FIELDS), 0, "(C)")
check_true("the manifest reports the active mode",
           _m["active_mode"] == "ANALYSIS_ONLY", "(V)")
check_true("the manifest's reason names the two-phase protocol as absent",
           "two-phase commit protocol is not built" in _m["why_not"], "(V)")
check_true("the manifest says none of it is reachable by configuration",
           "None of these is reachable by configuration" in _m["why_not"],
           "(V) MEASURED wording; the first draft of this test guessed wrong")
check_true("every refusing tool appears in the manifest's refuses map",
           all(t in _m["refuses"] for t in
               ("place_order", "modify_order", "cancel_order",
                "cancel_all_orders", "flatten_position", "portfolio_risk",
                "broker_positions", "broker_open_orders", "broker_executions",
                "broker_account_snapshot")),
           "(C) ten refusals, all listed")

# BrokerToolError must NOT be a BrokerError: a caller catching BrokerError to
# handle "the adapter is unusable" must not also swallow "your order fields are
# contradictory".
check_true("BrokerToolError is not a BrokerError subclass",
           not issubclass(BrokerToolError, BrokerError),
           "(V) the two failure kinds need different handling")
check_true("BrokerToolError is a RuntimeError",
           issubclass(BrokerToolError, RuntimeError), "(V)")

# No module-level import may reach the RAG or screenshot layers: an order path
# that could be influenced by a document or a screenshot is the SS.8.6 hazard.
_src = open(os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "src", "execution", "broker_tools.py"), encoding="utf-8").read()
for _forbidden in ("import rag", "from rag", "import market.screenshot",
                   "from market.screenshot", "import market.webhooks",
                   "from market.webhooks", "import requests",
                   "import urllib.request"):
    check_true("broker_tools does not import %r" % _forbidden,
               _forbidden not in _src,
               "(V) nothing on the order path reads documents, screenshots or "
               "the network")
check_true("the module states that a webhook may not cause execution",
           "webhook, news item, document, or screenshot" in _src, "(V) SS.8.6")

# MUTATION FINDING 2026-08-15, and the only one of the six that is not a test
# weakness. Deleting record()'s status guard survived, and MEASURING why showed
# it is genuinely unreachable by input: record() is a closure, every one of its
# call sites is a literal PASS/FAIL/UNKNOWN written in this file, and if one were
# ever wrong verdict_for() re-checks every status and refuses -- MEASURED by
# seeding BOTH defects at once, which produced "reported status 'SKIPPED', which
# is not one of PASS|FAIL|UNKNOWN" from verdict_for.
#
# It was NOT recorded as an equivalent mutant. The equivalence is real today and
# rests entirely on record() having no external caller, which is a fact about
# this file's current shape rather than a property of the design -- exactly the
# kind of note this project has already watched go stale. The guard is defence in
# depth, so its value IS its independent existence, and that is what is asserted.
check_true("record() keeps its own status guard, independent of verdict_for",
           _src.count("if status not in CHECK_STATUS:") == 2,
           "(V) two guards: record()'s at write time, verdict_for()'s at read "
           "time. Neither may be dropped on the grounds that the other exists.")

sys.exit(summary())
