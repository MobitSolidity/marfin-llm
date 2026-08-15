"""
SS.7.1 Level 3 -- visual integration (screenshot-derived market values).

WHAT THIS MODULE IS FOR

Level 3 exists because a user can see a number on their own screen that this
project has no licensed machine-readable route to. The module's job is NOT to
make that number usable. It is to let the number be carried with a label that has
consequences, and to make the consequences unavoidable:

    VISUALLY_EXTRACTED
    approximate unless exact text is reliably extracted
    unsuitable as SOLE evidence for material calculations
    unsuitable as authoritative live-order data

Those four lines are quoted from SS.7.1 Level 3. Three of them are already
enforced by quotes.py: VISUALLY_EXTRACTED is in WEAK_ORIGINS, so
Quote.assert_usable_for refuses live_order and material_calculation for it. This
module's contribution is the two things quotes.py cannot know about: whether the
capture was APPROVED, and whether the region captured was PERMITTED.

WHY CAPTURE IS NOT IMPLEMENTED HERE

MEASURED in this runtime, not assumed: mss ABSENT, pyautogui ABSENT, Xlib
ABSENT, pygetwindow ABSENT, pytesseract ABSENT, the tesseract binary is not on
PATH, easyocr ABSENT, paddleocr ABSENT, and DISPLAY is unset. PIL, cv2 and numpy
are present, but they process images that already exist; none of them can capture
a window and none of them reads text.

So there is no screen capture and no OCR available, and Phase 3A's acceptance
criterion is explicit: "No unsupported Desktop API claimed". A module that
exposed capture_window() and raised NotImplementedError deep inside would still
be a claim -- callers write against signatures, and a tool catalog advertising a
capability the runtime lacks is exactly the "invented capability" the master
prompt forbids. Therefore:

    CAPTURE_AVAILABLE = False
    OCR_AVAILABLE     = False

and capture_region() refuses immediately, naming what is missing and what the
user can do instead (Level 2: export a CSV -- which this project CAN validate).

WHAT IS IMPLEMENTED IS THE PART THAT MATTERS ANYWAY

The gating logic is written and tested even though capture is unavailable,
because it is the part that is dangerous when capture DOES become available, and
because writing it now records the decisions while the reasoning is present. The
alternative -- adding consent and redaction rules at the same moment someone
adds a capture backend, under deadline -- is how a "do not capture passwords"
list becomes a comment.

THE TRADINGVIEW POINT, WHICH IS THE WHOLE REASON LEVEL 3 IS TEMPTING

Level 3 says "capture only a user-selected TradingView window after explicit
approval". A screenshot of a TradingView chart is TradingView content: pixels do
not launder a licence. Their terms license content for "exclusive display-only
use" and "explicitly prohibit any form of non-display usage", including "any
processing of TradingView's content". OCR is processing. So:

  - a human looking at their own screen is display, and needs nothing from us;
  - extracting a number from those pixels so software can use it is non-display
    machine use, and is refused via tradingview.assert_display_only_use().

That second bullet was FALSE when this module was first written, and the falsehood
is worth recording rather than quietly fixing. The wall function existed and the
docstring described it, but no code path called it: MEASURED,
quote_from_screenshot(window_title="AAPL - TradingView") returned a usable Quote.
A guard reachable only by a caller who already knows to invoke it is decoration --
the same defect Phase 3 found in sources.py, reproduced here one file after I
documented it. It is now enforced at the two points where pixels would become
data (extract_text and quote_from_screenshot) via TRADINGVIEW_MARKERS, and a test
asserts the enforcement rather than the intention.

That refusal is unconditional and has no override, matching tradingview.py. The
consequence is worth stating plainly rather than hiding: for TradingView
specifically, Level 3 yields nothing this project may compute with. It is
retained for windows whose content is NOT licence-restricted in that way -- a
user's own spreadsheet, a broker's own position screen the user is entitled to
read -- and those still produce VISUALLY_EXTRACTED, still approximate, still
never live-order data.
"""

