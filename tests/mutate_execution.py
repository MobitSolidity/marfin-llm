"""
Mutation battery for the SS.5.6 / SS.6.1 execution layer.

This is the battery that matters most in the project so far. Every other module
can, at worst, produce a wrong number that a human reads. This one decides
whether an order can be submitted with real money, so a defect here is not an
analytical error but a financial one -- and the module is almost entirely made of
refusals, which are exactly the code that a passing test suite is worst at
verifying. A refusal that stops refusing looks like nothing at all.

The value of this battery is not hypothetical. Before it existed, mode.py stated
in a docstring that "live trading cannot be enabled even by editing the config",
and first execution disproved that outright: a two-line config file reached
require("submit_live_order") successfully. The prose was decoration. These
mutations exist so the replacement guard cannot quietly become decoration too.

ORACLE: test_execution.py alone -- unlike the market battery, which needs a
separate adversarial probe, this suite already contains both the refusals and the
positive controls (ANALYSIS_ONLY permits calculate; PAPER_TRADING permits a paper
order; a valid config IS honoured). A mutation that makes the layer refuse
everything dies on the positive controls; one that makes it permit everything dies
on the refusals.

Stdlib only.
"""

import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC_ROOT = os.path.join(ROOT, "src")

ORACLES = ("test_execution.py",)


def module_path(module):
    return os.path.join(SRC_ROOT, module)


# Empty, and it took a wrong entry to get here. "live_trading_enabled ignores the
# mode" was first recorded as a TEMPORARY equivalent: MEASURED, 10 of 12 SS.6.1
# prerequisites are unmet, so `not unmet_live_prerequisites()` is False in every
# mode and no INPUT can distinguish the mutant from the original. The note was
# accurate about behaviour and still the wrong conclusion -- the equivalence would
# have dissolved silently the moment the prerequisites were built, which is
# exactly when the mode check starts protecting real money. Asserting the
# conjunction's structure instead killed the mutant outright, and this battery's
# own RECHECK line is what reported that the note had become false.
EQUIVALENT = {}

