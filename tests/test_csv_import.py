"""
Tests for the CSV ingestion layer (SS.7.1 Level 2).

Written after probe_csv_import.py found six defects on the module's first
execution. The probe proves the attacks I thought of; this suite is what a
mutation battery can then try to defeat.

Two design decisions in this suite, both forced by earlier mistakes:

1. REFUSALS ARE ASSERTED BY MESSAGE, not just by type. Twice this session a
   test that asserted only *that* a function raised could not tell two guards
   apart, which left later guards entirely unexecuted -- three of five broker
   guards, and assert_provider_usable's third guard. A CsvValidationError from
   the timezone check and one from the currency check are the same type and
   completely different facts, so every refusal here names the guard it expects.

2. FINDINGS ARE ASSERTED AS (validation, severity) PAIRS AND FOR ENFORCEMENT.
   parse_csv returns a report, so a finding recorded at ADVISORY when it should
   be MATERIAL changes nothing about the type raised and everything about
   whether the file can price a calculation. Severity is the behaviour here.

Run:  python3 tests/test_csv_import.py
"""

import datetime
import operator
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from _harness import check, check_raises, check_true, section, summary

from market import csv_import as ci
from market.quotes import MarketDataError

NOW = datetime.datetime.now(datetime.timezone.utc)
TMP = tempfile.mkdtemp(prefix="marfin_csvtest_")

HEADER = "timestamp,open,high,low,close,volume\n"


def write(name, text):
    path = os.path.join(TMP, name)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    return path


def rows(n=6, step_days=1, start=None):
    base = start or datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)
    out = []
    for i in range(n):
        d = base + datetime.timedelta(days=i * step_days)
        px = 100.0 + i
        out.append("%s,%.2f,%.2f,%.2f,%.2f,%d"
                   % (d.isoformat(), px, px + 1, px - 1, px + 0.5, 1000 + i))
    return "\n".join(out) + "\n"


def kw(**over):
    """Everything declared, so each test introduces exactly one problem."""
    d = dict(expected_symbol="AAPL", expected_exchange="NASDAQ",
             expected_currency="USD", expected_timeframe="1d",
             declared_timezone="UTC", declared_adjustment_status="ADJUSTED",
             declared_exported_at=NOW - datetime.timedelta(hours=1))
    d.update(over)
    return d


def parse(name, body, **over):
    return ci.parse_csv(write(name, body), **kw(**over))


def why(fn):
    """The refusal text, so a test can assert WHICH guard fired."""
    try:
        fn()
    except (MarketDataError, ci.CsvValidationError) as exc:
        return str(exc)
    except Exception as exc:            # noqa: BLE001
        return "WRONG-EXCEPTION-TYPE %s: %s" % (type(exc).__name__, exc)
    return "DID-NOT-RAISE"


def has(series, validation, severity):
    return any(f.validation == validation and f.severity == severity
               for f in series.findings)


def clean():
    return parse("clean_%d.csv" % len(os.listdir(TMP)), HEADER + rows(10))


# ---------------------------------------------------------------------------
section("SS.7.1 Level 2: all fourteen validations are declared, as data")

check("fourteen validations", len(ci.VALIDATIONS), 14)
for name in ("file_hash", "export_time", "symbol", "exchange", "timeframe",
             "timezone", "columns", "indicator_columns", "missing_bars",
             "duplicates", "ordering", "adjustment_status", "coverage_period",
             "currency"):
    check_true("SS.7.1 lists %r" % name, name in ci.VALIDATIONS)
check("no validation is duplicated", len(set(ci.VALIDATIONS)), 14)
check("manifest reports all fourteen", len(ci.manifest()["validations"]), 14)
check_true("manifest names the level",
           "Level 2" in ci.manifest()["level"])
# A CSV the user exported themselves needs no PROVIDER licence -- but the
# underlying terms still bind, which is the whole TradingView finding.
check_true("no provider licence needed for a user's own export",
           ci.manifest()["needs_data_licence"] is False)
check_true("but the underlying terms are still recorded",
           "TradingView" in ci.manifest()["licence_note"])

check("three severities", len(ci.SEVERITIES), 3)
check_true("BLOCKING is a severity", "BLOCKING" in ci.SEVERITIES)
check_true("MATERIAL is a severity", "MATERIAL" in ci.SEVERITIES)
check_true("ADVISORY is a severity", "ADVISORY" in ci.SEVERITIES)


# ---------------------------------------------------------------------------
section("a Finding is a record, and it refuses to be anything else")

f = ci.Finding("columns", "MATERIAL", "a message", "detail")
check_true("finding keeps its validation", f.validation == "columns")
check_true("finding keeps its severity", f.severity == "MATERIAL")
check_true("finding keeps its message", f.message == "a message")
check_true("unknown validation refused",
           "unknown validation" in why(lambda: ci.Finding("vibes", "MATERIAL", "m")))
check_true("unknown severity refused",
           "unknown severity" in why(lambda: ci.Finding("columns", "SEVERE", "m")))
check_true("a finding must carry a message",
           "must carry a message" in why(lambda: ci.Finding("columns", "MATERIAL", "")))
