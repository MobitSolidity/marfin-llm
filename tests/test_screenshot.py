"""
Tests for SS.7.1 Level 3 visual integration (market.screenshot).

WHAT THIS MODULE IS, AND WHY IT NEEDS ITS OWN SUITE
It is 649 lines of consent and licence guards for a capability THIS RUNTIME DOES
NOT HAVE: there is no capture backend and no OCR backend. That combination is the
most dangerous kind of code in the project. Nothing exercises it, so nothing
notices when a guard rots, and the day a backend is installed is the day every
one of these refusals starts mattering -- at which point they will be believed
rather than tested.

The module's own history says the same thing. Its docstring once claimed
TradingView extraction "is refused via tradingview.assert_display_only_use()",
and the function to do it existed -- but NOTHING CALLED IT. MEASURED at the time:
a TradingView window produced a usable Quote. A licence wall reachable only by a
caller who already knows to invoke it protects nothing.

HOW THESE ASSERTIONS ARE WRITTEN
Every refusal is asserted on its MESSAGE, not merely its type. This module has
many guards that raise the same ScreenshotError, and several sit behind one
another -- consent, then forbidden-target screening, then availability. A
type-only assertion cannot tell which one answered, so a guard could be deleted
and the one behind it would answer in its place, silently. That masking pattern
has been found in every mutation battery in this project so far.

Positive controls are included deliberately: an ordinary chart window IS
approvable, a non-TradingView window DOES build a Quote, and a valid approval
DOES cover its window. Without them, a module that refused everything would pass.

Stdlib only. No network, no display, no capture.
"""

import datetime
import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _harness import check, check_true, check_raises, section, summary  # noqa: E402

import market.screenshot as ss  # noqa: E402
from market.screenshot import (CAPABILITY_PROBE, CAPTURE_AVAILABLE,  # noqa: E402
                               FORBIDDEN_TARGETS, OCR_AVAILABLE,
                               STRUCTURALLY_PREVENTED, TRADINGVIEW_MARKERS,
                               CaptureApproval, ScreenshotError,
                               assert_capture_permitted,
                               assert_tradingview_extraction_refused,
                               capture_region, extract_text, forbidden_reasons,
                               is_tradingview_surface, manifest,
                               quote_from_screenshot)
from market.quotes import MarketDataError  # noqa: E402
from market.tradingview import TradingViewLicenceError  # noqa: E402

UTC = datetime.timezone.utc
NOW = datetime.datetime(2026, 8, 14, 12, 0, 0, tzinfo=UTC)


def why(fn):
    """The refusal message, or a marker if there wasn't one."""
    try:
        fn()
        return "((NO REFUSAL))"
    except BaseException as exc:  # noqa: BLE001
        return "%s: %s" % (type(exc).__name__, exc)


def approval(title="AAPL Chart", **kw):
    kw.setdefault("purpose", "read the last price for a manual note")
    kw.setdefault("granted_by", "user")
    kw.setdefault("granted_at", NOW)
    return CaptureApproval(title, **kw)


# ===========================================================================
section("the capability claim is MEASURED, not assumed")
# ===========================================================================

# These are hardcoded on purpose: a capability probed at import time flickers
# with whatever happens to be installed, producing refusals that cannot be tested
# and an audit record that cannot be reproduced.
check_true("capture is NOT available in this runtime", CAPTURE_AVAILABLE is False,
           "(V) MEASURED 2026-08-13")
check_true("OCR is NOT available in this runtime", OCR_AVAILABLE is False, "(V)")
check_true("the probe records exactly what was looked for",
           len(CAPABILITY_PROBE) >= 12,
           "(V) so the claim can be re-checked rather than believed")
for _absent in ("mss", "pyautogui", "pytesseract", "easyocr", "paddleocr"):
    check_true("%s is recorded ABSENT" % _absent,
               CAPABILITY_PROBE[_absent] == "ABSENT", "(V)")
check_true("tesseract is recorded as NOT ON PATH",
           CAPABILITY_PROBE["tesseract (binary)"] == "NOT ON PATH", "(V)")
check_true("DISPLAY is recorded unset", CAPABILITY_PROBE["DISPLAY"] == "unset",
           "(V) there is no screen to capture")

# PIL and cv2 ARE present, and the probe says why that does not amount to a
# capture backend. A bare "PRESENT" would read as a capability.
check_true("PIL is present but explicitly cannot capture a screen",
           "cannot capture" in CAPABILITY_PROBE["PIL"],
           "(V) processing an existing image is not taking one")
check_true("cv2 is present but explicitly does not read text",
           "does not read text" in CAPABILITY_PROBE["cv2"], "(V)")


# ===========================================================================
section("SS.7.1 Level 3: every declared forbidden target is enforced")
# ===========================================================================

