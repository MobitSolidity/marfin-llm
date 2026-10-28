# -*- coding: utf-8 -*-
"""
Multi-source market and economic data for the UI (D-0141).

WHY SEVERAL SOURCES AND NOT ONE
-------------------------------
The owner asked for "whatever source has the most data and covers most markets, or
several sources". No single free source is both licensed for this use and broad. Each
source below is the strongest PERMITTED one for its asset class, and every one of them
was probed on 2026-10-27 before this file was written (MEASURED):

  FX                 ECB Data Portal (EXR)   29 currencies with a 2026 fix, per EUR, daily
  policy rates       BIS WS_CBPOL            49 central banks in one call (40 still current)
  US rates, oil,     FRED                    public-domain series only; S&P 500 EXCLUDED
  gas, dollar index                          because its FRED notes carry a copyright claim
  economies          World Bank Indicators   217 economies, annual (inflation, GDP, debt, ...)
  stocks (EOD)       Alpha Vantage free      25 requests/day, END_OF_DAY, accepted risk
                                             (already enabled, D-0059); needs ALPHAVANTAGE_API_KEY

NOT used, with the reason recorded where it was decided: Twelve Data (paid; owner declined),
TradingView (terms prohibit machine use), Stooq (terms unreadable), the Iranian market
(descoped by the owner, Q3). No free source here is REAL-TIME: every figure is an official
daily fix or older, and the UI says so on every table.

WHAT THIS MODULE NEVER DOES
---------------------------
- No disk cache: results are held in memory for CACHE_TTL_S, then fetched again.
- No interpolation and no zero for a missing value (each client skips it).
- A cross rate or a conversion is COMPUTED from two RETRIEVED fixes of the SAME day, and
  is refused when the two days differ.
- The registry gate (check_access) runs inside each client before any network call.
"""
from __future__ import annotations

import datetime
import time
from typing import Any, Callable, Dict, List, Optional, Sequence

from rag import bis_stats as _bis
from rag import ecb_stats as _ecb
from rag import fred as _fred
from rag import worldbank as _wb
from rag.sources import required_notices

CACHE_TTL_S = 600.0
STALE_DAYS = 400            # a policy-rate series older than this is a discontinued one

#: ISO-2 -> (ISO-3 for the World Bank, Persian name). XM/EMU is the euro area.
COUNTRIES = {
    "US": ("USA", "آمریکا"), "XM": ("EMU", "منطقهٔ یورو"), "GB": ("GBR", "بریتانیا"), "JP": ("JPN", "ژاپن"),
    "CN": ("CHN", "چین"), "CA": ("CAN", "کانادا"), "CH": ("CHE", "سوئیس"), "AU": ("AUS", "استرالیا"),
    "NZ": ("NZL", "نیوزیلند"), "SE": ("SWE", "سوئد"), "NO": ("NOR", "نروژ"), "DK": ("DNK", "دانمارک"),
    "TR": ("TUR", "ترکیه"), "RU": ("RUS", "روسیه"), "IN": ("IND", "هند"), "BR": ("BRA", "برزیل"),
    "MX": ("MEX", "مکزیک"), "AR": ("ARG", "آرژانتین"), "CL": ("CHL", "شیلی"), "CO": ("COL", "کلمبیا"),
    "PE": ("PER", "پرو"), "ZA": ("ZAF", "آفریقای جنوبی"), "SA": ("SAU", "عربستان سعودی"), "KW": ("KWT", "کویت"),
    "IL": ("ISR", "اسرائیل"), "KR": ("KOR", "کرهٔ جنوبی"), "HK": ("HKG", "هنگ‌کنگ"), "ID": ("IDN", "اندونزی"),
    "MY": ("MYS", "مالزی"), "TH": ("THA", "تایلند"), "PH": ("PHL", "فیلیپین"), "PL": ("POL", "لهستان"),
    "CZ": ("CZE", "چک"), "HU": ("HUN", "مجارستان"), "RO": ("ROU", "رومانی"), "RS": ("SRB", "صربستان"),
    "MK": ("MKD", "مقدونیهٔ شمالی"), "IS": ("ISL", "ایسلند"), "MA": ("MAR", "مراکش"), "DE": ("DEU", "آلمان"),
    "FR": ("FRA", "فرانسه"), "IT": ("ITA", "ایتالیا"), "ES": ("ESP", "اسپانیا"), "NL": ("NLD", "هلند"),
    "AT": ("AUT", "اتریش"), "BE": ("BEL", "بلژیک"), "PT": ("PRT", "پرتغال"), "GR": ("GRC", "یونان"),
    "HR": ("HRV", "کرواسی"), "IR": ("IRN", "ایران"), "AE": ("ARE", "امارات"), "EG": ("EGY", "مصر"),
    "PK": ("PAK", "پاکستان"), "QA": ("QAT", "قطر"), "IQ": ("IRQ", "عراق"), "AF": ("AFG", "افغانستان"),
    "AZ": ("AZE", "آذربایجان"), "AM": ("ARM", "ارمنستان"),
}

