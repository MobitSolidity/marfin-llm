"""
Mutation battery for the SS.7.1 Level 3 visual integration surface.

WHY THIS MODULE NEEDS ONE MORE THAN MOST
screenshot.py is 660 lines of consent gates and a licence wall for a capability
this runtime DOES NOT HAVE: CAPTURE_AVAILABLE is False, OCR_AVAILABLE is False,
no backend is installed, DISPLAY is unset. Nothing exercises it in ordinary use,
which means nothing notices when a guard rots. It is the single most likely
module in the project to be quietly wrong, because being wrong here costs
nothing today and everything on the first machine that has a screen.

Its own history says so. MEASURED at first execution: the docstring claimed
TradingView extraction was refused, the refusal function existed, and NOTHING
CALLED IT -- a TradingView window returned a usable Quote. The wall was real and
unreachable.

And the adversarial probe written the same day as this battery found two more,
both MEASURED, neither visible to 162 passing unit assertions:

  1. is_expired() bounded the consent window at the TOP only, so an approval
     stamped tomorrow was honoured today.
  2. every attempt to widen ONE approval was refused by __slots__, but
     `CaptureApproval.MAX_TTL_SECONDS = 999999` succeeded and widened EVERY
     approval granted afterwards -- a 138-hour standing consent passed
     validation.

Both are fixed. These mutations exist so that neither fix, nor any of the guards
beside them, can quietly become decoration again.

ORACLES: test_screenshot.py AND probe_screenshot.py. Both are needed and neither
suffices. The unit suite holds the refusal WORDING and the positive controls; the
probe holds the structural facts no call can demonstrate -- that the licence wall
is called on the path rather than merely defined beside it, that no capture
backend is imported, that no approve_all shortcut exists. A mutation that deletes
a call while leaving the definition intact is invisible to the first and fatal to
the second.

Stdlib only.
"""

import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC_ROOT = os.path.join(ROOT, "src")

ORACLES = ("test_screenshot.py", "probe_screenshot.py")

M = "market/screenshot.py"


def module_path(module):
    return os.path.join(SRC_ROOT, module)


# Empty, and it is meant to stay that way. In the broker battery an "unreachable
# guard" was very nearly filed here, on the true observation that record() has no
# external caller today -- a fact about the file's current shape, not about the
# guard. It was killed structurally instead, and this project has already watched
# one equivalence note go stale exactly that way. An entry here must be an
# argument about INPUTS, not about who happens to call what this week.
EQUIVALENT = {}

