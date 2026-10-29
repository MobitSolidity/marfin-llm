# -*- coding: utf-8 -*-
"""
D-0142: crypto (CoinGecko), forex pairs / US quotes / ticker search (Alpha Vantage free
functions) and US company fundamentals (SEC EDGAR companyfacts).

Offline: every source is the shape-faithful fake in tests/_fake_data.py (shapes MEASURED
2026-10-28 from live calls). (V) verified invariant, (A) adversarial -- must refuse,
(B) hand-checked value, (M) measured shape.
"""
import copy
import datetime
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

from _harness import check, check_raises, check_true, section, summary  # noqa: E402
import _fake_data as FD                                                  # noqa: E402
from market import alpha_vantage as AV                                   # noqa: E402
from market import av_markets as M                                       # noqa: E402
from market import coingecko as CG                                       # noqa: E402
from rag import datahub as DH                                            # noqa: E402
from rag import sec_facts as SF                                          # noqa: E402
from rag import sources as S                                             # noqa: E402

_SAVED_ENV = dict(os.environ)


def err(fn):
    """The refusal text of fn(), or None if it did not raise."""
    try:
        fn()
    except Exception as exc:                                        # noqa: BLE001
        return "%s: %s" % (type(exc).__name__, exc)
    return None

os.environ["ALPHAVANTAGE_API_KEY"] = "FAKEKEY12345"
os.environ.pop("COINGECKO_DEMO_API_KEY", None)

# ===========================================================================
section("registry: CoinGecko registered with the attribution its terms require")
# ===========================================================================
src = S.check_access("coingecko")
check_true("coingecko is enabled and gated by the registry", src.enabled and src.key == "coingecko", "(V)")
check_true("its licence records the no-resale and attribution clauses verbatim",
           "re-distribute" in src.licence and "Powered by CoinGecko" in src.licence, "(V)")
check_true("the required notice is exactly 'Powered by CoinGecko'",
           S.required_notices(["coingecko"]) == ["Powered by CoinGecko"], "(V)")
check_true("CoinGecko is research-grade, never placed above official data",
           S.TRUST_LEVELS[src.trust_level] < S.TRUST_LEVELS["OFFICIAL_DATA"], "(V)")

# ===========================================================================
section("CoinGecko client: URLs, parsing, refusals")
# ===========================================================================
check_true("markets URL: documented parameters, capped page size",
           "per_page=50" in CG.markets_url("usd", 50) and "vs_currency=usd" in CG.markets_url("usd", 50), "(V)")
for name, fn in (("per_page above the documented 250", lambda: CG.markets_url("usd", 251)),
                 ("per_page as a boolean", lambda: CG.markets_url("usd", True)),
                 ("a query-string injection in the currency", lambda: CG.markets_url("usd&x=1")),
                 ("a path-traversal coin id", lambda: CG.chart_url("../x")),
                 ("more than the free plan's 365 days", lambda: CG.chart_url("bitcoin", "usd", 366)),
                 ("zero days", lambda: CG.chart_url("bitcoin", "usd", 0))):
    check_raises("refused: %s" % name, fn, CG.CoinGeckoError)
rows = CG.parse_markets(FD.cg_get(CG.markets_url("usd", 4)))
check("a coin without a price is skipped, never shown as 0", len(rows), 3, method="(A)")
check("BTC price parsed (MEASURED shape)", rows[0]["price"], 81036.0, method="(M)")
check("a negative 24h change is kept (changes may be negative)", rows[1]["change_24h"], -1.25, method="(V)")
base = FD.cg_get(CG.markets_url("usd", 1))
for field, bad in (("current_price", True), ("current_price", "81036"), ("current_price", float("nan")),
                   ("current_price", -1.0), ("id", "<script>"), ("market_cap", float("inf"))):
    x = copy.deepcopy(base)
    x[0][field] = bad
    check_raises("refused: %s = %r" % (field, bad), lambda x=x: CG.parse_markets(x), CG.CoinGeckoError)
check_raises("the HTTP-429 body shape is refused, not parsed",
             lambda: CG.parse_markets({"status": {"error_code": 429, "error_message": "rate limit"}}), CG.CoinGeckoError)
