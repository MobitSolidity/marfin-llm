"""
Adversarial probe against SS.7.1 Level 3 visual integration.

WHAT IT TRIES TO GET AWAY WITH
The unit suite asks whether each guard refuses when called directly. This asks a
harder question: can a determined caller reach a forbidden outcome by ANY route
the module leaves open? The two outcomes that matter are

  1. capturing something Level 3 forbids -- a password manager, a login dialog,
     a window nobody approved, or one whose approval has expired; and
  2. laundering TradingView content into a machine-usable value.

The second is not hypothetical. MEASURED in this module's first execution: its
docstring claimed TradingView extraction was refused, the refusal function
existed, and NOTHING CALLED IT -- a TradingView window returned a usable Quote.
A wall reachable only by a caller who already knows to invoke it protects
nothing. Several attempts below exist specifically to re-test that route from
angles the unit suite does not walk.

WHY A REFUSAL IS THE PASS, AND A CRASH IS NOT
An AttributeError or KeyError means a guard was reached by accident rather than
by design: the input got further than intended and fell over on the way. That is
counted as a finding, not a pass. The exception is attempt_immutable(), where an
AttributeError from a mappingproxy or a __slots__ object IS the designed refusal
-- immutability enforced by type rather than by a written guard. Widening
attempt()'s accepted set to cover that would have blinded it everywhere else, so
a second narrower helper is used instead.

Structural checks are counted separately: they are properties of the source that
no call can demonstrate, such as the absence of an approve_all shortcut.

Stdlib only. No network, no display, no capture.
"""

import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import market.screenshot as ss  # noqa: E402
from market.screenshot import (CaptureApproval, ScreenshotError,  # noqa: E402
                               assert_capture_permitted, capture_region,
                               extract_text, forbidden_reasons,
                               quote_from_screenshot)
from market.quotes import MarketDataError  # noqa: E402
from market.tradingview import TradingViewLicenceError  # noqa: E402

UTC = datetime.timezone.utc
NOW = datetime.datetime(2026, 8, 14, 12, 0, 0, tzinfo=UTC)

# TradingViewLicenceError is a RuntimeError, NOT a MarketDataError -- named
# explicitly here because the generic ValueError family would not catch it and
# the probe would misreport the licence wall as a crash.
REFUSALS = (ScreenshotError, MarketDataError, TradingViewLicenceError,
            ValueError, TypeError, NotImplementedError)
CRASHES = (AttributeError, IndexError, KeyError, NameError, UnboundLocalError,
           RecursionError, ZeroDivisionError)

STATE = {"refused": 0, "allowed": 0, "crashed": 0}
STRUCT = {"ok": 0, "broken": 0}
FINDINGS = []


def attempt(label, fn, note=""):
    """Try to get away with something. Refusal is the pass."""
    try:
        result = fn()
    except CRASHES as exc:
        STATE["crashed"] += 1
        FINDINGS.append("CRASHED: %s (%s: %s)" % (label, type(exc).__name__, exc))
        print("  CRASHED  %-62s %s: %s" % (label, type(exc).__name__, exc))
        return
    except REFUSALS as exc:
        STATE["refused"] += 1
        print("  refused  %-62s %s" % (label, note or type(exc).__name__))
        return
    except Exception as exc:  # noqa: BLE001
        STATE["crashed"] += 1
        FINDINGS.append("UNEXPECTED: %s (%s: %s)" % (label, type(exc).__name__, exc))
        print("  CRASHED  %-62s unexpected %s" % (label, type(exc).__name__))
        return
    STATE["allowed"] += 1
    FINDINGS.append("ALLOWED: %s -> %r" % (label, result))
    print("  ALLOWED  %-62s *** FINDING ***" % label)


