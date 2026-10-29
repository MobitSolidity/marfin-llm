"""
CoinGecko crypto market data (D-0142).

The owner chose CoinGecko on 2026-10-28 for crypto coverage, accepting its
attribution condition. Terms read the same day (coingecko.com/en/api_terms):
display "Powered by CoinGecko" (REQUIRED_NOTICES["coingecko"]) and never resell
or redistribute access. Kraken was not chosen (its terms exclude anyone in
Iran); Binance's terms could not be read, so it is not used.

Shapes are MEASURED 2026-10-28 from live calls (/coins/markets, /global) or
VERIFIED from the official OpenAPI schema (/coins/{id}/market_chart -- the live
call returned HTTP 429, the keyless limit, so the schema is the source).

Rules, as for every other client in this project:
  * the registry gate (check_access) runs BEFORE any network call;
  * a missing value is skipped, never shown as 0; a non-finite, negative or
    boolean number is refused;
  * redirects are refused (the optional Demo key travels in a header);
  * a 429 is reported as a rate limit and NOT retried (retrying a shared,
    per-IP keyless limit only extends the block).
"""
from __future__ import annotations

import datetime
import json
import math
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, List, Optional

from rag.sources import check_access

SOURCE_KEY = "coingecko"
BASE_URL = "https://api.coingecko.com/api/v3"
KEY_ENV = "COINGECKO_DEMO_API_KEY"
#: vs currencies offered in the UI (all listed by /simple/supported_vs_currencies).
VS_CURRENCIES = ("usd", "eur", "gbp", "jpy", "try", "aed", "btc", "eth")
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_VS_RE = re.compile(r"^[a-z]{3,5}$")
_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{10,80}$")


class CoinGeckoError(RuntimeError):
    """A CoinGecko request was refused or failed. Never carries the key."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def _num(value: Any, field: str, allow_negative: bool = False) -> Optional[float]:
    """A finite number, None for a missing value; refuses bools, strings, inf/NaN."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CoinGeckoError("%s is not a number: %r" % (field, value))
    v = float(value)
    if not math.isfinite(v):
        raise CoinGeckoError("%s is not finite: %r" % (field, value))
    if v < 0 and not allow_negative:
        raise CoinGeckoError("%s is negative: %r" % (field, value))
    return v


def _vs(vs: str) -> str:
    v = str(vs or "").strip().lower()
    if not _VS_RE.match(v):
        raise CoinGeckoError("vs currency %r must be 3-5 lower-case letters" % (vs,))
    return v


def markets_url(vs: str = "usd", per_page: int = 50, page: int = 1) -> str:
    if isinstance(per_page, bool) or not isinstance(per_page, int) or not 1 <= per_page <= 250:
        raise CoinGeckoError("per_page must be 1..250 (documented maximum), got %r" % (per_page,))
    if isinstance(page, bool) or not isinstance(page, int) or not 1 <= page <= 100:
        raise CoinGeckoError("page must be 1..100, got %r" % (page,))
    q = urllib.parse.urlencode({"vs_currency": _vs(vs), "order": "market_cap_desc", "per_page": per_page,
                                "page": page, "sparkline": "false", "price_change_percentage": "24h,7d"})
    return "%s/coins/markets?%s" % (BASE_URL, q)


def global_url() -> str:
    return BASE_URL + "/global"


def chart_url(coin_id: str, vs: str = "usd", days: int = 90) -> str:
    cid = str(coin_id or "").strip()
    if not _ID_RE.match(cid):
        raise CoinGeckoError("coin id %r is not a CoinGecko id (lower-case letters, digits, '-')" % (coin_id,))
    if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 365:
        raise CoinGeckoError("days must be 1..365 (the free plan's history window), got %r" % (days,))
    q = urllib.parse.urlencode({"vs_currency": _vs(vs), "days": days, "interval": "daily"})
    return "%s/coins/%s/market_chart?%s" % (BASE_URL, cid, q)


def _demo_key() -> Optional[str]:
    k = str(os.environ.get(KEY_ENV, "")).strip()
    if not k:
        return None
    if not _KEY_RE.match(k):
        raise CoinGeckoError("%s does not look like a CoinGecko key; refusing to send it" % KEY_ENV)
    return k


def _http_get(url: str, timeout: float = 20.0) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "marfin-llm/0.14 (personal research)",
                                               "Accept": "application/json"})
    key = _demo_key()
    if key:
        req.add_header("x-cg-demo-api-key", key)          # header, as the docs recommend
    try:
        with _OPENER.open(req, timeout=timeout) as resp:
            raw = resp.read(10_000_000)
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise CoinGeckoError("CoinGecko rate limit reached (status 429). The keyless limit is about 5 "
                                 "calls a minute per IP; wait a minute, or set %s (free Demo key)." % KEY_ENV)
        if 300 <= exc.code < 400:
            raise CoinGeckoError("CoinGecko answered with a redirect (status %d); not followed" % exc.code)
        raise CoinGeckoError("HTTP %s from CoinGecko" % exc.code)
    except (urllib.error.URLError, OSError) as exc:
        raise CoinGeckoError("could not reach CoinGecko: %s" % (getattr(exc, "reason", exc),))
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise CoinGeckoError("CoinGecko did not return JSON")