check_true("... and the refusal quotes CoinGecko's own reason",
           "Rate Limit" in (err(lambda: CG.parse_markets(
               {"status": {"error_code": 429, "error_message": "You've exceeded the Rate Limit"}})) or ""), "(A)")
check("a coin priced exactly 0 is skipped too (an unpriced listing, not a free coin)",
      len(CG.parse_markets([base[0], dict(base[0], id="zero", current_price=0)])), 1, method="(A)")
check_raises("an all-unpriced list is refused (no empty table that reads as 'no coins')",
             lambda: CG.parse_markets([dict(base[0], current_price=None)]), CG.CoinGeckoError)
g = CG.parse_global(FD.cg_get(CG.global_url()))
check("global: BTC dominance (MEASURED shape)", g["btc_dominance"], 59.46347482672264, method="(M)")
check_true("global: updated_at turned into a UTC timestamp", g["updated"] == "2026-10-28 20:44 UTC", "(B)")
check_raises("global: wrong shape refused", lambda: CG.parse_global({"data": []}), CG.CoinGeckoError)
pts = CG.parse_chart({"prices": [[1779027899041, 77953.8], [1779028199661, 78052.9], [1779114299661, 78100.0]]})
check_true("chart: one point per UTC day, the last of the day wins (official schema example)",
           pts == [{"date": "2026-05-17", "value": 78052.9}, {"date": "2026-05-18", "value": 78100.0}], "(B)")
check_raises("chart: fewer than two days refused", lambda: CG.parse_chart({"prices": [[1, 2.0]]}), CG.CoinGeckoError)
check_raises("chart: a malformed point refused", lambda: CG.parse_chart({"prices": [[1, 2, 3]]}), CG.CoinGeckoError)
os.environ["COINGECKO_DEMO_API_KEY"] = "bad key with spaces"
check_raises("a malformed Demo key is never sent", CG._demo_key, CG.CoinGeckoError)
os.environ.pop("COINGECKO_DEMO_API_KEY")
check_true("no Demo key set: keyless (None), not an error", CG._demo_key() is None, "(V)")

# ===========================================================================
section("Alpha Vantage free functions: forex pairs, quote, search")
# ===========================================================================
check_raises("a Premium function is refused before any request", lambda: M.build_url("FX_INTRADAY", "K"),
             AV.AlphaVantageError)
check_true("only the three verified free functions are permitted",
           sorted(M.FUNCTIONS) == ["FX_DAILY", "GLOBAL_QUOTE", "SYMBOL_SEARCH"], "(V)")
check_true("gold (XAU) is not offered as a pair (never verified on FX_DAILY)",
           all("XAU" not in p for p in M.MAJOR_PAIRS), "(V)")
for name, fn in (("the same currency twice", lambda: M._pair("USD", "usd")),
                 ("a 2-letter code", lambda: M._pair("US", "EUR")),
                 ("an injection in a currency", lambda: M._pair("USD&x", "EUR")),
                 ("an injection in a symbol", lambda: M._symbol("IBM&apikey=x")),
                 ("an injection in search keywords", lambda: M.fetch_search("a&function=OVERVIEW",
                                                                            http_get=lambda u, k: {}))):
    check_raises("refused: %s" % name, fn, AV.AlphaVantageError)
q = M.parse_quote(FD.av_get(M.build_url("GLOBAL_QUOTE", "FAKEKEY12345", symbol="IBM"), "FAKEKEY12345"))
check("quote price (MEASURED shape)", q["price"], 253.27, method="(M)")
check("quote change percent parsed from '1.2068%'", q["change_pct"], 1.2068, method="(B)")
bad = FD.av_get(M.build_url("GLOBAL_QUOTE", "FAKEKEY12345", symbol="IBM"), "FAKEKEY12345")
bad["Global Quote"]["09. change"] = "99"
check_raises("an internally inconsistent quote (price - prev close != change) is refused",
             lambda: M.parse_quote(bad), AV.AlphaVantageError)
badday = FD.av_get(M.build_url("GLOBAL_QUOTE", "FAKEKEY12345", symbol="IBM"), "FAKEKEY12345")
badday["Global Quote"]["07. latest trading day"] = "28/10/2026"
check_raises("a quote without a valid trading day is refused", lambda: M.parse_quote(badday), AV.AlphaVantageError)
check_raises("an unknown symbol (empty 'Global Quote') is refused",
             lambda: M.parse_quote({"Global Quote": {}}), AV.AlphaVantageError)
