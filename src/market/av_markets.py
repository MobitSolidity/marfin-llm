"""
Alpha Vantage: forex pairs, US stock quotes and ticker search (D-0142).

Same provider, same licence position and the SAME 25-requests/day budget as
market/alpha_vantage.py (enabled on USER_ACCEPTED_RISK, END_OF_DAY only). This
module adds three FREE functions, each checked against the official
documentation on 2026-10-28 (alphavantage.co/documentation):

  FX_DAILY       daily OHLC of any currency pair       (free; FX_INTRADAY is Premium)
  GLOBAL_QUOTE   latest price of one ticker            (free; "by default ... updated
                                                         at the end of each trading day")
  SYMBOL_SEARCH  ticker search by keyword              (free utility)

Response shapes MEASURED 2026-10-28 with the documented demo URLs:
  FX_DAILY      {"Meta Data": {...}, "Time Series FX (Daily)": {date: {"1. open"...}}}
  GLOBAL_QUOTE  {"Global Quote": {"01. symbol", "05. price", "07. latest trading day",
                 "08. previous close", "09. change", "10. change percent": "1.2068%"}}
  SYMBOL_SEARCH {"bestMatches": [{"1. symbol", "2. name", "3. type", "4. region",
                 "8. currency", ...}]}
Every failure this API has arrives as HTTP 200 with an "Information" / "Note" /
"Error Message" string (MEASURED), so the BODY is inspected, never the status.
"""
from __future__ import annotations

import math
import re
import urllib.parse
from typing import Any, Callable, Dict, List, Optional

from market import alpha_vantage as AV
from market.quotes import assert_provider_usable, assert_tier_supports

FUNCTIONS = {"FX_DAILY": "Time Series FX (Daily)", "GLOBAL_QUOTE": "Global Quote",
             "SYMBOL_SEARCH": "bestMatches"}
