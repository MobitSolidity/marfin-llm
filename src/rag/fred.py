"""
FRED client (D-0133): series observations -> Facts, through the registry gate.

The key is read from the argument or the FRED_API_KEY environment variable --
never from a file (the project loads no .env file; set the variable in the OS), never logged, and redacted from every
error message (it travels in the query string, so an un-redacted URL in an
exception would leak it into logs and bug reports).

MEASURED 2026-10-21 with the owner's key: /fred/series/observations for
CPIAUCSL returned HTTP 200 and parsed JSON (957 observations; 2026-09-01 =
336.298). Without a key the API answers HTTP 400 "Variable api_key is not set"
(MEASURED 2026-08-10), which is why check_access() refuses a missing key first.

FRED marks a missing observation with the string "." -- it is skipped, never
read as 0. Every Fact carries the FRED attribution through its provenance, and
callers must display rag.sources.required_notices(["fred"]).

Stdlib only.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, List, Optional

from rag.documents import Fact
from rag.ingest import provenance_for
from rag.sources import check_access

BASE_URL = "https://api.stlouisfed.org/fred"
ENV_KEY = "FRED_API_KEY"
_KEY_RE = re.compile(r"^[0-9a-f]{32}$")
_SERIES_RE = re.compile(r"^[A-Za-z0-9_.]{1,40}$")


class FredError(RuntimeError):
    """A refusal or failure. Its message never contains the API key."""


def redact(text: Any, key: Optional[str]) -> str:
    s = str(text)
    if key:
        s = s.replace(key, "<redacted>")
    return re.sub(r"api_key=[^&\s]+", "api_key=<redacted>", s)


def get_api_key(explicit: Optional[str] = None) -> str:
    key = str(explicit or os.environ.get(ENV_KEY, "")).strip()
    if not key:
        raise FredError("no FRED API key. Set the %s environment variable (Windows: "
                        "setx %s <key>, then open a new terminal). It is read from the "
                        "environment only and never stored in the repository." % (ENV_KEY, ENV_KEY))
    if not _KEY_RE.match(key):
        raise FredError("the FRED API key must be 32 lowercase hex characters; refusing to "
                        "send a malformed key (FRED would answer HTTP 400)")
    return key


def observations_url(series_id: str, api_key: str, limit: int = 10,
                     sort_order: str = "desc") -> str:
    if not _SERIES_RE.match(series_id or ""):
        raise FredError("invalid FRED series id %r" % (series_id,))
    if not isinstance(limit, int) or not 1 <= limit <= 100000:
        raise FredError("limit must be an int in 1..100000")
    if sort_order not in ("asc", "desc"):
        raise FredError("sort_order must be 'asc' or 'desc'")
    q = urllib.parse.urlencode({"series_id": series_id, "file_type": "json",
                                "sort_order": sort_order, "limit": limit,
                                "api_key": api_key})
    return "%s/series/observations?%s" % (BASE_URL, q)


def _http_get(url: str, api_key: str, timeout: float = 20.0) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "marfin-llm/0.10 (personal research)",
                                               "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read()[:300].decode("utf-8", "replace")
        except Exception:                                   # noqa: BLE001
            pass
        raise FredError("HTTP %s from FRED: %s" % (exc.code, redact(body or exc.reason, api_key)))
    except (urllib.error.URLError, OSError) as exc:
        raise FredError("could not reach FRED: %s" % redact(getattr(exc, "reason", exc), api_key))
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        # MEASURED 2026-10-21: during maintenance FRED serves an HTML page at 200.
        raise FredError("FRED did not return JSON (maintenance page?): %r"
                        % redact(raw[:120].decode("utf-8", "replace"), api_key))


def facts_from_observations(series_id: str, payload: Dict[str, Any], unit: str,
                            api_key: Optional[str] = None,
                            retrieved_at: Optional[str] = None) -> List[Fact]:
    """Parse a /series/observations payload. Refuses before parsing if FRED is not permitted."""
    src = check_access("fred", api_key=api_key)
    if not isinstance(payload, dict) or "observations" not in payload:
        msg = payload.get("error_message") if isinstance(payload, dict) else None
        raise FredError("not a FRED observations payload%s" % (": %s" % msg if msg else ""))
    if not unit:
        raise FredError("a unit is required: a bare FRED number has no meaning (SS.5.2)")
    prov = provenance_for("fred", api_key=api_key, url="%s/series/observations?series_id=%s"
                          % (BASE_URL, series_id), source_id=series_id,
                          retrieved_at=retrieved_at, published=None,
                          note="FRED series %s" % series_id)
    out: List[Fact] = []
    for ob in payload["observations"]:
        v = ob.get("value")
        if v in (None, "", "."):            # FRED's missing-value marker: skip, never 0
            continue
        try:
            val = float(v)
        except (TypeError, ValueError):
            raise FredError("non-numeric FRED value %r on %s" % (v, ob.get("date")))
        d = ob.get("date")
        out.append(Fact(series_id, val, unit, prov, period_start=d, period_end=d,
                        period_kind="instant", entity=src.name, label="VERIFIED"))
    return out


def fetch_observations(series_id: str, unit: str, api_key: Optional[str] = None,
                       limit: int = 10, sort_order: str = "desc", timeout: float = 20.0,
                       http_get: Optional[Callable[[str, str, float], Any]] = None) -> List[Fact]:
    """Fetch and parse. The registry gate runs BEFORE any network call."""
    key = get_api_key(api_key)
    check_access("fred", api_key=key)
    url = observations_url(series_id, key, limit=limit, sort_order=sort_order)
    payload = (http_get or _http_get)(url, key, timeout)
    return facts_from_observations(series_id, payload, unit, api_key=key)