check_raises("the daily-limit message (HTTP 200 'Information') is refused, not shown as data",
             lambda: M.parse_quote({"Information": "standard API rate limit is 25 requests per day"}),
             AV.AlphaVantageError)
fx = M.parse_fx_daily(FD.av_get(M.build_url("FX_DAILY", "FAKEKEY12345", from_symbol="EUR", to_symbol="USD"),
                                "FAKEKEY12345"))
check_true("FX rows oldest first", fx["rows"][0]["date"] < fx["rows"][-1]["date"], "(V)")
check("FX last close (fixture)", fx["rows"][-1]["close"], 1.1122, method="(B)")
broken = FD.av_get(M.build_url("FX_DAILY", "FAKEKEY12345", from_symbol="EUR", to_symbol="USD"), "FAKEKEY12345")
broken["Time Series FX (Daily)"]["2026-10-27"]["2. high"] = "0.5"
check_raises("an FX bar whose high is below its open is refused", lambda: M.parse_fx_daily(broken),
             AV.AlphaVantageError)
s = M.parse_search(FD.av_get(M.build_url("SYMBOL_SEARCH", "FAKEKEY12345", keywords="tesco"), "FAKEKEY12345"))
check_true("search: malformed symbols dropped, valid ones kept",
           [r["symbol"] for r in s] == ["TSCO.LON", "TSCDF"], "(A)")
check_true("search: the daily-limit body is refused in Alpha Vantage's own words",
           "25 requests per day" in (err(lambda: M.parse_search(
               {"Information": "Our standard API rate limit is 25 requests per day."})) or ""), "(A)")
sent = []
check_raises("search keywords with an injection are refused before any request",
             lambda: M.fetch_search("a&function=OVERVIEW", http_get=lambda u, k: sent.append(u) or {"bestMatches": []},
                                    budget=AV.RequestBudget(limit=5)), AV.AlphaVantageError)
check("... and nothing was sent", len(sent), 0, method="(A)")
import market.quotes as MQ                                               # noqa: E402
_avp, gb, sent = MQ.PROVIDERS[AV.PROVIDER_KEY], AV.RequestBudget(limit=5), []
object.__setattr__(_avp, "enabled", False)
try:
    check_raises("the licence gate runs first: a disabled provider is refused",
                 lambda: M.fetch_quote("IBM", http_get=lambda u, k: sent.append(u) or FD.av_get(u, k), budget=gb),
                 MQ.MarketDataError)
finally:
    object.__setattr__(_avp, "enabled", True)
check_true("... before the budget is spent or a request is sent; provider restored",
           gb.used == 0 and not sent and MQ.PROVIDERS[AV.PROVIDER_KEY].enabled is True, "(A)")
b = AV.RequestBudget(limit=1)
M.fetch_quote("IBM", http_get=FD.av_get, budget=b)
check_raises("the shared 25/day budget is enforced across the new functions",
             lambda: M.fetch_quote("IBM", http_get=FD.av_get, budget=b), AV.AlphaVantageError)

# ===========================================================================
section("SEC EDGAR: annual 10-K figures, restatements, contact User-Agent")
# ===========================================================================
os.environ.pop("SEC_CONTACT_EMAIL", None)
check_raises("no contact e-mail: refused before any request", SF.user_agent, SF.SecError)
for e in ("me", "@example.com", "me@localhost", "a b@x.com", "me@example.com<script>"):
    check_raises("refused contact %r" % e, lambda e=e: SF.user_agent(e), SF.SecError)
ua = SF.user_agent(FD.SEC_CONTACT)
check_true("UA names the project and the contact", ua == "marfin-llm/0.14 (owner@example.com)", "(V)")
check_raises("the registry gate refuses a UA without a contact (MEASURED 403 otherwise)",
             lambda: SF.fetch_fundamentals(320193, "marfin-llm/0.14", http_get=FD.sec_get), S.AccessError)
for cik in (True, 0, 10 ** 10, "320193"):
    check_raises("refused CIK %r" % (cik,), lambda c=cik: SF.fetch_fundamentals(c, ua, http_get=FD.sec_get),
                 SF.SecError)
