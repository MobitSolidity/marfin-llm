"""
Deterministic valuation and accounting calculations (master prompt SS.5.3).

Same design rules as returns_risk.py: stdlib only, raise on invalid input,
return a CalcResult carrying provenance, never guess a convention.

THE DOMINANT FAILURE MODE IN THIS FAMILY IS NOT ARITHMETIC -- IT IS UNITS AND
SIGNS. A P/E on negative earnings is not "cheap", it is undefined. A PEG fed a
fraction instead of percentage points is off by 100x. A DCF with growth above
the discount rate produces a confidently negative terminal value. Each of those
is guarded explicitly below, because each produces a plausible-looking number
rather than an obvious error.
"""

from typing import Sequence, Optional
import math

from calc.returns_risk import CalcResult, _check_series


def _pos(x, name):
    """Require a strictly positive denominator."""
    if x is None:
        raise ValueError("%s: value is None" % name)
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        raise TypeError("%s: non-numeric value %r" % (name, x))
    if math.isnan(x) or math.isinf(x):
        raise ValueError("%s: NaN/Inf" % name)
    if x <= 0:
        raise ValueError("%s must be > 0, got %g" % (name, x))
    return float(x)


def _num(x, name):
    """Require a finite number; sign unconstrained."""
    if x is None:
        raise ValueError("%s: value is None" % name)
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        raise TypeError("%s: non-numeric value %r" % (name, x))
    if math.isnan(x) or math.isinf(x):
        raise ValueError("%s: NaN/Inf" % name)
    return float(x)


# --------------------------------------------------------------------------
# Intrinsic value
# --------------------------------------------------------------------------

def dcf(cash_flows: Sequence[float], discount_rate: float,
        terminal_growth: Optional[float] = None,
        net_debt: float = 0.0, shares_outstanding: Optional[float] = None,
        mid_year: bool = False) -> CalcResult:
    """
    Discounted cash flow with an optional Gordon-growth terminal value.

    cash_flows are the EXPLICIT forecast period, period 1..N, discounted at
    end of period unless mid_year=True.

    Terminal value uses CF_N * (1+g) / (r - g), discounted back N periods.
    REFUSES terminal_growth >= discount_rate: that formula divides by a
    non-positive number and returns a confident, wildly wrong value (often
    negative). It is the single most common DCF error.
    """
    _check_series(cash_flows, "dcf.cash_flows", minlen=1)
    r = _num(discount_rate, "discount_rate")
    if r <= 0:
        raise ValueError("discount_rate must be > 0, got %g" % r)
    if r >= 1:
        raise ValueError("discount_rate %g looks like a percentage; pass a "
                         "fraction (0.10 for 10%%)" % r)

    pv_explicit = 0.0
    for i, cf in enumerate(cash_flows, start=1):
        t = (i - 0.5) if mid_year else float(i)
        pv_explicit += cf / ((1.0 + r) ** t)

    pv_terminal = 0.0
    tv = None
    n = len(cash_flows)
    if terminal_growth is not None:
        g = _num(terminal_growth, "terminal_growth")
        if g >= r:
            raise ValueError(
                "terminal_growth (%g) must be < discount_rate (%g); the "
                "Gordon formula is undefined otherwise and would return a "
                "meaningless value" % (g, r))
        tv = cash_flows[-1] * (1.0 + g) / (r - g)
        t_n = (n - 0.5) if mid_year else float(n)
        pv_terminal = tv / ((1.0 + r) ** t_n)

    enterprise = pv_explicit + pv_terminal
    equity = enterprise - _num(net_debt, "net_debt")

    value = equity
    units = "currency (equity value)"
    per_share = None
    if shares_outstanding is not None:
        s = _pos(shares_outstanding, "shares_outstanding")
        per_share = equity / s
        value = per_share
        units = "currency per share"

    return CalcResult(
        "dcf", value,
        "sum(CF_t/(1+r)^t) + TV/(1+r)^N, TV = CF_N(1+g)/(r-g); "
        "equity = EV - net_debt",
        {"n_periods": n, "discount_rate": r, "terminal_growth": terminal_growth,
         "pv_explicit": pv_explicit, "terminal_value": tv,
         "pv_terminal": pv_terminal, "enterprise_value": enterprise,
         "equity_value": equity, "net_debt": net_debt,
         "shares_outstanding": shares_outstanding, "per_share": per_share,
         "discounting": "mid-year" if mid_year else "end-of-period"},
        units,
        "Output is only as good as the forecast inputs. Terminal value is "
        "typically the majority of a DCF; state its share when presenting.")