# (module, description, find, replace)
MUTATIONS = [
    # --- the capability claim: the module must not acquire powers by edit ----
    # Disambiguated: "CAPTURE_AVAILABLE = False" is MEASURED at count 2 -- the
    # module docstring quotes the constant as well as setting it. The runner
    # would have reported an ambiguous SKIP, and a SKIP is worse than a survivor
    # because it prints a line inside a passing report while testing nothing.
    (M, "the module claims a capture backend it does not have",
     "\nCAPTURE_AVAILABLE = False\nOCR_AVAILABLE = False",
     "\nCAPTURE_AVAILABLE = True\nOCR_AVAILABLE = False"),
    (M, "the module claims OCR it does not have",
     "OCR_AVAILABLE = False", "OCR_AVAILABLE = True"),
    (M, "the capability probe is edited to hide an absent backend",
     '    "mss": "ABSENT",', '    "mss": "PRESENT",'),
    (M, "the probe table becomes mutable, so a caller can edit the evidence",
     "CAPABILITY_PROBE: Mapping[str, str] = MappingProxyType({",
     "CAPABILITY_PROBE: Mapping[str, str] = ({"),

    # --- the forbidden-target table -----------------------------------------
    (M, "'passwords' is dropped from the declared forbidden targets",
     '    "passwords",\n    "api keys",', '    "api keys",'),
    (M, "the password pattern stops matching",
     '"passwords": ("password", "passwd"',
     '"passwords": ("__never__", "passwd"'),
    (M, "the Persian password patterns are dropped",
     '"رمز عبور", "گذرواژه"', '"__never1__", "__never2__"'),
    (M, "the Persian login pattern is dropped",
     '"one-time code", "ورود"', '"one-time code", "__never__"'),
    (M, "the Persian api-key pattern is dropped",
     '"کلید api"', '"__never__"'),
    (M, "'login' stops marking a broker login dialog",
     '"broker login dialogs": ("login", "log in"',
     '"broker login dialogs": ("__never__", "log in"'),
    (M, "the api-key pattern loses 'api key'",
     '"api keys": ("api key", "api_key"',
     '"api keys": ("__never__", "api_key"'),
    (M, "private notifications stop being screened",
     '"private notifications": ("notification", "message from"',
     '"private notifications": ("__never__", "message from"'),
    (M, "the forbidden pattern table becomes mutable",
     "_FORBIDDEN_PATTERNS: Mapping[str, Tuple[str, ...]] = MappingProxyType({",
     "_FORBIDDEN_PATTERNS: Mapping[str, Tuple[str, ...]] = ({"),
    (M, "the structurally-prevented explanations become mutable",
     "STRUCTURALLY_PREVENTED: Mapping[str, str] = MappingProxyType({",
     "STRUCTURALLY_PREVENTED: Mapping[str, str] = ({"),
    (M, "a declared target loses its structural explanation",
     '    "other monitors":\n        "same reason:',
     '    "other monitors XX":\n        "same reason:'),

    # --- the seal on the consent limits -------------------------------------
    # PROBE FINDING 2026-08-15: this metaclass did not exist and the ceiling was
    # writable, so `CaptureApproval.MAX_TTL_SECONDS = 999999` widened every
    # approval granted afterwards. Each mutation below re-opens that hole a
    # different way.
    (M, "the consent limits are no longer sealed against rebinding",
     '        if name in _SealedLimits._SEALED:\n            raise ScreenshotError(\n                "refusing to rebind',
     '        if False:\n            raise ScreenshotError(\n                "refusing to rebind'),
    (M, "the TTL ceiling is dropped from the sealed set",
     '_SEALED = frozenset(("DEFAULT_TTL_SECONDS", "MAX_TTL_SECONDS", "_FIELDS"))',
     '_SEALED = frozenset(("DEFAULT_TTL_SECONDS", "_FIELDS"))'),
    (M, "the limits can be DELETED even though they cannot be set",
     '        if name in _SealedLimits._SEALED:\n            raise ScreenshotError(\n                "refusing to delete',
     '        if False:\n            raise ScreenshotError(\n                "refusing to delete'),
    (M, "the class stops using the sealing metaclass entirely",
     "class CaptureApproval(object, metaclass=_SealedLimits):",
     "class CaptureApproval(object):"),

    # --- the approval's own validation --------------------------------------
    (M, "an approval with no window title is accepted",
     "        if not isinstance(window_title, str) or not window_title.strip():\n"
     "            raise ScreenshotError(\n"
     '                "window_title must name the window',
     "        if False:\n"
     "            raise ScreenshotError(\n"
     '                "window_title must name the window'),
    (M, "a wildcard window title is accepted",
     '        if "*" in window_title or window_title.strip() in ("all", "any"):',
     "        if False:"),
    (M, "the wildcard check stops covering the bare word 'all'",
     '        if "*" in window_title or window_title.strip() in ("all", "any"):',
     '        if "*" in window_title or window_title.strip() in ("any",):'),
    (M, "an approval with no stated purpose is accepted",
     "        if not isinstance(purpose, str) or not purpose.strip():",
     "        if False:"),
    (M, "an approval with no grantor is accepted",
     "        if not isinstance(granted_by, str) or not granted_by.strip():",
     "        if False:"),
    (M, "ttl=True is accepted, and Python reads it as 1 second",
     "        if not isinstance(ttl_seconds, int) or isinstance(ttl_seconds, bool):",
     "        if not isinstance(ttl_seconds, int):"),
    (M, "a zero or negative ttl is accepted",
     "        if ttl_seconds <= 0:", "        if False:"),
    (M, "the ttl ceiling is no longer enforced at construction",
     "        if ttl_seconds > self.MAX_TTL_SECONDS:", "        if False:"),
    (M, "the ttl ceiling is raised to a full day",
     "    MAX_TTL_SECONDS = 3600", "    MAX_TTL_SECONDS = 86400"),
    (M, "the default ttl becomes a standing permission",
     "    DEFAULT_TTL_SECONDS = 900", "    DEFAULT_TTL_SECONDS = 86400"),
    (M, "account identifiers can be approved by a truthy value",
     "        if includes_account_identifiers is not True and \\\n"
     "                includes_account_identifiers is not False:",
     "        if False:"),
    (M, "a naive granted_at is accepted, so expiry cannot be checked",
     "        if granted_at.tzinfo is None:", "        if False:"),

    # --- immutability of a granted approval ---------------------------------
    (M, "a granted approval can be edited after the fact",
     '    def __setattr__(self, name, value):\n'
     '        if getattr(self, "_frozen", False):',
     '    def __setattr__(self, name, value):\n'
     '        if False:'),
    (M, "the freeze is never applied, so nothing is immutable",
     '        object.__setattr__(self, "_frozen", True)',
     '        object.__setattr__(self, "_frozen", False)'),
    (M, "fields can be deleted off a granted approval",
     '    def __delattr__(self, name):\n'
     '        raise ScreenshotError("an approval is immutable: refusing to delete',
     '    def __delattr__(self, name):\n'
     '        return None\n'
     '        raise ScreenshotError("an approval is immutable: refusing to delete'),
    (M, "__slots__ is dropped, so arbitrary attributes can be bolted on",
     '    __slots__ = _FIELDS + ("_frozen",)',
     '    __dict__slots_removed = _FIELDS + ("_frozen",)'),

    # --- the consent TIME WINDOW, bounded at both ends ----------------------
    # PROBE FINDING 2026-08-15: the lower bound did not exist, so an approval
    # stamped tomorrow was honoured today.
    (M, "the future-dating guard is removed from assert_covers",
     "        if self.is_not_yet_valid(now):", "        if False:"),
    (M, "is_not_yet_valid always answers False",
     "        return now < self.granted_at", "        return False"),
    (M, "the lower bound is made exclusive at the grant instant",
     "        return now < self.granted_at", "        return now <= self.granted_at"),
    (M, "the expiry guard is removed from assert_covers",
     "        if self.is_expired(now):", "        if False:"),
    (M, "is_expired always answers False, so consent never decays",
     "        return now >= self.expires_at", "        return False"),
    (M, "the expiry boundary becomes exclusive, granting one extra tick",
     "        return now >= self.expires_at", "        return now > self.expires_at"),
    (M, "expires_at ignores the ttl entirely",
     "        return self.granted_at + datetime.timedelta(seconds=self.ttl_seconds)",
     "        return self.granted_at + datetime.timedelta(days=3650)"),

    # --- assert_covers: exact window, no widening ---------------------------
    (M, "an approval covers ANY window, not the one it names",
     "        if window_title.strip().lower() != self.window_title.lower():",
     "        if False:"),
    (M, "window matching widens to a substring match",
     "        if window_title.strip().lower() != self.window_title.lower():",
     "        if self.window_title.lower() not in window_title.strip().lower():"),
    (M, "window matching becomes case-SENSITIVE, refusing valid captures",
     "        if window_title.strip().lower() != self.window_title.lower():",
     "        if window_title.strip() != self.window_title:"),
    (M, "assert_covers accepts an empty window title",
     '        if not isinstance(window_title, str) or not window_title.strip():\n'
     '            raise ScreenshotError("window_title must be a non-empty string")',
     '        if False:\n'
     '            raise ScreenshotError("window_title must be a non-empty string")'),

    # --- forbidden_reasons: the screen itself -------------------------------
    (M, "screening reports only the FIRST reason, implying one fix suffices",
     "            if pat in text:\n"
     '                found.append("%s (matched %r)" % (target, pat))\n'
     "                break",
     "            if pat in text:\n"
     '                found.append("%s (matched %r)" % (target, pat))\n'
     "                return tuple(found)"),
    (M, "screening finds nothing, ever",
     "            if pat in text:", "            if False:"),
    # Disambiguated: "text = window_title.lower()" is MEASURED at count 2 --
    # is_tradingview_surface's line begins with the same text before its
    # .replace("-", " "). Anchored on the following line instead.
    (M, "screening becomes case-sensitive, so 'PASSWORD' passes",
     "    text = window_title.lower()\n    found = []",
     "    text = window_title\n    found = []"),
    (M, "the account-identifier check is dropped from screening",
     "    if _looks_like_account_identifier(window_title) and not (",
     "    if False and _looks_like_account_identifier(window_title) and not ("),
    (M, "an approval's account flag is ignored, refusing an approved capture",
     "            approval is not None and approval.includes_account_identifiers):",
     "            approval is not None):"),
    (M, "the account pattern stops matching a long digit run",
     r'    r"(\d{6,})"                              # 1234567',
     r'    r"(?!x)x(\d{6,})"                        # 1234567'),
    (M, "the account pattern stops matching a grouped account number",
     r'    r"|(\d{3,}[\-\s]\d{3,}[\-\s]\d{2,})"     # 1234-5678-9012',
     r'    r"|(?!x)x(\d{3,}[\-\s]\d{3,}[\-\s]\d{2,})" # 1234-5678-9012'),
    (M, "the account pattern stops matching a masked number",
     r'    r"|([*x\u2022]{3,}[\s\-]?\d{2,})",       # ****5678 / xxxx-5678',
     r'    r"|(?!x)x([*x\u2022]{3,}[\s\-]?\d{2,})", # ****5678 / xxxx-5678'),
    (M, "the account pattern is loosened back to its MEASURED false-positive form",
     r'    r"(\d{6,})"                              # 1234567',
     r'    r"(\d[\d\-\s]{5,}\d)"                    # 1234567'),

    # --- assert_capture_permitted: consent BEFORE content -------------------
    (M, "capture no longer requires a CaptureApproval object at all",
     "    if not isinstance(approval, CaptureApproval):", "    if False:"),
    (M, "any duck-typed object is accepted as an approval",
     "    if not isinstance(approval, CaptureApproval):",
     "    if approval is None:"),
    (M, "the approval is never checked against the window",
     "    approval.assert_covers(window_title, now=now)\n"
     "    reasons = forbidden_reasons(window_title, approval)",
     "    reasons = forbidden_reasons(window_title, approval)"),
    (M, "the forbidden-target screen is skipped in the gate",
     "    reasons = forbidden_reasons(window_title, approval)\n    if reasons:",
     "    reasons = forbidden_reasons(window_title, approval)\n    if False:"),
    # MEASURED 2026-08-15, and the correction matters more than the mutation.
    # This entry first swapped the two STATEMENTS -- moving the
    # forbidden_reasons() call above assert_covers() -- and it survived. The
    # survivor was not a gap in the tests: it was a no-op mutation I had
    # mis-designed. forbidden_reasons() only COLLECTS reasons; the raise sits
    # below in `if reasons:`, so consent still answered first and no input could
    # distinguish the mutant. Reversing the order OBSERVABLY means moving the
    # raise, which is what this now does. The lesson is the one this project
    # keeps relearning: diagnose the survivor by measuring the mutant, because
    # "the tests are too weak" is only one of the possible answers.
    (M, "content is screened BEFORE consent, reversing the safe order",
     "    approval.assert_covers(window_title, now=now)\n"
     "    reasons = forbidden_reasons(window_title, approval)\n"
     "    if reasons:\n"
     "        raise ScreenshotError(\n"
     '            "refusing to capture %r: %s. SS.7.1 Level 3 forbids capturing these "\n'
     '            "regardless of approval -- a user may consent to a capture without "\n'
     '            "realising a credential is on screen, and an audit record is "\n'
     '            "designed to be durable."\n'
     '            % (window_title, "; ".join(reasons)))',
     "    reasons = forbidden_reasons(window_title, approval)\n"
     "    if reasons:\n"
     "        raise ScreenshotError(\n"
     '            "refusing to capture %r: %s. SS.7.1 Level 3 forbids capturing these "\n'
     '            "regardless of approval -- a user may consent to a capture without "\n'
     '            "realising a credential is on screen, and an audit record is "\n'
     '            "designed to be durable."\n'
     '            % (window_title, "; ".join(reasons)))\n'
     "    approval.assert_covers(window_title, now=now)"),
    (M, "the gate's `now` is dropped, so expiry is judged against wall clock",
     "    approval.assert_covers(window_title, now=now)",
     "    approval.assert_covers(window_title)"),

    # --- capture / extract: the refusals must stay refusals ------------------
    (M, "capture_region stops evaluating the consent gate first",
     "    assert_capture_permitted(window_title, approval, now=now)\n"
     "    raise ScreenshotError(\n"
     '        "screen capture is not available',
     "    raise ScreenshotError(\n"
     '        "screen capture is not available'),
    (M, "capture_region returns instead of refusing",
     "    raise ScreenshotError(\n"
     '        "screen capture is not available in this runtime',
     "    return None\n"
     "    raise ScreenshotError(\n"
     '        "screen capture is not available in this runtime'),
    (M, "extract_text returns instead of refusing",
     "    raise ScreenshotError(\n"
     '        "text extraction (OCR) is not available',
     "    return None\n"
     "    raise ScreenshotError(\n"
     '        "text extraction (OCR) is not available'),

    # --- THE LAUNDERING GATE -------------------------------------------------
    # MEASURED as this module's worst defect: the wall existed, the docstring
    # claimed it was enforced, and NOTHING CALLED IT. A TradingView window
    # returned a usable Quote. Each of these re-opens that exact route.
    (M, "the licence wall is not called when building a Quote",
     "    if is_tradingview_surface(window_title):\n"
     "        assert_tradingview_extraction_refused(\n"
     '            "building a Quote from window %r" % (window_title,))',
     "    if False:\n"
     "        assert_tradingview_extraction_refused(\n"
     '            "building a Quote from window %r" % (window_title,))'),
    (M, "the licence wall is not called when extracting text",
     "    if window_title and is_tradingview_surface(window_title):",
     "    if False:"),
    (M, "the licence wall is defined but its body does nothing",
     "    tradingview.assert_display_only_use(",
     "    return None\n    tradingview.assert_display_only_use("),
    # A duplicate of "the consent gate is not re-run where the label is
    # attached" sat here: same find, same replace, a description that misread a
    # DELETION as a reordering. Removed rather than left to inflate the seeded
    # count -- a battery that reports 90 while testing 89 things is lying about
    # the one number it exists to produce.
    (M, "'tradingview' stops being recognised as a TradingView surface",
     '    "tradingview", "trading view", "tradingview.com", "tv chart",',
     '    "__never__", "trading view", "tradingview.com", "tv chart",'),
    (M, "the Persian TradingView marker is dropped",
     '    "تریدینگ ویو",\n)', '    "__never__",\n)'),
    (M, "surface detection stops normalising hyphens",
     '    text = window_title.lower().replace("-", " ")',
     "    text = window_title.lower()"),
    (M, "surface detection becomes case-sensitive",
     "    return any(m in text or m in window_title.lower()\n"
     "               for m in TRADINGVIEW_MARKERS)",
     "    return any(m in window_title for m in TRADINGVIEW_MARKERS)"),

    # --- the Quote's labels: a mislabel here is undetectable downstream ------
    (M, "a screenshot quote claims REALTIME data",
     '        delay_status="UNKNOWN", market_status="UNKNOWN",',
     '        delay_status="REALTIME", market_status="UNKNOWN",'),
    (M, "a screenshot quote claims the market is OPEN",
     '        delay_status="UNKNOWN", market_status="UNKNOWN",',
     '        delay_status="UNKNOWN", market_status="OPEN",'),
    (M, "a screenshot quote is upgraded out of the WEAK origins",
     '        trust_level="UNVERIFIED", origin="VISUALLY_EXTRACTED", last=last,',
     '        trust_level="UNVERIFIED", origin="OFFICIAL_API", last=last,'),
    (M, "a screenshot quote claims a VERIFIED trust level",
     '        trust_level="UNVERIFIED", origin="VISUALLY_EXTRACTED", last=last,',
     '        trust_level="VERIFIED", origin="VISUALLY_EXTRACTED", last=last,'),
    (M, "the quote no longer names the screenshot as its provider",
     '        provider="screenshot:%s" % (approval.window_title,),',
     '        provider="%s" % (approval.window_title,),'),
    (M, "the provider is taken from the REQUESTED window, not the approved one",
     '        provider="screenshot:%s" % (approval.window_title,),',
     '        provider="screenshot:%s" % (window_title,),'),
    (M, "an APPROXIMATE reading is described as exact-text",
     '              % ("exact-text" if extraction_exact else "APPROXIMATE",',
     '              % ("exact-text" if not extraction_exact else "APPROXIMATE",'),
    (M, "the consent gate is not re-run where the label is attached",
     "    assert_capture_permitted(window_title, approval, now=now)\n"
     "    # THE LAUNDERING GATE.",
     "    # THE LAUNDERING GATE."),
    (M, "a quote can be built with no value at all",
     "    if last is None:", "    if False:"),
    (M, "extraction_exact accepts a truthy value and upgrades the claim",
     "    if extraction_exact is not True and extraction_exact is not False:",
     "    if False:"),
    (M, "confidence accepts a non-numeric value into an audit record",
     "        if not isinstance(confidence, (int, float)) or \\\n"
     "                isinstance(confidence, bool):",
     "        if False:"),
    (M, "confidence accepts a value outside 0..1",
     "        if not (0.0 <= float(confidence) <= 1.0):", "        if False:"),

    # --- the manifest must not misreport the module -------------------------
    (M, "the manifest claims capture is available",
     '            "capture_available": CAPTURE_AVAILABLE,',
     '            "capture_available": True,'),
    (M, "the manifest denies that the origin is weak",
     '            "is_weak_origin": True,', '            "is_weak_origin": False,'),
    (M, "the manifest claims screenshots are usable for live orders",
     '            "usable_for_live_order": False,',
     '            "usable_for_live_order": True,'),
    (M, "the manifest claims screenshots are usable for material calculation",
     '            "usable_for_material_calculation": False,',
     '            "usable_for_material_calculation": True,'),
    (M, "the manifest claims TradingView extraction is permitted",
     '            "tradingview_extraction": "REFUSED (non-display machine use)",',
     '            "tradingview_extraction": "PERMITTED",'),
    (M, "the manifest stops requiring approval",
     '            "approval_required": True,',
     '            "approval_required": False,'),
]

