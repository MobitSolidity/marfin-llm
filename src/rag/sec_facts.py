"""
US company fundamentals from SEC EDGAR XBRL "companyfacts" (D-0142).

Official, free, public domain (sources.py: sec_edgar_xbrl, "US government work").
SEC refuses requests without a contact User-Agent (MEASURED: HTTP 403), so the
address comes from SEC_CONTACT_EMAIL and check_access() validates it BEFORE any
network call. Nothing is hard-coded: a made-up contact is exactly what the
registry gate exists to refuse.

Shapes MEASURED 2026-10-28:
  www.sec.gov/files/company_tickers.json  -> {"0": {"cik_str": 1045810, "ticker": "NVDA",
                                              "title": "NVIDIA CORP"}, ...}  (10,430 rows)
  data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json -> {"cik", "entityName",
      "facts": {"us-gaap": {Concept: {"units": {"USD": [{"start", "end", "val", "accn",
      "fy", "fp", "form", "filed", "frame"}]}}}}}
  Apple FY2025 (10-K filed 2025-10-31): revenue 416,161,000,000; net income
  112,010,000,000; diluted EPS 7.46; assets 359,241,000,000.

ANNUAL FIGURES ONLY, AND WHY THE FILTER IS STRICT. A 10-K also carries the two
prior years as comparatives and, for some concepts, quarterly values. So a row
counts as an annual figure only if form is 10-K, fp is FY, and -- for a flow
concept -- its period spans 350..380 days. When several filings report the same
period end, the LATEST filing wins (it carries any restatement), and the
accession number is kept so every figure can be traced to its filing.
"""
from __future__ import annotations

import datetime
import json
import math
import os
import re
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, List, Optional

from rag.sources import check_access

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK%010d.json"
CONTACT_ENV = "SEC_CONTACT_EMAIL"
_TICKER = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
_EMAIL = re.compile(r"^[^@\s<>\"']{1,64}@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)+$")

#: (key, Persian title, unit kind, candidate us-gaap concepts in priority order, flow?)
METRICS = (
    ("revenue", "درآمد کل", "USD", ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues",
                                    "SalesRevenueNet"), True),
    ("operating_income", "سود عملیاتی", "USD", ("OperatingIncomeLoss",), True),
    ("net_income", "سود خالص", "USD", ("NetIncomeLoss",), True),
    ("eps_diluted", "سود رقیق‌شدهٔ هر سهم", "USD/shares", ("EarningsPerShareDiluted",), True),
    ("operating_cash_flow", "جریان نقد عملیاتی", "USD", ("NetCashProvidedByUsedInOperatingActivities",), True),
    ("assets", "جمع دارایی‌ها", "USD", ("Assets",), False),
    ("liabilities", "جمع بدهی‌ها", "USD", ("Liabilities",), False),
    ("equity", "حقوق صاحبان سهام", "USD", ("StockholdersEquity",), False),
)


