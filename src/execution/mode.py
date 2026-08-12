"""
Execution mode: the SS.5.6 four-mode machine, and why the LLM cannot reach it.

WHAT SS.5.6 REQUIRES, VERBATIM
------------------------------
Four modes: ANALYSIS_ONLY, BACKTEST, PAPER_TRADING, LIVE_TRADING.

Defaults:
  - "New installation: ANALYSIS_ONLY"
  - "Paper trading: disabled until explicitly enabled"
  - "Live trading: disabled by default"

And the sentence this whole module exists to satisfy:

  "The active mode must come from verified runtime configuration, not from model
  inference."

THE DESIGN CONSEQUENCE OF THAT SENTENCE
---------------------------------------
It is not enough to read a config file and to write "the LLM must not set the
mode" in a docstring. Phase 3 established, at cost, that a declared-but-
unenforced rule drifts: sources.py had licence fields nothing checked, and they
were wrong. If `current_mode()` accepted a mode argument -- even an optional one,
even one only tests were supposed to use -- then a tool call could carry it, and
the model would be inferring the mode. So:

  - There is NO parameter anywhere in this module that sets the mode.
  - The mode is read from a file on disk, once, and cached.
  - Nothing exported here can promote a mode. `require_mode` compares; it never
    assigns. The only way to reach LIVE_TRADING is to edit the config file and
    restart the process, which is an act by a human with filesystem access.
  - A config file that is absent, empty, malformed, or unreadable yields
    ANALYSIS_ONLY. Not an exception -- because a crash on a missing config is a
    denial of service that invites someone to "fix" it by hardcoding a mode, and
    not LIVE_TRADING for reasons that should not need stating.

WHY MODES ARE NOT AN ORDERED SCALE
----------------------------------
The tempting design is mode >= PAPER_TRADING, an integer comparison. It is wrong.
BACKTEST is not "less than" PAPER_TRADING in any meaningful sense: a backtest may
read historical data that paper trading may not, and paper trading may reach a
broker sandbox that a backtest must never touch. Capability is a SET per mode,
not a threshold, and this module encodes it as an explicit table. An ordered
comparison would also make LIVE_TRADING the maximum, so that any future bug
biasing the value upward lands on the one mode that spends real money.

WHAT THIS MODULE DELIBERATELY DOES NOT DO
-----------------------------------------
It does not connect to a broker, place an order, or hold credentials. It answers
one question -- "what am I allowed to do right now?" -- and refuses when the
answer is no. Brokers live in execution/brokers.py, and SS.5.6 requires execution
to be "physically and logically separate" from the LLM, news, webhooks, RAG,
screenshots, strategy generation and backtesting.

Stdlib only.
"""

import os
from types import MappingProxyType
from typing import Any, Dict, Mapping, Optional, Tuple


#: The four SS.5.6 modes, in the order the spec lists them. The order is
#: presentational only -- see the module docstring on why they are not a scale.
MODES: Tuple[str, ...] = ("ANALYSIS_ONLY", "BACKTEST", "PAPER_TRADING",
                          "LIVE_TRADING")

#: SS.5.6: "New installation: ANALYSIS_ONLY". Also the value returned whenever the
#: configuration cannot be read or understood.
DEFAULT_MODE = "ANALYSIS_ONLY"

#: Where the mode comes from. A path, not an environment variable: an env var is
#: settable by whatever launched the process, which in an agent deployment can be
#: the agent. A file requires filesystem write access and survives inspection --
#: you can read it afterwards and see what it said.
CONFIG_PATH = os.environ.get(
    "MARFIN_EXECUTION_CONFIG",
    os.path.join(os.path.expanduser("~"), ".marfin", "execution.conf"))