def run_oracle(name):
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = SRC_ROOT + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, os.path.join(HERE, name)],
        cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return proc.returncode == 0, proc.stdout.decode("utf-8", "replace")


def run_tests():
    for name in ORACLES:
        ok, out = run_oracle(name)
        if not ok:
            return False, "%s FAILED\n%s" % (name, out[-2000:])
    return True, ""


def main():
    for dirpath, dirnames, _ in os.walk(ROOT):
        for d in list(dirnames):
            if d == "__pycache__":
                shutil.rmtree(os.path.join(dirpath, d), ignore_errors=True)

    ok, out = run_tests()
    if not ok:
        print("ABORT: the oracle fails BEFORE any mutation is applied.")
        print(out[-3000:])
        return 1
    print("baseline: oracle passes (%s), %d mutations to apply\n"
          % (", ".join(ORACLES), len(MUTATIONS)))

    backup = tempfile.mkdtemp(prefix="shot_orig_")
    _backed_up = {}
    for module in sorted({m for (m, _, _, _) in MUTATIONS}):
        flat = module.replace("/", "__")
        shutil.copy2(module_path(module), os.path.join(backup, flat))
        _backed_up[flat] = module_path(module)

    killed = survived = skipped = equivalent = 0
    survivors, skips, unexpected_kills = [], [], []
    try:
        for i, (module, desc, find, repl) in enumerate(MUTATIONS, 1):
            path = module_path(module)
            with open(path, "r", encoding="utf-8") as fh:
                original = fh.read()
            if find not in original:
                skipped += 1
                skips.append("%s: %s" % (module, desc))
                print("  %2d. SKIP     %-58s (pattern absent)" % (i, desc[:58]))
                continue
            if original.count(find) > 1:
                skipped += 1
                skips.append("%s: %s (ambiguous)" % (module, desc))
                print("  %2d. SKIP     %-58s (ambiguous)" % (i, desc[:58]))
                continue
            mutated = original.replace(find, repl, 1)
            if mutated == original:
                # A no-op mutation is a bug in THIS file, not a finding. Written
                # one five times in this project; the check stays.
                skipped += 1
                skips.append("%s: %s (NO-OP)" % (module, desc))
                print("  %2d. SKIP     %-58s (NO-OP, fix the mutation)"
                      % (i, desc[:58]))
                continue
            try:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(mutated)
                passed, _ = run_tests()
                key = "%s: %s" % (module, desc)
                if passed and key in EQUIVALENT:
                    equivalent += 1
                    print("  %2d. equiv    %-58s (%s)"
                          % (i, desc[:58], EQUIVALENT[key][:40]))
                elif passed:
                    survived += 1
                    survivors.append(key)
                    print("  %2d. SURVIVED %-58s <-- NOT TESTED" % (i, desc[:58]))
                else:
                    killed += 1
                    if key in EQUIVALENT:
                        unexpected_kills.append(key)
                    print("  %2d. killed   %s" % (i, desc[:58]))
            finally:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(original)
    finally:
        for name, dest in _backed_up.items():
            shutil.copy2(os.path.join(backup, name), dest)
        shutil.rmtree(backup, ignore_errors=True)

    intact, _ = run_tests()
    print("\n" + "=" * 78)
    print("  seeded:     %d" % len(MUTATIONS))
    print("  killed:     %d" % killed)
    print("  equivalent: %d (documented redundant guards)" % equivalent)
    print("  survived:   %d" % survived)
    print("  skipped:    %d" % skipped)
    print("  source restored and oracles green: %s" % intact)
    for s in survivors:
        print("  SURVIVOR: %s" % s)
    for s in skips:
        print("  SKIPPED:  %s" % s)
    for s in unexpected_kills:
        print("  RECHECK:  %s was listed as equivalent but was KILLED" % s)
    print("=" * 78)
    return 0 if (survived == 0 and skipped == 0 and not unexpected_kills
                 and intact) else 1


if __name__ == "__main__":
    sys.exit(main())
