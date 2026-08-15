"""
Mutation battery for the SS.8.4 / SS.8.5 / SS.8.6 broker tool surface.

WHY THIS BATTERY IS NOT OPTIONAL
This module is almost entirely refusals, and a refusal that stops refusing looks
like nothing at all -- no exception, no output, no failing assertion unless a
test was written to notice the ABSENCE. test_broker_tools.py reports 282 passing
assertions and probe_broker_tools.py reports 62 refused attempts, and neither
number is evidence on its own. This file is what turns them into evidence: it
breaks each guard on purpose and requires the oracles to notice.

THE FINDING THAT PROVES THE POINT
Before this battery existed, the verdict rule in pre_trade_risk_check was an
inline expression, and seeding the exact bug the module exists to prevent --
treating an UNKNOWN check as good enough -- did NOT fail a single one of the 54
probe attempts then in place. MEASURED: kill_switch_status is unconditionally
FAIL, so a failure COUNT is never zero, so the mutant and the real rule agreed in
every state a caller could construct. A second guard was answering for the one
under test. The rule was extracted into verdict_for() so the discriminating state
(fifteen PASSes and one UNKNOWN) became reachable, and the same mutation now
dies. That is the class of defect this file exists to find, and it was found by
running a mutation, not by reading the code.

ORACLES: both files. They are complementary and neither is sufficient.
  - test_broker_tools.py asserts on refusal CONTENT, so a mutation that lets one
    guard's refusal be answered by a different guard still dies.
  - probe_broker_tools.py asserts that no adversarial call sequence gets through,
    so a mutation opening a path no unit test happens to walk still dies.
A mutation that makes the surface refuse EVERYTHING dies on the positive controls
present in both: a well-formed limit order validates, a full-PASS result set
really does return PASS, and a paper read really does reach the transport
refusal rather than an earlier gate.

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

ORACLES = ("test_broker_tools.py", "probe_broker_tools.py")


def module_path(module):
    return os.path.join(SRC_ROOT, module)


# Empty, and it should stay empty. Every entry here would be a claim that NO
# input can distinguish the mutant, and this project has already recorded one
# such claim that was true when written and false three commits later.
EQUIVALENT = {}

M = "execution/broker_tools.py"

# (module, description, find, replace)
MUTATIONS = [

    # -- the constant tables: the spec's vocabulary, not a broker's ----------
    (M, "SIDES conflates sell with sell_short",
     'SIDES: Tuple[str, ...] = ("buy", "sell", "sell_short", "buy_to_cover")',
     'SIDES: Tuple[str, ...] = ("buy", "sell", "buy_to_cover")'),

    (M, "CHECK_STATUS loses UNKNOWN, collapsing to a boolean",
     'CHECK_STATUS: Tuple[str, ...] = ("PASS", "FAIL", "UNKNOWN")',
     'CHECK_STATUS: Tuple[str, ...] = ("PASS", "FAIL")'),

    (M, "RISK_CHECKS drops the kill switch, leaving fifteen",
     '    "short_sale_restrictions", "user_limits", "kill_switch_status",',
     '    "short_sale_restrictions", "user_limits",'),

    (M, "MANDATORY_CONTROLS becomes editable at runtime",
     "MANDATORY_CONTROLS: Mapping[str, Tuple[bool, str]] = MappingProxyType({",
     "MANDATORY_CONTROLS: Mapping[str, Tuple[bool, str]] = dict({"),

    (M, "ENVIRONMENT_INPUT becomes editable at runtime",
     "ENVIRONMENT_INPUT: Mapping[str, str] = MappingProxyType({",
     "ENVIRONMENT_INPUT: Mapping[str, str] = dict({"),

    (M, "the kill switch is declared PRESENT",
     '    "kill-switch status": (False, "NO KILL SWITCH EXISTS -- a known absence"),',
     '    "kill-switch status": (True, "NO KILL SWITCH EXISTS -- a known absence"),'),

    (M, "a control that IS met is declared absent, drifting the count to 19",
     '    "paper/live environment": (\n'
     '        True, "execution.brokers.ENVIRONMENTS, required and never defaulted"),',
     '    "paper/live environment": (\n'
     '        False, "execution.brokers.ENVIRONMENTS, required and never defaulted"),'),

    (M, "unmet_controls() reports the MET controls instead",
     "    return tuple(n for n, (ok, _) in MANDATORY_CONTROLS.items() if not ok)",
     "    return tuple(n for n, (ok, _) in MANDATORY_CONTROLS.items() if ok)"),

    # -- environment: SS.6.3 forbids a default ------------------------------
    (M, "the environment acquires a default: the no-default guard is gone",
     '    if environment is None or environment == "":',
     "    if False:"),

    (M, "the environment type check is removed",
     "    if not isinstance(environment, str):",
     "    if False:"),

    (M, "the environment table case-folds 'Paper' and 'LiVe'",
     '    "paper": "PAPER", "PAPER": "PAPER", "live": "LIVE", "LIVE": "LIVE",',
     '    "paper": "PAPER", "PAPER": "PAPER", "live": "LIVE", "LIVE": "LIVE",\n'
     '    "Paper": "PAPER", "LiVe": "LIVE",'),

    # -- account identity ---------------------------------------------------
    (M, "an account_id with surrounding whitespace is accepted",
     "    if account_id != account_id.strip():",
     "    if False:"),

    (M, "an empty account_id is accepted",
     "    if not isinstance(account_id, str) or not account_id.strip():",
     "    if not isinstance(account_id, str):"),

    # -- numeric validation -------------------------------------------------
    (M, "a bool reaches arithmetic as 1 or 0",
     "    if isinstance(value, bool):",
     "    if False:"),

    (M, "NaN passes validation: every comparison against it is False",
     "    if f != f:",
     "    if False:"),

    (M, "infinity passes validation",
     '    if f in (float("inf"), float("-inf")):',
     "    if False:"),

    (M, "_positive_number accepts exactly zero",
     "    if f <= 0:",
     "    if f < 0:"),

    # -- timestamps ---------------------------------------------------------
    (M, "_iso_utc accepts a naive datetime",
     "    if when.tzinfo is None:",
     "    if False:"),

    (M, "_iso_utc RELABELS the zone instead of converting the instant",
     "    return when.astimezone(datetime.timezone.utc).isoformat()",
     "    return when.replace(tzinfo=datetime.timezone.utc).isoformat()"),

    # -- SS.8.5 position_size -----------------------------------------------
    (M, "position_size accepts stop=0, the defect this suite already caught",
     "    if stop_p == 0:",
     "    if False:"),

    (M, "the negative-stop guard swallows zero, masking the ambiguity refusal",
     "    if stop_p < 0:",
     "    if stop_p <= 0:"),

    (M, "a risk_budget larger than the account is silently capped",
     "    if budget > equity:",
     "    if False:"),

    (M, "stop == entry is no longer refused as unbounded",
     "    if price_risk == 0:",
     "    if False:"),

    (M, "the price risk loses its abs(), so a short sizes negatively",
     "    price_risk = abs(entry_p - stop_p)",
     "    price_risk = entry_p - stop_p"),

    (M, "costs are SUBTRACTED, enlarging the position instead of shrinking it",
     "    loss_per_unit = price_risk * mult + fee + slip",
     "    loss_per_unit = price_risk * mult - fee - slip"),

    (M, "the contract multiplier is dropped from the per-unit loss",
     "    loss_per_unit = price_risk * mult + fee + slip",
     "    loss_per_unit = price_risk + fee + slip"),

    (M, "negative fees and slippage are accepted",
     "    if fee < 0 or slip < 0:",
     "    if False:"),

    (M, "an empty currency is accepted",
     "    if not isinstance(currency, str) or not currency.strip():",
     "    if False:"),

    (M, "the quantity is silently rounded to a whole lot",
     "    quantity = budget / loss_per_unit",
     "    quantity = float(round(budget / loss_per_unit))"),

    (M, "position_size labels its output MEASURED instead of COMPUTED",
     '        "status": "COMPUTED",',
     '        "status": "MEASURED",'),

    # -- SS.8.5 verdict_for: the single most important rule in the module ---
    (M, "THE RULE: the verdict counts FAILs, so an UNKNOWN check passes",
     '    return "PASS" if all(e["status"] == "PASS" for e in results.values()) \\\n'
     '        else "REFUSE"',
     '    return "REFUSE" if any(e["status"] == "FAIL" for e in results.values()) \\\n'
     '        else "PASS"'),

    (M, "verdict_for reads an empty result set as 'nothing failed'",
     "    if not results:\n"
     "        raise BrokerToolError(",
     "    if False:\n"
     "        raise BrokerToolError("),

    # Disambiguated by the refusal MESSAGE: `missing = [...]` followed by
    # `if missing:` occurs twice -- here and in pre_trade_risk_check's internal
    # completeness guard. MEASURED count 2, which the runner would have reported
    # as an ambiguous SKIP, and a SKIP is worse than a survivor because it looks
    # like a line in a passing report.
    (M, "verdict_for judges a PARTIAL result set",
     "    if missing:\n"
     "        raise BrokerToolError(\n"
     '            "refusing to judge a partial result set:',
     "    if False:\n"
     "        raise BrokerToolError(\n"
     '            "refusing to judge a partial result set:'),

    (M, "verdict_for accepts an unrecognised status",
     "        status = entry[\"status\"]\n"
     "        if status not in CHECK_STATUS:",
     "        status = entry[\"status\"]\n"
     "        if False:"),

    # -- SS.8.5 pre_trade_risk_check ----------------------------------------
    (M, "the kill switch becomes UNKNOWN, as if a credential might reveal one",
     '    record("kill_switch_status", "FAIL",',
     '    record("kill_switch_status", "UNKNOWN",'),

    (M, "a check is silently not run, leaving fifteen of sixteen",
     '    record("user_limits", "UNKNOWN",\n'
     '           "no user limits are configured; an absent limit is not a satisfied "\n'
     '           "one")',
     "    pass"),

    (M, "record() accepts a status outside PASS/FAIL/UNKNOWN",
     "        if status not in CHECK_STATUS:\n"
     '            raise BrokerToolError("unknown check status %r" % (status,))',
     "        if False:\n"
     '            raise BrokerToolError("unknown check status %r" % (status,))'),

    (M, "a computable notional is reported PASS despite there being no limit",
     '            record("notional", "UNKNOWN",\n'
     '                   "notional computes to %.4f',
     '            record("notional", "PASS",\n'
     '                   "notional computes to %.4f'),

    (M, "the price-deviation tolerance widens from 5% to 6%",
     "        if dev > 0.05:",
     "        if dev > 0.06:"),

    (M, "the price-deviation boundary becomes exclusive: 5.00% now FAILs",
     "        if dev > 0.05:",
     "        if dev >= 0.05:"),

    (M, "a FUTURE-dated quote counts as very fresh instead of failing",
     "        if age < 0:",
     "        if False:"),

    (M, "the quote-age boundary shifts: exactly 60s now FAILs",
     "        elif age > max_quote_age_seconds:",
     "        elif age >= max_quote_age_seconds:"),

    (M, "a naive quote_timestamp is assumed to be UTC",
     "        if quote_timestamp.tzinfo is None:",
     "        if False:"),

    (M, "price_deviation is PASS when no reference price was supplied",
     '        record("price_deviation", "UNKNOWN",\n'
     '               "needs both an order price and a reference price;',
     '        record("price_deviation", "PASS",\n'
     '               "needs both an order price and a reference price;'),

    (M, "quote_freshness is PASS when no quote was supplied",
     '        record("quote_freshness", "UNKNOWN",\n'
     '               "no quote timestamp supplied.',
     '        record("quote_freshness", "PASS",\n'
     '               "no quote timestamp supplied.'),

    # -- SS.6.2 step 6: order field validation ------------------------------
    (M, "the side vocabulary is no longer checked",
     "    if side not in SIDES:",
     "    if False:"),

    (M, "the order_type vocabulary is no longer checked",
     "    if order_type not in ORDER_TYPES:",
     "    if False:"),

    (M, "the time_in_force vocabulary is no longer checked",
     "    if time_in_force not in TIME_IN_FORCE:",
     "    if False:"),

    (M, "extended_hours accepts a truthy string like 'false'",
     "    if not isinstance(extended_hours, bool):",
     "    if False:"),

    (M, "an empty instrument_id is accepted",
     "    if not isinstance(instrument_id, str) or not instrument_id.strip():",
     "    if False:"),

    (M, "a whitespace client_order_id is accepted: duplicate detection dies",
     "    if not isinstance(client_order_id, str) or not client_order_id.strip():",
     "    if False:"),

    (M, "trailing_stop is silently accepted with no offset",
     '    if order_type == "trailing_stop":',
     "    if False:"),

    (M, "a REQUIRED price field may be omitted",
     "        if supplied[field] is None:",
     "        if False:"),

    (M, "a FORBIDDEN price field is silently ignored rather than refused",
     "        if supplied[field] is not None:",
     "        if False:"),

    (M, "the BUY-side stop_limit wrong-side guard is removed",
     "        if buying and lp < sp:",
     "        if False:"),

    (M, "the SELL-side stop_limit wrong-side guard is removed",
     "        if not buying and lp > sp:",
     "        if False:"),

    (M, "buy_to_cover is not recognised as a buying side",
     '        buying = side in ("buy", "buy_to_cover")',
     '        buying = side == "buy"'),

    (M, "a stop_limit with limit EQUAL to stop is refused: over-broad guard",
     "        if buying and lp < sp:",
     "        if buying and lp <= sp:"),

    # -- SS.8.6 preview_order -----------------------------------------------
    (M, "preview_order asks for the WRONG capability",
     '    require("preview_order")',
     '    require("submit_live_order")'),

    (M, "the preview declares itself COMMITTABLE",
     '        "committable": False,',
     '        "committable": True,'),

    (M, "the preview issues a confirmation token",
     '        "confirmation_challenge": None,',
     '        "confirmation_challenge": "cnf_" + preview_id[4:12],'),

    (M, "the preview expiry stretches from 60 seconds to 600",
     "datetime.timedelta(seconds=60)",
     "datetime.timedelta(seconds=600)"),

    (M, "the preview id stops being a hash of the order's CONTENT",
     '    preview_id = "prv_" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]',
     '    preview_id = "prv_" + hashlib.sha256(account_id.encode("utf-8")).hexdigest()[:32]'),

    (M, "the preview id ignores the environment, so paper and live collide",
     '        account_id, env, fields["instrument_id"], fields["side"],',
     '        account_id, fields["instrument_id"], fields["side"],'),

    (M, "preview_order accepts a naive `now`",
     "    if created.tzinfo is None:\n"
     '        raise BrokerToolError("now must be timezone-aware")',
     "    if False:\n"
     '        raise BrokerToolError("now must be timezone-aware")'),

    (M, "preview_order no longer requires a client_order_id of its own",
     "    if not client_order_id:",
     "    if False:"),

    # -- SS.8.6 write refusals ----------------------------------------------
    (M, "_refuse_write returns instead of raising: every write tool opens",
     "    unmet = unmet_controls()\n"
     "    prereq = unmet_live_prerequisites()\n"
     "    raise NotImplementedError(",
     "    unmet = unmet_controls()\n"
     "    prereq = unmet_live_prerequisites()\n"
     "    return\n"
     "    raise NotImplementedError("),

    (M, "place_order accepts a preview_id plus a confirmation token",
     '    """SS.8.6 `place_order`. Refuses unconditionally."""\n'
     "    _refuse_write(",
     '    """SS.8.6 `place_order`. Refuses unconditionally."""\n'
     "    if preview_id and confirmation_token:\n"
     "        return None\n"
     "    _refuse_write("),

    (M, "modify_order stops refusing",
     '    """SS.8.6 `modify_order`. Refuses unconditionally."""\n'
     "    _refuse_write(",
     '    """SS.8.6 `modify_order`. Refuses unconditionally."""\n'
     "    return None\n"
     "    _refuse_write("),

    (M, "cancel_order stops refusing: a cancel is still a write",
     '    _refuse_write(\n        "cancel_order",',
     '    return None\n    _refuse_write(\n        "cancel_order",'),

    (M, "cancel_all_orders stops refusing",
     '    _refuse_write(\n        "cancel_all_orders",',
     '    return None\n    _refuse_write(\n        "cancel_all_orders",'),

    (M, "flatten_position stops refusing: the webhook's favourite action",
     '    _refuse_write(\n        "flatten_position",',
     '    return None\n    _refuse_write(\n        "flatten_position",'),

    # -- SS.8.4 reads: mode gate, adapter gate, transport -------------------
    (M, "the mode gate is skipped on broker reads",
     '    require("read_broker_account")',
     '    pass  # require("read_broker_account")'),

    (M, "the adapter gate is bypassed, so a LIVE read needs no prerequisites",
     "    adapter = assert_adapter_usable(usable[0], env)",
     "    adapter = [a for a in enabled_adapters() if a.key == usable[0]][0]"),

    (M, "a read returns an EMPTY result instead of refusing: 'you are flat'",
     "    adapter = assert_adapter_usable(usable[0], env)\n"
     "    raise BrokerToolError(",
     "    adapter = assert_adapter_usable(usable[0], env)\n"
     '    return {"tool": name, "positions": [], "orders": [], "executions": []}\n'
     "    raise BrokerToolError("),

    (M, "broker_executions accepts an inverted window",
     "        if a > b:",
     "        if False:"),

    (M, "broker_executions accepts a mixed-awareness window",
     "        if (a.tzinfo is None) != (b.tzinfo is None):",
     "        if False:"),

    (M, "broker_executions accepts a non-string start",
     "    if start is not None and not isinstance(start, str):",
     "    if False:"),

    # -- SS.8.5 portfolio_risk ----------------------------------------------
    (M, "portfolio_risk accepts a confidence level of exactly 0 or 1",
     "    if not 0.0 < conf < 1.0:",
     "    if not 0.0 <= conf <= 1.0:"),

    (M, "portfolio_risk accepts an unknown method",
     '    if method not in ("historical", "parametric", "monte_carlo"):',
     "    if False:"),

    (M, "portfolio_risk accepts a fractional horizon",
     "    if horizon <= 0 or horizon != int(horizon):",
     "    if horizon <= 0:"),

    # -- the manifest: an honest self-report --------------------------------
    (M, "the manifest claims an order CAN be submitted",
     '        "can_submit_an_order": False,',
     '        "can_submit_an_order": True,'),

    (M, "the manifest claims a kill switch exists",
     '        "kill_switch_exists": False,',
     '        "kill_switch_exists": True,'),

    (M, "the manifest's risk-check count is written down instead of computed",
     '        "n_risk_checks": len(RISK_CHECKS),',
     '        "n_risk_checks": 15,'),

    # -- the module boundary: nothing on the order path reads documents -----
    (M, "broker_tools imports the RAG document layer",
     "from execution.brokers import (ADAPTERS, BrokerError, assert_adapter_usable,",
     "from rag.documents import TRUST_LEVELS\n"
     "from execution.brokers import (ADAPTERS, BrokerError, assert_adapter_usable,"),

    (M, "BrokerToolError becomes a BrokerError, blurring the two layers",
     "class BrokerToolError(RuntimeError):",
     "class BrokerToolError(BrokerError):"),
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
        print("ABORT: an oracle fails BEFORE any mutation is applied.")
        print(out[-3000:])
        return 1
    print("baseline: oracles pass (%s), %d mutations to apply\n"
          % (", ".join(ORACLES), len(MUTATIONS)))

    backup = tempfile.mkdtemp(prefix="brokertools_orig_")
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
    print("  source restored and oracles green: %s" % intact)
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