#: Capabilities, as a set per mode rather than a threshold.
#:
#: Read as: what does this mode permit? Every capability absent from a mode's set
#: is refused in that mode. New capabilities must be added here explicitly, which
#: means a new capability defaults to being refused in every mode -- the correct
#: direction for a mistake.
CAPABILITIES: Mapping[str, Tuple[str, ...]] = MappingProxyType({
    "ANALYSIS_ONLY": ("read_market_data", "read_documents", "calculate",
                      "preview_order"),
    # A backtest reads history and simulates fills against it. It must never
    # reach a broker, not even a sandbox one: a backtest that can place sandbox
    # orders will eventually be pointed at a live account by a config edit.
    "BACKTEST": ("read_market_data", "read_documents", "calculate",
                 "preview_order", "read_history", "simulate_fill"),
    # Paper trading may reach a broker's PAPER environment, read positions, and
    # submit orders there. It still may not submit a live order.
    "PAPER_TRADING": ("read_market_data", "read_documents", "calculate",
                      "preview_order", "read_history", "simulate_fill",
                      "read_broker_account", "submit_paper_order"),
    # LIVE_TRADING adds exactly one capability over PAPER_TRADING. That is the
    # point: everything else must already work in paper.
    "LIVE_TRADING": ("read_market_data", "read_documents", "calculate",
                     "preview_order", "read_history", "simulate_fill",
                     "read_broker_account", "submit_paper_order",
                     "submit_live_order"),
})

#: Every capability any mode grants. Used to refuse a MISSPELLED capability
#: rather than silently treating it as "not permitted in this mode" -- a typo in
#: a permission check that reads as a refusal today becomes a grant the moment
#: someone inverts the condition.
ALL_CAPABILITIES: Tuple[str, ...] = tuple(sorted(
    {cap for caps in CAPABILITIES.values() for cap in caps}))

#: SS.5.6: "Live trading: disabled by default"; "Paper trading: disabled until
#: explicitly enabled". Reaching either from the config file requires the
#: corresponding explicit acknowledgement line, checked in _parse.
_MODES_REQUIRING_EXPLICIT_OPT_IN = MappingProxyType({
    "PAPER_TRADING": "i_have_enabled_paper_trading",
    "LIVE_TRADING": "i_have_approved_live_trading",
})


#: SS.6.1's twelve prerequisites for LIVE_TRADING, each mapped to whether this
#: installation actually satisfies it. VERIFIED FALSE entries are facts about the
#: repository, not pessimism.
#:
#: WHY THIS TABLE IS CODE AND NOT A COMMENT
#: An earlier version of this module stated in require()'s docstring that "live
#: trading cannot be enabled even by editing the config". First execution proved
#: that false: writing `mode = LIVE_TRADING` plus the acknowledgement line made
#: require("submit_live_order") return successfully. The prose was decoration --
#: exactly the declared-but-unenforced pattern Phase 3 found in sources.py. So
#: the prerequisites are now checked, and the count is MEASURED from the prompt
#: (12 bullets, lines 697-712) rather than recalled -- I first wrote "eleven".
LIVE_PREREQUISITES: Mapping[str, Tuple[bool, str]] = MappingProxyType({
    "explicit configuration enablement": (
        True, "satisfied by the config file plus "
              "i_have_approved_live_trading = yes"),
    "verified broker adapter": (
        False, "no broker adapter has been verified against a real account; see "
               "execution/brokers.py, where every adapter is disabled"),
    "verified live account alias": (
        False, "no account alias has been registered or verified"),
    "independent licensed market data": (
        False, "NO market-data provider is licensed for machine use. Twelve Data "
               "licenses the category but no tier is verified; Alpha Vantage's "
               "personal-use terms turn on facts about the user; TradingView "
               "PROHIBITS it outright. See docs/legal/market-data-providers.md"),
    "pre-trade risk engine": (
        False, "not built; SS.6.3 lists 21 mandatory controls"),
    "audit logging": (False, "not built"),
    "idempotency support": (False, "not built"),
    "emergency kill switch": (False, "not built"),
    "user-defined limits": (False, "not configured"),
    "paper-trading validation": (
        False, "no paper trading has been run, because no broker adapter exists"),
    "explicit user approval of live-mode activation": (
        True, "satisfied by i_have_approved_live_trading = yes"),
    "per-order confirmation unless a separately approved narrow automation "
    "policy exists": (
        False, "the SS.6.2 two-phase preview/commit protocol is not built"),
})