check("SS.7.1 lists 7 prohibited capture targets", len(FORBIDDEN_TARGETS), 7, 0,
      "(V) MEASURED from the spec")

# THE ASSERTION THAT CAUGHT THE ORIGINAL GAP. MEASURED on this module's first
# execution: three of the seven declared targets had no enforcement whatsoever.
# A list nothing checks is decoration, which is the failure mode Phase 3 found in
# sources.py. Every target must be enforced by a title pattern OR be recorded as
# structurally prevented WITH a stated reason.
_covered = set(ss._FORBIDDEN_PATTERNS) | set(STRUCTURALLY_PREVENTED)
_uncovered = [t for t in FORBIDDEN_TARGETS if t not in _covered]
check_true("every declared target is enforced or explicitly explained",
           _uncovered == [],
           "(V) a declared prohibition nothing implements is decoration; "
           "uncovered=%r" % (_uncovered,))
check_true("the structurally-prevented entries each carry a REASON",
           all(len(r) > 80 for r in STRUCTURALLY_PREVENTED.values()),
           "(V) 'not enforceable' without a reason is indistinguishable from "
           "having forgotten it")

for _title, _want in (
        ("Broker Login", "broker login dialogs"),
        ("1Password - Vault", "passwords"),
        ("Bitwarden", "passwords"),
        ("My API Key settings", "api keys"),
        ("Seed phrase backup", "api keys"),
        ("Two-Factor Authentication", "broker login dialogs"),
        ("WhatsApp", "private notifications"),
        ("Gmail - Inbox", "private notifications"),
):
    check_true("%r is refused as %s" % (_title, _want),
               any(_want in r for r in forbidden_reasons(_title)),
               "(D) screened by title")

# MUTATION FINDING 2026-08-15. Deleting the 'notification' pattern SURVIVED.
# MEASURED cause: every notification title above ("WhatsApp", "Gmail - Inbox")
# is caught by a DIFFERENT entry in the same tuple, so the deleted pattern was
# never the one doing the work. A table-driven test proves the TABLE refuses,
# not that each ROW does -- so each pattern that carries a case alone is now
# exercised by a title only it matches.
for _pat, _title, _want in (
        ("notification", "notification centre", "private notifications"),
        ("password", "password", "passwords"),
        ("api key", "api key manager", "api keys"),
        ("login", "login", "broker login dialogs"),
        ("access token", "access token viewer", "api keys"),
        ("otp", "otp entry", "broker login dialogs"),
        ("inbox", "inbox", "private notifications"),
        ("keychain", "keychain access", "passwords"),
):
    _reasons = forbidden_reasons(_title)
    check_true("the %r pattern alone refuses %r" % (_pat, _title),
               any(_want in r for r in _reasons),
               "(D) each row must carry its own case")
    check_true("...and the refusal names %r as the matched pattern" % _pat,
               any(repr(_pat) in r for r in _reasons),
               "(D) proves THIS row matched, not a neighbour standing in for it")

# Persian patterns: the user is a Persian speaker, so an English-only screen
# would be a wall with a door in it.
for _fa, _want in (("رمز عبور", "passwords"), ("گذرواژه", "passwords"),
                   ("ورود", "broker login dialogs"), ("کلید api", "api keys")):
    check_true("the Persian title %r is screened as %s" % (_fa, _want),
               any(_want in r for r in forbidden_reasons(_fa)),
               "(D) an English-only screen is a wall with a door in it")

# ALL reasons, not the first: "Broker Login - password reset" is two problems,
# and reporting one implies fixing it would be enough.
_multi = forbidden_reasons("Broker Login - password reset")
check("a two-problem title reports BOTH reasons", len(_multi), 2, 0,
      "(V) MEASURED: passwords AND broker login dialogs")
check_true("...naming passwords", any("passwords" in r for r in _multi), "(V)")
check_true("...and naming broker login dialogs",
           any("broker login" in r for r in _multi), "(V)")

# THE POSITIVE CONTROL. Without it, a screen that refused everything would pass
# every assertion above.
for _ok in ("AAPL Chart", "EURUSD 1.0850 - 15 minutes", "Portfolio Overview",
            "USDJPY 156.20 - 240 - Chart"):
    check_true("the ordinary window %r is NOT refused" % _ok,
               forbidden_reasons(_ok) == (),
               "(C) the screen discriminates; a screen that refuses everything "
               "trains the user to switch it off")

check_raises("a non-string window title is refused",
             lambda: forbidden_reasons(123), ScreenshotError)


# ===========================================================================
section("the account-identifier pattern, tuned against a MEASURED failure")
# ===========================================================================

