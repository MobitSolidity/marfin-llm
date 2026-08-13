"""
SS.7.1 Level 2: reading a CSV the user exported, and the fourteen validations.

WHAT SS.7.1 LEVEL 2 REQUIRES, VERBATIM
--------------------------------------
"Read a CSV explicitly exported by the user. Validate: File hash, Export time,
Symbol, Exchange, Timeframe, Timezone, Columns, Indicator columns, Missing bars,
Duplicates, Ordering, Adjustment status, Coverage period, Currency."

Fourteen checks. Each corresponds to a way a CSV can be wrong while looking
perfectly reasonable in a spreadsheet, which is the only kind of defect worth
building machinery for:

  file hash          the same filename re-exported with different content
  export time        a file exported months ago, read as current
  symbol/exchange    "AAPL" from an unknown venue, or a symbol mismatch
  timeframe          5-minute bars processed as daily
  timezone           naive timestamps compared across venues
  columns            a close column that is actually adjusted close
  indicator columns  a precomputed RSI whose parameters are unknown
  missing bars       gaps that silently shorten a return series
  duplicates         a repeated bar that double-counts a move
  ordering           descending rows treated as ascending
  adjustment status  unadjusted prices compared against adjusted ones
  coverage period    a 30-day file used to answer a 1-year question
  currency           a bare number that is not a price

WHY THE RESULT IS A REPORT AND NOT A SERIES OF EXCEPTIONS
--------------------------------------------------------
The tempting design raises on the first problem. It is wrong for this input,
because these findings are not equivalent: a file with a missing bar is still
perfectly good for inspecting a single day, while a file with an unknown timezone
is not usable for anything that crosses a session boundary. Raising on the first
problem also means the user fixes one thing, re-exports, and discovers the next --
whereas the whole point of validating a user-supplied artifact is to tell them
everything wrong with it at once.

So parsing produces a CsvSeries carrying findings at three severities, and the
REFUSALS happen at the point of use: assert_usable_for("material_calculation")
consults the findings. That mirrors Quote.assert_usable_for, and for the same
reason -- a label that nothing checks is decoration.

Structurally malformed input (unreadable file, no data rows, unparseable numbers)
still raises, because there is no series to report findings about.

WHY THIS FILE EXISTS AT ALL WHEN NO PROVIDER IS LICENSED
--------------------------------------------------------
Level 2 needs no data licence. A CSV the user exported themselves, from a service
they have their own relationship with, is their file. That makes Level 2 the only
machine-readable market-data path currently available to this project (Level 0,
hand-typed values, being the other), and therefore the one worth building well.

Note the boundary: this module validates a CSV's INTERNAL consistency. It cannot
establish that the user was permitted to export it. A TradingView CSV export is
still TradingView data under TradingView's terms, and those terms prohibit
non-display machine use -- so origin is recorded and provenance is preserved
rather than laundered by the act of passing through a file.

Stdlib only. Imports from market.quotes for the shared vocabulary.
"""

import csv
import datetime
import hashlib
import io
import os
from types import MappingProxyType
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from market.quotes import (ADJUSTMENT_STATUS, MarketDataError, Quote,
                           VALUE_ORIGINS)


#: How serious a finding is. Three levels, because two is not enough: the
#: difference between "this file cannot be used" and "this file can be used with
#: a stated caveat" is the difference between refusing the user's work and
#: qualifying it.
SEVERITIES: Tuple[str, ...] = ("BLOCKING", "MATERIAL", "ADVISORY")

#: The fourteen SS.7.1 Level 2 validations, by key, in the order the spec lists
#: them. Kept as data so that a test can assert all fourteen ran -- a validation
#: that silently stops running is the failure mode this list exists to prevent.
VALIDATIONS: Tuple[str, ...] = (
    "file_hash", "export_time", "symbol", "exchange", "timeframe", "timezone",
    "columns", "indicator_columns", "missing_bars", "duplicates", "ordering",
    "adjustment_status", "coverage_period", "currency")

#: Bar intervals this module can reason about, in seconds. A timeframe outside
#: this table is recorded as UNKNOWN rather than guessed, because guessing an
#: interval is how 5-minute bars get annualized as daily ones.
TIMEFRAME_SECONDS: Mapping[str, int] = MappingProxyType({
    "1m": 60, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "4h": 14400, "1d": 86400, "1w": 604800,
})