# (module, description, find, replace)
MUTATIONS = [
    # --- SS.6.1: the prerequisite table is the live-trading wall -------------
    ("execution/mode.py", "SS.6.1 prerequisites are no longer checked at all",
     "    if capability == \"submit_live_order\":\n        unmet = unmet_live_prerequisites()\n        if unmet:",
     "    if capability == \"submit_live_order\":\n        unmet = unmet_live_prerequisites()\n        if False:"),
    ("execution/mode.py", "unmet prerequisites are reported as satisfied",
     "    return tuple(name for name, (ok, _) in LIVE_PREREQUISITES.items() if not ok)",
     "    return ()"),
    ("execution/mode.py", "licensed market data is declared satisfied",
     '    "independent licensed market data": (\n        False,',
     '    "independent licensed market data": (\n        True,'),
    ("execution/mode.py", "a verified broker adapter is declared satisfied",
     '    "verified broker adapter": (\n        False,',
     '    "verified broker adapter": (\n        True,'),
    ("execution/mode.py", "the kill switch is declared satisfied",
     '    "emergency kill switch": (False, "not built"),',
     '    "emergency kill switch": (True, "not built"),'),
    ("execution/mode.py", "live_trading_enabled ignores the prerequisites",
     '    return (current_mode() == "LIVE_TRADING"\n'
     '            and not unmet_live_prerequisites())',
     '    return current_mode() == "LIVE_TRADING"'),
    ("execution/mode.py", "live_trading_enabled ignores the mode",
     '    return (current_mode() == "LIVE_TRADING"\n'
     '            and not unmet_live_prerequisites())',
     '    return not unmet_live_prerequisites()'),

    # --- SS.5.6 defaults: paper and live each need explicit opt-in -----------
    ("execution/mode.py", "PAPER_TRADING no longer needs its acknowledgement",
     '    if mode == "PAPER_TRADING" and not paper_ack:',
     "    if False:"),
    ("execution/mode.py", "LIVE_TRADING no longer needs its acknowledgement",
     '    if mode == "LIVE_TRADING" and not live_ack:',
     "    if False:"),
    ("execution/mode.py", "the default mode becomes LIVE_TRADING",
     'DEFAULT_MODE = "ANALYSIS_ONLY"',
     'DEFAULT_MODE = "LIVE_TRADING"'),
    ("execution/mode.py", "the default mode becomes PAPER_TRADING",
     'DEFAULT_MODE = "ANALYSIS_ONLY"',
     'DEFAULT_MODE = "PAPER_TRADING"'),
    # A truthy check instead of an equality check: any non-empty value for the
    # acknowledgement (including "no") would then enable live trading.
    ("execution/mode.py", "any non-empty value acknowledges live trading",
     '    live_ack = values.get(\n'
     '        _MODES_REQUIRING_EXPLICIT_OPT_IN["LIVE_TRADING"], "").lower() == "yes"',
     '    live_ack = bool(values.get(\n'
     '        _MODES_REQUIRING_EXPLICIT_OPT_IN["LIVE_TRADING"], ""))'),

    # --- config parsing: every failure must downgrade ------------------------
    ("execution/mode.py", "an unknown mode name is accepted as-is",
     "    elif mode not in MODES:",
     "    elif False:"),
    ("execution/mode.py", "an absent mode is not recorded as a problem",
     '        problems.append("no mode declared")',
     "        pass"),
    ("execution/mode.py", "a duplicate key lets the last line win",
     "        if key in values:",
     "        if False:"),
    ("execution/mode.py", "a malformed line is silently ignored",
     '            problems.append("line %d is not key = value: %r" % (lineno, line))',
     "            pass"),
    # An unreadable config must not crash: a crash invites a hardcoded mode.
    ("execution/mode.py", "an unreadable config raises instead of downgrading",
     "        except OSError as exc:",
     "        except _NeverRaised as exc:"),

    # --- the mode cannot come from model inference ---------------------------
    ("execution/mode.py", "require() gains a mode override parameter",
     "def require(capability: str) -> None:",
     "def require(capability: str, mode=None) -> None:"),
    ("execution/mode.py", "current_mode() accepts a caller-supplied mode",
     "def current_mode() -> str:",
     "def current_mode(mode=None) -> str:"),
    ("execution/mode.py", "a misspelled capability reads as a quiet False",
     "    if capability not in ALL_CAPABILITIES:",
     "    if False:"),
    ("execution/mode.py", "an empty capability is accepted",
     "    if not capability or not isinstance(capability, str):",
     "    if False:"),
    ("execution/mode.py", "require_mode accepts an unknown mode name",
     "        if m not in MODES:",
     "        if False:"),
    ("execution/mode.py", "require_mode with no arguments permits everything",
     "    if not allowed:",
     "    if False:"),
    ("execution/mode.py", "require_mode stops comparing the active mode",
     "    if mode not in allowed:",
     "    if False:"),
    ("execution/mode.py", "the config becomes mutable in-process",
     '    def __setattr__(self, name, value):\n'
     '        if getattr(self, "_frozen", False):\n'
     '            raise ExecutionModeError(\n'
     '                "execution configuration is immutable: refusing to set %r. A "',
     '    def __setattr__(self, name, value):\n'
     '        if False:\n'
     '            raise ExecutionModeError(\n'
     '                "execution configuration is immutable: refusing to set %r. A "'),
    ("execution/mode.py", "config fields become deletable",
     '    def __delattr__(self, name):\n'
     '        raise ExecutionModeError(\n'
     '            "execution configuration is immutable: refusing to delete %r"\n'
     '            % (name,))',
     '    def __delattr__(self, name):\n'
     '        object.__delattr__(self, name)'),

    # --- capability table: sets per mode, not a scale ------------------------
    ("execution/mode.py", "ANALYSIS_ONLY gains the live-order capability",
     '    "ANALYSIS_ONLY": ("read_market_data", "read_documents", "calculate",\n'
     '                      "preview_order"),',
     '    "ANALYSIS_ONLY": ("read_market_data", "read_documents", "calculate",\n'
     '                      "preview_order", "submit_live_order"),'),
    ("execution/mode.py", "BACKTEST gains broker access",
     '    "BACKTEST": ("read_market_data", "read_documents", "calculate",\n'
     '                 "preview_order", "read_history", "simulate_fill"),',
     '    "BACKTEST": ("read_market_data", "read_documents", "calculate",\n'
     '                 "preview_order", "read_history", "simulate_fill",\n'
     '                 "read_broker_account", "submit_paper_order"),'),
    ("execution/mode.py", "PAPER_TRADING gains the live-order capability",
     '                      "read_broker_account", "submit_paper_order"),\n'
     '    # LIVE_TRADING adds exactly one capability over PAPER_TRADING.',
     '                      "read_broker_account", "submit_paper_order",\n'
     '                      "submit_live_order"),\n'
     '    # LIVE_TRADING adds exactly one capability over PAPER_TRADING.'),
    ("execution/mode.py", "ANALYSIS_ONLY loses the ability to calculate",
     '    "ANALYSIS_ONLY": ("read_market_data", "read_documents", "calculate",',
     '    "ANALYSIS_ONLY": ("read_market_data", "read_documents",'),
    ("execution/mode.py", "capabilities() accepts an unknown mode",
     "    if mode not in CAPABILITIES:",
     "    if False:"),
    ("execution/mode.py", "is_permitted stops consulting the capability set",
     "    return capability in capabilities(mode)",
     "    return True"),

    # --- broker catalog: documented is not verified --------------------------
    ("execution/brokers.py", "an adapter can be enabled while merely DOCUMENTED",
     '        if enabled and verification != "VERIFIED":',
     "        if False:"),
    ("execution/brokers.py", "assert_adapter_usable stops checking verification",
     '    if a.verification != "VERIFIED":',
     "    if False:"),
    ("execution/brokers.py", "a registered-but-disabled adapter is usable",
     "    if not a.enabled:",
     "    if False:"),
    ("execution/brokers.py", "an adapter may be used in an environment it lacks",
     "    if environment not in a.environments:",
     "    if False:"),
    ("execution/brokers.py", "the environment argument stops being validated",
     "    if environment not in ENVIRONMENTS:",
     "    if False:"),
    ("execution/brokers.py", "the mode gate is skipped for broker use",
     '    require("submit_live_order" if environment == "LIVE"\n'
     '            else "submit_paper_order")',
     "    pass"),
    ("execution/brokers.py", "a LIVE environment is gated as if it were paper",
     '    require("submit_live_order" if environment == "LIVE"\n'
     '            else "submit_paper_order")',
     '    require("submit_paper_order")'),
    ("execution/brokers.py", "alpaca is marked VERIFIED without a round-trip",
     '    key="alpaca",\n'
     '    name="Alpaca Markets",\n'
     '    docs_url="https://docs.alpaca.markets/",\n'
     '    transport="REST + optional streaming",\n'
     '    verification="DOCUMENTED",',
     '    key="alpaca",\n'
     '    name="Alpaca Markets",\n'
     '    docs_url="https://docs.alpaca.markets/",\n'
     '    transport="REST + optional streaming",\n'
     '    verification="VERIFIED",'),
    ("execution/brokers.py", "an adapter need not record its unverifiable facts",
     "        if not unverifiable_without_credentials:",
     "        if False:"),
    ("execution/brokers.py", "an unknown verification level is accepted",
     "        if verification not in VERIFICATION_LEVELS:",
     "        if False:"),
    ("execution/brokers.py", "an unknown environment is accepted",
     "            if env not in ENVIRONMENTS:",
     "            if False:"),
    ("execution/brokers.py", "adapters become mutable after construction",
     '    def __setattr__(self, name, value):\n'
     '        if getattr(self, "_frozen", False):\n'
     '            raise BrokerError(\n'
     '                "broker adapters are immutable: refusing to set %r on %r. One "',
     '    def __setattr__(self, name, value):\n'
     '        if False:\n'
     '            raise BrokerError(\n'
     '                "broker adapters are immutable: refusing to set %r on %r. One "'),
    ("execution/brokers.py", "adapter fields become deletable",
     '    def __delattr__(self, name):\n'
     '        raise BrokerError("broker adapters are immutable: refusing to delete %r "\n'
     '                          "on %r" % (name, self.key))',
     '    def __delattr__(self, name):\n'
     '        object.__delattr__(self, name)'),
    ("execution/brokers.py", "the adapter registry is exposed as a mutable dict",
     "ADAPTERS: Mapping[str, BrokerAdapter] = MappingProxyType(_ADAPTERS)",
     "ADAPTERS: Mapping[str, BrokerAdapter] = _ADAPTERS"),
    ("execution/brokers.py", "register_adapter accepts any object",
     "    if not isinstance(a, BrokerAdapter):",
     "    if False:"),
    ("execution/brokers.py", "a reviewed adapter entry can be overwritten",
     "    if a.key in _ADAPTERS:",
     "    if False:"),
    ("execution/brokers.py", "submit_order silently returns instead of refusing",
     '    raise NotImplementedError(\n'
     '        "order submission is not implemented. SS.6.2 requires a two-phase "',
     '    return None\n'
     '    raise NotImplementedError(\n'
     '        "order submission is not implemented. SS.6.2 requires a two-phase "'),
    ("execution/brokers.py", "read_account silently returns instead of refusing",
     '    raise NotImplementedError(\n'
     '        "broker account reads are not implemented: no adapter has been "',
     '    return {}\n'
     '    raise NotImplementedError(\n'
     '        "broker account reads are not implemented: no adapter has been "'),
    ("execution/brokers.py", "TradingView gains execution environments",
     '    name="TradingView (NOT a broker; listed to close the door)",\n'
     '    docs_url="https://www.tradingview.com/broker-api-docs/",\n'
     '    transport="n/a",\n'
     '    verification="DOCUMENTED",\n'
     '    environments=(),',
     '    name="TradingView (NOT a broker; listed to close the door)",\n'
     '    docs_url="https://www.tradingview.com/broker-api-docs/",\n'
     '    transport="n/a",\n'
     '    verification="DOCUMENTED",\n'
     '    environments=("PAPER", "LIVE"),'),
    ("execution/brokers.py", "enabled_adapters reports every adapter as enabled",
     "    return [a for a in ADAPTERS.values() if a.enabled]",
     "    return list(ADAPTERS.values())"),

    # --- SS.5.6 separation: the import graph --------------------------------
    # If execution/ imports the RAG layer, the separation the spec requires is
    # gone. The suite parses imports with ast, so this must die.
    ("execution/brokers.py", "execution imports the RAG document layer",
     "from execution.mode import ExecutionModeError, require",
     "from execution.mode import ExecutionModeError, require\n"
     "from rag.documents import TRUST_LEVELS"),
]