from __future__ import annotations

import datetime
import re
from types import MappingProxyType
from typing import Any, Dict, Mapping, Optional, Tuple

from market.quotes import MarketDataError, Quote
from market import tradingview


class ScreenshotError(MarketDataError):
    """
    A visual-integration refusal.

    Subclasses MarketDataError (itself a ValueError) so the project's REFUSALS
    tuple covers it and a refusal is never mistaken for a crash.
    """


# ---------------------------------------------------------------------------
# What this runtime can actually do. MEASURED, then hardcoded deliberately.
# ---------------------------------------------------------------------------
# These are not probed at import time on purpose. A capability that flickers
# depending on what happens to be installed produces a module whose refusals
# cannot be tested and whose audit record cannot be reproduced. If a capture
# backend is ever added, this constant is changed in the same commit that adds
# it, and the change is reviewable.

CAPTURE_AVAILABLE = False
OCR_AVAILABLE = False

#: Exactly what was looked for, so the claim above can be re-checked rather than
#: believed. Probed 2026-08-13 in the project runtime (Python 3.13).
CAPABILITY_PROBE: Mapping[str, str] = MappingProxyType({
    "mss": "ABSENT",
    "pyautogui": "ABSENT",
    "Xlib": "ABSENT",
    "pygetwindow": "ABSENT",
    "pytesseract": "ABSENT",
    "tesseract (binary)": "NOT ON PATH",
    "easyocr": "ABSENT",
    "paddleocr": "ABSENT",
    "DISPLAY": "unset",
    "PIL": "PRESENT (processes existing images; cannot capture a screen)",
    "cv2": "PRESENT (processes existing images; does not read text)",
    "numpy": "PRESENT (arrays; not a capture or OCR backend)",
})


# ---------------------------------------------------------------------------
# SS.7.1 Level 3 prohibited capture targets.
# ---------------------------------------------------------------------------
#: Quoted from the spec, in its order. Kept as data so a test can assert the
#: list is complete rather than trusting that the code below covers it -- the
#: decoration failure mode found in Phase 3 was exactly a list nothing checked.
FORBIDDEN_TARGETS: Tuple[str, ...] = (
    "passwords",
    "api keys",
    "broker login dialogs",
    "unrelated applications",
    "other monitors",
    "private notifications",
    "account identifiers unless explicitly required and approved",
)

#: Substrings that indicate a window is one of the forbidden targets. Matching is
#: on lowercased text and is deliberately BROAD: a false refusal costs the user
#: one re-approval, while a false acceptance can put a password into an audit
#: record that is designed to be durable. The asymmetry decides the tuning.
_FORBIDDEN_PATTERNS: Mapping[str, Tuple[str, ...]] = MappingProxyType({
    "passwords": ("password", "passwd", "passphrase", "1password", "bitwarden",
                  "lastpass", "keepass", "keychain", "credential manager",
                  "رمز عبور", "گذرواژه"),
    "api keys": ("api key", "api_key", "apikey", "secret key", "access token",
                 "bearer ", "private key", "seed phrase", "mnemonic",
                 "کلید api"),
    "broker login dialogs": ("login", "log in", "sign in", "signin", "logon",
                             "authenticator", "two-factor", "2fa", "otp",
                             "one-time code", "ورود"),
    "private notifications": ("notification", "message from", "whatsapp",
                              "telegram", "signal -", "imessage", "slack",
                              "gmail", "outlook", "inbox"),
})

