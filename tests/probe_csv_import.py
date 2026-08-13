"""
Adversarial probe of the CSV ingestion layer (SS.7.1 Level 2).

First execution of csv_import.py. Every module written this session revealed a
defect on its first run -- including two that reading did not find -- so the
assumption here is that this module is broken until proven otherwise.

This probe has to be shaped differently from probe_quotes.py, and the reason is
a design decision in the module itself: parse_csv returns a REPORT rather than
raising on the first problem. So "did it refuse?" is the wrong question for most
of these attacks. Counting refusals alone would let the worst defect through --
a file parsed happily, with no finding recorded, and therefore usable for a
material calculation. That is not a crash; it is a wrong number carrying a clean
bill of health.

So there are two attack classes:

  A. STRUCTURAL -- the file is not a series at all (no header, no rows, missing
     required column, NaN cell). These must RAISE. A findings report about a
     file that could not be parsed would be a report about nothing.

  B. SEMANTIC -- the file parses but something about it makes calculation
     unsafe (descending order, duplicate timestamps, naive timestamps, an
     undeclared symbol, a future export time, finer-grained bars than declared).
     These must produce a finding AT THE RIGHT SEVERITY, and -- the part that
     actually matters -- must make assert_usable_for("material_calculation")
     refuse. A finding nobody enforces is the decoration problem again.

I am specifically looking for:

  - a defective file that reaches material_calculation anyway
  - a semantic problem recorded at too low a severity to block anything
  - a validation that silently does not run (gap detection with no timeframe)
  - a CSV laundered into a live-order price via quote_from_series
  - a crash where a finding was owed (ragged rows, mixed tz, empty cells)

Run:  python3 tests/probe_csv_import.py
"""

import datetime
import operator
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from market import csv_import as ci

# The project's refusal convention (tests/_harness.py). A crash is not a refusal.
# CsvValidationError subclasses MarketDataError -> ValueError, so it is covered.
REFUSALS = (ValueError, TypeError, ZeroDivisionError)
NOW = datetime.datetime.now(datetime.timezone.utc)

TMP = tempfile.mkdtemp(prefix="marfin_csv_")
out = []
findings_out = []


def write(name, text):
    """Materialise an attack file and return its path."""
    path = os.path.join(TMP, name)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    return path


def attempt(label, fn):
    """Class A: this must raise a refusal. ALLOWED and CRASHED are both defects."""
    try:
        result = fn()
    except NotImplementedError as exc:
        print("  REFUSED (NotImpl)  %-50s %s" % (label, str(exc)[:58]))
        out.append("refused")
        return
    except REFUSALS as exc:
        print("  REFUSED (%-9s %-50s %s"
              % (type(exc).__name__ + ")", label, str(exc).split("\n")[0][:60]))
        out.append("refused")
        return
    except Exception as exc:
        print("  !! CRASHED         %-50s %s: %s"
              % (label, type(exc).__name__, str(exc)[:53]))
        out.append("crashed")
        return
    print("  ** ALLOWED         %-50s -> %r" % (label, result))
    out.append("allowed")


def expect_finding(label, series, validation, severity):
    """
    Class B: the file parsed, so the finding is the whole defence.

    Checks three things, because any one alone is insufficient:
      1. a finding exists for that validation
      2. at that severity (MATERIAL vs ADVISORY decides whether it blocks)
      3. material_calculation actually refuses when severity is blocking-grade
    """
    got = [f for f in series.findings if f.validation == validation]
    at_sev = [f for f in got if f.severity == severity]
    if not got:
        print("  ** NO FINDING      %-50s expected %s/%s"
              % (label, validation, severity))
        findings_out.append("missing")
        return
    if not at_sev:
        print("  ** WRONG SEVERITY  %-50s %s is %s, expected %s"
              % (label, validation,
                 ",".join(sorted({f.severity for f in got})), severity))
        findings_out.append("wrong_severity")
        return

    if severity in ("BLOCKING", "MATERIAL"):
        try:
            series.assert_usable_for("material_calculation")
        except REFUSALS:
            print("  FINDING+BLOCKED    %-50s %s/%s" % (label, validation, severity))
            findings_out.append("ok")
            return
        print("  ** NOT ENFORCED    %-50s %s/%s recorded but calculation ALLOWED"
              % (label, validation, severity))
        findings_out.append("not_enforced")
        return

    print("  FINDING (advisory) %-50s %s/%s" % (label, validation, severity))
    findings_out.append("ok")