def attempt_immutable(label, fn):
    """
    An attempt to MUTATE an approval or one of the module's tables.

    For these, AttributeError and TypeError ARE the designed refusal: the tables
    are MappingProxyType and tuples, and CaptureApproval uses __slots__, so
    immutability is enforced by the type. attempt() must keep treating
    AttributeError as a crash -- that is how it detects a guard reached by
    accident -- so a separate helper is the honest fix.
    """
    try:
        fn()
    except (AttributeError, TypeError) + REFUSALS as exc:
        STATE["refused"] += 1
        print("  refused  %-62s immutable (%s)" % (label, type(exc).__name__))
        return
    except CRASHES as exc:
        STATE["crashed"] += 1
        FINDINGS.append("CRASHED: %s (%s)" % (label, exc))
        print("  CRASHED  %-62s %s" % (label, type(exc).__name__))
        return
    STATE["allowed"] += 1
    FINDINGS.append("ALLOWED: %s -- consent or a module table was MUTATED" % label)
    print("  ALLOWED  %-62s *** FINDING: mutated ***" % label)


def struct(label, cond, note=""):
    """An invariant that must hold. Counted separately from the attempts."""
    if cond:
        STRUCT["ok"] += 1
        print("  ok       %-62s %s" % (label, note))
    else:
        STRUCT["broken"] += 1
        FINDINGS.append("STRUCTURAL: %s" % label)
        print("  BROKEN   %-62s *** FINDING ***" % label)
    return cond


def approval(title="AAPL Chart", **kw):
    kw.setdefault("purpose", "read a price")
    kw.setdefault("granted_by", "user")
    kw.setdefault("granted_at", NOW)
    return CaptureApproval(title, **kw)


OK = approval()

print("=" * 78)
print("  ADVERSARIAL PROBE: SS.7.1 Level 3 visual integration")
print("=" * 78)

# ---------------------------------------------------------------------------
print("\n-- forging consent ---------------------------------------------------")
# ---------------------------------------------------------------------------
# Every one of these is an attempt to obtain a capture without a real, current,
# specific approval. If any succeeds, "explicit approval" is a formality.

attempt("capture with approval=None",
        lambda: assert_capture_permitted("AAPL Chart", None, now=NOW))
attempt("capture with the approval omitted entirely",
        lambda: assert_capture_permitted("AAPL Chart"))
attempt("capture with a STRING that looks like an approval",
        lambda: assert_capture_permitted("AAPL Chart", "approved", now=NOW))
attempt("capture with a dict duck-typed as an approval",
        lambda: assert_capture_permitted(
            "AAPL Chart", {"window_title": "AAPL Chart"}, now=NOW))


class _FakeApproval(object):
    """A duck type with every attribute the module reads, and no validation."""
    window_title = "AAPL Chart"
    purpose = "p"
    granted_by = "u"
    granted_at = NOW
    ttl_seconds = 999999
    includes_account_identifiers = True

    def assert_covers(self, window_title, now=None):
        return None

    def is_expired(self, now=None):
        return False


attempt("capture with a full duck-typed fake that self-approves",
        lambda: assert_capture_permitted("AAPL Chart", _FakeApproval(), now=NOW),
        "isinstance check, not duck typing")
attempt("build a Quote using the duck-typed fake",
        lambda: quote_from_screenshot("AAPL", "NASDAQ", "USD", NOW, "UTC", 1.0,
                                      _FakeApproval(), "AAPL Chart", now=NOW))

attempt("an approval granted by nobody", lambda: approval(granted_by=""))
attempt("an approval granted by whitespace", lambda: approval(granted_by="   "))
attempt("an approval with no stated purpose", lambda: approval(purpose=""))
attempt("a wildcard approval covering every window", lambda: approval("*"))
attempt("an approval for 'all'", lambda: approval("all"))
attempt("an approval for 'any'", lambda: approval("any"))
attempt("a glob-style approval", lambda: approval("AAPL*"))
attempt("an approval for an empty window title", lambda: approval(""))
attempt("an approval for a whitespace title", lambda: approval("   "))
attempt("an approval that never expires (ttl=0 read as unlimited)",
        lambda: approval(ttl_seconds=0))
attempt("an approval with a negative ttl", lambda: approval(ttl_seconds=-1))
attempt("a 24-hour standing approval", lambda: approval(ttl_seconds=86400))
attempt("a ttl one second over the maximum", lambda: approval(ttl_seconds=3601))
attempt("ttl=True, which Python would read as 1 second",
        lambda: approval(ttl_seconds=True))