#: Declared targets with NO title pattern, and WHY -- because the first version of
#: this module simply had no entry for them, which is indistinguishable from
#: having forgotten them. MEASURED on first execution: three of the seven
#: declared targets had no enforcement at all. Two of those are genuinely not
#: enforceable by title and are instead prevented STRUCTURALLY; saying so here is
#: what stops the gap being rediscovered as a defect later, and a test asserts
#: that every declared target appears either here or in _FORBIDDEN_PATTERNS.
STRUCTURALLY_PREVENTED: Mapping[str, str] = MappingProxyType({
    "unrelated applications":
        "prevented by construction, not by title matching: capture is scoped to "
        "the ONE window named in the approval, and assert_covers compares that "
        "title exactly. There is no whole-screen or multi-window code path to "
        "restrict. A title pattern here would imply the opposite -- that other "
        "applications are reachable and merely filtered.",
    "other monitors":
        "same reason: a per-window capture has no monitor argument. Any future "
        "backend that captures by screen coordinates instead of window identity "
        "would defeat this, so that change must re-derive this entry rather than "
        "inherit it.",
    "account identifiers unless explicitly required and approved":
        "enforced separately by _ACCOUNT_LIKE plus the approval's "
        "includes_account_identifiers flag, because it is the one conditional "
        "item in the list -- permitted when explicitly approved -- so a flat "
        "title pattern could not express it.",
})


# ---------------------------------------------------------------------------
# Consent -- an approval that cannot be inferred.
# ---------------------------------------------------------------------------

class _SealedLimits(type):
    """
    Refuse rebinding of the consent limits on the CLASS itself.

    PROBE FINDING 2026-08-15, MEASURED: every attempt to widen ONE approval was
    refused by __slots__ and __setattr__, but
    `CaptureApproval.MAX_TTL_SECONDS = 999999` succeeded and silently raised the
    ceiling for EVERY approval created afterwards -- a 138-hour standing consent
    passed validation. Guarding the instances while leaving the limit they are
    checked against writable protects the copies and not the original.
    """

    _SEALED = frozenset(("DEFAULT_TTL_SECONDS", "MAX_TTL_SECONDS", "_FIELDS"))

    def __setattr__(cls, name, value):
        if name in _SealedLimits._SEALED:
            raise ScreenshotError(
                "refusing to rebind %s.%s: the consent limits are sealed. "
                "Raising the ceiling at runtime would widen every approval "
                "granted afterwards at once, which is a policy change wearing "
                "the clothes of an assignment." % (cls.__name__, name))
        type.__setattr__(cls, name, value)

    def __delattr__(cls, name):
        if name in _SealedLimits._SEALED:
            raise ScreenshotError(
                "refusing to delete %s.%s: removing a limit is not a way to "
                "satisfy it." % (cls.__name__, name))
        type.__delattr__(cls, name)