#: ECB reference-rate currencies with a 2026 fix (MEASURED 2026-10-27), Persian names.
CURRENCIES = {
    "USD": "دلار آمریکا", "JPY": "ین ژاپن", "GBP": "پوند بریتانیا", "CHF": "فرانک سوئیس", "CNY": "یوان چین",
    "TRY": "لیر ترکیه", "AUD": "دلار استرالیا", "CAD": "دلار کانادا", "BRL": "رئال برزیل", "CZK": "کرون چک",
    "DKK": "کرون دانمارک", "HKD": "دلار هنگ‌کنگ", "HUF": "فورینت مجارستان", "IDR": "روپیهٔ اندونزی",
    "ILS": "شِکِل اسرائیل", "INR": "روپیهٔ هند", "ISK": "کرون ایسلند", "KRW": "وون کره", "MXN": "پزوی مکزیک",
    "MYR": "رینگیت مالزی", "NOK": "کرون نروژ", "NZD": "دلار نیوزیلند", "PHP": "پزوی فیلیپین",
    "PLN": "زلوتی لهستان", "RON": "لئوی رومانی", "SEK": "کرون سوئد", "SGD": "دلار سنگاپور",
    "THB": "بات تایلند", "ZAR": "راند آفریقای جنوبی",
}

#: FRED series shown on the markets page. Units are FRED's own strings (MEASURED 2026-10-27,
#: /fred/series); none carries a copyright note. SP500 is deliberately absent: its notes do.
FRED_MARKET = {
    "DGS2": ("Percent", "بازده اوراق ۲سالهٔ خزانهٔ آمریکا", "rates"),
    "DGS10": ("Percent", "بازده اوراق ۱۰سالهٔ خزانهٔ آمریکا", "rates"),
    "DGS30": ("Percent", "بازده اوراق ۳۰سالهٔ خزانهٔ آمریکا", "rates"),
    "T10Y2Y": ("Percent", "شکاف بازده ۱۰ساله منهای ۲ساله", "rates"),
    "DCOILWTICO": ("Dollars per Barrel", "نفت خام WTI", "commodities"),
    "DCOILBRENTEU": ("Dollars per Barrel", "نفت خام برنت", "commodities"),
    "DHHNGSP": ("Dollars per Million BTU", "گاز طبیعی هنری هاب", "commodities"),
    "DTWEXBGS": ("Index Jan 2006=100", "شاخص گستردهٔ دلار آمریکا", "fx"),
}

#: World Bank indicators offered in the UI: id -> (unit, Persian title).
WB_INDICATORS = {
    "FP.CPI.TOTL.ZG": ("percent per year", "تورم قیمت مصرف‌کننده (٪ سالانه)"),
    "NY.GDP.MKTP.KD.ZG": ("percent per year", "رشد اقتصادی (٪ سالانه)"),
    "NY.GDP.MKTP.CD": ("current US dollars", "تولید ناخالص داخلی (دلار)"),
    "NY.GDP.PCAP.CD": ("current US dollars", "تولید سرانه (دلار)"),
    "SL.UEM.TOTL.ZS": ("percent of labour force", "نرخ بیکاری (٪)"),
    "BN.CAB.XOKA.GD.ZS": ("percent of GDP", "حساب جاری (٪ تولید)"),
    "GC.DOD.TOTL.GD.ZS": ("percent of GDP", "بدهی دولت مرکزی (٪ تولید)"),
    "FR.INR.RINR": ("percent", "نرخ بهرهٔ واقعی (٪)"),
    "PA.NUS.FCRF": ("local currency per US dollar", "نرخ رسمی ارز (واحد پول ملی به دلار)"),
    "NE.EXP.GNFS.ZS": ("percent of GDP", "صادرات کالا و خدمات (٪ تولید)"),
}

