"""
Mutation battery for the Alpha Vantage connector (src/market/alpha_vantage.py).

WHY THIS MODULE NEEDS ITS OWN BATTERY
-------------------------------------
mutate_market.py runs test_market.py and probe_quotes.py as its oracles, and
neither imports alpha_vantage.py. A mutation to this connector applied under that
battery would survive for the uninteresting reason that the wrong suite was
watching. This battery's oracles are test_alpha_vantage.py AND
probe_alpha_vantage.py together, and each catches a class the other misses:

  - test_alpha_vantage.py asserts the POSITIVE contract: 100 quotes parse, the
    adjusted fetch returns the adjusted close, the labels are what downstream
    guards expect. Mutations that make the connector refuse EVERYTHING die here
    and only here.
  - probe_alpha_vantage.py fires 112 hostile payloads. Mutations that make the
    connector ACCEPT an error body, a NaN, or a premium endpoint die there and
    only there.

That split is not hypothetical for this module. When the error-key guard was
disabled as a check, the error-ONLY bodies were still refused -- by the
missing-series guard downstream -- and only the "notice arriving ALONGSIDE a full
series" cases exposed it. One oracle alone would have reported all clear.

WHAT A SURVIVOR MEANS
---------------------
A survivor is a finding about the TESTS, not the code: the seeded defect is real
and nothing noticed. A SKIP is worse than a survivor, because it reads as a
non-event -- in this project a SKIP has already concealed a live survivor, and on
2026-08-14 a stale find-string in mutate_market.py had silently stopped testing
anything while still printing a line. Both are failures and both set a non-zero
exit.

THE DEFECT THIS MODULE ALREADY HAD
----------------------------------
adjusted=True read "4. close" instead of "5. adjusted close", because the loop
tried fields in a fixed order and the adjusted payload contains BOTH. MEASURED on
IBM's 100-day window: 96 of 100 days differ, by up to 3.57 on a ~245 price
(1.45%), from two dividend events. It is seeded below as mutation #1, so that its
absence stays a tested property rather than a fix nobody watches.

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

ORACLES = ("test_alpha_vantage.py", "probe_alpha_vantage.py")


def module_path(module):
    return os.path.join(SRC_ROOT, module)


def clear_pycache():
    for base, dirs, _ in os.walk(SRC_ROOT):
        for d in list(dirs):
            if d == "__pycache__":
                shutil.rmtree(os.path.join(base, d), ignore_errors=True)


# Mutations that cannot be killed because another layer independently enforces
# the same rule. The bar for an entry is NOT "I could not think of a test": it is
# "I attempted to reach the guard and FAILED, and the attempt is recorded here."
EQUIVALENT = {}


MUTATIONS = [
    # --- the defect this module actually had -------------------------------
    # Seeded first because it is the one failure known to have occurred. If this
    # ever survives, the regression is live again.
    ("market/alpha_vantage.py",
     "adjusted=True reads the UNADJUSTED close (the original defect)",
     "        want = CLOSE_FIELD[bool(adjusted)]",
     '        want = None\n'
     '        for _f in ("4. close", "5. adjusted close", "close"):\n'
     '            if _f in row:\n'
     '                want = _f\n'
     '                break'),
    ("market/alpha_vantage.py", "the close field mapping is inverted",
     'CLOSE_FIELD = {False: "4. close", True: "5. adjusted close"}',
     'CLOSE_FIELD = {False: "5. adjusted close", True: "4. close"}'),
    ("market/alpha_vantage.py",
     "a missing adjusted-close field falls back instead of refusing",
     "        if want not in row:",
     "        if False:"),
    ("market/alpha_vantage.py", "the adjustment label ignores what was asked",
     '            adjustment_status="ADJUSTED" if adjusted else "UNADJUSTED",',
     '            adjustment_status="ADJUSTED",'),
    ("market/alpha_vantage.py", "the series container key is guessed, not measured",
     'SERIES_KEY = "Time Series (Daily)"',
     'SERIES_KEY = "Time Series (Daily Adjusted)"'),

    # --- the central guard: HTTP 200 is not success ------------------------
    ("market/alpha_vantage.py", "error bodies are parsed as data",
     "    for k in ERROR_KEYS:\n        if k in payload:",
     "    for k in ERROR_KEYS:\n        if False:"),
    ("market/alpha_vantage.py", "only the FIRST error key is checked",
     "    for k in ERROR_KEYS:\n        if k in payload:",
     "    for k in ERROR_KEYS[:1]:\n        if k in payload:"),
    ("market/alpha_vantage.py", "the rate-limit key is dropped from the vocabulary",
     'ERROR_KEYS = ("Error Message", "Information", "Note")',
     'ERROR_KEYS = ("Error Message", "Information")'),
    ("market/alpha_vantage.py",
     "the Information key -- the one MEASURED in every failure -- is dropped",
     'ERROR_KEYS = ("Error Message", "Information", "Note")',
     'ERROR_KEYS = ("Error Message", "Note")'),
    ("market/alpha_vantage.py", "a non-object payload is accepted",
     "    if not isinstance(payload, dict):",
     "    if False:"),
    ("market/alpha_vantage.py", "a missing series becomes an empty result",
     "    if series_key not in payload:",
     "    if False:"),
    ("market/alpha_vantage.py", "an empty series is returned as no-trading",
     "    if not isinstance(series, dict) or not series:",
     "    if False:"),
    # `or not series` is the half that catches the empty dict. Deleting only that
    # half still refuses a list, so a test that only tries a list cannot see it.
    ("market/alpha_vantage.py", "an EMPTY series object passes the type check",
     "    if not isinstance(series, dict) or not series:",
     "    if not isinstance(series, dict):"),
    ("market/alpha_vantage.py", "a series that is a LIST passes the emptiness check",
     "    if not isinstance(series, dict) or not series:",
     "    if not series:"),
    ("market/alpha_vantage.py", "a row that is not an object is parsed anyway",
     "        if not isinstance(row, dict):",
     "        if False:"),

    # --- numbers that are not prices ---------------------------------------
    ("market/alpha_vantage.py", "a non-numeric price is coerced instead of refused",
     "    try:\n        value = float(str(raw).strip())\n"
     "    except (TypeError, ValueError):",
     "    try:\n        value = float(str(raw).strip() or 0)\n"
     "    except (TypeError, ValueError):"),
    ("market/alpha_vantage.py", "NaN and infinity enter calculations",
     '    if value != value or value in (float("inf"), float("-inf")):',
     "    if False:"),
    # NaN != NaN is the only reliable NaN test; keeping just the infinity half
    # still refuses inf, so an inf-only test cannot detect this.
    ("market/alpha_vantage.py", "NaN passes while infinity is still refused",
     '    if value != value or value in (float("inf"), float("-inf")):',
     '    if value in (float("inf"), float("-inf")):'),
    ("market/alpha_vantage.py", "infinity passes while NaN is still refused",
     '    if value != value or value in (float("inf"), float("-inf")):',
     "    if value != value:"),
    ("market/alpha_vantage.py", "a negative price is accepted",
     "    if value < 0:",
     "    if False:"),
    ("market/alpha_vantage.py", "a zero price is accepted",
     '    if field != "volume" and value == 0:',
     "    if False:"),
    # The mirror-image error: refusing a legitimate zero VOLUME. A suite made
    # only of refusals would call this an improvement.
    ("market/alpha_vantage.py", "a legitimate zero VOLUME is refused",
     '    if field != "volume" and value == 0:',
     "    if value == 0:"),

    # --- the constructed timestamp -----------------------------------------
    ("market/alpha_vantage.py", "a malformed date key is accepted",
     "    if not _DATE_RE.match(str(date_str)):",
     "    if False:"),
    ("market/alpha_vantage.py", "the date pattern accepts anything date-like",
     '_DATE_RE = re.compile(r"^\\d{4}-\\d{2}-\\d{2}$")',
     '_DATE_RE = re.compile(r"\\d{4}")'),
    ("market/alpha_vantage.py", "quotes are stamped at midnight, not the close",
     "SESSION_CLOSE_HOUR = 16",
     "SESSION_CLOSE_HOUR = 0"),
    ("market/alpha_vantage.py",
     "the constructed-timestamp assumption is dropped from the quote",
     "            note=assumption))",
     '            note=""))'),
    ("market/alpha_vantage.py",
     "the assumption no longer says the timestamp was constructed",
     '        "timestamp CONSTRUCTED, not observed: the daily payload carries a date "',
     '        "timestamp: the daily payload carries a date "'),
    ("market/alpha_vantage.py",
     "an EST/EDT offset is invented rather than declared unknown",
     '    stamp = datetime.datetime(d.year, d.month, d.day, SESSION_CLOSE_HOUR, 0,\n'
     "                              tzinfo=datetime.timezone.utc)",
     '    stamp = datetime.datetime(d.year, d.month, d.day, SESSION_CLOSE_HOUR, 0,\n'
     "                              tzinfo=datetime.timezone(\n"
     "                                  datetime.timedelta(hours=-4)))"),

    # --- the labels downstream guards depend on ----------------------------
    # Each of these makes the connector's output MORE useful and less true, which
    # is the direction a well-meaning maintainer breaks it.
    ("market/alpha_vantage.py", "quotes are labelled REALTIME instead of END_OF_DAY",
     '            delay_status="END_OF_DAY",',
     '            delay_status="REALTIME",'),
    ("market/alpha_vantage.py", "quotes claim exchange-level trust",
     '            trust_level="UNVERIFIED",',
     '            trust_level="EXCHANGE",'),
    ("market/alpha_vantage.py", "quotes claim the market is CLOSED, not UNKNOWN",
     '            market_status="UNKNOWN",',
     '            market_status="CLOSED",'),
    ("market/alpha_vantage.py", "the licence string stops naming the risk basis",
     '            licence="Alpha Vantage free tier, personal non-commercial use; "',
     '            licence="Alpha Vantage free tier; "'),
    ("market/alpha_vantage.py", "the constructed instant is echoed as the provider's own",
     "            provider_timestamp=None, retrieved_at=retrieved,",
     "            provider_timestamp=stamp, retrieved_at=retrieved,"),

    # --- what the connector refuses to ask for -----------------------------
    ("market/alpha_vantage.py", "any function may be requested",
     "    if function not in PERMITTED_FUNCTIONS:",
     "    if False:"),
    ("market/alpha_vantage.py", "premium endpoints are added to the permitted set",
     'PERMITTED_FUNCTIONS = ("TIME_SERIES_DAILY", "TIME_SERIES_DAILY_ADJUSTED")',
     'PERMITTED_FUNCTIONS = ("TIME_SERIES_DAILY", "TIME_SERIES_DAILY_ADJUSTED",\n'
     '                       "TIME_SERIES_INTRADAY", "GLOBAL_QUOTE")'),
    ("market/alpha_vantage.py", "any symbol is sent to the provider",
     "    if not _SYMBOL_RE.match(sym):",
     "    if False:"),
    ("market/alpha_vantage.py", "the symbol pattern allows separators and spaces",
     '_SYMBOL_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\\-]{0,15}$")',
     '_SYMBOL_RE = re.compile(r"^.{1,40}$")'),
    ("market/alpha_vantage.py", "outputsize is unvalidated",
     '    if outputsize not in ("compact", "full"):',
     "    if False:"),
    ("market/alpha_vantage.py", "the response format is left to the provider",
     '              "apikey": api_key, "datatype": "json"}',
     '              "apikey": api_key}'),

    # --- credentials -------------------------------------------------------
    # This mutation SKIPPED on 2026-08-14 as (ambiguous), and the skip WAS the
    # finding. Its find-string "    if not key:" occurs TWICE in the module
    # (MEASURED with str.count) because redact() begins with the same line -- so
    # it silently tested nothing while still printing a result line. A SKIP is
    # treated here as worse than a survivor for exactly this reason.
    #
    # Re-targeted with the preceding strip() line, which MEASURED at exactly one
    # occurrence. The mutation now really does default a missing key to "demo",
    # and it is killed by the message-level assertions in test_alpha_vantage.py:
    # the outcome is still a refusal either way, so only the wording separates a
    # MISSING key from a FORBIDDEN one.
    ("market/alpha_vantage.py", "a missing API key is silently defaulted to demo",
     "    key = str(key).strip()\n    if not key:",
     '    key = str(key).strip()\n    if not key:\n        key = "demo"\n'
     "    if False:"),
    ("market/alpha_vantage.py", "the demo key is accepted",
     '    if key.lower() == "demo":',
     "    if False:"),
    ("market/alpha_vantage.py", "the demo check is case-sensitive",
     '    if key.lower() == "demo":',
     '    if key == "demo":'),
    ("market/alpha_vantage.py", "a malformed key is sent anyway",
     '    if not re.match(r"^[A-Za-z0-9]{8,64}$", key):',
     "    if False:"),
    ("market/alpha_vantage.py", "redaction leaves the key in the message",
     "    return str(text).replace(key, \"[REDACTED-API-KEY]\")",
     "    return str(text)"),
    ("market/alpha_vantage.py", "redaction is skipped when a key IS present",
     "    if not key:\n        return text",
     "    if key:\n        return text"),

    # --- the 25/day budget -------------------------------------------------
    ("market/alpha_vantage.py", "the budget never refuses",
     "        if self._used >= self.limit:",
     "        if False:"),
    ("market/alpha_vantage.py", "the budget is off by one and allows a 26th",
     "        if self._used >= self.limit:",
     "        if self._used > self.limit:"),
    ("market/alpha_vantage.py", "spending does not increment the counter",
     "        self._used += 1",
     "        self._used += 0"),
    ("market/alpha_vantage.py", "a zero or negative budget limit is accepted",
     "        if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:",
     "        if False:"),
    # bool is an int subclass: without the explicit check, limit=True means 1.
    ("market/alpha_vantage.py", "True is accepted as a budget limit",
     "        if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:",
     "        if not isinstance(limit, int) or limit <= 0:"),
    ("market/alpha_vantage.py", "the budget claims to be durable",
     '                "in_memory_only": True,',
     '                "in_memory_only": False,'),
    ("market/alpha_vantage.py", "the budget presents itself as a data cache",
     '                "note": "resets on process restart; not a substitute for the "\n'
     '                        "provider\'s own accounting, and NOT a data cache"}',
     '                "note": "a durable cache of provider responses"}'),

    # --- ORDER: the gates must run before the budget is spent --------------
    ("market/alpha_vantage.py", "the licence gate is skipped entirely",
     "    provider = assert_provider_usable(PROVIDER_KEY)",
     "    provider = get_provider(PROVIDER_KEY)"),
    ("market/alpha_vantage.py", "the tier gate is skipped entirely",
     '    assert_tier_supports(PROVIDER_KEY, "END_OF_DAY")',
     "    pass"),
    ("market/alpha_vantage.py",
     "the request is paid for before it is known to be valid",
     '    url = build_url(symbol, function=function, outputsize=outputsize,\n'
     "                    api_key=key)\n"
     "    b = budget if budget is not None else BUDGET\n"
     '    b.spend("%s %s" % (function, str(symbol).upper()))',
     "    b = budget if budget is not None else BUDGET\n"
     '    b.spend("%s %s" % (function, str(symbol).upper()))\n'
     '    url = build_url(symbol, function=function, outputsize=outputsize,\n'
     "                    api_key=key)"),

    # --- the manifest ------------------------------------------------------
    ("market/alpha_vantage.py", "the manifest claims the licence permits machine use",
     '        "permits_machine_use": p.permits_machine_use,',
     '        "permits_machine_use": True,'),
    ("market/alpha_vantage.py", "the manifest reports a stronger trust level",
     '        "trust_level_of_quotes": "UNVERIFIED",',
     '        "trust_level_of_quotes": "EXCHANGE",'),
    ("market/alpha_vantage.py", "the manifest stops reporting what it cannot do",
     '        "cannot": [',
     '        "cannot": [] and ['),
    ("market/alpha_vantage.py", "the manifest hides who accepted the risk",
     '        "decided_by": p.decided_by,',
     '        "decided_by": "",'),
]
def run_oracle(name):
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = SRC_ROOT + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, os.path.join(HERE, name)],
        cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = proc.stdout.decode("utf-8", "replace")
    ok = proc.returncode == 0
    # probe_quotes.py exits 0 when everything was refused, but an ALLOWED or
    # CRASHED line is a failure even so. Belt and braces: a probe that starts
    # allowing things must not read as a passing oracle.
    if "** ALLOWED" in out or "!! CRASHED" in out:
        ok = False
    return ok, out


def run_tests():
    """Both oracles must pass. Either one failing kills the mutation."""
    for name in ORACLES:
        ok, out = run_oracle(name)
        if not ok:
            return False, "%s FAILED\n%s" % (name, out[-2000:])
    return True, ""


def clear_pycache():
    for dirpath, dirnames, _ in os.walk(ROOT):
        for d in list(dirnames):
            if d == "__pycache__":
                shutil.rmtree(os.path.join(dirpath, d), ignore_errors=True)


def main():
    clear_pycache()

    ok, out = run_tests()
    if not ok:
        print("ABORT: an oracle fails BEFORE any mutation is applied.")
        print(out[-3000:])
        return 1
    print("baseline: both oracles pass (%s), %d mutations to apply\n"
          % (", ".join(ORACLES), len(MUTATIONS)))

    backup = tempfile.mkdtemp(prefix="market_orig_")
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
                # A no-op "mutation" is not a finding, it is a bug in this file.
                # This check exists because I have written one five times.
                skipped += 1
                skips.append("%s: %s (NO-OP: find == replace)" % (module, desc))
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
