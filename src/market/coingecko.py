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

D-0143 adds the token lookup endpoints, all listed in the official Demo/Keyless
endpoint overview (docs.coingecko.com/demo/reference/endpoint-overview, VERIFIED
2026-10-30) and recorded once each into tests/fixtures/coingecko/ (MEASURED
2026-10-30): /search, /coins/{id} and /coins/{platform}/contract/{address}. An
unknown contract is HTTP 404 {"error":"coin not found"} (MEASURED) and becomes
CoinNotFound, which the resolver reads as "not on this chain", not as a failure.

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


class CoinNotFound(CoinGeckoError):
    """HTTP 404 / {"error": "coin not found"}: CoinGecko has no coin for this id or contract."""


#: D-0143: chains tried for a contract address, in this order (the owner's order).
#: (our key, CoinGecko asset-platform id, label, address kind)
PLATFORMS = (
    ("ethereum", "ethereum", "Ethereum", "evm"),
    ("bsc", "binance-smart-chain", "BNB Smart Chain", "evm"),
    ("polygon", "polygon-pos", "Polygon PoS", "evm"),
    ("base", "base", "Base", "evm"),
    ("arbitrum", "arbitrum-one", "Arbitrum One", "evm"),
    ("solana", "solana", "Solana", "solana"),
    ("tron", "tron", "Tron", "tron"),
)
_PLATFORM_IDS = {p[1]: p for p in PLATFORMS}
_EVM_RE = re.compile(r"^0x[0-9a-f]{40}$")
_B58_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]+$")


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


def search_url(query: str) -> str:
    q = " ".join(str(query or "").split())
    if not 1 <= len(q) <= 64:
        raise CoinGeckoError("a search needs 1..64 characters, got %d" % len(q))
    return "%s/search?%s" % (BASE_URL, urllib.parse.urlencode({"query": q}))


def coin_url(coin_id: str) -> str:
    cid = str(coin_id or "").strip()
    if _ID_RE.match(cid) is None:                      # written apart from chart_url's check on purpose
        raise CoinGeckoError("coin id %r is not a CoinGecko id (lower-case letters, digits, '-')" % (coin_id,))
    q = urllib.parse.urlencode({"localization": "false", "tickers": "false", "market_data": "true",
                                "community_data": "false", "developer_data": "false", "sparkline": "false"})
    return "%s/coins/%s?%s" % (BASE_URL, cid, q)


def contract_url(platform_id: str, address: str) -> str:
    """Only a whitelisted platform, and only an address of that platform's shape, reaches the URL."""
    p = _PLATFORM_IDS.get(platform_id)
    if p is None:
        raise CoinGeckoError("platform %r is not one of %s" % (platform_id, ", ".join(_PLATFORM_IDS)))
    a = str(address or "").strip()
    if p[3] == "evm":
        a = a.lower()
        ok = bool(_EVM_RE.match(a))
    elif p[3] == "solana":
        ok = 32 <= len(a) <= 44 and bool(_B58_RE.match(a))
    else:
        ok = len(a) == 34 and a[:1] == "T" and bool(_B58_RE.match(a))
    if not ok:
        raise CoinGeckoError("%r is not a %s address" % (address, p[2]))
    return "%s/coins/%s/contract/%s" % (BASE_URL, p[1], a)


def _demo_key() -> Optional[str]:
    k = str(os.environ.get(KEY_ENV, "")).strip()
    if not k:
        return None
    if not _KEY_RE.match(k):
        raise CoinGeckoError("%s does not look like a CoinGecko key; refusing to send it" % KEY_ENV)
    return k


def _http_get(url: str, timeout: float = 20.0) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "Andarz/0.15 (personal research)",
                                               "Accept": "application/json"})
    key = _demo_key()
    if key:
        req.add_header("x-cg-demo-api-key", key)          # header, as the docs recommend
    try:
        with _OPENER.open(req, timeout=timeout) as resp:
            raw = resp.read(10_000_000)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise CoinNotFound("CoinGecko has no coin for this request (HTTP 404)")
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


# ---------------------------------------------------------------------------------------------
# D-0143: token lookup (search, coin detail, contract address)
# ---------------------------------------------------------------------------------------------
def _refused(payload: Any) -> None:
    if isinstance(payload, dict):
        if str(payload.get("error") or "").lower() == "coin not found":
            raise CoinNotFound("CoinGecko has no coin for this request")
        st = payload.get("status")
        if isinstance(st, dict) and st.get("error_code") is not None:
            raise CoinGeckoError("CoinGecko refused the request: %s" % str(st.get("error_message") or st)[:200])


def _rank(v: Any) -> Optional[int]:
    return v if isinstance(v, int) and not isinstance(v, bool) and v > 0 else None