#: Column names this module understands, mapped to canonical names. Deliberately
#: conservative: an unrecognised column becomes an INDICATOR column rather than
#: being quietly matched to a price field.
_CANONICAL_COLUMNS: Mapping[str, str] = MappingProxyType({
    "time": "timestamp", "date": "timestamp", "datetime": "timestamp",
    "timestamp": "timestamp",
    "open": "open", "high": "high", "low": "low", "close": "close",
    "volume": "volume", "vol": "volume",
    # NOT mapped to "close". An adjusted close IS a different number, and
    # treating the two as interchangeable is the exact error that makes an
    # unadjusted/adjusted comparison look valid.
    "adj close": "adj_close", "adjclose": "adj_close",
    "adjusted close": "adj_close", "adj_close": "adj_close",
})

_REQUIRED_COLUMNS = ("timestamp", "close")


class CsvValidationError(MarketDataError):
    """
    The file cannot be parsed into a series at all.

    Subclasses MarketDataError (and so ValueError), keeping it inside the
    project's REFUSALS convention. Used only for structural failures -- an
    unreadable file, no data rows, a timestamp column that is not timestamps.
    Everything else is a finding, not an exception.
    """


class Finding(object):
    """One validation result. Immutable, because findings are evidence."""

    _FIELDS = ("validation", "severity", "message", "detail")
    __slots__ = _FIELDS + ("_frozen",)

    def __init__(self, validation, severity, message, detail=""):
        object.__setattr__(self, "_frozen", False)
        if validation not in VALIDATIONS:
            raise CsvValidationError(
                "unknown validation %r; SS.7.1 Level 2 lists: %s"
                % (validation, ", ".join(VALIDATIONS)))
        if severity not in SEVERITIES:
            raise CsvValidationError(
                "unknown severity %r; allowed: %s"
                % (severity, ", ".join(SEVERITIES)))
        if not message:
            raise CsvValidationError("a finding must carry a message")
        self.validation = validation
        self.severity = severity
        self.message = message
        self.detail = detail
        object.__setattr__(self, "_frozen", True)

    def __setattr__(self, name, value):
        if getattr(self, "_frozen", False):
            raise CsvValidationError(
                "findings are immutable: refusing to set %r. A finding that can "
                "be downgraded after the fact is not a finding." % (name,))
        object.__setattr__(self, name, value)

    def __delattr__(self, name):
        raise CsvValidationError("findings are immutable: refusing to delete %r"
                                 % (name,))

    def __repr__(self):
        return "Finding(%s/%s: %s)" % (self.severity, self.validation,
                                       self.message)

    def to_dict(self):
        return {k: getattr(self, k) for k in self._FIELDS}