check_raises("severity cannot be rewritten",
             lambda: setattr(f, "severity", "ADVISORY"))
check_raises("validation cannot be rewritten",
             lambda: setattr(f, "validation", "symbol"))
check_raises("a finding cannot be deleted", lambda: delattr(f, "message"))
check_true("to_dict round-trips the severity",
           ci.Finding("symbol", "BLOCKING", "m").to_dict()["severity"] == "BLOCKING")


# ---------------------------------------------------------------------------
section("structural failures RAISE -- a report about an unparseable file "
        "is a report about nothing")

check_true("no such file",
           "no such CSV file" in why(lambda: ci.parse_csv(os.path.join(TMP, "no.csv"))))
check_true("empty path", "non-empty string" in why(lambda: ci.parse_csv("")))
check_true("None path", "non-empty string" in why(lambda: ci.parse_csv(None)))
check_true("a directory is not a CSV",
           "no such CSV file" in why(lambda: ci.parse_csv(TMP)))
check_true("zero-byte file",
           "is empty" in why(lambda: ci.parse_csv(write("z.csv", ""))))
check_true("header but no rows",
           "no data rows" in why(lambda: ci.parse_csv(write("h.csv", HEADER))))
check_true("timestamp column is required",
           "lacks required column" in why(
               lambda: ci.parse_csv(write("nt.csv", "open,close\n1,2\n"))))
check_true("close column is required",
           "lacks required column" in why(
               lambda: ci.parse_csv(write("nc.csv", "timestamp,open\n2024-01-01,2\n"))))

# Defect 5 from the probe: an all-ragged file was reported as "no data rows".
# A user told their file is empty when its columns do not line up will not fix
# it, so the message must name the real cause.
_ragged_msg = why(lambda: ci.parse_csv(
    write("ar.csv", HEADER + "2024-01-01T00:00:00+00:00,1\n"
                             "2024-01-02T00:00:00+00:00,2\n"), **kw()))
check_true("all-ragged file names raggedness, not emptiness",
           "ragged" in _ragged_msg)
check_true("all-ragged file explicitly denies being empty",
           "not empty" in _ragged_msg)


# ---------------------------------------------------------------------------
section("numeric pathologies: a bad number is a stop, an absent one is a finding")

for label, cell in (("NaN", "NaN"), ("nan", "nan"), ("NAN", "NAN"),
                    ("+nan", "+nan")):
    # Defect 2: 'NaN' and 'nan' were swallowed as nulls before float() ran, so
    # the NaN guard was reachable only via '+nan' while the docstring claimed
    # otherwise. Each spelling is asserted separately -- asserting only one
    # would have left the defect in place.
    check_true("%s is refused as NaN" % label,
               "is NaN" in why(lambda c=cell: ci.parse_csv(
                   write("nan_%s.csv" % label, "timestamp,close\n"
                         "2024-01-01T00:00:00+00:00,%s\n" % c), **kw())))
for label, cell in (("inf", "inf"), ("-Infinity", "-Infinity")):
    check_true("%s is refused as infinite" % label,
               "infinite" in why(lambda c=cell: ci.parse_csv(
                   write("inf_%s.csv" % abs(hash(label)), "timestamp,close\n"
                         "2024-01-01T00:00:00+00:00,%s\n" % c), **kw())))
check_true("text is not a number",
           "not a number" in why(lambda: ci.parse_csv(
               write("txt.csv", "timestamp,close\n"
                     "2024-01-01T00:00:00+00:00,probably 100\n"), **kw())))

# Defect 3: unconditional comma-stripping turned '1,5' into 15.0. The
# ambiguous forms must be refused; the legitimate US thousands form must not.
for label, cell in (("1,5", '"1,5"'), ("1.234,56", '"1.234,56"')):
    check_true("%s refused as locale-ambiguous" % label,
               "ambiguous" in why(lambda c=cell: ci.parse_csv(
                   write("loc_%s.csv" % abs(hash(label)),
                         "timestamp,close\n2024-01-01T00:00:00+00:00,%s\n"
                         "2024-01-02T00:00:00+00:00,101\n" % c), **kw())))
_thou = parse("thou.csv", 'timestamp,close\n2024-01-01T00:00:00+00:00,"1,234.5"\n'
                          '2024-01-02T00:00:00+00:00,"1,235.5"\n')
check("US thousands separator still parses", _thou.bars[0]["close"], 1234.5)
_grp = parse("grp.csv", 'timestamp,close\n2024-01-01T00:00:00+00:00,"12,345,678"\n'
                        '2024-01-02T00:00:00+00:00,101\n')
check("repeated commas are thousands groups", _grp.bars[0]["close"], 12345678.0)

# Defect 1, the worst one: blank cells recorded NOTHING, so a file whose every
# close was empty was usable for a material calculation.
_allnull = parse("allnull.csv", "timestamp,close\n" +
                 "".join("2024-01-0%dT00:00:00+00:00,\n" % i for i in range(1, 6)))
check_true("all-blank close is BLOCKING", has(_allnull, "columns", "BLOCKING"))
check_true("all-blank close blocks the file", _allnull.is_blocked)
check_true("all-blank close names the column",
           any("'close'" in f.message for f in _allnull.findings_at("BLOCKING")))
