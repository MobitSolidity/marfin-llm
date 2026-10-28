"""
World Bank Indicators API client (D-0141): annual country indicators -> Facts.

Licence (registry entry `world_bank_indicators`): personal / non-commercial research use
with attribution. The notice the registry requires is shown with every table.

MEASURED 2026-10-27:
/v2/country/TUR;IRN;DEU/indicator/FP.CPI.TOTL.ZG?format=json&mrv=2 returned HTTP 200 and
[metadata, rows]; Iran 2025 inflation 42.17 %, Germany 2025 2.17 %. A bad country code
returns HTTP 200 with [{"message": [{"id": "120", "key": "Invalid value", ...}]}], so the
SHAPE of the body is checked, never only the status (the same lesson as Alpha Vantage).
/v2/country lists 296 entries, of which 217 are economies (the rest are aggregates).

Values are ANNUAL and often a year or more behind; every row carries its own year.
A null value is a missing year and is skipped, never shown as 0.

No key. Stdlib only.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, List, Optional, Sequence

from rag.documents import Fact
from rag.ingest import provenance_for
from rag.sources import check_access

BASE_URL = "https://api.worldbank.org/v2"
SOURCE_KEY = "world_bank_indicators"
_ISO3 = re.compile(r"^[A-Z]{3}$")
_IND = re.compile(r"^[A-Z]{2}(\.[A-Z0-9]{2,8}){2,4}$")


class WorldBankError(RuntimeError):
    pass


def data_url(countries: Sequence[str], indicator: str, mrv: int = 5) -> str:
    cs = list(countries)
    if not cs or len(cs) > 30:
        raise WorldBankError("between 1 and 30 countries are required")
    for c in cs:
        if not _ISO3.match(c or ""):
            raise WorldBankError("invalid ISO-3 country code %r" % (c,))
    if not _IND.match(indicator or ""):
        raise WorldBankError("invalid World Bank indicator id %r" % (indicator,))
    if not isinstance(mrv, int) or not 1 <= mrv <= 60:
        raise WorldBankError("mrv (most recent values) must be an int in 1..60")
    return "%s/country/%s/indicator/%s?%s" % (BASE_URL, ";".join(cs), indicator,
                                              urllib.parse.urlencode({"format": "json", "mrv": mrv,
                                                                      "per_page": 2000}))


def _http_get(url: str, timeout: float = 20.0) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "marfin-llm/0.13 (personal research)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise WorldBankError("HTTP %s from the World Bank API" % exc.code)
    except (urllib.error.URLError, OSError, UnicodeDecodeError, ValueError) as exc:
        raise WorldBankError("could not read the World Bank API: %s" % (exc,))


def facts_from_payload(indicator: str, payload: Any, unit: str) -> List[Fact]:
    src = check_access(SOURCE_KEY)
    if not unit:
        raise WorldBankError("a unit is required: a bare indicator value has no meaning")
    if isinstance(payload, list) and payload and isinstance(payload[0], dict) and "message" in payload[0]:
        msgs = payload[0]["message"]
        raise WorldBankError("World Bank refused the request: %s" % "; ".join(
            "%s %s" % (m.get("key", ""), m.get("value", "")) for m in (msgs if isinstance(msgs, list) else [])))
    if not (isinstance(payload, list) and len(payload) == 2 and isinstance(payload[1], (list, type(None)))):
        raise WorldBankError("not a World Bank [metadata, rows] payload")
    out: List[Fact] = []
    for r in payload[1] or ():
        if (r.get("indicator") or {}).get("id") != indicator:
            raise WorldBankError("row for indicator %r in a %s response" % ((r.get("indicator") or {}).get("id"),
                                                                           indicator))
        v = r.get("value")
        if v is None:
            continue                                   # missing year: skipped, never 0
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise WorldBankError("non-numeric value %r" % (v,))
        year = str(r.get("date") or "")
        iso3 = str(r.get("countryiso3code") or "")
        if not re.match(r"^\d{4}$", year) or not _ISO3.match(iso3):
            raise WorldBankError("malformed row: year %r country %r" % (year, iso3))
        prov = provenance_for(SOURCE_KEY, url="%s/country/%s/indicator/%s" % (BASE_URL, iso3, indicator),
                              source_id="%s/%s" % (iso3, indicator),
                              note="World Bank %s %s %s" % (indicator, iso3, year))
        out.append(Fact(indicator, float(v), unit, prov, period_start="%s-01-01" % year,
                        period_end="%s-12-31" % year, period_kind="annual", entity=iso3,
                        entity_id=(r.get("country") or {}).get("value"), fiscal_year=int(year)))
    return out


def fetch(countries: Sequence[str], indicator: str, unit: str, mrv: int = 5, timeout: float = 20.0,
          http_get: Optional[Callable[[str, float], Any]] = None) -> List[Fact]:
    check_access(SOURCE_KEY)                           # gate BEFORE the network call
    return facts_from_payload(indicator, (http_get or _http_get)(data_url(countries, indicator, mrv), timeout),
                              unit)
