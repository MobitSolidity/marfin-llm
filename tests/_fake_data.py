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


def hub(**kw):
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
    from rag import datahub as DH
    args = dict(ecb_get=ecb_get, bis_get=bis_get, fred_get=fred_get, wb_get=wb_get, av_fetch=av_fetch,
                fred_key=FRED_KEY, sleep=lambda s: None)
    args.update(kw)
    return DH.DataHub(**args)
