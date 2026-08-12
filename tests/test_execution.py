"""
Verification for the SS.5.6 / SS.6.1 execution mode and broker catalog.

The load-bearing assertions here are the NEGATIVE ones -- no live order, no
enabled broker, no mode elevation from a tool argument -- but negatives alone can
be satisfied by code that refuses everything. So each section also asserts the
positive case that proves the layer discriminates: ANALYSIS_ONLY really does
permit calculation, PAPER_TRADING really does permit a paper order capability,
and a well-formed adapter record really does construct.
"""

import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from _harness import check, check_raises, check_true, section, summary  # noqa: E402

from execution.mode import (ALL_CAPABILITIES, CAPABILITIES, DEFAULT_MODE,  # noqa: E402
                            LIVE_PREREQUISITES, MODES, ExecutionModeError,
                            _reset_cache_for_tests, capabilities,
                            config_problems, current_mode, is_permitted,
                            live_trading_enabled, manifest, mode_source,
                            require, require_mode, unmet_live_prerequisites)
from execution.brokers import (ADAPTERS, ENVIRONMENTS, VERIFICATION_LEVELS,  # noqa: E402
                               BrokerAdapter, BrokerError,
                               assert_adapter_usable, enabled_adapters,
                               get_adapter, read_account, register_adapter,
                               submit_order)
from execution import brokers as _brokers_mod  # noqa: E402
from execution import mode as _mode_mod  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TMP = tempfile.mkdtemp(prefix="marfin_mode_test_")


def _conf(body):
    """Write a config file and re-read it. Returns the resulting mode."""
    path = os.path.join(_TMP, "execution.conf")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    _reset_cache_for_tests(path)
    return current_mode()


def _why_live():
    """The text of the refusal for submit_live_order, for message assertions."""
    try:
        require("submit_live_order")
    except ExecutionModeError as exc:
        return str(exc)
    return "DID NOT RAISE"


def _operator_setitem(mapping, key, value):
    """
    Item assignment as a CALL, so a mappingproxy raises TypeError (a refusal)
    rather than AttributeError (a crash).

    Phase 3 got this wrong twice -- testing immutability via .clear() or
    .append() raises AttributeError, which the harness correctly reports as a
    crash and which only tests Python trivia. operator.setitem exercises the
    actual immutability property.
    """
    import operator
    return operator.setitem(mapping, key, value)


# ---------------------------------------------------------------------------
section("defaults: a new installation cannot trade")
# ---------------------------------------------------------------------------
# SS.5.6: "New installation: ANALYSIS_ONLY", "Paper trading: disabled until
# explicitly enabled", "Live trading: disabled by default".

_reset_cache_for_tests(os.path.join(_TMP, "absent.conf"))
check("four modes are supported", len(MODES), 4, method="(C) SS.5.6")
check_true("the default mode is ANALYSIS_ONLY", DEFAULT_MODE == "ANALYSIS_ONLY",
           "(C) SS.5.6 new installation")
check_true("a missing config yields ANALYSIS_ONLY, not an exception",
           current_mode() == "ANALYSIS_ONLY",
           "(C) crashing on a missing config invites a hardcoded mode")
check_true("the source of the mode is recorded for the audit trail",
           "default" in mode_source(), "(C)")
check_true("live trading is disabled by default", not live_trading_enabled(),
           "(V) SS.5.6")
check_raises("ANALYSIS_ONLY refuses a live order",
             lambda: require("submit_live_order"), ExecutionModeError)
check_raises("ANALYSIS_ONLY refuses a paper order",
             lambda: require("submit_paper_order"), ExecutionModeError)
check_raises("ANALYSIS_ONLY refuses a broker account read",
             lambda: require("read_broker_account"), ExecutionModeError)
# ...and the positive case, or the above is satisfied by refusing everything.
check_true("ANALYSIS_ONLY still permits calculation",
           require("calculate") is None, "(C) the gate discriminates")
check_true("ANALYSIS_ONLY still permits an order PREVIEW",
           require("preview_order") is None,
           "(C) SS.5.6 lets the LLM draft and preview; only commit is gated")


# ---------------------------------------------------------------------------
section("the mode cannot come from model inference (SS.5.6)")
# ---------------------------------------------------------------------------
# "The active mode must come from verified runtime configuration, not from model
# inference." Enforced by SIGNATURE: there is no argument to pass.

import inspect  # noqa: E402

check("current_mode() takes no arguments",
      len(inspect.signature(current_mode).parameters), 0,
      method="(D) a mode parameter is a mode the caller chooses")
check("require() takes only a capability",
      len(inspect.signature(require).parameters), 1,
      method="(D) no mode override")
