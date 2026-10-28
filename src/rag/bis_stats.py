"""
BIS statistics client (D-0133): SDMX CSV -> Facts, through the registry gate.

This is the BIS *statistics* licence, which is separate from (and far more
permissive than) the BIS *publications* licence that keeps `bis_working_papers`
disabled. data.bis.org/help/legal, read 2026-10-21: "The use of the statistics
is unrestricted, provided that" the BIS is cited as the source, a translation
is labelled unofficial, the use does not imply endorsement, and a commercial
product does not charge extra for them. The API terms add: no warranty; the BIS
may limit an IP; users "may not ... modify, distribute, decompile ... the APIs"
(the software, not the statistics); "use the most up-to-date version".

MEASURED 2026-10-21: /api/v1/data/WS_CBPOL/D.US?lastNObservations=1&format=csv
returned HTTP 200 and a CSV row: 2026-10-20, 3.875 (US policy rate, mid-point
of the Fed target range 3.75-4.00 -- the NY Fed API reported the same range the
same day, an independent cross-check).

No key. Stdlib only.
"""

from __future__ import annotations

import csv
import io
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, List, Optional

from rag.documents import Fact
from rag.ingest import provenance_for
from rag.sources import check_access

BASE_URL = "https://stats.bis.org/api/v1/data"
_ID = re.compile(r"^[A-Z0-9_]{2,40}$")
_KEY = re.compile(r"^[A-Za-z0-9_.+]{1,80}$")


class BisStatsError(RuntimeError):
    pass


def data_url(dataflow: str, key: str, last_n: int = 1) -> str:
    if not _ID.match(dataflow or ""):
        raise BisStatsError("invalid BIS dataflow id %r" % (dataflow,))
    if not _KEY.match(key or ""):
        raise BisStatsError("invalid BIS series key %r" % (key,))
    if not isinstance(last_n, int) or not 1 <= last_n <= 10000:
        raise BisStatsError("last_n must be an int in 1..10000")
    return "%s/%s/%s?%s" % (BASE_URL, dataflow, key,
                            urllib.parse.urlencode({"lastNObservations": last_n, "format": "csv"}))


def _http_get(url: str, timeout: float = 20.0) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "marfin-llm/0.10 (personal research)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise BisStatsError("HTTP %s from BIS statistics API" % exc.code)
    except (urllib.error.URLError, OSError, UnicodeDecodeError) as exc:
        raise BisStatsError("could not read BIS statistics API: %s" % (exc,))


def facts_from_csv(dataflow: str, key: str, text: str, unit: str) -> List[Fact]:
    src = check_access("bis_statistics")
    if not unit:
        raise BisStatsError("a unit is required: a bare BIS number has no meaning (SS.5.2)")
    rows = list(csv.DictReader(io.StringIO(text or "")))
    if not rows or "OBS_VALUE" not in rows[0] or "TIME_PERIOD" not in rows[0]:
        raise BisStatsError("not a BIS SDMX CSV payload (no OBS_VALUE/TIME_PERIOD columns)")
    prov = provenance_for("bis_statistics", url="%s/%s/%s" % (BASE_URL, dataflow, key),
                          source_id="%s/%s" % (dataflow, key),
                          note="BIS statistics %s %s" % (dataflow, key))
    out: List[Fact] = []
    for r in rows:
        v = (r.get("OBS_VALUE") or "").strip()
        if v in ("", "NaN", "NA"):
            continue                     # missing observation: skipped, never 0
        try:
            val = float(v)
        except ValueError:
            raise BisStatsError("non-numeric BIS value %r on %s" % (v, r.get("TIME_PERIOD")))
        d = (r.get("TIME_PERIOD") or "").strip()
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", d):
            raise BisStatsError("only daily series are parsed here; got period %r" % (d,))
        out.append(Fact("%s:%s" % (dataflow, key), val, unit, prov, period_start=d,
                        period_end=d, period_kind="instant", entity=src.name))
    return out


def fetch(dataflow: str, key: str, unit: str, last_n: int = 1, timeout: float = 20.0,
          http_get: Optional[Callable[[str, float], str]] = None) -> List[Fact]:
    check_access("bis_statistics")                      # gate BEFORE the network call
    return facts_from_csv(dataflow, key, (http_get or _http_get)(data_url(dataflow, key, last_n),
                                                               timeout), unit)


def facts_per_area(dataflow: str, text: str, unit: str) -> List[Fact]:
    """
    D-0141: one CSV holding SEVERAL reference areas (key "D." = every area, or "D.US+GB")
    -> Facts whose concept names the area, "WS_CBPOL:D.US". facts_from_csv() above gives
    every row the requested key, which is right for one series and wrong for many, so it
    is left untouched and this is separate. MEASURED 2026-10-27: WS_CBPOL/D. with
    lastNObservations=1 returned 49 areas, including 9 euro members whose series stop in
    1998-2000 (superseded by XM) -- callers must look at each row's own date.
    """
    src = check_access("bis_statistics")
    if not unit:
        raise BisStatsError("a unit is required: a bare BIS number has no meaning (SS.5.2)")
    rows = list(csv.DictReader(io.StringIO(text or "")))
    need = ("FREQ", "REF_AREA", "OBS_VALUE", "TIME_PERIOD")
    if not rows or any(k not in rows[0] for k in need):
        raise BisStatsError("not a multi-area BIS SDMX CSV payload (missing %s)" % ", ".join(need))
    out: List[Fact] = []
    for r in rows:
        area, freq = (r.get("REF_AREA") or "").strip(), (r.get("FREQ") or "").strip()
        if not re.match(r"^[A-Z0-9]{2,3}$", area) or freq != "D":
            raise BisStatsError("unexpected area %r / frequency %r" % (area, freq))
        v = (r.get("OBS_VALUE") or "").strip()
        if v in ("", "NaN", "NA"):
            continue                     # missing observation: skipped, never 0
        try:
            val = float(v)
        except ValueError:
            raise BisStatsError("non-numeric BIS value %r for %s" % (v, area))
        d = (r.get("TIME_PERIOD") or "").strip()
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", d):
            raise BisStatsError("only daily series are parsed here; got period %r" % (d,))
        key = "%s.%s" % (freq, area)
        prov = provenance_for("bis_statistics", url="%s/%s/%s" % (BASE_URL, dataflow, key),
                              source_id="%s/%s" % (dataflow, key), note="BIS statistics %s %s" % (dataflow, key))
        out.append(Fact("%s:%s" % (dataflow, key), val, unit, prov, period_start=d, period_end=d,
                        period_kind="instant", entity=area))
    return out


def fetch_per_area(dataflow: str, key: str, unit: str, last_n: int = 1, timeout: float = 20.0,
                   http_get: Optional[Callable[[str, float], str]] = None) -> List[Fact]:
    check_access("bis_statistics")                      # gate BEFORE the network call
    return facts_per_area(dataflow, (http_get or _http_get)(data_url(dataflow, key, last_n), timeout), unit)