f = SF.fetch_fundamentals(320193, ua, http_get=FD.sec_get)
got = {m["key"]: m["points"][-1]["value"] for m in f["metrics"] if m["points"]}
check("revenue FY2025 = 416,161,000,000 (Apple 10-K, MEASURED 2026-10-28)", got["revenue"], 416161000000, method="(M)")
check("diluted EPS FY2025 = 7.46", got["eps_diluted"], 7.46, method="(M)")
check("a quarter reported inside a 10-K is NOT an annual figure",
      len([m for m in f["metrics"] if m["key"] == "net_income"][0]["points"]), 2, method="(A)")
x = {"cik": 1, "entityName": "X", "facts": {"us-gaap": {"NetIncomeLoss": {"units": {"USD": [
    {"start": "2024-09-29", "end": "2025-09-27", "val": 100, "form": "10-K", "fp": "FY", "filed": "2025-10-31", "accn": "a"},
    {"start": "2024-09-29", "end": "2025-06-28", "val": 70, "form": "10-Q", "fp": "Q3", "filed": "2025-08-01", "accn": "q"},
    {"start": "2024-09-29", "end": "2025-09-27", "val": 101, "form": "10-K", "fp": "FY", "filed": "2026-10-30", "accn": "b"},
    {"start": "2023-10-01", "end": "2024-09-28", "val": True, "form": "10-K", "fp": "FY", "filed": "2024-11-01", "accn": "c"}]}}}}}
pts = [m for m in SF.parse_companyfacts(x)["metrics"] if m["key"] == "net_income"][0]["points"]
check_true("10-Q and boolean rows excluded; the LATER filing (a restatement) wins, accession kept",
           pts == [{"fy_end": "2025-09-27", "value": 101.0, "filed": "2026-10-30", "accn": "b"}], "(A)")
y = {"cik": 2, "entityName": "Y", "facts": {"us-gaap": {
    "Assets": {"units": {"USD": [
        {"end": "2025-09-27", "val": 100, "form": "10-K", "fp": "FY", "filed": "2025-10-31", "accn": "k"},
        {"end": "2025-06-28", "val": 90, "form": "10-Q", "fp": "Q3", "filed": "2025-08-01", "accn": "q"}]}},
    "NetIncomeLoss": {"units": {"USD": [
        {"start": "2024-09-29", "end": "2025-09-27", "val": 100, "form": "10-K", "fp": "FY", "filed": "2025-10-31", "accn": "a"},
        {"start": "2025-06-29", "end": "2025-09-27", "val": 25, "form": "10-K", "fp": "FY", "filed": "2025-11-01", "accn": "q4"},
        {"start": "2023-09-30", "end": "2025-09-27", "val": 190, "form": "10-K", "fp": "FY", "filed": "2025-11-02", "accn": "2y"}]}}}}}
ym = {m["key"]: m["points"] for m in SF.parse_companyfacts(y)["metrics"]}
check_true("balance sheet: a 10-Q value is never an annual figure", [p["accn"] for p in ym["assets"]] == ["k"], "(A)")
check_true("flows: a quarter or a two-year span is never an annual figure, even when filed later",
           [p["value"] for p in ym["net_income"]] == [100.0], "(A)")
check_raises("no annual figures at all is refused (not an empty table)",
             lambda: SF.parse_companyfacts({"cik": 1, "facts": {"us-gaap": {}}}), SF.SecError)
t = SF.parse_tickers(FD.sec_get(SF.TICKERS_URL, ua))
check_true("tickers mapped to CIKs", t["AAPL"]["cik"] == 320193 and t["NVDA"]["cik"] == 1045810, "(M)")

# ===========================================================================
section("real loopback sockets: redirects refused, 429 explained (M)")
# ===========================================================================
import http.server                                                       # noqa: E402
import threading                                                         # noqa: E402
HITS = []


class _H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/steal"):
            HITS.append(dict(self.headers))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"facts": {}, "data": []}')
        elif self.path.startswith("/limited"):
            self.send_response(429)
            self.end_headers()
        else:
            self.send_response(302)
            self.send_header("Location", "http://127.0.0.1:%d/steal" % SRV.server_port)
            self.end_headers()

    def log_message(self, *a):
        pass