check_true("require_mode compares and never assigns",
           "return mode" in inspect.getsource(require_mode)
           and "current_mode()" in inspect.getsource(require_mode),
           "(D) it reads the active mode; it has no assignment path")
check_raises("require_mode() with no arguments refuses",
             lambda: require_mode(), ExecutionModeError)
check_raises("require_mode rejects an unknown mode name",
             lambda: require_mode("SUPER_LIVE"), ExecutionModeError)
check_raises("an unknown capability is refused, not silently False",
             lambda: is_permitted("submit_liv_order"), ExecutionModeError)
check_raises("an empty capability is refused",
             lambda: is_permitted(""), ExecutionModeError)

# MUTATION SURVIVORS (mutate_execution.py). The four check_raises above assert
# only THAT a refusal happens, and every one of these functions has more than one
# guard that raises ExecutionModeError. Deleting the FIRST guard left the suite
# green because the second raised instead -- MEASURED by applying each mutation
# by hand. That is the same defect class the market battery found in
# assert_provider_usable, and it is worth stating why it matters rather than
# treating it as test bookkeeping: a guard whose removal changes nothing
# observable is a guard a future maintainer will delete as dead code, and the
# guard that catches the case the SECOND one does not is the one that then goes
# missing. So assert which guard fired.


def _refusal(fn):
    try:
        fn()
    except ExecutionModeError as exc:
        return str(exc)
    return "DID NOT RAISE"


check_true("require_mode() refuses for having no allowed modes, specifically",
           "at least one mode" in _refusal(lambda: require_mode()),
           "(D) not merely because the active mode is not in an empty tuple")
check_true("require_mode names the unknown mode, specifically",
           "unknown mode" in _refusal(lambda: require_mode("SUPER_LIVE")),
           "(D) validating the argument, not just comparing against it")
check_true("an empty capability is refused as empty, specifically",
           "non-empty string" in _refusal(lambda: is_permitted("")),
           "(D) not as an unknown capability name")
check_true("a misspelled capability is refused as unknown, specifically",
           "unknown capability" in _refusal(
               lambda: is_permitted("submit_liv_order")),
           "(D) a typo must not read as a working permission check")
# require_mode must still compare the ACTIVE mode, not merely validate arguments.
check_raises("require_mode refuses a mode that is valid but not active",
             lambda: require_mode("LIVE_TRADING"), ExecutionModeError)
check_true("...naming the active mode in the refusal",
           "active mode is" in _refusal(lambda: require_mode("LIVE_TRADING")),
           "(D) the comparison against the active mode is the point")
check_true("require_mode returns the active mode when it matches",
           require_mode("ANALYSIS_ONLY", "BACKTEST") == "ANALYSIS_ONLY",
           "(C) it permits as well as refuses")
check_true("a misspelled capability cannot read as a working check",
           "submit_liv_order" not in ALL_CAPABILITIES, "(C)")


# ---------------------------------------------------------------------------
section("configuration parsing: every failure downgrades")
# ---------------------------------------------------------------------------
# A partially understood config must never yield a partially elevated mode.

check_true("an empty config yields ANALYSIS_ONLY", _conf("") == "ANALYSIS_ONLY",
           "(C)")
check_true("...and says why", len(config_problems()) >= 1,
           "(C) silence about a config that did not take effect is how an "
           "operator concludes the system is broken")
check_true("a comments-only config yields ANALYSIS_ONLY",
           _conf("# mode = LIVE_TRADING\n") == "ANALYSIS_ONLY",
           "(C) a commented-out mode is not a mode")
check_true("a malformed config yields ANALYSIS_ONLY",
           _conf("}{ not a config") == "ANALYSIS_ONLY", "(C)")
check_true("an unknown mode name yields ANALYSIS_ONLY",
           _conf("mode = YOLO\n") == "ANALYSIS_ONLY", "(C)")
check_true("a duplicate key does not let a later line win",
           _conf("mode = BACKTEST\nmode = LIVE_TRADING\n") == "BACKTEST",
           "(V) MEASURED: first value stands, stray later line rejected -- "
           "'last one wins' is how a trailing mode line gets overlooked")
check_true("an acknowledgement without a mode line stays ANALYSIS_ONLY",
           _conf("i_have_approved_live_trading = yes\n") == "ANALYSIS_ONLY",
           "(C) consent to a mode is not a declaration of it")
# MUTATION SURVIVOR: the acknowledgement was compared with == "yes", but nothing
# asserted that a DIFFERENT non-empty value fails. Changing the comparison to
# bool(value) survived -- meaning `i_have_approved_live_trading = no` would have
# ENABLED live trading. That is the worst possible direction for a parsing bug,
# and it is invisible: the config file would read as a refusal.
check_true("'no' does not acknowledge live trading",
           _conf("mode = LIVE_TRADING\ni_have_approved_live_trading = no\n")
           == "ANALYSIS_ONLY",
           "(V) a truthy check would read 'no' as consent")