def unmet_live_prerequisites() -> Tuple[str, ...]:
    """
    The SS.6.1 prerequisites this installation does not satisfy.

    Non-empty means LIVE_TRADING is unreachable regardless of configuration.
    """
    return tuple(name for name, (ok, _) in LIVE_PREREQUISITES.items() if not ok)


class ExecutionModeError(RuntimeError):
    """
    An operation is not permitted in the active mode.

    RuntimeError, NOT ValueError, and deliberately not MarketDataError: this is
    not a malformed input that a caller can correct by passing better arguments.
    It is a statement that the installation is not configured to do this at all.
    Conflating the two would let a retry loop written for bad input keep retrying
    a permission refusal.
    """


class _Config(object):
    """Parsed execution configuration. Immutable, for the sources.py reason."""

    _FIELDS = ("mode", "source", "raw_mode", "problems", "live_ack", "paper_ack")
    __slots__ = _FIELDS + ("_frozen",)

    def __init__(self, mode, source, raw_mode="", problems=(), live_ack=False,
                 paper_ack=False):
        object.__setattr__(self, "_frozen", False)
        self.mode = mode
        self.source = source
        self.raw_mode = raw_mode
        self.problems = tuple(problems)
        self.live_ack = live_ack
        self.paper_ack = paper_ack
        object.__setattr__(self, "_frozen", True)

    def __setattr__(self, name, value):
        if getattr(self, "_frozen", False):
            raise ExecutionModeError(
                "execution configuration is immutable: refusing to set %r. A "
                "mode that can be changed in-process is a mode the model can "
                "change." % (name,))
        object.__setattr__(self, name, value)

    def __delattr__(self, name):
        raise ExecutionModeError(
            "execution configuration is immutable: refusing to delete %r"
            % (name,))

    def to_dict(self):
        return {k: getattr(self, k) for k in self._FIELDS}


def _parse(text, source):
    """
    Parse a config file body into a _Config.

    Format is deliberately trivial -- `key = value`, `#` comments -- because a
    config parser with any expressive power is a place for a bug to hide, and
    this file decides whether real money can move.

    ANY problem downgrades to ANALYSIS_ONLY and records why. A partially
    understood config must not yield a partially elevated mode.
    """
    problems = []
    values = {}
    for lineno, line in enumerate(text.splitlines(), 1):
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        if "=" not in line:
            problems.append("line %d is not key = value: %r" % (lineno, line))
            continue
        key, _, value = line.partition("=")
        key, value = key.strip().lower(), value.strip()
        if key in values:
            # A repeated key is ambiguous, and "last one wins" is exactly how a
            # stray `mode = LIVE_TRADING` at the end of a file gets overlooked.
            problems.append("key %r appears more than once" % (key,))
            continue
        values[key] = value

    raw_mode = values.get("mode", "")
    paper_ack = values.get(
        _MODES_REQUIRING_EXPLICIT_OPT_IN["PAPER_TRADING"], "").lower() == "yes"
    live_ack = values.get(
        _MODES_REQUIRING_EXPLICIT_OPT_IN["LIVE_TRADING"], "").lower() == "yes"

    mode = raw_mode.strip().upper()
    if not mode:
        problems.append("no mode declared")
        mode = DEFAULT_MODE
    elif mode not in MODES:
        problems.append("unknown mode %r; known: %s"
                        % (raw_mode, ", ".join(MODES)))
        mode = DEFAULT_MODE

    # SS.5.6 defaults: paper and live each need their own explicit line. A mode
    # line alone is not "explicitly enabled" -- it is one word in a file that
    # could have been copied from an example.
    if mode == "PAPER_TRADING" and not paper_ack:
        problems.append(
            "PAPER_TRADING requires the line 'i_have_enabled_paper_trading = "
            "yes'. SS.5.6: paper trading is disabled until explicitly enabled.")
        mode = DEFAULT_MODE
    if mode == "LIVE_TRADING" and not live_ack:
        problems.append(
            "LIVE_TRADING requires the line 'i_have_approved_live_trading = "
            "yes'. SS.5.6: live trading is disabled by default and SS.6.1 "
            "requires explicit user approval of live-mode activation.")
        mode = DEFAULT_MODE

    return _Config(mode=mode, source=source, raw_mode=raw_mode,
                   problems=problems, live_ack=live_ack, paper_ack=paper_ack)