attempt("a naive granted_at, so expiry cannot be checked",
        lambda: approval(granted_at=datetime.datetime(2026, 8, 14, 12)))
# PROBE FINDING 2026-08-15: this was ALLOWED on the first run. is_expired()
# bounded the window at the top only, so an approval stamped tomorrow was
# honoured today. Source fixed (is_not_yet_valid); the attempt stays as the
# regression that would notice the bound being removed again.
attempt("a FUTURE-dated approval used before it was granted",
        lambda: approval(granted_at=NOW + datetime.timedelta(days=1)).assert_covers(
            "AAPL Chart", now=NOW))
attempt("account identifiers approved by a truthy string",
        lambda: approval(includes_account_identifiers="yes"))
attempt("account identifiers approved by 1",
        lambda: approval(includes_account_identifiers=1))

# ---------------------------------------------------------------------------
print("\n-- widening a consent after it was given -----------------------------")
# ---------------------------------------------------------------------------
attempt_immutable("extend a granted approval's ttl",
                  lambda: setattr(OK, "ttl_seconds", 999999))
attempt_immutable("repoint a granted approval at another window",
                  lambda: setattr(OK, "window_title", "Broker Login"))
attempt_immutable("add account identifiers to a granted approval",
                  lambda: setattr(OK, "includes_account_identifiers", True))
attempt_immutable("move a granted approval's timestamp forward",
                  lambda: setattr(OK, "granted_at", NOW + datetime.timedelta(days=1)))
attempt_immutable("delete the ttl so expiry cannot be computed",
                  lambda: delattr(OK, "ttl_seconds"))
attempt_immutable("bolt an approve_all flag onto the object",
                  lambda: setattr(OK, "approve_all", True))
attempt_immutable("mutate the object's __dict__ directly",
                  lambda: OK.__dict__.update({"ttl_seconds": 999999}))
# PROBE FINDING 2026-08-15: this was ALLOWED on the first run, and it is the
# more serious of the two -- widening ONE approval was refused everywhere, but
# raising the class ceiling widened EVERY approval granted afterwards, MEASURED
# at a 138-hour standing consent passing validation. Source fixed (_SealedLimits
# metaclass). These stay as the regression.
attempt_immutable("raise the class-wide TTL ceiling for all future approvals",
                  lambda: setattr(CaptureApproval, "MAX_TTL_SECONDS", 999999))
attempt_immutable("lower the default ttl so callers silently get less scrutiny",
                  lambda: setattr(CaptureApproval, "DEFAULT_TTL_SECONDS", 1))
attempt_immutable("delete the ceiling so no ttl can exceed it",
                  lambda: delattr(CaptureApproval, "MAX_TTL_SECONDS"))
attempt_immutable("rewrite the field list to smuggle in an extra field",
                  lambda: setattr(CaptureApproval, "_FIELDS", ("window_title",)))

# The ceiling must not merely be un-writable -- a later approval must still be
# checked against the ORIGINAL value. Proven by trying to use the widened ttl.
attempt("a 138-hour approval, after trying to raise the ceiling for it",
        lambda: approval(ttl_seconds=500000))

struct("the approval survived every widening attempt",
       OK.ttl_seconds == 900 and OK.window_title == "AAPL Chart"
       and OK.includes_account_identifiers is False,
       "consent is what was given, not what was later wanted")
struct("the class TTL ceiling is still one hour",
       CaptureApproval.MAX_TTL_SECONDS == 3600,
       "a mutable ceiling would widen every future approval at once")

# ---------------------------------------------------------------------------
print("\n-- editing the module's own tables -----------------------------------")
# ---------------------------------------------------------------------------
attempt_immutable("delete 'passwords' from the forbidden pattern table",
                  lambda: ss._FORBIDDEN_PATTERNS.pop("passwords"))
attempt_immutable("empty the broker-login patterns",
                  lambda: ss._FORBIDDEN_PATTERNS.__setitem__(
                      "broker login dialogs", ()))
attempt_immutable("append to the forbidden targets tuple",
                  lambda: ss.FORBIDDEN_TARGETS.append("x"))
attempt_immutable("clear the TradingView marker list",
                  lambda: ss.TRADINGVIEW_MARKERS.clear())