check_true("all-blank close is refused for calculation",
           "BLOCKING" in why(lambda: _allnull.assert_usable_for("material_calculation")))
_somenull = parse("somenull.csv", "timestamp,close\n2024-01-01T00:00:00+00:00,\n" +
                  "".join("2024-01-0%dT00:00:00+00:00,10%d\n" % (i, i)
                          for i in range(2, 6)))
check_true("one blank close is MATERIAL", has(_somenull, "columns", "MATERIAL"))
check_true("one blank close still blocks a calculation",
           "MATERIAL" in why(lambda: _somenull.assert_usable_for("material_calculation")))
check_true("one blank close does NOT block display",
           why(lambda: _somenull.assert_usable_for("display")) == "DID-NOT-RAISE")
_novol = parse("novol.csv", "timestamp,close,volume\n" +
               "".join("2024-01-0%dT00:00:00+00:00,10%d,N/A\n" % (i, i)
                       for i in range(1, 6)))
check_true("an all-N/A volume column is reported",
           has(_novol, "columns", "MATERIAL"))
check_true("N/A is treated as absent, not as text",
           _novol.bars[0]["volume"] is None)
# A branch nobody executes cannot be defended. _novol above uses an ALL-N/A
# column, which takes the `share >= 0.5` branch, so the `else` branch -- a
# non-close column blank in FEWER than half its bars -- was never exercised and
# a mutation downgrading it to ADVISORY survived a suite that passed. MEASURED:
# volume blank in 1 of 5 bars (20%) reaches that branch and is MATERIAL.
_partvol = parse("partvol.csv", "timestamp,close,volume\n" +
                 "".join("2024-01-0%dT00:00:00+00:00,10%d,%s\n"
                         % (i, i, "" if i == 3 else str(1000 + i))
                         for i in range(1, 6)))
check_true("a non-close column blank in a MINORITY of bars is MATERIAL",
           has(_partvol, "columns", "MATERIAL"))
check_true("it is NOT downgraded to ADVISORY",
           not has(_partvol, "columns", "ADVISORY"))
check_true("the finding reports the share it measured",
           any("1 of 5 bar(s) (20%)" in f.message
               for f in _partvol.findings_at("MATERIAL")))
# Severity IS the behaviour: ADVISORY would leave this file able to price a
# calculation, which is the whole point of the distinction.
check_true("a minority-blank column still blocks a calculation",
           "MATERIAL" in why(
               lambda: _partvol.assert_usable_for("material_calculation")))
check_true("one blank volume does not BLOCK the file outright",
           _partvol.is_blocked is False)
for sentinel in ("N/A", "NA", "NULL", "NONE", "-", "--", "#N/A", ""):
    check_true("%r counts as absent" % sentinel,
               ci._parse_number(sentinel, "volume", 2) == (None, True))
check_true("_parse_number returns a (value, was_null) pair",
           ci._parse_number("100.5", "close", 2) == (100.5, False))


# ---------------------------------------------------------------------------
section("timestamps: naive is not silently stamped UTC")

_naive = parse("naive.csv", "timestamp,close\n" +
               "".join("2024-01-0%d,10%d\n" % (i, i) for i in range(1, 6)),
               declared_timezone=None)
check_true("naive timestamps with no declared tz are BLOCKING",
           has(_naive, "timezone", "BLOCKING"))
check_true("the refusal names the timezone check",
           "timezone" in why(lambda: _naive.assert_usable_for("material_calculation")))
_naive_ok = parse("naive2.csv", "timestamp,close\n" +
                  "".join("2024-01-0%d,10%d\n" % (i, i) for i in range(1, 6)),
                  declared_timezone="America/New_York")
check_true("a declared tz downgrades it to ADVISORY",
           has(_naive_ok, "timezone", "ADVISORY"))
check_true("declaring a tz does not make it BLOCKING",
           not has(_naive_ok, "timezone", "BLOCKING"))
check_true("the advisory says it rests on the user's word",
           any("user's word" in f.message
               for f in _naive_ok.findings_at("ADVISORY")))
check_true("empty timestamp refused",
           "empty timestamp" in why(lambda: ci.parse_csv(
               write("ets.csv", "timestamp,close\n,100\n"), **kw())))
check_true("garbage timestamp refused",
           "unparseable" in why(lambda: ci.parse_csv(
               write("gts.csv", "timestamp,close\nyesterday,100\n"), **kw())))
# Epoch seconds are a supported export format (several charting tools emit
# them), so they must parse AND come out timezone-aware.
_ep = parse("ep.csv", "timestamp,close\n1704067200,100\n1704153600,101\n"
                      "1704240000,102\n")
check("epoch seconds parse to the right year", _ep.bars[0]["timestamp"].year, 2024)
check_true("epoch seconds are timezone-aware",
           _ep.bars[0]["timestamp"].tzinfo is not None)
check_true("epoch seconds are not counted as naive",
           not has(_ep, "timezone", "BLOCKING"))


# ---------------------------------------------------------------------------
section("ordering, duplicates and gaps")

_desc = parse("desc.csv", HEADER + "\n".join(
    reversed(rows().strip().split("\n"))) + "\n")