# The first pattern was (\d[\d\-\s]{5,}\d), which allowed spaces and hyphens
# INSIDE the run and so joined unrelated digit groups. MEASURED at the time:
# "EURUSD 1.0850 - 15 minutes" matched '0850 - 15'. That direction of error is
# the dangerous one here: a screen that refuses ordinary chart windows trains the
# user to pass includes_account_identifiers=True to get past it, disabling the
# very check the broad pattern was meant to provide. A false positive does not
# fail safe -- it manufactures a reason to switch the guard off.
for _ordinary in ("EURUSD 1.0850 - 15 minutes",
                  "USDJPY 156.20 - 240 - TradingView",
                  "BTCUSD 64,200 - 1H", "AAPL 214.50", "SPX 5,400 - Daily",
                  "GBPUSD 1.2650 - 30", "Chart 15 30 60", "NQ 18500 - 5m"):
    check_true("the ordinary chart title %r is not read as an account" % _ordinary,
               ss._looks_like_account_identifier(_ordinary) is False,
               "(C) MEASURED: 0 false positives on 8 ordinary titles")

for _acct in ("IBKR U1234567", "Acct 1234-5678-9012", "Account 987654321",
              "****5678", "xxxx-5678"):
    check_true("the account-like title %r IS detected" % _acct,
               ss._looks_like_account_identifier(_acct) is True,
               "(D) MEASURED: 5/5 still caught after tightening")

# The one CONDITIONAL item in the spec's list: permitted when explicitly approved.
check_true("an account-like title is refused WITHOUT the explicit flag",
           any("account identifiers" in r
               for r in forbidden_reasons("IBKR U1234567", approval())),
           "(D) 'unless explicitly required and approved'")
check_true("...and permitted WITH it",
           forbidden_reasons("IBKR U1234567",
                             approval("IBKR U1234567",
                                      includes_account_identifiers=True)) == (),
           "(C) the conditional item is genuinely conditional")


# ===========================================================================
section("consent that cannot be inferred, widened, or outlived")
# ===========================================================================

_a = approval()
check_true("a well-formed approval is accepted",
           _a.window_title == "AAPL Chart" and _a.granted_by == "user",
           "(C) the class discriminates")
check_true("the default TTL is 15 minutes",
           _a.ttl_seconds == 900 and CaptureApproval.DEFAULT_TTL_SECONDS == 900,
           "(V) long enough for the task, too short to become ambient")
check_true("expiry is granted_at plus the TTL",
           _a.expires_at == NOW + datetime.timedelta(seconds=900), "(B)")

# There is no approve_all, no wildcard, no remember=True. Each is a mechanism by
# which an explicit approval quietly becomes a default.
check_true("the class offers no approve_all",
           not hasattr(CaptureApproval, "approve_all"),
           "(V) a blanket approval is not an explicit one")
for _wild in ("*", "all", "any", "AAPL*"):
    check_true("the wildcard title %r is refused" % _wild,
               "wildcard" in why(lambda w=_wild: approval(w)),
               "(D) a pattern matching many windows is not a selection")

for _field, _bad, _fragment in (
        ("window_title", "", "must name the window"),
        ("window_title", "   ", "must name the window"),
        ("purpose", "", "must state what the capture is for"),
        ("granted_by", "", "must identify who approved"),
):
    _kw = {"window_title": "W", "purpose": "p", "granted_by": "u",
           "granted_at": NOW}
    _kw[_field] = _bad
    check_true("an approval with a blank %s is refused" % _field,
               _fragment in why(lambda k=_kw: CaptureApproval(**k)),
               "(D) named by its own guard")

# TTL bounds. A zero or negative lifetime would make every capture fail in a way
# that invites disabling the expiry check altogether.
check_true("a zero TTL is refused, and the message says why that matters",
           "invites disabling the expiry check"
           in why(lambda: approval(ttl_seconds=0)), "(D)")
check_true("a negative TTL is refused",
           "must be positive" in why(lambda: approval(ttl_seconds=-1)), "(D)")
check_true("a TTL over the 1-hour maximum is refused",
           "standing permission wearing the word 'explicit'"
           in why(lambda: approval(ttl_seconds=3601)),
           "(D) MEASURED wording")
check_true("exactly the maximum TTL is accepted",
           approval(ttl_seconds=3600).ttl_seconds == 3600,
           "(C) the boundary is where it claims to be")
check_true("a bool TTL is refused (True would be 1 second)",
           "must be an integer" in why(lambda: approval(ttl_seconds=True)),
           "(D) isinstance(True, int) is True in Python")
check_true("a float TTL is refused",
           "must be an integer" in why(lambda: approval(ttl_seconds=900.0)), "(D)")