# --- fixture bodies ---------------------------------------------------------

CLEAN_HEADER = "timestamp,open,high,low,close,volume\n"


def clean_rows(n=6, start_day=1, step_days=1):
    rows = []
    for i in range(n):
        d = datetime.datetime(2024, 1, start_day, 0, 0,
                              tzinfo=datetime.timezone.utc) \
            + datetime.timedelta(days=i * step_days)
        px = 100.0 + i
        rows.append("%s,%.2f,%.2f,%.2f,%.2f,%d"
                    % (d.isoformat(), px, px + 1, px - 1, px + 0.5, 1000 + i))
    return "\n".join(rows) + "\n"


def clean_kwargs(**over):
    """Everything declared, so one problem is tested at a time."""
    kw = dict(expected_symbol="AAPL", expected_exchange="NASDAQ",
              expected_currency="USD", expected_timeframe="1d",
              declared_timezone="UTC", declared_adjustment_status="ADJUSTED",
              declared_exported_at=NOW - datetime.timedelta(hours=1))
    kw.update(over)
    return kw


def main():
    print("=" * 78)
    print("ADVERSARIAL PROBE: CSV ingestion (SS.7.1 Level 2), first execution")
    print("=" * 78)

    # ---------------------------------------------------------------- class A
    print("\n[A1] not a series at all -- these must RAISE, not report")
    attempt("nonexistent path", lambda: ci.parse_csv(os.path.join(TMP, "nope.csv")))
    attempt("empty string path", lambda: ci.parse_csv(""))
    attempt("None as path", lambda: ci.parse_csv(None))
    attempt("a directory, not a file", lambda: ci.parse_csv(TMP))
    attempt("zero-byte file", lambda: ci.parse_csv(write("empty.csv", "")))
    attempt("header only, no data rows",
            lambda: ci.parse_csv(write("hdr.csv", CLEAN_HEADER)))
    attempt("blank lines only after header",
            lambda: ci.parse_csv(write("blank.csv", CLEAN_HEADER + "\n\n,,,,,\n")))
    attempt("no timestamp column",
            lambda: ci.parse_csv(write("nots.csv", "open,high,low,close\n1,2,3,4\n")))
    attempt("no close column",
            lambda: ci.parse_csv(write("nocl.csv", "timestamp,open\n2024-01-01,5\n")))

    # A value that is NOT A NUMBER is a stop, not a finding: there is nothing to
    # report about it and no severity that makes it usable. But a value that is
    # merely ABSENT is a finding -- the file is intact, one cell is empty -- so
    # '' and 'n/a' are asserted in class B, not here. The first version of this
    # probe put them here and reported the module as defective for correctly
    # returning a report. That is the same category error the docstring above
    # warns about, made in the very probe that warns about it.
    print("\n[A2] cell-level pathologies -- a bad number is a stop, not a finding")
    for label, cell in (("NaN close", "NaN"), ("nan lowercase", "nan"),
                        ("+nan close", "+nan"),
                        ("inf close", "inf"), ("-inf close", "-Infinity"),
                        ("text close cell", "probably 100"),
                        ("boolean close cell", "TRUE")):
        body = "timestamp,close\n2024-01-01T00:00:00+00:00,%s\n" % (cell,)
        attempt(label, lambda b=body, l=label: ci.parse_csv(
            write("cell_%s.csv" % abs(hash(l)), b), **clean_kwargs()))

    # NOTE: epoch seconds ('1704067200') are DELIBERATELY supported -- several
    # charting tools export them, and _parse_timestamp documents the case. It is
    # therefore not an attack and is asserted as a positive control in [C]
    # instead. Listing it here (as the first version of this probe did) would
    # have demanded a refusal for a documented feature.
    print("\n[A3] timestamp pathologies")
    for label, ts in (("empty timestamp", ""), ("garbage timestamp", "yesterday"),
                      ("half-written ISO", "2024-01-"),
                      ("epoch milliseconds (year 55969)", "1704067200000")):
        body = "timestamp,close\n%s,100\n" % (ts,)
        attempt(label, lambda b=body, l=label: ci.parse_csv(
            write("ts_%s.csv" % abs(hash(l)), b), **clean_kwargs()))

    print("\n[A2b] locale and null cells -- defects this probe found on first run")
    # An unconditional .replace(",", "") turned '1,5' into 15.0 and '1.234,56'
    # into 1.23456: a silent factor-of-ten error in a price. Ambiguous forms must
    # now be refused rather than guessed.
    #
    # The cells MUST be quoted. Unquoted, csv.reader splits '1,5' into two
    # fields, so the row is merely ragged and _parse_number never sees it -- the
    # first version of this probe left them unquoted and therefore tested
    # nothing about locale at all while appearing to. MEASURED with csv.reader
    # directly: ['2024-01-01', '1', '5'] versus ['2024-01-01', '1,5'].
    for label, cell in (("European decimal comma 1,5", '"1,5"'),
                        ("European 1.234,56", '"1.234,56"'),
                        ("bare comma", '","'),
                        ("two decimal points", "1.2.3")):
        body = ("timestamp,close\n2024-01-01T00:00:00+00:00,%s\n"
                "2024-01-02T00:00:00+00:00,101\n" % (cell,))
        attempt(label, lambda b=body, l=label: ci.parse_csv(
            write("loc_%s.csv" % abs(hash(l)), b), **clean_kwargs()))
    # The legitimate thousands form must still parse: a validator that refuses
    # '1,234.5' would reject most US exports.
    thousands = ci.parse_csv(write("thou.csv",
        'timestamp,close\n2024-01-01T00:00:00+00:00,"1,234.5"\n'
        '2024-01-02T00:00:00+00:00,"1,235.5"\n'), **clean_kwargs())
    print("  CONTROL: '1,234.5' parsed as %r (must be 1234.5)"
          % (thousands.bars[0]["close"],))
    if thousands.bars[0]["close"] != 1234.5:
        out.append("allowed")
    # A file whose every row is ragged must not be reported as "no data rows":
    # a user told their file is empty when it is misaligned will not fix it.
    attempt("every row ragged (must not say 'no data rows')",
            lambda: ci.parse_csv(write("allragged.csv",
                CLEAN_HEADER + "2024-01-01T00:00:00+00:00,1\n"
                               "2024-01-02T00:00:00+00:00,2\n"),
                **clean_kwargs()))
    # A bar with no close cannot become a Quote: substituting the previous
    # close would invent an observation the file does not contain.
    nullclose = ci.parse_csv(write("nullclose.csv",
        "timestamp,close\n2024-01-01T00:00:00+00:00,\n"
        "2024-01-02T00:00:00+00:00,101\n2024-01-03T00:00:00+00:00,102\n"),
        **clean_kwargs())
    attempt("Quote from a bar whose close is empty",
            lambda: ci.quote_from_series(nullclose, 0))

    print("\n[A4] a CSV may never price a live order, however clean it is")
    clean = ci.parse_csv(write("clean.csv", CLEAN_HEADER + clean_rows()),
                        **clean_kwargs())
    attempt("clean series -> live_order",
            lambda: clean.assert_usable_for("live_order"))
    attempt("unknown purpose is not assumed permitted",
            lambda: clean.assert_usable_for("hedging"))
    attempt("empty purpose", lambda: clean.assert_usable_for(""))
    attempt("None purpose", lambda: clean.assert_usable_for(None))
    attempt("unknown severity queried", lambda: clean.findings_at("CRITICAL"))

    print("\n[A5] a validated series must be immutable")
    attempt("append a bar via attribute",
            lambda: setattr(clean, "bars", clean.bars + ({"timestamp": NOW},)))
    attempt("rewrite the file hash",
            lambda: setattr(clean, "file_sha256", "0" * 64))
    attempt("delete the findings", lambda: delattr(clean, "findings"))
    # operator.setitem / delitem, NOT tuple.__setitem__: a tuple has no such
    # attribute, so the dunder form raises AttributeError -- which this probe
    # counts as a CRASH, not a refusal. The first version of this probe made
    # exactly that mistake and reported a defect in the module for what was a
    # defect in the probe. The operator form asks "can this be assigned?" and
    # gets the honest TypeError.
    attempt("mutate the bars tuple in place",
            lambda: operator.setitem(clean.bars, 0, {}))
    attempt("drop a finding from the tuple",
            lambda: operator.delitem(clean.findings, 0))

    print("\n[A6] a Quote built from a bar must not launder its provenance")
    q = ci.quote_from_series(clean)
    attempt("CSV-derived quote -> live_order",
            lambda: q.assert_usable_for("live_order"))
    attempt("index past the end", lambda: ci.quote_from_series(clean, 999))
    attempt("non-integer index", lambda: ci.quote_from_series(clean, 1.5))
    attempt("bool as index", lambda: ci.quote_from_series(clean, True))
    attempt("not a series at all", lambda: ci.quote_from_series({"bars": []}))

    print("\n[A7] a Finding is a record, not a scratchpad")
    f = clean.findings[0]
    attempt("rewrite a finding's severity", lambda: setattr(f, "severity", "ADVISORY"))
    attempt("unknown severity at construction",
            lambda: ci.Finding("columns", "SEVERE", "x"))
    attempt("unknown validation name", lambda: ci.Finding("vibes", "MATERIAL", "x"))
    attempt("finding with no message", lambda: ci.Finding("columns", "MATERIAL", ""))

    # ---------------------------------------------------------------- class B
    print("\n[B1] semantic defects: the finding is the whole defence")

    desc = write("desc.csv", CLEAN_HEADER + "\n".join(
        reversed(clean_rows().strip().split("\n"))) + "\n")
    expect_finding("descending time order", ci.parse_csv(desc, **clean_kwargs()),
                   "ordering", "MATERIAL")

    dup = write("dup.csv", CLEAN_HEADER + clean_rows(3) +
                clean_rows(3).split("\n")[0] + "\n")
    expect_finding("duplicated timestamp", ci.parse_csv(dup, **clean_kwargs()),
                   "duplicates", "MATERIAL")

    naive = write("naive.csv", "timestamp,close\n" +
                  "".join("2024-01-0%d,10%d\n" % (i, i) for i in range(1, 6)))
    expect_finding("naive timestamps, no tz declared",
                   ci.parse_csv(naive, **clean_kwargs(declared_timezone=None)),
                   "timezone", "BLOCKING")

    expect_finding("no symbol declared",
                   ci.parse_csv(write("s.csv", CLEAN_HEADER + clean_rows()),
                                **clean_kwargs(expected_symbol=None)),
                   "symbol", "BLOCKING")
    expect_finding("no exchange declared",
                   ci.parse_csv(write("e.csv", CLEAN_HEADER + clean_rows()),
                                **clean_kwargs(expected_exchange=None)),
                   "exchange", "BLOCKING")
    expect_finding("no currency declared",
                   ci.parse_csv(write("c.csv", CLEAN_HEADER + clean_rows()),
                                **clean_kwargs(expected_currency=None)),
                   "currency", "BLOCKING")
    expect_finding("no timeframe declared",
                   ci.parse_csv(write("t.csv", CLEAN_HEADER + clean_rows()),
                                **clean_kwargs(expected_timeframe=None)),
                   "timeframe", "MATERIAL")
    expect_finding("gap detection did not run (no timeframe)",
                   ci.parse_csv(write("t2.csv", CLEAN_HEADER + clean_rows()),
                                **clean_kwargs(expected_timeframe=None)),
                   "missing_bars", "MATERIAL")
    expect_finding("adjustment status UNKNOWN",
                   ci.parse_csv(write("a.csv", CLEAN_HEADER + clean_rows()),
                                **clean_kwargs(declared_adjustment_status="UNKNOWN")),
                   "adjustment_status", "MATERIAL")
    expect_finding("no export time declared",
                   ci.parse_csv(write("x.csv", CLEAN_HEADER + clean_rows()),
                                **clean_kwargs(declared_exported_at=None)),
                   "export_time", "MATERIAL")
    expect_finding("export time in the FUTURE",
                   ci.parse_csv(write("f.csv", CLEAN_HEADER + clean_rows()),
                                **clean_kwargs(declared_exported_at=NOW +
                                               datetime.timedelta(days=30))),
                   "export_time", "BLOCKING")
    expect_finding("exported months ago",
                   ci.parse_csv(write("old.csv", CLEAN_HEADER + clean_rows()),
                                **clean_kwargs(declared_exported_at=NOW -
                                               datetime.timedelta(days=120))),
                   "export_time", "MATERIAL")

    # 1-minute bars declared as daily: the annualization factor would be off by
    # ~390x and the resulting number would look entirely plausible.
    rows = []
    for i in range(8):
        d = datetime.datetime(2024, 1, 2, 14, 30, tzinfo=datetime.timezone.utc) \
            + datetime.timedelta(minutes=i)
        rows.append("%s,100,101,99,100.5,10" % d.isoformat())
    fine = write("fine.csv", CLEAN_HEADER + "\n".join(rows) + "\n")
    expect_finding("1m bars declared as 1d",
                   ci.parse_csv(fine, **clean_kwargs()), "timeframe", "BLOCKING")

    expect_finding("unrecognised indicator columns",
                   ci.parse_csv(write("ind.csv",
                       "timestamp,close,RSI,MACD_signal\n" +
                       "".join("2024-01-0%dT00:00:00+00:00,10%d,55.2,0.31\n"
                               % (i, i) for i in range(1, 6))),
                       **clean_kwargs()),
                   "indicator_columns", "MATERIAL")

    ragged = write("ragged.csv", CLEAN_HEADER + clean_rows(4) +
                   "2024-02-01T00:00:00+00:00,1,2\n")
    expect_finding("ragged row (3 fields, header has 6)",
                   ci.parse_csv(ragged, **clean_kwargs()), "columns", "MATERIAL")

    unordered = write("unord.csv", CLEAN_HEADER +
                      "2024-01-03T00:00:00+00:00,1,2,0.5,1.5,10\n"
                      "2024-01-01T00:00:00+00:00,1,2,0.5,1.5,10\n"
                      "2024-01-05T00:00:00+00:00,1,2,0.5,1.5,10\n"
                      "2024-01-02T00:00:00+00:00,1,2,0.5,1.5,10\n")
    expect_finding("neither ascending nor descending",
                   ci.parse_csv(unordered, **clean_kwargs()), "ordering", "BLOCKING")

    dupcol = write("dupcol.csv",
                   "timestamp,close,Close\n2024-01-01T00:00:00+00:00,100,200\n"
                   "2024-01-02T00:00:00+00:00,101,201\n")
    expect_finding("two columns map to 'close'",
                   ci.parse_csv(dupcol, **clean_kwargs()), "columns", "BLOCKING")

    # THE WORST DEFECT THIS PROBE FOUND. A file whose closes are blank parsed
    # into a series with NO finding at all: is_blocked False and
    # material_calculation ALLOWED. Not a crash -- a wrong number carrying a
    # clean bill of health, which is the exact outcome SS.7.1 exists to prevent.
    expect_finding("every close is blank",
                   ci.parse_csv(write("allnull.csv",
                       "timestamp,close\n" +
                       "".join("2024-01-0%dT00:00:00+00:00,\n" % i
                               for i in range(1, 6))),
                       **clean_kwargs()),
                   "columns", "BLOCKING")
    expect_finding("some closes blank",
                   ci.parse_csv(write("somenull.csv",
                       "timestamp,close\n2024-01-01T00:00:00+00:00,\n" +
                       "".join("2024-01-0%dT00:00:00+00:00,10%d\n" % (i, i)
                               for i in range(2, 6))),
                       **clean_kwargs()),
                   "columns", "MATERIAL")
    # An ABSENT value is a finding, not a stop (see the note in [A2]): the file
    # is intact and one cell is empty. What must NOT happen is the file passing
    # with no finding, which is what the first version did.
    expect_finding("single bar, close cell empty",
                   ci.parse_csv(write("one_empty.csv",
                       "timestamp,close\n2024-01-01T00:00:00+00:00,\n"),
                       **clean_kwargs()),
                   "columns", "BLOCKING")
    expect_finding("close cell says n/a",
                   ci.parse_csv(write("one_na.csv",
                       "timestamp,close\n2024-01-01T00:00:00+00:00,n/a\n"),
                       **clean_kwargs()),
                   "columns", "BLOCKING")
    expect_finding("volume column entirely N/A",
                   ci.parse_csv(write("novol.csv",
                       "timestamp,close,volume\n" +
                       "".join("2024-01-0%dT00:00:00+00:00,10%d,N/A\n" % (i, i)
                               for i in range(1, 6))),
                       **clean_kwargs()),
                   "columns", "MATERIAL")

    # The finding must state the TRUE reason. A 2-bar file with a correctly
    # declared timeframe previously produced "gap detection did not run:
    # timeframe is 1d" -- a self-contradicting sentence bound for an audit log.
    two_bar = ci.parse_csv(write("twobar.csv",
        "timestamp,close\n2024-01-01T00:00:00+00:00,100\n"
        "2024-01-02T00:00:00+00:00,101\n"), **clean_kwargs())
    mb = [f for f in two_bar.findings if f.validation == "missing_bars"]
    if mb and "timeframe is 1d" in mb[0].message:
        print("  ** FALSE REASON    %-50s %r"
              % ("2-bar file blames the declared timeframe", mb[0].message))
        findings_out.append("false_reason")
    else:
        print("  REASON IS TRUE     %-50s %s"
              % ("2-bar file does not blame the timeframe",
                 mb[0].message[:44] if mb else "no finding (gap check ran)"))
        findings_out.append("ok")

    # ---------------------------------------------------------------- controls
    print("\n[C] positive controls -- a validator that refuses everything is useless")
    ok = True

    c = ci.parse_csv(write("clean2.csv", CLEAN_HEADER + clean_rows(10)),
                     **clean_kwargs())
    sev = {s: len(c.findings_at(s)) for s in ci.SEVERITIES}
    print("   fully-declared clean file: findings %s" % (sev,))
    if sev["BLOCKING"] or sev["MATERIAL"]:
        print("   !! a clean, fully-declared file produced blocking findings")
        for bad in c.findings_at("BLOCKING") + c.findings_at("MATERIAL"):
            print("      %s/%s %s" % (bad.severity, bad.validation, bad.message))
        ok = False
    try:
        c.assert_usable_for("material_calculation")
        print("   clean file IS usable for a material calculation: yes")
    except Exception as exc:
        print("   !! clean file refused for calculation: %s" % str(exc)[:90])
        ok = False
    try:
        c.assert_usable_for("display")
        print("   clean file IS displayable: yes")
    except Exception as exc:
        print("   !! clean file refused for display: %s" % exc)
        ok = False

    blocked = ci.parse_csv(write("blk.csv", CLEAN_HEADER + clean_rows()),
                           **clean_kwargs(expected_symbol=None))
    try:
        blocked.assert_usable_for("display")
        print("   a BLOCKED file is still displayable alongside findings: yes")
    except Exception as exc:
        print("   !! blocked file refused for display (worse than showing it): %s" % exc)
        ok = False
    print("   blocked.is_blocked = %s (must be True)" % blocked.is_blocked)
    ok = ok and blocked.is_blocked is True
    print("   clean.is_blocked   = %s (must be False)" % c.is_blocked)
    ok = ok and c.is_blocked is False

    print("   bars parsed from a 10-row file: %d (must be 10)" % len(c.bars))
    ok = ok and len(c.bars) == 10
    h = c.file_sha256
    print("   file_sha256 = %s... (len %d, must be 64)" % (h[:16], len(h)))
    ok = ok and len(h) == 64
    same = ci.parse_csv(write("clean3.csv", CLEAN_HEADER + clean_rows(10)),
                        **clean_kwargs())
    print("   identical bytes -> identical hash: %s" % (same.file_sha256 == h))
    ok = ok and same.file_sha256 == h
    diff = ci.parse_csv(write("clean4.csv", CLEAN_HEADER + clean_rows(11)),
                        **clean_kwargs())
    print("   different bytes -> different hash: %s" % (diff.file_sha256 != h))
    ok = ok and diff.file_sha256 != h

    m = ci.manifest()
    print("   manifest lists %d validations (SS.7.1 requires 14)"
          % len(m["validations"]))
    ok = ok and len(m["validations"]) == 14

    qq = ci.quote_from_series(c)
    print("   quote origin=%s delay=%s trust=%s is_weak=%s is_live=%s"
          % (qq.origin, qq.delay_status, qq.trust_level, qq.is_weak, qq.is_live))
    # is_weak is False BY DESIGN and this probe originally asserted True, which
    # was the probe being wrong about the module's intent: WEAK_ORIGINS is
    # (VISUALLY_EXTRACTED, USER_SUPPLIED, UNKNOWN). A file the user exported
    # from their own terminal outranks a number read off a screenshot. What must
    # hold is that it is not LIVE and not trusted, which is asserted instead.
    ok = ok and qq.origin == "CSV_EXPORT"
    ok = ok and qq.trust_level == "UNVERIFIED"
    ok = ok and qq.is_live is False
    ok = ok and qq.delay_status == "END_OF_DAY"

    # Epoch-seconds timestamps are a supported export format, not an attack.
    ep = ci.parse_csv(write("epoch.csv", "timestamp,close\n1704067200,100\n"
                            "1704153600,101\n1704240000,102\n"),
                      **clean_kwargs())
    print("   epoch-seconds export parsed: first bar %s (tz-aware=%s)"
          % (ep.bars[0]["timestamp"].isoformat(),
             ep.bars[0]["timestamp"].tzinfo is not None))
    ok = ok and ep.bars[0]["timestamp"].year == 2024
    ok = ok and ep.bars[0]["timestamp"].tzinfo is not None

    print("\n" + "=" * 78)
    allowed, crashed = out.count("allowed"), out.count("crashed")
    bad_findings = len(findings_out) - findings_out.count("ok")
    print("class A: attempts=%d refused=%d ALLOWED=%d CRASHED=%d"
          % (len(out), out.count("refused"), allowed, crashed))
    print("class B: checks=%d enforced=%d DEFECTIVE=%d  (%s)"
          % (len(findings_out), findings_out.count("ok"), bad_findings,
             ", ".join("%s=%d" % (k, findings_out.count(k))
                       for k in ("missing", "wrong_severity", "not_enforced",
                                 "false_reason")
                       if findings_out.count(k)) or "none"))
    print("invariants=%s" % ("OK" if ok else "BROKEN"))
    shutil.rmtree(TMP, ignore_errors=True)
    if allowed or crashed or bad_findings or not ok:
        print("RESULT: defects present. Fix before proceeding.")
        return 1
    print("RESULT: structural attacks refused, semantic defects recorded AND "
          "enforced, clean files still usable.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