class CaptureApproval(object, metaclass=_SealedLimits):
    """
    One explicit, narrow, expiring approval to capture one window.

    Every field exists because its absence is a way for consent to become
    fictional:

      window_title  -- approval is for A window, not for "the screen". "Capture
                       only a user-selected window" cannot be satisfied by an
                       approval that does not name one.
      purpose       -- an approval with no stated purpose authorises everything
                       later, which is not consent but a blank cheque.
      granted_at /  -- consent decays. A standing approval granted once during
      ttl_seconds      setup is indistinguishable from no approval at all by the
                       time it is used, so it expires and must be re-asked.
      granted_by    -- an approval nobody granted is the failure this class is
                       built to prevent. It must be a non-empty human identifier.

    There is no `approve_all`, no wildcard title, and no `remember=True`. Each is
    the mechanism by which an explicit approval quietly becomes a default.
    """

    _FIELDS = ("window_title", "purpose", "granted_by", "granted_at",
               "ttl_seconds", "includes_account_identifiers", "note")
    __slots__ = _FIELDS + ("_frozen",)

    #: 15 minutes. Long enough to complete the task the user approved, short
    #: enough that it cannot survive to a later session as an ambient permission.
    DEFAULT_TTL_SECONDS = 900
    MAX_TTL_SECONDS = 3600

    def __init__(self, window_title, purpose, granted_by, granted_at=None,
                 ttl_seconds=DEFAULT_TTL_SECONDS,
                 includes_account_identifiers=False, note=""):
        object.__setattr__(self, "_frozen", False)

        if not isinstance(window_title, str) or not window_title.strip():
            raise ScreenshotError(
                "window_title must name the window the user selected. An "
                "approval that does not identify a window is an approval to "
                "capture anything, which SS.7.1 Level 3 forbids.")
        if "*" in window_title or window_title.strip() in ("all", "any"):
            # Refuse the wildcard explicitly rather than letting it match every
            # window through the ordinary comparison path.
            raise ScreenshotError(
                "window_title %r is a wildcard. Level 3 permits capturing a "
                "user-SELECTED window; a pattern matching many windows is not a "
                "selection." % (window_title,))
        if not isinstance(purpose, str) or not purpose.strip():
            raise ScreenshotError(
                "purpose must state what the capture is for. An unexplained "
                "approval cannot be reviewed later by the person who gave it.")
        if not isinstance(granted_by, str) or not granted_by.strip():
            raise ScreenshotError(
                "granted_by must identify who approved this capture. An "
                "approval with no grantor is not consent.")
        if not isinstance(ttl_seconds, int) or isinstance(ttl_seconds, bool):
            raise ScreenshotError("ttl_seconds must be an integer number of "
                                  "seconds")
        if ttl_seconds <= 0:
            raise ScreenshotError(
                "ttl_seconds must be positive; got %r. A zero or negative "
                "lifetime would make every capture fail in a way that invites "
                "disabling the expiry check altogether." % (ttl_seconds,))
        if ttl_seconds > self.MAX_TTL_SECONDS:
            raise ScreenshotError(
                "ttl_seconds %d exceeds the maximum %d. A long-lived approval "
                "is a standing permission wearing the word 'explicit'."
                % (ttl_seconds, self.MAX_TTL_SECONDS))
        if includes_account_identifiers is not True and \
                includes_account_identifiers is not False:
            # A truthy string here would silently widen the approval.
            raise ScreenshotError(
                "includes_account_identifiers must be exactly True or False, "
                "got %r. Level 3 permits account identifiers only when "
                "'explicitly required and approved', so this cannot be inferred "
                "from a truthy value." % (includes_account_identifiers,))

        granted_at = granted_at or datetime.datetime.now(datetime.timezone.utc)
        if granted_at.tzinfo is None:
            raise ScreenshotError(
                "granted_at must be timezone-aware: a naive approval timestamp "
                "cannot be checked for expiry across a timezone change, and the "
                "failure is invisible.")

        self.window_title = window_title.strip()
        self.purpose = purpose.strip()
        self.granted_by = granted_by.strip()
        self.granted_at = granted_at
        self.ttl_seconds = ttl_seconds
        self.includes_account_identifiers = includes_account_identifiers
        self.note = note
        object.__setattr__(self, "_frozen", True)

    def __setattr__(self, name, value):
        if getattr(self, "_frozen", False):
            raise ScreenshotError(
                "an approval is immutable: refusing to set %r. Widening a "
                "consent after it was given -- extending its ttl, adding "
                "account identifiers -- is the failure this class exists to "
                "prevent." % (name,))
        object.__setattr__(self, name, value)

    def __delattr__(self, name):
        raise ScreenshotError("an approval is immutable: refusing to delete %r"
                              % (name,))

    def __repr__(self):
        return ("CaptureApproval(%r by %s, %ds, account_ids=%s)"
                % (self.window_title, self.granted_by, self.ttl_seconds,
                   self.includes_account_identifiers))

    @property
    def expires_at(self) -> datetime.datetime:
        return self.granted_at + datetime.timedelta(seconds=self.ttl_seconds)

    def is_expired(self, now=None) -> bool:
        now = now or datetime.datetime.now(datetime.timezone.utc)
        return now >= self.expires_at

    def is_not_yet_valid(self, now=None) -> bool:
        """
        True if this approval is dated AFTER the moment it is being used.

        PROBE FINDING 2026-08-15, MEASURED: is_expired() checked only the upper
        bound, so an approval stamped tomorrow was honoured today -- consent
        used before it was given. The window is bounded at BOTH ends because a
        one-sided bound is not a window.
        """
        now = now or datetime.datetime.now(datetime.timezone.utc)
        return now < self.granted_at

    def assert_covers(self, window_title: str, now=None) -> None:
        """
        Refuse unless this approval covers exactly this window and is unexpired.

        Comparison is case-insensitive on stripped text but otherwise EXACT: no
        prefix match, no substring match. A substring match would let an
        approval for "AAPL - TradingView" cover "AAPL - TradingView - Broker
        Login", which is precisely the window the spec forbids capturing.
        """
        if not isinstance(window_title, str) or not window_title.strip():
            raise ScreenshotError("window_title must be a non-empty string")
        if window_title.strip().lower() != self.window_title.lower():
            raise ScreenshotError(
                "approval covers window %r, not %r. Capture is refused rather "
                "than widened: the user selected one window, and an adjacent "
                "one may be a login dialog or an unrelated application."
                % (self.window_title, window_title.strip()))
        if self.is_not_yet_valid(now):
            raise ScreenshotError(
                "approval for %r is dated %s, which is AFTER the moment it is "
                "being used (%s). Refusing rather than treating a future "
                "consent as a present one: a clock skew or a forged timestamp "
                "must not become a capture."
                % (self.window_title, self.granted_at.isoformat(),
                   (now or datetime.datetime.now(datetime.timezone.utc)).isoformat()))
        if self.is_expired(now):
            raise ScreenshotError(
                "approval for %r expired at %s (granted %s, ttl %ds). Ask "
                "again: a consent that outlives the task it was given for is "
                "not the consent that was given."
                % (self.window_title, self.expires_at.isoformat(),
                   self.granted_at.isoformat(), self.ttl_seconds))

    def to_dict(self) -> Dict[str, Any]:
        d = {k: getattr(self, k) for k in self._FIELDS}
        d["expires_at"] = self.expires_at
        return d