def parse_search(payload: Any) -> List[Dict[str, Any]]:
    """Coins of /search, in CoinGecko's order. Only coins: exchanges, categories and NFTs are ignored."""
    _refused(payload)
    coins = payload.get("coins") if isinstance(payload, dict) else None
    if not isinstance(coins, list):
        raise CoinGeckoError("expected {'coins': [...]} from /search")
    out = []
    for c in coins:
        if not isinstance(c, dict):
            raise CoinGeckoError("a search result is not an object")
        cid, sym, name = c.get("id"), c.get("symbol"), c.get("name")
        if not (isinstance(cid, str) and _ID_RE.match(cid) and isinstance(sym, str) and isinstance(name, str)):
            raise CoinGeckoError("a search result lacks a valid id/symbol/name: %r" % (cid,))
        out.append({"id": cid, "symbol": sym.upper()[:16], "name": name[:80], "rank": _rank(c.get("market_cap_rank"))})
    return out


def _cur(md: Dict[str, Any], field: str, vs: str, allow_negative: bool = False) -> Optional[float]:
    v = md.get(field)
    if isinstance(v, dict):
        return _num(v.get(vs), "%s.%s" % (field, vs), allow_negative)
    if v is None:
        return None
    raise CoinGeckoError("%s is not a per-currency object" % field)


def _date(md: Dict[str, Any], field: str, vs: str) -> Optional[str]:
    v = md.get(field)
    d = v.get(vs) if isinstance(v, dict) else None
    return d[:10] if isinstance(d, str) and re.match(r"^\d{4}-\d{2}-\d{2}", d) else None


def _iso(v: Any) -> Optional[str]:
    """CoinGecko's own timestamp, to the second, as 'YYYY-MM-DD HH:MM:SS UTC'; None when absent or malformed."""
    m = re.match(r"^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})", v) if isinstance(v, str) else None
    return "%s %s UTC" % (m.group(1), m.group(2)) if m else None


def parse_coin(payload: Any, vs: str = "usd") -> Dict[str, Any]:
    """
    /coins/{id} or /coins/{platform}/contract/{address}. Every missing figure is None (shown as a
    dash), never 0. Contract addresses come from CoinGecko's own `platforms` map.
    """
    vs = _vs(vs)
    _refused(payload)
    if not isinstance(payload, dict):
        raise CoinGeckoError("expected a coin object")
    cid, sym, name = payload.get("id"), payload.get("symbol"), payload.get("name")
    if not (isinstance(cid, str) and _ID_RE.match(cid) and isinstance(sym, str) and isinstance(name, str)):
        raise CoinGeckoError("the coin object lacks a valid id/symbol/name: %r" % (cid,))
    md = payload.get("market_data")
    if md is not None and not isinstance(md, dict):
        raise CoinGeckoError("market_data is not an object")
    md = md or {}
    plats = payload.get("platforms")
    platforms = {}
    if isinstance(plats, dict):
        for k, v in plats.items():
            if isinstance(k, str) and k and isinstance(v, str) and v.strip():
                platforms[k[:40]] = v.strip()[:120]
    price = _cur(md, "current_price", vs)
    return {
        "id": cid, "symbol": sym.upper()[:16], "name": name[:80], "vs": vs,
        "rank": _rank(payload.get("market_cap_rank")) or _rank(md.get("market_cap_rank")),
        "price": price if price else None,
        "change_24h": _num(md.get("price_change_percentage_24h"), "24h change", True),
        "change_7d": _num(md.get("price_change_percentage_7d"), "7d change", True),
        "market_cap": _cur(md, "market_cap", vs) or None,
        "volume": _cur(md, "total_volume", vs),
        "high_24h": _cur(md, "high_24h", vs), "low_24h": _cur(md, "low_24h", vs),
        "ath": _cur(md, "ath", vs), "ath_date": _date(md, "ath_date", vs),
        "atl": _cur(md, "atl", vs), "atl_date": _date(md, "atl_date", vs),
        "circulating_supply": _num(md.get("circulating_supply"), "circulating_supply"),
        "total_supply": _num(md.get("total_supply"), "total_supply"),
        "max_supply": _num(md.get("max_supply"), "max_supply"),
        "platforms": platforms,
        "asset_platform_id": payload.get("asset_platform_id") if isinstance(payload.get("asset_platform_id"), str) else None,
        "contract_address": payload.get("contract_address") if isinstance(payload.get("contract_address"), str) else None,
        "last_updated": _iso(md.get("last_updated") or payload.get("last_updated")),
    }


def fetch_search(query: str, http_get: Optional[Callable[[str], Any]] = None):
    check_access(SOURCE_KEY)
    return parse_search((http_get or _http_get)(search_url(query)))


def fetch_coin(coin_id: str, vs: str = "usd", http_get: Optional[Callable[[str], Any]] = None):
    check_access(SOURCE_KEY)
    return parse_coin((http_get or _http_get)(coin_url(coin_id)), vs)


def fetch_contract(platform_id: str, address: str, vs: str = "usd", http_get: Optional[Callable[[str], Any]] = None):
    check_access(SOURCE_KEY)
    return parse_coin((http_get or _http_get)(contract_url(platform_id, address)), vs)