# The account flag must be EXACTLY True or False: a truthy string would silently
# widen the approval to cover account identifiers.
for _truthy in ("yes", "true", 1, [1]):
    check_true("includes_account_identifiers=%r is refused" % (_truthy,),
               "must be exactly True or False"
               in why(lambda t=_truthy: approval(includes_account_identifiers=t)),
               "(D) Level 3 permits these only when explicitly approved")

check_true("a naive granted_at is refused",
           "must be timezone-aware"
           in why(lambda: approval(granted_at=datetime.datetime(2026, 8, 14, 12))),
           "(D) expiry across a timezone change would fail invisibly")


# ===========================================================================
section("an approval is immutable after it is given")
# ===========================================================================

# Widening a consent after the fact -- extending its ttl, adding account
# identifiers -- is the failure the class exists to prevent.
for _field, _value in (("ttl_seconds", 999999),
                       ("window_title", "*"),
                       ("includes_account_identifiers", True),
                       ("granted_by", "someone else")):
    check_true("setting %s on a granted approval is refused" % _field,
               "an approval is immutable"
               in why(lambda f=_field, v=_value: setattr(_a, f, v)),
               "(D) consent cannot be widened after the fact")
check_true("deleting a field is refused too",
           "refusing to delete" in why(lambda: delattr(_a, "ttl_seconds")),
           "(D) deletion is widening by another route")
check_true("a new attribute cannot be added either",
           "an approval is immutable"
           in why(lambda: setattr(_a, "approve_all", True)), "(D)")
check_true("the approval survived every attempt unchanged",
           _a.ttl_seconds == 900 and _a.window_title == "AAPL Chart"
           and _a.includes_account_identifiers is False,
           "(C) the refusals were real, not cosmetic")


# ===========================================================================
section("assert_covers: exact window, unexpired, no substring widening")
# ===========================================================================

check_true("an approval covers its own window", _a.assert_covers(
    "AAPL Chart", now=NOW) is None, "(C)")
check_true("...case-insensitively on stripped text",
           _a.assert_covers("  aapl chart  ", now=NOW) is None,
           "(C) titles vary in case between window managers")

# THE ASSERTION THAT KEEPS AN APPROVAL FROM SPREADING. A substring match would
# let "AAPL - TradingView" cover "AAPL - TradingView - Broker Login", which is
# precisely the window the spec forbids capturing.
for _adjacent in ("AAPL Chart - Broker Login", "AAPL Chart 2", "AAPL",
                  "AAPL Chart - 1Password"):
    check_true("the adjacent window %r is NOT covered" % _adjacent,
               "approval covers window" in why(
                   lambda w=_adjacent: _a.assert_covers(w, now=NOW)),
               "(D) no prefix match, no substring match")

check_true("an approval is not yet expired one second before its TTL",
           _a.is_expired(NOW + datetime.timedelta(seconds=899)) is False, "(B)")
check_true("...and IS expired exactly at the TTL",
           _a.is_expired(NOW + datetime.timedelta(seconds=900)) is True,
           "(B) the boundary is inclusive")
check_true("an expired approval refuses, and says to ask again",
           "not the consent that was given" in why(
               lambda: _a.assert_covers("AAPL Chart",
                                        now=NOW + datetime.timedelta(seconds=901))),
           "(D) consent decays")
check_true("...and that refusal is NOT the coverage guard standing in for it",
           "approval covers window" not in why(
               lambda: _a.assert_covers("AAPL Chart",
                                        now=NOW + datetime.timedelta(seconds=901))),
           "(D) the two guards must be distinguishable")

# --- PROBE FINDING 2026-08-15: the window was bounded at ONE end only -------
# MEASURED before the fix: an approval stamped a day in the future was honoured
# today, because is_expired() asked only whether the TTL had run out. Consent
# used before it was given is not consent, and a clock skew is enough to produce
# it without anyone forging anything.
_fut = CaptureApproval("AAPL Chart", "chart reading", "user",
                       granted_at=NOW + datetime.timedelta(days=1))
check_true("an approval dated in the future is NOT YET VALID",
           _fut.is_not_yet_valid(NOW) is True, "(D) MEASURED: this once passed")
_w_fut = why(lambda: _fut.assert_covers("AAPL Chart", now=NOW))
check_true("...and assert_covers refuses it, naming the future dating",
           "AFTER the moment it is being used" in _w_fut, "(D)")
check_true("...and NOT via the expiry guard standing in for it",
           "expired at" not in _w_fut,
           "(D) a future approval is not an expired one; the report must differ")
check_true("the lower bound is inclusive at the instant of granting",
           _fut.is_not_yet_valid(NOW + datetime.timedelta(days=1)) is False,
           "(B) valid AT its grant time, not one tick later")
check_true("an ordinary approval is not caught by the new lower bound",
           _a.is_not_yet_valid(NOW) is False,
           "(C) POSITIVE CONTROL: a guard that refuses everything is not a guard")