check_true("descending order is MATERIAL", has(_desc, "ordering", "MATERIAL"))
check_true("the finding says DESCENDING",
           any("DESCENDING" in f.message for f in _desc.findings))
# The module deliberately does not reorder the user's file. A validator that
# silently fixes the input hides the defect and changes the bytes the hash
# describes.
check_true("descending rows are NOT silently reordered",
           _desc.bars[0]["timestamp"] > _desc.bars[-1]["timestamp"])
check_true("descending order blocks a calculation",
           "MATERIAL" in why(lambda: _desc.assert_usable_for("material_calculation")))

_unord = parse("unord.csv", HEADER +
               "2024-01-03T00:00:00+00:00,1,2,0.5,1.5,10\n"
               "2024-01-01T00:00:00+00:00,1,2,0.5,1.5,10\n"
               "2024-01-05T00:00:00+00:00,1,2,0.5,1.5,10\n"
               "2024-01-02T00:00:00+00:00,1,2,0.5,1.5,10\n")
check_true("neither ascending nor descending is BLOCKING",
           has(_unord, "ordering", "BLOCKING"))
check_true("an ascending file records no ordering finding",
           not any(f.validation == "ordering" for f in clean().findings))

_dup = parse("dup.csv", HEADER + rows(3) + rows(3).split("\n")[0] + "\n")
check_true("a duplicated timestamp is MATERIAL",
           has(_dup, "duplicates", "MATERIAL"))
check_true("the duplicate finding names a timestamp",
           any("2024-01-01" in f.message for f in _dup.findings_at("MATERIAL")))
check_true("a clean file records no duplicate finding",
           not any(f.validation == "duplicates" for f in clean().findings))

# Gaps are ADVISORY on purpose: for daily bars every weekend is a gap, and a
# validator that cries wolf on normal market closure teaches its user to ignore
# it. If this were MATERIAL, almost no real daily export could be calculated on.
_gap = parse("gap.csv", HEADER +
             "2024-01-01T00:00:00+00:00,1,2,0.5,1.5,10\n"
             "2024-01-02T00:00:00+00:00,1,2,0.5,1.5,10\n"
             "2024-01-20T00:00:00+00:00,1,2,0.5,1.5,10\n")
check_true("a gap is ADVISORY, not MATERIAL",
           has(_gap, "missing_bars", "ADVISORY"))
check_true("a gap does NOT block a calculation",
           why(lambda: _gap.assert_usable_for("material_calculation")) == "DID-NOT-RAISE")
check_true("the gap finding admits it does not know the trading calendar",
           any("calendar" in f.detail for f in _gap.findings_at("ADVISORY")))
_nogap = parse("nogap.csv", HEADER + rows(5))
check_true("consecutive daily bars record no gap",
           not any(f.validation == "missing_bars" for f in _nogap.findings))

# Defect 4: a two-bar file with a CORRECTLY declared timeframe used to report
# "gap detection did not run: timeframe is 1d" -- a self-contradicting sentence
# headed for an audit record as the stated reason.
_two = parse("two.csv", HEADER + rows(2))
_mb = [f for f in _two.findings if f.validation == "missing_bars"]
check_true("a 2-bar file does not blame its declared timeframe",
           not any("timeframe is 1d" in f.message for f in _mb))
check_true("2 bars is enough for gap detection to run", not _mb)
_one = parse("one.csv", HEADER + rows(1))
check_true("a 1-bar file says the reason is the bar count",
           any("only 1 bar" in f.message
               for f in _one.findings if f.validation == "missing_bars"))
_notf = parse("notf.csv", HEADER + rows(5), expected_timeframe=None)
check_true("no timeframe means gap detection did not run",
           has(_notf, "missing_bars", "MATERIAL"))
check_true("that finding blames the timeframe, correctly this time",
           any("no usable timeframe" in f.message
               for f in _notf.findings if f.validation == "missing_bars"))


# ---------------------------------------------------------------------------
section("the declared timeframe is CROSS-CHECKED, not taken on trust")

# A declaration nothing verifies is the same decoration problem as an unenforced
# licence field -- the defect Phase 3 found in sources.py and this session found
# twice more.
_fine = parse("fine.csv", HEADER + "\n".join(
    "%s,100,101,99,100.5,10"
    % (datetime.datetime(2024, 1, 2, 14, 30, tzinfo=datetime.timezone.utc)
       + datetime.timedelta(minutes=i)).isoformat() for i in range(8)) + "\n")
check_true("1m bars declared as 1d is BLOCKING",
           has(_fine, "timeframe", "BLOCKING"))
check_true("the finding states the measured gap",
           any("smallest gap" in f.message for f in _fine.findings_at("BLOCKING")))
check_true("1m-as-1d blocks a calculation",
           "BLOCKING" in why(lambda: _fine.assert_usable_for("material_calculation")))
# Two bars is the real minimum for the cross-check: one interval already
# contradicts a wrong declaration, and requiring three left a two-bar
# minute-data file declared as daily entirely unchecked.
_fine2 = parse("fine2.csv", HEADER +
               "2024-01-02T14:30:00+00:00,100,101,99,100.5,10\n"
               "2024-01-02T14:31:00+00:00,100,101,99,100.5,10\n")