SRV = http.server.HTTPServer(("127.0.0.1", 0), _H)
threading.Thread(target=SRV.serve_forever, daemon=True).start()
LB = "http://127.0.0.1:%d" % SRV.server_port
os.environ["COINGECKO_DEMO_API_KEY"] = "CG-FAKEFAKEFAKEFAKE"
check_true("CoinGecko client: a real 302 is refused, not followed",
           "redirect" in (err(lambda: CG._http_get(LB + "/redir")) or ""), "(M)")
_m = err(lambda: CG._http_get(LB + "/limited")) or ""
check_true("CoinGecko client: a real 429 names the keyless limit and the Demo-key remedy",
           "rate limit" in _m and CG.KEY_ENV in _m and "FAKEFAKE" not in _m, "(M)")
os.environ.pop("COINGECKO_DEMO_API_KEY")
check_true("SEC client: a real 302 is refused, not followed",
           "302" in (err(lambda: SF._http_get(LB + "/redir", ua)) or ""), "(M)")
check("... and nothing reached the redirect target (no Demo key, no contact address)", len(HITS), 0, method="(M)")
SRV.shutdown()

# ===========================================================================
section("DataHub: crypto, forex pairs, quotes, search, fundamentals")
# ===========================================================================
FD.CALLS.clear()
h = FD.hub()
c = h.crypto()
check_true("crypto table carries the CoinGecko notice and an 'indicative' label",
           c["notices"] == ["Powered by CoinGecko"] and "indicative" in c["label"], "(V)")
check_raises("an unoffered quote currency is refused before any request", lambda: h.crypto("xyz"), DH.DataError)
check_true("chart: oldest first, one point per day", h.crypto_chart("bitcoin", "usd", 30)["points"][0]["date"]
           < h.crypto_chart("bitcoin", "usd", 30)["points"][-1]["date"], "(V)")
check_raises("a CoinGecko 429 becomes a DataError (shown, not crashed)", lambda: h.crypto_chart("limited"), DH.DataError)
p = h.fx_pair("eur", "usd")
check("pair change COMPUTED from the last two closes", p["change_pct"], (1.1122 / 1.1132 - 1) * 100, 1e-9, "(B)")
check_raises("an Alpha Vantage 'Error Message' becomes a DataError", lambda: h.fx_pair("XXX", "USD"), DH.DataError)
check("quote via the hub", h.quote("ibm")["price"], 253.27, method="(V)")
check_raises("the daily-limit string becomes a DataError", lambda: h.quote("LIMIT"), DH.DataError)
check_true("search via the hub", [r["symbol"] for r in h.search("tesco")] == ["TSCO.LON", "TSCDF"], "(V)")
fu = h.fundamentals("aapl")
check_true("fundamentals via the hub: ticker -> CIK -> companyfacts", fu["ticker"] == "AAPL"
           and fu["name"] == "Apple Inc." and "10-K" in fu["label"], "(V)")
check_raises("a ticker not on SEC's list is refused", lambda: h.fundamentals("ZZZZ"), DH.DataError)
check_raises("a ticker with an injection is refused before any request", lambda: h.fundamentals("A&B"), DH.DataError)
FD.CALLS.clear()
check_true("a malformed ticker is refused with that reason (fresh hub, empty cache)",
           "not a ticker symbol" in (err(lambda: FD.hub().fundamentals("A&B")) or ""), "(A)")
check("... and no request reached SEC", len(FD.CALLS), 0, method="(A)")
check_raises("no SEC contact configured: refused, nothing fetched",
             lambda: FD.hub(sec_contact="").fundamentals("AAPL"), DH.DataError)
n = len(FD.CALLS)
h.crypto(), h.fx_pair("EUR", "USD"), h.quote("IBM"), h.fundamentals("AAPL")
check("a second request within the TTL is served from memory", len(FD.CALLS) - n, 0, method="(V)")
broken_hub = FD.hub(cg_get=lambda u: (_ for _ in ()).throw(KeyError("bug")))
check_raises("a programming bug (KeyError) is NOT disguised as 'data unavailable'",
             lambda: broken_hub.crypto(), KeyError)