class CsvSeries(object):
    """
    A validated OHLCV series from a user-exported CSV, with its findings.

    Immutable, including the bar list, which is exposed as a tuple. A caller that
    could append a bar could extend the coverage period past what was validated.
    """

    _FIELDS = ("path", "file_sha256", "n_bytes", "symbol", "exchange",
               "currency", "timeframe", "timezone", "adjustment_status",
               "exported_at", "read_at", "columns", "indicator_columns", "bars",
               "findings", "origin", "note")
    __slots__ = _FIELDS + ("_frozen",)

    def __init__(self, path, file_sha256, n_bytes, symbol, exchange, currency,
                 timeframe, timezone, adjustment_status, exported_at, read_at,
                 columns, indicator_columns, bars, findings, origin, note=""):
        object.__setattr__(self, "_frozen", False)
        if origin not in VALUE_ORIGINS:
            raise CsvValidationError(
                "origin must be one of %s, got %r"
                % (", ".join(VALUE_ORIGINS), origin))
        if adjustment_status not in ADJUSTMENT_STATUS:
            raise CsvValidationError(
                "adjustment_status must be one of %s, got %r"
                % (", ".join(ADJUSTMENT_STATUS), adjustment_status))
        self.path = path
        self.file_sha256 = file_sha256
        self.n_bytes = n_bytes
        self.symbol = symbol
        self.exchange = exchange
        self.currency = currency
        self.timeframe = timeframe
        self.timezone = timezone
        self.adjustment_status = adjustment_status
        self.exported_at = exported_at
        self.read_at = read_at
        self.columns = tuple(columns)
        self.indicator_columns = tuple(indicator_columns)
        self.bars = tuple(bars)
        self.findings = tuple(findings)
        self.origin = origin
        self.note = note
        object.__setattr__(self, "_frozen", True)

    def __setattr__(self, name, value):
        if getattr(self, "_frozen", False):
            raise CsvValidationError(
                "a validated series is immutable: refusing to set %r. Appending "
                "a bar would extend the coverage period past what was "
                "validated." % (name,))
        object.__setattr__(self, name, value)

    def __delattr__(self, name):
        raise CsvValidationError(
            "a validated series is immutable: refusing to delete %r" % (name,))

    def __repr__(self):
        return ("CsvSeries(%s/%s %s %d bars, %d findings)"
                % (self.exchange, self.symbol, self.timeframe, len(self.bars),
                   len(self.findings)))

    # -- the questions a caller needs answered ------------------------------

    def findings_at(self, severity: str) -> Tuple[Finding, ...]:
        if severity not in SEVERITIES:
            raise CsvValidationError("unknown severity %r" % (severity,))
        return tuple(f for f in self.findings if f.severity == severity)

    @property
    def is_blocked(self) -> bool:
        return bool(self.findings_at("BLOCKING"))

    @property
    def validations_run(self) -> Tuple[str, ...]:
        """
        Which of the fourteen produced a finding.

        NOT the same as "which ran" -- a clean validation produces nothing. The
        distinction is why parse_csv records a CLEAN finding for checks that pass
        with a caveat worth stating, and why manifest() reports the full list.
        """
        return tuple(sorted({f.validation for f in self.findings}))

    def assert_usable_for(self, purpose: str) -> None:
        """
        Refuse uses the findings do not support.

        Mirrors Quote.assert_usable_for deliberately: same purposes, same
        principle that an unrecognised purpose is not assumed permitted.
        """
        if not purpose or not isinstance(purpose, str):
            raise CsvValidationError("purpose must be a non-empty string")

        blocking = self.findings_at("BLOCKING")
        material = self.findings_at("MATERIAL")

        if purpose == "live_order":
            # SS.7.1 Level 2 is an EXPORT. It is historical by construction: the
            # export time is in the past, and no CSV is a live quote. This is
            # refused unconditionally rather than on the strength of findings.
            raise CsvValidationError(
                "a CSV export may never price a live order: it is historical by "
                "construction (exported %s, read %s). Obtain the price from the "
                "broker at order time."
                % (self.exported_at or "at an unknown time", self.read_at))
        if purpose == "material_calculation":
            if blocking:
                raise CsvValidationError(
                    "%d BLOCKING finding(s) make this file unusable for a "
                    "material calculation: %s"
                    % (len(blocking), "; ".join(f.message for f in blocking)))
            if material:
                raise CsvValidationError(
                    "%d MATERIAL finding(s) mean a calculation from this file "
                    "would be wrong in a way the result would not show: %s. "
                    "Re-export with the problem fixed, or state the result as "
                    "approximate and cite the caveat."
                    % (len(material), "; ".join(f.message for f in material)))
            return
        if purpose == "display":
            # Anything may be shown to a human ALONGSIDE ITS FINDINGS. A blocked
            # file displayed without them would be worse than refusing.
            return
        raise CsvValidationError(
            "unknown purpose %r; allowed: live_order, material_calculation, "
            "display. An unrecognised purpose is not assumed permitted."
            % (purpose,))

    def to_dict(self) -> Dict[str, Any]:
        d = {k: getattr(self, k) for k in self._FIELDS
             if k not in ("bars", "findings")}
        d["n_bars"] = len(self.bars)
        d["findings"] = [f.to_dict() for f in self.findings]
        return d


def _sha256_and_size(path):
    h = hashlib.sha256()
    n = 0
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(65536)
            if not chunk:
                break
            n += len(chunk)
            h.update(chunk)
    return h.hexdigest(), n


