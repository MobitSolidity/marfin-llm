#!/usr/bin/env python3
"""
Independent verification of src/calc/valuation.py (R14).

Method codes (A) closed form, (B) hand arithmetic, (C) invariant,
(D) must-raise -- see tests/_harness.py.

Run: python3 tests/test_valuation.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _harness import check, check_true, check_raises, section, summary  # noqa: E402

from calc import valuation as v  # noqa: E402

print("=" * 78)
print("VALUATION AND ACCOUNTING -- INDEPENDENT VERIFICATION")
print("=" * 78)

# -------------------------------------------------------------------------
section("DCF")

# (A) A single cash flow of 105 discounted one year at 5% is exactly 100.
check("dcf single flow closed form", v.dcf([105], 0.05).value, 100.0,
      tol=1e-12, method="(A) 105/1.05 == 100")

# (B) [100,110,121] at r=10%: each PV is exactly 90.9090..., so PV = 272.7273.
#     TV = 121*1.02/0.08 = 1542.75, discounted 3y = 1159.0909.
check("dcf explicit PV (no terminal)", v.dcf([100, 110, 121], 0.10).value,
      272.727272727272, tol=1e-9, method="(B) 3 x 100/1.1")
check("dcf with terminal value", v.dcf([100, 110, 121], 0.10, 0.02).value,
      1431.818181818182, tol=1e-9, method="(B) 272.7273 + 1159.0909")

# (B) net debt subtracts from enterprise value.
check("dcf net debt subtracted",
      v.dcf([105], 0.05, net_debt=40).value, 60.0, tol=1e-12,
      method="(B) 100 - 40")
# (B) per-share divides equity value.
check("dcf per share", v.dcf([105], 0.05, net_debt=0,
                             shares_outstanding=4).value, 25.0, tol=1e-12,
      method="(B) 100 / 4")

# (C) Raising the discount rate must lower the value. Monotonicity is
#     implementation-independent.
lo = v.dcf([100, 100, 100], 0.08).value
hi = v.dcf([100, 100, 100], 0.15).value
check_true("dcf falls as discount rate rises", hi < lo,
           "(C) %.2f < %.2f" % (hi, lo))
# (C) Mid-year discounting brings cash flows nearer, so value must be higher.
check_true("dcf mid-year > end-of-period",
           v.dcf([100, 100], 0.10, mid_year=True).value >
           v.dcf([100, 100], 0.10).value, "(C)")
# (C) Terminal value must be the majority here -- the report claims this.
r = v.dcf([100, 110, 121], 0.10, 0.02)
check_true("dcf exposes terminal share",
           r.inputs["pv_terminal"] > r.inputs["pv_explicit"],
           "(C) TV %.0f > explicit %.0f" % (r.inputs["pv_terminal"],
                                            r.inputs["pv_explicit"]))

# (D) g >= r makes Gordon growth undefined; it must refuse, not return a
#     confident negative number.
check_raises("dcf refuses g == r", lambda: v.dcf([100], 0.08, 0.08),
             ValueError)
check_raises("dcf refuses g > r", lambda: v.dcf([100], 0.08, 0.12),
             ValueError)
check_raises("dcf refuses percentage rate", lambda: v.dcf([100], 10.0),
             ValueError)
check_raises("dcf refuses zero rate", lambda: v.dcf([100], 0.0), ValueError)
check_raises("dcf refuses empty flows", lambda: v.dcf([], 0.10), ValueError)
check_raises("dcf refuses NaN flow",
             lambda: v.dcf([float("nan")], 0.10), ValueError)

# -------------------------------------------------------------------------
section("dividend discount model")

# (B) D0=2, g=5% -> D1=2.10; 2.10/(0.10-0.05) = 42.
check("ddm grows D0 once",
      v.dividend_discount_model(2.0, 0.10, 0.05).value, 42.0, tol=1e-12,
      method="(B) 2.10/0.05")
# (B) Supplying D1 directly must NOT grow it again: 2/0.05 = 40.
check("ddm accepts D1 directly",
      v.dividend_discount_model(2.0, 0.10, 0.05,
                                dividend_is_next_period=True).value,
      40.0, tol=1e-12, method="(B) 2.00/0.05")
check_raises("ddm refuses g >= r",
             lambda: v.dividend_discount_model(2.0, 0.05, 0.05), ValueError)
check_raises("ddm refuses negative dividend",
             lambda: v.dividend_discount_model(-1.0, 0.10, 0.02), ValueError)

# -------------------------------------------------------------------------
section("multiples")

check("pe_ratio", v.pe_ratio(150, 8.4).value, 17.857142857142858, tol=1e-12,
      method="(B) 150/8.4")
check("forward_pe", v.forward_pe(150, 10.0).value, 15.0, tol=1e-12,
      method="(B)")
check("ps_ratio", v.ps_ratio(1000, 250).value, 4.0, tol=1e-12, method="(B)")
check("pb_ratio", v.pb_ratio(1000, 400).value, 2.5, tol=1e-12, method="(B)")
check("enterprise_value", v.enterprise_value(1000, 300, 100).value, 1200.0,
      tol=1e-12, method="(B) 1000+300-100")
check("ev_ebitda", v.ev_ebitda(1200, 150).value, 8.0, tol=1e-12, method="(B)")
check("ev_sales", v.ev_sales(1200, 400).value, 3.0, tol=1e-12, method="(B)")
check("peg_ratio", v.peg_ratio(20, 25).value, 0.8, tol=1e-12,
      method="(B) 20/25")

# (C) EV must rise with debt and fall with cash -- the sign convention is the
#     whole point of the formula.
check_true("EV rises with debt",
           v.enterprise_value(1000, 500, 100).value >
           v.enterprise_value(1000, 300, 100).value, "(C)")
check_true("EV falls with cash",
           v.enterprise_value(1000, 300, 400).value <
           v.enterprise_value(1000, 300, 100).value, "(C)")

# (D) Negative-earnings multiples are undefined, NOT cheap.
check_raises("P/E refuses negative EPS", lambda: v.pe_ratio(150, -2.0),
             ValueError)
check_raises("P/E refuses zero EPS", lambda: v.pe_ratio(150, 0.0), ValueError)
check_raises("forward P/E refuses negative EPS",
             lambda: v.forward_pe(150, -1.0), ValueError)
check_raises("P/B refuses negative book equity",
             lambda: v.pb_ratio(1000, -100.0), ValueError)
check_raises("EV/EBITDA refuses negative EBITDA",
             lambda: v.ev_ebitda(1200, -50.0), ValueError)
# (D) PEG fed a FRACTION instead of percentage points is a 100x error.
check_raises("PEG refuses fraction growth", lambda: v.peg_ratio(20, 0.15),
             ValueError)
check_raises("PEG refuses negative growth", lambda: v.peg_ratio(20, -5.0),
             ValueError)
check_raises("EV refuses signed (negative) debt",
             lambda: v.enterprise_value(1000, -300, 100), ValueError)

# -------------------------------------------------------------------------
section("returns on capital")

check("roe", v.roe(100, 500).value, 0.20, tol=1e-12, method="(B)")
check("roa", v.roa(100, 2000).value, 0.05, tol=1e-12, method="(B)")
# (B) NOPAT = 200 x 0.75 = 150; 150/1000 = 0.15
check("roic applies tax to EBIT", v.roic(200, 0.25, 1000).value, 0.15,
      tol=1e-12, method="(B) 200*0.75/1000")
# (C) A zero tax rate must leave EBIT untouched.
check("roic zero tax", v.roic(200, 0.0, 1000).value, 0.20, tol=1e-12,
      method="(C) untaxed == EBIT/IC")
check_raises("ROE refuses negative equity", lambda: v.roe(100, -500),
             ValueError)
check_raises("ROIC refuses percentage tax rate",
             lambda: v.roic(200, 25.0, 1000), ValueError)
check_raises("ROIC refuses tax_rate 1.0", lambda: v.roic(200, 1.0, 1000),
             ValueError)

# -------------------------------------------------------------------------
section("cash flow")

check("free_cash_flow", v.free_cash_flow(500, 200).value, 300.0, tol=1e-12,
      method="(B) 500-200")
# (D) Capex arrives NEGATIVE on a cash-flow statement. Accepting the signed
#     value would ADD it, overstating FCF by 2x capex.
check_raises("FCF refuses signed (negative) capex",
             lambda: v.free_cash_flow(500, -200), ValueError)
check("fcf_conversion", v.fcf_conversion(300, 400).value, 0.75, tol=1e-12,
      method="(B)")
check_true("fcf_conversion echoes denominator kind",
           v.fcf_conversion(300, 400, "ebitda").inputs["denominator_kind"]
           == "ebitda", "(C)")
check_raises("fcf_conversion refuses unknown denominator",
             lambda: v.fcf_conversion(300, 400, "vibes"), ValueError)
check_raises("fcf_conversion refuses negative denominator",
             lambda: v.fcf_conversion(300, -400), ValueError)

# -------------------------------------------------------------------------
section("margins")

check("gross_margin", v.gross_margin(1000, 600).value, 0.40, tol=1e-12,
      method="(B)")
# (A) Zero COGS -> margin exactly 1; COGS == revenue -> exactly 0.
check("gross_margin zero cogs", v.gross_margin(1000, 0).value, 1.0,
      tol=1e-12, method="(A)")
check("gross_margin cogs==revenue", v.gross_margin(1000, 1000).value, 0.0,
      tol=1e-12, method="(A)")
check("operating_margin", v.operating_margin(200, 1000).value, 0.20,
      tol=1e-12, method="(B)")
check("net_margin", v.net_margin(150, 1000).value, 0.15, tol=1e-12,
      method="(B)")
# (C) A loss-making company has a negative net margin; that must compute, not
#     raise -- unlike P/E, the ratio is well defined.
check("net_margin allows losses", v.net_margin(-150, 1000).value, -0.15,
      tol=1e-12, method="(C)")
check_raises("gross_margin refuses zero revenue",
             lambda: v.gross_margin(0, 100), ValueError)
check_raises("gross_margin refuses negative cogs",
             lambda: v.gross_margin(1000, -50), ValueError)

# -------------------------------------------------------------------------
section("leverage and coverage")

check("debt_to_equity", v.debt_to_equity(600, 400).value, 1.5, tol=1e-12,
      method="(B)")
check("debt_to_assets", v.debt_to_assets(600, 2000).value, 0.30, tol=1e-12,
      method="(B)")
# (B) net debt = 600 - 100 = 500; 500/250 = 2.0 turns
check("net_debt_to_ebitda", v.net_debt_to_ebitda(600, 100, 250).value, 2.0,
      tol=1e-12, method="(B)")
# (C) Net cash must produce a NEGATIVE ratio, not an error: it is a strength.
check("net_debt_to_ebitda allows net cash",
      v.net_debt_to_ebitda(100, 300, 250).value, -0.8, tol=1e-12,
      method="(C) net cash -> negative")
check("interest_coverage", v.interest_coverage(300, 50).value, 6.0,
      tol=1e-12, method="(B)")
check_raises("debt_to_equity refuses negative equity",
             lambda: v.debt_to_equity(600, -400), ValueError)
# (D) Zero interest expense makes coverage undefined, not infinite.
check_raises("interest_coverage refuses zero interest",
             lambda: v.interest_coverage(300, 0), ValueError)
check_raises("net_debt_to_ebitda refuses negative EBITDA",
             lambda: v.net_debt_to_ebitda(600, 100, -250), ValueError)

# -------------------------------------------------------------------------
section("working capital")

check("current_ratio", v.current_ratio(600, 300).value, 2.0, tol=1e-12,
      method="(B)")
check("quick_ratio excludes inventory",
      v.quick_ratio(600, 200, 300).value, 1.3333333333333333, tol=1e-12,
      method="(B) (600-200)/300")
# (C) The acid test can never exceed the current ratio.
check_true("quick_ratio <= current_ratio",
           v.quick_ratio(600, 200, 300).value <=
           v.current_ratio(600, 300).value, "(C)")
check("working_capital", v.working_capital(600, 300).value, 300.0,
      tol=1e-12, method="(B)")
check("cash_conversion_cycle", v.cash_conversion_cycle(45, 60, 30).value,
      75.0, tol=1e-12, method="(B) 45+60-30")
# (C) Supplier-financed operations give a negative cycle -- a strength.
check("cash_conversion_cycle allows negative",
      v.cash_conversion_cycle(10, 5, 60).value, -45.0, tol=1e-12,
      method="(C)")
check_raises("current_ratio refuses zero liabilities",
             lambda: v.current_ratio(600, 0), ValueError)
check_raises("quick_ratio refuses inventory > current assets",
             lambda: v.quick_ratio(600, 700, 300), ValueError)
check_raises("cash_conversion_cycle refuses negative days",
             lambda: v.cash_conversion_cycle(-5, 60, 30), ValueError)

# -------------------------------------------------------------------------
section("provenance -- SS.5.3 requires formula + inputs on every result")

res = v.dcf([100, 110, 121], 0.10, 0.02)
check_true("result carries formula", bool(res.formula), "(C)")
check_true("result carries inputs", len(res.inputs) > 3,
           "(C) %d fields" % len(res.inputs))
check_true("result labelled COMPUTED", res.label == "COMPUTED", "(C)")
check_true("forward P/E flags estimate in notes",
           "ESTIMATE" in v.forward_pe(150, 10.0).notes.upper(), "(C)")

sys.exit(summary())