# MUTATION FINDING 2026-08-15. Removing assert_covers' empty-title guard
# SURVIVED. MEASURED cause: the window-mismatch guard two lines below raises the
# SAME ScreenshotError for "", so a type-only expectation could not tell which
# guard answered. Asserted on the refusal CONTENT instead -- the same weakness,
# and the same fix, as the broker battery's verdict_for({}) survivor.
for _blank in ("", "   ", "\t\n"):
    _w_blank = why(lambda b=_blank: _a.assert_covers(b))
    check_true("assert_covers refuses %r by its own empty-title guard" % _blank,
               "must be a non-empty string" in _w_blank, "(D)")
    check_true("...and NOT by the window-mismatch guard standing in for it",
               "approval covers window" not in _w_blank,
               "(D) both raise ScreenshotError; only the wording distinguishes them")

def _seal_ok():
    """The seal must be narrow: three named limits, not the whole class."""
    try:
        CaptureApproval._probe_marker = 1
        del CaptureApproval._probe_marker
        return True
    except Exception:  # noqa: BLE001
        return False


# --- PROBE FINDING 2026-08-15: the ceiling itself was writable --------------
# MEASURED before the fix: every attempt to widen ONE approval was refused, but
# `CaptureApproval.MAX_TTL_SECONDS = 999999` succeeded and widened every
# approval granted afterwards -- a 138-hour standing consent passed validation.
check_true("the class TTL ceiling cannot be rebound at runtime",
           "consent limits are sealed" in why(
               lambda: setattr(CaptureApproval, "MAX_TTL_SECONDS", 999999)),
           "(D) guarding the instances but not the limit protects only copies")
check_true("the default TTL cannot be rebound either",
           "consent limits are sealed" in why(
               lambda: setattr(CaptureApproval, "DEFAULT_TTL_SECONDS", 1)),
           "(D)")
check_true("the ceiling cannot be DELETED to escape being checked against it",
           "not a way to satisfy it" in why(
               lambda: delattr(CaptureApproval, "MAX_TTL_SECONDS")),
           "(D) removing a limit is not a way to meet it")
check_true("the ceiling still holds its measured value after every attempt",
           CaptureApproval.MAX_TTL_SECONDS == 3600, "(V)")
check_true("...so an over-long approval is still refused afterwards",
           "exceeds the maximum" in why(
               lambda: CaptureApproval("AAPL Chart", "p", "user",
                                       ttl_seconds=500000)),
           "(D) the seal must protect the CHECK, not just the attribute")
check_true("an unrelated class attribute may still be set",
           _seal_ok(),
           "(C) POSITIVE CONTROL: the seal names three fields, not the class")


# ===========================================================================
section("the Level 3 gate runs consent BEFORE content")
# ===========================================================================

# Order is deliberate. If screening ran first, an unapproved capture of an
# innocuous window would pass the screen and the refusal would depend on a later
# check -- and any reordering would go unnoticed. Consent first, then content.
_w_order = why(lambda: assert_capture_permitted("Broker Login", _a, now=NOW))
check_true("an unapproved forbidden window fails on CONSENT first",
           "approval covers window" in _w_order,
           "(D) MEASURED: consent answers before content")
check_true("...and not on the forbidden-target screen",
           "refusing to capture" not in _w_order,
           "(D) the ordering is asserted, not assumed")

# Approved AND forbidden: now the content screen must answer, and it must refuse
# despite the approval. A user may consent without realising a credential is on
# screen, and an audit record is designed to be durable.
_w_content = why(lambda: assert_capture_permitted(
    "Broker Login", approval("Broker Login"), now=NOW))
check_true("an APPROVED forbidden window is still refused",
           "refusing to capture" in _w_content,
           "(D) forbidden targets are refused regardless of approval")

# MUTATION FINDING 2026-08-15. Swapping the two gates so content is screened
# BEFORE consent SURVIVED. MEASURED cause: in the unapproved case the coverage
# guard answers either way, and in the approved-forbidden case the content guard
# answers either way -- so neither existing case can see the order. The order is
# only observable where BOTH would fire and the messages differ, which is an
# approval that does not cover a window that is ALSO forbidden.
_w_both = why(lambda: assert_capture_permitted(
    "Broker Login", approval("AAPL Chart"), now=NOW))
check_true("when BOTH guards would fire, CONSENT is the one that answers",
           "approval covers window" in _w_both,
           "(D) MEASURED: this is the only input that can observe the order")
check_true("...and the content screen has not run yet",
           "refusing to capture" not in _w_both,
           "(D) a reordering is now visible; before this it was not")
check_true("...naming the matched target",
           "broker login dialogs" in _w_content, "(D)")

