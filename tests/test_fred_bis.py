# -*- coding: utf-8 -*-
"""
D-0133: FRED and BIS-statistics clients. Offline: the HTTP layer is injected, so
no key and no network are needed, and the owner's real key never appears here.

(V) verified invariant, (A) adversarial: must be refused, (B) hand-checked value.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

from _harness import check, check_raises, check_true, section, summary  # noqa: E402
from rag import bis_stats as B                                           # noqa: E402
from rag import fred as F                                                # noqa: E402
from rag import sources as S                                             # noqa: E402

FAKE = "0123456789abcdef0123456789abcdef"     # shape of a FRED key; not a real one
REF = (F.FredError, B.BisStatsError, S.AccessError, ValueError)

# ===========================================================================
section("FRED: the key comes from the environment only, and is never echoed")
# ===========================================================================
_saved = os.environ.pop("FRED_API_KEY", None)
check_raises("no key anywhere: refused before any network call", lambda: F.get_api_key(), F.FredError)
os.environ["FRED_API_KEY"] = FAKE
check_true("key read from FRED_API_KEY", F.get_api_key() == FAKE, "(V)")
os.environ["FRED_API_KEY"] = "  " + FAKE + "\n"
check_true("surrounding whitespace (e.g. a pasted line) is stripped", F.get_api_key() == FAKE, "(V)")
for bad in ("demo", FAKE[:-1], FAKE.upper(), FAKE + "0", "z" * 32):
    check_raises("malformed key refused: %r" % bad[:12], lambda b=bad: F.get_api_key(b), F.FredError)
os.environ.pop("FRED_API_KEY", None)
if _saved is not None:
    os.environ["FRED_API_KEY"] = _saved
check_true("redact() removes the key and any api_key= value",
           F.redact("GET ...&api_key=%s&x=1 failed (%s)" % (FAKE, FAKE), FAKE).count(FAKE) == 0
           and "api_key=<redacted>" in F.redact("u?api_key=%s" % FAKE, FAKE), "(A)")
_seen = {}


def _boom(url, key, timeout):
    _seen["url"] = url
    raise F.FredError("HTTP 400 from FRED: " + F.redact(url, key))


try:
    F.fetch_observations("CPIAUCSL", "index", api_key=FAKE, http_get=_boom)
    _msg = ""
except F.FredError as exc:
    _msg = str(exc)
check_true("an HTTP failure message never contains the key", FAKE not in _msg and "<redacted>" in _msg, "(A)")
check_true("the request did carry the key (in the query string, as FRED requires)",
           "api_key=%s" % FAKE in _seen.get("url", ""), "(V)")

# ===========================================================================
section("FRED: URL building refuses bad input")
# ===========================================================================
check_true("observations URL uses file_type=json and the series id",
           "series_id=DGS10" in F.observations_url("DGS10", FAKE) and "file_type=json"
           in F.observations_url("DGS10", FAKE), "(V)")
for bad in ("", "a b", "x;rm", "../x", "A" * 41):
    check_raises("series id refused: %r" % bad[:10], lambda b=bad: F.observations_url(b, FAKE), F.FredError)
check_raises("limit 0 refused", lambda: F.observations_url("DGS10", FAKE, limit=0), F.FredError)
check_raises("sort order other than asc/desc refused",
             lambda: F.observations_url("DGS10", FAKE, sort_order="rand"), F.FredError)

# ===========================================================================
section("FRED: payload -> Facts (MEASURED shape, 2026-10-21)")
# ===========================================================================
PAY = {"realtime_start": "2026-10-21", "units": "lin", "count": 957, "observations": [
    {"date": "2026-09-01", "value": "336.298"}, {"date": "2026-08-01", "value": "334.131"},
    {"date": "2026-07-01", "value": "."}]}
fs = F.facts_from_observations("CPIAUCSL", PAY, "index 1982-1984=100", api_key=FAKE)
check("two numeric observations; FRED's '.' (missing) is skipped, never 0", len(fs), 2, method="(B)")
check("CPIAUCSL 2026-09-01 = 336.298 (MEASURED value)", fs[0].value, 336.298, method="(B)")
check_true("each Fact carries FRED provenance at OFFICIAL_DATA (90)",
           fs[0].provenance.trust_level == "OFFICIAL_DATA" and fs[0].provenance.source_id == "CPIAUCSL", "(V)")
check_true("the provenance licence is the registry's, which names the mandatory notice",
           "REQUIRED_NOTICES['fred']" in fs[0].provenance.licence, "(V)")
check_true("the unit is required and kept", fs[0].unit == "index 1982-1984=100", "(V)")
check_raises("no unit: refused (a bare number is meaningless)",
             lambda: F.facts_from_observations("CPIAUCSL", PAY, "", api_key=FAKE), F.FredError)
check_raises("FRED error payload is refused with its message",
             lambda: F.facts_from_observations("X", {"error_code": 400, "error_message": "Bad Request"},
                                               "u", api_key=FAKE), F.FredError)
check_raises("non-numeric value refused, not guessed",
             lambda: F.facts_from_observations("X", {"observations": [{"date": "2026-01-01", "value": "n/a"}]},
                                               "u", api_key=FAKE), F.FredError)
check_raises("no key: the registry gate refuses even an in-hand payload",
             lambda: F.facts_from_observations("CPIAUCSL", PAY, "u", api_key=None), S.AccessError)
_calls = []
F.fetch_observations("CPIAUCSL", "index", api_key=FAKE, http_get=lambda u, k, t: _calls.append(u) or PAY)
check("fetch: exactly one HTTP call", len(_calls), 1, method="(V)")
check_true("the FRED notice is what required_notices(['fred']) displays",
           S.required_notices(["fred"]) == [S.REQUIRED_NOTICES["fred"]], "(V)")
check_true("FRED is recorded as verified end to end, with the measured values",
           "END TO END" in S.SOURCES["fred"].verified_status and "336.298" in S.SOURCES["fred"].verified_status
           and S.SOURCES["fred"].verified_on == "2026-10-21", "(V)")
# The real key is compared only when the owner's upload exists on this machine,
# and no part of it is written in this file (a prefix would still disclose it).
_up = "/home/user/uploaded_files/FRED.env.txt"
_real = None
if os.path.exists(_up):
    import re as _re
    _m = _re.search(r"[0-9a-f]{32}", open(_up, encoding="utf-8", errors="ignore").read())
    _real = _m.group(0) if _m else None
_tracked = __import__("subprocess").check_output(["git", "-C", ROOT, "ls-files"]).decode().split()
check_true("the real FRED key is in no tracked file (checked when the owner's upload is present)",
           _real is None or not any(_real in open(os.path.join(ROOT, t), encoding="utf-8", errors="ignore").read()
                                    for t in _tracked if os.path.isfile(os.path.join(ROOT, t))), "(A)")

# ===========================================================================
section("BIS statistics: separate, unrestricted licence; publications stay capped")
# ===========================================================================
src = S.SOURCES["bis_statistics"]
check_true("bis_statistics is enabled with a MEASURED payload and the licence quoted",
           src.enabled and "HTTP 200, payload parsed" in src.verified_status
           and "The use of the statistics is unrestricted" in src.licence, "(V)")
check_true("BIS publications remain disabled (400-word extract cap)",
           not S.SOURCES["bis_working_papers"].enabled, "(V)")
check_true("bis_statistics scope excludes publications", "statistics only" in src.licence, "(V)")
check_true("BIS citation condition is discharged by required_notices()",
           any("Bank for International Settlements" in n for n in S.required_notices(["bis_statistics"])), "(V)")
CSV = ("FREQ,REF_AREA,TITLE,TIME_PERIOD,OBS_VALUE\n"
       "D,US,Central bank policy rates - United States,2026-10-20,3.875\n"
       "D,US,Central bank policy rates - United States,2026-10-19,NaN\n")
bf = B.facts_from_csv("WS_CBPOL", "D.US", CSV, "percent")
check("one numeric row; NaN skipped, never 0", len(bf), 1, method="(B)")
check("US policy rate 2026-10-20 = 3.875 (MEASURED)", bf[0].value, 3.875, method="(B)")
check_true("BIS Fact at OFFICIAL_DATA with series id", bf[0].provenance.trust_level == "OFFICIAL_DATA"
           and bf[0].concept == "WS_CBPOL:D.US", "(V)")
check("cross-check: 3.875 is the mid-point of the NY Fed-reported 3.75-4.00 target range",
      (3.75 + 4.00) / 2, bf[0].value, method="(B)")
check_raises("not CSV: refused", lambda: B.facts_from_csv("WS_CBPOL", "D.US", "<xml/>", "percent"),
             B.BisStatsError)
check_raises("non-daily period refused (no silent mis-dating)",
             lambda: B.facts_from_csv("WS_CBPOL", "M.US", "TIME_PERIOD,OBS_VALUE\n2026-09,3.875\n", "percent"),
             B.BisStatsError)
check_raises("no unit: refused", lambda: B.facts_from_csv("WS_CBPOL", "D.US", CSV, ""), B.BisStatsError)
for bad in ("ws_cbpol", "X;Y", ""):
    check_raises("bad dataflow refused: %r" % bad, lambda b=bad: B.data_url(b, "D.US"), B.BisStatsError)
check_raises("bad key refused", lambda: B.data_url("WS_CBPOL", "D US"), B.BisStatsError)
check_true("BIS URL requests CSV and the last N observations",
           "format=csv" in B.data_url("WS_CBPOL", "D.US", 5) and "lastNObservations=5" in B.data_url(
               "WS_CBPOL", "D.US", 5), "(V)")

print("")
sys.exit(summary())