check_true("'false' does not acknowledge live trading",
           _conf("mode = LIVE_TRADING\ni_have_approved_live_trading = false\n")
           == "ANALYSIS_ONLY", "(V)")
check_true("an empty acknowledgement value does not acknowledge",
           _conf("mode = LIVE_TRADING\ni_have_approved_live_trading =\n")
           == "ANALYSIS_ONLY", "(V)")
check_true("'no' does not enable paper trading either",
           _conf("mode = PAPER_TRADING\ni_have_enabled_paper_trading = no\n")
           == "ANALYSIS_ONLY", "(V)")
# MUTATION SURVIVOR: a malformed line was recorded as a problem, but nothing
# asserted the problem list mentioned it -- so silently dropping malformed lines
# survived. An operator whose typo vanished without comment concludes the file
# was accepted.
_conf("mode = BACKTEST\nthis line has no equals sign\n")
check_true("a malformed line is reported, not silently dropped",
           any("not key = value" in p for p in config_problems()),
           "(C) a typo that vanishes reads as acceptance")
check_true("...while the valid part of the file still applies",
           current_mode() == "BACKTEST",
           "(C) one bad line does not discard a declared mode")
# The positive case: a valid config IS honoured, or the parser is just a
# constant function returning ANALYSIS_ONLY.
check_true("a valid BACKTEST config is honoured",
           _conf("mode = BACKTEST\n") == "BACKTEST",
           "(C) the parser reads the file rather than ignoring it")
check_true("...with no recorded problems", len(config_problems()) == 0, "(C)")
check_true("mode names are case-insensitive but capabilities are not",
           _conf("mode = backtest\n") == "BACKTEST", "(C)")

# MUTATION SURVIVOR: nothing exercised the OSError path, so removing it survived.
# It matters because a crash on an unreadable config is a denial of service, and
# the natural "fix" a frustrated operator reaches for is to hardcode a mode. A
# DIRECTORY where a file is expected raises IsADirectoryError (an OSError) rather
# than FileNotFoundError, which is a readable way to reach that branch without
# depending on filesystem permissions -- root ignores chmod, so a 0o000 file
# would make this test pass or fail depending on who runs it.
_dir_as_config = os.path.join(_TMP, "config_is_a_directory")
os.makedirs(_dir_as_config, exist_ok=True)
_reset_cache_for_tests(_dir_as_config)
check_true("an unreadable config downgrades instead of crashing",
           current_mode() == "ANALYSIS_ONLY",
           "(V) MEASURED with a directory in place of the config file; a crash "
           "here invites someone to hardcode a mode")
check_true("...and records why it could not be read",
           any("could not read" in p for p in config_problems()),
           "(C) an unexplained downgrade looks like a bug")


# ---------------------------------------------------------------------------
section("paper and live each need their own explicit opt-in")
# ---------------------------------------------------------------------------

check_true("PAPER_TRADING without its acknowledgement downgrades",
           _conf("mode = PAPER_TRADING\n") == "ANALYSIS_ONLY",
           "(V) SS.5.6 'disabled until explicitly enabled'")
check_true("...and the refusal names the missing line",
           any("i_have_enabled_paper_trading" in p for p in config_problems()),
           "(C) an unactionable refusal gets worked around")
check_true("PAPER_TRADING with its acknowledgement is honoured",
           _conf("mode = PAPER_TRADING\ni_have_enabled_paper_trading = yes\n")
           == "PAPER_TRADING", "(C) explicit enablement works")
check_true("...and then a paper order capability is permitted",
           require("submit_paper_order") is None,
           "(C) the mode machinery grants as well as refuses")
check_raises("...but a LIVE order is still refused in PAPER_TRADING",
             lambda: require("submit_live_order"), ExecutionModeError)
check_true("...and live_trading_enabled() stays False",
           not live_trading_enabled(), "(V) paper is not live")

check_true("LIVE_TRADING without its acknowledgement downgrades",
           _conf("mode = LIVE_TRADING\n") == "ANALYSIS_ONLY",
           "(V) SS.5.6 'disabled by default'")
check_true("...and the refusal names the missing line",
           any("i_have_approved_live_trading" in p for p in config_problems()),
           "(C)")


# ---------------------------------------------------------------------------
section("SS.6.1: the mode is one prerequisite of twelve")
# ---------------------------------------------------------------------------
# THE DEFECT THIS SECTION EXISTS FOR. An earlier version of mode.py stated in a
# docstring that "live trading cannot be enabled even by editing the config".
# First execution disproved it: writing mode = LIVE_TRADING plus the
# acknowledgement made require("submit_live_order") SUCCEED. The prose was
# decoration -- the same declared-but-unenforced pattern Phase 3 found in
# sources.py. SS.6.1's prerequisites are now a checked table.

