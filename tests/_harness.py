"""
Shared assertion harness for the calculation test suites.

Extracted so the four R14 family suites use identical, already-exercised
assertion logic rather than four near-copies that can drift apart.

VERIFICATION METHOD CODES used throughout the suites:
  (A) CLOSED FORM     -- an input whose answer is known analytically
                         (par bond prices at par; zero-coupon Macaulay
                         duration equals maturity; constant prices give zero
                         volatility).
  (B) HAND ARITHMETIC -- computed independently on paper, written as a literal.
  (C) INVARIANT       -- a property that must hold whatever the implementation
                         (put-call parity; binomial converging to
                         Black-Scholes; a round trip through an inverse).
  (D) FAILURE         -- invalid input must RAISE, not return a wrong number.

No test re-runs the formula under test. That would only prove code equals
itself.
"""

import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

_STATE = {"pass": 0, "fail": 0, "failures": []}


def _ok(name, method):
    _STATE["pass"] += 1
    print("  PASS  %-46s %s" % (name, method))


def _bad(name, detail):
    _STATE["fail"] += 1
    _STATE["failures"].append(name)
    print("  FAIL  %-46s %s" % (name, detail))


def check(name, got, want, tol=1e-9, method=""):
    """Numeric equality within tolerance."""
    try:
        got = float(got)
    except (TypeError, ValueError):
        _bad(name, "non-numeric result %r" % (got,))
        return
    if math.isnan(got) or math.isinf(got):
        _bad(name, "NaN/Inf result")
        return
    if abs(got - want) <= tol:
        _ok(name, method)
    else:
        _bad(name, "got %.12g want %.12g (tol %g)" % (got, want, tol))


def check_true(name, cond, method=""):
    if cond:
        _ok(name, method)
    else:
        _bad(name, "condition false")


def check_raises(name, fn, exc=Exception):
    """(D) The call MUST raise. Silence here is a defect, not a pass."""
    try:
        fn()
    except exc:
        _ok(name, "(D) correctly raised")
        return
    except Exception as e:  # noqa: BLE001
        _bad(name, "wrong exception: %r" % (e,))
        return
    _bad(name, "did NOT raise")


def section(title):
    print("\n[%s]" % title)


def summary():
    print("\n" + "=" * 78)
    print("RESULT: %d passed, %d failed" % (_STATE["pass"], _STATE["fail"]))
    if _STATE["failures"]:
        print("Failed: %s" % ", ".join(_STATE["failures"]))
    print("=" * 78)
    return 1 if _STATE["fail"] else 0
