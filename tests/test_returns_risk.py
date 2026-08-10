#!/usr/bin/env python3
"""
Independent verification of src/calc/returns_risk.py (Phase 2 acceptance).

VERIFICATION METHOD MATTERS. A test that re-implements the function under test
with the same formula proves nothing -- it only proves the code equals itself.
Every expected value below comes from one of:

  (A) CLOSED FORM   -- an input whose answer is known analytically
                       (e.g. 10 identical returns of +1% -> vol exactly 0).
  (B) HAND ARITHMETIC -- computed independently and written as a literal.
  (C) INVARIANT     -- a property that must hold regardless of implementation
                       (CVaR <= VaR; risk contributions sum to portfolio vol;
                       beta of a series against itself == 1).
  (D) FAILURE       -- invalid input must RAISE, not return a wrong number.

Run: python3 tests/test_returns_risk.py
"""

import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from calc import returns_risk as rr  # noqa: E402

PASS = FAIL = 0
FAILURES = []


def check(name, got, want, tol=1e-9, method=""):
    global PASS, FAIL
    ok = abs(got - want) <= tol
    if ok:
        PASS += 1
        print("  PASS  %-40s %s" % (name, method))
    else:
        FAIL += 1
        FAILURES.append(name)
        print("  FAIL  %-40s got %.12g want %.12g" % (name, got, want))