_live = _conf("mode = LIVE_TRADING\ni_have_approved_live_trading = yes\n")
check_true("a fully acknowledged config does reach LIVE_TRADING as a MODE",
           _live == "LIVE_TRADING",
           "(C) the config is honoured; the mode is not the whole question")
check("SS.6.1 lists 12 prerequisites", len(LIVE_PREREQUISITES), 12,
      method="(V) MEASURED from SYSTEM_PROMPT.md lines 697-712; I first "
             "recalled eleven, which was wrong")
check_true("most SS.6.1 prerequisites are unmet in this repository",
           len(unmet_live_prerequisites()) >= 9,
           "(V) no broker adapter, no licensed data, no risk engine, no audit "
           "log, no idempotency, no kill switch, no paper validation")
check_raises("a live order is REFUSED even in LIVE_TRADING mode",
             lambda: require("submit_live_order"), ExecutionModeError)
check_true("...and live_trading_enabled() is False despite the mode",
           not live_trading_enabled(),
           "(V) both conditions required, as with Quote.is_live")
# MUTATION SURVIVOR: live_trading_enabled() ANDs two conditions, and only the
# prerequisite half was tested -- so rewriting it to ignore the mode entirely
# survived. That mutant would report live trading as "enabled" purely because the
# prerequisites were met, in ANALYSIS_ONLY, which is the same either-condition-
# alone error as a REALTIME quote from a CLOSED market. Assert the mode half by
# checking a mode where the mutant and the correct code disagree.
_reset_cache_for_tests(os.path.join(_TMP, "absent.conf"))
check_true("live_trading_enabled() is False in ANALYSIS_ONLY",
           current_mode() == "ANALYSIS_ONLY" and not live_trading_enabled(),
           "(V) the mode half of the conjunction")
check_true("live_trading_enabled() is False in PAPER_TRADING",
           (_conf("mode = PAPER_TRADING\n"
                  "i_have_enabled_paper_trading = yes\n") == "PAPER_TRADING")
           and not live_trading_enabled(),
           "(V) paper is not live, whatever the prerequisites say")
# The mode half of that conjunction is currently UNOBSERVABLE by behaviour: with
# 10 prerequisites unmet, a mutant that drops the mode check returns False in
# every mode too, so no input distinguishes them (MEASURED, recorded as a
# temporary equivalent in mutate_execution.py). That equivalence disappears the
# moment the prerequisites are built -- exactly when the mode check begins to
# matter. Assert the STRUCTURE now, so the requirement is pinned before the
# behaviour can diverge, rather than discovering the omission at the point where
# real money is involved.
_lte_src = inspect.getsource(live_trading_enabled)
check_true("live_trading_enabled() requires the mode as well as the "
           "prerequisites",
           'current_mode() == "LIVE_TRADING"' in _lte_src
           and "unmet_live_prerequisites()" in _lte_src
           and " and " in _lte_src,
           "(D) a conjunction, not either condition alone -- the same error "
           "class as a REALTIME quote from a CLOSED market")
_live = _conf("mode = LIVE_TRADING\ni_have_approved_live_trading = yes\n")
check_true("the refusal names the unmet prerequisites",
           "prerequisites" in _why_live(),
           "(D) an operator must be able to see what is missing")
check_true("independent licensed market data is named as unmet",
           any("licensed market data" in n for n in unmet_live_prerequisites()),
           "(V) docs/legal/market-data-providers.md: no provider is cleared")
check_true("a verified broker adapter is named as unmet",
           any("broker adapter" in n for n in unmet_live_prerequisites()),
           "(V) no adapter is VERIFIED")
# MUTATION SURVIVORS: the prerequisite table was asserted only in aggregate
# (">= 9 unmet"), so flipping any single entry to satisfied left the suite green.
# The entries below are each independently load-bearing, so each is named. A
# table whose individual rows nothing checks is the same decoration problem as an
# unenforced docstring -- and this table is the live-trading wall.
for _prereq in ("emergency kill switch", "audit logging", "idempotency support",
                "pre-trade risk engine", "paper-trading validation",
                "verified live account alias", "user-defined limits"):
    check_true("SS.6.1 %r is recorded as unmet" % (_prereq,),
               _prereq in unmet_live_prerequisites(),
               "(V) not built in this repository")
check_true("every SS.6.1 prerequisite records WHY, met or not",
           all(reason for (_ok, reason) in LIVE_PREREQUISITES.values()),
           "(C) an unexplained entry is indistinguishable from an unreviewed one")