def _parse_timestamp(raw):
    """
    Parse a timestamp, returning (datetime, was_naive).

    `was_naive` is returned rather than silently assumed UTC: SS.7.1 lists
    timezone as its own validation precisely because a naive timestamp is the
    classic cross-market defect, and quietly stamping UTC on it would destroy
    the evidence that it was missing.
    """
    text = (raw or "").strip()
    if not text:
        raise CsvValidationError("empty timestamp")
    # Unix epoch seconds, as exported by several charting tools.
    if text.isdigit() and len(text) >= 9:
        return (datetime.datetime.fromtimestamp(
            int(text), datetime.timezone.utc), False)
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.datetime.fromisoformat(normalized)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
                    "%d/%m/%Y", "%m/%d/%Y"):
            try:
                parsed = datetime.datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        else:
            raise CsvValidationError("unparseable timestamp %r" % (text,))
    return (parsed, parsed.tzinfo is None)


#: Cell contents that mean "this bar has no value here", as distinct from a
#: value that is unparseable. Spreadsheets and chart exports produce all of
#: these routinely. NOTE the deliberate ABSENCE of "NAN": the first version of
#: this list contained it, which made the NaN guard below almost unreachable --
#: 'NaN' and 'nan' were swallowed here as nulls before float() ever saw them,
#: while the docstring claimed NaN was refused "like quotes.py". Only '+nan'
#: reached the guard. That is the declared-not-enforced defect this project
#: exists to prevent, found in my own new code by executing it.
_NULL_CELLS = ("", "N/A", "NA", "NULL", "NONE", "-", "--", "#N/A")


def _parse_number(raw, column, lineno):
    """
    Parse one numeric cell into (value, was_null).

    Returns a PAIR rather than a bare value because the caller must be able to
    tell "this bar genuinely has no volume" from "this cell said 100". The
    first version returned None for both a null cell and an absent column, so a
    file whose closes were all blank parsed into a series with no finding
    recorded, is_blocked False, and material_calculation ALLOWED. A missing
    price is not a validation-free file; it is the thing most worth reporting.
    """
    text = (raw or "").strip()
    if text.upper() in _NULL_CELLS:
        return (None, True)

    # A thousands separator is stripped, but ONLY when the string cannot be a
    # European decimal comma. Unconditional .replace(",", "") -- what the first
    # version did -- turns '1,5' into 15.0 and '1.234,56' into 1.23456: a
    # silent factor-of-ten error in a price, which is exactly the class of
    # defect that survives every test that only checks "did it parse".
    candidate = text
    if "," in text:
        if "." in text and text.rfind(".") > text.rfind(","):
            # 1,234.56 -- comma groups thousands, dot is the decimal point.
            candidate = text.replace(",", "")
        elif "." not in text and text.count(",") > 1:
            # 12,345,678 -- repeated commas cannot all be decimal points.
            candidate = text.replace(",", "")
        else:
            # '1,5' / '1.234,56' -- ambiguous or European. Refusing beats
            # guessing: this module cannot know the export's locale, and a
            # wrong guess produces a plausible number.
            raise CsvValidationError(
                "line %d: column %r is ambiguous: %r may be a decimal comma "
                "(%s) or a thousands separator (%s). This module will not "
                "guess the export's locale. Re-export with a dot decimal "
                "separator."
                % (lineno, column, text, text.replace(",", "."),
                   text.replace(",", "")))

    try:
        value = float(candidate)
    except ValueError:
        raise CsvValidationError(
            "line %d: column %r is not a number: %r" % (lineno, column, text))
    # The same pathologies quotes.py refuses, refused here too. A CSV is a
    # likelier source of them than an API: spreadsheets produce inf and blank
    # cells routinely, and a zero close divides into every ratio downstream.
    if value != value:
        raise CsvValidationError(
            "line %d: column %r is NaN. A NaN propagates silently through every "
            "sum and mean it touches." % (lineno, column))
    if value in (float("inf"), float("-inf")):
        raise CsvValidationError(
            "line %d: column %r is infinite" % (lineno, column))
    return (value, False)


