"""
macro_data (SYSTEM_PROMPT SS.8.3) over the two licensed macro sources, D-0135.

    macro_data(series, source=None, start_date=None, end_date=None, frequency=None)

WHAT THIS IS
------------
A CLOSED catalogue of macro series, each pinned to one licensed source
(`fred` or `bis_statistics`), with the unit and frequency VERIFIED against the
source's own metadata on 2026-10-23 (FRED /fred/series; BIS CSV header). Every
value comes back as a `Fact` carrying the registry's trust level and licence,
and as a `Passage` that the existing RAG index and citation verifier accept
unchanged -- so a macro figure is cited and checked exactly like a filing row.

WHY A CLOSED CATALOGUE AND NOT "ANY FRED SERIES"
------------------------------------------------
The unit decides what a number means, and the model must never be the one to
supply it. A free-form series id would need its unit read from the network at
every call AND trusted; a catalogue pins the unit that was VERIFIED, and
`fetch()` re-checks it against FRED's series metadata when FRED reports one
(`units` field), refusing on any mismatch instead of guessing. Adding a series
is one reviewed line here, plus its test.

WHAT IT NEVER DOES
------------------
- Never fabricates a value: a missing observation ("." on FRED, NaN on BIS) is
  skipped, an empty window is a refusal, and nothing is interpolated.
- Never reads the FRED key from a file (rag.fred.get_api_key: environment only).
- Never "converts" a unit: CPI stays an index. Inflation is a DERIVED figure,
  computed by `year_over_year()` from two index values the caller can see, and
  labelled COMPUTED -- never presented as a published rate.

Stdlib only.
"""

from __future__ import annotations

import datetime
from typing import Any, Callable, Dict, List, Optional, Sequence

from rag import bis_stats as _bis
from rag import fred as _fred
from rag.documents import Fact, Passage
from rag.normalize import fold
from rag.sources import check_access, required_notices


class MacroError(RuntimeError):
    """A refusal. The message never contains an API key."""


# ---------------------------------------------------------------------------
# The catalogue. Units/frequencies VERIFIED 2026-10-23 from the source itself:
#   FRED: GET /fred/series?series_id=<id> -> "units", "frequency",
#         "seasonal_adjustment_short"   (the owner's key, via FRED_API_KEY)
#   BIS : WS_CBPOL CSV header UNIT_MEASURE=368, UNIT_MULT=0, FREQ=D, and the
#         dataflow title "Central bank policy rates" (percent per annum).
# `units_note` is what the citation verifier scales by. "billion" for FRED's
# "Billions of Dollars" (a scale word). For an index or a percent it is the
# source's OWN unit string: not a scale word, so the verifier scales by 1, but a
# DECLARED unit -- with None the verifier must (correctly) refuse every bare
# figure as "scale unknown", MEASURED 2026-10-23 on "CPI was 336.298".
# `terms` are the words a question must contain to select the series; matched
# on fold()ed text, so Persian digit/letter variants match too.
# ---------------------------------------------------------------------------
SERIES: Dict[str, Dict[str, Any]] = {
    "CPIAUCSL": {
        "source": "fred", "unit": "Index 1982-1984=100", "units_note": "Index 1982-1984=100",
        "frequency": "monthly", "adjustment": "SA",
        "title": "Consumer Price Index for All Urban Consumers: All Items, U.S. city average",
        "title_fa": "\u0634\u0627\u062e\u0635 \u0642\u06cc\u0645\u062a \u0645\u0635\u0631\u0641\u200c\u06a9\u0646\u0646\u062f\u0647 \u0622\u0645\u0631\u06cc\u06a9\u0627",
        "terms": ("cpi", "consumer price", "inflation",
                  "\u062a\u0648\u0631\u0645",                                   # tavarrom
                  "\u0634\u0627\u062e\u0635 \u0642\u06cc\u0645\u062a"),         # shakhes-e gheymat
    },
    "UNRATE": {
        "source": "fred", "unit": "Percent", "units_note": "Percent",
        "frequency": "monthly", "adjustment": "SA",
        "title": "Unemployment Rate (U.S., U-3)",
        "title_fa": "\u0646\u0631\u062e \u0628\u06cc\u06a9\u0627\u0631\u06cc \u0622\u0645\u0631\u06cc\u06a9\u0627",
        "terms": ("unemployment", "jobless",
                  "\u0628\u06cc\u06a9\u0627\u0631\u06cc"),                       # bikari
    },
    "FEDFUNDS": {
        "source": "fred", "unit": "Percent", "units_note": "Percent",
        "frequency": "monthly", "adjustment": "NSA",
        "title": "Federal Funds Effective Rate (monthly average)",
        "title_fa": "\u0646\u0631\u062e \u0645\u0624\u062b\u0631 \u0648\u062c\u0648\u0647 \u0641\u062f\u0631\u0627\u0644",
        "terms": ("fed funds", "federal funds", "fedfunds",
                  "\u0648\u062c\u0648\u0647 \u0641\u062f\u0631\u0627\u0644"),   # vojuh-e federal
    },
    "DGS10": {
        "source": "fred", "unit": "Percent", "units_note": "Percent",
        "frequency": "daily", "adjustment": "NSA",
        "title": "Market Yield on U.S. Treasury Securities at 10-Year Constant Maturity",
        "title_fa": "\u0628\u0627\u0632\u062f\u0647 \u0627\u0648\u0631\u0627\u0642 \u062e\u0632\u0627\u0646\u0647 \u06f1\u06f0 \u0633\u0627\u0644\u0647 \u0622\u0645\u0631\u06cc\u06a9\u0627",
        "terms": ("10-year", "10 year", "ten-year", "treasury yield", "dgs10",
                  "\u062e\u0632\u0627\u0646\u0647"),                             # khazane
    },
    "GDP": {
        "source": "fred", "unit": "Billions of Dollars", "units_note": "billion",
        "frequency": "quarterly", "adjustment": "SAAR",
        "title": "Gross Domestic Product (U.S., nominal)",
        "title_fa": "\u062a\u0648\u0644\u06cc\u062f \u0646\u0627\u062e\u0627\u0644\u0635 \u062f\u0627\u062e\u0644\u06cc \u0622\u0645\u0631\u06cc\u06a9\u0627",
        "terms": ("gdp", "gross domestic product",
                  "\u062a\u0648\u0644\u06cc\u062f \u0646\u0627\u062e\u0627\u0644\u0635"),  # tolid-e nakhales
    },
}

