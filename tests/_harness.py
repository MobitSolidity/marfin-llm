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


# Exceptions that represent a DELIBERATE refusal. Every `raise` in src/ is one
# of these (MEASURED: 172 ValueError, 13 TypeError, 11 ZeroDivisionError).
REFUSALS = (ValueError, TypeError, ZeroDivisionError)

# Exceptions that mean the code CRASHED on its way to somewhere else. These are
# not refusals, however much they look like one from the outside.
CRASHES = (AttributeError, IndexError, KeyError, NameError, UnboundLocalError,
           RecursionError)


def check_raises(name, fn, exc=REFUSALS):
    """
    (D) The call MUST refuse. Silence here is a defect, not a pass.

    The default used to be `Exception`, which accepted ANY failure -- including
    an AttributeError raised three frames deeper because a guard had been
    deleted. A mutation battery caught exactly that: removing rerank's type
    check left the test green, because a bare list then crashed instead of
    being refused, and the assertion could not tell the difference.

    So the default now accepts only exceptions that a deliberate guard raises,
    and names crash-type exceptions as failures. A test that genuinely wants a
    crash type must say so explicitly.
    """
    try:
        fn()
    except exc:
        _ok(name, "(D) correctly raised")
        return
    except CRASHES as e:
        _bad(name, "CRASHED rather than refused: %s: %s"
                   % (type(e).__name__, e))
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