attempt_immutable("rewrite the capability probe to claim capture exists",
                  lambda: ss.CAPABILITY_PROBE.__setitem__("mss", "PRESENT"))
attempt_immutable("edit the structurally-prevented table",
                  lambda: ss.STRUCTURALLY_PREVENTED.__setitem__("other monitors", ""))

struct("the forbidden pattern table still covers passwords",
       "passwords" in ss._FORBIDDEN_PATTERNS, "unedited")
struct("the TradingView markers still include the brand",
       "tradingview" in ss.TRADINGVIEW_MARKERS, "unedited")
struct("the capability probe still reports mss ABSENT",
       ss.CAPABILITY_PROBE["mss"] == "ABSENT", "unedited")

# ---------------------------------------------------------------------------
print("\n-- reaching a forbidden window ---------------------------------------")
# ---------------------------------------------------------------------------
for _forbidden in ("Broker Login", "1Password - Vault", "Bitwarden - My Vault",
                   "LastPass", "KeePass", "Sign in - Interactive Brokers",
                   "Two-Factor Authentication", "OTP code", "API Key settings",
                   "Seed phrase backup", "WhatsApp", "Telegram",
                   "Gmail - Inbox", "رمز عبور", "ورود به حساب"):
    attempt("capture %r with a matching approval" % _forbidden,
            lambda w=_forbidden: assert_capture_permitted(
                w, approval(w), now=NOW),
            "forbidden regardless of approval")

# Approval for one window must not spread to an adjacent one. A substring match
# would let "AAPL Chart" cover "AAPL Chart - Broker Login".
for _adjacent in ("AAPL Chart - Broker Login", "AAPL Chart - 1Password",
                  "AAPL Chart 2", "AAPL Chart - password reset"):
    attempt("use the AAPL Chart approval on %r" % _adjacent,
            lambda w=_adjacent: assert_capture_permitted(w, OK, now=NOW),
            "exact match only")

attempt("capture on an approval that expired one second ago",
        lambda: assert_capture_permitted(
            "AAPL Chart", OK, now=NOW + datetime.timedelta(seconds=901)))
attempt("capture a day after the approval was granted",
        lambda: assert_capture_permitted(
            "AAPL Chart", OK, now=NOW + datetime.timedelta(days=1)))
attempt("capture an account-numbered window without the explicit flag",
        lambda: assert_capture_permitted(
            "IBKR U1234567", approval("IBKR U1234567"), now=NOW))

# ---------------------------------------------------------------------------
print("\n-- obtaining pixels or text at all -----------------------------------")
# ---------------------------------------------------------------------------
attempt("capture_region on a fully approved window",
        lambda: capture_region("AAPL Chart", OK, now=NOW),
        "no backend exists")
attempt("capture_region on a forbidden window",
        lambda: capture_region("Broker Login", approval("Broker Login"), now=NOW))
attempt("extract_text with no arguments", lambda: extract_text())
attempt("extract_text on an ordinary window",
        lambda: extract_text(window_title="AAPL Chart"))
attempt("extract_text with a forged image object",
        lambda: extract_text(image=object(), window_title="AAPL Chart"))
attempt("extract_text with unexpected kwargs that might reach a backend",
        lambda: extract_text(window_title="AAPL Chart", lang="eng", config="--psm 6"))

# ---------------------------------------------------------------------------
print("\n-- laundering TradingView content ------------------------------------")
# ---------------------------------------------------------------------------
# THE ROUTE THAT WAS ONCE OPEN. Each of these tries to turn TradingView pixels
# into a machine-usable number by a different door.
for _tv in ("AAPL - TradingView", "tradingview.com/chart/xyz", "TV Chart",
            "Trading View - BTCUSD", "تریدینگ ویو - طلا"):
    attempt("build a Quote from the TradingView window %r" % _tv,
            lambda w=_tv: quote_from_screenshot(
                "AAPL", "NASDAQ", "USD", NOW, "UTC", 214.5, approval(w), w,
                now=NOW),
            "licence wall")
    attempt("OCR the TradingView window %r" % _tv,
            lambda w=_tv: extract_text(window_title=w), "licence wall")