#: BIS central-bank policy rates: one series per central bank (WS_CBPOL, daily).
#: Values MEASURED 2026-10-23 for the record (not used by the code): US 3.875,
#: XM 2.5, GB 3.75, JP 1.25, CA 2.25, CH 0.
_CB = {
    "US": ("United States (Federal Reserve)", "\u0641\u062f\u0631\u0627\u0644 \u0631\u0632\u0631\u0648",
           ("federal reserve", "fed ", "u.s. policy", "us policy", "\u0641\u062f\u0631\u0627\u0644 \u0631\u0632\u0631\u0648")),
    "XM": ("Euro area (European Central Bank)", "\u0628\u0627\u0646\u06a9 \u0645\u0631\u06a9\u0632\u06cc \u0627\u0631\u0648\u067e\u0627",
           ("ecb", "european central bank", "euro area", "eurozone",
            "\u0628\u0627\u0646\u06a9 \u0645\u0631\u06a9\u0632\u06cc \u0627\u0631\u0648\u067e\u0627", "\u0645\u0646\u0637\u0642\u0647 \u06cc\u0648\u0631\u0648")),
    "GB": ("United Kingdom (Bank of England)", "\u0628\u0627\u0646\u06a9 \u0627\u0646\u06af\u0644\u0633\u062a\u0627\u0646",
           ("bank of england", "boe", "united kingdom", " uk ", "\u0628\u0627\u0646\u06a9 \u0627\u0646\u06af\u0644\u0633\u062a\u0627\u0646", "\u0627\u0646\u06af\u0644\u0633\u062a\u0627\u0646")),
    "JP": ("Japan (Bank of Japan)", "\u0628\u0627\u0646\u06a9 \u0698\u0627\u067e\u0646",
           ("bank of japan", "boj", "japan", "\u0698\u0627\u067e\u0646")),
    "CA": ("Canada (Bank of Canada)", "\u0628\u0627\u0646\u06a9 \u06a9\u0627\u0646\u0627\u062f\u0627",
           ("bank of canada", "canada", "\u06a9\u0627\u0646\u0627\u062f\u0627")),
    "CH": ("Switzerland (Swiss National Bank)", "\u0628\u0627\u0646\u06a9 \u0645\u0644\u06cc \u0633\u0648\u0626\u06cc\u0633",
           ("swiss national bank", "snb", "switzerland", "\u0633\u0648\u0626\u06cc\u0633")),
}
for _area, (_name, _name_fa, _terms) in _CB.items():
    SERIES["WS_CBPOL:D.%s" % _area] = {
        "source": "bis_statistics", "unit": "Percent per annum", "units_note": "Percent per annum",
        "frequency": "daily", "adjustment": "NSA",
        "title": "Central bank policy rate, %s" % _name,
        "title_fa": "\u0646\u0631\u062e \u0633\u06cc\u0627\u0633\u062a\u06cc %s" % _name_fa,
        # A question must name the BANK/AREA and a policy-rate word (see select()).
        "terms": _terms, "needs_any": ("policy rate", "interest rate", "key rate", "base rate",
                                       "\u0646\u0631\u062e \u0628\u0647\u0631\u0647",
                                       "\u0646\u0631\u062e \u0633\u06cc\u0627\u0633\u062a\u06cc",
                                       "\u0633\u0648\u062f \u0628\u0627\u0646\u06a9\u06cc"),
    }

