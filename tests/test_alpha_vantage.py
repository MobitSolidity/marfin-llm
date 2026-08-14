"""
Verification of the Alpha Vantage connector (src/market/alpha_vantage.py).

WHY THIS SUITE USES SAVED PAYLOADS AND NOT THE NETWORK
------------------------------------------------------
The free tier is 25 requests per DAY (MEASURED, recorded in FREE_TIER_LIMITS). A
suite that called the API would consume the user's daily allowance every time it
ran, and once exhausted the API returns a rate-limit STRING at HTTP 200 -- so the
suite would then be testing the connector against error bodies. Tests must not
compete with the user for a scarce resource.

So every payload in tests/fixtures/alpha_vantage/ is a verbatim capture from the
live API on 2026-08-14, and only the single HTTP function is substituted. What is
under test is the parsing and refusal logic, which is where every defect found so
far has actually lived.

THE MEASUREMENTS THIS SUITE ENCODES
-----------------------------------
1. EVERY failure returns HTTP 200. Bad symbol, unknown function, missing
   parameter and demo-key misuse were all measured: four HTTP 200s with an
   "Information" string. A connector checking the status code treats all four as
   success, so refusal must key on the SHAPE OF THE BODY.
2. An INVALID key still returns real data (apikey=INVALIDKEY999 returned a full
   100-day IBM series), so a successful response proves nothing about the key.
3. Both TIME_SERIES_DAILY and TIME_SERIES_DAILY_ADJUSTED return the SAME
   container key, "Time Series (Daily)". The adjusted one does not say
   "Adjusted" anywhere in it.
4. The adjusted payload carries BOTH "4. close" and "5. adjusted close", and on
   IBM's 100-day window 96 of 100 days DIFFER -- the relative gap peaking at
   1.4351%, with the largest absolute gap 3.6692 on 2026-04-21 (raw 255.6800 vs
   adjusted 252.0108), because of two dividend events. Re-derived from the saved
   fixture rather than quoted from memory. Reading the wrong field is a wrong
   price under a correct-looking label.
5. The daily payload has no time component, so a timestamp can only be
   CONSTRUCTED. That assumption has to travel with the quote.

Stdlib only.
"""

import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "src"))

from _harness import check, check_raises, check_true, section, summary  # noqa: E402

import market.alpha_vantage as av                                      # noqa: E402
from market.alpha_vantage import (AlphaVantageError, CLOSE_FIELD,      # noqa: E402
                                  ERROR_KEYS, PERMITTED_FUNCTIONS,
                                  PROVIDER_KEY, RequestBudget,
                                  SERIES_KEY, assert_usable_response,
                                  build_url, fetch_daily, get_api_key,
                                  manifest, redact)
import market.quotes as mq                                             # noqa: E402
from market.quotes import MarketDataError                              # noqa: E402

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "fixtures", "alpha_vantage")
GOOD_KEY = "TESTKEY1234567890"       # shape-valid, and never sent anywhere