_CCY = re.compile(r"^[A-Z]{3}$")
_KEYWORDS = re.compile(r"^[A-Za-z0-9 .&\-]{1,40}$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
#: Pairs offered as one-click chips in the UI (any valid pair can be typed).
MAJOR_PAIRS = (("EUR", "USD"), ("GBP", "USD"), ("USD", "JPY"), ("USD", "CHF"), ("AUD", "USD"),
               ("USD", "CAD"), ("NZD", "USD"), ("USD", "TRY"), ("USD", "CNY"))
#: Gold (XAU) is NOT offered: the docs route precious metals to a separate function, and
#: FX_DAILY with XAU was never verified (D-0142: no unverified pairs).


def build_url(function: str, api_key: str, **params: str) -> str:
    if function not in FUNCTIONS:
        raise AV.AlphaVantageError("function %r is not permitted here; allowed: %s"
                                   % (function, ", ".join(sorted(FUNCTIONS))))
    q = dict(params, function=function, apikey=api_key)
    return AV.BASE_URL + "?" + urllib.parse.urlencode(sorted(q.items()))


def _pair(frm: str, to: str):
    a, b = str(frm or "").strip().upper(), str(to or "").strip().upper()
    if not (_CCY.match(a) and _CCY.match(b)):
        raise AV.AlphaVantageError("a currency pair needs two 3-letter codes, got %r/%r" % (frm, to))
    if a == b:
        raise AV.AlphaVantageError("a pair needs two different currencies")
    return a, b


def _symbol(sym: str) -> str:
    s = str(sym or "").strip().upper()
    if not AV._SYMBOL_RE.match(s):
        raise AV.AlphaVantageError("%r is not a ticker symbol" % (sym,))
    return s


def _signed(raw: Any, field: str) -> float:
    try:
        v = float(str(raw).strip().rstrip("%"))
    except (TypeError, ValueError):
        raise AV.AlphaVantageError("%s is not a number: %r" % (field, raw))
    if not math.isfinite(v):
        raise AV.AlphaVantageError("%s is not finite: %r" % (field, raw))
    return v


def _refuse_errors(payload: Any) -> None:
    if not isinstance(payload, dict):
        raise AV.AlphaVantageError("expected a JSON object from Alpha Vantage")
    for k in AV.ERROR_KEYS:
        if k in payload:
            raise AV.AlphaVantageError("Alpha Vantage returned HTTP 200 with no data: %s=%r"
                                       % (k, str(payload[k])[:200]))


def parse_fx_daily(payload: Any) -> Dict[str, Any]:
    series = AV.assert_usable_response(payload, FUNCTIONS["FX_DAILY"], "FX_DAILY")
    meta = payload.get("Meta Data") or {}
    rows = []
    for d in sorted(series):
        if not _DATE.match(str(d)):
            raise AV.AlphaVantageError("FX row date %r is not YYYY-MM-DD" % (d,))
        bar = series[d]
        if not isinstance(bar, dict):
            raise AV.AlphaVantageError("FX row %s is not an object" % d)
        rows.append({"date": d, "open": AV._num(bar.get("1. open"), "open", d),
                     "high": AV._num(bar.get("2. high"), "high", d), "low": AV._num(bar.get("3. low"), "low", d),
                     "close": AV._num(bar.get("4. close"), "close", d)})
    for r in rows:
        if not r["low"] <= min(r["open"], r["close"]) <= max(r["open"], r["close"]) <= r["high"]:
            raise AV.AlphaVantageError("FX bar %s is inconsistent (low/high do not bracket open/close)" % r["date"])
    return {"from": str(meta.get("2. From Symbol") or ""), "to": str(meta.get("3. To Symbol") or ""),
            "last_refreshed": str(meta.get("5. Last Refreshed") or ""), "rows": rows}


def parse_quote(payload: Any) -> Dict[str, Any]:
    q = AV.assert_usable_response(payload, FUNCTIONS["GLOBAL_QUOTE"], "GLOBAL_QUOTE")
    day = str(q.get("07. latest trading day") or "")
    if not _DATE.match(day):
        raise AV.AlphaVantageError("quote has no valid trading day: %r" % (day,))
    sym = str(q.get("01. symbol") or "")
    if not AV._SYMBOL_RE.match(sym):
        raise AV.AlphaVantageError("quote has no valid symbol: %r" % (sym,))
    out = {"symbol": sym, "day": day, "price": AV._num(q.get("05. price"), "price", day),
           "open": AV._num(q.get("02. open"), "open", day), "high": AV._num(q.get("03. high"), "high", day),
           "low": AV._num(q.get("04. low"), "low", day), "prev_close": AV._num(q.get("08. previous close"), "previous close", day),
           "volume": AV._num(q.get("06. volume"), "volume", day),
           "change": _signed(q.get("09. change"), "change"), "change_pct": _signed(q.get("10. change percent"), "change percent")}
    if abs((out["price"] - out["prev_close"]) - out["change"]) > max(0.011, 1e-6 * out["price"]):
        raise AV.AlphaVantageError("quote for %s is inconsistent: price - previous close != change" % sym)
    return out


def parse_search(payload: Any) -> List[Dict[str, Any]]:
    _refuse_errors(payload)
    m = payload.get("bestMatches")
    if not isinstance(m, list):
        raise AV.AlphaVantageError("search response has no bestMatches list")
    out = []
    for r in m:
        if not isinstance(r, dict):
            continue
        sym = str(r.get("1. symbol") or "").strip().upper()
        if not AV._SYMBOL_RE.match(sym):
            continue
        out.append({"symbol": sym, "name": str(r.get("2. name") or "")[:80], "type": str(r.get("3. type") or "")[:20],
                    "region": str(r.get("4. region") or "")[:40], "currency": str(r.get("8. currency") or "")[:5]})
    return out


def _fetch(function: str, params: Dict[str, str], http_get: Optional[Callable] = None,
           budget: Optional[AV.RequestBudget] = None, api_key: Optional[str] = None) -> Any:
    assert_provider_usable(AV.PROVIDER_KEY)               # licence gate before anything else
    assert_tier_supports(AV.PROVIDER_KEY, "END_OF_DAY")   # tier gate before the budget is spent
    key = AV.get_api_key(api_key)
    url = build_url(function, key, **params)
    (budget if budget is not None else AV.BUDGET).spend("%s %s" % (function, " ".join(sorted(params.values()))))
    return (http_get or AV._http_get)(url, key)


def fetch_fx_daily(frm: str, to: str, **kw) -> Dict[str, Any]:
    a, b = _pair(frm, to)
    return parse_fx_daily(_fetch("FX_DAILY", {"from_symbol": a, "to_symbol": b}, **kw))


def fetch_quote(symbol: str, **kw) -> Dict[str, Any]:
    return parse_quote(_fetch("GLOBAL_QUOTE", {"symbol": _symbol(symbol)}, **kw))


def fetch_search(keywords: str, **kw) -> List[Dict[str, Any]]:
    k = str(keywords or "").strip()
    if not _KEYWORDS.match(k):
        raise AV.AlphaVantageError("search keywords must be 1-40 letters, digits, spaces or .&-")
    return parse_search(_fetch("SYMBOL_SEARCH", {"keywords": k}, **kw))