attempt("claim exact extraction to make a TradingView value authoritative",
        lambda: quote_from_screenshot(
            "AAPL", "NASDAQ", "USD", NOW, "UTC", 214.5,
            approval("AAPL - TradingView"), "AAPL - TradingView",
            extraction_exact=True, confidence=1.0, now=NOW))
attempt("pass a TradingView approval but declare a clean window title",
        lambda: quote_from_screenshot(
            "AAPL", "NASDAQ", "USD", NOW, "UTC", 214.5,
            approval("AAPL - TradingView"), "AAPL Chart", now=NOW),
        "the approval and the title must agree")

# ---------------------------------------------------------------------------
print("\n-- using a screenshot value where it must not go ---------------------")
# ---------------------------------------------------------------------------
_q = quote_from_screenshot("AAPL", "NASDAQ", "USD", NOW, "UTC", 214.5, OK,
                           "AAPL Chart", now=NOW)
attempt("price a LIVE ORDER from a screenshot value",
        lambda: _q.assert_usable_for("live_order"))
attempt("use a screenshot value as sole evidence for a material calculation",
        lambda: _q.assert_usable_for("material_calculation"))
attempt_immutable("relabel the screenshot quote as a provider value",
                  lambda: setattr(_q, "origin", "PROVIDER_API"))
attempt_immutable("upgrade the screenshot quote's trust level",
                  lambda: setattr(_q, "trust_level", "VERIFIED"))
attempt_immutable("relabel the quote as realtime",
                  lambda: setattr(_q, "delay_status", "REALTIME"))

attempt("build a screenshot quote with no value at all",
        lambda: quote_from_screenshot("AAPL", "NASDAQ", "USD", NOW, "UTC", None,
                                      OK, "AAPL Chart", now=NOW))
attempt("declare a confidence above 1",
        lambda: quote_from_screenshot("AAPL", "NASDAQ", "USD", NOW, "UTC", 1.0,
                                      OK, "AAPL Chart", confidence=1.5, now=NOW))
attempt("declare a negative confidence",
        lambda: quote_from_screenshot("AAPL", "NASDAQ", "USD", NOW, "UTC", 1.0,
                                      OK, "AAPL Chart", confidence=-1, now=NOW))
attempt("declare extraction_exact with a truthy string",
        lambda: quote_from_screenshot("AAPL", "NASDAQ", "USD", NOW, "UTC", 1.0,
                                      OK, "AAPL Chart", extraction_exact="yes",
                                      now=NOW))

# ---------------------------------------------------------------------------
print("\n-- structural invariants ---------------------------------------------")
# ---------------------------------------------------------------------------

# POSITIVE CONTROLS FIRST. Everything above is a refusal, and a module that
# refused unconditionally would pass all of it while being useless. These three
# prove the probe is measuring discrimination, not blanket denial.
struct("an ordinary window IS approvable",
       assert_capture_permitted("AAPL Chart", OK, now=NOW) is None,
       "otherwise every refusal above proves nothing")
struct("a non-TradingView window DOES yield a Quote",
       _q is not None and _q.last == 214.5, "the module still functions")
struct("a screenshot value MAY be displayed to a human",
       _q.assert_usable_for("display") is None,
       "Level 3 output is for a person to read")

struct("the quote is labelled VISUALLY_EXTRACTED",
       _q.origin == "VISUALLY_EXTRACTED", "SS.7.1 Level 3")
struct("the quote is UNVERIFIED", _q.trust_level == "UNVERIFIED", "")
struct("the quote is not live", _q.is_live is False,
       "pixels cannot prove liveness")
struct("the quote survived every relabelling attempt",
       _q.origin == "VISUALLY_EXTRACTED" and _q.trust_level == "UNVERIFIED"
       and _q.delay_status == "UNKNOWN", "the label is what it was")

struct("CAPTURE_AVAILABLE is False", ss.CAPTURE_AVAILABLE is False, "MEASURED")
struct("OCR_AVAILABLE is False", ss.OCR_AVAILABLE is False, "MEASURED")

_src = open(os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "src", "market", "screenshot.py"), encoding="utf-8").read()