check_true("even 2 bars catch a wrong timeframe",
           has(_fine2, "timeframe", "BLOCKING"))
# A threshold test must sit NEAR the boundary, not deep inside it. The 1m
# fixtures above have 60s gaps, and 60 < 86.4, so they die under a tolerance
# mutated all the way from step*0.5 to step*0.001 -- the mutation survived.
# MEASURED: hourly bars (3600s) declared 1d are caught at 0.5 (< 43200s) but
# NOT at 0.001 (< 86.4s), so this fixture discriminates and the 1m ones cannot.
# Hourly-as-daily is also the realistic version of the mistake: a 24x error in
# every annualization, from a file that looks entirely ordinary.
_hourly = parse("hourly.csv", HEADER + "".join(
    "%s,100,101,99,100.5,10\n"
    % (datetime.datetime(2024, 1, 2, 9, tzinfo=datetime.timezone.utc)
       + datetime.timedelta(hours=i)).isoformat() for i in range(6)))
check_true("HOURLY bars declared 1d is BLOCKING (the near-boundary case)",
           has(_hourly, "timeframe", "BLOCKING"))
check_true("the finding reports the measured 3600s gap",
           any("3600s" in f.message for f in _hourly.findings_at("BLOCKING")))
check_true("hourly-as-daily blocks a calculation",
           "BLOCKING" in why(
               lambda: _hourly.assert_usable_for("material_calculation")))
# The tolerance is a ratio, so state both sides of it as arithmetic: this is the
# fact that makes the fixture above discriminating rather than lucky.
check_true("3600s is inside step*0.5 for 1d",
           3600 < ci.TIMEFRAME_SECONDS["1d"] * 0.5)
check_true("3600s is OUTSIDE step*0.001 for 1d",
           not 3600 < ci.TIMEFRAME_SECONDS["1d"] * 0.001)
check_true("a correctly declared timeframe records no finding",
           not any(f.validation == "timeframe" for f in clean().findings))
_unknown_tf = parse("utf.csv", HEADER + rows(5), expected_timeframe="fortnightly")
check_true("an unknown timeframe is MATERIAL, not guessed",
           has(_unknown_tf, "timeframe", "MATERIAL"))
check_true("the finding lists the timeframes it knows",
           any("1d" in f.detail for f in _unknown_tf.findings_at("MATERIAL")))
check("eight known timeframes", len(ci.TIMEFRAME_SECONDS), 8)
check("1d is 86400 seconds", ci.TIMEFRAME_SECONDS["1d"], 86400)
check("1w is 604800 seconds", ci.TIMEFRAME_SECONDS["1w"], 604800)


# ---------------------------------------------------------------------------
section("columns: an adjusted close is a DIFFERENT NUMBER, not a substitute")

check_true("'adj close' maps to adj_close",
           ci._CANONICAL_COLUMNS["adj close"] == "adj_close")
check_true("'adjusted close' maps to adj_close",
           ci._CANONICAL_COLUMNS["adjusted close"] == "adj_close")
# This is the assertion that matters: mapping adj_close onto close is exactly
# what makes an adjusted/unadjusted comparison look valid.
for name in ("adj close", "adjclose", "adjusted close", "adj_close"):
    check_true("%r is NOT mapped to close" % name,
               ci._CANONICAL_COLUMNS[name] != "close")
check_true("'vol' maps to volume", ci._CANONICAL_COLUMNS["vol"] == "volume")
check_true("'date' maps to timestamp", ci._CANONICAL_COLUMNS["date"] == "timestamp")

_both = parse("both.csv", "timestamp,close,adj close\n" +
              "".join("2024-01-0%dT00:00:00+00:00,10%d,9%d\n" % (i, i, i)
                      for i in range(1, 6)))
check_true("close and adj close together is ADVISORY only",
           has(_both, "columns", "ADVISORY"))
check_true("bars use close, not adj_close", _both.bars[0]["close"] == 101.0)
check_true("adj_close is preserved separately", _both.bars[0]["adj_close"] == 91.0)
check_true("having both does not block a calculation",
           why(lambda: _both.assert_usable_for("material_calculation")) == "DID-NOT-RAISE")

_dupcol = parse("dupcol.csv", "timestamp,close,Close\n"
                "2024-01-01T00:00:00+00:00,100,200\n"
                "2024-01-02T00:00:00+00:00,101,201\n")
check_true("two columns mapping to close is BLOCKING",
           has(_dupcol, "columns", "BLOCKING"))
check_true("the finding says which name collided",
           any("already appeared" in f.message for f in _dupcol.findings_at("BLOCKING")))

_ind = parse("ind.csv", "timestamp,close,RSI,MACD_signal\n" +
             "".join("2024-01-0%dT00:00:00+00:00,10%d,55.2,0.31\n" % (i, i)
                     for i in range(1, 6)))
check_true("unrecognised columns become indicator columns, not price fields",
           _ind.indicator_columns == ("RSI", "MACD_signal"))
check_true("indicator columns are MATERIAL",
           has(_ind, "indicator_columns", "MATERIAL"))
