"""
Adversarial probe of the Alpha Vantage connector.

First adversarial execution of alpha_vantage.py. The record so far is that a
module's first hostile run finds live defects: sources.py had three, and this
connector already had one -- adjusted=True returned the UNADJUSTED close while
labelling the quote ADJUSTED, wrong by up to 1.4351% on measured data (largest
absolute gap 3.6692 on 2026-04-21). So the
assumption here is that this module is broken until proven otherwise.

What I am hunting for is a specific class of failure, arising from one MEASURED
fact: EVERY failure this API has returns HTTP 200 with an explanatory string.

  - an error body ("Information", "Note", "Error Message") parsed as data
  - a rate-limit message becoming an empty series that reads as "no trading"
  - the daily budget of 25 spent on requests that were never going to work
  - the API key appearing in an exception message or a URL
  - a constructed timestamp presented as an observed one
  - a premium/realtime endpoint reached through the function parameter
  - a value that is not a price (NaN, 0, negative, null) becoming one

NO REQUEST IS MADE. Every payload is either a verbatim capture in
tests/fixtures/alpha_vantage/ or hand-built here. A probe that spent the user's
25 daily requests to test itself would be the defect, not the test.

Run:  python3 tests/probe_alpha_vantage.py
"""

import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

from market import alpha_vantage as av       # noqa: E402
from market import quotes as q               # noqa: E402

# The project's refusal convention (tests/_harness.py). A crash is NOT a refusal:
# MarketDataError subclasses ValueError, so a guard firing is a refusal while an
# unhandled KeyError is a defect even though both stop execution.
REFUSALS = (ValueError, TypeError, ZeroDivisionError)
FIXTURES = os.path.join(HERE, "fixtures", "alpha_vantage")
KEY = "PROBEKEY1234567890"          # shape-valid; never sent anywhere