SOURCES_FA = (
    ("ecb_data_portal", "بانک مرکزی اروپا (ECB)", "نرخ مرجع روزانهٔ ۲۹ ارز در برابر یورو", "بدون کلید"),
    ("bis_statistics", "بانک تسویه‌های بین‌المللی (BIS)", "نرخ بهرهٔ سیاستی ۴۹ بانک مرکزی", "بدون کلید"),
    ("fred", "فدرال رزرو سنت‌لوئیس (FRED)", "اوراق خزانه، نفت، گاز، شاخص دلار، تورم و بیکاری آمریکا",
     "کلید رایگان FRED_API_KEY"),
    ("world_bank_indicators", "بانک جهانی", "۱۰ شاخص اقتصادی برای ۲۱۷ کشور (سالانه)", "بدون کلید"),
    ("alpha_vantage", "Alpha Vantage (رایگان)", "قیمت پایانی روزانهٔ سهام؛ ۲۵ درخواست در روز",
     "کلید رایگان ALPHAVANTAGE_API_KEY"),
)

_TRANSIENT = ("timed out", "timeout", "temporarily", "connection reset", "connection refused", "handshake",
              "remote end closed", "name resolution", "getaddrinfo", "unreachable", "http 429", "http 500",
              "http 502", "http 503", "http 504")
_ERRORS = (_ecb.EcbError, _bis.BisStatsError, _fred.FredError, _wb.WorldBankError)


class DataError(RuntimeError):
    """A data request refused or failed. The message is shown to the user verbatim."""


def _transient(exc):
    return isinstance(exc, _ERRORS) and any(t in str(exc).lower() for t in _TRANSIENT)