def fixture(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as fh:
        return json.load(fh)


def fetch_from(name, **over):
    """Run the REAL fetch_daily against a saved payload.

    Only av._http_get is replaced -- validation, the budget, the tier gate, the
    licence gate and Quote construction all run for real. A fake that returned
    finished Quotes would test nothing.
    """
    saved = av._http_get
    av._http_get = lambda url, api_key, timeout=20.0: fixture(name)
    try:
        kw = dict(symbol="IBM", exchange="NYSE", currency="USD",
                  api_key=GOOD_KEY, budget=RequestBudget())
        kw.update(over)
        return fetch_daily(**kw)
    finally:
        av._http_get = saved


def with_payload(payload, fn):
    """Run fn() with a hand-built payload standing in for the response."""
    saved = av._http_get
    av._http_get = lambda url, api_key, timeout=20.0: payload
    try:
        return fn()
    finally:
        av._http_get = saved


def why(fn):
    """The refusal MESSAGE. Only MarketDataError is caught: anything else must
    escape and crash the suite rather than be reshaped into a string that
    happens not to contain the expected phrase."""
    try:
        fn()
    except MarketDataError as exc:
        return str(exc)
    return "DID NOT RAISE"


# ---------------------------------------------------------------------------
section("every failure arrives as HTTP 200: refusal must read the BODY")
# ---------------------------------------------------------------------------
# The four captured failures are byte-for-byte what the live API returned. Each
# is a 200 and each must be refused. A connector checking the status code would
# return all four as successful data.

for _name in ("err_bad_symbol.json", "err_unknown_function.json",
              "err_missing_symbol.json", "err_demo_misuse.json"):
    _payload = fixture(_name)
    check_true("%s really is an error-shaped 200 body" % _name,
               any(k in _payload for k in ERROR_KEYS)
               and SERIES_KEY not in _payload,
               "(V) captured live 2026-08-14. If this fails the fixture has "
               "drifted and every assertion below it proves nothing")
    check_raises("%s is refused, not parsed" % _name,
                 lambda n=_name: fetch_from(n), AlphaVantageError)
    check_true("...and the refusal names the mechanism",
               "HTTP 200 with no data" in why(lambda n=_name: fetch_from(n)),
               "(D) a caller told only 'failed' would retry, and each retry "
               "costs one of only 25 requests per day")

# A 200 with NEITHER data NOR an error key is the case nobody writes a branch
# for. It must not become an empty series that reads as "no trading activity".
check_raises("a 200 with no series and no error key is refused",
             lambda: assert_usable_response({"Meta Data": {}}, SERIES_KEY),
             AlphaVantageError)
check_true("...and says so rather than returning empty",
           "no error key either" in why(
               lambda: assert_usable_response({"Meta Data": {}}, SERIES_KEY)),
           "(D) an empty result reading as 'no trading activity' is worse than "
           "an error, because it is actionable and wrong")
check_raises("an empty series object is refused",
             lambda: assert_usable_response({SERIES_KEY: {}}, SERIES_KEY),
             AlphaVantageError)
check_raises("a series that is a LIST is refused",
             lambda: assert_usable_response({SERIES_KEY: []}, SERIES_KEY),
             AlphaVantageError)
check_raises("a JSON array instead of an object is refused",
             lambda: assert_usable_response([], SERIES_KEY), AlphaVantageError)
check_raises("a bare JSON string is refused",
             lambda: assert_usable_response("Information", SERIES_KEY),
             AlphaVantageError)
# None is what a failed parse produces. `if not payload` would treat it as the
# same fault as an empty dict, and the two need different remedies.
check_raises("None instead of a payload is refused",
             lambda: assert_usable_response(None, SERIES_KEY),
             AlphaVantageError)

# Each error key ALONE, so none can be dropped from ERROR_KEYS unnoticed. The
# series is present in every case: what makes the response unusable is the
# NOTICE, not the absence of rows.
for _k in ERROR_KEYS:
    check_raises("the %r key alone is enough to refuse" % _k,
                 lambda k=_k: assert_usable_response(
                     {k: "whatever the provider said",
                      SERIES_KEY: {"2026-08-13": {"4. close": "1"}}},
                     SERIES_KEY),
                 AlphaVantageError)
check_true("...even with a FULL series present alongside it",
           "HTTP 200 with no data" in why(
               lambda: assert_usable_response(
                   {"Note": "rate limited",
                    SERIES_KEY: fixture("daily_ibm.json")[SERIES_KEY]},
                   SERIES_KEY)),
           "(D) MEASURED shape: the provider can send both. Data arriving next "
           "to a rate-limit notice is not trustworthy data")


# ---------------------------------------------------------------------------
section("the container key was measured, not guessed")
# ---------------------------------------------------------------------------
# In the module this looked like a copy-paste bug: a conditional whose two
# branches were identical. It was checked before being "fixed".

check_true("both permitted functions use the same container key",
           SERIES_KEY == "Time Series (Daily)",
           "(V) MEASURED 2026-08-14: TIME_SERIES_DAILY and "
           "TIME_SERIES_DAILY_ADJUSTED both return top-level keys "
           "['Meta Data', 'Time Series (Daily)']")
for _f in ("daily_ibm.json", "daily_adjusted_ibm.json"):
    check_true("%s contains %r verbatim" % (_f, SERIES_KEY),
               SERIES_KEY in fixture(_f),
               "(V) the adjusted endpoint does NOT say 'Adjusted' in its key; "
               "the tidier-looking guess would have refused every call")


# ---------------------------------------------------------------------------
section("adjusted vs unadjusted: a wrong price under a correct label")
# ---------------------------------------------------------------------------
# A DEFECT found on 2026-08-14 and measured before it was fixed. The module tried
# "4. close" first for BOTH functions, and the adjusted payload contains both
# fields -- so adjusted=True read the unadjusted number while the Quote was still
# labelled ADJUSTED.

_adj_raw = fixture("daily_adjusted_ibm.json")[SERIES_KEY]
_differ = [d for d in sorted(_adj_raw)
           if float(_adj_raw[d]["4. close"])
           != float(_adj_raw[d]["5. adjusted close"])]
check("96 of the 100 captured days have a DIFFERENT adjusted close",
      len(_differ), 96, 0,
      "(V) MEASURED. This anchors everything below: if the two fields agreed "
      "everywhere, no test here could detect the defect at all")
check_true("the divergence is material, not rounding",
           max(abs(float(_adj_raw[d]["4. close"])
                   - float(_adj_raw[d]["5. adjusted close"]))
               for d in _differ) > 3.0,
           "(V) largest absolute gap 3.6692 on 2026-04-21 (raw 255.6800 vs "
           "adjusted 252.0108), a relative gap of 1.4351%, caused by two real "
           "dividend events (2026-05-08 and 2026-08-10, 1.69 each)")
check_true("the field read is decided by what was ASKED FOR",
           CLOSE_FIELD[False] == "4. close"
           and CLOSE_FIELD[True] == "5. adjusted close",
           "(C) not by whichever key happens to appear first in the row")

_unadj_q = fetch_from("daily_ibm.json", adjusted=False)
_adj_q = fetch_from("daily_adjusted_ibm.json", adjusted=True)
check("the unadjusted fetch returns 100 quotes", len(_unadj_q), 100, 0, "(C)")
check("the adjusted fetch returns 100 quotes", len(_adj_q), 100, 0, "(C)")

# The LATEST day happens to have close == adjusted close, so it cannot
# discriminate: asserting on the newest quote would pass with the defect
# restored. The witness is therefore a day where the two fields differ.
_by_day = {q.timestamp.date().isoformat(): q for q in _adj_q}
_probe = _differ[0]
check_true("a day where the two fields differ is used as the witness",
           _probe in _by_day,
           "(D) MEASURED: on the most recent day the values coincide, so the "
           "newest row proves nothing")
check_true("the ADJUSTED fetch returns the ADJUSTED close on that day",
           abs(_by_day[_probe].last
               - float(_adj_raw[_probe]["5. adjusted close"])) < 1e-9,
           "(D) %s: adjusted=%s unadjusted=%s"
           % (_probe, _adj_raw[_probe]["5. adjusted close"],
              _adj_raw[_probe]["4. close"]))
check_true("...and NOT the unadjusted one",
           abs(_by_day[_probe].last
               - float(_adj_raw[_probe]["4. close"])) > 1.0,
           "(D) this is the assertion the defect failed")
check_true("every adjusted quote is labelled ADJUSTED",
           all(q.adjustment_status == "ADJUSTED" for q in _adj_q),
           "(C) the label must match the field actually read")
check_true("every unadjusted quote is labelled UNADJUSTED",
           all(q.adjustment_status == "UNADJUSTED" for q in _unadj_q),
           "(C) an UNADJUSTED label on adjusted data is the same fault mirrored")

# The fallback that CAUSED the defect must be gone: a missing field is now a
# refusal, not a quiet substitution of a number that means something else.
_no_adj = {"Meta Data": {"5. Time Zone": "US/Eastern"},
           SERIES_KEY: {"2026-08-13": {"1. open": "236.0", "2. high": "238.0",
                                       "3. low": "235.0", "4. close": "237.14",
                                       "5. volume": "1000"}}}
check_raises("asking for ADJUSTED data the payload lacks is refused",
             lambda: with_payload(_no_adj, lambda: fetch_daily(
                 "IBM", api_key=GOOD_KEY, budget=RequestBudget(),
                 adjusted=True)),
             AlphaVantageError)
check_true("...and the refusal names the missing field",
           "5. adjusted close" in why(
               lambda: with_payload(_no_adj, lambda: fetch_daily(
                   "IBM", api_key=GOOD_KEY, budget=RequestBudget(),
                   adjusted=True))),
           "(D) silently using '4. close' here IS the defect")
check_true("...and says why a fallback would be wrong",
           "means something different" in why(
               lambda: with_payload(_no_adj, lambda: fetch_daily(
                   "IBM", api_key=GOOD_KEY, budget=RequestBudget(),
                   adjusted=True))),
           "(D) the number exists; it just answers a different question")
check_true("...while the SAME payload is fine when UNADJUSTED is asked for",
           len(with_payload(_no_adj, lambda: fetch_daily(
               "IBM", api_key=GOOD_KEY, budget=RequestBudget(),
               adjusted=False))) == 1,
           "(C) the connector discriminates rather than refusing both")


# ---------------------------------------------------------------------------
section("the timestamp is CONSTRUCTED, and says so")
# ---------------------------------------------------------------------------
# MEASURED: the daily payload's keys are bare dates. An instant cannot be READ
# from it, only BUILT from a stated convention -- and the risk is that the
# convention quietly becomes a fact.

_q = _unadj_q[-1]
check("the latest captured session is stamped at the 16:00 close",
      _q.timestamp.hour, 16, 0,
      "(C) midnight would put a US close on the wrong calendar day for a "
      "reader in Tehran")
check_true("the assumption travels WITH the quote, in its note",
           "CONSTRUCTED, not observed" in (_q.note or ""),
           "(D) an assumption recorded only in a docstring is not available to "
           "whoever later reads the number")
check_true("...and the note records that no EST/EDT offset was applied",
           "does not say which applied" in (_q.note or ""),
           "(D) picking one would fabricate up to an hour of false precision")
check_true("the timezone label is the provider's own string",
           _q.timezone == "US/Eastern",
           "(V) copied from '5. Time Zone' in the payload, not inferred")
check_true("every quote carries the assumption, not just the last one",
           all("CONSTRUCTED" in (x.note or "") for x in _unadj_q),
           "(D) a caveat on one row of a hundred is decoration")
check_raises("a non-ISO date key is refused",
             lambda: av._session_close_utc("13/08/2026"), AlphaVantageError)
check_raises("an impossible date is refused",
             lambda: av._session_close_utc("2026-02-31"), AlphaVantageError)
check_raises("an empty date is refused",
             lambda: av._session_close_utc(""), AlphaVantageError)
check_raises("a date with a time attached is refused",
             lambda: av._session_close_utc("2026-08-13T16:00"),
             AlphaVantageError)


# ---------------------------------------------------------------------------
section("the labels the rest of the system will act on")
# ---------------------------------------------------------------------------
# Each of these is enforced elsewhere, so a wrong value here would defeat a
# guard that is itself well tested.

check_true("every quote is END_OF_DAY",
           all(q.delay_status == "END_OF_DAY" for q in _unadj_q),
           "(V) the free tier cannot lawfully supply realtime or 15-min data")
check_true("every quote is PROVIDER_API in origin",
           all(q.origin == "PROVIDER_API" for q in _unadj_q),
           "(C) it did arrive over an API -- a claim about the PATH")
check_true("every quote is UNVERIFIED in trust",
           all(q.trust_level == "UNVERIFIED" for q in _unadj_q),
           "(C) and a separate claim about AUTHORITY: the licence position is "
           "unknown and the timestamp is constructed")
check_true("market_status is UNKNOWN, not CLOSED",
           all(q.market_status == "UNKNOWN" for q in _unadj_q),
           "(D) a daily bar IS a closed session, but the payload says nothing "
           "about the CURRENT market and 'CLOSED' would assert that it does")
check_true("the licence string names the basis it was enabled on",
           all("USER_ACCEPTED_RISK" in (q.licence or "") for q in _unadj_q),
           "(D) so a quote read months from now still carries WHY it exists")
check_true("the provider timestamp is left None, not invented",
           all(q.provider_timestamp is None for q in _unadj_q),
           "(D) the provider stated no instant; an echo of our own construction "
           "would look like corroboration")

# The downstream consequences, asserted rather than assumed.
check_true("no quote from this connector is 'weak' by origin",
           not any(q.is_weak for q in _unadj_q),
           "(C) the path was clean, and that is the honest reading of it")
check_raises("...but it still cannot price a live order",
             lambda: _unadj_q[-1].assert_usable_for("live_order"))
check_raises("...and cannot be sole evidence for a material calculation",
             lambda: _unadj_q[-1].assert_usable_for("material_calculation"))
check_true("...while it MAY be displayed with its labels",
           _unadj_q[-1].assert_usable_for("display") is None,
           "(C) refusing to show it would train the user to bypass the layer")
check_true("the material-calculation refusal names the TRUST level",
           "trust_level=UNVERIFIED" in why(
               lambda: _unadj_q[-1].assert_usable_for("material_calculation")),
           "(D) not the origin: this connector's data is refused for authority, "
           "and a reader told 'bad origin' would look for the wrong fix")


# ---------------------------------------------------------------------------
section("numbers that break calculations are refused at the boundary")
# ---------------------------------------------------------------------------

for _bad, _label in ((float("nan"), "NaN"), (float("inf"), "infinity"),
                     ("-1", "a negative price"), ("0", "a zero price"),
                     ("", "an empty string"), ("N/A", "a non-numeric string"),
                     (None, "null"), ("1e400", "an overflowing literal")):
    check_raises("%s is refused as a close" % _label,
                 lambda b=_bad: av._num(b, "4. close", "2026-08-13"),
                 AlphaVantageError)
check_true("a zero price is refused WITH the reason",
           "reads as a real event" in why(
               lambda: av._num("0", "4. close", "2026-08-13")),
           "(D) zero is what a missing field becomes when coerced, and it "
           "yields a -100% return that looks like a crash")
check_true("volume MAY be zero",
           av._num("0", "volume", "2026-08-13") == 0.0,
           "(C) a session with no trades is a real observation; refusing it "
           "would be the mirror-image error")
check_true("a normal price parses",
           av._num("237.1400", "4. close", "2026-08-13") == 237.14, "(C)")

# A row that is not an object is the shape a truncated response takes.
check_raises("a series entry that is a string, not an object, is refused",
             lambda: with_payload(
                 {"Meta Data": {}, SERIES_KEY: {"2026-08-13": "237.14"}},
                 lambda: fetch_daily("IBM", api_key=GOOD_KEY,
                                     budget=RequestBudget())),
             AlphaVantageError)
check_raises("a null price inside an otherwise valid row is refused",
             lambda: with_payload(
                 {"Meta Data": {}, SERIES_KEY: {"2026-08-13":
                                                {"4. close": None}}},
                 lambda: fetch_daily("IBM", api_key=GOOD_KEY,
                                     budget=RequestBudget())),
             AlphaVantageError)


# ---------------------------------------------------------------------------
section("the API key: never defaulted, never logged")
# ---------------------------------------------------------------------------

check_raises("a missing key is refused, not defaulted to 'demo'",
             lambda: get_api_key(""), AlphaVantageError)
check_raises("the literal 'demo' key is refused",
             lambda: get_api_key("demo"), AlphaVantageError)
check_raises("...in any casing", lambda: get_api_key("DEMO"),
            AlphaVantageError)
check_true("...and the refusal explains why it is worse than nothing",
           "look like a provider outage" in why(lambda: get_api_key("demo")),
           "(D) MEASURED: the demo key answers ONE sample request and returns "
           "an Information string for everything else")
check_raises("a malformed key is refused before it is sent",
             lambda: get_api_key("has spaces and $ymbols"), AlphaVantageError)
check_raises("a too-short key is refused", lambda: get_api_key("abc"),
             AlphaVantageError)
check_true("a plausible key is accepted", get_api_key(GOOD_KEY) == GOOD_KEY,
           "(C) the guard must not refuse everything")

# Redaction. The key travels in the query string, so any URL in any message is a
# leak unless it is removed.
_url = build_url("IBM", api_key=GOOD_KEY)
check_true("the key DOES appear in the URL that gets sent", GOOD_KEY in _url,
           "(C) it is a query parameter -- that is how this API authenticates, "
           "which is exactly why redaction is needed")
check_true("...and redact() removes it", GOOD_KEY not in redact(_url, GOOD_KEY),
           "(D) otherwise an exception message or log line publishes it")
check_true("...replacing it with a visible marker",
           "[REDACTED-API-KEY]" in redact(_url, GOOD_KEY),
           "(D) silent removal would make a truncated URL look like a bug")
check_true("redact() is safe when there is no key to remove",
           redact("plain text", "") == "plain text", "(C)")


# ---------------------------------------------------------------------------
section("what the connector refuses to ask for")
# ---------------------------------------------------------------------------
# Refusing BEFORE the request matters twice over: the answer would be useless,
# and asking spends one of only 25 daily requests to learn nothing.

check_raises("a premium function is refused",
             lambda: build_url("IBM", function="TIME_SERIES_INTRADAY"),
             AlphaVantageError)
check_raises("an invented function is refused",
             lambda: build_url("IBM", function="GET_EVERYTHING"),
             AlphaVantageError)
check_true("...and the refusal gives the regulatory reason",
           "cannot lawfully serve realtime" in why(
               lambda: build_url("IBM", function="TIME_SERIES_INTRADAY")),
           "(D) a caller told only 'not permitted' goes looking for a workaround")
for _f in PERMITTED_FUNCTIONS:
    check_true("%s is permitted" % _f,
               "function=" + _f in build_url("IBM", function=_f), "(C)")

for _sym, _label in (("", "an empty symbol"), (" ", "whitespace"),
                     ("../../etc/passwd", "a path"),
                     ("IBM IBM", "an embedded space"),
                     ("IBM&function=X", "a smuggled parameter"),
                     ("A" * 40, "an over-long symbol"),
                     ("<script>", "markup"), (None, "None")):
    check_raises("%s is refused as a symbol" % _label,
                 lambda s=_sym: build_url(s), AlphaVantageError)
check_true("a real ticker is accepted", "symbol=IBM" in build_url("IBM"), "(C)")
check_true("a lowercase ticker is normalised, not refused",
           "symbol=IBM" in build_url("ibm"),
           "(C) case is not a security property; refusing it would be noise")
check_true("a dotted ticker is accepted",
           "symbol=BRK.B" in build_url("brk.b"),
           "(C) real tickers contain dots and hyphens")
check_raises("an invalid outputsize is refused",
             lambda: build_url("IBM", outputsize="everything"),
             AlphaVantageError)
check_true("datatype is pinned to json", "datatype=json" in build_url("IBM"),
           "(D) a CSV response would parse as garbage rather than refuse")


# ---------------------------------------------------------------------------
section("the request budget: 25 per day, enforced")
# ---------------------------------------------------------------------------
# MEASURED: "25 API requests per day". Not per minute. Once exhausted the API
# returns a rate-limit message at HTTP 200, indistinguishable from data unless
# inspected -- so the budget refuses locally first.

_b = RequestBudget()
check("the default budget is the MEASURED 25", _b.limit, 25, 0,
      "(V) read from FREE_TIER_LIMITS rather than written down twice")
check("a fresh budget has spent nothing", _b.used, 0, 0, "(C)")
check("...and has all 25 remaining", _b.remaining, 25, 0, "(C)")
_b.spend("test")
check("spending one leaves 24", _b.remaining, 24, 0, "(C)")
check("...and records it as used", _b.used, 1, 0, "(C)")

_small = RequestBudget(limit=2)
_small.spend("a")
_small.spend("b")
check_raises("the budget refuses the request past its limit",
             lambda: _small.spend("c"), AlphaVantageError)
check_true("...naming the limit and where the number came from",
           "budget of 2 requests/day is exhausted" in why(
               lambda: _small.spend("c"))
           and "alphavantage.co" in why(lambda: _small.spend("c")),
           "(D) so the figure can be re-checked when the tier changes")
check_true("...and pointing at the fallbacks that still work",
           "CSV path" in why(lambda: _small.spend("c")),
           "(D) a dead end invites the user to disable the guard")
check("an exhausted budget reports 0 remaining", _small.remaining, 0, 0, "(C)")

check_raises("a zero budget limit is refused",
             lambda: RequestBudget(limit=0), AlphaVantageError)
check_raises("a negative budget limit is refused",
             lambda: RequestBudget(limit=-5), AlphaVantageError)
check_raises("a float budget limit is refused",
             lambda: RequestBudget(limit=2.5), AlphaVantageError)
# bool is an int subclass, so isinstance(True, int) is True: without an explicit
# check, RequestBudget(limit=True) would silently mean a limit of one.
check_raises("True is refused as a budget limit",
             lambda: RequestBudget(limit=True), AlphaVantageError)
check_raises("a string budget limit is refused",
             lambda: RequestBudget(limit="25"), AlphaVantageError)

# The budget must be honest about being in-memory. Claiming durability it does
# not have would be worse than the limitation itself.
_d = RequestBudget().to_dict()
check_true("the budget declares that it is in-memory only",
           _d["in_memory_only"] is True and "restart" in _d["note"],
           "(D) it cannot be the sole protection against exceeding the "
           "provider's limit and must not be presented as if it were")
check_true("...and that it is NOT a data cache",
           "NOT a data cache" in _d["note"],
           "(D) storing responses would breach a storage clause whose "
           "permitted timeframes are UNKNOWN")

# The gates must run BEFORE the budget is spent: a request the tier cannot serve
# should not cost one of 25.
_b2 = RequestBudget()
check_raises("an invalid symbol never reaches the network",
             lambda: fetch_daily("not a ticker", api_key=GOOD_KEY, budget=_b2),
             AlphaVantageError)
check("...and costs nothing from the budget", _b2.used, 0, 0,
      "(D) validating after spending would burn the daily allowance on typos")
_b3 = RequestBudget()
check_raises("a refused API key never reaches the network",
             lambda: fetch_daily("IBM", api_key="demo", budget=_b3),
             AlphaVantageError)
check("...and also costs nothing", _b3.used, 0, 0, "(C)")
# A successful fetch DOES spend exactly one -- otherwise the counter is decorative.
_b4 = RequestBudget()
_saved = av._http_get
av._http_get = lambda url, api_key, timeout=20.0: fixture("daily_ibm.json")
try:
    fetch_daily("IBM", api_key=GOOD_KEY, budget=_b4)
finally:
    av._http_get = _saved
check("a successful fetch spends exactly one request", _b4.used, 1, 0,
      "(D) a budget that never increments would report 25 remaining forever")


# ---------------------------------------------------------------------------
section("the manifest reports the position honestly")
# ---------------------------------------------------------------------------

_m = manifest()
_mj = json.dumps(_m)
check_true("the manifest names the provider", _m.get("provider") == PROVIDER_KEY,
           "(C)")
check_true("...records the activation basis",
           _m.get("activation_basis") == "USER_ACCEPTED_RISK",
           "(D) a report that omits WHY this is on cannot be reviewed later")
check_true("...and does NOT claim the licence permits machine use",
           _m.get("permits_machine_use") is None,
           "(D) 'non-display' appears 0 times in those terms; silence is not a "
           "grant and True here would be a falsehood")
check_true("...records the 25/day limit", "25" in _mj,
           "(C) a report omitting the binding constraint is not a report")
check_true("...records what it CANNOT do",
           any("realtime" in c.lower() for c in _m["cannot"])
           and any("live order" in c.lower() for c in _m["cannot"]),
           "(C) the user asked for a free tier; what it cannot do is part of "
           "the answer, not a footnote")
check_true("...and carries the accepted risks with an owner and a date",
           len(_m["accepted_risks"]) >= 3 and _m["decided_by"]
           and _m["decided_on"],
           "(D) an accepted risk with no owner is indistinguishable from a "
           "default nobody chose")
check_true("the quotes' trust level is reported as UNVERIFIED",
           _m.get("trust_level_of_quotes") == "UNVERIFIED",
           "(C) and must match what fetch_daily actually stamps")
check_true("...which it does",
           all(q.trust_level == _m["trust_level_of_quotes"] for q in _unadj_q),
           "(D) a manifest that disagrees with the code is worse than none")

# ---------------------------------------------------------------------------
section("closing eight mutation survivors: the guard under test must be the "
        "guard that answers")
# ---------------------------------------------------------------------------
# Every assertion below exists because a seeded defect SURVIVED this suite on
# 2026-08-14, and each survivor was MEASURED before anything was written. The
# pattern behind seven of the eight is the same one that has now appeared in
# every battery in this project: a SECOND guard answered in place of the one
# being tested, so the test passed while the guard it named was dead.
#
# The remedy is never to relax an assertion. It is to choose an input that only
# the guard under test can answer, or -- when no such input exists -- to assert
# the refusal MESSAGE, because two guards refusing the same input still say
# different things.

# -- S1: a series that is a LIST -------------------------------------------
# MEASURED: [] and [1, 2] are BOTH refused today ("is list with N entries"), so
# every existing test passed. But the seeded defect weakened the check to
# `if not series:` -- which still refuses the EMPTY list and lets a NON-EMPTY one
# through. No test used a non-empty list, so the emptiness half of the guard was
# doing all the work and the isinstance half was untested.
check_raises("a series that is a non-empty LIST is refused, not iterated",
             lambda: assert_usable_response(
                 {SERIES_KEY: [{"4. close": "1"}]}, SERIES_KEY,
                 context="probe"),
             AlphaVantageError)
check_true("...and the refusal names the TYPE, so it is the isinstance check "
           "answering and not the emptiness check",
           "is list with 1 entries" in why(lambda: assert_usable_response(
               {SERIES_KEY: [{"4. close": "1"}]}, SERIES_KEY, context="probe")),
           "(D) a truthiness test alone accepts a non-empty list of the wrong "
           "shape, and the failure then surfaces as a TypeError deep in the "
           "parse loop instead of a refusal at the boundary")
check_raises("a series that is a non-empty STRING is refused too",
             lambda: assert_usable_response(
                 {SERIES_KEY: "2026-08-13"}, SERIES_KEY, context="probe"),
             AlphaVantageError)
check_true("...naming str, because a string is iterable and would otherwise "
           "parse into one 'row' per character",
           "is str with 10 entries" in why(lambda: assert_usable_response(
               {SERIES_KEY: "2026-08-13"}, SERIES_KEY, context="probe")),
           "(D) the most dangerous wrong type here is the one that iterates "
           "without complaint")
check_true("the empty list is still refused, so neither half was traded away",
           "is list with 0 entries" in why(lambda: assert_usable_response(
               {SERIES_KEY: []}, SERIES_KEY, context="probe")),
           "(D) a fix that closes one gap by opening another is not a fix")

# -- S2: a row that is not an object ---------------------------------------
# MEASURED: all five wrong row types are refused today. The seeded defect removed
# the guard entirely and the tests still passed -- because row[want] then raises a
# raw TypeError, which check_raises(AlphaVantageError) does NOT accept but which
# an unqualified "it raised" style of assertion would have. The refusal text is
# what distinguishes a checked boundary from a crash.
for _bad_row, _typename in (("astring", "str"), (["a"], "list"),
                            (None, "NoneType"), (5, "int"), (True, "bool")):
    _row_payload = {"Meta Data": {"5. Time Zone": "US/Eastern"},
                    SERIES_KEY: {"2026-08-13": _bad_row}}
    _row_why = with_payload(
        _row_payload,
        lambda: why(lambda: fetch_daily(symbol="IBM", api_key=GOOD_KEY,
                                        budget=RequestBudget())))
    check_true("a row that is %s is refused BY NAME, not by crashing in the "
               "parse" % _typename,
               "is %s, not an object" % _typename in _row_why,
               "(D) MEASURED: with the type guard removed the same input raises "
               "TypeError from row[field]. A test that only asks 'did something "
               "go wrong' cannot tell a boundary refusal from a bug.")

# -- S3: a non-numeric price coerced -------------------------------------
# MEASURED: the seeded defect was float(str(raw).strip() or 0), which changes
# behaviour for EXACTLY two inputs -- "" and " " -- turning them into 0.0. And
# 0.0 is then refused by the ZERO-PRICE guard three lines further down. So the
# defect was fully shadowed: the input was still refused, by a different guard,
# with a different message. Only the message separates them.
check_true("an EMPTY price is refused as NOT A NUMBER, not as a zero",
           "is not a number: ''" in why(
               lambda: av._num("", "4. close", "2026-08-13")),
           "(D) MEASURED: coercing '' to 0 is still refused -- by the zero-price "
           "guard. The distinction matters because the two describe different "
           "faults: one is a missing field, the other is a real price of zero, "
           "and only the first should read as 'the payload was malformed'.")
check_true("a BLANK price is refused as not a number as well",
           "is not a number: ' '" in why(
               lambda: av._num(" ", "4. close", "2026-08-13")),
           "(D) the only other input the coercion defect changes")
check_true("a genuine '0' is still refused by the ZERO guard, with its own "
           "wording",
           "is zero" in why(lambda: av._num("0", "4. close", "2026-08-13")),
           "(V) confirms the two guards really are distinguishable by message, "
           "which is what makes the assertion above meaningful")
check_true("...and the zero refusal explains the -100%% return, so the two "
           "messages cannot be confused",
           "-100%" in why(lambda: av._num("0.0", "4. close", "2026-08-13")),
           "(C) a reader who sees the wrong message diagnoses the wrong fault")

# -- S4: an invented EST/EDT offset ---------------------------------------
# MEASURED: the constructed stamp is 2026-08-13 16:00:00+00:00 with
# utcoffset()==0. The seeded defect stamped tzinfo=UTC-4 instead -- the same
# WALL-CLOCK hour, so every existing assertion (hour == 16) still passed while
# the instant moved by four hours. The hour is not the property under test; the
# OFFSET is.
_stamp, _assumption = av._session_close_utc("2026-08-13")
check_true("the constructed instant carries a ZERO offset, not a guessed "
           "EST/EDT one",
           _stamp.utcoffset() == datetime.timedelta(0),
           "(D) MEASURED: seeding UTC-4 leaves hour==16 intact and moves the "
           "instant four hours. Asserting the hour cannot see that; asserting "
           "the offset can.")
check_true("...and the same holds for every quote the fetch produces",
           all(q.timestamp.utcoffset() == datetime.timedelta(0)
               for q in _unadj_q),
           "(D) one checked row out of a hundred is not a checked series")
check_true("the note states plainly that no offset was applied",
           "No EST/EDT offset was applied" in _assumption,
           "(D) a zero offset that is not DECLARED reads as UTC fact rather "
           "than as an unresolved unknown")
check_true("the stamp is UTC-labelled rather than naive",
           _stamp.tzinfo is datetime.timezone.utc,
           "(C) a naive datetime silently takes on the reader's local zone, "
           "which for this user is +03:30 and not the US session at all")

# -- S5: the licence string ------------------------------------------------
# MEASURED full string: 'Alpha Vantage free tier, personal non-commercial use;
# terms SILENT on machine use; enabled on USER_ACCEPTED_RISK (see
# docs/legal/market-data-providers.md)'. The seeded defect dropped
# "personal non-commercial use" while KEEPING "USER_ACCEPTED_RISK" -- and the
# only assertion was on the latter. Each clause of a licence label has to be
# asserted, because each one is a separate claim about what may lawfully be done.
_lic = _unadj_q[-1].licence or ""
check_true("the licence names the USE the free tier is limited to",
           "personal non-commercial use" in _lic,
           "(D) MEASURED: the seeded defect removed exactly this clause and the "
           "suite passed, because only USER_ACCEPTED_RISK was asserted. Dropping "
           "it would leave a quote that reads as licensed for any use.")
check_true("...that the terms are SILENT rather than permissive",
           "SILENT on machine use" in _lic,
           "(V) silence is not a grant; the label must not round it up to one")
check_true("...and that the enabling basis was a decision, not a permission",
           "USER_ACCEPTED_RISK" in _lic,
           "(D) the accountability half of the same label")
check_true("...and points at the document holding the reasoning",
           "docs/legal/market-data-providers.md" in _lic,
           "(D) a risk accepted with no retrievable basis is a risk nobody can "
           "later review")

# -- S6: the demo-key check's case sensitivity ---------------------------
# MEASURED, and this one corrected an earlier assumption. All four casings are
# refused today BY THE DEMO GUARD. Under the seeded defect (key == "demo") the
# uppercase form is no longer caught there -- but it is 4 characters long, so the
# 8-64 alphanumeric LENGTH regex refuses it instead. check_raises therefore
# cannot see the difference at all. Only the message can.
for _casing in ("demo", "DEMO", "Demo", "dEmO"):
    _dwhy = why(lambda c=_casing: get_api_key(c))
    check_true("the key %r is refused BY THE DEMO GUARD, whatever its case"
               % _casing,
               "refusing the 'demo' key" in _dwhy,
               "(D) MEASURED: with the comparison made case-sensitive, %r is "
               "still refused -- by the 8-64 character length regex, which "
               "happens to catch a 4-character string. Same outcome, wrong "
               "reason, and the reason is what stops a longer disguised demo "
               "key later." % _casing)
    check_true("...and not by the length regex standing in for it",
               "does not look like an Alpha Vantage key" not in _dwhy,
               "(D) if the length guard answers, the demo guard is untested")

# -- SKIP: a missing key silently defaulted to demo -----------------------
# This mutation SKIPPED on 2026-08-14, and the skip was the finding: its
# find-string "    if not key:" occurs TWICE in the module (MEASURED with
# str.count) because redact() opens with the same line. An ambiguous mutation
# tests nothing while still printing a line, which is why a SKIP is treated here
# as worse than a survivor. Re-targeted with the preceding strip() line, which
# occurs exactly once.
check_true("a missing key is refused, and the refusal says the key is MISSING",
           "no Alpha Vantage API key" in why(lambda: get_api_key("")),
           "(D) the failure being prevented is a silent fallback to the demo "
           "key, which answers one hard-coded request and makes every other "
           "symbol look like a provider outage")
check_true("...and points at the environment variable rather than a repo file",
           "ALPHAVANTAGE_API_KEY" in why(lambda: get_api_key("")),
           "(D) the alternative a reader reaches for is a file in the repo")
check_true("...and never quietly becomes the demo key",
           "refusing the 'demo' key" not in why(lambda: get_api_key("")),
           "(D) MEASURED: defaulting a missing key to 'demo' IS still refused, "
           "by the demo guard -- so the outcome looks identical and only the "
           "message distinguishes a missing key from a forbidden one")

# -- S7 and S8: the two gates fetch_daily runs before spending anything ---
# These two survived because Alpha Vantage is now ENABLED and its tier DOES
# permit END_OF_DAY, so both gates say yes on every happy path and removing them
# changes nothing observable. MEASURED before writing: the gates are reachable,
# and each can be made to refuse.
#
# S7 needs a provider that is registered but disabled. Provider terms are
# immutable by design, so the normal route is refused (asserted below, because
# that immutability is itself load-bearing) and object.__setattr__ is the only
# way in -- the same technique the market battery needed to reach a fail-open
# default.
_av_provider = mq.PROVIDERS[PROVIDER_KEY]
check_raises("provider terms cannot be flipped by ordinary assignment",
             lambda: setattr(_av_provider, "enabled", False),
             MarketDataError)
object.__setattr__(_av_provider, "enabled", False)
try:
    check_true("a DISABLED provider is still returned by the plain lookup",
               mq.get_provider(PROVIDER_KEY) is _av_provider,
               "(V) which is exactly why the lookup is not a gate: this is the "
               "difference the seeded defect exploited")
    _gate_budget = RequestBudget(limit=5)
    _gate_why = with_payload(
        fixture("daily_ibm.json"),
        lambda: why(lambda: fetch_daily(symbol="IBM", api_key=GOOD_KEY,
                                        budget=_gate_budget)))
    check_true("...but the FETCH refuses it, so the licence gate is a gate",
               "is registered but not enabled" in _gate_why,
               "(D) MEASURED: replacing assert_provider_usable with "
               "get_provider changes nothing while the provider is enabled, so "
               "the gate can only be tested against one that is not")
    check(" ...and a request refused at the licence gate costs no allowance",
          _gate_budget.used, 0, 0,
          "(C) 25 requests per DAY: paying for a request that was never sent "
          "is a whole day's budget lost to a bug")
finally:
    object.__setattr__(_av_provider, "enabled", True)
check_true("the provider was restored to enabled after the probe",
           mq.PROVIDERS[PROVIDER_KEY].enabled is True,
           "(D) a test that leaves global state altered corrupts every suite "
           "that runs after it")

# S8 needs a tier that does NOT permit END_OF_DAY. FREE_TIER_LIMITS is a
# MappingProxy, so the module attribute is swapped rather than mutated -- and
# assert_tier_supports reads it as a module global, so the substitution is seen.
_saved_limits = mq.FREE_TIER_LIMITS
try:
    mq.FREE_TIER_LIMITS = {PROVIDER_KEY: {
        "requests_per_day": 25,
        "permitted_delay_status": ("REALTIME",),
        "source": "synthetic probe, tests/test_alpha_vantage.py"}}
    _tier_budget = RequestBudget(limit=5)
    _tier_why_msg = with_payload(
        fixture("daily_ibm.json"),
        lambda: why(lambda: fetch_daily(symbol="IBM", api_key=GOOD_KEY,
                                        budget=_tier_budget)))
    check_true("a tier that does not permit END_OF_DAY stops the daily fetch",
               "not licensed to supply END_OF_DAY data" in _tier_why_msg,
               "(D) MEASURED: with the real limits in place the gate always "
               "says yes, so deleting it is invisible. The gate exists to stop "
               "a quote whose LABEL outruns the licence, and only a tier that "
               "refuses can demonstrate it still runs.")
    check(" ...and the refusal happens BEFORE the request is paid for",
          _tier_budget.used, 0, 0,
          "(D) the gate is placed above the budget spend on purpose: asking "
          "for data the tier cannot lawfully supply must not consume one of "
          "the 25")
finally:
    mq.FREE_TIER_LIMITS = _saved_limits
check_true("the real free-tier limits were restored after the probe",
           mq.FREE_TIER_LIMITS is _saved_limits
           and mq.FREE_TIER_LIMITS[PROVIDER_KEY]["requests_per_day"] == 25,
           "(D) the measured 25/day constraint must survive its own test")
check_true("...and the restored tier permits END_OF_DAY again",
           "END_OF_DAY"
           in mq.FREE_TIER_LIMITS[PROVIDER_KEY]["permitted_delay_status"],
           "(V) otherwise every later suite would refuse for the wrong reason")


sys.exit(summary())
