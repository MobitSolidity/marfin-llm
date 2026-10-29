# -*- coding: utf-8 -*-
"""
Offline stand-ins for the D-0141 data sources (ECB, BIS, FRED, World Bank, Alpha Vantage).

Each fake reads the REAL request URL the client built and answers in the provider's REAL
payload shape (MEASURED 2026-10-27), so the clients' URL builders and parsers are both
exercised. Numbers are fixtures, not market data.
"""
import datetime
import re
import urllib.parse

FRED_KEY = "0123456789abcdef0123456789abcdef"     # shape of a FRED key; not a real one

ECB_RATES = {"USD": [("2026-10-23", 1.1193), ("2026-10-26", 1.1188)],
             "JPY": [("2026-10-23", 175.51), ("2026-10-26", 176.15)],
             "TRY": [("2026-10-23", 55.6715), ("2026-10-26", 55.6746)],
             "GBP": [("2026-10-23", 0.83728), ("2026-10-26", 0.8382)],
             # a currency whose last fix is a DIFFERENT day from the dollar's
             "CHF": [("2026-10-22", 0.9250), ("2026-10-23", 0.9243)]}
ECB_HEAD = "KEY,FREQ,CURRENCY,CURRENCY_DENOM,EXR_TYPE,EXR_SUFFIX,TIME_PERIOD,OBS_VALUE,OBS_STATUS\r\n"

BIS_RATES = [("US", "2026-10-20", "3.875"), ("TR", "2026-10-16", "37"), ("XM", "2026-10-20", "2.5"),
             ("GB", "2026-10-19", "3.75"), ("JP", "2026-10-20", "1.25"), ("CH", "2026-10-20", "0"),
             ("DE", "1998-12-31", "3"), ("PH", "2026-10-18", "NaN")]

WB = {("IRN", "FP.CPI.TOTL.ZG"): [(2025, 42.17), (2024, 32.46), (2023, None)],
      ("TUR", "FP.CPI.TOTL.ZG"): [(2025, 34.88), (2024, 58.51)],
      ("USA", "FP.CPI.TOTL.ZG"): [(2024, 2.95), (2023, 4.12)]}

CALLS = []


def ecb_get(url, timeout=20.0):
    CALLS.append(("ecb", url))
    m = re.search(r"/EXR/D\.([A-Z+]+)\.EUR\.SP00\.A\?", url)
    n = int(urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)["lastNObservations"][0])
    out = [ECB_HEAD]
    for c in m.group(1).split("+"):
        for d, v in ECB_RATES.get(c, [])[-n:]:
            out.append("EXR.D.%s.EUR.SP00.A,D,%s,EUR,SP00,A,%s,%s,A\r\n" % (c, c, d, v))
    return "".join(out)


def bis_get(url, timeout=20.0):
    CALLS.append(("bis", url))
    assert "/WS_CBPOL/D." in url, url
    rows = ["FREQ,REF_AREA,UNIT_MEASURE,TIME_PERIOD,OBS_VALUE\r\n"]
    rows += ["D,%s,368,%s,%s\r\n" % r for r in BIS_RATES]
    return "".join(rows)


def fred_get(url, key, timeout=20.0):
    CALLS.append(("fred", url))
    q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
    sid, limit = q["series_id"][0], int(q["limit"][0])
    base = {"DGS10": 5.0, "DCOILWTICO": 107.89, "DTWEXBGS": 121.32}.get(sid, 4.0)
    d0 = datetime.date(2026, 10, 23)
    obs = [{"date": (d0 - datetime.timedelta(days=i)).isoformat(),
            "value": "." if i == 3 else "%.2f" % (base - 0.05 * i)} for i in range(limit)]
    return {"observations": obs}