# ---------------------------------------------------------------------------
# Redaction / target screening.
# ---------------------------------------------------------------------------

def forbidden_reasons(window_title: str,
                      approval: Optional[CaptureApproval] = None) -> Tuple[str, ...]:
    """
    Every reason this window must not be captured. Empty tuple means none found.

    Returns ALL matches rather than the first, because a window titled
    "Broker Login - password reset" is two problems and reporting one implies
    fixing it would be enough.

    This is screening by window TITLE, which is a weak signal and is documented
    as such rather than presented as a guarantee: a password manager whose title
    is "Untitled" defeats it entirely. It is a floor, not a filter, and the
    strong control is that the user selects the window and approves it by name.
    """
    if not isinstance(window_title, str):
        raise ScreenshotError("window_title must be a string")
    text = window_title.lower()
    found = []
    for target, patterns in _FORBIDDEN_PATTERNS.items():
        for pat in patterns:
            if pat in text:
                found.append("%s (matched %r)" % (target, pat))
                break
    if _looks_like_account_identifier(window_title) and not (
            approval is not None and approval.includes_account_identifiers):
        found.append("account identifiers unless explicitly required and "
                     "approved (window title contains an account-number-like "
                     "string)")
    return tuple(found)


#: Window titles carrying these are TradingView surfaces. A screenshot of one is
#: TradingView content, and extracting a value from it is "any processing of
#: TradingView's content" -- prohibited non-display use.
#
# This list exists because of the worst defect found in this module's first
# execution. Its own module docstring stated that extracting values from a
# TradingView window "is refused via tradingview.assert_display_only_use()", and
# assert_tradingview_extraction_refused() existed to do it -- but NOTHING CALLED
# IT. MEASURED: quote_from_screenshot(..., window_title="AAPL - TradingView")
# returned Quote(screenshot:AAPL - TradingView/AAPL USD last=214.5). A licence
# wall reachable only by a caller who already knows to invoke it protects nothing;
# it is precisely the decoration failure Phase 3 found in sources.py, reproduced by
# me one file after documenting it.
#
# Matching by title is a floor, not a proof, exactly as with the forbidden targets:
# a user who renames the window defeats it. It is still worth having, because the
# default title of every TradingView window contains the brand, and the failure
# being prevented is not adversarial -- it is a well-intentioned user handing over
# a chart screenshot.
TRADINGVIEW_MARKERS: Tuple[str, ...] = (
    "tradingview", "trading view", "tradingview.com", "tv chart",
    "تریدینگ ویو",
)