class DataHub(object):
    """
    One instance per UI process. Every fetcher is injectable so the whole module is tested
    offline; the defaults are the real clients.
    """

    def __init__(self, ecb_get=None, bis_get=None, fred_get=None, wb_get=None, av_fetch=None,
                 clock: Callable[[], float] = time.time, sleep: Callable[[float], None] = time.sleep,
                 fred_key: Optional[str] = None, ttl: float = CACHE_TTL_S):
        self.ecb_get, self.bis_get, self.fred_get, self.wb_get = ecb_get, bis_get, fred_get, wb_get
        self.av_fetch = av_fetch
        self.clock, self.sleep, self.fred_key, self.ttl = clock, sleep, fred_key, ttl
        self._cache: Dict[Any, Any] = {}
        self.calls = 0                      # network calls actually made (tests read it)

    # -- plumbing ---------------------------------------------------------------------------
    def _cached(self, key, fn):
        hit = self._cache.get(key)
        now = self.clock()
        if hit is not None and now - hit[0] < self.ttl:
            return hit[1]
        for attempt in range(2):
            try:
                self.calls += 1
                val = fn()
                break
            except _ERRORS as exc:
                if attempt == 0 and _transient(exc):
                    self.sleep(2.0)
                    continue
                raise DataError(str(exc))
            except (ValueError, RuntimeError) as exc:      # AccessError, Fact validation
                raise DataError(str(exc))
        self._cache[key] = (now, val)
        return val

    def clear(self):
        self._cache.clear()

    # -- FX (ECB) ------------------------------------------------------------------------------
    def fx(self, last_n: int = 1) -> Dict[str, Any]:
        facts = self._cached(("fx", last_n), lambda: _ecb.fetch(sorted(CURRENCIES), last_n=last_n,
                                                                http_get=self.ecb_get))
        latest: Dict[str, Any] = {}
        for f in facts:
            c = f.currency
            if c not in latest or f.period_end > latest[c].period_end:
                latest[c] = f
        usd = latest.get("USD")
        rows = []
        for c in sorted(latest, key=lambda k: CURRENCIES.get(k, k)):
            f = latest[c]
            same_day = usd is not None and usd.period_end == f.period_end
            rows.append({"ccy": c, "name_fa": CURRENCIES.get(c, c), "per_eur": f.value,
                         "date": f.period_end.isoformat(),
                         # COMPUTED cross: units of c per 1 USD, only from same-day fixes
                         "per_usd": (f.value / usd.value) if same_day else None})
        return {"base": "EUR", "rows": rows, "label": "RETRIEVED (ECB reference rates); per_usd COMPUTED",
                "as_of": max((r["date"] for r in rows), default=None),
                "notices": required_notices(["ecb_data_portal"]),
                "note": "نرخ مرجع رسمی روزانه حدود ساعت ۱۴:۱۵ به وقت اروپای مرکزی؛ قیمت قابل معامله یا لحظه‌ای نیست."}

    def fx_history(self, ccy: str, last_n: int = 60) -> List[Dict[str, Any]]:
        if ccy not in CURRENCIES:
            raise DataError("currency %r is not in the catalogue" % (ccy,))
        facts = self._cached(("fxh", ccy, last_n), lambda: _ecb.fetch([ccy], last_n=last_n,
                                                                      http_get=self.ecb_get))
        return [{"date": f.period_end.isoformat(), "value": f.value} for f in sorted(facts, key=lambda f: f.period_end)]

    def convert(self, amount: float, frm: str, to: str, fx: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """COMPUTED conversion through the euro, from two fixes of the SAME day."""
        if not isinstance(amount, (int, float)) or isinstance(amount, bool) or amount != amount \
                or amount in (float("inf"), float("-inf")):
            raise DataError("amount must be a finite number")
        fx = fx or self.fx()
        per = {r["ccy"]: (r["per_eur"], r["date"]) for r in fx["rows"]}
        per["EUR"] = (1.0, None)
        for c in (frm, to):
            if c not in per:
                raise DataError("currency %r has no ECB reference rate" % (c,))
        (a, da), (b, db) = per[frm], per[to]
        if da and db and da != db:
            raise DataError("the %s fix is from %s and the %s fix from %s; a cross from two different "
                            "days is refused" % (frm, da, to, db))
        rate = b / a                                   # units of `to` per 1 `frm`
        return {"amount": amount, "from": frm, "to": to, "rate": rate, "result": amount * rate,
                "date": da or db, "label": "COMPUTED from ECB reference rates (via EUR)"}

    # -- central-bank policy rates (BIS) -------------------------------------------------------
    def policy_rates(self) -> Dict[str, Any]:
        facts = self._cached(("cbpol",), lambda: _bis.fetch_per_area("WS_CBPOL", "D.", "Percent per annum",
                                                                    last_n=1, http_get=self.bis_get))
        latest: Dict[str, Any] = {}
        for f in facts:
            if f.entity not in latest or f.period_end > latest[f.entity].period_end:
                latest[f.entity] = f
        newest = max((f.period_end for f in latest.values()), default=None)
        rows = []
        for area, f in latest.items():
            stale = newest is not None and (newest - f.period_end).days > STALE_DAYS
            rows.append({"area": area, "name_fa": COUNTRIES.get(area, (None, area))[1], "rate": f.value,
                         "date": f.period_end.isoformat(), "stale": stale})
        rows.sort(key=lambda r: (r["stale"], -r["rate"]))
        return {"rows": rows, "n_current": sum(1 for r in rows if not r["stale"]),
                "label": "RETRIEVED (BIS central bank policy rates)", "as_of": newest.isoformat() if newest else None,
                "notices": required_notices(["bis_statistics"]),
                "note": "سری‌هایی که بیش از %d روز به‌روز نشده‌اند (مثل کشورهای عضو یورو پیش از ۱۹۹۹) "
                        "جدا نشان داده می‌شوند." % STALE_DAYS}

    # -- FRED market series ----------------------------------------------------------------------
    def fred_series(self, series: str, limit: int = 60) -> Dict[str, Any]:
        if series not in FRED_MARKET:
            raise DataError("series %r is not in the markets catalogue" % (series,))
        unit, title, group = FRED_MARKET[series]
        facts = self._cached(("fred", series, limit), lambda: _fred.fetch_observations(
            series, unit, api_key=self.fred_key, limit=limit, sort_order="desc", http_get=self.fred_get))
        pts = [{"date": f.period_end.isoformat(), "value": f.value} for f in sorted(facts, key=lambda f: f.period_end)]
        if not pts:
            raise DataError("FRED returned no observation for %s" % series)
        return {"series": series, "title_fa": title, "unit": unit, "group": group, "points": pts,
                "last": pts[-1], "label": "RETRIEVED (FRED)", "notices": required_notices(["fred"])}

    def fred_board(self, limit: int = 30) -> List[Dict[str, Any]]:
        """Every catalogue series; a failing one becomes an error row, never a missing row."""
        out = []
        for s in FRED_MARKET:
            try:
                out.append(self.fred_series(s, limit))
            except DataError as exc:
                out.append({"series": s, "title_fa": FRED_MARKET[s][1], "unit": FRED_MARKET[s][0],
                            "group": FRED_MARKET[s][2], "error": str(exc)})
        return out

    # -- World Bank ----------------------------------------------------------------------------
    def world(self, indicator: str, countries: Sequence[str], mrv: int = 6) -> Dict[str, Any]:
        if indicator not in WB_INDICATORS:
            raise DataError("indicator %r is not in the catalogue" % (indicator,))
        iso2 = [c for c in countries if c in COUNTRIES]
        if not iso2 or len(iso2) != len(list(countries)):
            raise DataError("unknown country code(s): %s" % ", ".join(c for c in countries if c not in COUNTRIES))
        unit, title = WB_INDICATORS[indicator]
        iso3 = [COUNTRIES[c][0] for c in iso2]
        facts = self._cached(("wb", indicator, tuple(iso3), mrv), lambda: _wb.fetch(
            iso3, indicator, unit, mrv=mrv, http_get=self.wb_get))
        back = {v[0]: k for k, v in COUNTRIES.items()}
        series: Dict[str, List[Dict[str, Any]]] = {c: [] for c in iso2}
        for f in facts:
            c = back.get(f.entity)
            if c in series:
                series[c].append({"year": f.fiscal_year, "value": f.value})
        rows = []
        for c in iso2:
            pts = sorted(series[c], key=lambda p: p["year"])
            rows.append({"country": c, "name_fa": COUNTRIES[c][1], "points": pts,
                         "last": pts[-1] if pts else None})
        return {"indicator": indicator, "title_fa": title, "unit": unit, "rows": rows,
                "label": "RETRIEVED (World Bank, annual)", "notices": required_notices(["world_bank_indicators"]),
                "note": "داده‌ها سالانه‌اند و معمولاً یک تا دو سال تأخیر دارند؛ سال هر عدد کنارش آمده است."}

    # -- stocks (Alpha Vantage, END_OF_DAY) ---------------------------------------------------
    def stock(self, symbol: str) -> Dict[str, Any]:
        sym = (symbol or "").strip().upper()
        if not sym:
            raise DataError("a symbol is required")

        def _go():
            if self.av_fetch is not None:
                return self.av_fetch(sym)
            from market import alpha_vantage as AV
            return AV.fetch_daily(sym)
        try:
            quotes = self._cached(("av", sym), _go)
        except DataError:
            raise
        except Exception as exc:                          # MarketDataError / AlphaVantageError
            raise DataError(str(exc))
        pts = [{"date": str(q.timestamp)[:10], "value": q.last} for q in quotes]
        if not pts:
            raise DataError("no daily bars for %s" % sym)
        return {"symbol": sym, "points": pts[-90:], "last": pts[-1],
                "label": "RETRIEVED (Alpha Vantage free tier, END_OF_DAY, trust UNVERIFIED)",
                "note": "قیمت پایانی روز است، نه لحظه‌ای. نسخهٔ رایگان ۲۵ درخواست در روز اجازه می‌دهد."}


def today() -> datetime.date:
    return datetime.datetime.now(datetime.timezone.utc).date()
