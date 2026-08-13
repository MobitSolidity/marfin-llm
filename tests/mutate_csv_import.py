"""
Mutation battery for the CSV ingestion layer (src/market/csv_import.py).

WHY THIS BATTERY NEEDS TWO ORACLES
----------------------------------
Same reason mutate_market.py does, but sharper here, because csv_import.py has a
failure mode the other modules do not: it returns a REPORT instead of raising.

  - probe_csv_import.py kills mutations that make the layer ACCEPT garbage: 45
    structural attacks that must raise, and 23 semantic defects that must be
    recorded at the right severity AND actually block a calculation.
  - test_csv_import.py kills mutations that make the layer REFUSE EVERYTHING,
    or record findings at the wrong severity, or refuse for the wrong reason.

Running only the probe would let every severity mutation through -- downgrading
a MATERIAL finding to ADVISORY changes nothing about what raises, and everything
about whether a defective file can price a calculation. Running only the suite
would let "accept anything" mutations through in the paths the suite happens not
to construct. That is not hypothetical: this module's first execution produced
FIVE files that parsed with no finding at all while the suite did not yet exist.

THE SEVERITY MUTATIONS ARE THE POINT OF THIS FILE
-------------------------------------------------
A guard that raises is easy to test. A finding is not: it is data, and data can
be wrong quietly. So this battery seeds, for every severity in the module, a
downgrade (BLOCKING -> ADVISORY, MATERIAL -> ADVISORY). Each one leaves the
module importable, every attack still "reported", and the file usable for a
material calculation it should not support. If a downgrade survives, the finding
it produces is decoration.

WHAT A SURVIVOR MEANS
---------------------
A survivor is a finding about the TESTS, not the code: the seeded defect is real
and nothing noticed. A SKIP is worse than a survivor, because it looks like a
non-event -- in this project a SKIP has already concealed a live survivor. Both
are failures and both set a non-zero exit.

ON WRITING THE MUTATIONS THEMSELVES
-----------------------------------
Six times in this project I have seeded a mutation that changed nothing and then
read its survival as a test gap. The NO-OP guard below exists because of that,
and every replacement here was checked for being a genuine behavioural change
before it was added.

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

# Both oracles. Order matters only for readability of the output.
ORACLES = ("test_csv_import.py", "probe_csv_import.py")


def module_path(module):
    return os.path.join(SRC_ROOT, module)


# Mutations that cannot be killed because another layer independently enforces
# the same thing. Documented individually so that "survived: 0" keeps meaning
# something and nobody learns to skim past a nonzero count.
#
# This dict starts EMPTY on purpose. In the execution battery I recorded an
# entry that was accurate about behaviour and still the wrong conclusion: the
# equivalence would have dissolved silently the moment the surrounding code
# changed. An empty dict here is a claim I would rather be forced to defend
# mutation by mutation.
EQUIVALENT = {}

# (module, description, find, replace)
MUTATIONS = [
    # --- structural refusals: the file is not a series at all ---------------
    ("market/csv_import.py", "a missing file is parsed anyway",
     "    if not os.path.isfile(path):",
     "    if False:"),
    ("market/csv_import.py", "an empty path is accepted",
     "    if not path or not isinstance(path, str):",
     "    if False:"),
    ("market/csv_import.py", "a zero-byte file is accepted",
     "    if n_bytes == 0:",
     "    if False:"),
    ("market/csv_import.py", "a file with no data rows is accepted",
     "        if ragged_count:",
     "        if False:"),
    ("market/csv_import.py", "timestamp and close stop being required",
     '_REQUIRED_COLUMNS = ("timestamp", "close")',
     '_REQUIRED_COLUMNS = ()'),
    ("market/csv_import.py", "the missing-column check no longer refuses",
     "    if missing:",
     "    if False:"),

    # --- numeric pathologies -----------------------------------------------
    # The NaN guard was near-dead code in the first version: 'NaN' was swallowed
    # as a null sentinel before float() ran. Removing 'NAN' from _NULL_CELLS is
    # what made the guard reachable, so the sentinel list itself is mutated here.
    ("market/csv_import.py", "NaN goes back to being swallowed as a null cell",
     '_NULL_CELLS = ("", "N/A", "NA", "NULL", "NONE", "-", "--", "#N/A")',
     '_NULL_CELLS = ("", "N/A", "NA", "NAN", "NULL", "NONE", "-", "--", "#N/A")'),
    ("market/csv_import.py", "NaN prices are accepted",
     "    if value != value:",
     "    if False:"),
    ("market/csv_import.py", "infinite prices are accepted",
     '    if value in (float("inf"), float("-inf")):',
     "    if False:"),
    ("market/csv_import.py", "unparseable text becomes a silent null",
     '        raise CsvValidationError(\n'
     '            "line %d: column %r is not a number: %r" % (lineno, column, text))',
     '        return (None, True)'),
    # The locale defect: unconditional comma-stripping turned '1,5' into 15.0,
    # a silent factor-of-ten error in a price.
    ("market/csv_import.py", "commas are stripped unconditionally again (1,5 -> 15)",
     '    candidate = text\n'
     '    if "," in text:',
     '    candidate = text.replace(",", "")\n'
     '    if False:'),
    ("market/csv_import.py", "the ambiguous-locale refusal is removed",
     '            raise CsvValidationError(\n'
     '                "line %d: column %r is ambiguous: %r may be a decimal comma "',
     '            candidate = text.replace(",", "")\n'
     '        if False:\n'
     '            raise CsvValidationError(\n'
     '                "line %d: column %r is ambiguous: %r may be a decimal comma "'),
    # _parse_number returning a bare value instead of a pair is how the
    # null-tracking defect existed in the first place.
    ("market/csv_import.py", "a null cell is indistinguishable from a parsed one",
     "        return (None, True)\n\n    # A thousands separator",
     "        return (None, False)\n\n    # A thousands separator"),

    # --- the blank-cell finding: the worst defect this module had -----------
    ("market/csv_import.py", "blank cells are recorded nowhere (the original defect)",
     "    for field in sorted(null_counts):",
     "    for field in ():"),
    ("market/csv_import.py", "a wholly empty close column is only MATERIAL",
     '            severity = "BLOCKING" if (field == "close" and share >= 0.5) \\\n'
     '                else "MATERIAL"',
     '            severity = "MATERIAL"'),
    ("market/csv_import.py", "a partly empty column is downgraded to ADVISORY",
     '        else:\n'
     '            severity = "MATERIAL"\n'
     '        add("columns", severity,',
     '        else:\n'
     '            severity = "ADVISORY"\n'
     '        add("columns", severity,'),
    ("market/csv_import.py", "null cells are counted but never totalled",
     "                if was_null:\n"
     "                    null_counts[field] = null_counts.get(field, 0) + 1",
     "                if False:\n"
     "                    null_counts[field] = null_counts.get(field, 0) + 1"),

    # --- timestamps and timezone -------------------------------------------
    ("market/csv_import.py", "an empty timestamp is accepted",
     '        raise CsvValidationError("empty timestamp")',
     "        return (datetime.datetime(1970, 1, 1), True)"),
    ("market/csv_import.py", "an unparseable timestamp is accepted",
     '            raise CsvValidationError("unparseable timestamp %r" % (text,))',
     "            return (datetime.datetime(1970, 1, 1), True)"),
    # Silently stamping UTC on a naive timestamp destroys the evidence that it
    # was missing -- which is why _parse_timestamp returns was_naive at all.
    ("market/csv_import.py", "naive timestamps are silently stamped UTC",
     "    return (parsed, parsed.tzinfo is None)",
     "    return (parsed, False)"),
    ("market/csv_import.py", "a naive series with no declared tz is not BLOCKING",
     '    if naive_count and not declared_timezone:\n'
     '        add("timezone", "BLOCKING",',
     '    if naive_count and not declared_timezone:\n'
     '        add("timezone", "ADVISORY",'),
    ("market/csv_import.py", "declaring a timezone is treated as verifying it",
     '    elif naive_count and declared_timezone:',
     '    elif False:'),
    ("market/csv_import.py", "epoch timestamps stop being timezone-aware",
     "        return (datetime.datetime.fromtimestamp(\n"
     "            int(text), datetime.timezone.utc), False)",
     "        return (datetime.datetime.utcfromtimestamp(int(text)), False)"),

    # --- ordering and duplicates ------------------------------------------
    ("market/csv_import.py", "an unordered series is not BLOCKING",
     '    if not ascending and not descending:\n'
     '        add("ordering", "BLOCKING",',
     '    if not ascending and not descending:\n'
     '        add("ordering", "ADVISORY",'),
    ("market/csv_import.py", "descending order is downgraded to ADVISORY",
     '        add("ordering", "MATERIAL",\n'
     '            "rows are in DESCENDING time order",',
     '        add("ordering", "ADVISORY",\n'
     '            "rows are in DESCENDING time order",'),
    ("market/csv_import.py", "descending order is silently reordered for the user",
     "    comparable = [t.replace(tzinfo=None) for t in timestamps]",
     "    comparable = sorted(t.replace(tzinfo=None) for t in timestamps)"),
    ("market/csv_import.py", "duplicate timestamps are downgraded to ADVISORY",
     '        add("duplicates", "MATERIAL",',
     '        add("duplicates", "ADVISORY",'),
    ("market/csv_import.py", "duplicates are no longer detected",
     "    dupes = sorted(t for t, c in counts.items() if c > 1)",
     "    dupes = []"),
    # A 2-element duplicate check that used > 2 would miss a two-row file.
    ("market/csv_import.py", "the duplicate threshold is off by one",
     "    dupes = sorted(t for t, c in counts.items() if c > 1)",
     "    dupes = sorted(t for t, c in counts.items() if c > 2)"),

    # --- the timeframe cross-check: a declaration nothing verifies ----------
    ("market/csv_import.py", "the declared timeframe is taken on trust",
     "    elif len(ordered) >= 2:",
     "    elif False:"),
    ("market/csv_import.py", "finer-grained data than declared is only ADVISORY",
     '                add("timeframe", "BLOCKING",\n'
     '                    "declared timeframe %s but the smallest gap between bars is "',
     '                add("timeframe", "ADVISORY",\n'
     '                    "declared timeframe %s but the smallest gap between bars is "'),
    ("market/csv_import.py", "the cross-check needs 3 bars again (2-bar file unchecked)",
     "    elif len(ordered) >= 2:\n"
     "        # Cross-check the declared timeframe",
     "    elif len(ordered) > 2:\n"
     "        # Cross-check the declared timeframe"),
    ("market/csv_import.py", "the spacing tolerance is loosened past usefulness",
     "            if modal < step * 0.5:",
     "            if modal < step * 0.001:"),
    ("market/csv_import.py", "an undeclared timeframe is not reported",
     '    if not expected_timeframe:\n'
     '        add("timeframe", "MATERIAL",',
     '    if not expected_timeframe:\n'
     '        add("timeframe", "ADVISORY",'),
    ("market/csv_import.py", "an unknown timeframe is guessed instead of reported",
     "    elif expected_timeframe not in TIMEFRAME_SECONDS:",
     "    elif False:"),
    ("market/csv_import.py", "1d is redefined as 1h (annualization off by 24x)",
     '"1h": 3600, "4h": 14400, "1d": 86400, "1w": 604800,',
     '"1h": 3600, "4h": 14400, "1d": 3600, "1w": 604800,'),

    # --- missing bars: ADVISORY on purpose, and that must not drift ---------
    ("market/csv_import.py", "gaps are escalated to MATERIAL (cries wolf on weekends)",
     '            add("missing_bars", "ADVISORY",\n'
     '                "%d gap(s) larger than one %s interval" % (gaps, timeframe),',
     '            add("missing_bars", "MATERIAL",\n'
     '                "%d gap(s) larger than one %s interval" % (gaps, timeframe),'),
    ("market/csv_import.py", "gap detection never runs",
     "    if timeframe in TIMEFRAME_SECONDS and len(ordered) >= 2:",
     "    if False:"),
    ("market/csv_import.py", "the gap tolerance is widened to hide gaps",
     "            if delta > step * 1.5:",
     "            if delta > step * 500:"),
    ("market/csv_import.py", "a 2-bar file blames its declared timeframe again",
     '    elif timeframe not in TIMEFRAME_SECONDS:\n'
     '        add("missing_bars", "MATERIAL",\n'
     '            "gap detection did not run: no usable timeframe (%s)" % (timeframe,),',
     '    elif True:\n'
     '        add("missing_bars", "MATERIAL",\n'
     '            "gap detection did not run: timeframe is %s" % (timeframe,),'),
    ("market/csv_import.py", "no-timeframe gap failure is downgraded to ADVISORY",
     '    elif timeframe not in TIMEFRAME_SECONDS:\n'
     '        add("missing_bars", "MATERIAL",',
     '    elif timeframe not in TIMEFRAME_SECONDS:\n'
     '        add("missing_bars", "ADVISORY",'),

    # --- what the USER declared: the opposite of inferring from a filename --
    ("market/csv_import.py", "an undeclared symbol/exchange/currency is not BLOCKING",
     '            add(key, "BLOCKING", "no %s was declared for this file" % (key,), why)',
     '            add(key, "ADVISORY", "no %s was declared for this file" % (key,), why)'),
    ("market/csv_import.py", "the symbol/exchange/currency checks stop running",
     "        if not value:\n"
     '            add(key, "BLOCKING",',
     "        if False:\n"
     '            add(key, "BLOCKING",'),
    ("market/csv_import.py", "an UNKNOWN adjustment status is not reported",
     '    if declared_adjustment_status == "UNKNOWN":',
     "    if False:"),
    ("market/csv_import.py", "adjustment status is downgraded to ADVISORY",
     '        add("adjustment_status", "MATERIAL",\n'
     '            "adjustment status is UNKNOWN",',
     '        add("adjustment_status", "ADVISORY",\n'
     '            "adjustment status is UNKNOWN",'),
    ("market/csv_import.py", "an unknown adjustment status value is accepted",
     "        if adjustment_status not in ADJUSTMENT_STATUS:",
     "        if False:"),
    ("market/csv_import.py", "an unknown origin is accepted",
     "        if origin not in VALUE_ORIGINS:",
     "        if False:"),

    # --- export time: stale data's quietest entry point ---------------------
    ("market/csv_import.py", "a missing export time is not reported",
     "    if exported_at is None:",
     "    if False:"),
    ("market/csv_import.py", "a missing export time is downgraded to ADVISORY",
     '        add("export_time", "MATERIAL",\n'
     '            "no export time was declared",',
     '        add("export_time", "ADVISORY",\n'
     '            "no export time was declared",'),
    ("market/csv_import.py", "a FUTURE export time is not BLOCKING",
     '            add("export_time", "BLOCKING",',
     '            add("export_time", "ADVISORY",'),
    ("market/csv_import.py", "the future-timestamp window is widened to a year",
     "        if age_days < -1:",
     "        if age_days < -365:"),
    ("market/csv_import.py", "a stale export is not reported",
     "        elif age_days > max_export_age_days:",
     "        elif False:"),
    ("market/csv_import.py", "the staleness threshold is ignored",
     "        elif age_days > max_export_age_days:",
     "        elif age_days > 100000:"),
    # The filesystem mtime as a substitute for a declared export time: copying a
    # file rewrites mtime, so a year-old export would look minutes old.
    ("market/csv_import.py", "mtime is used as the export time",
     "    exported_at = declared_exported_at\n",
     "    exported_at = declared_exported_at or datetime.datetime.fromtimestamp(\n"
     "        os.path.getmtime(path), datetime.timezone.utc)\n"),

    # --- columns: an adjusted close is a DIFFERENT number ------------------
    ("market/csv_import.py", "adjusted close is treated as close",
     '    "adj close": "adj_close", "adjclose": "adj_close",',
     '    "adj close": "close", "adjclose": "close",'),
    ("market/csv_import.py", "a duplicate column mapping is not BLOCKING",
     '                add("columns", "BLOCKING",\n'
     '                    "column %r maps to %r, which already appeared as %r"',
     '                add("columns", "ADVISORY",\n'
     '                    "column %r maps to %r, which already appeared as %r"'),
    ("market/csv_import.py", "duplicate column detection stops",
     "            if key in seen:",
     "            if False:"),
    ("market/csv_import.py", "unrecognised columns are silently dropped",
     "        if key is None:\n"
     "            indicator_columns.append(name)",
     "        if key is None:\n"
     "            pass"),
    ("market/csv_import.py", "indicator columns are not reported",
     "    if indicator_columns:",
     "    if False:"),
    ("market/csv_import.py", "indicator columns are downgraded to ADVISORY",
     '        add("indicator_columns", "MATERIAL",',
     '        add("indicator_columns", "ADVISORY",'),
    ("market/csv_import.py", "a ragged row is silently accepted and misaligned",
     "        if len(row) != len(raw_names):",
     "        if False:"),
    ("market/csv_import.py", "a ragged row is only ADVISORY",
     '            add("columns", "MATERIAL",\n'
     '                "line %d has %d fields but the header has %d"',
     '            add("columns", "ADVISORY",\n'
     '                "line %d has %d fields but the header has %d"'),

    # --- assert_usable_for: where findings become consequences -------------
    ("market/csv_import.py", "a CSV may price a live order after all",
     '        if purpose == "live_order":',
     "        if False:"),
    ("market/csv_import.py", "BLOCKING findings no longer block a calculation",
     "            if blocking:",
     "            if False:"),
    ("market/csv_import.py", "MATERIAL findings no longer block a calculation",
     "            if material:",
     "            if False:"),
    ("market/csv_import.py", "an unrecognised purpose is assumed permitted",
     '        raise CsvValidationError(\n'
     '            "unknown purpose %r; allowed: live_order, material_calculation, "',
     '        return\n'
     '        raise CsvValidationError(\n'
     '            "unknown purpose %r; allowed: live_order, material_calculation, "'),
    ("market/csv_import.py", "an empty purpose is accepted",
     "        if not purpose or not isinstance(purpose, str):",
     "        if False:"),
    ("market/csv_import.py", "display is refused (a validator that refuses all)",
     '        if purpose == "display":\n'
     "            # Anything may be shown to a human ALONGSIDE ITS FINDINGS. A blocked",
     '        if False:\n'
     "            # Anything may be shown to a human ALONGSIDE ITS FINDINGS. A blocked"),
    ("market/csv_import.py", "is_blocked ignores BLOCKING findings",
     '        return bool(self.findings_at("BLOCKING"))',
     "        return False"),
    # 'if severity not in SEVERITIES:' appears TWICE (Finding.__init__ and
    # findings_at), so the bare pattern is ambiguous and the battery correctly
    # refuses to guess which one it would hit. Both are disambiguated by the
    # line that follows them. A skip here is not a non-event: an ambiguous
    # mutation silently tests nothing while appearing in the seeded count.
    ("market/csv_import.py", "findings_at accepts an unknown severity",
     '        if severity not in SEVERITIES:\n'
     '            raise CsvValidationError("unknown severity %r" % (severity,))',
     '        if False:\n'
     '            raise CsvValidationError("unknown severity %r" % (severity,))'),
    ("market/csv_import.py", "findings_at ignores the severity asked for",
     "        return tuple(f for f in self.findings if f.severity == severity)",
     "        return tuple(self.findings)"),

    # --- immutability: evidence that can be edited is not evidence ---------
    ("market/csv_import.py", "a validated series becomes mutable",
     '    def __setattr__(self, name, value):\n'
     '        if getattr(self, "_frozen", False):\n'
     '            raise CsvValidationError(\n'
     '                "a validated series is immutable: refusing to set %r. Appending "',
     '    def __setattr__(self, name, value):\n'
     '        if False:\n'
     '            raise CsvValidationError(\n'
     '                "a validated series is immutable: refusing to set %r. Appending "'),
    ("market/csv_import.py", "series attributes become deletable",
     '    def __delattr__(self, name):\n'
     '        raise CsvValidationError(\n'
     '            "a validated series is immutable: refusing to delete %r" % (name,))',
     '    def __delattr__(self, name):\n'
     '        object.__delattr__(self, name)'),
    ("market/csv_import.py", "bars are exposed as a mutable list",
     "        self.bars = tuple(bars)",
     "        self.bars = list(bars)"),
    ("market/csv_import.py", "findings are exposed as a mutable list",
     "        self.findings = tuple(findings)",
     "        self.findings = list(findings)"),
    ("market/csv_import.py", "a finding becomes editable",
     '    def __setattr__(self, name, value):\n'
     '        if getattr(self, "_frozen", False):\n'
     '            raise CsvValidationError(\n'
     '                "findings are immutable: refusing to set %r',
     '    def __setattr__(self, name, value):\n'
     '        if False:\n'
     '            raise CsvValidationError(\n'
     '                "findings are immutable: refusing to set %r'),
    ("market/csv_import.py", "a finding accepts an unknown validation name",
     "        if validation not in VALIDATIONS:",
     "        if False:"),
    ("market/csv_import.py", "a finding accepts an unknown severity",
     '        if severity not in SEVERITIES:\n'
     '            raise CsvValidationError(\n'
     '                "unknown severity %r; allowed: %s"',
     '        if False:\n'
     '            raise CsvValidationError(\n'
     '                "unknown severity %r; allowed: %s"'),
    ("market/csv_import.py", "a finding needs no message",
     "        if not message:",
     "        if False:"),

    # --- quote_from_series: the laundering point ---------------------------
    ("market/csv_import.py", "a Quote can be built from a blocked series",
     '    series.assert_usable_for("material_calculation")',
     "    pass"),
    ("market/csv_import.py", "a non-series is passed straight through",
     "    if not isinstance(series, CsvSeries):",
     "    if False:"),
    ("market/csv_import.py", "a bar with no close becomes a Quote",
     '    if bar.get("close") is None:',
     "    if False:"),
    ("market/csv_import.py", "a CSV price is relabelled REALTIME",
     '        delay_status="END_OF_DAY", market_status="UNKNOWN",',
     '        delay_status="REALTIME", market_status="OPEN",'),
    ("market/csv_import.py", "a CSV price is relabelled as exchange-trusted",
     '        origin="CSV_EXPORT", last=bar.get("close"),',
     '        origin="PROVIDER_API", last=bar.get("close"),'),
    ("market/csv_import.py", "a CSV price claims a verified trust level",
     '        corporate_action_status="UNKNOWN", trust_level="UNVERIFIED",',
     '        corporate_action_status="UNKNOWN", trust_level="EXCHANGE",'),
    ("market/csv_import.py", "the index type check is dropped (bool becomes 1)",
     "    if not isinstance(index, int) or isinstance(index, bool):",
     "    if not isinstance(index, int):"),
    ("market/csv_import.py", "the provenance note loses the file hash",
     '        note="bar %d of %d from %s (sha256 %s)"',
     '        note="bar %d of %d from %s (%.0s)"'),

    # --- the audit surface -------------------------------------------------
    ("market/csv_import.py", "the file hash is no longer recorded",
     '    add("file_hash", "ADVISORY",',
     '    if False: add("file_hash", "ADVISORY",'),
    ("market/csv_import.py", "the hash is computed over the first block only",
     "            if not chunk:\n                break",
     "            break"),
    ("market/csv_import.py", "coverage period is no longer recorded",
     '    add("coverage_period", "ADVISORY",',
     '    if False: add("coverage_period", "ADVISORY",'),
    ("market/csv_import.py", "a validation silently drops out of the declared set",
     '    "adjustment_status", "coverage_period", "currency")',
     '    "adjustment_status", "coverage_period")'),
    ("market/csv_import.py", "to_dict dumps every bar into the audit record",
     '        d = {k: getattr(self, k) for k in self._FIELDS\n'
     '             if k not in ("bars", "findings")}',
     "        d = {k: getattr(self, k) for k in self._FIELDS}"),
    ("market/csv_import.py", "the manifest claims a provider licence is needed",
     '            "needs_data_licence": False,',
     '            "needs_data_licence": True,'),
    ("market/csv_import.py", "the manifest drops the TradingView caveat",
     '            "licence_note": "A user\'s own export needs no provider licence, but "',
     '            "licence_note": "no licence considerations apply. " or "A user\'s own export needs no provider licence, but "'),
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
    # probe_csv_import.py exits non-zero on its own, but belt and braces: a probe
    # that starts allowing things, crashing, recording no finding, or recording a
    # false reason must not read as a passing oracle.
    for marker in ("** ALLOWED", "!! CRASHED", "** NO FINDING",
                   "** WRONG SEVERITY", "** NOT ENFORCED", "** FALSE REASON"):
        if marker in out:
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

    backup = tempfile.mkdtemp(prefix="csv_orig_")
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
                # This check exists because I have written one six times.
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