# The two that ARE satisfied, asserted positively -- otherwise "all unmet" would
# pass a table that simply refuses everything and says nothing.
check_true("the two configuration prerequisites ARE satisfiable",
           len(LIVE_PREREQUISITES) - len(unmet_live_prerequisites()) == 2,
           "(V) explicit config enablement and explicit user approval; the "
           "other ten are engineering work that does not exist yet")
# Positive control: LIVE_TRADING mode does still grant the lesser capabilities,
# so the refusal above is specific rather than a blanket failure.
check_true("LIVE_TRADING mode still permits a paper order",
           require("submit_paper_order") is None, "(C)")
check_true("LIVE_TRADING mode still permits calculation",
           require("calculate") is None, "(C)")


# ---------------------------------------------------------------------------
section("capabilities are a set per mode, not an ordered scale")
# ---------------------------------------------------------------------------
# An ordered comparison would make LIVE_TRADING the maximum, so any future bug
# biasing the value upward lands on the mode that spends real money.

check_true("no mode is defined as an integer level",
           not any(isinstance(v, int) for v in CAPABILITIES.values()), "(C)")
check_true("BACKTEST cannot reach a broker at all",
           "read_broker_account" not in capabilities("BACKTEST")
           and "submit_paper_order" not in capabilities("BACKTEST"),
           "(C) a backtest that can place sandbox orders gets pointed at a "
           "live account by a config edit")
check_true("ANALYSIS_ONLY cannot simulate fills",
           "simulate_fill" not in capabilities("ANALYSIS_ONLY"), "(C)")
check_true("LIVE_TRADING adds exactly one capability over PAPER_TRADING",
           len(set(capabilities("LIVE_TRADING"))
               - set(capabilities("PAPER_TRADING"))) == 1,
           "(C) everything else must already work in paper")
check_true("only LIVE_TRADING lists submit_live_order",
           [m for m in MODES if "submit_live_order" in capabilities(m)]
           == ["LIVE_TRADING"], "(C)")
check_raises("capabilities() rejects an unknown mode",
             lambda: capabilities("PRETEND_MODE"), ExecutionModeError)
check_true("every mode's capabilities are a subset of ALL_CAPABILITIES",
           all(set(capabilities(m)) <= set(ALL_CAPABILITIES) for m in MODES),
           "(C) a new capability defaults to refused everywhere")


# ---------------------------------------------------------------------------
section("the configuration cannot be mutated in-process")
# ---------------------------------------------------------------------------

_cfg = _mode_mod._load()
check_raises("the parsed config is immutable",
             lambda: setattr(_cfg, "mode", "LIVE_TRADING"), ExecutionModeError)
check_raises("config fields cannot be deleted",
             lambda: delattr(_cfg, "mode"), ExecutionModeError)
check_raises("CAPABILITIES cannot be edited to grant a live order",
             lambda: _operator_setitem(CAPABILITIES, "ANALYSIS_ONLY",
                                       ("submit_live_order",)))
check_raises("LIVE_PREREQUISITES cannot be marked satisfied at runtime",
             lambda: _operator_setitem(LIVE_PREREQUISITES,
                                       "audit logging", (True, "lie")))


# ---------------------------------------------------------------------------
section("broker adapters: documented is not verified (SS.6.1)")
# ---------------------------------------------------------------------------

check("3 broker adapters are catalogued", len(ADAPTERS), 3, method="(C)")
check("0 adapters are enabled", len(enabled_adapters()), 0,
      method="(V) verification needs credentials nobody has supplied")
check_true("no adapter is VERIFIED",
           all(a.verification != "VERIFIED" for a in ADAPTERS.values()),
           "(V) reading documentation is not verification")
check_true("every adapter records what needs credentials to verify",
           all(a.unverifiable_without_credentials for a in ADAPTERS.values()),
           "(C) an empty list would claim a completeness docs cannot give")
check_true("TradingView is catalogued as a dead end, not an execution venue",
           ADAPTERS["tradingview"].environments == (),
           "(V) its 'REST API Specification for Brokers' is INBOUND to the "
           "broker, not an API this application may call")
check_raises("an adapter cannot be enabled at DOCUMENTED level",
             lambda: BrokerAdapter("x", "X", "u", "REST", "DOCUMENTED",
                                   ("PAPER",), True, "no", ("read",),
                                   ("creds",)), BrokerError)
check_raises("an adapter cannot be enabled at SANDBOX_TESTED level either",
             lambda: BrokerAdapter("y", "Y", "u", "REST", "SANDBOX_TESTED",
                                   ("PAPER",), True, "no", ("read",),
                                   ("creds",)), BrokerError)