def parse_csv(path: str,
              expected_symbol: Optional[str] = None,
              expected_exchange: Optional[str] = None,
              expected_currency: Optional[str] = None,
              expected_timeframe: Optional[str] = None,
              declared_timezone: Optional[str] = None,
              declared_adjustment_status: str = "UNKNOWN",
              declared_exported_at: Optional[datetime.datetime] = None,
              origin: str = "CSV_EXPORT",
              max_export_age_days: int = 7) -> CsvSeries:
    """
    Read and validate a user-exported CSV. Runs all fourteen SS.7.1 checks.

    The `expected_*` arguments are what the USER says the file contains. They are
    required for a clean result, and their ABSENCE is itself a finding: a CSV
    whose symbol nobody stated is a column of numbers. This is the opposite of
    inferring them from the filename, which is how a EURUSD export becomes an
    AAPL series.
    """
    findings: List[Finding] = []

    def add(validation, severity, message, detail=""):
        findings.append(Finding(validation, severity, message, detail))

    if not path or not isinstance(path, str):
        raise CsvValidationError("path must be a non-empty string")
    if not os.path.isfile(path):
        raise CsvValidationError("no such CSV file: %r" % (path,))

    read_at = datetime.datetime.now(datetime.timezone.utc)

    # --- 1. file hash -------------------------------------------------------
    # Recorded, not compared: there is nothing to compare a first import
    # against. The hash is what makes a LATER re-export detectable, and what ties
    # a calculation in an audit log to the exact bytes it used.
    file_sha256, n_bytes = _sha256_and_size(path)
    if n_bytes == 0:
        raise CsvValidationError("CSV file is empty: %r" % (path,))
    add("file_hash", "ADVISORY",
        "file sha256 recorded for provenance",
        "%s (%d bytes). Compare against this on re-import to detect a changed "
        "export sharing the same filename." % (file_sha256, n_bytes))

    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        text = fh.read()
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        raise CsvValidationError("CSV has no header row")

    # --- 7. columns ---------------------------------------------------------
    raw_names = [h.strip() for h in header]
    canonical, indicator_columns, seen = [], [], {}
    for name in raw_names:
        key = _CANONICAL_COLUMNS.get(name.lower())
        if key is None:
            indicator_columns.append(name)
            canonical.append(None)
        else:
            if key in seen:
                add("columns", "BLOCKING",
                    "column %r maps to %r, which already appeared as %r"
                    % (name, key, seen[key]),
                    "An ambiguous duplicate column means every row is read from "
                    "one of two places and nothing says which.")
            seen[key] = name
            canonical.append(key)

    missing = [c for c in _REQUIRED_COLUMNS if c not in seen]
    if missing:
        raise CsvValidationError(
            "CSV lacks required column(s): %s. Found: %s"
            % (", ".join(missing), ", ".join(raw_names)))

    if "adj_close" in seen and "close" in seen:
        add("columns", "ADVISORY",
            "both close and adjusted close are present",
            "Bars use %r. The adjusted column is preserved as an indicator "
            "column rather than substituted, because the two are different "
            "numbers." % (seen["close"],))

    # --- 8. indicator columns ----------------------------------------------
    if indicator_columns:
        add("indicator_columns", "MATERIAL",
            "%d unrecognised column(s) treated as precomputed indicators: %s"
            % (len(indicator_columns), ", ".join(indicator_columns)),
            "Their parameters, warm-up period and adjustment basis are UNKNOWN. "
            "SS.7.1 requires indicator columns to be validated, and nothing in "
            "the file states how they were computed -- so they may not be relied "
            "on. Recompute from OHLCV instead.")

    idx = {key: i for i, key in enumerate(canonical) if key}

    # --- parse rows ---------------------------------------------------------
    bars = []
    naive_count = 0
    ragged_count = 0
    data_lines = 0
    null_counts = {}            # column -> how many bars have no value there
    for lineno, row in enumerate(reader, 2):
        if not row or all(not c.strip() for c in row):
            continue
        data_lines += 1
        if len(row) != len(raw_names):
            ragged_count += 1
            add("columns", "MATERIAL",
                "line %d has %d fields but the header has %d"
                % (lineno, len(row), len(raw_names)),
                "A ragged row means column alignment is not guaranteed.")
            continue
        ts, was_naive = _parse_timestamp(row[idx["timestamp"]])
        if was_naive:
            naive_count += 1
        bar = {"timestamp": ts}
        for field in ("open", "high", "low", "close", "volume", "adj_close"):
            if field in idx:
                value, was_null = _parse_number(row[idx[field]], field, lineno)
                bar[field] = value
                if was_null:
                    null_counts[field] = null_counts.get(field, 0) + 1
        for name in indicator_columns:
            bar[name] = row[raw_names.index(name)].strip()
        bars.append(bar)

    if not bars:
        # Distinguish the two ways a file can yield no bars. The first version
        # reported "no data rows" for BOTH, so a file whose every row was
        # ragged was refused for a reason that was not true -- and a user told
        # their file is empty when it is actually misaligned will not fix it.
        if ragged_count:
            raise CsvValidationError(
                "CSV yielded no usable bars: all %d data row(s) are ragged "
                "(field count does not match the %d-column header). The file "
                "is not empty; its columns do not line up." % (ragged_count,
                                                               len(raw_names)))
        raise CsvValidationError(
            "CSV has a header but no data rows: %r" % (path,))

    # --- 7. columns (continued): declared columns whose cells are empty -----
    # SS.7.1 requires the columns to be validated, and a column that exists in
    # the header but holds nothing is not a validated column. The first version
    # recorded NOTHING here: a file whose closes were all blank produced a
    # series with no finding, is_blocked False, and material_calculation
    # ALLOWED. That is the single worst outcome this module can produce -- a
    # defective file carrying a clean bill of health -- and only executing it
    # revealed it.
    for field in sorted(null_counts):
        n_null = null_counts[field]
        share = n_null / float(len(bars))
        if field == "close" or share >= 0.5:
            # close is a required column: without it a bar prices nothing.
            severity = "BLOCKING" if (field == "close" and share >= 0.5) \
                else "MATERIAL"
        else:
            severity = "MATERIAL"
        add("columns", severity,
            "column %r is empty in %d of %d bar(s) (%.0f%%)"
            % (field, n_null, len(bars), share * 100),
            "An empty cell is not a zero and not a carried-forward value. Any "
            "sum, mean or return computed across it silently skips a bar, so "
            "the result describes a different series than the user thinks.")

    # --- 6. timezone --------------------------------------------------------
    if naive_count and not declared_timezone:
        add("timezone", "BLOCKING",
            "%d of %d timestamps carry no timezone and none was declared"
            % (naive_count, len(bars)),
            "A naive timestamp compared across venues is wrong in a way nothing "
            "detects. Pass declared_timezone with the timezone the export used.")
    elif naive_count and declared_timezone:
        add("timezone", "ADVISORY",
            "%d naive timestamp(s) interpreted as %s on the user's word"
            % (naive_count, declared_timezone),
            "The file itself does not state this.")

    # --- 11. ordering -------------------------------------------------------
    timestamps = [b["timestamp"] for b in bars]
    # Compare naive against naive: mixing tz-aware and naive raises TypeError,
    # which would be a crash rather than a finding.
    comparable = [t.replace(tzinfo=None) for t in timestamps]
    ascending = all(comparable[i] <= comparable[i + 1]
                    for i in range(len(comparable) - 1))
    descending = all(comparable[i] >= comparable[i + 1]
                     for i in range(len(comparable) - 1))
    if not ascending and not descending:
        add("ordering", "BLOCKING",
            "rows are neither ascending nor descending in time",
            "An unordered series cannot be differenced, so every return, "
            "moving average and drawdown computed from it is meaningless.")
    elif descending and len(bars) > 1:
        add("ordering", "MATERIAL",
            "rows are in DESCENDING time order",
            "Treated as ascending, every return changes sign. The caller must "
            "reverse the series before use; this module does not silently "
            "reorder the user's file.")

    # --- 10. duplicates -----------------------------------------------------
    counts = {}
    for t in comparable:
        counts[t] = counts.get(t, 0) + 1
    dupes = sorted(t for t, c in counts.items() if c > 1)
    if dupes:
        add("duplicates", "MATERIAL",
            "%d duplicated timestamp(s), e.g. %s"
            % (len(dupes), dupes[0].isoformat()),
            "A repeated bar double-counts the move it contains, inflating "
            "volume and distorting volatility.")

    # --- 9. missing bars ----------------------------------------------------
    timeframe = expected_timeframe or "UNKNOWN"
    ordered = sorted(comparable)
    # Two bars are enough: one interval can already be compared against the
    # declared step. The first version required more than two AND folded the
    # "too few bars" case into the "no timeframe" message, so a file with a
    # declared 1d timeframe and two bars produced the finding "gap detection did
    # not run: timeframe is 1d" -- a sentence that contradicts itself and would
    # have gone into an audit record as the reason. A false explanation is worse
    # than no explanation: it sends the user to fix something that is not wrong.
    if timeframe in TIMEFRAME_SECONDS and len(ordered) >= 2:
        step = TIMEFRAME_SECONDS[timeframe]
        gaps = 0
        for i in range(len(ordered) - 1):
            delta = (ordered[i + 1] - ordered[i]).total_seconds()
            if delta > step * 1.5:
                gaps += 1
        if gaps:
            # ADVISORY, not MATERIAL: for daily bars, every weekend is a gap, and
            # a validator that cries wolf on normal market closure teaches its
            # user to ignore it. The count is reported so a human can judge.
            add("missing_bars", "ADVISORY",
                "%d gap(s) larger than one %s interval" % (gaps, timeframe),
                "Expected for weekends, holidays and halts; unexpected for a "
                "continuous 24h market. Not classified automatically because "
                "this module does not know the venue's trading calendar.")
    elif timeframe not in TIMEFRAME_SECONDS:
        add("missing_bars", "MATERIAL",
            "gap detection did not run: no usable timeframe (%s)" % (timeframe,),
            "Without a stated bar interval, a missing bar is indistinguishable "
            "from a bar that was never expected. Pass expected_timeframe.")
    else:
        add("missing_bars", "MATERIAL",
            "gap detection did not run: only %d bar(s), so there is no interval "
            "to compare against the declared %s" % (len(ordered), timeframe),
            "A single bar cannot reveal a gap. This states the actual reason "
            "rather than blaming the timeframe, which was declared correctly.")

    # --- 5. timeframe -------------------------------------------------------
    if not expected_timeframe:
        add("timeframe", "MATERIAL",
            "no timeframe was declared",
            "5-minute bars processed as daily produce plausible, wrong "
            "annualized figures. The file does not state its own interval.")
    elif expected_timeframe not in TIMEFRAME_SECONDS:
        add("timeframe", "MATERIAL",
            "timeframe %r is not one this module can reason about"
            % (expected_timeframe,),
            "Known: %s" % (", ".join(sorted(TIMEFRAME_SECONDS)),))
    elif len(ordered) >= 2:
        # Cross-check the declared timeframe against the actual spacing. A
        # declaration nothing verifies is the same decoration problem as an
        # unenforced licence field. Two bars is the real minimum: one interval
        # already contradicts a wrong declaration, and requiring three left a
        # two-bar 1-minute file declared as daily entirely unchecked.
        step = TIMEFRAME_SECONDS[expected_timeframe]
        deltas = [(ordered[i + 1] - ordered[i]).total_seconds()
                  for i in range(len(ordered) - 1)]
        positive = [d for d in deltas if d > 0]
        if positive:
            modal = min(positive)
            if modal < step * 0.5:
                add("timeframe", "BLOCKING",
                    "declared timeframe %s but the smallest gap between bars is "
                    "%.0fs" % (expected_timeframe, modal),
                    "The file contains finer-grained data than declared, so any "
                    "resampling or annualization would use the wrong factor.")

    # --- 3. symbol / 4. exchange / 14. currency ----------------------------
    for key, value, why in (
            ("symbol", expected_symbol,
             "a column of numbers with no instrument attached cannot be "
             "reconciled against any other source"),
            ("exchange", expected_exchange,
             "the same ticker trades on different venues at different prices"),
            ("currency", expected_currency,
             "a bare number is not a price, and a cross-currency comparison "
             "looks perfectly valid")):
        if not value:
            add(key, "BLOCKING", "no %s was declared for this file" % (key,), why)

    # --- 12. adjustment status ---------------------------------------------
    if declared_adjustment_status == "UNKNOWN":
        add("adjustment_status", "MATERIAL",
            "adjustment status is UNKNOWN",
            "Comparing an adjusted series against an unadjusted one produces a "
            "plausible, wrong answer. Most chart exports are adjusted and most "
            "do not say so.")

    # --- 2. export time -----------------------------------------------------
    exported_at = declared_exported_at
    if exported_at is None:
        add("export_time", "MATERIAL",
            "no export time was declared",
            "A file exported months ago, read as current, is the quietest way "
            "for stale data to enter a calculation. The filesystem mtime is not "
            "used as a substitute: copying a file rewrites it.")
    else:
        exp = exported_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=datetime.timezone.utc)
        age_days = (read_at - exp).total_seconds() / 86400.0
        if age_days < -1:
            add("export_time", "BLOCKING",
                "declared export time is %.1f days in the FUTURE" % (-age_days,),
                "Either a clock is wrong or the value was mistyped; both make "
                "the file's freshness unknowable.")
        elif age_days > max_export_age_days:
            add("export_time", "MATERIAL",
                "exported %.1f days ago (threshold %d)"
                % (age_days, max_export_age_days),
                "Prices have moved since. Usable for history, not as a current "
                "picture.")

    # --- 13. coverage period ------------------------------------------------
    span_days = (ordered[-1] - ordered[0]).total_seconds() / 86400.0
    add("coverage_period", "ADVISORY",
        "covers %.1f days across %d bars (%s to %s)"
        % (span_days, len(bars), ordered[0].isoformat(),
           ordered[-1].isoformat()),
        "Any question whose window exceeds this period cannot be answered from "
        "this file, and a partial answer would not look partial.")

    return CsvSeries(
        path=path, file_sha256=file_sha256, n_bytes=n_bytes,
        symbol=expected_symbol, exchange=expected_exchange,
        currency=expected_currency, timeframe=timeframe,
        timezone=declared_timezone, adjustment_status=declared_adjustment_status,
        exported_at=exported_at, read_at=read_at,
        columns=tuple(c for c in canonical if c),
        indicator_columns=tuple(indicator_columns), bars=tuple(bars),
        findings=tuple(findings), origin=origin)