check_true("capture without any approval object is refused",
           "requires a CaptureApproval" in why(
               lambda: assert_capture_permitted("AAPL Chart", None, now=NOW)),
           "(D) there is no code path that captures without one")
for _fake in ("AAPL Chart", {"window_title": "AAPL Chart"}, 1):
    check_true("a look-alike approval %r is refused" % (type(_fake).__name__,),
               "requires a CaptureApproval" in why(
                   lambda f=_fake: assert_capture_permitted("AAPL Chart", f,
                                                            now=NOW)),
               "(D) duck typing would defeat the whole class")

check_true("a fully valid capture request passes the gate",
           assert_capture_permitted("AAPL Chart", _a, now=NOW) is None,
           "(C) THE POSITIVE CONTROL: the gate is not a blanket refusal")


# ===========================================================================
section("capture and OCR refuse for the RIGHT reason")
# ===========================================================================

# capture_region evaluates the gate FIRST, so a caller who is also doing
# something forbidden learns that too. An availability message would otherwise
# hide a consent defect until a backend is installed -- the worst possible moment
# to discover one.
check_true("capture of an unapproved window reports the CONSENT defect",
           "approval covers window" in why(
               lambda: capture_region("Some Other Window", _a, now=NOW)),
           "(D) not 'capture unavailable', which would hide it")
_w_cap = why(lambda: capture_region("AAPL Chart", _a, now=NOW))
check_true("an approved capture refuses on AVAILABILITY",
           "screen capture is not available" in _w_cap, "(D)")
check_true("...and states the project will not claim an API it lacks",
           "will not claim a Desktop API it does not have" in _w_cap, "(V)")
check_true("...and reports the MEASURED probe rather than asserting it",
           "mss=ABSENT" in _w_cap and "DISPLAY=unset" in _w_cap,
           "(V) the claim is re-checkable")
check_true("...and points at Level 2 CSV as the better route",
           "csv_import" in _w_cap and "strictly better evidence" in _w_cap,
           "(V) a validated CSV is exact, hashable, and its gaps detectable")

_w_ocr = why(lambda: extract_text(window_title="AAPL Chart"))
check_true("OCR refuses, naming every backend that is absent",
           "pytesseract ABSENT" in _w_ocr and "easyocr ABSENT" in _w_ocr, "(D)")
check_true("OCR with no window title still refuses",
           "not available" in why(lambda: extract_text()), "(D)")


# ===========================================================================
section("the TradingView laundering gate: pixels do not launder a licence")
# ===========================================================================

for _tv in ("AAPL - TradingView", "tradingview.com/chart", "TV Chart - BTC",
            "Trading View", "تریدینگ ویو"):
    check_true("%r is recognised as a TradingView surface" % _tv,
               is_tradingview_surface(_tv) is True, "(V)")
for _not_tv in ("AAPL Chart", "Portfolio Overview", "Interactive Brokers"):
    check_true("%r is NOT a TradingView surface" % _not_tv,
               is_tradingview_surface(_not_tv) is False,
               "(C) the marker list discriminates")
check_true("the marker list is non-empty and includes the brand",
           len(TRADINGVIEW_MARKERS) >= 4 and "tradingview" in TRADINGVIEW_MARKERS,
           "(V) the default title of every TradingView window carries it")

# MUTATION FINDING 2026-08-15. Removing .replace("-", " ") SURVIVED. MEASURED
# cause: the function tests the normalised text OR the raw lowercased title, so
# every case above still matched through the second clause. Normalisation is
# only observable on a title where a hyphen sits INSIDE a two-word marker --
# "trading-view", which the raw clause cannot match. That is not a contrived
# input: it is how a window title is commonly punctuated.
for _hyphen in ("AAPL trading-view", "trading-view chart", "TRADING-VIEW"):
    check_true("%r is recognised despite the internal hyphen" % _hyphen,
               is_tradingview_surface(_hyphen) is True,
               "(D) hyphen normalisation is load-bearing, not cosmetic")
check_true("a hyphen does not make everything a TradingView surface",
           is_tradingview_surface("AAPL-Chart-Daily") is False,
           "(C) POSITIVE CONTROL: normalisation must not match by accident")

# THE DEFECT THIS MODULE RECORDS AGAINST ITSELF. The licence wall existed and
# nothing called it; a TradingView window produced a usable Quote. These two
# assertions are the ones that would have caught it.
_w_q = why(lambda: quote_from_screenshot(
    "AAPL", "NASDAQ", "USD", NOW, "UTC", 214.5,
    approval("AAPL - TradingView"), "AAPL - TradingView", now=NOW))
check_true("a Quote CANNOT be built from a TradingView window",
           "TradingView content may not be used" in _w_q,
           "(D) THE LAUNDERING GATE: MEASURED, this once returned a Quote")