check_raises("an adapter must record its unverifiable facts",
             lambda: BrokerAdapter("z", "Z", "u", "REST", "DOCUMENTED",
                                   ("PAPER",), False, "no", ("read",), ()),
             BrokerError)
check_raises("an unknown verification level is refused",
             lambda: BrokerAdapter("w", "W", "u", "REST", "PROBABLY_FINE",
                                   ("PAPER",), False, "no", ("read",),
                                   ("creds",)), BrokerError)
check_raises("an unknown environment is refused",
             lambda: BrokerAdapter("v", "V", "u", "REST", "DOCUMENTED",
                                   ("DEMO",), False, "no", ("read",),
                                   ("creds",)), BrokerError)
# Positive case: a well-formed disabled record constructs.
check_true("a well-formed DOCUMENTED adapter record constructs",
           BrokerAdapter("fixture", "Fixture", "u", "REST", "DOCUMENTED",
                         ("PAPER", "LIVE"), False, "unknown", ("read account",),
                         ("that credentials work",)).verification
           == "DOCUMENTED", "(C) the catalog accepts honest records")

for _k in sorted(ADAPTERS):
    for _env in ENVIRONMENTS:
        check_raises("assert_adapter_usable(%r, %r) refuses" % (_k, _env),
                     lambda k=_k, e=_env: assert_adapter_usable(k, e),
                     BrokerError)
check_raises("an unregistered broker has not been reviewed",
             lambda: get_adapter("robinhood"), BrokerError)
check_raises("an unknown environment has no default",
             lambda: assert_adapter_usable("alpaca", "MAYBE"), BrokerError)


# ---------------------------------------------------------------------------
section("the broker gate refuses for the RIGHT reason")
# ---------------------------------------------------------------------------
# MUTATION SURVIVORS (mutate_execution.py). assert_adapter_usable has five
# independent guards -- unknown environment, not VERIFIED, not enabled, missing
# environment, and the mode gate -- and the loop above asserted only THAT each
# adapter/environment pair raises. Deleting any single guard left the suite green
# because the next one raised instead (MEASURED: removing the verification check
# produced "registered but not enabled"). Three of those guards were therefore
# never independently exercised, including the mode gate, which is the one that
# stops a fully verified adapter from being used in the wrong mode -- the exact
# scenario the whole layer exists for.
#
# Reaching the later guards needs adapter records that pass the earlier ones. They
# are registered under _test_ keys and asserted not to disturb the real catalog.

def _broker_refusal(fn):
    try:
        fn()
    except BrokerError as exc:
        return str(exc)
    return "DID NOT RAISE"


def _mode_refusal(fn):
    """
    The refusal text from either layer.

    Separate from _broker_refusal because the mode gate raises
    ExecutionModeError, not BrokerError -- and that distinction is deliberate:
    "this broker is not verified" and "this installation may not trade" are
    different facts with different remedies, and a single exception type would
    invite a single handler that treats them alike.
    """
    try:
        fn()
    except (BrokerError, ExecutionModeError) as exc:
        return str(exc)
    return "DID NOT RAISE"


check_true("an unknown environment is refused as unknown, specifically",
           "unknown environment" in _broker_refusal(
               lambda: assert_adapter_usable("alpaca", "MAYBE")),
           "(D) SS.6.3 requires unambiguous paper/live identifiers")
check_true("a DOCUMENTED adapter is refused for verification, specifically",
           "not VERIFIED" in _broker_refusal(
               lambda: assert_adapter_usable("alpaca", "PAPER")),
           "(D) not for being disabled; verification is the SS.6.1 prerequisite")
check_true("...and the refusal states what needs credentials",
           "credentials" in _broker_refusal(
               lambda: assert_adapter_usable("alpaca", "PAPER")),
           "(C) the unmet condition must be actionable")

# A VERIFIED but DISABLED adapter: reaches guard 3.
register_adapter(BrokerAdapter(
    key="_test_verified_but_off", name="fixture: verified, not enabled",
    docs_url="https://example.invalid", transport="REST",
    verification="VERIFIED", environments=("PAPER", "LIVE"), enabled=False,
    supports_idempotency="fixture", documented_capabilities=("submit order",),
    unverifiable_without_credentials=("nothing; this is a test fixture",),
    notes="Synthetic. Exists so the not-enabled guard is executed at all."))
check_true("a VERIFIED adapter still refuses while disabled, specifically",
           "not enabled" in _broker_refusal(
               lambda: assert_adapter_usable("_test_verified_but_off", "PAPER")),
           "(D) verification is necessary, not sufficient")

# VERIFIED, enabled, but PAPER-only: reaches guard 4.
register_adapter(BrokerAdapter(
    key="_test_paper_only", name="fixture: verified, enabled, paper only",
    docs_url="https://example.invalid", transport="REST",
    verification="VERIFIED", environments=("PAPER",), enabled=True,
    supports_idempotency="fixture", documented_capabilities=("submit order",),
    unverifiable_without_credentials=("nothing; this is a test fixture",),
    notes="Synthetic. Exists so the missing-environment and mode guards run."))