def quote_from_series(series: CsvSeries, index: int = -1) -> Quote:
    """
    Build a Quote from one bar, preserving provenance rather than laundering it.

    origin=CSV_EXPORT, delay_status=END_OF_DAY, market_status=UNKNOWN,
    trust_level=UNVERIFIED. A number does not become authoritative by passing
    through a file, and this is the point where that could quietly happen.
    """
    # Type-check BEFORE calling a method on it. The first version went straight
    # to series.assert_usable_for(...), so passing a dict produced an
    # AttributeError -- a crash, not a refusal, and the project's convention is
    # explicit that those are different things. A caller who passes the wrong
    # object gets told what is wrong, not a traceback from inside the module.
    if not isinstance(series, CsvSeries):
        raise CsvValidationError(
            "series must be a CsvSeries returned by parse_csv, got %s. A Quote "
            "may only be built from a series whose fourteen validations "
            "actually ran." % (type(series).__name__,))
    series.assert_usable_for("material_calculation")
    if not isinstance(index, int) or isinstance(index, bool):
        raise CsvValidationError("index must be an integer")
    try:
        bar = series.bars[index]
    except IndexError:
        raise CsvValidationError(
            "no bar at index %r; the series has %d" % (index, len(series.bars)))
    # Quote() would refuse this anyway, but with "a quote must carry at least one
    # of bid/ask/last" -- true, and useless to someone holding a CSV. Naming the
    # actual cause here means the refusal survives even if Quote's own guard is
    # ever relaxed, rather than depending on a check in another module.
    if bar.get("close") is None:
        raise CsvValidationError(
            "bar %d has no close value, so it cannot become a Quote. An empty "
            "cell is not a price; substituting the previous bar's close would "
            "invent an observation the file does not contain." % (index,))
    return Quote(
        provider="csv:%s" % (os.path.basename(series.path),),
        symbol=series.symbol, instrument_id=None, exchange=series.exchange,
        asset_class=None, currency=series.currency,
        timestamp=bar["timestamp"], timezone=series.timezone or "UNKNOWN",
        delay_status="END_OF_DAY", market_status="UNKNOWN",
        adjustment_status=series.adjustment_status,
        corporate_action_status="UNKNOWN", trust_level="UNVERIFIED",
        origin="CSV_EXPORT", last=bar.get("close"),
        licence="user-exported file; this module cannot establish the user was "
                "permitted to export it",
        note="bar %d of %d from %s (sha256 %s)"
             % (index, len(series.bars), series.path, series.file_sha256[:16]))


def manifest() -> Dict[str, Any]:
    return {"level": "SS.7.1 Level 2 (CSV integration)",
            "validations": list(VALIDATIONS),
            "n_validations": len(VALIDATIONS),
            "severities": list(SEVERITIES),
            "known_timeframes": sorted(TIMEFRAME_SECONDS),
            "needs_data_licence": False,
            "licence_note": "A user's own export needs no provider licence, but "
                            "the underlying terms still apply: a TradingView CSV "
                            "remains TradingView data, whose terms prohibit "
                            "non-display machine use."}
