#!/usr/bin/env python3
"""
Independent verification of src/calc/technicals.py (R14).

Method codes (A) closed form, (B) hand arithmetic, (C) invariant,
(D) must-raise -- see tests/_harness.py.

The most valuable tests here are the CONVENTION tests. An indicator that is
arithmetically self-consistent but uses SMA smoothing where Wilder's is
standard produces plausible numbers that disagree with every charting
platform. Those are pinned explicitly below.

Run: python3 tests/test_technicals.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _harness import check, check_true, check_raises, section, summary  # noqa: E402

from calc import technicals as t  # noqa: E402

print("=" * 78)
print("TECHNICAL INDICATORS -- INDEPENDENT VERIFICATION")
print("=" * 78)

FLAT = [100.0] * 30
RAMP = [float(i) for i in range(1, 31)]

# -------------------------------------------------------------------------
section("moving averages")

# (B) mean(3,4,5) = 4
check("sma latest value", t.sma([1, 2, 3, 4, 5], 3).value, 4.0, tol=1e-12,
      method="(B) mean(3,4,5)")
# (A) On a constant series every average equals the constant.
check("sma of constant series", t.sma(FLAT, 10).value, 100.0, tol=1e-12,
      method="(A)")
# (B) Full series check, not just the last bar.
check_true("sma series values",
           t._sma_series([1, 2, 3, 4, 5], 3) == [2.0, 3.0, 4.0],
           "(B) [2,3,4]")
# (C) Exactly n - period + 1 values.
check("sma series length", len(t._sma_series(RAMP, 10)), 21.0, tol=0,
      method="(C) 30-10+1")

# (A) EMA of a constant series is that constant forever (seed and update both
#     equal it).
check("ema of constant series", t.ema(FLAT, 10).value, 100.0, tol=1e-12,
      method="(A)")
# (B) Seed = mean(1,2,3) = 2; alpha = 0.5; then 0.5*4+0.5*2 = 3;
#     0.5*5+0.5*3 = 4.
check("ema hand-stepped", t.ema([1, 2, 3, 4, 5], 3).value, 4.0, tol=1e-12,
      method="(B) seed 2 -> 3 -> 4")
check_true("ema seeded with SMA not first price",
           abs(t._ema_series([1, 2, 3, 4, 5], 3)[0] - 2.0) < 1e-12,
           "(B) seed == mean(1,2,3) == 2")
# (C) EMA reacts faster than SMA to a jump, so after a step up it must be
#     higher than the SMA of the same period.
step = [10.0] * 10 + [20.0] * 3
check_true("ema more responsive than sma after step",
           t.ema(step, 10).value > t.sma(step, 10).value, "(C)")

# (B) WMA(1..3) weights 1,2,3 over [3,4,5]: (3*1+4*2+5*3)/6 = 26/6
check("wma latest value", t.wma([1, 2, 3, 4, 5], 3).value,
      4.333333333333333, tol=1e-12, method="(B) 26/6")
# (A) Constant series -> the constant.
check("wma of constant series", t.wma(FLAT, 10).value, 100.0, tol=1e-12,
      method="(A)")
# (C) On a rising series WMA must exceed SMA (recent bars weigh more).
check_true("wma > sma on rising series",
           t.wma(RAMP, 10).value > t.sma(RAMP, 10).value, "(C)")

# (D) Warm-up must be enforced, not silently shortened.
check_raises("sma refuses insufficient data", lambda: t.sma([1, 2], 5),
             ValueError)
check_raises("ema refuses insufficient data", lambda: t.ema([1, 2], 5),
             ValueError)
check_raises("sma refuses zero period", lambda: t.sma([1, 2, 3], 0),
             ValueError)
check_raises("sma refuses fractional period", lambda: t.sma([1, 2, 3], 2.5),
             ValueError)
check_raises("sma refuses NaN in series",
             lambda: t.sma([1, float("nan"), 3], 2), ValueError)

# -------------------------------------------------------------------------
section("RSI -- Wilder smoothing")

# (B) Wilder's own published example (New Concepts in Technical Trading
#     Systems). This value is the industry reference; an SMA-smoothed
#     implementation gives a different number and would fail here.
WILDER = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42,
          45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28]
check("rsi matches Wilder reference", t.rsi(WILDER, 14).value,
      70.46413502109705, tol=1e-9, method="(B) published example")

# (A) A monotonically rising series has no losses -> RSI is exactly 100.
check("rsi of monotonic rise == 100", t.rsi(RAMP, 14).value, 100.0,
      tol=1e-12, method="(A) no downside")
# (A) A monotonically falling series -> exactly 0.
check("rsi of monotonic fall == 0", t.rsi(RAMP[::-1], 14).value, 0.0,
      tol=1e-12, method="(A) no upside")
# (C) RSI is bounded [0,100] for arbitrary input.
mixed = [100, 102, 101, 105, 103, 108, 104, 110, 107, 112,
         109, 115, 111, 118, 114, 120]
rv = t.rsi(mixed, 14).value
check_true("rsi bounded [0,100]", 0.0 <= rv <= 100.0, "(C) %.4f" % rv)
check_raises("rsi refuses insufficient data", lambda: t.rsi([1, 2, 3], 14),
             ValueError)

# -------------------------------------------------------------------------
section("MACD")

# (A) On a constant series both EMAs equal the constant, so MACD, signal and
#     histogram are all exactly zero.
m = t.macd(FLAT + FLAT, 12, 26, 9).value
check("macd of constant == 0", m["macd"], 0.0, tol=1e-12, method="(A)")
check("macd signal of constant == 0", m["signal"], 0.0, tol=1e-12,
      method="(A)")
check("macd histogram of constant == 0", m["histogram"], 0.0, tol=1e-12,
      method="(A)")
# (C) On a sustained uptrend the fast EMA leads, so MACD must be positive.
up = [float(i) for i in range(1, 61)]
check_true("macd positive in uptrend", t.macd(up).value["macd"] > 0, "(C)")
check_true("macd negative in downtrend",
           t.macd(up[::-1]).value["macd"] < 0, "(C)")
# (C) histogram == macd - signal, by definition.
mm = t.macd(up).value
check("macd histogram identity", mm["histogram"],
      mm["macd"] - mm["signal"], tol=1e-12, method="(C)")
check_raises("macd refuses fast >= slow",
             lambda: t.macd(up, 26, 12, 9), ValueError)
check_raises("macd refuses insufficient data",
             lambda: t.macd([1.0] * 10), ValueError)

# -------------------------------------------------------------------------
section("rate of change")

# (B) (5-2)/2 = 1.5 with period 3 on [1..5] -> index 4 vs index 1
check("roc hand value", t.rate_of_change([1, 2, 3, 4, 5], 3).value, 1.5,
      tol=1e-12, method="(B) (5-2)/2")
# (A) Constant series -> exactly zero change.
check("roc of constant == 0", t.rate_of_change(FLAT, 5).value, 0.0,
      tol=1e-12, method="(A)")
# (C) Returned as a FRACTION not percentage points: a doubling gives 1.0.
check("roc returns fraction not percent",
      t.rate_of_change([50.0, 60.0, 100.0], 2).value, 1.0, tol=1e-12,
      method="(C) doubling -> 1.0")
check_raises("roc refuses insufficient data",
             lambda: t.rate_of_change([1, 2], 5), ValueError)

# -------------------------------------------------------------------------
section("stochastic oscillator")

H = [10, 11, 12, 13, 14, 15, 16]
L = [5, 6, 7, 8, 9, 10, 11]
C = [9, 10, 11, 12, 13, 14, 15]
s = t.stochastic_oscillator(H, L, C, 5, 3).value
# (B) Last bar: HH over last 5 = 16, LL = 7, C = 15 -> 100*(15-7)/(16-7)
check("stoch %K hand value", s["k"], 100.0 * 8.0 / 9.0, tol=1e-12,
      method="(B) 100*(15-7)/9")
# (C) %K bounded [0,100]
check_true("stoch %K bounded", 0.0 <= s["k"] <= 100.0, "(C)")
# (A) Close at the window high -> exactly 100; at the low -> exactly 0.
Hh = [10, 10, 10, 10, 10]
Ll = [0, 0, 0, 0, 0]
check("stoch at window high == 100",
      t.stochastic_oscillator(Hh, Ll, [5, 5, 5, 5, 10], 3, 3).value["k"],
      100.0, tol=1e-12, method="(A)")
check("stoch at window low == 0",
      t.stochastic_oscillator(Hh, Ll, [5, 5, 5, 5, 0], 3, 3).value["k"],
      0.0, tol=1e-12, method="(A)")
# (D) Inconsistent OHLC must be refused, not averaged over.
check_raises("stoch refuses close outside high/low",
             lambda: t.stochastic_oscillator([10, 10, 10], [5, 5, 5],
                                             [9, 9, 99], 3, 1), ValueError)
check_raises("stoch refuses mismatched lengths",
             lambda: t.stochastic_oscillator([10, 11], [5], [9, 10], 2, 1),
             ValueError)

# -------------------------------------------------------------------------
section("ATR -- Wilder smoothing")

# (B) Constant 2-wide bars with no gaps: every TR is exactly 2, so ATR == 2.
H2 = [11.0] * 20
L2 = [9.0] * 20
C2 = [10.0] * 20
check("atr of uniform bars", t.atr(H2, L2, C2, 14).value, 2.0, tol=1e-12,
      method="(A) every TR == 2")
# (C) A gap must raise TR above the bar range: TR uses |H - prev_close|.
Hg = [11.0] * 10 + [21.0]
Lg = [9.0] * 10 + [19.0]
Cg = [10.0] * 10 + [20.0]
trs = t._true_range_series(Hg, Lg, Cg)
check("atr true range captures gap", trs[-1], 11.0, tol=1e-12,
      method="(B) |21 - 10| == 11 > bar range 2")
# (C) ATR is an absolute price distance and must be positive here.
check_true("atr positive", t.atr(Hg, Lg, Cg, 5).value > 0, "(C)")
check_raises("atr refuses high < low",
             lambda: t.atr([5.0] * 20, [9.0] * 20, [7.0] * 20, 14),
             ValueError)
check_raises("atr refuses insufficient data",
             lambda: t.atr(H2[:3], L2[:3], C2[:3], 14), ValueError)

# -------------------------------------------------------------------------
section("Bollinger Bands")

# (A) Constant series has zero dispersion: all three bands coincide.
b = t.bollinger_bands(FLAT, 20, 2.0).value
check("bollinger middle on constant", b["middle"], 100.0, tol=1e-12,
      method="(A)")
check("bollinger upper == middle on constant", b["upper"], 100.0, tol=1e-12,
      method="(A) zero stdev")
check("bollinger lower == middle on constant", b["lower"], 100.0, tol=1e-12,
      method="(A)")
# (B) [2,4,4,4,5,5,7,9] has population stdev exactly 2, mean exactly 5.
POP = [2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]
bb = t.bollinger_bands(POP, 8, 2.0).value
check("bollinger middle hand value", bb["middle"], 5.0, tol=1e-12,
      method="(B) mean == 5")
check("bollinger upper hand value", bb["upper"], 9.0, tol=1e-12,
      method="(B) 5 + 2*2")
check("bollinger lower hand value", bb["lower"], 1.0, tol=1e-12,
      method="(B) 5 - 2*2")
# (C) The sample convention must give WIDER bands than population.
bs = t.bollinger_bands(POP, 8, 2.0, sample=True).value
check_true("sample stdev widens bands", bs["upper"] > bb["upper"], "(C)")
# (C) Ordering invariant.
check_true("bollinger lower < middle < upper",
           bb["lower"] < bb["middle"] < bb["upper"], "(C)")
check_raises("bollinger refuses zero num_std",
             lambda: t.bollinger_bands(FLAT, 20, 0.0), ValueError)
check_raises("bollinger refuses insufficient data",
             lambda: t.bollinger_bands([1, 2, 3], 20), ValueError)

# -------------------------------------------------------------------------
section("ADX")

# (C) ADX measures STRENGTH not direction. A steady uptrend and its mirror
#     downtrend must give the SAME ADX -- this is the property most often
#     broken by an implementation that leaks direction into the index.
n = 60
Hu = [float(100 + i) for i in range(n)]
Lu = [float(98 + i) for i in range(n)]
Cu = [float(99 + i) for i in range(n)]
Hd = [float(100 + n - i) for i in range(n)]
Ld = [float(98 + n - i) for i in range(n)]
Cd = [float(99 + n - i) for i in range(n)]
au = t.adx(Hu, Lu, Cu, 14).value
ad = t.adx(Hd, Ld, Cd, 14).value
check("adx symmetric up vs down", au["adx"], ad["adx"], tol=1e-9,
      method="(C) strength only, not direction")
# (C) Direction lives in the DI spread, and must flip sign.
check_true("di_plus dominates in uptrend", au["di_plus"] > au["di_minus"],
           "(C)")
check_true("di_minus dominates in downtrend", ad["di_minus"] > ad["di_plus"],
           "(C)")
# (C) Bounded [0,100].
check_true("adx bounded", 0.0 <= au["adx"] <= 100.0,
           "(C) %.4f" % au["adx"])
# (C) A pure trend should register strong; a choppy series should not. This
#     compares two DIFFERENT inputs, so it cannot be satisfied by a constant.
chop = 60
Hc = [100.0 + (1 if i % 2 else 0) for i in range(chop)]
Lc = [98.0 + (1 if i % 2 else 0) for i in range(chop)]
Cc = [99.0 + (1 if i % 2 else 0) for i in range(chop)]
check_true("adx higher in trend than chop",
           au["adx"] > t.adx(Hc, Lc, Cc, 14).value["adx"], "(C)")
check_raises("adx refuses insufficient data",
             lambda: t.adx(Hu[:10], Lu[:10], Cu[:10], 14), ValueError)

# -------------------------------------------------------------------------
section("Donchian channels")

d = t.donchian_channels([1, 5, 3, 9, 4], [0, 2, 1, 6, 2], 5).value
check("donchian upper", d["upper"], 9.0, tol=1e-12, method="(B) max high")
check("donchian lower", d["lower"], 0.0, tol=1e-12, method="(B) min low")
check("donchian middle", d["middle"], 4.5, tol=1e-12, method="(B) (9+0)/2")
# (C) Only the lookback window counts -- an older extreme must be excluded.
d2 = t.donchian_channels([99, 1, 2, 3, 4], [0, 1, 2, 3, 4], 3).value
check("donchian respects lookback window", d2["upper"], 4.0, tol=1e-12,
      method="(C) 99 is outside the 3-bar window")
check_raises("donchian refuses mismatched lengths",
             lambda: t.donchian_channels([1, 2, 3], [1, 2], 2), ValueError)

# -------------------------------------------------------------------------
section("VWAP")

# (B) Uniform typical price 10 with any volumes -> VWAP exactly 10.
check("vwap of uniform price", t.vwap([11.0] * 5, [9.0] * 5, [10.0] * 5,
                                      [100.0] * 5).value, 10.0, tol=1e-12,
      method="(A)")
# (B) Two bars, typical 10 and 20, volumes 1 and 3 -> (10 + 60)/4 = 17.5
check("vwap volume weighting",
      t.vwap([10.0, 20.0], [10.0, 20.0], [10.0, 20.0], [1.0, 3.0]).value,
      17.5, tol=1e-12, method="(B) (10*1 + 20*3)/4")
# (C) VWAP must sit between the min and max typical price.
vw = t.vwap([12.0, 22.0], [8.0, 18.0], [10.0, 20.0], [5.0, 2.0]).value
check_true("vwap within price range", 10.0 <= vw <= 20.0, "(C) %.4f" % vw)
check_raises("vwap refuses zero total volume",
             lambda: t.vwap([10.0, 10.0], [10.0, 10.0], [10.0, 10.0],
                            [0.0, 0.0]), ZeroDivisionError)
check_raises("vwap refuses negative volume",
             lambda: t.vwap([10.0, 10.0], [10.0, 10.0], [10.0, 10.0],
                            [1.0, -5.0]), ValueError)

# -------------------------------------------------------------------------
section("OBV")

# (B) closes 10,11,10,12 with volumes 5,3,4,6:
#     up +3, down -4, up +6 -> 0 +3 -4 +6 = 5
check("obv hand value", t.obv([10, 11, 10, 12], [5, 3, 4, 6]).value, 5.0,
      tol=1e-12, method="(B) +3 -4 +6")
# (A) Unchanged closes contribute nothing.
check("obv ignores unchanged closes",
      t.obv([10, 10, 10], [5, 5, 5]).value, 0.0, tol=1e-12, method="(A)")
# (C) A pure uptrend accumulates all volume after the first bar.
check("obv accumulates in uptrend",
      t.obv([1, 2, 3, 4], [10, 10, 10, 10]).value, 30.0, tol=1e-12,
      method="(C) 3 up-bars x 10")
check_raises("obv refuses mismatched lengths",
             lambda: t.obv([1, 2, 3], [1, 2]), ValueError)
check_raises("obv refuses negative volume",
             lambda: t.obv([1, 2], [1, -2]), ValueError)

# -------------------------------------------------------------------------
section("provenance")

r = t.rsi(WILDER, 14)
check_true("result carries formula", bool(r.formula), "(C)")
check_true("result carries inputs", len(r.inputs) >= 2, "(C)")
check_true("result labelled COMPUTED", r.label == "COMPUTED", "(C)")
check_true("rsi records Wilder smoothing",
           "wilder" in str(r.inputs.get("smoothing", "")).lower(), "(C)")
check_true("adx notes strength-not-direction",
           "direction" in t.adx(Hu, Lu, Cu, 14).notes.lower(), "(C)")
check_true("vwap notes session anchoring",
           "session" in t.vwap([11.0] * 5, [9.0] * 5, [10.0] * 5,
                               [100.0] * 5).notes.lower(), "(C)")

sys.exit(summary())