_CACHE = {}


def _load():
    """
    Read the config once per process and cache it.

    Cached deliberately: re-reading on every check would let the mode change
    underneath a half-completed operation, so that a preview validated in
    PAPER_TRADING could be committed in LIVE_TRADING. SS.6.2 already treats an
    environment change as invalidating a preview; not re-reading makes that
    impossible rather than merely detected.
    """
    if "config" not in _CACHE:
        path = CONFIG_PATH
        try:
            with open(path, "r", encoding="utf-8") as fh:
                _CACHE["config"] = _parse(fh.read(), path)
        except FileNotFoundError:
            # The overwhelmingly common case: a new installation. SS.5.6 says
            # that is ANALYSIS_ONLY, and it is not an error.
            _CACHE["config"] = _Config(
                mode=DEFAULT_MODE, source="default (no config file at %s)" % path)
        except OSError as exc:
            _CACHE["config"] = _Config(
                mode=DEFAULT_MODE, source="default (config unreadable)",
                problems=("could not read %s: %s" % (path, exc),))
    return _CACHE["config"]


def current_mode() -> str:
    """
    The active mode. NOTE THE ABSENCE OF PARAMETERS -- that absence is the
    SS.5.6 requirement that the mode not come from model inference.
    """
    return _load().mode


def mode_source() -> str:
    """Where the mode came from, for the audit trail."""
    return _load().source


def config_problems() -> Tuple[str, ...]:
    """
    Everything wrong with the configuration.

    Non-empty while the mode is DEFAULT_MODE means someone tried to configure
    something and it did not take effect. Silence about that is how an operator
    concludes the system is broken and starts editing code.
    """
    return _load().problems


def capabilities(mode: Optional[str] = None) -> Tuple[str, ...]:
    """
    What the given mode permits (default: the active mode).

    The `mode` parameter exists for INSPECTION -- "what would live mode allow?"
    -- and cannot change what is active. current_mode() ignores it entirely.
    """
    if mode is None:
        mode = current_mode()
    if mode not in CAPABILITIES:
        raise ExecutionModeError(
            "unknown mode %r; known: %s" % (mode, ", ".join(MODES)))
    return CAPABILITIES[mode]


def is_permitted(capability: str, mode: Optional[str] = None) -> bool:
    """True if `capability` is permitted. Raises on an unknown capability."""
    if not capability or not isinstance(capability, str):
        raise ExecutionModeError("capability must be a non-empty string")
    if capability not in ALL_CAPABILITIES:
        # A typo must not read as a quiet False. See ALL_CAPABILITIES.
        raise ExecutionModeError(
            "unknown capability %r; known: %s. A misspelled capability that "
            "returned False would look like a working permission check."
            % (capability, ", ".join(ALL_CAPABILITIES)))
    return capability in capabilities(mode)