check_true("the finding says to recompute from OHLCV",
           any("Recompute" in f.detail for f in _ind.findings_at("MATERIAL")))
check_true("indicator values are kept as text, not silently floated",
           isinstance(_ind.bars[0]["RSI"], str))
check_true("a clean OHLCV file has no indicator columns",
           clean().indicator_columns == ())

_ragged = parse("ragged.csv", HEADER + rows(4) +
                "2024-02-01T00:00:00+00:00,1,2\n")
check_true("a ragged row is MATERIAL", has(_ragged, "columns", "MATERIAL"))
check("a ragged row is dropped, not padded", len(_ragged.bars), 4)


# ---------------------------------------------------------------------------
section("what the USER declared is required -- the file is not asked to "
        "identify itself")

# The opposite of inferring the symbol from the filename, which is how a EURUSD
# export becomes an AAPL series.
for field, arg in (("symbol", "expected_symbol"),
                   ("exchange", "expected_exchange"),
                   ("currency", "expected_currency")):
    s = parse("miss_%s.csv" % field, HEADER + rows(5), **{arg: None})
    check_true("no %s declared is BLOCKING" % field, has(s, field, "BLOCKING"))
    check_true("the %s refusal names %s" % (field, field),
               field in why(lambda x=s: x.assert_usable_for("material_calculation")))
    check_true("%s absence blocks the file" % field, s.is_blocked)

_adj = parse("adj.csv", HEADER + rows(5), declared_adjustment_status="UNKNOWN")
check_true("UNKNOWN adjustment status is MATERIAL",
           has(_adj, "adjustment_status", "MATERIAL"))
check_true("the finding explains the comparison failure",
           any("unadjusted" in f.detail for f in _adj.findings_at("MATERIAL")))
check_true("a stated adjustment status records nothing",
           not any(f.validation == "adjustment_status" for f in clean().findings))
check_true("an unknown adjustment status value is refused outright",
           "adjustment_status must be one of" in why(
               lambda: parse("bad_adj.csv", HEADER + rows(3),
                             declared_adjustment_status="MOSTLY")))
check_true("an unknown origin is refused outright",
           "origin must be one of" in why(
               lambda: parse("bad_org.csv", HEADER + rows(3), origin="VIBES")))


# ---------------------------------------------------------------------------
section("export time: stale data's quietest entry point")

_noexp = parse("noexp.csv", HEADER + rows(5), declared_exported_at=None)
check_true("no export time is MATERIAL", has(_noexp, "export_time", "MATERIAL"))
# The filesystem mtime is deliberately NOT used: copying a file rewrites it, so
# mtime would silently make a year-old export look minutes old.
check_true("mtime is explicitly rejected as a substitute",
           any("mtime" in f.detail for f in _noexp.findings_at("MATERIAL")))
_future = parse("fut.csv", HEADER + rows(5),
                declared_exported_at=NOW + datetime.timedelta(days=30))
check_true("a future export time is BLOCKING",
           has(_future, "export_time", "BLOCKING"))
check_true("the finding says FUTURE",
           any("FUTURE" in f.message for f in _future.findings_at("BLOCKING")))
_old = parse("old.csv", HEADER + rows(5),
             declared_exported_at=NOW - datetime.timedelta(days=120))
check_true("a months-old export is MATERIAL", has(_old, "export_time", "MATERIAL"))
check_true("the finding states the age and the threshold",
           any("threshold" in f.message for f in _old.findings_at("MATERIAL")))
check_true("a fresh export records nothing",
           not any(f.validation == "export_time" for f in clean().findings))
# The threshold is a parameter, so a caller doing long-horizon work can widen
# it deliberately rather than being forced to ignore the finding.
_wide = parse("wide.csv", HEADER + rows(5),
              declared_exported_at=NOW - datetime.timedelta(days=120),
              max_export_age_days=365)
check_true("a widened threshold is honoured",
           not any(f.validation == "export_time" for f in _wide.findings))
# A naive declared export time must not crash against an aware read time.
_naive_exp = parse("nexp.csv", HEADER + rows(5),
                   declared_exported_at=datetime.datetime(2024, 1, 1, 12, 0))
check_true("a naive declared export time is handled, not crashed",
           isinstance(_naive_exp, ci.CsvSeries))


# ---------------------------------------------------------------------------
section("file hash and coverage period are recorded for the audit trail")

c1 = parse("h1.csv", HEADER + rows(5))
c2 = parse("h2.csv", HEADER + rows(5))
c3 = parse("h3.csv", HEADER + rows(6))
check("sha256 is 64 hex characters", len(c1.file_sha256), 64)
check_true("identical bytes hash identically", c1.file_sha256 == c2.file_sha256)
check_true("different bytes hash differently", c1.file_sha256 != c3.file_sha256)
check_true("the hash is recorded as a finding", has(c1, "file_hash", "ADVISORY"))
check_true("the hash finding explains re-import detection",
           any("re-import" in f.detail for f in c1.findings_at("ADVISORY")))
check_true("coverage period is recorded", has(c1, "coverage_period", "ADVISORY"))
check_true("coverage names both endpoints",
           any("2024-01-01" in f.message and "2024-01-05" in f.message
               for f in c1.findings))