FREQUENCIES = ("daily", "monthly", "quarterly")
# The FRED "units" strings the catalogue was verified against. fetch() refuses
# when FRED reports something else for the same id.
_FRED_UNIT = {k: v["unit"] for k, v in SERIES.items() if v["source"] == "fred"}


def _iso(d: Optional[str], name: str) -> Optional[datetime.date]:
    if d in (None, ""):
        return None
    try:
        return datetime.date.fromisoformat(str(d))
    except ValueError:
        raise MacroError("%s must be an ISO date YYYY-MM-DD, got %r" % (name, d))


def spec(series: str, source: Optional[str] = None,
         frequency: Optional[str] = None) -> Dict[str, Any]:
    """The catalogue entry, after refusing anything outside the catalogue."""
    s = SERIES.get(series)
    if s is None:
        raise MacroError("series %r is not in the macro catalogue (%s). Units are "
                         "pinned per series, so an unknown series is refused rather "
                         "than guessed." % (series, ", ".join(sorted(SERIES))))
    if source is not None and source != s["source"]:
        raise MacroError("series %r is served by %r, not %r" % (series, s["source"], source))
    if frequency is not None and frequency != s["frequency"]:
        # No resampling: averaging a daily series into a monthly one is an
        # analytical choice, and it would produce a number the source never
        # published.
        raise MacroError("series %r is %s; resampling to %r is not done (it would "
                         "create a figure the source never published)"
                         % (series, s["frequency"], frequency))
    return s


def select(question: str) -> List[str]:
    """
    The catalogue series a question asks about, in catalogue order. [] when none.

    Deliberately literal: a series is chosen only when the question contains one
    of its terms (BIS policy rates also need a policy-rate word). A question
    that merely mentions "rate" selects nothing -- an unwanted fetch is cheap,
    but an unwanted figure in the evidence invites the model to quote it.
    """
    q = " %s " % fold(question or "")
    out = []
    for key, s in SERIES.items():
        if not any(fold(t) in q for t in s["terms"]):
            continue
        need = s.get("needs_any")
        if need and not any(fold(t) in q for t in need):
            continue
        out.append(key)
    return out


def _window(facts: Sequence[Fact], start: Optional[datetime.date],
            end: Optional[datetime.date]) -> List[Fact]:
    return [f for f in facts
            if (start is None or f.period_end >= start)
            and (end is None or f.period_end <= end)]


