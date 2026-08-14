"""
Alpha Vantage connector -- the project's first live market-data source.

WHY THIS FILE EXISTS NOW AND NOT BEFORE
---------------------------------------
From 2026-08-12 to 2026-08-14 this project had NO connector, and that was
correct: both candidates were blocked on questions only the user could answer.
On 2026-08-14 the user answered both.

  - "Are you employed by or affiliated with a financial advisor, investment
    adviser, bank, or insurance company?"  -> No; sole individual, no
    affiliation, building the project alone. This clears Alpha Vantage exclusion
    criterion (iv) and the "on behalf of a corporation" exclusion.
  - "Are you willing to pay for a Twelve Data tier that permits non-display
    use?" -> No. That closes Twelve Data, which sells the permission by tier.

So Alpha Vantage is enabled on `USER_ACCEPTED_RISK`, NOT on a licence grant. Its
terms are SILENT on machine use -- the token `non-display` appears zero times --
and silence is not permission. quotes.py records that distinction in
`activation_basis` rather than lying with `permits_machine_use=True`.

WHAT WAS MEASURED BEFORE ANY OF THIS WAS WRITTEN
------------------------------------------------
Every design decision below came from probing the real API on 2026-08-14, not
from documentation and not from memory.

1. THE FREE TIER IS 25 REQUESTS PER DAY. Quoted from alphavantage.co/support/:
   "free stock API service covering the majority of our datasets for 25 API
   requests per day". Not 25 per minute. A polling loop would exhaust a day's
   budget in under a minute.

2. THE FREE TIER CANNOT SUPPLY REALTIME OR 15-MINUTE-DELAYED DATA. Quoted:
   "Realtime and 15-minute delayed US market data is regulated by the stock
   exchanges, FINRA, and the SEC" and is premium-only. This is a REGULATORY
   boundary. Every quote this module returns is therefore END_OF_DAY, and
   `assert_usable_for("live_order")` will refuse it -- correctly.

3. EVERY FAILURE RETURNS HTTP 200. This is the finding that shaped the whole
   module, and it is the kind of thing no amount of reading would have revealed.
   MEASURED:
     bad symbol      -> HTTP 200, body {"Information": "The **demo** API key..."}
     unknown function-> HTTP 200, same
     missing symbol  -> HTTP 200, same
   A connector that checks `status == 200` and then reads the payload would treat
   all three as success and hand back an empty series. So this module refuses on
   the SHAPE of the body, never on the status code.

4. AN INVALID API KEY CAN STILL RETURN REAL DATA. MEASURED:
   `apikey=INVALIDKEY999` for IBM returned a full 100-day series. So a successful
   response proves nothing about key validity, and this module never infers "my
   credentials are fine" from data arriving.

5. THE DAILY SERIES HAS NO TIME COMPONENT. Keys are dates ("2026-08-13") and the
   metadata says "5. Time Zone": "US/Eastern". There is no intraday timestamp, so
   constructing a UTC instant requires a stated convention rather than a guess --
   see _session_close_utc().

WHAT THIS MODULE DELIBERATELY DOES NOT DO
-----------------------------------------
No caching to disk. Alpha Vantage's permitted storage timeframes are UNKNOWN
(never read), so market data stays non-persistable, exactly as the licence review
concluded. An in-memory request counter is not a cache of DATA.

No realtime endpoint. No order placement. No key in source.

Stdlib only.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from types import MappingProxyType
from typing import Any, Dict, List, Mapping, Optional, Tuple

from market.quotes import (DELAY_STATUS, FREE_TIER_LIMITS, MarketDataError,
                           Quote, assert_provider_usable, assert_tier_supports,
                           get_provider)

PROVIDER_KEY = "alpha_vantage"

#: The one endpoint this module uses. A tuple of permitted functions rather than
#: a free-form parameter: an unrestricted `function=` would let a caller reach
#: premium endpoints the free tier cannot lawfully serve, and the refusal would
#: arrive as an "Information" string that looks like a data problem.
PERMITTED_FUNCTIONS = ("TIME_SERIES_DAILY", "TIME_SERIES_DAILY_ADJUSTED")

BASE_URL = "https://www.alphavantage.co/query"

#: Alpha Vantage states the daily series is stamped in US/Eastern. The exchange
#: session closes at 16:00 local. Since the payload carries no time, this module
#: stamps each bar at the CLOSE and records the convention in the Quote's note --
#: rather than defaulting to midnight, which would place a US close on the wrong
#: side of a day boundary for anyone reading it in Tehran.
SESSION_CLOSE_HOUR = 16
#: US/Eastern is UTC-5 (EST) or UTC-4 (EDT). Without zoneinfo data guaranteed
#: present, this module does NOT guess which: it labels the timezone exactly as
#: the provider stated it and leaves the offset out of the instant, marking the
#: timestamp as a date-with-convention. Inventing an offset would be fabricating
#: precision the payload does not contain.
PROVIDER_TIMEZONE = "US/Eastern"

_SYMBOL_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,15}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

#: The keys Alpha Vantage uses to report a problem while still returning 200.
#: MEASURED: "Information" is what the demo key and every malformed request
#: produced. "Note" is the documented rate-limit key and "Error Message" the
#: documented bad-parameter key; both are included because a response carrying
#: any of them contains no usable series, and treating an unknown one as data is
#: the failure this module exists to prevent.
ERROR_KEYS = ("Error Message", "Information", "Note")


class AlphaVantageError(MarketDataError):
    """
    A request could not be turned into trustworthy observations.

    Subclasses MarketDataError so existing refusal handling catches it, and so a
    caller cannot accidentally treat a provider failure as a different class of
    problem from an unusable quote.
    """


# ---------------------------------------------------------------------------
# Request budget. MEASURED at 25/day; enforced, not documented.
# ---------------------------------------------------------------------------

class RequestBudget(object):
    """
    Counts requests against the MEASURED free-tier limit of 25 per day.

    In memory only. This is honest about what it is: if the process restarts the
    count restarts, so it cannot be the sole protection against exceeding the
    provider's limit. It exists to stop the failure this project can actually
    cause -- a loop that fires 25 requests in a second and silently returns
    rate-limit strings as data for the rest of the day.

    It is NOT a cache. Storing the responses would breach the storage clause
    whose permitted timeframes are UNKNOWN.
    """

    __slots__ = ("limit", "_day", "_used", "_calls")

    def __init__(self, limit: Optional[int] = None):
        if limit is None:
            limit = FREE_TIER_LIMITS[PROVIDER_KEY]["requests_per_day"]
        if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
            raise AlphaVantageError(
                "request budget limit must be a positive integer, got %r"
                % (limit,))
        self.limit = limit
        self._day = None
        self._used = 0
        self._calls = []

    def _today(self) -> str:
        return datetime.datetime.now(datetime.timezone.utc).date().isoformat()

    @property
    def used(self) -> int:
        if self._day != self._today():
            return 0
        return self._used

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)

    def spend(self, what: str = "") -> int:
        """Reserve one request, or refuse. Returns the number remaining after."""
        today = self._today()
        if self._day != today:
            self._day = today
            self._used = 0
            self._calls = []
        if self._used >= self.limit:
            raise AlphaVantageError(
                "the free-tier budget of %d requests/day is exhausted (%d used "
                "today, UTC). MEASURED from %s. Further requests would return "
                "a rate-limit message with HTTP 200, which is indistinguishable "
                "from data unless inspected -- so they are refused here instead. "
                "Use the CSV path (SS.7.1 Level 2) or supply the price directly "
                "(Level 0)."
                % (self.limit, self._used,
                   FREE_TIER_LIMITS[PROVIDER_KEY]["source"]))
        self._used += 1
        self._calls.append((datetime.datetime.now(
            datetime.timezone.utc).isoformat(), str(what)[:120]))
        return self.limit - self._used

    def to_dict(self) -> Dict[str, Any]:
        return {"limit": self.limit, "used": self.used,
                "remaining": self.remaining, "day_utc": self._day,
                "calls": list(self._calls),
                "in_memory_only": True,
                "note": "resets on process restart; not a substitute for the "
                        "provider's own accounting, and NOT a data cache"}


#: The module-level budget. One per process, because the limit is per API key.
BUDGET = RequestBudget()


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------

def get_api_key(explicit: Optional[str] = None) -> str:
    """
    The API key, from the argument or ALPHAVANTAGE_API_KEY.

    Never from a file in the repo, and never defaulted to "demo". MEASURED: the
    demo key answers ONLY the exact documented sample request and returns
    {"Information": ...} for everything else -- so a silent fallback to it would
    produce refusals that look like the provider is broken.
    """
    key = explicit or os.environ.get("ALPHAVANTAGE_API_KEY", "")
    key = str(key).strip()
    if not key:
        raise AlphaVantageError(
            "no Alpha Vantage API key. Set ALPHAVANTAGE_API_KEY in the "
            "environment (free key: alphavantage.co/support/#api-key). It is "
            "read from the environment and never stored in the repository.")
    if key.lower() == "demo":
        raise AlphaVantageError(
            "refusing the 'demo' key. MEASURED 2026-08-14: it serves one "
            "hard-coded sample request and answers everything else with "
            "{\"Information\": \"The **demo** API key is for demo purposes "
            "only...\"} at HTTP 200. Accepting it would make every other symbol "
            "look like a provider outage.")
    if not re.match(r"^[A-Za-z0-9]{8,64}$", key):
        raise AlphaVantageError(
            "the API key does not look like an Alpha Vantage key (expected 8-64 "
            "alphanumeric characters). Refusing rather than sending it, because "
            "a malformed key still returns HTTP 200 and the response would be "
            "indistinguishable from a data problem.")
    return key


def redact(text: str, key: str) -> str:
    """Remove the API key from anything about to be logged or raised."""
    if not key:
        return text
    return str(text).replace(key, "[REDACTED-API-KEY]")


# ---------------------------------------------------------------------------
# Response validation. The whole point of this module.
# ---------------------------------------------------------------------------

def assert_usable_response(payload: Any, series_key: str,
                           context: str = "") -> Mapping[str, Any]:
    """
    Refuse a 200 response that contains no series.

    This is the module's central guard, and it exists because of a MEASUREMENT
    rather than a theory: every failure mode this API has -- unknown symbol,
    unknown function, missing parameter, demo-key misuse, rate limit -- arrives
    as HTTP 200 with an explanatory STRING and no data. Checking the status code
    would pass all of them.
    """
    if not isinstance(payload, dict):
        raise AlphaVantageError(
            "expected a JSON object from Alpha Vantage, got %s. %s"
            % (type(payload).__name__, context))
    for k in ERROR_KEYS:
        if k in payload:
            raise AlphaVantageError(
                "Alpha Vantage returned HTTP 200 with no data: %s=%r. %s "
                "(Every failure this API has -- bad symbol, bad key, rate "
                "limit -- looks like a success at the transport layer, which is "
                "why the body is inspected rather than the status code.)"
                % (k, str(payload[k])[:300], context))
    if series_key not in payload:
        raise AlphaVantageError(
            "response contains no %r and no error key either; keys present: %s. "
            "Refusing rather than returning an empty series: an empty result "
            "that reads as 'no trading activity' is worse than an error."
            % (series_key, sorted(payload)[:12]))
    series = payload[series_key]
    if not isinstance(series, dict) or not series:
        raise AlphaVantageError(
            "%r is %s with %d entries -- unusable. %s"
            % (series_key, type(series).__name__,
               len(series) if hasattr(series, "__len__") else -1, context))
    return series


def _num(raw: Any, field: str, date: str) -> float:
    """Parse one OHLCV number, refusing the values that break calculations."""
    try:
        value = float(str(raw).strip())
    except (TypeError, ValueError):
        raise AlphaVantageError(
            "%s for %s is not a number: %r" % (field, date, raw))
    if value != value or value in (float("inf"), float("-inf")):
        raise AlphaVantageError(
            "%s for %s is %r. A non-finite price propagates through every "
            "calculation without raising, so it is refused at the boundary."
            % (field, date, value))
    if value < 0:
        raise AlphaVantageError(
            "%s for %s is negative (%r)" % (field, date, value))
    if field != "volume" and value == 0:
        # Volume may legitimately be zero. A zero PRICE cannot be: it is the
        # value a missing field takes when someone coerces it, and it produces
        # -100% returns that look like real crashes.
        raise AlphaVantageError(
            "%s for %s is zero. A zero price is not an observation; it is what "
            "a missing field becomes when coerced, and it yields a -100%% "
            "return that reads as a real event." % (field, date))
    return value


def _session_close_utc(date_str: str) -> Tuple[datetime.datetime, str]:
    """
    Turn a bare date into an instant, and say what was assumed.

    MEASURED: the daily payload has no time component; keys are dates and the
    metadata states "US/Eastern". So an instant cannot be READ from the response,
    only CONSTRUCTED -- and the construction needs a stated convention. This
    stamps 16:00 US/Eastern (the session close) and returns the assumption text
    alongside, so it lands in the Quote's note instead of disappearing.

    The returned datetime is UTC-labelled at the session-close hour WITHOUT an
    EST/EDT offset applied, because the payload does not say which was in force
    and guessing would fabricate up to an hour of false precision. Callers doing
    intraday work must not use this series -- and cannot, since delay_status is
    END_OF_DAY and assert_usable_for("live_order") refuses it.
    """
    if not _DATE_RE.match(str(date_str)):
        raise AlphaVantageError(
            "expected an ISO date key (YYYY-MM-DD), got %r" % (date_str,))
    try:
        d = datetime.date.fromisoformat(date_str)
    except ValueError as exc:
        raise AlphaVantageError("unparseable date %r: %s" % (date_str, exc))
    stamp = datetime.datetime(d.year, d.month, d.day, SESSION_CLOSE_HOUR, 0,
                              tzinfo=datetime.timezone.utc)
    assumption = (
        "timestamp CONSTRUCTED, not observed: the daily payload carries a date "
        "only. Stamped at %02d:00 (session close) and labelled tz=%s as the "
        "provider states. No EST/EDT offset was applied because the payload "
        "does not say which applied on this date; do not treat this instant as "
        "accurate to the hour." % (SESSION_CLOSE_HOUR, PROVIDER_TIMEZONE))
    return stamp, assumption


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------

def build_url(symbol: str, function: str = "TIME_SERIES_DAILY",
              outputsize: str = "compact", api_key: str = "") -> str:
    """Build the query URL. Validates before any network call."""
    if function not in PERMITTED_FUNCTIONS:
        raise AlphaVantageError(
            "function %r is not permitted here (allowed: %s). The free tier "
            "cannot lawfully serve realtime or 15-minute-delayed endpoints, and "
            "requesting one returns an 'Information' string at HTTP 200 that "
            "reads like a data fault."
            % (function, ", ".join(PERMITTED_FUNCTIONS)))
    sym = str(symbol or "").strip().upper()
    if not _SYMBOL_RE.match(sym):
        raise AlphaVantageError(
            "symbol %r is not a plausible ticker. Refused before the request, "
            "because an unknown symbol also returns HTTP 200 with no data and "
            "would spend one of only %d daily requests to learn nothing."
            % (symbol, FREE_TIER_LIMITS[PROVIDER_KEY]["requests_per_day"]))
    if outputsize not in ("compact", "full"):
        raise AlphaVantageError(
            "outputsize must be 'compact' or 'full', got %r" % (outputsize,))
    params = {"function": function, "symbol": sym, "outputsize": outputsize,
              "apikey": api_key, "datatype": "json"}
    return BASE_URL + "?" + urllib.parse.urlencode(params)


def _http_get(url: str, api_key: str, timeout: float = 20.0) -> Any:
    """One GET. Raises with the key redacted from every message."""
    req = urllib.request.Request(
        url, headers={"User-Agent": "marfin-llm/0.1 (personal, non-commercial)",
                      "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", resp.getcode())
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        raise AlphaVantageError(
            "HTTP %s from Alpha Vantage: %s"
            % (exc.code, redact(str(exc.reason), api_key)))
    except urllib.error.URLError as exc:
        raise AlphaVantageError(
            "could not reach Alpha Vantage: %s. No data is returned and none is "
            "invented; the caller should fall back to SS.7.1 Level 0/2."
            % (redact(str(exc.reason), api_key),))
    except OSError as exc:
        raise AlphaVantageError(
            "network error contacting Alpha Vantage: %s"
            % (redact(str(exc), api_key),))
    if status != 200:
        raise AlphaVantageError("unexpected HTTP status %s" % (status,))
    try:
        return json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise AlphaVantageError("response is not valid UTF-8: %s" % (exc,))
    except ValueError as exc:
        raise AlphaVantageError(
            "response is not valid JSON: %s. First 200 bytes: %r"
            % (exc, redact(raw[:200].decode("utf-8", "replace"), api_key)))


def fetch_daily(symbol: str, exchange: str = "UNKNOWN",
                currency: str = "USD", api_key: Optional[str] = None,
                outputsize: str = "compact", budget: Optional[RequestBudget] = None,
                timeout: float = 20.0,
                adjusted: bool = False) -> List[Quote]:
    """
    Fetch the daily series and return it as SS.5.5 Quotes.

    Every returned Quote is:
      origin        PROVIDER_API   (it did come from an API)
      delay_status  END_OF_DAY     (MEASURED: the free tier cannot serve
                                    realtime or 15-min data -- a regulatory
                                    limit, so this is not pessimism)
      trust_level   UNVERIFIED     (the licence position is UNKNOWN; a source
                                    enabled on a human's accepted risk must not
                                    outrank one whose terms were actually read)

    The consequence is deliberate and worth stating plainly: because
    trust_level is UNVERIFIED these quotes are NOT sole-source material for a
    material calculation, and assert_usable_for("live_order") refuses them. That
    is the honest position for data whose licence is silent and whose timestamp
    is constructed.
    """
    provider = assert_provider_usable(PROVIDER_KEY)
    # The tier gate runs BEFORE the budget is spent: asking for data the tier
    # cannot lawfully supply should not cost one of 25 daily requests.
    assert_tier_supports(PROVIDER_KEY, "END_OF_DAY")
    key = get_api_key(api_key)
    function = "TIME_SERIES_DAILY_ADJUSTED" if adjusted else "TIME_SERIES_DAILY"
    url = build_url(symbol, function=function, outputsize=outputsize,
                    api_key=key)
    b = budget if budget is not None else BUDGET
    b.spend("%s %s" % (function, str(symbol).upper()))

    payload = _http_get(url, key, timeout=timeout)
    series_key = ("Time Series (Daily)" if not adjusted
                  else "Time Series (Daily)")
    series = assert_usable_response(
        payload, series_key,
        context="symbol=%s function=%s" % (str(symbol).upper(), function))

    meta = payload.get("Meta Data", {})
    stated_tz = str(meta.get("5. Time Zone", PROVIDER_TIMEZONE))
    retrieved = datetime.datetime.now(datetime.timezone.utc)

    quotes: List[Quote] = []
    for date_str in sorted(series):
        row = series[date_str]
        if not isinstance(row, dict):
            raise AlphaVantageError(
                "the entry for %s is %s, not an object"
                % (date_str, type(row).__name__))
        close = None
        for field in ("4. close", "5. adjusted close", "close"):
            if field in row:
                close = _num(row[field], field, date_str)
                break
        if close is None:
            raise AlphaVantageError(
                "no close field for %s; keys present: %s"
                % (date_str, sorted(row)[:8]))
        stamp, assumption = _session_close_utc(date_str)
        quotes.append(Quote(
            provider=PROVIDER_KEY, symbol=str(symbol).strip().upper(),
            instrument_id=None, exchange=exchange, asset_class=None,
            currency=currency, timestamp=stamp, timezone=stated_tz,
            delay_status="END_OF_DAY",
            # The payload says nothing about session state, and a daily bar is
            # by definition a closed session -- but "CLOSED" would assert
            # knowledge of the CURRENT market, which this response does not
            # carry. UNKNOWN is the truthful label.
            market_status="UNKNOWN",
            adjustment_status="ADJUSTED" if adjusted else "UNADJUSTED",
            corporate_action_status="UNKNOWN",
            trust_level="UNVERIFIED",
            origin="PROVIDER_API",
            provider_timestamp=None, retrieved_at=retrieved,
            last=close,
            licence="Alpha Vantage free tier, personal non-commercial use; "
                    "terms SILENT on machine use; enabled on USER_ACCEPTED_RISK "
                    "(see docs/legal/market-data-providers.md)",
            note=assumption))
    return quotes


def manifest() -> Dict[str, Any]:
    """What this connector is, and what it cannot do."""
    p = get_provider(PROVIDER_KEY)
    return {
        "provider": PROVIDER_KEY,
        "enabled": p.enabled,
        "activation_basis": p.activation_basis,
        "permits_machine_use": p.permits_machine_use,
        "trust_level_of_quotes": "UNVERIFIED",
        "delay_status_of_quotes": "END_OF_DAY",
        "permitted_functions": list(PERMITTED_FUNCTIONS),
        "budget": BUDGET.to_dict(),
        "accepted_risks": list(p.accepted_risks),
        "decided_by": p.decided_by,
        "decided_on": p.decided_on,
        "cannot": [
            "supply realtime or 15-minute-delayed quotes (regulatory, "
            "premium-only -- MEASURED 2026-08-14)",
            "be the sole basis of a material calculation (trust UNVERIFIED)",
            "price a live order (assert_usable_for('live_order') refuses)",
            "persist data (permitted storage timeframes UNKNOWN)",
            "exceed 25 requests/day (MEASURED; enforced by RequestBudget)",
        ],
        "measured_on": "2026-08-14",
    }