class SecError(RuntimeError):
    """An EDGAR request was refused or failed."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def user_agent(email: Optional[str] = None) -> str:
    """'marfin-llm/0.14 (<contact>)' from the argument or SEC_CONTACT_EMAIL; refuses a non-address."""
    e = str(email if email is not None else os.environ.get(CONTACT_ENV, "")).strip()
    if not _EMAIL.match(e):
        raise SecError("SEC requires a contact e-mail in every request (MEASURED: HTTP 403 without one). "
                       "Set %s to your e-mail address; it is sent only to sec.gov." % CONTACT_ENV)
    return "marfin-llm/0.14 (%s)" % e


def _http_get(url: str, ua: str, timeout: float = 30.0) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "application/json"})
    try:
        with _OPENER.open(req, timeout=timeout) as resp:
            raw = resp.read(30_000_000)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise SecError("SEC has no XBRL facts for this company (HTTP 404)")
        raise SecError("HTTP %s from SEC EDGAR" % exc.code)
    except (urllib.error.URLError, OSError) as exc:
        raise SecError("could not reach SEC EDGAR: %s" % (getattr(exc, "reason", exc),))
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise SecError("SEC EDGAR did not return JSON")


def parse_tickers(payload: Any) -> Dict[str, Dict[str, Any]]:
    """{TICKER: {"cik": int, "title": str}} from company_tickers.json."""
    if not isinstance(payload, dict) or not payload:
        raise SecError("company_tickers.json is not a non-empty object")
    out = {}
    for row in payload.values():
        if not isinstance(row, dict):
            continue
        t, cik, title = str(row.get("ticker") or "").upper(), row.get("cik_str"), row.get("title")
        if _TICKER.match(t) and isinstance(cik, int) and not isinstance(cik, bool) and 0 < cik < 10 ** 10 \
                and isinstance(title, str):
            out.setdefault(t, {"cik": cik, "title": title[:100]})
    if not out:
        raise SecError("company_tickers.json held no usable rows")
    return out


def _days(a: str, b: str) -> Optional[int]:
    try:
        return (datetime.date.fromisoformat(b) - datetime.date.fromisoformat(a)).days
    except (TypeError, ValueError):
        return None


def annual_series(facts: Dict[str, Any], concepts, unit: str, flow: bool) -> Dict[str, Any]:
    """The first concept with annual 10-K values: {concept, points: [{fy_end, value, filed, accn}]}."""
    gaap = facts.get("us-gaap") if isinstance(facts, dict) else None
    if not isinstance(gaap, dict):
        return {"concept": None, "points": []}
    for c in concepts:
        rows = ((gaap.get(c) or {}).get("units") or {}).get(unit)
        if not isinstance(rows, list):
            continue
        best: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            if not isinstance(r, dict) or r.get("form") != "10-K" or r.get("fp") != "FY":
                continue
            end, v, filed = r.get("end"), r.get("val"), str(r.get("filed") or "")
            if not isinstance(end, str) or isinstance(v, bool) or not isinstance(v, (int, float)) \
                    or not math.isfinite(float(v)):
                continue
            if flow:
                span = _days(r.get("start"), end)
                if span is None or not 350 <= span <= 380:
                    continue
            prev = best.get(end)
            if prev is None or filed > prev["filed"]:
                best[end] = {"fy_end": end, "value": float(v), "filed": filed, "accn": str(r.get("accn") or "")}
        if best:
            return {"concept": c, "points": [best[k] for k in sorted(best)]}
    return {"concept": None, "points": []}


def parse_companyfacts(payload: Any, years: int = 6) -> Dict[str, Any]:
    if not isinstance(payload, dict) or not isinstance(payload.get("facts"), dict):
        raise SecError("companyfacts payload has no 'facts' object")
    cik, name = payload.get("cik"), payload.get("entityName")
    metrics = []
    for key, title, unit, concepts, flow in METRICS:
        s = annual_series(payload["facts"], concepts, unit, flow)
        metrics.append({"key": key, "title_fa": title, "unit": unit, "concept": s["concept"],
                        "points": s["points"][-years:]})
    if not any(m["points"] for m in metrics):
        raise SecError("no annual 10-K figures in this company's XBRL facts")
    return {"cik": cik, "name": str(name or "")[:120], "metrics": metrics}


def fetch_tickers(ua: str, http_get: Optional[Callable] = None) -> Dict[str, Dict[str, Any]]:
    check_access("sec_edgar_submissions", user_agent=ua)
    return parse_tickers((http_get or _http_get)(TICKERS_URL, ua))


def fetch_fundamentals(cik: int, ua: str, http_get: Optional[Callable] = None, years: int = 6) -> Dict[str, Any]:
    if isinstance(cik, bool) or not isinstance(cik, int) or not 0 < cik < 10 ** 10:
        raise SecError("CIK must be a positive integer of at most 10 digits, got %r" % (cik,))
    check_access("sec_edgar_xbrl", user_agent=ua)
    return parse_companyfacts((http_get or _http_get)(FACTS_URL % cik, ua), years=years)
