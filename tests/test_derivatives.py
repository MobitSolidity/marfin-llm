#!/usr/bin/env python3
"""
Independent verification of src/calc/derivatives.py (R14).

Method codes (A) closed form, (B) hand arithmetic, (C) invariant,
(D) must-raise -- see tests/_harness.py.

Options pricing is the hardest family to test without re-running the formula,
so this suite leans on relationships that are TRUE OF THE MARKET rather than
of any implementation:

  - PUT-CALL PARITY: C - P = S e^-qT - K e^-rT. Holds exactly, always. If
    either the call or the put is wrong, parity breaks.
  - BINOMIAL -> BLACK-SCHOLES: two completely different algorithms must
    converge. Agreement cross-validates BOTH.
  - GREEKS vs FINITE DIFFERENCE: each analytic Greek is checked against a
    numerical bump of the price function. This catches a wrong closed form
    that is nonetheless internally consistent.
  - IV ROUND TRIP: price -> IV -> price must return the input.

Run: python3 tests/test_derivatives.py
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _harness import check, check_true, check_raises, section, summary  # noqa: E402

from calc import derivatives as d  # noqa: E402

print("=" * 78)
print("DERIVATIVES -- INDEPENDENT VERIFICATION")
print("=" * 78)

S, K, T, VOL, R, Q = 100.0, 100.0, 1.0, 0.20, 0.05, 0.0

# -------------------------------------------------------------------------
section("Black-Scholes")

# (B) The canonical textbook case: S=K=100, T=1, sigma=20%, r=5%, q=0.
#     Call = 10.4506; put = 5.5735. These are published reference values.
check("BS call textbook value",
      d.black_scholes(S, K, T, VOL, R, "call").value, 10.450583572185565,
      tol=1e-9, method="(B) published reference")
check("BS put textbook value",
      d.black_scholes(S, K, T, VOL, R, "put").value, 5.573526022256971,
      tol=1e-9, method="(B) published reference")

# (C) PUT-CALL PARITY -- the strongest structural test available.
c = d.black_scholes(S, K, T, VOL, R, "call").value
p = d.black_scholes(S, K, T, VOL, R, "put").value
parity = S * math.exp(-Q * T) - K * math.exp(-R * T)
check("put-call parity holds", c - p, parity, tol=1e-9,
      method="(C) C - P == S e^-qT - K e^-rT")
# (C) Parity must also hold with a dividend yield.
c2 = d.black_scholes(S, K, T, VOL, R, "call", 0.03).value
p2 = d.black_scholes(S, K, T, VOL, R, "put", 0.03).value
check("put-call parity with dividend", c2 - p2,
      S * math.exp(-0.03 * T) - K * math.exp(-R * T), tol=1e-9, method="(C)")

# (C) Deep in-the-money call approaches its discounted intrinsic value.
deep = d.black_scholes(200.0, 100.0, 1.0, 0.01, 0.0, "call").value
check("deep ITM call ~ intrinsic", deep, 100.0, tol=1e-6,
      method="(C) S-K at ~zero vol")
# (C) Deep out-of-the-money call is worth ~0.
check_true("deep OTM call ~ 0",
           d.black_scholes(50.0, 200.0, 0.1, 0.10, 0.0, "call").value < 1e-6,
           "(C)")
# (C) Monotonicity: price rises with volatility and with time.
check_true("call rises with volatility",
           d.black_scholes(S, K, T, 0.40, R).value >
           d.black_scholes(S, K, T, 0.20, R).value, "(C)")
check_true("call rises with time to expiry",
           d.black_scholes(S, K, 2.0, VOL, R).value >
           d.black_scholes(S, K, 0.5, VOL, R).value, "(C)")
# (C) Dividends reduce a call and increase a put.
check_true("dividend reduces call value", c2 < c, "(C)")
check_true("dividend increases put value", p2 > p, "(C)")

# (D) Degenerate inputs must be refused, not silently reduced to intrinsic.
check_raises("BS refuses zero time",
             lambda: d.black_scholes(S, K, 0.0, VOL, R), ValueError)
check_raises("BS refuses zero volatility",
             lambda: d.black_scholes(S, K, T, 0.0, R), ValueError)
check_raises("BS refuses negative spot",
             lambda: d.black_scholes(-100, K, T, VOL, R), ValueError)
check_raises("BS refuses bad option type",
             lambda: d.black_scholes(S, K, T, VOL, R, "straddle"), ValueError)
# (D) Volatility as a percentage (20 instead of 0.20) is a 100x error.
check_raises("BS refuses percentage volatility",
             lambda: d.black_scholes(S, K, T, 20.0, R), ValueError)
# (D) Time in days instead of years.
check_raises("BS refuses implausible time",
             lambda: d.black_scholes(S, K, 365.0, VOL, R), ValueError)

# -------------------------------------------------------------------------
section("Black-76")

# (C) Parity for futures options: C - P = e^-rT (F - K).
fc = d.black_76(100.0, 95.0, 1.0, 0.25, 0.05, "call").value
fp = d.black_76(100.0, 95.0, 1.0, 0.25, 0.05, "put").value
check("black-76 parity", fc - fp, math.exp(-0.05) * (100.0 - 95.0),
      tol=1e-9, method="(C) e^-rT (F - K)")
# (C) With F = S e^(r-q)T, Black-76 must equal Black-Scholes exactly. This is
#     a genuine cross-model identity, not a re-run of the same code path.
fwd = S * math.exp((R - Q) * T)
check("black-76 equals BS at the forward",
      d.black_76(fwd, K, T, VOL, R, "call").value,
      d.black_scholes(S, K, T, VOL, R, "call", Q).value, tol=1e-9,
      method="(C) F = S e^(r-q)T")
# (C) At-the-money-forward, call and put are equal.
check("black-76 ATM-forward call == put",
      d.black_76(100.0, 100.0, 1.0, 0.25, 0.05, "call").value,
      d.black_76(100.0, 100.0, 1.0, 0.25, 0.05, "put").value, tol=1e-12,
      method="(C)")

# -------------------------------------------------------------------------
section("binomial tree")

# (C) THE cross-validation: an entirely different algorithm (discrete tree)
#     must converge to the closed-form Black-Scholes value.
bs_call = d.black_scholes(S, K, T, VOL, R, "call").value
bin_call = d.binomial_price(S, K, T, VOL, R, "call", steps=2000).value
check("binomial converges to Black-Scholes", bin_call, bs_call, tol=0.01,
      method="(C) 2000 steps, independent algorithm")
bs_put = d.black_scholes(S, K, T, VOL, R, "put").value
check("binomial put converges to BS",
      d.binomial_price(S, K, T, VOL, R, "put", steps=2000).value, bs_put,
      tol=0.01, method="(C)")
# (C) Convergence must IMPROVE with more steps.
e50 = abs(d.binomial_price(S, K, T, VOL, R, "call", steps=50).value - bs_call)
e500 = abs(d.binomial_price(S, K, T, VOL, R, "call", steps=500).value
           - bs_call)
check_true("binomial error shrinks with steps", e500 < e50,
           "(C) %.5f < %.5f" % (e500, e50))
# (C) An American option is worth AT LEAST its European equivalent -- early
#     exercise is a right, never an obligation.
am_put = d.binomial_price(S, K, T, VOL, R, "put", steps=500,
                          american=True).value
eu_put = d.binomial_price(S, K, T, VOL, R, "put", steps=500,
                          american=False).value
check_true("american put >= european put", am_put >= eu_put - 1e-12,
           "(C) %.6f >= %.6f" % (am_put, eu_put))
# (C) For a NON-dividend-paying stock, early exercise of a CALL is never
#     optimal, so American == European exactly. A tree that wrongly allows
#     profitable early call exercise fails here.
am_call = d.binomial_price(S, K, T, VOL, R, "call", steps=300,
                           american=True).value
eu_call = d.binomial_price(S, K, T, VOL, R, "call", steps=300,
                           american=False).value
check("american call == european (no dividend)", am_call, eu_call, tol=1e-9,
      method="(C) early exercise never optimal")
check_raises("binomial refuses zero steps",
             lambda: d.binomial_price(S, K, T, VOL, R, "call", steps=0),
             ValueError)
check_raises("binomial refuses excessive steps",
             lambda: d.binomial_price(S, K, T, VOL, R, "call", steps=99999),
             ValueError)

# -------------------------------------------------------------------------
section("implied volatility")

# (C) ROUND TRIP: price at a known vol, recover that vol exactly.
target = d.black_scholes(S, K, T, 0.2735, R, "call").value
iv = d.implied_volatility(target, S, K, T, R, "call").value
check("iv round trip recovers volatility", iv, 0.2735, tol=1e-8,
      method="(C) price -> IV -> price")
# (C) Round trip for a put, away from the money.
tp = d.black_scholes(90.0, 100.0, 0.5, 0.4123, R, "put").value
check("iv round trip put OTM",
      d.implied_volatility(tp, 90.0, 100.0, 0.5, R, "put").value, 0.4123,
      tol=1e-8, method="(C)")
# (C) With a dividend yield.
td = d.black_scholes(S, K, T, 0.31, R, "call", 0.02).value
check("iv round trip with dividend",
      d.implied_volatility(td, S, K, T, R, "call", 0.02).value, 0.31,
      tol=1e-8, method="(C)")
# (D) Arbitrage bounds: a price below intrinsic has NO implied vol. Returning
#     one would be fabricating a market-consistent number from an impossible
#     quote.
check_raises("iv refuses price below intrinsic",
             lambda: d.implied_volatility(0.01, 200.0, 100.0, 1.0, 0.0,
                                          "call"), ValueError)
check_raises("iv refuses price above spot",
             lambda: d.implied_volatility(150.0, 100.0, 100.0, 1.0, 0.0,
                                          "call"), ValueError)
check_raises("iv refuses zero price",
             lambda: d.implied_volatility(0.0, S, K, T, R), ValueError)

# -------------------------------------------------------------------------
section("Greeks -- checked against finite differences")


def fd(fn_price, arg_index, args, h):
    """Central finite difference of the price function."""
    up = list(args)
    dn = list(args)
    up[arg_index] += h
    dn[arg_index] -= h
    return (fn_price(*up) - fn_price(*dn)) / (2 * h)


def bs_price(s, k, t, v, r, kind, q):
    return d.black_scholes(s, k, t, v, r, kind, q).value


# (C) DELTA vs dPrice/dSpot
an_delta = d.delta(S, K, T, VOL, R, "call").value
num_delta = fd(bs_price, 0, [S, K, T, VOL, R, "call", Q], 0.001)
check("call delta matches finite difference", an_delta, num_delta, tol=1e-6,
      method="(C) dP/dS")
an_dput = d.delta(S, K, T, VOL, R, "put").value
num_dput = fd(bs_price, 0, [S, K, T, VOL, R, "put", Q], 0.001)
check("put delta matches finite difference", an_dput, num_dput, tol=1e-6,
      method="(C)")
# (C) Delta bounds and the parity relationship C_delta - P_delta = e^-qT.
check_true("call delta in (0,1)", 0.0 < an_delta < 1.0,
           "(C) %.6f" % an_delta)
check_true("put delta in (-1,0)", -1.0 < an_dput < 0.0,
           "(C) %.6f" % an_dput)
check("delta parity", an_delta - an_dput, math.exp(-Q * T), tol=1e-9,
      method="(C) C_d - P_d == e^-qT")

# (C) DIVIDEND DISCOUNT ON DELTA -- added after mutation testing.
# Every delta test above uses q = 0, where e^-qT == 1, so a mutation that
# dropped the dividend discount entirely SURVIVED. Re-check delta against a
# finite difference with a NON-ZERO dividend yield, where the factor bites.
QD = 0.05
an_dq = d.delta(S, K, T, VOL, R, "call", QD).value
num_dq = fd(bs_price, 0, [S, K, T, VOL, R, "call", QD], 0.001)
check("call delta with dividend matches FD", an_dq, num_dq, tol=1e-6,
      method="(C) dP/dS at q=5%")
# (C) A dividend yield must REDUCE call delta; equality would mean the
#     discount factor is missing.
check_true("dividend reduces call delta", an_dq < an_delta,
           "(C) %.6f < %.6f" % (an_dq, an_delta))
# (C) Delta parity must still hold with dividends: C_d - P_d == e^-qT.
check("delta parity with dividend",
      an_dq - d.delta(S, K, T, VOL, R, "put", QD).value,
      math.exp(-QD * T), tol=1e-9, method="(C)")

# (C) GAMMA vs d2Price/dSpot2 (second central difference)
h = 0.01
g_num = (bs_price(S + h, K, T, VOL, R, "call", Q)
         - 2 * bs_price(S, K, T, VOL, R, "call", Q)
         + bs_price(S - h, K, T, VOL, R, "call", Q)) / (h * h)
check("gamma matches second difference", d.gamma(S, K, T, VOL, R).value,
      g_num, tol=1e-5, method="(C) d2P/dS2")
check_true("gamma positive", d.gamma(S, K, T, VOL, R).value > 0, "(C)")

# (C) VEGA vs dPrice/dVol
an_vega = d.vega(S, K, T, VOL, R).value
num_vega = fd(bs_price, 3, [S, K, T, VOL, R, "call", Q], 1e-5)
check("vega matches finite difference", an_vega, num_vega, tol=1e-4,
      method="(C) dP/dsigma")
check_true("vega positive", an_vega > 0, "(C)")
# (C) Vega is identical for calls and puts (parity has no vol term).
vp_num = fd(bs_price, 3, [S, K, T, VOL, R, "put", Q], 1e-5)
check("vega same for call and put", an_vega, vp_num, tol=1e-4, method="(C)")

# (C) VEGA AT T != 1 -- added after mutation testing.
# The check above uses T = 1.0, where sqrt(T) == T == 1, so a mutation
# replacing sqrt(T) with T SURVIVED. Re-check at T = 4, where sqrt(4) = 2 but
# T = 4 -- a 2x divergence.
T4 = 4.0
an_v4 = d.vega(S, K, T4, VOL, R).value
num_v4 = fd(bs_price, 3, [S, K, T4, VOL, R, "call", Q], 1e-5)
check("vega at T=4 matches FD", an_v4, num_v4, tol=1e-3,
      method="(C) sqrt(T) != T here")
# (C) Same trap on the short side: T = 0.25 -> sqrt = 0.5, a 2x divergence
#     the other way.
an_v025 = d.vega(S, K, 0.25, VOL, R).value
num_v025 = fd(bs_price, 3, [S, K, 0.25, VOL, R, "call", Q], 1e-5)
check("vega at T=0.25 matches FD", an_v025, num_v025, tol=1e-3, method="(C)")
# (C) Vega must scale with sqrt(T), not T: quadrupling time roughly doubles
#     vega (exactly so at the money, absent rate effects).
check_true("vega scales sub-linearly in time", an_v4 < 4.0 * an_vega,
           "(C) %.4f < %.4f" % (an_v4, 4.0 * an_vega))

# (C) THETA vs -dPrice/dTime. Price rises with T, so theta is its negative.
an_theta = d.theta(S, K, T, VOL, R, "call").value
num_dpdt = fd(bs_price, 2, [S, K, T, VOL, R, "call", Q], 1e-5)
check("call theta matches -dP/dT", an_theta, -num_dpdt, tol=1e-4,
      method="(C)")
check_true("long call theta negative", an_theta < 0, "(C) %.6f" % an_theta)
# (C) The per-day figure must be the annual figure / 365. Getting this wrong
#     overstates decay by ~365x.
th = d.theta(S, K, T, VOL, R, "call")
check("theta per_day is annual/365", th.inputs["per_day"],
      th.value / 365.0, tol=1e-12, method="(C)")

# (C) RHO vs dPrice/dRate
an_rho = d.rho(S, K, T, VOL, R, "call").value
num_rho = fd(bs_price, 4, [S, K, T, VOL, R, "call", Q], 1e-6)
check("call rho matches finite difference", an_rho, num_rho, tol=1e-4,
      method="(C) dP/dr")
check_true("call rho positive", an_rho > 0, "(C)")
check_true("put rho negative", d.rho(S, K, T, VOL, R, "put").value < 0, "(C)")

# (D) Greeks inherit the same input guards.
check_raises("delta refuses zero time",
             lambda: d.delta(S, K, 0.0, VOL, R), ValueError)
check_raises("gamma refuses zero volatility",
             lambda: d.gamma(S, K, T, 0.0, R), ValueError)

# -------------------------------------------------------------------------
section("payoff and breakeven")

# (B) Long call, K=100, premium 5, expiry at 120, 1 contract x 100:
#     intrinsic 20 -> payoff 2000, premium -500, profit 1500.
r1 = d.contract_payoff(120, 100, 5, "call", "long", 1, 100).value
check("long call payoff", r1["payoff"], 2000.0, tol=1e-9, method="(B)")
check("long call profit net of premium", r1["profit"], 1500.0, tol=1e-9,
      method="(B) 2000 - 500")
# (B) Expiring worthless: payoff 0, loss is the premium.
r2 = d.contract_payoff(90, 100, 5, "call", "long", 1, 100).value
check("OTM call payoff zero", r2["payoff"], 0.0, tol=1e-12, method="(B)")
check("OTM call loses premium", r2["profit"], -500.0, tol=1e-9, method="(B)")
# (C) The short side is the exact mirror of the long side.
r3 = d.contract_payoff(120, 100, 5, "call", "short", 1, 100).value
check("short is mirror of long", r3["profit"], -r1["profit"], tol=1e-9,
      method="(C)")
# (B) Long put in the money: K=100, S=80 -> intrinsic 20.
r4 = d.contract_payoff(80, 100, 3, "put", "long", 2, 100).value
check("long put payoff 2 contracts", r4["payoff"], 4000.0, tol=1e-9,
      method="(B) 20 x 2 x 100")
check("long put profit", r4["profit"], 3400.0, tol=1e-9,
      method="(B) 4000 - 600")
# (C) Unbounded short-call risk must be disclosed, not implied bounded.
note = d.contract_payoff(120, 100, 5, "call", "short").notes.upper()
check_true("short call discloses unbounded loss", "UNBOUNDED" in note, "(C)")

check("call breakeven", d.breakeven(100, 5, "call").value, 105.0, tol=1e-12,
      method="(B) K + premium")
check("put breakeven", d.breakeven(100, 5, "put").value, 95.0, tol=1e-12,
      method="(B) K - premium")
# (C) At breakeven, profit must be exactly zero -- ties the two functions
#     together.
be = d.breakeven(100, 5, "call").value
check("profit at breakeven is zero",
      d.contract_payoff(be, 100, 5, "call", "long", 1, 100).value["profit"],
      0.0, tol=1e-9, method="(C)")
check_raises("payoff refuses negative premium",
             lambda: d.contract_payoff(120, 100, -5, "call"), ValueError)
check_raises("payoff refuses bad position",
             lambda: d.contract_payoff(120, 100, 5, "call", "sideways"),
             ValueError)
check_raises("breakeven refuses premium > strike for put",
             lambda: d.breakeven(10, 50, "put"), ValueError)

# -------------------------------------------------------------------------
section("margin and liquidation -- must be labelled ESTIMATED")

m = d.margin_estimate(10000, 2, 0.25)
check("initial margin", m.value["initial_margin"], 5000.0, tol=1e-9,
      method="(B) 10000/2")
check("maintenance margin", m.value["maintenance_margin"], 2500.0, tol=1e-9,
      method="(B) 10000*0.25")
# (C) SS.2 label discipline: a generic estimate must never claim COMPUTED.
check_true("margin labelled ESTIMATED", m.label == "ESTIMATED",
           "(C) %s" % m.label)
check_true("margin notes say confirm with broker",
           "broker" in m.notes.lower(), "(C)")
# (D) Maintenance above initial means instant liquidation -- refuse it.
check_raises("margin refuses maintenance > initial",
             lambda: d.margin_estimate(10000, 5, 0.25), ValueError)
check_raises("margin refuses leverage < 1",
             lambda: d.margin_estimate(10000, 0.5), ValueError)

# (B) Long at 100, 5x, mmr 0.5% -> 100 * (1 - 0.2 + 0.005) = 80.5
liq = d.liquidation_estimate(100, 5, 0.005, "long")
check("long liquidation price", liq.value, 80.5, tol=1e-9, method="(B)")
check("short liquidation price",
      d.liquidation_estimate(100, 5, 0.005, "short").value, 119.5, tol=1e-9,
      method="(B) 100*(1 + 0.2 - 0.005)")
check_true("liquidation labelled ESTIMATED", liq.label == "ESTIMATED",
           "(C) %s" % liq.label)
# (C) Higher leverage moves liquidation CLOSER to entry.
check_true("higher leverage liquidates sooner",
           d.liquidation_estimate(100, 20, 0.005, "long").value >
           d.liquidation_estimate(100, 5, 0.005, "long").value, "(C)")
# (C) Long liquidation must be below entry; short must be above.
check_true("long liquidation below entry", liq.value < 100.0, "(C)")
check_true("short liquidation above entry",
           d.liquidation_estimate(100, 5, 0.005, "short").value > 100.0,
           "(C)")
check_true("liquidation discloses fees move trigger closer",
           "closer" in liq.notes.lower(), "(C)")
# (D) Unleveraged spot cannot be liquidated.
check_raises("liquidation refuses leverage 1.0",
             lambda: d.liquidation_estimate(100, 1.0), ValueError)
check_raises("liquidation refuses bad side",
             lambda: d.liquidation_estimate(100, 5, 0.005, "flat"),
             ValueError)

# -------------------------------------------------------------------------
section("provenance")

res = d.black_scholes(S, K, T, VOL, R, "call")
check_true("result carries formula", bool(res.formula), "(C)")
check_true("result carries inputs", len(res.inputs) >= 6, "(C)")
check_true("result labelled COMPUTED", res.label == "COMPUTED", "(C)")
check_true("BS discloses model-not-quote",
           "quote" in res.notes.lower(), "(C)")
check_true("black-76 warns forward not spot",
           "forward" in d.black_76(100, 95, 1, 0.25, 0.05).notes.lower(),
           "(C)")
check_true("iv discloses model dependence",
           "model" in d.implied_volatility(10.0, S, K, T, R).notes.lower(),
           "(C)")
check_true("vega discloses unit convention",
           "vol point" in d.vega(S, K, T, VOL, R).notes.lower(), "(C)")

sys.exit(summary())