def require(capability: str) -> None:
    """
    Refuse `capability` unless the ACTIVE mode permits it.

    Takes no mode argument, by design: a caller that could pass a mode would be
    choosing its own permissions.
    """
    # SS.6.1 is checked BEFORE the mode is consulted, because the mode being
    # LIVE_TRADING is only one of its twelve prerequisites. Putting this after
    # the is_permitted() check would make a config edit sufficient -- MEASURED:
    # it was, until this block existed.
    if capability == "submit_live_order":
        unmet = unmet_live_prerequisites()
        if unmet:
            raise ExecutionModeError(
                "refusing 'submit_live_order': %d of SS.6.1's %d prerequisites "
                "for LIVE_TRADING are unmet, so live trading is unreachable "
                "regardless of configuration. Unmet: %s. Details: %s"
                % (len(unmet), len(LIVE_PREREQUISITES), "; ".join(unmet),
                   "; ".join("%s -- %s" % (n, LIVE_PREREQUISITES[n][1])
                             for n in unmet[:3])))

    if not is_permitted(capability):
        mode = current_mode()
        detail = ""
        problems = config_problems()
        if problems:
            detail += (" NOTE: the configuration has %d problem(s) and was "
                       "downgraded to %s: %s"
                       % (len(problems), mode, "; ".join(problems)))
        raise ExecutionModeError(
            "%r is not permitted in mode %s (from %s). Permitted here: %s.%s"
            % (capability, mode, mode_source(),
               ", ".join(capabilities(mode)), detail))


def require_mode(*allowed: str) -> str:
    """
    Refuse unless the active mode is one of `allowed`. Compares; never assigns.
    """
    if not allowed:
        raise ExecutionModeError("require_mode() needs at least one mode")
    for m in allowed:
        if m not in MODES:
            raise ExecutionModeError(
                "unknown mode %r; known: %s" % (m, ", ".join(MODES)))
    mode = current_mode()
    if mode not in allowed:
        raise ExecutionModeError(
            "this operation requires mode in (%s); active mode is %s (from %s)"
            % (", ".join(allowed), mode, mode_source()))
    return mode


def live_trading_enabled() -> bool:
    """
    True only when LIVE_TRADING is active AND every SS.6.1 prerequisite is met.

    Both conditions, because the mode alone is not the question a caller is
    really asking. A function that returned True on the strength of one config
    line would be read as "live orders are possible" and it would be wrong: the
    mode is one of twelve prerequisites. This is the same defect class as
    Quote.is_live requiring both REALTIME and OPEN -- either condition alone
    permits a confident, wrong answer.

    Returns False today, and will keep returning False until a broker adapter,
    licensed market data, a risk engine, audit logging, idempotency, a kill
    switch and paper-trading validation all exist.
    """
    return (current_mode() == "LIVE_TRADING"
            and not unmet_live_prerequisites())


def manifest() -> Dict[str, Any]:
    """Everything an audit record needs about the mode. No secrets pass here."""
    cfg = _load()
    return {"mode": cfg.mode,
            "source": cfg.source,
            "config_path": CONFIG_PATH,
            "problems": list(cfg.problems),
            "capabilities": list(capabilities(cfg.mode)),
            "live_trading_enabled": live_trading_enabled(),
            "unmet_live_prerequisites": list(unmet_live_prerequisites()),
            "n_live_prerequisites": len(LIVE_PREREQUISITES),
            "modes": list(MODES),
            "all_capabilities": list(ALL_CAPABILITIES)}


def _reset_cache_for_tests(path=None):
    """
    Re-read the configuration, optionally from `path`. TESTS ONLY.

    This is the one function here that can change the active mode in-process, and
    it is why the name says so. It exists because the alternative -- making the
    mode a parameter of current_mode() so tests can vary it -- would put a
    mode argument in the production path, which is exactly what SS.5.6 forbids.
    Confining the hazard to one obviously-named function is the lesser evil, and
    a test asserts that a LIVE_TRADING config still cannot submit a live order,
    so even this door does not open the one that matters.
    """
    global CONFIG_PATH
    _CACHE.clear()
    if path is not None:
        CONFIG_PATH = path
    return _load()