def wb_get(url, timeout=20.0):
    CALLS.append(("wb", url))
    m = re.search(r"/country/([A-Z;]+)/indicator/([A-Z0-9.]+)\?", url)
    rows = []
    for c in m.group(1).split(";"):
        for year, v in WB.get((c, m.group(2)), []):
            rows.append({"indicator": {"id": m.group(2), "value": "x"}, "country": {"id": c[:2], "value": c},
                         "countryiso3code": c, "date": str(year), "value": v})
    return [{"page": 1, "total": len(rows)}, rows]


class _Q(object):
    def __init__(self, d, v):
        self.timestamp, self.last = d, v


def av_fetch(sym):
    CALLS.append(("av", sym))
    if sym == "BAD":
        raise ValueError("Alpha Vantage refused: invalid symbol")
    return [_Q("2026-10-%02d" % d, 100.0 + d) for d in range(1, 24)]


# ---------------------------------------------------------------------------
# D-0142: CoinGecko, Alpha Vantage (FX_DAILY / GLOBAL_QUOTE / SYMBOL_SEARCH), SEC EDGAR.
# Shapes MEASURED 2026-10-28 from live calls (market_chart from the official schema: the
# live call hit the keyless 429). Numbers are fixtures.
# ---------------------------------------------------------------------------
SEC_CONTACT = "owner@example.com"
CG_COINS = [("bitcoin", "btc", "Bitcoin", 81036, 1, 0.57665, -3.4086),
            ("ethereum", "eth", "Ethereum", 3010.5, 2, -1.25, 2.5),
            ("tether", "usdt", "Tether", 1.0002, 3, 0.01, -0.02),
            ("deadcoin", "dead", "Dead", None, 4, None, None)]          # no price: must be skipped


def cg_get(url):
    CALLS.append(("cg", url))
    u = urllib.parse.urlsplit(url)
    q = urllib.parse.parse_qs(u.query)
    if u.path.endswith("/coins/markets"):
        n = int(q["per_page"][0])
        return [{"id": i, "symbol": s, "name": nm, "current_price": p, "market_cap": (p or 0) * 1e7,
                 "market_cap_rank": r, "total_volume": 2.6e10, "high_24h": p and p * 1.01, "low_24h": p and p * 0.99,
                 "price_change_percentage_24h_in_currency": c24, "price_change_percentage_7d_in_currency": c7,
                 "last_updated": "2026-10-28T20:42:55.000Z"} for i, s, nm, p, r, c24, c7 in CG_COINS[:n]]
    if u.path.endswith("/global"):
        return {"data": {"active_cryptocurrencies": 22563, "markets": 1516, "updated_at": 1793220292,
                         "total_market_cap": {"usd": 2730249601050.187}, "total_volume": {"usd": 9.1e10},
                         "market_cap_percentage": {"btc": 59.46347482672264, "eth": 11.2},
                         "market_cap_change_percentage_24h_usd": -2.2356978937414533}}
    m = re.search(r"/coins/([a-z0-9-]+)/market_chart$", u.path)
    if m:
        if m.group(1) == "limited":
            raise _cg_error("CoinGecko rate limit reached (status 429).")
        d0 = 1790000000000
        return {"prices": [[d0 + i * 86400000, 70000.0 + 100 * i] for i in range(int(q["days"][0]) + 1)],
                "market_caps": [], "total_volumes": []}
    raise AssertionError(url)


def _cg_error(msg):
    from market.coingecko import CoinGeckoError
    return CoinGeckoError(msg)