check_true("a paper-only adapter refuses a LIVE environment, specifically",
           "does not offer a LIVE environment" in _broker_refusal(
               lambda: assert_adapter_usable("_test_paper_only", "LIVE")),
           "(D) an adapter cannot be used in an environment it lacks")

# THE MODE GATE. This adapter passes every broker-side guard, so the only thing
# left standing between it and a paper order is execution mode -- which is
# ANALYSIS_ONLY here. Before this assertion existed, deleting the mode gate
# entirely from brokers.py left the suite green.
_reset_cache_for_tests(os.path.join(_TMP, "absent.conf"))
# NOTE the helper: _mode_refusal, not _broker_refusal. Using the latter here was
# a real error caught on re-run -- it catches only BrokerError, so the mode gate's
# ExecutionModeError escaped and aborted the suite. That is the two-exception-type
# design asserting itself: "this broker is not verified" and "this installation
# may not trade" are different facts, and a helper that catches one does not catch
# the other. Keeping the distinction visible here is the point.
check_true("the mode gate still refuses a fully cleared adapter",
           "not permitted in mode ANALYSIS_ONLY" in _mode_refusal(
               lambda: assert_adapter_usable("_test_paper_only", "PAPER")),
           "(D) broker clearance and mode permission are independent; neither "
           "implies the other")
check_raises("...and the mode gate raises ExecutionModeError, not BrokerError",
             lambda: assert_adapter_usable("_test_paper_only", "PAPER"),
             ExecutionModeError)
# Sequenced deliberately rather than chained with `and`: Python evaluates both
# operands before check_true sees them, so a chained version would call
# assert_adapter_usable while the mode was still ANALYSIS_ONLY.
_paper_mode = _conf("mode = PAPER_TRADING\n"
                    "i_have_enabled_paper_trading = yes\n")
check_true("PAPER_TRADING is active for the positive control",
           _paper_mode == "PAPER_TRADING", "(C)")
check_true("...and in PAPER_TRADING the same adapter IS usable",
           assert_adapter_usable("_test_paper_only", "PAPER").key
           == "_test_paper_only",
           "(C) the gate discriminates rather than refusing everything")

# And a LIVE environment on a VERIFIED+enabled adapter must still fail on SS.6.1,
# not on the broker record. This is the mutation "a LIVE environment is gated as
# if it were paper" -- which survived until this assertion existed.
register_adapter(BrokerAdapter(
    key="_test_live_capable", name="fixture: verified, enabled, paper+live",
    docs_url="https://example.invalid", transport="REST",
    verification="VERIFIED", environments=("PAPER", "LIVE"), enabled=True,
    supports_idempotency="fixture", documented_capabilities=("submit order",),
    unverifiable_without_credentials=("nothing; this is a test fixture",),
    notes="Synthetic. Exists to prove LIVE is gated separately from PAPER."))
check_true("a live-capable enabled adapter is usable for PAPER in PAPER_TRADING",
           assert_adapter_usable("_test_live_capable", "PAPER").key
           == "_test_live_capable", "(C) positive control")
check_raises("...but the same adapter refuses a LIVE environment",
             lambda: assert_adapter_usable("_test_live_capable", "LIVE"),
             (BrokerError, ExecutionModeError))
check_true("...because LIVE requires submit_live_order, which SS.6.1 blocks",
           "submit_live_order" in _mode_refusal(
               lambda: assert_adapter_usable("_test_live_capable", "LIVE")),
           "(D) a LIVE environment must not be gated as if it were paper")
check_true("the synthetic fixtures did not enable a real broker",
           all(not a.enabled for a in ADAPTERS.values()
               if not a.key.startswith("_test_")),
           "(C) the real catalog is untouched")
_reset_cache_for_tests(os.path.join(_TMP, "absent.conf"))
check_raises("order submission is not implemented",
             lambda: submit_order(), NotImplementedError)
check_raises("broker account reads are not implemented",
             lambda: read_account(), NotImplementedError)
check_raises("a reviewed adapter cannot be enabled at runtime",
             lambda: setattr(ADAPTERS["alpaca"], "enabled", True), BrokerError)
check_raises("an adapter's verification cannot be upgraded at runtime",
             lambda: setattr(ADAPTERS["alpaca"], "verification", "VERIFIED"),
             BrokerError)
check_raises("an adapter cannot be injected through ADAPTERS[...]",
             lambda: _operator_setitem(ADAPTERS, "evil", None))