check_true("...and the refusal is the LICENCE error, not a generic one",
           _w_q.startswith("TradingViewLicenceError"),
           "(D) the failure mode here is legal, not numerical")
check_raises("...raised as TradingViewLicenceError specifically",
             lambda: quote_from_screenshot(
                 "AAPL", "NASDAQ", "USD", NOW, "UTC", 214.5,
                 approval("AAPL - TradingView"), "AAPL - TradingView", now=NOW),
             TradingViewLicenceError)

# TradingViewLicenceError is a RuntimeError, NOT a MarketDataError. That is
# deliberate: the licence wall must not be swallowed by routine market-data
# handling that exists to fall back to another source. There is no other source.
check_true("TradingViewLicenceError is NOT a MarketDataError",
           not issubclass(TradingViewLicenceError, MarketDataError),
           "(V) `except MarketDataError` must NOT catch the licence wall")
check_true("...it is a RuntimeError, so callers must name it",
           issubclass(TradingViewLicenceError, RuntimeError), "(V)")

check_true("OCR of a TradingView window refuses on LICENCE, not availability",
           "TradingView content may not be used" in why(
               lambda: extract_text(window_title="AAPL - TradingView")),
           "(D) reporting 'OCR unavailable' would send the user to install "
           "tesseract, which is not the obstacle")
check_raises("the licence router raises for any detail",
             lambda: assert_tradingview_extraction_refused("x"),
             TradingViewLicenceError)

# An unapproved TradingView window must report the CONSENT defect too: the
# laundering gate sits after the consent gate on purpose.
check_true("an unapproved TradingView window reports the consent defect first",
           "approval covers window" in why(
               lambda: quote_from_screenshot(
                   "AAPL", "NASDAQ", "USD", NOW, "UTC", 214.5, _a,
                   "AAPL - TradingView", now=NOW)),
           "(D) both defects are real; consent is reported first")


# ===========================================================================
section("the Quote a screenshot produces is labelled for what it is")
# ===========================================================================

_q = quote_from_screenshot("AAPL", "NASDAQ", "USD", NOW, "UTC", 214.5, _a,
                           "AAPL Chart", now=NOW)
check_true("a NON-TradingView window DOES produce a Quote",
           _q is not None and _q.last == 214.5,
           "(C) THE POSITIVE CONTROL: the module is not a blanket refusal")
check_true("the quote is UNVERIFIED", _q.trust_level == "UNVERIFIED", "(V)")
check_true("the quote's origin is VISUALLY_EXTRACTED",
           _q.origin == "VISUALLY_EXTRACTED", "(V) SS.7.1 Level 3")
check_true("...which makes it a WEAK origin", _q.is_weak is True, "(C)")
check_true("the provider names the window it was read from",
           _q.provider == "screenshot:AAPL Chart", "(V) provenance is visible")

# MUTATION FINDING 2026-08-15. Sourcing the provider from the REQUESTED window
# title instead of the APPROVED one SURVIVED. MEASURED cause: every existing
# case passed a requested title identical to the approved one, so the two
# expressions could not be told apart. They CAN differ -- assert_covers matches
# case-insensitively on stripped text -- and the audit record must carry the
# title the user actually consented to, not the caller's spelling of it.
_q_case = quote_from_screenshot(
    "AAPL", "NASDAQ", "USD", NOW, "UTC", 214.5,
    approval("AAPL Chart"), "  aapl chart  ", now=NOW)
check_true("the provider records the APPROVED title, not the caller's spelling",
           _q_case.provider == "screenshot:AAPL Chart",
           "(D) MEASURED: the caller passed '  aapl chart  '")
check_true("...and the note names the approved title too",
           "'AAPL Chart'" in _q_case.note,
           "(D) an audit record quotes what was consented to")

# Never REALTIME/OPEN. A chart on screen may be delayed, paused, or showing a
# replay, and nothing in the pixels distinguishes those from live.
check_true("delay_status is UNKNOWN, never REALTIME",
           _q.delay_status == "UNKNOWN", "(V) pixels cannot prove liveness")
check_true("market_status is UNKNOWN, never OPEN",
           _q.market_status == "UNKNOWN", "(V)")
check_true("the quote is therefore not live", _q.is_live is False, "(C)")
check_true("the licence field admits what cannot be established",
           "cannot establish the underlying content was licensed" in _q.licence,
           "(V)")

# THE CONSEQUENCE, which is the entire point of the label.
check_raises("a screenshot quote may NOT price a live order",
             lambda: _q.assert_usable_for("live_order"), MarketDataError)
check_raises("...nor be sole evidence for a material calculation",
             lambda: _q.assert_usable_for("material_calculation"),
             MarketDataError)