def is_tradingview_surface(window_title: str) -> bool:
    if not isinstance(window_title, str):
        raise ScreenshotError("window_title must be a string")
    text = window_title.lower().replace("-", " ")
    return any(m in text or m in window_title.lower()
               for m in TRADINGVIEW_MARKERS)


#: 6+ consecutive digits, a grouped account number, or a masked form (****1234,
#: xxxx-5678).
#
# The first version was `(\d[\d\-\s]{5,}\d)`, which allowed spaces and hyphens
# INSIDE the run and therefore joined unrelated digit groups across a title.
# MEASURED: "EURUSD 1.0850 - 15 minutes" matched '0850 - 15' and
# "USDJPY 156.20 - 240 - TradingView" matched '20 - 240' -- so two perfectly
# ordinary chart titles were reported as containing an account number.
#
# That direction of error matters more than it looks. This module is the one that
# says a refusal is cheaper than a leak, and that argument only holds while the
# refusals are about real risks: a screen that refuses ordinary chart windows
# trains the user to grant includes_account_identifiers=True to get past it, which
# disables the very check the broad pattern was protecting. A false positive here
# does not fail safe -- it manufactures a reason to switch the guard off.
#
# MEASURED after tightening: 0 matches on 8 ordinary chart titles, 5/5 still
# caught on account-like titles (including 'IBKR U1234567', 'Acct 1234-5678-9012').
_ACCOUNT_LIKE = re.compile(
    r"(\d{6,})"                              # 1234567
    r"|(\d{3,}[\-\s]\d{3,}[\-\s]\d{2,})"     # 1234-5678-9012
    r"|([*x\u2022]{3,}[\s\-]?\d{2,})",       # ****5678 / xxxx-5678
    re.IGNORECASE)


def _looks_like_account_identifier(text: str) -> bool:
    return bool(_ACCOUNT_LIKE.search(text or ""))


def assert_capture_permitted(window_title: str,
                             approval: CaptureApproval,
                             now=None) -> None:
    """
    The full Level 3 gate, in the order that fails safest.

    Order is deliberate and is asserted by the tests: the approval must exist and
    cover this window BEFORE the title is screened. If screening ran first, an
    unapproved capture of an innocuous window would pass the screen and the
    refusal would then depend on a later check -- and any reordering would go
    unnoticed. Consent first, then content.
    """
    if not isinstance(approval, CaptureApproval):
        raise ScreenshotError(
            "capture requires a CaptureApproval, got %s. Level 3 permits "
            "capture only 'after explicit approval', so there is no code path "
            "that captures without one." % (type(approval).__name__,))
    approval.assert_covers(window_title, now=now)
    reasons = forbidden_reasons(window_title, approval)
    if reasons:
        raise ScreenshotError(
            "refusing to capture %r: %s. SS.7.1 Level 3 forbids capturing these "
            "regardless of approval -- a user may consent to a capture without "
            "realising a credential is on screen, and an audit record is "
            "designed to be durable."
            % (window_title, "; ".join(reasons)))