def av_get(url, key):
    CALLS.append(("av2", url))
    q = {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlsplit(url).query).items()}
    assert q["apikey"] == key, "the key must travel only as apikey"
    f = q["function"]
    if f == "FX_DAILY":
        if q["from_symbol"] == "XXX":
            return {"Error Message": "Invalid API call."}
        d0 = datetime.date(2026, 10, 27)
        ts = {}
        for i in range(30):
            c = 1.1122 + 0.001 * i
            ts[(d0 - datetime.timedelta(days=i)).isoformat()] = {
                "1. open": "%.5f" % (c + 0.0005), "2. high": "%.5f" % (c + 0.003),
                "3. low": "%.5f" % (c - 0.001), "4. close": "%.5f" % c}
        return {"Meta Data": {"2. From Symbol": q["from_symbol"], "3. To Symbol": q["to_symbol"],
                              "5. Last Refreshed": "2026-10-27"}, "Time Series FX (Daily)": ts}
    if f == "GLOBAL_QUOTE":
        if q["symbol"] == "NOPE":
            return {"Global Quote": {}}
        if q["symbol"] == "LIMIT":
            return {"Information": "Thank you for using Alpha Vantage! Our standard API rate limit is 25 requests per day."}
        return {"Global Quote": {"01. symbol": q["symbol"], "02. open": "248.7600", "03. high": "253.8500",
                                 "04. low": "247.6800", "05. price": "253.2700", "06. volume": "3686593",
                                 "07. latest trading day": "2026-10-28", "08. previous close": "250.2500",
                                 "09. change": "3.0200", "10. change percent": "1.2068%"}}
    if f == "SYMBOL_SEARCH":
        return {"bestMatches": [{"1. symbol": "TSCO.LON", "2. name": "Tesco PLC", "3. type": "Equity",
                                 "4. region": "United Kingdom", "8. currency": "GBX"},
                                {"1. symbol": "TSCDF", "2. name": "Tesco plc", "3. type": "Equity",
                                 "4. region": "United States", "8. currency": "USD"},
                                {"1. symbol": "<bad>", "2. name": "x"}]}
    raise AssertionError(url)


def sec_get(url, ua):
    CALLS.append(("sec", url))
    assert SEC_CONTACT in ua, "SEC requires the contact address in the User-Agent"
    if url.endswith("/company_tickers.json"):
        return {"0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"},
                "1": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
                "2": {"cik_str": 999, "ticker": "EMPTY", "title": "Empty Co"}}
    if url.endswith("CIK0000000999.json"):
        return {"cik": 999, "entityName": "Empty Co", "facts": {"us-gaap": {}}}
    assert url.endswith("CIK0000320193.json"), url

    def fy(end, v, filed="2025-10-31", start=None):
        r = {"end": end, "val": v, "fy": int(end[:4]), "fp": "FY", "form": "10-K", "filed": filed, "accn": "acc-" + end}
        if start:
            r["start"] = start
        return r
    years = [("2023-10-01", "2024-09-28"), ("2024-09-29", "2025-09-27")]
    flows = {"RevenueFromContractWithCustomerExcludingAssessedTax": (391035000000, 416161000000),
             "NetIncomeLoss": (93736000000, 112010000000), "OperatingIncomeLoss": (123216000000, 133050000000),
             "NetCashProvidedByUsedInOperatingActivities": (118254000000, 111482000000)}
    gaap = {k: {"units": {"USD": [fy(e, v, start=s) for (s, e), v in zip(years, vals)]
                          + [dict(fy("2025-09-27", 1, start="2025-06-29"))]}}       # a quarter inside a 10-K
            for k, vals in flows.items()}
    gaap["EarningsPerShareDiluted"] = {"units": {"USD/shares": [fy(e, v, start=s) for (s, e), v in zip(years, (6.08, 7.46))]}}
    for k, v in (("Assets", 359241000000), ("Liabilities", 285508000000), ("StockholdersEquity", 73733000000)):
        gaap[k] = {"units": {"USD": [fy("2025-09-27", v)]}}
    return {"cik": 320193, "entityName": "Apple Inc.", "facts": {"us-gaap": gaap}}


def hub(**kw):
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
    from rag import datahub as DH
    args = dict(ecb_get=ecb_get, bis_get=bis_get, fred_get=fred_get, wb_get=wb_get, av_fetch=av_fetch,
                fred_key=FRED_KEY, sleep=lambda s: None, cg_get=cg_get, av_get=av_get, sec_get=sec_get,
                sec_contact=SEC_CONTACT)
    args.update(kw)
    return DH.DataHub(**args)