check_true("coverage explains that a partial answer would not look partial",
           any("partial" in f.detail for f in c1.findings_at("ADVISORY")))
check("bar count matches the file", len(c1.bars), 5)
check("n_bytes is recorded", c1.n_bytes, os.path.getsize(c1.path))


# ---------------------------------------------------------------------------
section("a validated series is immutable, including its bars")

s = clean()
check_raises("bars cannot be replaced",
             lambda: setattr(s, "bars", ()))
check_raises("the hash cannot be rewritten",
             lambda: setattr(s, "file_sha256", "0" * 64))
check_raises("findings cannot be replaced",
             lambda: setattr(s, "findings", ()))
check_raises("the symbol cannot be rewritten",
             lambda: setattr(s, "symbol", "TSLA"))
check_raises("attributes cannot be deleted",
             lambda: delattr(s, "bars"))
# operator.setitem, not tuple.__setitem__: the dunder does not exist on a tuple,
# so that form raises AttributeError -- a CRASH by this project's convention,
# which check_raises correctly refuses to accept as a refusal.
check_raises("a bar cannot be assigned into the tuple",
             lambda: operator.setitem(s.bars, 0, {}), exc=(TypeError,))
check_raises("a finding cannot be deleted from the tuple",
             lambda: operator.delitem(s.findings, 0), exc=(TypeError,))
check_true("bars is a tuple, not a list", isinstance(s.bars, tuple))
check_true("findings is a tuple, not a list", isinstance(s.findings, tuple))
check_true("the refusal explains WHY immutability matters here",
           "coverage period" in why(lambda: setattr(s, "bars", ())))


# ---------------------------------------------------------------------------
section("assert_usable_for: a CSV may NEVER price a live order")

# Unconditional, not findings-dependent: an export is historical by
# construction. Asserted on the CLEANEST possible file, because a refusal that
# only fires on defective files would be no protection at all.
_perfect = clean()
check_true("the cleanest possible file still cannot price a live order",
           "may never price a live order" in why(
               lambda: _perfect.assert_usable_for("live_order")))
check_true("the refusal says it is historical by construction",
           "historical by construction" in why(
               lambda: _perfect.assert_usable_for("live_order")))
check_true("it directs the caller to the broker",
           "broker" in why(lambda: _perfect.assert_usable_for("live_order")))
check_true("a clean file IS usable for a material calculation",
           why(lambda: _perfect.assert_usable_for("material_calculation"))
           == "DID-NOT-RAISE")
check_true("a clean file IS displayable",
           why(lambda: _perfect.assert_usable_for("display")) == "DID-NOT-RAISE")
check_true("an unrecognised purpose is NOT assumed permitted",
           "unknown purpose" in why(lambda: _perfect.assert_usable_for("hedging")))
check_true("the refusal lists the permitted purposes",
           "material_calculation" in why(
               lambda: _perfect.assert_usable_for("hedging")))
check_true("empty purpose refused",
           "non-empty string" in why(lambda: _perfect.assert_usable_for("")))
check_true("None purpose refused",
           "non-empty string" in why(lambda: _perfect.assert_usable_for(None)))
check_true("a non-string purpose refused",
           "non-empty string" in why(lambda: _perfect.assert_usable_for(42)))
# A blocked file remains displayable: showing it WITH its findings is better
# than refusing, which would leave the user with nothing and no explanation.
_blocked = parse("blk.csv", HEADER + rows(5), expected_symbol=None)
check_true("a BLOCKED file is still displayable",
           why(lambda: _blocked.assert_usable_for("display")) == "DID-NOT-RAISE")
check_true("but not calculable", "BLOCKING" in why(
    lambda: _blocked.assert_usable_for("material_calculation")))
check_true("is_blocked is True for it", _blocked.is_blocked)
check_true("is_blocked is False for a clean file", not _perfect.is_blocked)
check_true("unknown severity queried is refused",
           "unknown severity" in why(lambda: _perfect.findings_at("CRITICAL")))
check("findings_at returns only that severity",
      len([f for f in _perfect.findings_at("ADVISORY") if f.severity != "ADVISORY"]), 0)


# ---------------------------------------------------------------------------
section("quote_from_series preserves provenance rather than laundering it")

q = ci.quote_from_series(_perfect)
check_true("origin is CSV_EXPORT", q.origin == "CSV_EXPORT")
check_true("trust level is UNVERIFIED", q.trust_level == "UNVERIFIED")
check_true("delay status is END_OF_DAY", q.delay_status == "END_OF_DAY")
check_true("market status is UNKNOWN", q.market_status == "UNKNOWN")
check_true("it is NOT live", q.is_live is False)
# CSV_EXPORT is deliberately NOT in WEAK_ORIGINS: a file the user exported from
# their own terminal outranks a number read off a screenshot. What must hold is
# that it is not live and not trusted.
check_true("a user's own export is not classed as weak", q.is_weak is False)
check_true("the quote still cannot price a live order",
           "not live" in why(lambda: q.assert_usable_for("live_order")))
check_true("the note carries the file hash",
           _perfect.file_sha256[:16] in q.note)