def dividend_discount_model(dividend: float, discount_rate: float,
                            growth_rate: float = 0.0,
                            dividend_is_next_period: bool = False) -> CalcResult:
    """
    Gordon growth model: P0 = D1 / (r - g).

    dividend_is_next_period=False (default) treats `dividend` as D0 (the
    dividend just paid) and grows it once. True treats it as D1 already.
    That distinction moves the answer by a full (1+g) and is silently wrong
    if assumed, so it is an explicit argument.
    """
    d = _num(dividend, "dividend")
    if d < 0:
        raise ValueError("dividend must be >= 0, got %g" % d)
    r = _num(discount_rate, "discount_rate")
    g = _num(growth_rate, "growth_rate")
    if g >= r:
        raise ValueError("growth_rate (%g) must be < discount_rate (%g); "
                         "the model is undefined otherwise" % (g, r))
    d1 = d if dividend_is_next_period else d * (1.0 + g)
    v = d1 / (r - g)
    return CalcResult("dividend_discount_model", v, "P0 = D1 / (r - g)",
                      {"D0_or_D1": d, "D1_used": d1, "discount_rate": r,
                       "growth_rate": g,
                       "input_is": "D1" if dividend_is_next_period else "D0"},
                      "currency per share")


# --------------------------------------------------------------------------
# Multiples
# --------------------------------------------------------------------------

def pe_ratio(price: float, eps: float) -> CalcResult:
    """
    Price / earnings per share.

    REFUSES eps <= 0. A negative P/E is not a low valuation, it is an
    undefined one, and printing "-8x" invites exactly the wrong conclusion.
    """
    p = _pos(price, "price")
    e = _num(eps, "eps")
    if e <= 0:
        raise ValueError("P/E is undefined for non-positive EPS (%g). The "
                         "company has no earnings; use EV/Sales or P/S and "
                         "say so explicitly." % e)
    return CalcResult("pe_ratio", p / e, "price / EPS",
                      {"price": p, "eps": e}, "x (multiple)")


def forward_pe(price: float, forward_eps: float) -> CalcResult:
    """Price divided by FORECAST EPS. The estimate is not a measured fact."""
    p = _pos(price, "price")
    e = _num(forward_eps, "forward_eps")
    if e <= 0:
        raise ValueError("Forward P/E is undefined for non-positive forecast "
                         "EPS (%g)." % e)
    return CalcResult("forward_pe", p / e, "price / forward EPS",
                      {"price": p, "forward_eps": e}, "x (multiple)",
                      "Forward EPS is an ESTIMATE. Attribute the source and "
                      "period; never present it as measured.")


def ps_ratio(market_cap: float, revenue: float) -> CalcResult:
    mc = _pos(market_cap, "market_cap")
    rev = _pos(revenue, "revenue")
    return CalcResult("ps_ratio", mc / rev, "market_cap / revenue",
                      {"market_cap": mc, "revenue": rev}, "x (multiple)")


def pb_ratio(market_cap: float, book_value_equity: float) -> CalcResult:
    mc = _pos(market_cap, "market_cap")
    bv = _num(book_value_equity, "book_value_equity")
    if bv <= 0:
        raise ValueError("P/B is undefined for non-positive book equity (%g); "
                         "negative equity is a solvency signal, not a cheap "
                         "multiple." % bv)
    return CalcResult("pb_ratio", mc / bv, "market_cap / book_value_equity",
                      {"market_cap": mc, "book_value_equity": bv},
                      "x (multiple)")