def fetch(series: str, source: Optional[str] = None, start_date: Optional[str] = None,
          end_date: Optional[str] = None, frequency: Optional[str] = None,
          limit: int = 13, api_key: Optional[str] = None,
          fred_get: Optional[Callable[..., Any]] = None,
          fred_meta: Optional[Callable[[str, str], Optional[str]]] = None,
          bis_get: Optional[Callable[..., str]] = None) -> List[Fact]:
    """
    Newest-last Facts for one catalogue series, inside [start_date, end_date].

    The registry gate (check_access) runs BEFORE any network call, inside the
    two clients. `limit` caps how many observations are requested (most recent
    first); the window then filters them. An empty result is a refusal, never [].
    """
    s = spec(series, source, frequency)
    start, end = _iso(start_date, "start_date"), _iso(end_date, "end_date")
    if start and end and start > end:
        raise MacroError("start_date %s is after end_date %s" % (start, end))
    if not isinstance(limit, int) or not 1 <= limit <= 1000:
        raise MacroError("limit must be an int in 1..1000")
    if s["source"] == "fred":
        key = _fred.get_api_key(api_key)
        check_access("fred", api_key=key)
        if fred_meta is not None:
            got = fred_meta(series, key)
            if got is not None and got != _FRED_UNIT[series]:
                raise MacroError("FRED now reports unit %r for %s, but the catalogue was "
                                 "verified as %r; refusing rather than mislabelling"
                                 % (got, series, _FRED_UNIT[series]))
        facts = _fred.fetch_observations(series, s["unit"], api_key=key, limit=limit,
                                         sort_order="desc", http_get=fred_get)
    else:
        dataflow, key = series.split(":", 1)
        facts = _bis.fetch(dataflow, key, s["unit"], last_n=limit, http_get=bis_get)
    facts = sorted(_window(facts, start, end), key=lambda f: f.period_end)
    if not facts:
        raise MacroError("no %s observation inside the requested window (%s .. %s); "
                         "nothing is interpolated" % (series, start or "-", end or "-"))
    return facts


def fred_series_units(series: str, api_key: str, timeout: float = 20.0) -> Optional[str]:
    """FRED's own `units` string for a series (the live half of the unit check)."""
    import urllib.parse
    url = "%s/series?%s" % (_fred.BASE_URL, urllib.parse.urlencode(
        {"series_id": series, "file_type": "json", "api_key": api_key}))
    js = _fred._http_get(url, api_key, timeout)
    try:
        return js["seriess"][0]["units"]
    except (KeyError, IndexError, TypeError):
        return None


def year_over_year(facts: Sequence[Fact]) -> Optional[Dict[str, Any]]:
    """
    COMPUTED 12-month change of a monthly index: (latest / same month a year
    earlier) - 1. None when the year-earlier observation is not in `facts` --
    never an approximation from a neighbouring month.
    """
    if not facts:
        return None
    last = max(facts, key=lambda f: f.period_end)
    try:
        prior_date = last.period_end.replace(year=last.period_end.year - 1)
    except ValueError:            # 29 Feb
        return None
    prior = [f for f in facts if f.period_end == prior_date]
    if not prior or prior[0].value == 0:
        return None
    from calc.returns_risk import simple_return      # the registry's own tool
    r = simple_return(prior[0].value, last.value)
    return {"value": r.value, "pct": round(100.0 * r.value, 2), "from": prior_date.isoformat(),
            "to": last.period_end.isoformat(), "start": prior[0].value, "end": last.value,
            "formula": r.formula, "label": "COMPUTED", "tool": "simple_return"}


def computed_passage(series: str, yoy: Dict[str, Any], basis: Fact, lang: str = "en") -> Passage:
    """
    The COMPUTED 12-month change as an evidence row, so the model may quote it
    and the verifier can check it. The row says COMPUTED and names the tool and
    both input dates; its provenance is the source series it was derived from.
    """
    s = spec(series)
    label = ("\u062a\u063a\u06cc\u06cc\u0631 \u06f1\u06f2 \u0645\u0627\u0647\u0647 (\u062a\u0648\u0631\u0645 \u0633\u0627\u0644\u0627\u0646\u0647)"
             if lang == "fa" else "12-month percent change (annual inflation)")
    text = "%s of %s, COMPUTED by the simple_return tool from the %s and %s rows | %s | %s" % (
        label, series, yoy["from"], yoy["to"], yoy["to"], _fmt(yoy["pct"]))
    return Passage(text, basis.provenance, section_path=("Macro", series, "COMPUTED"),
                   entity=s["title"], entity_id=series, period_start=yoy["from"],
                   period_end=yoy["to"], lang=lang,
                   doc_id="MACRO-%s-YOY-%s" % (series, yoy["to"]), units_note="Percent")