def capture_region(window_title: str, approval: CaptureApproval,
                   now=None) -> None:
    """
    Always raises. There is no capture backend in this runtime.

    The gate is still evaluated first, so a caller who is ALSO doing something
    forbidden learns that too -- an unavailability message would otherwise hide a
    consent defect until the day a backend is installed, which is the worst
    moment to discover it.

    Capturing a TradingView window for a human to look at is display use and is
    permitted by the terms; it is EXTRACTION that is prohibited. So this function
    does not refuse on licence grounds -- it refuses because no backend exists --
    and the licence wall sits at extract_text() and quote_from_screenshot(), which
    are the points where pixels would become data. Putting it here instead would
    be both wrong about the terms and useless, since a user can already screenshot
    their own screen without this project's help.
    """
    assert_capture_permitted(window_title, approval, now=now)
    raise ScreenshotError(
        "screen capture is not available in this runtime, and this project will "
        "not claim a Desktop API it does not have.\n"
        "  MEASURED: %s\n"
        "  Use SS.7.1 Level 2 instead: export the data as CSV and pass it to "
        "market.csv_import.parse_csv, which validates fourteen properties of "
        "the file. A validated CSV is strictly better evidence than a "
        "screenshot -- it is exact, it is hashable, and its gaps are "
        "detectable."
        % ("; ".join("%s=%s" % (k, v) for k, v in CAPABILITY_PROBE.items()
                     if v in ("ABSENT", "NOT ON PATH", "unset")),))


def extract_text(image: Any = None, window_title: str = "", **kwargs) -> None:
    """
    Always raises. No OCR backend exists here, and for TradingView it would be
    prohibited even if one did.

    The licence check runs FIRST when a window title is supplied, so the refusal
    the user sees is the one that would still apply after a backend is installed.
    Reporting only "OCR unavailable" would imply that installing tesseract is the
    fix, sending the user to solve a problem that is not the obstacle.
    """
    if window_title and is_tradingview_surface(window_title):
        assert_tradingview_extraction_refused(
            "OCR of window %r" % (window_title,))
    raise ScreenshotError(
        "text extraction (OCR) is not available in this runtime: pytesseract "
        "ABSENT, tesseract not on PATH, easyocr ABSENT, paddleocr ABSENT. "
        "Separately, extracting numbers from a TradingView window is non-display "
        "machine use of TradingView content and is refused by "
        "market.tradingview.assert_display_only_use regardless of what is "
        "installed.")


def assert_tradingview_extraction_refused(detail: str = "") -> None:
    """
    Route a TradingView pixel-extraction attempt to the licence wall.

    Delegates rather than re-implementing the message, so there is exactly one
    place where the TradingView terms are stated and one place to update when
    they are re-verified.

    RAISES TradingViewLicenceError, WHICH IS A RuntimeError -- NOT a ValueError,
    and therefore NOT a MarketDataError and NOT covered by this project's REFUSALS
    tuple. MEASURED, because the delegation makes it easy to assume otherwise:
    TradingViewLicenceError.__mro__ is (TradingViewLicenceError, RuntimeError,
    Exception, BaseException), so a caller writing `except MarketDataError` around
    market-data code will NOT catch this and the harness's check_raises would
    class it as a CRASH unless told the type explicitly.

    That is deliberate and is left as-is rather than re-wrapped in ScreenshotError:
    the licence wall is the one refusal in this project whose failure mode is legal
    rather than numerical, and it should not be swallowed by the routine
    market-data error handling that exists to fall back to another source. There
    is no other source; there is no fallback. Callers must name it.
    """
    tradingview.assert_display_only_use(
        "extracting values from a TradingView window by screenshot/OCR",
        detail or "pixels do not launder a licence: a screenshot of a chart is "
                  "still TradingView content, and reading numbers out of it is "
                  "'any processing of TradingView's content'")


# ---------------------------------------------------------------------------
# The value a screenshot may produce, if capture and OCR ever exist.
# ---------------------------------------------------------------------------