check_raises("a network failure (OSError) IS a DataError",
             lambda: FD.hub(cg_get=lambda u: (_ for _ in ()).throw(OSError("reset"))).crypto(), DH.DataError)
check("the sources list now names 7 sources", len(DH.SOURCES_FA), 7, method="(V)")

# ===========================================================================
section("web UI: crypto, forex and US-stock tabs (offline, escaped, attributed)")
# ===========================================================================
import tempfile                                                          # noqa: E402
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import ui as U                                                           # noqa: E402

_td = tempfile.mkdtemp(prefix="marfin_mkt_")
G = U.App(paper_dir=os.path.join(_td, "p"), ask_audit_path=os.path.join(_td, "a.jsonl"), hub=FD.hub(),
          settings_path=os.path.join(_td, "s.json"))


def page(**q):
    r = G.handle("GET", "/markets", q)
    return r.status, r.body.split("</head>", 1)[1]


check_true("the three new tabs are registered", {"crypto", "forex", "stocks"} <= set(dict(U.App.MARKET_TABS)), "(V)")
for tab, _t in U.App.MARKET_TABS:
    st, b = page(tab=tab)
    check_true("tab %s: 200, no internal error, no style attribute" % tab,
               st == 200 and "INTERNAL ERROR" not in b and ' style="' not in b, "(V)")
st, b = page(tab="crypto")
check_true("crypto: table, global stats and 8 quote-currency chips", "81,036" in b and "59.46%" in b
           and b.count("tab=crypto&amp;vs=") >= 8, "(V)")
check_true("crypto: 'Powered by CoinGecko' shown as required by its terms",
           'class="attrib ltr">Powered by CoinGecko' in b, "(V)")
check_true("crypto: a coin without a price never appears", ">DEAD<" not in b, "(A)")
st, b = page(tab="crypto", coin="bitcoin", vs="eur")
check_true("crypto: 90-day chart with a COMPUTED change", '<svg class="chart' in b and "bitcoin / EUR" in b
           and "COMPUTED" in b, "(V)")
st, b = page(tab="crypto", coin="limited")
check_true("crypto: a rate limit is shown as a refusal, not a crash", st == 200 and "rate limit" in b, "(A)")
st, b = page(tab="crypto", vs="<script>")
check_true("crypto: an unknown quote currency falls back to USD, escaped",
           "<script>" not in b and 'class="chip on" href="/markets?tab=crypto&amp;vs=usd"' in b, "(A)")
st, b = page(tab="forex")
check_true("forex: nothing is fetched until a pair is chosen (saves the 25/day budget)",
           'class="big"' not in b and b.count("tab=forex&amp;from=") == len(M.MAJOR_PAIRS), "(V)")
st, b = page(tab="forex", **{"from": "eur", "to": "usd"})
check_true("forex: EUR/USD close, chart, OHLC table, daily change", "1.11220" in b and '<svg class="chart' in b
           and "تغییر روزانه" in b, "(V)")
st, b = page(tab="forex", **{"from": "<b>", "to": "USD"})
check_true("forex: an injected code is refused and escaped (only the brand wordmark's <b> remains)",
           "دریافت نشد" in b and "&lt;B&gt;" in b and b.count("<b>") == 1, "(A)")
st, b = page(tab="stocks", symbol="aapl")
check_true("stocks: EOD price plus SEC annual fundamentals with fiscal year-ends",
           "123.00" in b and "416,161,000,000" in b and "Apple Inc." in b and "2025/09" in b, "(V)")
st, b = page(tab="stocks", q="tesco")
check_true("stocks: ticker search lists valid symbols only", "TSCO.LON" in b and "&lt;bad&gt;" not in b, "(A)")
st, b = page(tab="stocks", symbol="ibm")
check_true("stocks: no SEC facts -> a refusal card, the price is still shown",
           "123.00" in b and "SEC_CONTACT_EMAIL" in b, "(A)")
st, b = page(tab="sources")
check_true("sources: 7 sources, why Kraken and Binance are not used, CoinGecko attribution",
           b.count("<tr>") >= 8 and "Kraken" in b and "Binance" in b and "Powered by CoinGecko" in b, "(V)")

os.environ.clear()
os.environ.update(_SAVED_ENV)
print("")
sys.exit(summary())