def evidence_for(series: str, facts: Sequence[Fact], lang: str = "en",
                 max_rows: int = 2) -> List[Passage]:
    """Newest rows, plus (monthly index only) the year-earlier row and the COMPUTED change."""
    out = to_passages(series, facts, lang, max_rows)
    if series == "CPIAUCSL":
        yoy = year_over_year(facts)
        if yoy is not None:
            prior = [f for f in facts if f.period_end.isoformat() == yoy["from"]]
            out = to_passages(series, prior, lang, 1) + out
            out.append(computed_passage(series, yoy, prior[0], lang))
    return out


def to_passages(series: str, facts: Sequence[Fact], lang: str = "en",
                max_rows: int = 3) -> List[Passage]:
    """
    One Passage per observation (newest `max_rows`), in the "label | date | value"
    row shape the citation verifier's row rule already understands. The unit is
    spelled in the row, and `units_note` carries the scale word (or None), so a
    bare figure from a "Billions of Dollars" series can only be confirmed when
    the claim says "billion" -- the 10^6 rule, applied to macro data.
    """
    s = spec(series)
    out = []
    for f in sorted(facts, key=lambda x: x.period_end)[-max_rows:]:
        title = s["title_fa"] if lang == "fa" else s["title"]
        text = "%s (%s; %s; %s) | %s | %s" % (
            title, s["unit"], s["frequency"], s["adjustment"],
            f.period_end.isoformat(), _fmt(f.value))
        out.append(Passage(text, f.provenance, section_path=("Macro", series),
                           entity=s["title"], entity_id=series,
                           period_start=f.period_end.isoformat(),
                           period_end=f.period_end.isoformat(), lang=lang,
                           doc_id="MACRO-%s-%s" % (series, f.period_end.isoformat()),
                           units_note=s["units_note"]))
    return out


def _fmt(v: float) -> str:
    """The value as the source wrote it: no rounding, no thousands separator."""
    return ("%.10f" % v).rstrip("0").rstrip(".") if v != int(v) else "%d" % int(v)


_PCT = None


def verify_percent_claim(claim: str, passages: Sequence[Passage]) -> Optional[str]:
    """
    The percent half of citation checking, for macro passages only.

    rag.citations.extract_numbers skips every percentage on purpose (in a filing
    "grew 12%" is derived, not a row). For a macro series the value IS a percent
    (UNRATE 4.2, DGS10 4.13), or a COMPUTED percent change we put in the evidence.
    Returns "SUPPORTED" when every percentage in the claim equals a passage value
    within half a unit of the claim's own last decimal, "CONTRADICTED" when one
    does not, and None when the claim states no percentage.
    """
    import re
    global _PCT
    if _PCT is None:
        _PCT = re.compile(r"([-+]?\d+(?:\.\d+)?)\s*(?:%|\u066a|\u062f\u0631\u0635\u062f)")
    from rag.normalize import mask_non_quantities
    text = fold(mask_non_quantities(claim or ""))
    found = _PCT.findall(text)
    if not found:
        return None
    values = []
    for ps in passages:
        tail = ps.text.rsplit("|", 1)[-1]
        try:
            values.append(float(fold(tail).strip()))
        except ValueError:
            continue
    for raw in found:
        dec = len(raw.split(".")[1]) if "." in raw else 0
        tol = 0.5 * 10 ** -dec + 1e-12
        if not any(abs(float(raw) - v) <= tol for v in values):
            return "CONTRADICTED"
    return "SUPPORTED"


def notices(series_keys: Sequence[str]) -> List[str]:
    """The attribution lines the sources used require (FRED's is verbatim)."""
    return required_notices(sorted({SERIES[k]["source"] for k in series_keys if k in SERIES}))


def macro_data(series: str, source: Optional[str] = None, start_date: Optional[str] = None,
               end_date: Optional[str] = None, frequency: Optional[str] = None,
               **kw: Any) -> Dict[str, Any]:
    """The SS.8.3 tool: the exact argument names of the catalogue spec."""
    facts = fetch(series, source, start_date, end_date, frequency, **kw)
    s = SERIES[series]
    return {"series": series, "source": s["source"], "unit": s["unit"],
            "frequency": s["frequency"], "adjustment": s["adjustment"],
            "observations": [{"date": f.period_end.isoformat(), "value": f.value} for f in facts],
            "trust_level": facts[0].provenance.trust_level,
            "licence": facts[0].provenance.licence, "label": "RETRIEVED",
            "notices": notices([series])}
