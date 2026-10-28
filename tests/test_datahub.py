# -*- coding: utf-8 -*-
"""
D-0141: the multi-source data layer (rag/ecb_stats.py, rag/worldbank.py,
bis_stats.facts_per_area, rag/datahub.py) and the Persian calculator catalogue
(tools/catalog_fa.py).

Offline: every source is the shape-faithful fake in tests/_fake_data.py.
(V) verified invariant, (A) adversarial -- must refuse, (B) hand-checked value,
(M) measured shape.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

from _harness import check, check_raises, check_true, section, summary  # noqa: E402
import _fake_data as FD                                                  # noqa: E402
from rag import bis_stats as B                                           # noqa: E402
from rag import datahub as DH                                            # noqa: E402
from rag import ecb_stats as E                                           # noqa: E402
from rag import sources as S                                             # noqa: E402
from rag import worldbank as W                                           # noqa: E402
from tools import catalog_fa as C                                        # noqa: E402
from tools import registry as R                                          # noqa: E402

# ===========================================================================
section("ECB EXR client: URL, parsing, refusals")
# ===========================================================================
u = E.data_url(["USD", "JPY"], last_n=3)
check_true("URL names the per-EUR daily reference series and asks for CSV",
           "/EXR/D.USD+JPY.EUR.SP00.A?" in u and "lastNObservations=3" in u and "format=csvdata" in u, "(V)")
check_raises("EUR itself refused (it is the base of every rate)", lambda: E.data_url(["EUR"]), E.EcbError)
check_raises("malformed currency refused", lambda: E.data_url(["usd"]), E.EcbError)
check_raises("injection in a currency code refused", lambda: E.data_url(["USD&x=1"]), E.EcbError)
check_raises("empty currency list refused", lambda: E.data_url([]), E.EcbError)
check_raises("last_n out of range refused", lambda: E.data_url(["USD"], last_n=0), E.EcbError)
f = E.fetch(["USD", "JPY"], last_n=2, http_get=FD.ecb_get)
check("4 facts for 2 currencies x 2 days", len(f), 4, method="(V)")
usd = [x for x in f if x.currency == "USD"]
check("USD 2026-10-26 = 1.1188 per EUR (fixture)", sorted(usd, key=lambda x: x.period_end)[-1].value, 1.1188,
      method="(B)")
check_true("unit names both currencies", usd[0].unit == "USD per EUR", "(V)")
check_true("provenance is the ECB registry entry (licence from the registry, not the caller)",
           usd[0].provenance.source == S.SOURCES["ecb_data_portal"].name
           and usd[0].provenance.trust_level == "OFFICIAL_DATA", "(V)")
H = FD.ECB_HEAD
check("a missing value is skipped, never 0", len(E.facts_from_csv(
    H + "k,D,USD,EUR,SP00,A,2026-10-26,,A\r\nk,D,USD,EUR,SP00,A,2026-10-27,NaN,A\r\n")), 0, method="(A)")
check_raises("a non-EUR denominator refused", lambda: E.facts_from_csv(
    H + "k,D,USD,GBP,SP00,A,2026-10-26,1.2,A\r\n"), E.EcbError)
check_raises("a non-numeric rate refused", lambda: E.facts_from_csv(
    H + "k,D,USD,EUR,SP00,A,2026-10-26,abc,A\r\n"), E.EcbError)
check_raises("a zero rate refused", lambda: E.facts_from_csv(
    H + "k,D,USD,EUR,SP00,A,2026-10-26,0,A\r\n"), E.EcbError)
check_raises("a monthly period refused (only daily is parsed)", lambda: E.facts_from_csv(
    H + "k,D,USD,EUR,SP00,A,2026-10,1.1,A\r\n"), E.EcbError)
check_raises("an HTML page instead of CSV refused", lambda: E.facts_from_csv("<html>maintenance</html>"), E.EcbError)
check_raises("a CSV missing the OBS_VALUE column refused (not silently empty)", lambda: E.facts_from_csv(
    "CURRENCY,CURRENCY_DENOM,TIME_PERIOD\r\nUSD,EUR,2026-10-26\r\n"), E.EcbError)

# ===========================================================================
section("World Bank client: URL, shape checks (HTTP 200 errors), refusals")
# ===========================================================================
u = W.data_url(["IRN", "TUR"], "FP.CPI.TOTL.ZG", mrv=4)
check_true("URL: countries joined by ';', JSON, mrv", "/country/IRN;TUR/indicator/FP.CPI.TOTL.ZG?" in u
           and "format=json" in u and "mrv=4" in u, "(V)")
check_raises("ISO-2 instead of ISO-3 refused", lambda: W.data_url(["IR"], "FP.CPI.TOTL.ZG"), W.WorldBankError)
check_raises("malformed indicator refused", lambda: W.data_url(["IRN"], "../etc"), W.WorldBankError)
check_raises("more than 30 countries refused", lambda: W.data_url(["IRN"] * 31, "FP.CPI.TOTL.ZG"), W.WorldBankError)
w = W.fetch(["IRN", "TUR"], "FP.CPI.TOTL.ZG", "percent per year", http_get=FD.wb_get)
check("Iran 3 rows, one null -> 2 facts; Turkey 2 -> 4 facts", len(w), 4, method="(V)")
check_true("Iran 2025 inflation 42.17 (fixture); annual period", any(
    x.entity == "IRN" and x.fiscal_year == 2025 and abs(x.value - 42.17) < 1e-9 and x.period_kind == "annual"
    for x in w), "(B)")
check_raises("World Bank's HTTP-200 error message refused (MEASURED shape)", lambda: W.facts_from_payload(
    "FP.CPI.TOTL.ZG", [{"message": [{"id": "120", "key": "Invalid value", "value": "not valid"}]}], "p"),
    W.WorldBankError)
try:
    W.facts_from_payload("FP.CPI.TOTL.ZG", [{"message": [{"id": "120", "key": "Invalid value", "value": "x"}]}], "p")
    _wbmsg = ""
except W.WorldBankError as exc:
    _wbmsg = str(exc)
check_true("... and the refusal quotes the World Bank's own message, not a generic shape error",
           "refused the request" in _wbmsg and "Invalid value" in _wbmsg, "(A) %r" % _wbmsg)
check_raises("a row for a different indicator refused", lambda: W.facts_from_payload("FP.CPI.TOTL.ZG", [{}, [
    {"indicator": {"id": "NY.GDP.MKTP.CD"}, "countryiso3code": "IRN", "date": "2025", "value": 1.0}]], "p"),
    W.WorldBankError)
check_raises("a string value refused", lambda: W.facts_from_payload("FP.CPI.TOTL.ZG", [{}, [
    {"indicator": {"id": "FP.CPI.TOTL.ZG"}, "countryiso3code": "IRN", "date": "2025", "value": "42"}]], "p"),
    W.WorldBankError)
check_raises("a missing unit refused", lambda: W.facts_from_payload("FP.CPI.TOTL.ZG", [{}, []], ""),
             W.WorldBankError)
check("an empty result is an empty list (no data for those years), not an error",
      len(W.facts_from_payload("FP.CPI.TOTL.ZG", [{}, None], "p")), 0, method="(V)")

# ===========================================================================
section("BIS: all central banks in one call (facts_per_area)")
# ===========================================================================
pa = B.fetch_per_area("WS_CBPOL", "D.", "Percent per annum", http_get=FD.bis_get)
check("8 fixture rows, one NaN skipped -> 7", len(pa), 7, method="(V)")
check_true("each fact names its own area", {x.entity for x in pa} == {"US", "TR", "XM", "GB", "JP", "CH", "DE"}
           and all(x.concept == "WS_CBPOL:D.%s" % x.entity for x in pa), "(V)")
check_true("Switzerland's 0 % is kept as 0 (a real value, not a missing one)",
           any(x.entity == "CH" and x.value == 0.0 for x in pa), "(A)")
check_raises("a monthly frequency refused even with a daily-looking date", lambda: B.facts_per_area(
    "WS_CBPOL", "FREQ,REF_AREA,TIME_PERIOD,OBS_VALUE\nM,US,2026-10-20,3\n", "p"), B.BisStatsError)
check_raises("a malformed area refused", lambda: B.facts_per_area(
    "WS_CBPOL", "FREQ,REF_AREA,TIME_PERIOD,OBS_VALUE\nD,u-s,2026-10-20,3\n", "p"), B.BisStatsError)
check_raises("no unit refused", lambda: B.facts_per_area(
    "WS_CBPOL", "FREQ,REF_AREA,TIME_PERIOD,OBS_VALUE\nD,US,2026-10-20,3\n", ""), B.BisStatsError)

# ===========================================================================
section("DataHub: FX table, COMPUTED crosses only from same-day fixes")
# ===========================================================================
hub = FD.hub()
fx = hub.fx()
rows = {r["ccy"]: r for r in fx["rows"]}
check("latest USD fix kept (2026-10-26 = 1.1188)", rows["USD"]["per_eur"], 1.1188, method="(B)")
check("JPY per USD = 176.15 / 1.1188 (COMPUTED, same day)", rows["JPY"]["per_usd"], 176.15 / 1.1188, method="(B)")
check_true("CHF's last fix is a different day from the dollar's -> no per-USD figure",
           rows["CHF"]["per_usd"] is None and rows["CHF"]["date"] == "2026-10-23", "(A)")
check_true("table carries the ECB notice and a not-real-time note",
           any("European Central Bank" in n for n in fx["notices"]) and "لحظه‌ای نیست" in fx["note"], "(V)")
def ecb_all(url, timeout=20.0):
    # several fixes per currency, oldest first (the order the ECB returns them)
    return FD.ecb_get(re.sub(r"lastNObservations=\d+", "lastNObservations=5", url), timeout)
check("several fixes, oldest first: the NEWEST is kept (USD 2026-10-26 = 1.1188)",
      {r["ccy"]: r for r in FD.hub(ecb_get=ecb_all).fx()["rows"]}["USD"]["per_eur"], 1.1188, method="(B)")
cv = hub.convert(100, "USD", "JPY", fx)
check("100 USD -> JPY = 100 x 176.15/1.1188", cv["result"], 100 * 176.15 / 1.1188, method="(B)")
check("1 EUR -> USD = 1.1188 (EUR is the base, rate 1)", hub.convert(1, "EUR", "USD", fx)["result"], 1.1188,
      method="(B)")
check_raises("a cross from two different days refused (CHF vs USD)",
             lambda: hub.convert(1, "CHF", "USD", fx), DH.DataError)
check_raises("an unknown currency refused", lambda: hub.convert(1, "IRR", "USD", fx), DH.DataError)
check_raises("NaN amount refused", lambda: hub.convert(float("nan"), "USD", "JPY", fx), DH.DataError)
check_raises("infinite amount refused", lambda: hub.convert(float("inf"), "USD", "JPY", fx), DH.DataError)
check_raises("a boolean amount refused", lambda: hub.convert(True, "USD", "JPY", fx), DH.DataError)
check("fx history: 2 fixture days for JPY, oldest first", len(hub.fx_history("JPY", 30)), 2, method="(V)")
check_raises("fx history for a currency outside the catalogue refused",
             lambda: hub.fx_history("XAU", 30), DH.DataError)

# ===========================================================================
section("DataHub: policy rates, discontinued series separated")
# ===========================================================================
pr = hub.policy_rates()
cur = [r for r in pr["rows"] if not r["stale"]]
check("6 current, 1 stale (Germany 1998, superseded by the euro area)", (len(cur), len(pr["rows"]) - len(cur))[0], 6,
      method="(V)")
check_true("the stale one is Germany 1998", [r["area"] for r in pr["rows"] if r["stale"]] == ["DE"], "(V)")
check_true("current rows sorted highest first (Turkey 37 first)", cur[0]["area"] == "TR"
           and [r["rate"] for r in cur] == sorted([r["rate"] for r in cur], reverse=True), "(V)")
check_true("Persian names come from the catalogue", cur[0]["name_fa"] == "ترکیه", "(V)")
check("n_current reported", pr["n_current"], 6, method="(V)")

# ===========================================================================
section("DataHub: FRED market board, World Bank, stocks")
# ===========================================================================
check_true("the S&P 500 is NOT in the FRED catalogue (its notes carry a copyright claim, MEASURED)",
           "SP500" not in DH.FRED_MARKET, "(V)")
check_true("every FRED unit is the series' own string (MEASURED 2026-10-27)",
           DH.FRED_MARKET["DGS10"][0] == "Percent" and DH.FRED_MARKET["DCOILWTICO"][0] == "Dollars per Barrel"
           and DH.FRED_MARKET["DTWEXBGS"][0] == "Index Jan 2006=100", "(M)")
s10 = hub.fred_series("DGS10", 10)
check("FRED: 10 asked, one '.' missing -> 9 points", len(s10["points"]), 9, method="(V)")
check_true("points oldest first; last is the newest date", s10["points"][-1]["date"] == "2026-10-23"
           and s10["points"][0]["date"] < s10["points"][-1]["date"], "(V)")
check_raises("a series outside the markets catalogue refused", lambda: hub.fred_series("SP500"), DH.DataError)
nk = FD.hub(fred_key=None)
_env = os.environ.pop("FRED_API_KEY", None)
board = nk.fred_board(5)
if _env is not None:
    os.environ["FRED_API_KEY"] = _env
check_true("no FRED key: every card becomes an error row, none missing, nothing invented",
           len(board) == len(DH.FRED_MARKET) and all("error" in b and "points" not in b for b in board), "(A)")
wd = hub.world("FP.CPI.TOTL.ZG", ["IR", "TR", "US"])
check_true("World Bank rows in the requested order, ISO-2 mapped back",
           [r["country"] for r in wd["rows"]] == ["IR", "TR", "US"], "(V)")
check_true("Iran's latest is 2025 = 42.17", wd["rows"][0]["last"] == {"year": 2025, "value": 42.17}, "(B)")
check_raises("an unknown country refused (no silent drop)", lambda: hub.world("FP.CPI.TOTL.ZG", ["IR", "ZZ"]),
             DH.DataError)
check_raises("an indicator outside the catalogue refused", lambda: hub.world("SP.POP.TOTL", ["IR"]), DH.DataError)
check_true("every catalogue country has an ISO-3 code and a Persian name",
           all(len(v[0]) == 3 and v[1] for v in DH.COUNTRIES.values()), "(V)")
st = hub.stock("ibm")
check_true("stock symbol upper-cased; last EOD bar returned", st["symbol"] == "IBM" and st["last"]["value"] == 123.0
           and "END_OF_DAY" in st["label"], "(V)")
check_raises("a provider refusal becomes a DataError (shown, not crashed)", lambda: hub.stock("BAD"), DH.DataError)
check_raises("an empty symbol refused before any call", lambda: hub.stock("  "), DH.DataError)
def av_down(sym):
    raise OSError("connection reset by peer")
check_raises("a network failure in the stock provider becomes a DataError (shown, not crashed)",
             lambda: FD.hub(av_fetch=av_down).stock("IBM"), DH.DataError)

# ===========================================================================
section("DataHub: cache, retry, error conversion")
# ===========================================================================
t = [1000.0]
calls = []


def ecb_count(url, timeout=20.0):
    calls.append(url)
    return FD.ecb_get(url, timeout)


hc = FD.hub(ecb_get=ecb_count, clock=lambda: t[0])
hc.fx()
hc.fx()
check("second request inside the TTL is served from memory", len(calls), 1, method="(V)")
t[0] += DH.CACHE_TTL_S + 1
hc.fx()
check("after the TTL the source is asked again (nothing persists)", len(calls), 2, method="(V)")
flaky = {"n": 0}


def ecb_flaky(url, timeout=20.0):
    flaky["n"] += 1
    if flaky["n"] == 1:
        raise E.EcbError("could not read the ECB Data Portal: timed out")
    return FD.ecb_get(url, timeout)


slept = []
hf = FD.hub(ecb_get=ecb_flaky, sleep=slept.append)
check_true("one transient timeout is retried once, then succeeds", len(hf.fx()["rows"]) == 5
           and flaky["n"] == 2 and slept == [2.0], "(V)")


def ecb_down(url, timeout=20.0):
    raise E.EcbError("could not read the ECB Data Portal: timed out")


check_raises("a source that keeps timing out is a DataError after 2 attempts",
             lambda: FD.hub(ecb_get=ecb_down).fx(), DH.DataError)
bad = {"n": 0}


def ecb_html(url, timeout=20.0):
    bad["n"] += 1
    return "<html>maintenance</html>"


check_raises("a format error is NOT retried", lambda: FD.hub(ecb_get=ecb_html).fx(), DH.DataError)
check("format error asked once only", bad["n"], 1, method="(A)")
src = open(os.path.join(ROOT, "src", "rag", "datahub.py"), encoding="utf-8").read()
check_true("datahub writes nothing to disk (no open(), no json.dump)",
           "open(" not in src and "json.dump" not in src, "(V)")

# ===========================================================================
section("Persian calculator catalogue: complete, runnable, displayable")
# ===========================================================================
names = set(R.tool_names())
check_true("catalogue covers exactly the registered tools", set(C.TOOLS) == names, "(V)")
check("85 tools", len(C.TOOLS), 85, method="(V)")
params = set()
for sc in R.tool_schemas():
    params |= set(sc["function"]["parameters"]["properties"])
check_true("every parameter has a Persian label, and no stale ones", set(C.PARAMS) == params, "(V)")
check_true("every tool's category is a known category", all(t[0] in dict(C.CATEGORIES) for t in C.TOOLS.values()),
           "(V)")
check_true("every category is used", {t[0] for t in C.TOOLS.values()} == set(dict(C.CATEGORIES)), "(V)")
check_true("every usage line is one non-empty Persian line under 130 characters", all(
    u and "\n" not in u and len(u) < 130 and any("\u0600" <= ch <= "\u06ff" for ch in u)
    for _, _, u, _ in C.TOOLS.values()), "(V)")
check_true("every title is non-empty and distinct", len({t[1] for t in C.TOOLS.values()}) == 85, "(V)")
bad_ex = []
for n, (_, _, _, ex) in C.TOOLS.items():
    props = R._REGISTRY[n]["schema"]["function"]["parameters"]["properties"]
    req = R._REGISTRY[n]["schema"]["function"]["parameters"]["required"]
    r = R.call_tool(n, ex)
    if set(ex) - set(props) or set(req) - set(ex) or not r["ok"]:
        bad_ex.append(n)
check_true("all 85 worked examples run through call_tool with ok=True", bad_ex == [], "(M) %s" % bad_ex)
check("example P/E = 150 / 8.4", R.call_tool("pe_ratio", C.TOOLS["pe_ratio"][3])["value"], 150 / 8.4, method="(B)")
check("example position size = 250", R.call_tool("position_size", C.TOOLS["position_size"][3])["value"], 250.0,
      method="(B)")
check_true("example_text: lists comma-joined, booleans lower-case",
           C.example_text([1, 2.5]) == "1, 2.5" and C.example_text(True) == "true" and C.example_text(3) == "3", "(V)")
enums = set()
for sc in R.tool_schemas():
    for spec in sc["function"]["parameters"]["properties"].values():
        enums |= set(spec.get("enum", ()))
check_true("every enum value has a Persian display label", enums <= set(C.ENUM_FA), "(V) %s" % (enums - set(C.ENUM_FA)))
check_true("by_category lists all 85 once, in category order",
           sum(len(x[2]) for x in C.by_category()) == 85 and [x[0] for x in C.by_category()] == [k for k, _ in C.CATEGORIES],
           "(V)")
check_true("category sizes pinned (returns 18, trade 6, valuation 12, ratios 14, technical 13, bonds 11, options 11)",
           {k: len(v) for k, _, v in C.by_category()} == {"returns": 18, "trade": 6, "valuation": 12, "ratios": 14,
                                                           "technical": 13, "bonds": 11, "options": 11}
           and C.TOOLS["dv01"][0] == "bonds", "(V)")
check_raises("a duplicate catalogue entry refused", lambda: C._t("pe_ratio", "valuation", "x", "y", {}), ValueError)

print("")
sys.exit(summary())