def check_true(name, cond, method=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  PASS  %-40s %s" % (name, method))
    else:
        FAIL += 1
        FAILURES.append(name)
        print("  FAIL  %-40s condition false" % name)


def check_raises(name, fn, exc=Exception):
    global PASS, FAIL
    try:
        fn()
    except exc:
        PASS += 1
        print("  PASS  %-40s (D) correctly raised" % name)
        return
    except Exception as e:
        FAIL += 1
        FAILURES.append(name)
        print("  FAIL  %-40s wrong exception: %r" % (name, e))
        return
    FAIL += 1
    FAILURES.append(name)
    print("  FAIL  %-40s did NOT raise" % name)


print("=" * 78)
print("DETERMINISTIC CALCULATION ENGINE -- INDEPENDENT VERIFICATION")
print("=" * 78)

# -------------------------------------------------------------------------
print("\n[returns]")
# (B) 100 -> 150 is +50%. Trivially hand-checkable.
check("simple_return 100->150", rr.simple_return(100, 150).value, 0.5,
      method="(B) hand")
# (B) halving is -50%
check("simple_return 200->100", rr.simple_return(200, 100).value, -0.5,
      method="(B) hand")
# (A) ln(e) == 1 exactly
check("log_return 1->e", rr.log_return(1.0, math.e).value, 1.0,
      method="(A) closed form")
# (A) no change -> 0
check("log_return flat", rr.log_return(50, 50).value, 0.0,
      method="(A) closed form")
# (A) doubling over exactly 1 year = 100%
check("cagr double in 1yr", rr.cagr(100, 200, 1).value, 1.0,
      method="(A) closed form")
# (B) 100->400 over 2 years: sqrt(4)-1 = 1.0
check("cagr 100->400 in 2yr", rr.cagr(100, 400, 2).value, 1.0,
      method="(B) hand: sqrt(4)-1")
# (A) 12 monthly returns of exactly 0 -> annualized 0
check("annualized_return zeros", rr.annualized_return([0.0] * 12, "monthly").value,
      0.0, method="(A) closed form")
# (B) 12 monthly returns of +1% -> 1.01^12 - 1
check("annualized_return 1%/mo",
      rr.annualized_return([0.01] * 12, "monthly").value,
      1.01 ** 12 - 1, tol=1e-12, method="(B) 1.01^12-1")

# -------------------------------------------------------------------------
print("\n[volatility]")
# (A) constant returns have exactly zero dispersion
check("vol of constant series",
      rr.annualized_volatility([0.01] * 30, "daily").value, 0.0,
      method="(A) closed form")
# (B) sample stdev of [1,2,3,4,5] = sqrt(2.5) -- textbook value
check("stdev [1..5] sample", rr.stdev([1, 2, 3, 4, 5]), math.sqrt(2.5),
      method="(B) textbook sqrt(2.5)")
# (B) population stdev of [1,2,3,4,5] = sqrt(2)
check("stdev [1..5] population", rr.stdev([1, 2, 3, 4, 5], sample=False),
      math.sqrt(2.0), method="(B) textbook sqrt(2)")
# (C) annualization scales by sqrt(ppy)
_d = [0.01, -0.02, 0.015, -0.005, 0.02, -0.01, 0.003, 0.007]
_sd = rr.stdev(_d)
check("vol = stdev*sqrt(252)", rr.annualized_volatility(_d, "daily").value,
      _sd * math.sqrt(252), method="(C) scaling invariant")

# -------------------------------------------------------------------------
print("\n[risk-adjusted]")
# (C) Sharpe is scale-invariant in the sense that doubling every excess return
# doubles both mean and stdev -> ratio unchanged.
base = [0.01, -0.005, 0.02, 0.003, -0.01, 0.015, 0.007, -0.002]
s1 = rr.sharpe_ratio(base, 0.0, "daily").value
s2 = rr.sharpe_ratio([2 * x for x in base], 0.0, "daily").value
check("sharpe scale-invariant", s1, s2, tol=1e-9, method="(C) invariant")
# (D) zero volatility must raise, not divide by zero
check_raises("sharpe zero-vol raises",
             lambda: rr.sharpe_ratio([0.01] * 10), ZeroDivisionError)
# (C) Sortino >= Sharpe when downside is smaller than total dispersion
mixed = [0.02, 0.03, -0.005, 0.025, 0.01, -0.002, 0.018, 0.012]
sh = rr.sharpe_ratio(mixed, 0.0, "daily").value
so = rr.sortino_ratio(mixed, 0.0, "daily").value
check_true("sortino >= sharpe (mild downside)", so >= sh,
           "(C) invariant  sharpe=%.3f sortino=%.3f" % (sh, so))
# (B) PINS THE DIVISOR. returns [0.10,-0.05,0.10,-0.05], rf=0, target=0, ppy=1.
#     mean excess = 0.025; sum of squared downside = 0.005.
#     Sortino's definition divides by n=4 -> dd = sqrt(0.00125) = 0.0353553
#       -> ratio = 0.025/0.0353553 = 0.70710678...
#     The common BUG divides by the downside COUNT=2 -> dd = 0.05
#       -> ratio = 0.50 exactly.
#     These differ by 41%, so this test discriminates the two implementations.
#     Added after mutation testing showed the invariant test above did NOT
#     catch that bug.
check("sortino pins n-divisor",
      rr.sortino_ratio([0.10, -0.05, 0.10, -0.05], 0.0, "annual").value,
      0.7071067811865475, tol=1e-12,
      method="(B) hand: 0.025/sqrt(0.005/4); bug would give 0.500")

# -------------------------------------------------------------------------
print("\n[drawdown]")
# (B) 100 -> 50 is exactly -50%
check("max_drawdown 100->50",
      rr.max_drawdown([100, 120, 90, 50, 80]).value, -0.5833333333333334,
      tol=1e-12, method="(B) (50-120)/120")
# (A) monotonically rising equity has zero drawdown
check("max_drawdown monotonic",
      rr.max_drawdown([100, 101, 102, 103]).value, 0.0,
      method="(A) closed form")
# (B) simple 20% decline from peak
check("max_drawdown 20pct",
      rr.max_drawdown([100, 80, 100]).value, -0.2,
      tol=1e-12, method="(B) (80-100)/100")
# (D) non-positive equity must raise
check_raises("max_drawdown zero equity raises",
             lambda: rr.max_drawdown([100, 0, 50]), ValueError)

# -------------------------------------------------------------------------
print("\n[relative risk]")
a = [0.01, 0.02, -0.01, 0.03, -0.02, 0.015, 0.005, -0.005]
# (A) a series is perfectly correlated with itself
check("correlation self == 1", rr.correlation(a, a).value, 1.0, tol=1e-12,
      method="(A) closed form")
# (A) a series has beta 1 against itself
check("beta self == 1", rr.beta(a, a).value, 1.0, tol=1e-12,
      method="(A) closed form")
# (A) exact negation -> correlation -1
check("correlation negated == -1",
      rr.correlation(a, [-x for x in a]).value, -1.0, tol=1e-12,
      method="(A) closed form")
# (A) doubling the asset doubles beta
check("beta 2x == 2", rr.beta([2 * x for x in a], a).value, 2.0, tol=1e-12,
      method="(A) closed form")
# (A) tracking error against itself is zero
check("tracking_error self == 0", rr.tracking_error(a, a).value, 0.0,
      tol=1e-12, method="(A) closed form")
# (C) covariance of a series with itself == its sample variance
check("cov(a,a) == var(a)", rr.covariance(a, a).value, rr.stdev(a) ** 2,
      tol=1e-12, method="(C) invariant")
# (D) mismatched lengths must raise
check_raises("correlation length mismatch raises",
             lambda: rr.correlation(a, a[:-1]), ValueError)

# -------------------------------------------------------------------------
print("\n[tail risk]")
# (B) 100 sorted returns -0.50..0.49 step 0.01; 95% VaR takes index 5
tail = [(-50 + i) / 100.0 for i in range(100)]
var95 = rr.value_at_risk(tail, 0.95).value
check("VaR95 on ramp", var95, -0.45, tol=1e-12, method="(B) index 5 of ramp")
cvar95 = rr.conditional_value_at_risk(tail, 0.95).value
# (B) mean of the 5 worst: -0.50,-0.49,-0.48,-0.47,-0.46 = -0.48
check("CVaR95 on ramp", cvar95, -0.48, tol=1e-12, method="(B) mean of 5 worst")
# (C) THE defining property of expected shortfall
check_true("CVaR <= VaR", cvar95 <= var95,
           "(C) invariant  cvar=%.4f var=%.4f" % (cvar95, var95))
# (D) confidence outside (0,1) must raise
check_raises("VaR bad confidence raises",
             lambda: rr.value_at_risk(tail, 1.5), ValueError)

# -------------------------------------------------------------------------
print("\n[position sizing]  <-- safety-critical")
# (B) 10000 equity, 1% risk = $100 risk; entry 50 stop 45 -> $5/unit -> 20 units
ps = rr.position_size(10000, 0.01, 50, 45)
check("position_size 20 units", ps.value, 20.0, tol=1e-12,
      method="(B) (10000*0.01)/5")
# (C) halving risk_pct halves size
ps2 = rr.position_size(10000, 0.005, 50, 45)
check("position_size halves with risk", ps2.value, 10.0, tol=1e-12,
      method="(C) linear invariant")
# (B) SHORT position: stop ABOVE entry. Risk per unit is still 5, so size is
#     still 20 units. Without abs() this returns -20 units -- a sign-flipped
#     size that a caller could act on. Added after mutation testing showed
#     removing abs() went undetected.
ps_short = rr.position_size(10000, 0.01, 50, 55)
check("position_size short (stop above entry)", ps_short.value, 20.0, tol=1e-12,
      method="(B) (10000*0.01)/|50-55|; no-abs bug gives -20")
check_true("position_size never negative", ps_short.value > 0,
           "(C) size must be positive regardless of direction")
# (D) THE dangerous case: stop == entry implies infinite size. Must raise.
check_raises("position_size stop==entry raises",
             lambda: rr.position_size(10000, 0.01, 50, 50), ZeroDivisionError)
# (D) risk_pct given as 5 (meaning 5%) instead of 0.05 must be rejected
check_raises("position_size rejects pct>1",
             lambda: rr.position_size(10000, 5, 50, 45), ValueError)
# (D) negative equity must raise
check_raises("position_size negative equity raises",
             lambda: rr.position_size(-100, 0.01, 50, 45), ValueError)
# (B) entry 100, stop 95, target 115 -> reward 15 / risk 5 = 3.0
check("risk_reward 3:1", rr.risk_reward(100, 95, 115).value, 3.0, tol=1e-12,
      method="(B) 15/5")
# (B) SHORT trade: entry 100, stop 105, target 85. Reward 15, risk 5 -> 3.0.
#     Without abs() on reward this returns -3.0, making a good short look like
#     a losing trade. Same defect class as the position_size short case.
check("risk_reward short 3:1", rr.risk_reward(100, 105, 85).value, 3.0,
      tol=1e-12, method="(B) |85-100|/|100-105|; no-abs bug gives -3.0")

# -------------------------------------------------------------------------
print("\n[portfolio structure]")
# (A) single position -> HHI exactly 1
check("concentration single", rr.concentration([1.0]).value, 1.0,
      method="(A) closed form")
# (A) 4 equal weights -> HHI exactly 0.25
check("concentration 4 equal",
      rr.concentration([0.25, 0.25, 0.25, 0.25]).value, 0.25, tol=1e-12,
      method="(A) closed form 1/n")
# (B) leverage 150000 gross on 100000 equity = 1.5x
check("leverage 1.5x", rr.portfolio_leverage(150000, 100000).value, 1.5,
      tol=1e-12, method="(B) hand")
# (C) risk contributions must sum to portfolio volatility
w = [0.5, 0.3, 0.2]
cov = [[0.04, 0.01, 0.00],
       [0.01, 0.09, 0.02],
       [0.00, 0.02, 0.16]]
rc = rr.risk_contribution(w, cov)
port_var = sum(w[i] * cov[i][j] * w[j] for i in range(3) for j in range(3))
check("risk contributions sum to vol", sum(rc.value), math.sqrt(port_var),
      tol=1e-12, method="(C) Euler decomposition")

# -------------------------------------------------------------------------
print("\n[input validation]  <-- must refuse bad data, not guess")
check_raises("NaN in series raises",
             lambda: rr.annualized_volatility([0.01, float("nan"), 0.02]),
             ValueError)
check_raises("Inf in series raises",
             lambda: rr.annualized_volatility([0.01, float("inf"), 0.02]),
             ValueError)
check_raises("None in series raises",
             lambda: rr.annualized_volatility([0.01, None, 0.02]), ValueError)
check_raises("string in series raises",
             lambda: rr.annualized_volatility([0.01, "0.02", 0.03]), TypeError)
check_raises("too-short series raises",
             lambda: rr.annualized_volatility([0.01]), ValueError)
check_raises("zero start simple_return raises",
             lambda: rr.simple_return(0, 100), ZeroDivisionError)
check_raises("negative price log_return raises",
             lambda: rr.log_return(-10, 100), ValueError)
check_raises("unknown frequency raises",
             lambda: rr.annualized_volatility([0.01, 0.02], "fortnightly"),
             ValueError)
check_raises("return <= -100% raises",
             lambda: rr.annualized_return([-1.0, 0.5], "monthly"), ValueError)

# -------------------------------------------------------------------------
print("\n[provenance]  <-- SS.5.3 requires formula + inputs on every result")
r = rr.sharpe_ratio(base, 0.02, "daily")
check_true("result carries formula", bool(r.formula), "(C) %s" % r.formula)
check_true("result carries inputs", len(r.inputs) > 0, "(C) %d fields" % len(r.inputs))
check_true("result labelled COMPUTED", r.label == "COMPUTED", "(C) %s" % r.label)
# The annual->period risk-free conversion must actually have happened
check_true("annual rf de-annualized",
           r.inputs["period_risk_free"] < r.inputs["annual_risk_free"],
           "(C) %.8f < %.4f" % (r.inputs["period_risk_free"],
                                r.inputs["annual_risk_free"]))

print("\n" + "=" * 78)
print("RESULT: %d passed, %d failed" % (PASS, FAIL))
if FAILURES:
    print("Failed: %s" % ", ".join(FAILURES))
print("=" * 78)
sys.exit(1 if FAIL else 0)