def enterprise_value(market_cap: float, total_debt: float,
                     cash_and_equivalents: float,
                     minority_interest: float = 0.0,
                     preferred_equity: float = 0.0) -> CalcResult:
    """EV = market cap + debt - cash + minority interest + preferred."""
    mc = _pos(market_cap, "market_cap")
    d = _num(total_debt, "total_debt")
    c = _num(cash_and_equivalents, "cash_and_equivalents")
    mi = _num(minority_interest, "minority_interest")
    pf = _num(preferred_equity, "preferred_equity")
    if d < 0 or c < 0:
        raise ValueError("total_debt and cash must be >= 0 (supply magnitudes, "
                         "not signed balance-sheet entries)")
    ev = mc + d - c + mi + pf
    return CalcResult("enterprise_value", ev,
                      "market_cap + total_debt - cash + minority + preferred",
                      {"market_cap": mc, "total_debt": d, "cash": c,
                       "minority_interest": mi, "preferred_equity": pf},
                      "currency")


def ev_ebitda(enterprise_value_: float, ebitda: float) -> CalcResult:
    ev = _num(enterprise_value_, "enterprise_value")
    e = _num(ebitda, "ebitda")
    if e <= 0:
        raise ValueError("EV/EBITDA is undefined for non-positive EBITDA (%g)."
                         % e)
    return CalcResult("ev_ebitda", ev / e, "enterprise_value / EBITDA",
                      {"enterprise_value": ev, "ebitda": e}, "x (multiple)")


def ev_sales(enterprise_value_: float, revenue: float) -> CalcResult:
    ev = _num(enterprise_value_, "enterprise_value")
    rev = _pos(revenue, "revenue")
    return CalcResult("ev_sales", ev / rev, "enterprise_value / revenue",
                      {"enterprise_value": ev, "revenue": rev},
                      "x (multiple)")


def peg_ratio(pe: float, growth_rate_pct: float) -> CalcResult:
    """
    PEG = P/E divided by the earnings growth rate IN PERCENTAGE POINTS.

    15% growth is passed as 15, not 0.15. Passing the fraction inflates PEG
    by 100x, so a value in (0, 1) is REFUSED as ambiguous rather than used.
    (A genuine sub-1% growth rate is indistinguishable from a mis-entered
    fraction, so the tool asks instead of guessing.)
    """
    p = _num(pe, "pe")
    if p <= 0:
        raise ValueError("PEG requires a positive P/E, got %g" % p)
    g = _num(growth_rate_pct, "growth_rate_pct")
    if g <= 0:
        raise ValueError("PEG is not meaningful for non-positive growth (%g)"
                         % g)
    if g < 1.0:
        raise ValueError(
            "growth_rate_pct=%g is ambiguous: PEG expects PERCENTAGE POINTS "
            "(15 for 15%%), and this looks like a fraction. Re-supply as "
            "percentage points." % g)
    return CalcResult("peg_ratio", p / g, "P/E / growth_rate_in_percent",
                      {"pe": p, "growth_rate_pct": g}, "x (ratio)",
                      "Growth rate must cover the same horizon the P/E is "
                      "quoted on; mixing trailing P/E with forward growth is "
                      "a common distortion.")


# --------------------------------------------------------------------------
# Returns on capital
# --------------------------------------------------------------------------

def roe(net_income: float, shareholders_equity: float) -> CalcResult:
    ni = _num(net_income, "net_income")
    eq = _num(shareholders_equity, "shareholders_equity")
    if eq <= 0:
        raise ValueError("ROE is undefined for non-positive equity (%g)" % eq)
    return CalcResult("roe", ni / eq, "net_income / shareholders_equity",
                      {"net_income": ni, "shareholders_equity": eq},
                      "fraction",
                      "Use average equity across the period when the balance "
                      "sheet moved materially.")


def roa(net_income: float, total_assets: float) -> CalcResult:
    ni = _num(net_income, "net_income")
    ta = _pos(total_assets, "total_assets")
    return CalcResult("roa", ni / ta, "net_income / total_assets",
                      {"net_income": ni, "total_assets": ta}, "fraction")


def roic(ebit: float, tax_rate: float, invested_capital: float) -> CalcResult:
    """ROIC = NOPAT / invested capital, NOPAT = EBIT x (1 - tax rate)."""
    e = _num(ebit, "ebit")
    t = _num(tax_rate, "tax_rate")
    if not (0.0 <= t < 1.0):
        raise ValueError("tax_rate must be a fraction in [0,1), got %g" % t)
    ic = _pos(invested_capital, "invested_capital")
    nopat = e * (1.0 - t)
    return CalcResult("roic", nopat / ic,
                      "EBIT x (1 - tax_rate) / invested_capital",
                      {"ebit": e, "tax_rate": t, "nopat": nopat,
                       "invested_capital": ic}, "fraction")