# The named shortcuts by which an explicit approval becomes a default. Checked
# against the source because absence cannot be demonstrated by calling anything.
#
# PROBE BUG 2026-08-15, MEASURED: a bare `in _src` reported 'approve_all' and
# 'remember=True' as FINDINGS because the class docstring says "There is no
# `approve_all` ... and no `remember=True`". The probe was reading the sentence
# promising the absence as evidence of the presence. A probe that fires on prose
# trains its reader to ignore it, so the docstring lines are stripped and the
# check is run against EXECUTABLE source only.
_code_lines = []
_in_doc = False
for _ln in _src.splitlines():
    _ticks = _ln.count('"""')
    if _in_doc:
        if _ticks:
            _in_doc = False
        continue
    if _ticks == 1:
        _in_doc = True
        continue
    if _ticks >= 2:
        continue
    if _ln.lstrip().startswith("#"):
        continue
    _code_lines.append(_ln)
_code = "\n".join(_code_lines)

for _shortcut in ("approve_all", "remember=True", "def bypass", "SKIP_APPROVAL",
                  "allow_all"):
    struct("no %r shortcut exists in executable code" % _shortcut,
           _shortcut not in _code,
           "each is how an explicit approval quietly becomes a default")

# The stripper must not become a way to hide code from the check. If it ever
# removes so much that the module's own guards vanish, every check above passes
# vacuously -- so prove the executable text still contains them.
struct("the docstring stripper kept the executable guards",
       "def assert_covers" in _code and "MAX_TTL_SECONDS" in _code,
       "a filter that removed the code would make every check above vacuous")

# No capture or OCR backend may be imported. If one ever is, CAPTURE_AVAILABLE
# must change in the same commit -- and this check is what forces that pairing.
_import_lines = [ln for ln in _src.splitlines()
                 if ln.lstrip().startswith(("import ", "from "))]
for _backend in ("mss", "pyautogui", "pytesseract", "easyocr", "paddleocr",
                 "Xlib", "pygetwindow"):
    struct("no %s import exists" % _backend,
           not any(_backend in ln for ln in _import_lines),
           "a capability claim must change in the same commit as its import")
for _forbidden in ("eval(", "exec(", "os.system", "__import__", "subprocess"):
    struct("the module never calls %r" % _forbidden, _forbidden not in _src,
           "no dynamic execution near a consent gate")

# The laundering gate must be CALLED, not merely defined. This is the exact
# defect this module recorded against itself: the function existed and nothing
# invoked it.
struct("the licence wall is CALLED inside quote_from_screenshot",
       _src.count("assert_tradingview_extraction_refused(") >= 3,
       "defined once and called from quote_from_screenshot and extract_text; "
       "a wall nothing calls protects nothing")
struct("quote_from_screenshot checks the TradingView surface",
       "if is_tradingview_surface(window_title):" in _src,
       "the gate is on the path, not beside it")
struct("the consent gate is re-run where the label is attached",
       "assert_capture_permitted(window_title, approval, now=now)" in _src,
       "a Quote must not exist for a window nobody approved")

# Every declared prohibition must be enforced or explicitly explained.
_covered = set(ss._FORBIDDEN_PATTERNS) | set(ss.STRUCTURALLY_PREVENTED)
struct("every declared forbidden target is enforced or explained",
       all(t in _covered for t in ss.FORBIDDEN_TARGETS),
       "a list nothing checks is decoration")

print()
print("=" * 78)
print("  attempts:  %d" % (STATE["refused"] + STATE["allowed"] + STATE["crashed"]))
print("  refused:   %d" % STATE["refused"])
print("  ALLOWED:   %d" % STATE["allowed"])
print("  CRASHED:   %d" % STATE["crashed"])
print("  structural: %d ok, %d broken" % (STRUCT["ok"], STRUCT["broken"]))
if FINDINGS:
    print()
    print("  FINDINGS:")
    for f in FINDINGS:
        print("    - %s" % f)
print("=" * 78)

_bad = STATE["allowed"] + STATE["crashed"] + STRUCT["broken"]
print("PROBE RESULT: %s" % ("OK" if _bad == 0 else "%d FINDINGS" % _bad))
sys.exit(1 if _bad else 0)