def fixture(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as fh:
        return json.load(fh)


def attempt(label, fn):
    try:
        result = fn()
    except REFUSALS as exc:
        print("  REFUSED (%-16s %-52s %s"
              % (type(exc).__name__ + ")", label,
                 str(exc).split("\n")[0][:58]))
        return "refused"
    except Exception as exc:
        print("  !! CRASHED         %-52s %s: %s"
              % (label, type(exc).__name__, str(exc)[:52]))
        return "crashed"
    print("  ** ALLOWED         %-52s -> %r" % (label, str(result)[:40]))
    return "allowed"


def served(payload):
    """A fetch_daily call answered by `payload` instead of the network."""
    def _go():
        saved = av._http_get
        av._http_get = lambda url, api_key, timeout=20.0: payload
        try:
            return av.fetch_daily("IBM", api_key=KEY,
                                  budget=av.RequestBudget())
        finally:
            av._http_get = saved
    return _go


def main():
    out = []
    print("=" * 78)
    print("ADVERSARIAL PROBE: Alpha Vantage connector (no network requests)")
    print("=" * 78)

    # -- 1. the HTTP-200 failure shapes, exactly as captured ----------------
    print("\n[1] captured failure bodies -- all four were HTTP 200 when measured")
    for name in sorted(f for f in os.listdir(FIXTURES) if f.startswith("err_")):
        out.append(attempt("%s parsed as data" % name, served(fixture(name))))

    # -- 2. error bodies I can invent, including ones not yet seen ----------
    print("\n[2] error-shaped bodies the provider could send")
    for key in av.ERROR_KEYS:
        out.append(attempt("%r alone, no series" % key,
                           served({key: "some explanation"})))
        # The dangerous case: a notice arriving WITH data. Checking `if not
        # series` would let this through.
        out.append(attempt("%r alongside a FULL series" % key,
                           served({key: "rate limited",
                                   av.SERIES_KEY: fixture(
                                       "daily_ibm.json")[av.SERIES_KEY]})))
    out.append(attempt("an empty object", served({})))
    out.append(attempt("only Meta Data, no series and no error",
                       served({"Meta Data": {"5. Time Zone": "US/Eastern"}})))
    out.append(attempt("an empty series object",
                       served({av.SERIES_KEY: {}})))
    out.append(attempt("a series that is a list", served({av.SERIES_KEY: []})))
    out.append(attempt("a series that is a string",
                       served({av.SERIES_KEY: "no data"})))
    out.append(attempt("a JSON array at the top level", served([])))
    out.append(attempt("a JSON string at the top level", served("Information")))
    out.append(attempt("a JSON number at the top level", served(0)))
    out.append(attempt("null instead of a payload", served(None)))
    out.append(attempt("true instead of a payload", served(True)))
    # An HTML error page is what a proxy or captive portal returns. json.load
    # would already have failed, but assert_usable_response must not accept the
    # string either.
    out.append(attempt("an HTML error page as a string",
                       served("<html><body>503</body></html>")))

    # -- 3. values that are not prices --------------------------------------
    print("\n[3] rows whose numbers would poison a calculation")
    def row(**over):
        r = {"1. open": "236.0", "2. high": "238.0", "3. low": "235.0",
             "4. close": "237.14", "5. volume": "1000"}
        r.update(over)
        return {"Meta Data": {"5. Time Zone": "US/Eastern"},
                av.SERIES_KEY: {"2026-08-13": r}}
    for bad, label in (("0", "a zero close"), ("-5", "a negative close"),
                       ("NaN", "NaN as a close"), ("inf", "infinity"),
                       ("-inf", "negative infinity"), ("", "an empty close"),
                       ("N/A", "a text close"), (None, "a null close"),
                       ("1e400", "an overflowing literal"),
                       ([], "a list as a close"), ({}, "an object as a close"),
                       ("237.14 USD", "a close with a currency suffix"),
                       ("2,371.4", "a thousands separator")):
        out.append(attempt("%s" % label, served(row(**{"4. close": bad}))))
    out.append(attempt("a row with no close field at all",
                       served({"Meta Data": {},
                               av.SERIES_KEY: {"2026-08-13":
                                               {"5. volume": "1000"}}})))
    out.append(attempt("a row that is a string, not an object",
                       served({"Meta Data": {},
                               av.SERIES_KEY: {"2026-08-13": "237.14"}})))
    out.append(attempt("a row that is a list",
                       served({"Meta Data": {},
                               av.SERIES_KEY: {"2026-08-13": ["237.14"]}})))
    out.append(attempt("a row that is null",
                       served({"Meta Data": {},
                               av.SERIES_KEY: {"2026-08-13": None}})))

    # -- 4. date keys that are not dates ------------------------------------
    print("\n[4] series keys that cannot be turned into an instant")
    for bad in ("13/08/2026", "2026-8-13", "2026-02-31", "", "yesterday",
                "2026-08-13T16:00:00", "0000-00-00", "2026-13-01",
                "20260813", "2026-08-13 ", "latest"):
        out.append(attempt("date key %r" % bad,
                           served({"Meta Data": {},
                                   av.SERIES_KEY: {bad: {"4. close": "1.0"}}})))

    # -- 5. reaching an endpoint the tier cannot lawfully serve -------------
    print("\n[5] asking for data the free tier is not licensed to receive")
    for fn in ("TIME_SERIES_INTRADAY", "GLOBAL_QUOTE", "REALTIME_BULK_QUOTES",
               "TIME_SERIES_WEEKLY", "", None, "time_series_daily",
               "TIME_SERIES_DAILY; DROP TABLE"):
        out.append(attempt("function=%r" % fn,
                           lambda f=fn: av.build_url("IBM", function=f)))
    for status in ("REALTIME", "DELAYED"):
        out.append(attempt("tier asked for %s data" % status,
                           lambda s=status: q.assert_tier_supports(
                               av.PROVIDER_KEY, s)))

    # -- 6. symbols that are not symbols ------------------------------------
    print("\n[6] symbols")
    for bad in ("", " ", "\t", "../../etc/passwd", "IBM IBM",
                "IBM&function=TIME_SERIES_INTRADAY", "IBM#frag", "A" * 40,
                "<script>alert(1)</script>", None, 0, [], "IBM\nGOOG",
                "IBM%26apikey%3Dx", "*", "%s", "IBM'--"):
        out.append(attempt("symbol=%r" % bad, lambda s=bad: av.build_url(s)))
    for bad in ("everything", "", None, "COMPACT", "full "):
        out.append(attempt("outputsize=%r" % bad,
                           lambda o=bad: av.build_url("IBM", outputsize=o)))

    # -- 7. credentials -----------------------------------------------------
    print("\n[7] API keys that must never be used")
    for bad in ("", "   ", "demo", "DEMO", "Demo", "abc", "x" * 200,
                "key with spaces", "key$ymbol", None, 12345,
                "demo\n", " demo "):
        out.append(attempt("api key %r" % bad,
                           lambda k=bad: av.get_api_key(k)))

    # -- 8. the budget ------------------------------------------------------
    print("\n[8] the 25/day budget")
    for bad in (0, -1, -25, 2.5, True, False, "25", None if False else "",
                [], float("inf")):
        out.append(attempt("RequestBudget(limit=%r)" % bad,
                           lambda b=bad: av.RequestBudget(limit=b)))
    exhausted = av.RequestBudget(limit=1)
    exhausted.spend("first")
    out.append(attempt("spending past an exhausted budget",
                       lambda: exhausted.spend("second")))
    out.append(attempt("a fetch on an exhausted budget",
                       lambda: av.fetch_daily("IBM", api_key=KEY,
                                              budget=exhausted)))

    # -- 9. a live order, which this data must never price -------------------
    print("\n[9] using end-of-day data as if it were live")
    saved = av._http_get
    av._http_get = lambda url, api_key, timeout=20.0: fixture("daily_ibm.json")
    try:
        quotes = av.fetch_daily("IBM", api_key=KEY, budget=av.RequestBudget())
    finally:
        av._http_get = saved
    latest = quotes[-1]
    out.append(attempt("assert_usable_for('live_order')",
                       lambda: latest.assert_usable_for("live_order")))
    out.append(attempt("assert_usable_for('material_calculation')",
                       lambda: latest.assert_usable_for("material_calculation")))
    out.append(attempt("relabelling it REALTIME after the fact",
                       lambda: setattr(latest, "delay_status", "REALTIME")))
    out.append(attempt("upgrading its trust level after the fact",
                       lambda: setattr(latest, "trust_level", "EXCHANGE")))
    out.append(attempt("erasing the constructed-timestamp note",
                       lambda: setattr(latest, "note", "")))
    out.append(attempt("claiming the market is OPEN",
                       lambda: setattr(latest, "market_status", "OPEN")))

    # -- 10. structural checks: things that must be TRUE --------------------
    # A probe made only of refusals would pass while the connector returned
    # nothing usable. These assert it still works, and that the key never leaks.
    print("\n[10] structural checks (these must hold, not refuse)")
    ok = True

    def structural(label, condition, detail=""):
        nonlocal ok
        print("  %-7s %-52s %s" % ("ok" if condition else "DEFECT", label,
                                   detail[:60]))
        if not condition:
            ok = False

    structural("100 quotes parsed from the captured payload",
               len(quotes) == 100, "n=%d" % len(quotes))
    structural("every quote is END_OF_DAY",
               all(x.delay_status == "END_OF_DAY" for x in quotes))
    structural("every quote is UNVERIFIED in trust",
               all(x.trust_level == "UNVERIFIED" for x in quotes))
    structural("every quote is PROVIDER_API in origin",
               all(x.origin == "PROVIDER_API" for x in quotes))
    structural("every quote's market_status is UNKNOWN, not CLOSED",
               all(x.market_status == "UNKNOWN" for x in quotes))
    structural("every quote carries the constructed-timestamp assumption",
               all("CONSTRUCTED" in (x.note or "") for x in quotes))
    structural("every quote names USER_ACCEPTED_RISK in its licence",
               all("USER_ACCEPTED_RISK" in (x.licence or "") for x in quotes))
    structural("no quote invents a provider timestamp",
               all(x.provider_timestamp is None for x in quotes))
    structural("a valid quote MAY still be displayed",
               quotes[-1].assert_usable_for("display") is None,
               "refusing everything would be broken, not safe")

    # The key must not survive into anything printable. This is checked on the
    # REAL URL and on a refusal message that contains one.
    url = av.build_url("IBM", api_key=KEY)
    structural("the API key is redactable out of the URL",
               KEY not in av.redact(url, KEY))
    structural("...and redaction leaves a visible marker",
               "[REDACTED-API-KEY]" in av.redact(url, KEY))
    leak = None
    try:
        av._http_get("https://www.alphavantage.co/query?apikey=" + KEY
                     + "&function=BAD", KEY, timeout=0.001)
    except Exception as exc:      # noqa: BLE001 -- inspecting the message only
        leak = str(exc)
    structural("a network failure message does not contain the key",
               leak is None or KEY not in leak,
               "message=%s" % (str(leak)[:40],))

    # The adjusted path, which is where the one real defect was found.
    saved = av._http_get
    av._http_get = lambda u, k, timeout=20.0: fixture("daily_adjusted_ibm.json")
    try:
        adj = av.fetch_daily("IBM", api_key=KEY, budget=av.RequestBudget(),
                             adjusted=True)
    finally:
        av._http_get = saved
    raw = fixture("daily_adjusted_ibm.json")[av.SERIES_KEY]
    differ = [d for d in sorted(raw)
              if float(raw[d]["4. close"]) != float(raw[d]["5. adjusted close"])]
    by_day = {x.timestamp.date().isoformat(): x for x in adj}
    structural("the adjusted payload has days where the two closes differ",
               len(differ) == 96, "n=%d (MEASURED 96)" % len(differ))
    structural("the ADJUSTED fetch returns the adjusted close, not the raw one",
               all(abs(by_day[d].last - float(raw[d]["5. adjusted close"]))
                   < 1e-9 for d in differ),
               "checked on all %d discriminating days" % len(differ))
    structural("every adjusted quote is labelled ADJUSTED",
               all(x.adjustment_status == "ADJUSTED" for x in adj))

    # The gates must run before the budget is spent.
    b = av.RequestBudget()
    try:
        av.fetch_daily("not a ticker", api_key=KEY, budget=b)
    except REFUSALS:
        pass
    structural("a refused request costs nothing from the budget",
               b.used == 0, "used=%d" % b.used)
    b2 = av.RequestBudget()
    saved = av._http_get
    av._http_get = lambda u, k, timeout=20.0: fixture("daily_ibm.json")
    try:
        av.fetch_daily("IBM", api_key=KEY, budget=b2)
    finally:
        av._http_get = saved
    structural("a successful request costs exactly one",
               b2.used == 1, "used=%d" % b2.used)

    print("\n" + "=" * 78)
    allowed, crashed = out.count("allowed"), out.count("crashed")
    print("attempts=%d refused=%d ALLOWED=%d CRASHED=%d structural=%s"
          % (len(out), out.count("refused"), allowed, crashed,
             "OK" if ok else "BROKEN"))
    if allowed or crashed or not ok:
        print("RESULT: defects present. Fix before proceeding.")
        return 1
    print("RESULT: every hostile input refused; the connector still returns "
          "usable labelled quotes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
