"""
ECB Data Portal client (D-0141): euro reference exchange rates (dataflow EXR) -> Facts.

Licence (registry entry `ecb_data_portal`, read 2026-08-30): free use of the statistics
WITH CITATION -- "the ECB must be cited as the source". The data portal only: ECB Working
Papers stay disabled (and the permission request for them was cancelled by the owner,
D-0140).

MEASURED 2026-10-27:
/service/data/EXR/D.USD+JPY+GBP.EUR.SP00.A?lastNObservations=2&format=csvdata returned
HTTP 200 and SDMX CSV, one row per currency and day: GBP 2026-10-26 0.8382, JPY 176.15.
29 currencies had a 2026 observation (AUD BRL CAD CHF CNY CZK DKK GBP HKD HUF IDR ILS INR
ISK JPY KRW MXN MYR NOK NZD PHP PLN RON SEK SGD THB TRY USD ZAR). Discontinued ones
(ARS, RUB since 2022-03-01, the pre-euro currencies) still answer with their LAST value;
that is why the catalogue below is closed and every row carries its own date.

WHAT A ROW MEANS
"USD 1.1643" is the ECB reference rate: US dollars per 1 euro, fixed once a day around
14:15 CET. It is NOT a tradable quote, and it is END_OF_DAY by construction.

No key. Stdlib only.
"""
from __future__ import annotations

import csv
import io
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, List, Optional, Sequence

from rag.documents import Fact
from rag.ingest import provenance_for
from rag.sources import check_access

BASE_URL = "https://data-api.ecb.europa.eu/service/data/EXR"
SOURCE_KEY = "ecb_data_portal"
_CCY = re.compile(r"^[A-Z]{3}$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class EcbError(RuntimeError):
    pass


def data_url(currencies: Sequence[str], last_n: int = 1) -> str:
    cs = list(currencies)
    if not cs or len(cs) > 60:
        raise EcbError("between 1 and 60 currencies are required")
    for c in cs:
        if not _CCY.match(c or ""):
            raise EcbError("invalid currency code %r (expected 3 capital letters)" % (c,))
        if c == "EUR":
            raise EcbError("EUR is the base of every ECB reference rate; it has no row of its own")
    if not isinstance(last_n, int) or not 1 <= last_n <= 1000:
        raise EcbError("last_n must be an int in 1..1000")
    return "%s/D.%s.EUR.SP00.A?%s" % (BASE_URL, "+".join(cs),
                                      urllib.parse.urlencode({"lastNObservations": last_n,
                                                              "format": "csvdata"}))


def _http_get(url: str, timeout: float = 20.0) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "marfin-llm/0.13 (personal research)",
                                               "Accept": "text/csv"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise EcbError("HTTP %s from the ECB Data Portal" % exc.code)
    except (urllib.error.URLError, OSError, UnicodeDecodeError) as exc:
        raise EcbError("could not read the ECB Data Portal: %s" % (exc,))


def facts_from_csv(text: str) -> List[Fact]:
    src = check_access(SOURCE_KEY)
    rows = list(csv.DictReader(io.StringIO(text or "")))
    need = ("CURRENCY", "CURRENCY_DENOM", "TIME_PERIOD", "OBS_VALUE")
    if not rows or any(k not in rows[0] for k in need):
        raise EcbError("not an ECB SDMX CSV payload (missing %s)" % ", ".join(need))
    out: List[Fact] = []
    for r in rows:
        if (r.get("CURRENCY_DENOM") or "").strip() != "EUR":
            raise EcbError("unexpected denominator %r: only per-euro rates are parsed" % r.get("CURRENCY_DENOM"))
        ccy = (r.get("CURRENCY") or "").strip()
        v = (r.get("OBS_VALUE") or "").strip()
        d = (r.get("TIME_PERIOD") or "").strip()
        if v in ("", "NaN", "NA"):
            continue                                   # missing: skipped, never 0
        if not _CCY.match(ccy) or not _DATE.match(d):
            raise EcbError("malformed ECB row: currency %r period %r" % (ccy, d))
        try:
            val = float(v)
        except ValueError:
            raise EcbError("non-numeric ECB value %r for %s on %s" % (v, ccy, d))
        if not val > 0:
            raise EcbError("non-positive exchange rate %r for %s on %s" % (val, ccy, d))
        prov = provenance_for(SOURCE_KEY, url="%s/D.%s.EUR.SP00.A" % (BASE_URL, ccy),
                              source_id="EXR/D.%s.EUR.SP00.A" % ccy,
                              note="ECB euro reference rate %s per EUR" % ccy)
        out.append(Fact("EXR:%s" % ccy, val, "%s per EUR" % ccy, prov, period_start=d, period_end=d,
                        period_kind="instant", entity=src.name, currency=ccy))
    return out


def fetch(currencies: Sequence[str], last_n: int = 1, timeout: float = 20.0,
          http_get: Optional[Callable[[str, float], str]] = None) -> List[Fact]:
    check_access(SOURCE_KEY)                           # gate BEFORE the network call
    return facts_from_csv((http_get or _http_get)(data_url(currencies, last_n), timeout))