check_true("...but it MAY be displayed to a human",
           _q.assert_usable_for("display") is None,
           "(C) Level 3 output is for a person to read, and that still works")

# extraction_exact changes the NOTE and nothing about usability. Making it change
# usability would create exactly the incentive to pass extraction_exact=True.
_qe = quote_from_screenshot("AAPL", "NASDAQ", "USD", NOW, "UTC", 214.5, _a,
                            "AAPL Chart", extraction_exact=True, now=NOW)
check_true("an APPROXIMATE reading says so in its note",
           "APPROXIMATE reading" in _q.note, "(V)")
check_true("an exact-text reading says that instead",
           "exact-text reading" in _qe.note, "(V)")
check_true("...but an exact reading is STILL unusable for a live order",
           "may not be authoritative" in why(
               lambda: _qe.assert_usable_for("live_order")),
           "(D) otherwise extraction_exact=True becomes the way past the gate")
check_true("...and still weak", _qe.is_weak is True, "(C)")
check_true("...and still UNVERIFIED", _qe.trust_level == "UNVERIFIED", "(V)")

check_true("a quote with no value is refused",
           "not an observation" in why(
               lambda: quote_from_screenshot("AAPL", "NASDAQ", "USD", NOW, "UTC",
                                             None, _a, "AAPL Chart", now=NOW)),
           "(D) an empty reading is not an observation")
for _truthy in ("yes", 1, [1]):
    check_true("extraction_exact=%r is refused as not exactly True/False"
               % (_truthy,),
               "must be exactly True or False" in why(
                   lambda t=_truthy: quote_from_screenshot(
                       "AAPL", "NASDAQ", "USD", NOW, "UTC", 214.5, _a,
                       "AAPL Chart", extraction_exact=t, now=NOW)),
               "(D) a truthy value would upgrade stated reliability by accident")
for _bad_conf in (-0.1, 1.1, "high", True):
    check_true("a confidence of %r is refused" % (_bad_conf,),
               why(lambda c=_bad_conf: quote_from_screenshot(
                   "AAPL", "NASDAQ", "USD", NOW, "UTC", 214.5, _a, "AAPL Chart",
                   confidence=c, now=NOW)).startswith("ScreenshotError"),
               "(D) it would be reported verbatim into an audit record")
check_true("a valid confidence appears in the note",
           "confidence 0.80" in quote_from_screenshot(
               "AAPL", "NASDAQ", "USD", NOW, "UTC", 214.5, _a, "AAPL Chart",
               confidence=0.8, now=NOW).note,
           "(C) the guard discriminates")

# The gate is RE-RUN here: a Quote must not exist for a window that was never
# approved, even if a caller obtained the pixels some other way.
check_true("a Quote cannot be built for an unapproved window",
           "approval covers window" in why(
               lambda: quote_from_screenshot("AAPL", "NASDAQ", "USD", NOW, "UTC",
                                             214.5, _a, "Other Window", now=NOW)),
           "(D) the gate is re-run at the point the label is attached")
check_true("a Quote cannot be built on an EXPIRED approval",
           "expired" in why(
               lambda: quote_from_screenshot(
                   "AAPL", "NASDAQ", "USD", NOW, "UTC", 214.5, _a, "AAPL Chart",
                   now=NOW + datetime.timedelta(seconds=901))),
           "(D)")


# ===========================================================================
section("the manifest reports the truth about this module")
# ===========================================================================

_m = manifest()
check_true("the manifest says capture is unavailable",
           _m["capture_available"] is False, "(V)")
check_true("the manifest says OCR is unavailable",
           _m["ocr_available"] is False, "(V)")
check_true("the manifest names the origin label",
           _m["origin_label"] == "VISUALLY_EXTRACTED", "(V)")
check_true("the manifest says the origin is weak", _m["is_weak_origin"] is True,
           "(V)")
check_true("the manifest says it cannot serve a material calculation",
           _m["usable_for_material_calculation"] is False, "(V)")
check_true("the manifest says it cannot serve a live order",
           _m["usable_for_live_order"] is False, "(V)")
check_true("the manifest says approval is required",
           _m["approval_required"] is True, "(V)")
check_true("the manifest's TTL ceiling matches the class",
           _m["approval_max_ttl_seconds"] == CaptureApproval.MAX_TTL_SECONDS,
           "(C) computed, not written down")
check_true("the manifest lists all seven forbidden targets",
           len(_m["forbidden_targets"]) == len(FORBIDDEN_TARGETS) == 7, "(C)")
check_true("the manifest says TradingView extraction is REFUSED",
           "REFUSED" in _m["tradingview_extraction"], "(V)")
check_true("the manifest recommends Level 2 CSV instead",
           "Level 2" in _m["recommended_alternative"], "(V)")

sys.exit(summary())