def quote_from_screenshot(symbol, exchange, currency, timestamp, timezone,
                          last, approval, window_title,
                          extraction_exact=False, note="",
                          confidence=None, now=None) -> Quote:
    """
    Build a Quote labelled VISUALLY_EXTRACTED, with its Level 3 consequences.

    Written and tested although capture is unavailable, because this is where the
    label is attached and a mislabel here would be undetectable downstream. The
    gate is re-run: a Quote must not exist for a window that was never approved,
    even if a caller obtained the pixels some other way.

    delay_status is UNKNOWN and market_status is UNKNOWN, never REALTIME/OPEN.
    A chart on screen may be delayed, paused, or showing a replay, and nothing in
    the pixels distinguishes those from live. Combined with origin
    VISUALLY_EXTRACTED (a WEAK_ORIGIN), this makes live_order and
    material_calculation refuse -- which is the point.

    `extraction_exact` exists because SS.7.1 Level 3 says values are
    "approximate unless exact text is reliably extracted". It changes the note
    and nothing about usability: even an exactly-read number is still a number
    whose provenance is a screen, and Level 3 bars it from being sole evidence
    either way. Making it change usability would create precisely the incentive
    to pass extraction_exact=True.
    """
    assert_capture_permitted(window_title, approval, now=now)
    # THE LAUNDERING GATE. Without this line the module's licence wall was
    # unreachable and its docstring was false: MEASURED, a TradingView window
    # produced a usable Quote object. Placed after the consent gate so that an
    # unapproved capture of a TradingView window still reports the consent defect
    # too, and before every other validation so that no amount of well-formed
    # arguments can get a TradingView value into a Quote.
    if is_tradingview_surface(window_title):
        assert_tradingview_extraction_refused(
            "building a Quote from window %r" % (window_title,))
    if last is None:
        raise ScreenshotError(
            "a screenshot quote must carry a value; got last=None. An empty "
            "reading is not an observation.")
    if extraction_exact is not True and extraction_exact is not False:
        raise ScreenshotError(
            "extraction_exact must be exactly True or False, got %r. A truthy "
            "value would upgrade a reading's stated reliability by accident."
            % (extraction_exact,))
    if confidence is not None:
        if not isinstance(confidence, (int, float)) or \
                isinstance(confidence, bool):
            raise ScreenshotError("confidence must be a number or None")
        if not (0.0 <= float(confidence) <= 1.0):
            raise ScreenshotError(
                "confidence must be within 0..1, got %r. A number outside the "
                "range would be reported verbatim into an audit record."
                % (confidence,))
    return Quote(
        provider="screenshot:%s" % (approval.window_title,),
        symbol=symbol, instrument_id=None, exchange=exchange,
        asset_class=None, currency=currency,
        timestamp=timestamp, timezone=timezone,
        # Never REALTIME/OPEN: see the docstring. is_live must be False.
        delay_status="UNKNOWN", market_status="UNKNOWN",
        adjustment_status="UNKNOWN", corporate_action_status="UNKNOWN",
        trust_level="UNVERIFIED", origin="VISUALLY_EXTRACTED", last=last,
        licence="read from the user's own screen; this module cannot establish "
                "the underlying content was licensed for machine use, and for "
                "TradingView content it is not",
        note=("%s reading of %r%s%s"
              % ("exact-text" if extraction_exact else "APPROXIMATE",
                 approval.window_title,
                 "" if confidence is None else " (confidence %.2f)" % confidence,
                 ("; " + note) if note else "")))


def manifest() -> Dict[str, Any]:
    return {"level": "SS.7.1 Level 3 (visual integration)",
            "capture_available": CAPTURE_AVAILABLE,
            "ocr_available": OCR_AVAILABLE,
            "capability_probe": dict(CAPABILITY_PROBE),
            "origin_label": "VISUALLY_EXTRACTED",
            "is_weak_origin": True,
            "usable_for_material_calculation": False,
            "usable_for_live_order": False,
            "forbidden_targets": list(FORBIDDEN_TARGETS),
            "structurally_prevented": dict(STRUCTURALLY_PREVENTED),
            "tradingview_markers": list(TRADINGVIEW_MARKERS),
            "approval_required": True,
            "approval_max_ttl_seconds": CaptureApproval.MAX_TTL_SECONDS,
            "tradingview_extraction": "REFUSED (non-display machine use)",
            "recommended_alternative": "SS.7.1 Level 2 (validated CSV export)"}