# --------------------------------------------------------------------------
# Cash flow
# --------------------------------------------------------------------------

def free_cash_flow(cash_flow_operations: float, capital_expenditure: float
                   ) -> CalcResult:
    """
    FCF = CFO - capex.

    capital_expenditure is supplied as a POSITIVE magnitude. Cash-flow
    statements report it negative; passing it signed would add instead of
    subtract, overstating FCF by 2x capex.
    """
    cfo = _num(cash_flow_operations, "cash_flow_operations")
    capex = _num(capital_expenditure, "capital_expenditure")
    if capex < 0:
        raise ValueError(
            "capital_expenditure must be a positive magnitude (%g given). "
            "Cash-flow statements show it as negative; supply its absolute "
            "value or FCF will be overstated." % capex)
    return CalcResult("free_cash_flow", cfo - capex, "CFO - capex",
                      {"cash_flow_operations": cfo,
                       "capital_expenditure": capex}, "currency")


def fcf_conversion(free_cash_flow_: float, denominator: float,
                   denominator_kind: str = "net_income") -> CalcResult:
    """
    FCF conversion. The denominator is ambiguous in practice (net income vs
    EBITDA), so it is named explicitly and echoed in the output.
    """
    kinds = ("net_income", "ebitda", "revenue")
    if denominator_kind not in kinds:
        raise ValueError("denominator_kind must be one of %s" % (kinds,))
    f = _num(free_cash_flow_, "free_cash_flow")
    d = _num(denominator, "denominator")
    if d <= 0:
        raise ValueError("FCF conversion is undefined for non-positive %s (%g)"
                         % (denominator_kind, d))
    return CalcResult("fcf_conversion", f / d,
                      "free_cash_flow / %s" % denominator_kind,
                      {"free_cash_flow": f, "denominator": d,
                       "denominator_kind": denominator_kind}, "fraction")


# --------------------------------------------------------------------------
# Margins
# --------------------------------------------------------------------------

def gross_margin(revenue: float, cost_of_goods_sold: float) -> CalcResult:
    rev = _pos(revenue, "revenue")
    cogs = _num(cost_of_goods_sold, "cost_of_goods_sold")
    if cogs < 0:
        raise ValueError("cost_of_goods_sold must be >= 0, got %g" % cogs)
    return CalcResult("gross_margin", (rev - cogs) / rev,
                      "(revenue - COGS) / revenue",
                      {"revenue": rev, "cogs": cogs,
                       "gross_profit": rev - cogs}, "fraction")


def operating_margin(operating_income: float, revenue: float) -> CalcResult:
    oi = _num(operating_income, "operating_income")
    rev = _pos(revenue, "revenue")
    return CalcResult("operating_margin", oi / rev,
                      "operating_income / revenue",
                      {"operating_income": oi, "revenue": rev}, "fraction")


def net_margin(net_income: float, revenue: float) -> CalcResult:
    ni = _num(net_income, "net_income")
    rev = _pos(revenue, "revenue")
    return CalcResult("net_margin", ni / rev, "net_income / revenue",
                      {"net_income": ni, "revenue": rev}, "fraction")


# --------------------------------------------------------------------------
# Leverage and coverage
# --------------------------------------------------------------------------

def debt_to_equity(total_debt: float, shareholders_equity: float
                   ) -> CalcResult:
    d = _num(total_debt, "total_debt")
    if d < 0:
        raise ValueError("total_debt must be >= 0, got %g" % d)
    eq = _num(shareholders_equity, "shareholders_equity")
    if eq <= 0:
        raise ValueError("debt/equity is undefined for non-positive equity "
                         "(%g); report negative equity directly instead." % eq)
    return CalcResult("debt_to_equity", d / eq,
                      "total_debt / shareholders_equity",
                      {"total_debt": d, "shareholders_equity": eq},
                      "x (ratio)")


def debt_to_assets(total_debt: float, total_assets: float) -> CalcResult:
    d = _num(total_debt, "total_debt")
    if d < 0:
        raise ValueError("total_debt must be >= 0, got %g" % d)
    ta = _pos(total_assets, "total_assets")
    return CalcResult("debt_to_assets", d / ta, "total_debt / total_assets",
                      {"total_debt": d, "total_assets": ta}, "fraction")