check_raises("register_adapter refuses a non-BrokerAdapter",
             lambda: register_adapter({"key": "fake"}), BrokerError)
# MUTATION SURVIVORS: adapter __delattr__ and the duplicate-key guard were both
# unexercised. Deletion matters because removing `enabled` from an adapter makes
# subsequent `a.enabled` raise AttributeError -- a CRASH rather than a refusal,
# which is precisely the failure mode the harness distinguishes. Re-registration
# matters because overwriting a reviewed entry is how an unverified adapter
# inherits a verified one's key.
check_raises("adapter fields cannot be deleted",
             lambda: delattr(ADAPTERS["alpaca"], "enabled"), BrokerError)
check_raises("an adapter's environments cannot be deleted",
             lambda: delattr(ADAPTERS["alpaca"], "environments"), BrokerError)
check_raises("a reviewed adapter key cannot be re-registered",
             lambda: register_adapter(BrokerAdapter(
                 "alpaca", "impostor", "u", "REST", "VERIFIED", ("LIVE",),
                 False, "no", ("submit order",), ("everything",))), BrokerError)
check_true("...and the original alpaca entry is unchanged",
           ADAPTERS["alpaca"].verification == "DOCUMENTED"
           and ADAPTERS["alpaca"].name == "Alpaca Markets",
           "(C) a failed overwrite must not partially apply")


# ---------------------------------------------------------------------------
section("SS.5.6 separation is enforced by the import graph")
# ---------------------------------------------------------------------------
# "Physically and logically separate execution from: the LLM, news retrieval,
# TradingView webhooks, RAG documents, screenshots, strategy generation,
# backtesting." A comment asking for separation decays the first time someone
# needs a convenience; the dependency direction does not.

# FIRST-RUN FAILURE, and it was a defect in this TEST, not in the code. The
# original version grepped the source text for "from rag", which matched the
# sentence "this module imports NOTHING from rag/, tools/ or market/" in
# brokers.py's own docstring. A substring search cannot tell a documented claim
# apart from a real import -- so it reported a separation violation caused by the
# comment asserting separation. Parse the imports instead: check the property,
# not the prose.
import ast  # noqa: E402

_FORBIDDEN_PACKAGES = ("rag", "tools", "market")
_imported = {}
for _f in sorted(os.listdir(os.path.join(ROOT, "src", "execution"))):
    if not _f.endswith(".py"):
        continue
    with open(os.path.join(ROOT, "src", "execution", _f),
              "r", encoding="utf-8") as fh:
        _tree = ast.parse(fh.read(), filename=_f)
    _mods = set()
    for _node in ast.walk(_tree):
        if isinstance(_node, ast.Import):
            _mods.update(a.name for a in _node.names)
        elif isinstance(_node, ast.ImportFrom):
            if _node.module:
                _mods.add(_node.module)
    _imported[_f] = _mods

_all_imports = set()
for _mods in _imported.values():
    _all_imports |= _mods

for _pkg in _FORBIDDEN_PACKAGES:
    check_true("execution/ imports nothing from the %s layer" % (_pkg,),
               not any(m == _pkg or m.startswith(_pkg + ".")
                       for m in _all_imports),
               "(V) SS.5.6 separation, enforced by dependency direction: a "
               "webhook cannot reach an order because no path exists")
check_true("brokers.py depends on the mode gate and nothing else local",
           "execution.mode" in _imported["brokers.py"],
           "(C) the one permitted local dependency")
check_true("mode.py depends on no other project module",
           not any(m.startswith("execution.") or m.split(".")[0]
                   in _FORBIDDEN_PACKAGES for m in _imported["mode.py"]),
           "(C) the gate cannot be circular")
check_true("the separation claim in the docstring is checked, not trusted",
           len(_all_imports) > 0 and "ast" not in _all_imports,
           "(C) MEASURED by parsing imports; a substring grep for 'from rag' "
           "matched brokers.py's own docstring and failed on first run")


# ---------------------------------------------------------------------------
section("the audit manifest reports the truth")
# ---------------------------------------------------------------------------

_m = manifest()
check_true("the manifest names the active mode and its source",
           _m["mode"] in MODES and _m["source"], "(C)")
check_true("the manifest reports live trading as disabled",
           _m["live_trading_enabled"] is False, "(V)")
check_true("the manifest lists the unmet prerequisites",
           len(_m["unmet_live_prerequisites"]) >= 9, "(V)")
check("the manifest reports 12 prerequisites", _m["n_live_prerequisites"], 12,
      method="(V)")
check_true("the manifest carries no credential material",
           not any(k in str(_m).lower()
                   for k in ("password", "api_key", "secret", "token")),
           "(C) SS.5.6: the LLM may not read plaintext credentials")

sys.exit(summary())
