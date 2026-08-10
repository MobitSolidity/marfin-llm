#!/usr/bin/env python3
"""
Independent verification of src/calc/fixed_income.py (R14).

Method codes (A) closed form, (B) hand arithmetic, (C) invariant,
(D) must-raise -- see tests/_harness.py.

Fixed income has unusually strong closed-form anchors, and they are used
heavily here because they are impossible to satisfy by accident:

  - A bond priced at its coupon rate trades EXACTLY at par.
  - A zero-coupon bond's Macaulay duration EQUALS its maturity, exactly.
  - YTM and price are exact inverses; a round trip must return the input.

Run: python3 tests/test_fixed_income.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _harness import check, check_true, check_raises, section, summary  # noqa: E402

from calc import fixed_income as fi  # noqa: E402

print("=" * 78)
print("FIXED INCOME -- INDEPENDENT VERIFICATION")
print("=" * 78)

# -------------------------------------------------------------------------
section("cash-flow schedule")

sch = fi.cash_flow_schedule(1000, 0.06, 3, 2).value
check("schedule period count", len(sch), 6.0, tol=0, method="(B) 3y x 2")
check("schedule coupon amount", sch[0]["coupon"], 30.0, tol=1e-12,
      method="(B) 1000*0.06/2")
check("schedule no early principal", sch[0]["principal"], 0.0, tol=1e-12,
      method="(B)")
check("schedule repays principal at maturity", sch[-1]["principal"], 1000.0,
      tol=1e-12, method="(B)")
check("schedule final total", sch[-1]["total"], 1030.0, tol=1e-12,
      method="(B) 30 + 1000")
# (B) Total undiscounted = 6 coupons of 30 + 1000 = 1180
check("schedule total undiscounted",
      fi.cash_flow_schedule(1000, 0.06, 3, 2).inputs["total_undiscounted"],
      1180.0, tol=1e-12, method="(B)")
# (C) Time in years must reach exactly the maturity.
check("schedule final time in years", sch[-1]["time_years"], 3.0, tol=1e-12,
      method="(C)")
# (D) A maturity off a coupon boundary would silently drop or add a coupon.
check_raises("schedule refuses partial period",
             lambda: fi.cash_flow_schedule(1000, 0.06, 3.3, 2), ValueError)
check_raises("schedule refuses zero face",
             lambda: fi.cash_flow_schedule(0, 0.06, 3, 2), ValueError)
check_raises("schedule refuses percentage coupon",
             lambda: fi.cash_flow_schedule(1000, 6.0, 3, 2), ValueError)
check_raises("schedule refuses frequency 0",
             lambda: fi.cash_flow_schedule(1000, 0.06, 3, 0), ValueError)

# -------------------------------------------------------------------------
section("bond price")

# (A) THE anchor: yield == coupon -> price is exactly par. No implementation
#     can satisfy this by coincidence.
check("par bond prices at par", fi.bond_price(1000, 0.05, 0.05, 10, 2).value,
      1000.0, tol=1e-9, method="(A) ytm == coupon")
check("par bond annual freq", fi.bond_price(1000, 0.07, 0.07, 5, 1).value,
      1000.0, tol=1e-9, method="(A)")
# (C) Below-coupon yield -> premium; above-coupon yield -> discount.
check_true("discount when ytm > coupon",
           fi.bond_price(1000, 0.05, 0.08, 10, 2).value < 1000.0, "(C)")
check_true("premium when ytm < coupon",
           fi.bond_price(1000, 0.05, 0.03, 10, 2).value > 1000.0, "(C)")
# (A) Zero-coupon: price = 1000/1.05^10 with annual compounding.
check("zero coupon price closed form",
      fi.bond_price(1000, 0.0, 0.05, 10, 1).value,
      1000.0 / (1.05 ** 10), tol=1e-9, method="(A)")
# (A) Zero yield -> price is the undiscounted sum of cash flows.
check("zero yield sums cash flows",
      fi.bond_price(1000, 0.06, 0.0, 3, 2).value, 1180.0, tol=1e-9,
      method="(A) 6x30 + 1000")
# (C) Longer maturity at a discount must price lower.
check_true("longer discount bond prices lower",
           fi.bond_price(1000, 0.03, 0.06, 20, 2).value <
           fi.bond_price(1000, 0.03, 0.06, 5, 2).value, "(C)")
check_raises("bond_price refuses partial period",
             lambda: fi.bond_price(1000, 0.05, 0.05, 3.3, 2), ValueError)

# -------------------------------------------------------------------------
section("accrued interest and clean/dirty")

# (B) Half a semiannual period on a 6% 1000 bond: coupon 30, half = 15.
check("accrued half period", fi.accrued_interest(1000, 0.06, 90, 180, 2).value,
      15.0, tol=1e-12, method="(B) 30 * 90/180")
# (A) Zero days accrued -> exactly zero.
check("accrued zero days", fi.accrued_interest(1000, 0.06, 0, 180, 2).value,
      0.0, tol=1e-12, method="(A)")
# (A) Full period accrued -> the whole coupon.
check("accrued full period",
      fi.accrued_interest(1000, 0.06, 180, 180, 2).value, 30.0, tol=1e-12,
      method="(A)")
check("dirty_price adds accrued", fi.dirty_price(980.0, 15.0).value, 995.0,
      tol=1e-12, method="(B)")
check("clean_price subtracts accrued", fi.clean_price(995.0, 15.0).value,
      980.0, tol=1e-12, method="(B)")
# (C) Round trip must be exact -- these are inverses.
check("clean/dirty round trip",
      fi.clean_price(fi.dirty_price(980.0, 15.0).value, 15.0).value,
      980.0, tol=1e-12, method="(C) inverse")
# (D) Accruing past a coupon date means a coupon was missed.
check_raises("accrued refuses days > period",
             lambda: fi.accrued_interest(1000, 0.06, 200, 180, 2), ValueError)
check_raises("accrued refuses negative days",
             lambda: fi.accrued_interest(1000, 0.06, -5, 180, 2), ValueError)
check_raises("accrued refuses unknown day count",
             lambda: fi.accrued_interest(1000, 0.06, 90, 180, 2, "lunar"),
             ValueError)
check_raises("clean_price refuses accrued > dirty",
             lambda: fi.clean_price(10.0, 50.0), ValueError)
check_true("accrued echoes day count",
           fi.accrued_interest(1000, 0.06, 90, 180, 2,
                               "actual/365").inputs["day_count"]
           == "actual/365", "(C)")

# -------------------------------------------------------------------------
section("yield to maturity")

# (A) A bond priced at par yields exactly its coupon.
check("par price implies coupon yield",
      fi.yield_to_maturity(1000, 1000, 0.05, 10, 2).value, 0.05, tol=1e-9,
      method="(A)")
# (C) THE strongest test in this file: price -> yield -> price must round
#     trip. It cannot be satisfied unless BOTH functions are correct.
p = fi.bond_price(1000, 0.05, 0.0731, 7, 2).value
y = fi.yield_to_maturity(p, 1000, 0.05, 7, 2).value
check("ytm round trip recovers yield", y, 0.0731, tol=1e-9,
      method="(C) price -> ytm -> price")
check("ytm round trip recovers price",
      fi.bond_price(1000, 0.05, y, 7, 2).value, p, tol=1e-7, method="(C)")
# (C) Discount price -> yield above coupon.
check_true("discount implies yield > coupon",
           fi.yield_to_maturity(900, 1000, 0.05, 10, 2).value > 0.05, "(C)")
check_true("premium implies yield < coupon",
           fi.yield_to_maturity(1100, 1000, 0.05, 10, 2).value < 0.05, "(C)")
# (A) Zero-coupon round trip: price 1000/1.05^10, yield must be 5%.
zp = 1000.0 / (1.05 ** 10)
check("zero coupon ytm", fi.yield_to_maturity(zp, 1000, 0.0, 10, 1).value,
      0.05, tol=1e-9, method="(A)")
check_raises("ytm refuses zero price",
             lambda: fi.yield_to_maturity(0, 1000, 0.05, 10, 2), ValueError)
# (D) A price 1,000,000x the face value IS mathematically solvable (it implies
#     a yield near -99.5%). Bisection alone would return that number with full
#     confidence. The plausibility gate must refuse it: such a price is an
#     input error, and reporting a yield would launder it into a result.
check_raises("ytm refuses implausible negative yield",
             lambda: fi.yield_to_maturity(1e9, 1000, 0.05, 10, 2), ValueError)
# (C) A mildly negative yield is real and must still compute -- the gate must
#     not over-reach. Sovereign bonds have genuinely traded below zero.
neg_price = fi.bond_price(1000, 0.0, -0.004, 5, 1).value
check_true("ytm allows genuine small negative yield",
           fi.yield_to_maturity(neg_price, 1000, 0.0, 5, 1).value < 0,
           "(C) real negative-yield bonds exist")
check_raises("ytc refuses implausible negative yield",
             lambda: fi.yield_to_call(1e9, 1000, 0.05, 5, 1000, 2), ValueError)

# -------------------------------------------------------------------------
section("yield to call")

# (A) Called at par on a coupon date, priced at par -> YTC == coupon.
check("ytc at par equals coupon",
      fi.yield_to_call(1000, 1000, 0.05, 5, 1000, 2).value, 0.05, tol=1e-9,
      method="(A)")
# (C) A premium call price must raise the yield relative to a par call.
check_true("higher call price raises ytc",
           fi.yield_to_call(1000, 1000, 0.05, 5, 1050, 2).value >
           fi.yield_to_call(1000, 1000, 0.05, 5, 1000, 2).value, "(C)")
# (C) For a bond above par callable at par, YTC < YTM -- the reason
#     yield-to-worst exists.
price_above_par = 1100.0
ytm = fi.yield_to_maturity(price_above_par, 1000, 0.06, 10, 2).value
ytc = fi.yield_to_call(price_above_par, 1000, 0.06, 2, 1000, 2).value
check_true("ytc < ytm for premium callable", ytc < ytm,
           "(C) %.5f < %.5f" % (ytc, ytc if ytc > ytm else ytm))
check_raises("ytc refuses zero call price",
             lambda: fi.yield_to_call(1000, 1000, 0.05, 5, 0, 2), ValueError)

# -------------------------------------------------------------------------
section("duration")

# (A) THE zero-coupon anchor: Macaulay duration EQUALS maturity exactly.
check("zero coupon macaulay == maturity",
      fi.macaulay_duration(1000, 0.0, 0.05, 10, 1).value, 10.0, tol=1e-9,
      method="(A)")
check("zero coupon macaulay semiannual",
      fi.macaulay_duration(1000, 0.0, 0.05, 7, 2).value, 7.0, tol=1e-9,
      method="(A)")
# (C) A coupon bond's duration is strictly LESS than its maturity, because
#     cash arrives earlier.
check_true("coupon bond duration < maturity",
           fi.macaulay_duration(1000, 0.05, 0.05, 10, 2).value < 10.0, "(C)")
# (C) Modified duration is strictly below Macaulay (divides by 1 + y/f).
mac = fi.macaulay_duration(1000, 0.05, 0.05, 10, 2).value
mod = fi.modified_duration(1000, 0.05, 0.05, 10, 2).value
check_true("modified < macaulay", mod < mac, "(C) %.6f < %.6f" % (mod, mac))
# (B) The exact relationship: mod = mac / (1 + y/f)
check("modified duration relationship", mod, mac / (1 + 0.05 / 2), tol=1e-12,
      method="(B) mac/(1+y/f)")
# (C) Duration must be reported POSITIVE (sign lives in the formula).
check_true("modified duration positive", mod > 0, "(C)")
# (C) A higher coupon shortens duration; a longer maturity lengthens it.
check_true("higher coupon shortens duration",
           fi.macaulay_duration(1000, 0.10, 0.05, 10, 2).value <
           fi.macaulay_duration(1000, 0.02, 0.05, 10, 2).value, "(C)")
check_true("longer maturity lengthens duration",
           fi.macaulay_duration(1000, 0.05, 0.05, 20, 2).value >
           fi.macaulay_duration(1000, 0.05, 0.05, 5, 2).value, "(C)")

# -------------------------------------------------------------------------
section("convexity")

# (C) Convexity is positive for an option-free bond.
cx = fi.convexity(1000, 0.05, 0.05, 10, 2).value
check_true("convexity positive", cx > 0, "(C) %.4f" % cx)
# (C) Longer bonds are more convex.
check_true("longer maturity more convex",
           fi.convexity(1000, 0.05, 0.05, 20, 2).value > cx, "(C)")
# (C) Zero-coupon convexity exceeds a same-maturity coupon bond's.
check_true("zero coupon more convex than coupon bond",
           fi.convexity(1000, 0.0, 0.05, 10, 1).value >
           fi.convexity(1000, 0.10, 0.05, 10, 1).value, "(C)")

# (A) ABSOLUTE ANCHOR -- added after mutation testing.
# The comparisons above are all RELATIVE, so they survived a mutation that
# dropped the f^2 scaling: every convexity was wrong by the same factor and
# the orderings still held. A zero-coupon bond has the closed form
#     convexity = n(n+1) / (f^2 (1 + y/f)^2)   [years^2]
# which pins the absolute magnitude and the frequency scaling together.
# 10y zero, semiannual: n=20, f=2, y=5% -> 20*21/(4*1.025^2) = 99.9405
check("zero coupon convexity closed form (semiannual)",
      fi.convexity(1000, 0.0, 0.05, 10, 2).value, 99.94051160023795,
      tol=1e-9, method="(A) n(n+1)/(f^2 (1+y/f)^2)")
# Annual: n=10, f=1 -> 10*11/1.05^2 = 99.7732. Different f, so a missing or
# wrong f^2 term cannot satisfy both.
check("zero coupon convexity closed form (annual)",
      fi.convexity(1000, 0.0, 0.05, 10, 1).value, 99.77324263038548,
      tol=1e-9, method="(A) n(n+1)/(1+y)^2")
# (C) Convexity is in years^2, so it must be dimensionally consistent across
#     frequencies: the same 10-year zero gives nearly the same value whether
#     quoted annually or semiannually. Dropping f^2 breaks this by ~4x.
check_true("convexity consistent across frequency",
           abs(fi.convexity(1000, 0.0, 0.05, 10, 2).value -
               fi.convexity(1000, 0.0, 0.05, 10, 1).value) < 1.0,
           "(C) years^2 is frequency-independent")

# -------------------------------------------------------------------------
section("DV01")

# (C) DV01 must be POSITIVE (a magnitude) and small relative to price.
d = fi.dv01(1000, 0.05, 0.05, 10, 2)
check_true("dv01 positive magnitude", d.value > 0, "(C) %.6f" % d.value)
check_true("dv01 small vs price", d.value < 5.0, "(C) %.6f" % d.value)
# (C) DV01 must approximate ModDur x price x 0.0001 -- two independent routes
#     to the same quantity. Agreement to 0.1% validates BOTH.
approx = mod * 1000.0 * 0.0001
check("dv01 matches duration approximation", d.value, approx,
      tol=abs(approx) * 1e-3, method="(C) ModDur x P x 1bp")
# (C) Longer duration -> larger DV01.
check_true("longer bond has larger dv01",
           fi.dv01(1000, 0.05, 0.05, 30, 2).value > d.value, "(C)")
# (C) Full-revaluation method must be recorded (not the approximation).
check_true("dv01 records full revaluation",
           "revaluation" in str(d.inputs.get("method", "")), "(C)")

# -------------------------------------------------------------------------
section("provenance and disclosure")

r = fi.yield_to_maturity(950, 1000, 0.05, 10, 2)
check_true("result carries formula", bool(r.formula), "(C)")
check_true("result carries inputs", len(r.inputs) >= 4, "(C)")
check_true("result labelled COMPUTED", r.label == "COMPUTED", "(C)")
check_true("ytm discloses reinvestment assumption",
           "reinvest" in r.notes.lower(), "(C)")
check_true("bond_price flags clean vs dirty",
           "clean" in fi.bond_price(1000, 0.05, 0.05, 10, 2).notes.lower(),
           "(C)")
check_true("modified duration discloses sign convention",
           "-" in fi.modified_duration(1000, 0.05, 0.05, 10, 2).notes, "(C)")

sys.exit(summary())