def run_oracle(name):
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = SRC_ROOT + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, os.path.join(HERE, name)],
        cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return proc.returncode == 0, proc.stdout.decode("utf-8", "replace")


def run_tests():
    for name in ORACLES:
        ok, out = run_oracle(name)
        if not ok:
            return False, "%s FAILED\n%s" % (name, out[-2000:])
    return True, ""


def main():
    for dirpath, dirnames, _ in os.walk(ROOT):
        for d in list(dirnames):
            if d == "__pycache__":
                shutil.rmtree(os.path.join(dirpath, d), ignore_errors=True)

    ok, out = run_tests()
    if not ok:
        print("ABORT: the oracle fails BEFORE any mutation is applied.")
        print(out[-3000:])
        return 1
    print("baseline: oracle passes (%s), %d mutations to apply\n"
          % (", ".join(ORACLES), len(MUTATIONS)))

    backup = tempfile.mkdtemp(prefix="exec_orig_")
    _backed_up = {}
    for module in sorted({m for (m, _, _, _) in MUTATIONS}):
        flat = module.replace("/", "__")
        shutil.copy2(module_path(module), os.path.join(backup, flat))
        _backed_up[flat] = module_path(module)

    killed = survived = skipped = equivalent = 0
    survivors, skips, unexpected_kills = [], [], []
    try:
        for i, (module, desc, find, repl) in enumerate(MUTATIONS, 1):
            path = module_path(module)
            with open(path, "r", encoding="utf-8") as fh:
                original = fh.read()
            if find not in original:
                skipped += 1
                skips.append("%s: %s" % (module, desc))
                print("  %2d. SKIP     %-58s (pattern absent)" % (i, desc[:58]))
                continue
            if original.count(find) > 1:
                skipped += 1
                skips.append("%s: %s (ambiguous)" % (module, desc))
                print("  %2d. SKIP     %-58s (ambiguous)" % (i, desc[:58]))
                continue
            mutated = original.replace(find, repl, 1)
            if mutated == original:
                # A no-op mutation is a bug in THIS file, not a finding. Written
                # one five times in this project; the check stays.
                skipped += 1
                skips.append("%s: %s (NO-OP)" % (module, desc))
                print("  %2d. SKIP     %-58s (NO-OP, fix the mutation)"
                      % (i, desc[:58]))
                continue
            try:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(mutated)
                passed, _ = run_tests()
                key = "%s: %s" % (module, desc)
                if passed and key in EQUIVALENT:
                    equivalent += 1
                    print("  %2d. equiv    %-58s (%s)"
                          % (i, desc[:58], EQUIVALENT[key][:40]))
                elif passed:
                    survived += 1
                    survivors.append(key)
                    print("  %2d. SURVIVED %-58s <-- NOT TESTED" % (i, desc[:58]))
                else:
                    killed += 1
                    if key in EQUIVALENT:
                        unexpected_kills.append(key)
                    print("  %2d. killed   %s" % (i, desc[:58]))
            finally:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(original)
    finally:
        for name, dest in _backed_up.items():
            shutil.copy2(os.path.join(backup, name), dest)
        shutil.rmtree(backup, ignore_errors=True)

    intact, _ = run_tests()
    print("\n" + "=" * 78)
    print("  seeded:     %d" % len(MUTATIONS))
    print("  killed:     %d" % killed)
    print("  equivalent: %d (documented redundant guards)" % equivalent)
    print("  survived:   %d" % survived)
    print("  skipped:    %d" % skipped)
    print("  source restored and oracle green: %s" % intact)
    for s in survivors:
        print("  SURVIVOR: %s" % s)
    for s in skips:
        print("  SKIPPED:  %s" % s)
    for s in unexpected_kills:
        print("  RECHECK:  %s was listed as equivalent but was KILLED" % s)
    print("=" * 78)
    return 0 if (survived == 0 and skipped == 0 and not unexpected_kills
                 and intact) else 1


if __name__ == "__main__":
    sys.exit(main())