check_true("the licence field admits what it cannot establish",
           "cannot establish" in q.licence)
check_true("the provider names the file", "csv:" in q.provider)
check_true("last comes from the bar's close",
           q.last == _perfect.bars[-1]["close"])
q0 = ci.quote_from_series(_perfect, 0)
check_true("index 0 selects the first bar", q0.last == _perfect.bars[0]["close"])

# A blocked series must not become a Quote at all: that would be the laundering
# route, since a Quote carries no findings.
check_true("a BLOCKED series cannot become a Quote",
           "BLOCKING" in why(lambda: ci.quote_from_series(_blocked)))
check_true("a non-series is refused, not crashed on",
           "must be a CsvSeries" in why(lambda: ci.quote_from_series({"bars": []})))
check_true("None is refused", "must be a CsvSeries" in why(
    lambda: ci.quote_from_series(None)))
check_true("index past the end refused",
           "no bar at index" in why(lambda: ci.quote_from_series(_perfect, 999)))
check_true("a float index refused",
           "must be an integer" in why(lambda: ci.quote_from_series(_perfect, 1.5)))
check_true("a bool index refused",
           "must be an integer" in why(lambda: ci.quote_from_series(_perfect, True)))
# A bar with no close must be refused HERE, naming that cause, rather than
# relying on Quote's bid/ask/last guard to refuse for a reason a CSV user
# cannot act on.
_nullbar = parse("nb.csv", "timestamp,close\n2024-01-01T00:00:00+00:00,\n" +
                 "".join("2024-01-0%dT00:00:00+00:00,10%d\n" % (i, i)
                         for i in range(2, 6)))
check_true("a bar with no close cannot become a Quote",
           why(lambda: ci.quote_from_series(_nullbar, 0)) != "DID-NOT-RAISE")
# ...but the assertion above is the exact mistake this suite's docstring warns
# about, and the mutation battery proved it: through parse_csv the null-close
# guard is SHADOWED by assert_usable_for, which fires FIRST on the MATERIAL
# blank-cell finding. So `it raised` was satisfied by a different guard, and
# deleting the null-close guard entirely changed nothing observable.
check_true("the refusal above actually comes from the SHADOWING guard",
           "MATERIAL" in why(lambda: ci.quote_from_series(_nullbar, 0)))
# Reaching the shadowed guard needs a series that is clean EXCEPT for the null
# close -- which parse_csv cannot produce, because it always records the blank
# cell. So the series is hand-built, the same fixture technique that killed the
# shadowed broker guards in Phase 3A task 5. MEASURED: assert_usable_for passes
# (findings=()) and the null-close guard is then reached.
_synth = ci.CsvSeries(
    path=os.path.join(TMP, "synthetic-never-parsed.csv"),
    file_sha256="0" * 64, n_bytes=1, symbol="AAPL", exchange="NASDAQ",
    currency="USD", timeframe="1d", timezone="UTC",
    adjustment_status="ADJUSTED", exported_at=NOW, read_at=NOW,
    columns=("timestamp", "close"), indicator_columns=(),
    bars=({"timestamp": NOW, "close": None},), findings=(),
    origin="CSV_EXPORT",
    note="hand-built to reach a guard parse_csv shadows")
check_true("the synthetic series is otherwise usable (guard not shadowed)",
           why(lambda: _synth.assert_usable_for("material_calculation"))
           == "DID-NOT-RAISE")
# Asserted BY MESSAGE, per this suite's rule, so it can only be satisfied by the
# guard under test and no other.
check_true("a None close is refused by name, not by a neighbouring guard",
           "has no close value" in why(lambda: ci.quote_from_series(_synth, 0)))
check_true("the refusal explains why carrying the previous close is wrong",
           "invent an observation" in why(lambda: ci.quote_from_series(_synth, 0)))


# ---------------------------------------------------------------------------
section("the report itself is honest about what it does and does not say")

check_true("validations_run reports only what produced a finding",
           set(_perfect.validations_run) <= set(ci.VALIDATIONS))
check_true("a clean file produces fewer findings than validations",
           len(_perfect.validations_run) < 14)
d = _perfect.to_dict()
check_true("to_dict does not dump every bar", "bars" not in d)
check("to_dict reports the bar count", d["n_bars"], 10)
check_true("to_dict includes the hash", d["file_sha256"] == _perfect.file_sha256)
check_true("to_dict serialises findings as dicts",
           all(isinstance(x, dict) for x in d["findings"]))
check_true("repr names the instrument", "AAPL" in repr(_perfect))
check_true("repr states the bar count", "10 bars" in repr(_perfect))

shutil.rmtree(TMP, ignore_errors=True)
# sys.exit(summary()), NOT a bare summary(): summary() RETURNS the exit code
# rather than raising, so a bare call always exits 0 and the suite reports
# success no matter how many assertions failed. The first version of this file
# made that mistake, and it was invisible -- the suite printed "218 passed, 0
# failed" and would have printed "215 passed, 3 failed" with exit 0 just as
# happily. The mutation battery is what caught it: 23 mutations "survived"
# because the oracle could not fail. A test suite that cannot report failure is
# worse than no suite, because it manufactures confidence.
sys.exit(summary())