def parse_markets(payload: Any) -> List[Dict[str, Any]]:
    """Rows of /coins/markets. A coin without a price is skipped, never shown as 0."""
    if isinstance(payload, dict) and "status" in payload:
        raise CoinGeckoError("CoinGecko refused the request: %s" % str(payload.get("status"))[:200])
    if not isinstance(payload, list):
        raise CoinGeckoError("expected a list of coins, got %s" % type(payload).__name__)
    out = []
    for r in payload:
        if not isinstance(r, dict):
            raise CoinGeckoError("a market row is not an object")
        cid, sym, name = r.get("id"), r.get("symbol"), r.get("name")
        if not (isinstance(cid, str) and _ID_RE.match(cid) and isinstance(sym, str) and isinstance(name, str)):
            raise CoinGeckoError("a market row lacks a valid id/symbol/name: %r" % (cid,))
        price = _num(r.get("current_price"), "current_price of %s" % cid)
        if price is None or price == 0:
            continue
        rank = r.get("market_cap_rank")
        out.append({"id": cid, "symbol": sym.upper()[:12], "name": name[:60], "price": price,
                    "rank": rank if isinstance(rank, int) and not isinstance(rank, bool) and rank > 0 else None,
                    "market_cap": _num(r.get("market_cap"), "market_cap of %s" % cid),
                    "volume": _num(r.get("total_volume"), "total_volume of %s" % cid),
                    "high_24h": _num(r.get("high_24h"), "high_24h of %s" % cid),
                    "low_24h": _num(r.get("low_24h"), "low_24h of %s" % cid),
                    "change_24h": _num(r.get("price_change_percentage_24h_in_currency"), "24h change", True),
                    "change_7d": _num(r.get("price_change_percentage_7d_in_currency"), "7d change", True),
                    "last_updated": str(r.get("last_updated") or "")[:20] or None})
    if not out:
        raise CoinGeckoError("CoinGecko returned no priced coins")
    return out


def parse_global(payload: Any) -> Dict[str, Any]:
    d = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(d, dict):
        raise CoinGeckoError("expected {'data': {...}} from /global")
    caps, pct = d.get("total_market_cap"), d.get("market_cap_percentage")
    if not isinstance(caps, dict) or not isinstance(pct, dict):
        raise CoinGeckoError("/global lacks total_market_cap / market_cap_percentage")
    upd = d.get("updated_at")
    when = (datetime.datetime.fromtimestamp(upd, datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            if isinstance(upd, (int, float)) and not isinstance(upd, bool) and upd > 0 else None)
    n = d.get("active_cryptocurrencies")
    return {"total_market_cap_usd": _num(caps.get("usd"), "total_market_cap.usd"),
            "total_volume_usd": _num((d.get("total_volume") or {}).get("usd"), "total_volume.usd"),
            "btc_dominance": _num(pct.get("btc"), "market_cap_percentage.btc"),
            "eth_dominance": _num(pct.get("eth"), "market_cap_percentage.eth"),
            "change_24h": _num(d.get("market_cap_change_percentage_24h_usd"), "24h market-cap change", True),
            "active": n if isinstance(n, int) and not isinstance(n, bool) else None, "updated": when}


def parse_chart(payload: Any) -> List[Dict[str, Any]]:
    """Daily prices from /market_chart, oldest first, one point per UTC date (the last one wins)."""
    if isinstance(payload, dict) and "status" in payload and "prices" not in payload:
        raise CoinGeckoError("CoinGecko refused the request: %s" % str(payload.get("status"))[:200])
    prices = payload.get("prices") if isinstance(payload, dict) else None
    if not isinstance(prices, list):
        raise CoinGeckoError("expected {'prices': [[ms, price], ...]}")
    by_day: Dict[str, float] = {}
    for p in prices:
        if not (isinstance(p, list) and len(p) == 2):
            raise CoinGeckoError("a price point is not [timestamp, price]: %r" % (p,))
        ms = _num(p[0], "timestamp")
        v = _num(p[1], "price")
        if ms is None or v is None or v == 0:
            continue
        day = datetime.datetime.fromtimestamp(ms / 1000.0, datetime.timezone.utc).date().isoformat()
        by_day[day] = v
    if len(by_day) < 2:
        raise CoinGeckoError("fewer than two priced days in the chart")
    return [{"date": d, "value": by_day[d]} for d in sorted(by_day)]


def fetch_markets(vs: str = "usd", per_page: int = 50, http_get: Optional[Callable[[str], Any]] = None):
    check_access(SOURCE_KEY)
    return parse_markets((http_get or _http_get)(markets_url(vs, per_page)))


def fetch_global(http_get: Optional[Callable[[str], Any]] = None):
    check_access(SOURCE_KEY)
    return parse_global((http_get or _http_get)(global_url()))


def fetch_chart(coin_id: str, vs: str = "usd", days: int = 90, http_get: Optional[Callable[[str], Any]] = None):
    check_access(SOURCE_KEY)
    return parse_chart((http_get or _http_get)(chart_url(coin_id, vs, days)))