def net_debt_to_ebitda(total_debt: float, cash_and_equivalents: float,
                       ebitda: float) -> CalcResult:
    d = _num(total_debt, "total_debt")
    c = _num(cash_and_equivalents, "cash_and_equivalents")
    if d < 0 or c < 0:
        raise ValueError("total_debt and cash must be >= 0")
    e = _num(ebitda, "ebitda")
    if e <= 0:
        raise ValueError("net debt / EBITDA is undefined for non-positive "
                         "EBITDA (%g)" % e)
    nd = d - c
    return CalcResult("net_debt_to_ebitda", nd / e,
                      "(total_debt - cash) / EBITDA",
                      {"total_debt": d, "cash": c, "net_debt": nd,
                       "ebitda": e}, "x (turns)",
                      "Net debt can be negative (net cash); the resulting "
                      "negative ratio means the company holds more cash than "
                      "debt, not that it is distressed.")


def interest_coverage(ebit: float, interest_expense: float) -> CalcResult:
    e = _num(ebit, "ebit")
    i = _num(interest_expense, "interest_expense")
    if i <= 0:
        raise ValueError("interest_expense must be a positive magnitude (%g); "
                         "zero interest makes coverage undefined, not infinite"
                         % i)
    return CalcResult("interest_coverage", e / i, "EBIT / interest_expense",
                      {"ebit": e, "interest_expense": i}, "x (times)")


# --------------------------------------------------------------------------
# Working capital
# --------------------------------------------------------------------------

def current_ratio(current_assets: float, current_liabilities: float
                  ) -> CalcResult:
    ca = _num(current_assets, "current_assets")
    if ca < 0:
        raise ValueError("current_assets must be >= 0, got %g" % ca)
    cl = _pos(current_liabilities, "current_liabilities")
    return CalcResult("current_ratio", ca / cl,
                      "current_assets / current_liabilities",
                      {"current_assets": ca, "current_liabilities": cl},
                      "x (ratio)")


def quick_ratio(current_assets: float, inventory: float,
                current_liabilities: float) -> CalcResult:
    """Acid test: excludes inventory from current assets."""
    ca = _num(current_assets, "current_assets")
    inv = _num(inventory, "inventory")
    if ca < 0 or inv < 0:
        raise ValueError("current_assets and inventory must be >= 0")
    if inv > ca:
        raise ValueError("inventory (%g) exceeds current_assets (%g); inputs "
                         "are inconsistent" % (inv, ca))
    cl = _pos(current_liabilities, "current_liabilities")
    return CalcResult("quick_ratio", (ca - inv) / cl,
                      "(current_assets - inventory) / current_liabilities",
                      {"current_assets": ca, "inventory": inv,
                       "current_liabilities": cl}, "x (ratio)")


def working_capital(current_assets: float, current_liabilities: float
                    ) -> CalcResult:
    ca = _num(current_assets, "current_assets")
    cl = _num(current_liabilities, "current_liabilities")
    if ca < 0 or cl < 0:
        raise ValueError("current assets and liabilities must be >= 0")
    return CalcResult("working_capital", ca - cl,
                      "current_assets - current_liabilities",
                      {"current_assets": ca, "current_liabilities": cl},
                      "currency")


def cash_conversion_cycle(days_sales_outstanding: float,
                          days_inventory_outstanding: float,
                          days_payables_outstanding: float) -> CalcResult:
    """CCC = DSO + DIO - DPO. Negative is favourable (supplier-financed)."""
    dso = _num(days_sales_outstanding, "days_sales_outstanding")
    dio = _num(days_inventory_outstanding, "days_inventory_outstanding")
    dpo = _num(days_payables_outstanding, "days_payables_outstanding")
    for nm, v in (("DSO", dso), ("DIO", dio), ("DPO", dpo)):
        if v < 0:
            raise ValueError("%s must be >= 0 days, got %g" % (nm, v))
    return CalcResult("cash_conversion_cycle", dso + dio - dpo,
                      "DSO + DIO - DPO",
                      {"dso": dso, "dio": dio, "dpo": dpo}, "days",
                      "A negative cycle means suppliers fund operations; it "
                      "is a strength, not an error.")
