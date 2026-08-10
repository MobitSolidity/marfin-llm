"""
Tool registry and dispatcher (master prompt SS.5.3, SS.7).

This is the boundary between the model and the deterministic engine. The model
emits a tool call; this module validates and executes it. The model never
computes, and never sees a result without provenance.

SECURITY POSTURE (SS.11):
  - Whitelist only. An unknown tool name is refused, never eval'd.
  - Arguments are type-checked and coerced through the Persian-aware parser
    before reaching any calculation.
  - Tools are PURE: no network, no filesystem, no state mutation. Nothing here
    can place an order. Execution capability lives behind separate, gated
    modules that do not exist yet.
  - A tool raising an exception returns a structured error. The model must
    surface that error, not invent a number to replace it.
"""

from typing import Any, Dict, Callable
import inspect

from calc import returns_risk as rr
from calc import valuation as val
from calc import technicals as tech
from calc import fixed_income as fi
from calc import derivatives as der
from calc.persian_num import parse_number

# Whitelist: tool name -> (callable, JSON schema for the model).
_REGISTRY: Dict[str, Dict[str, Any]] = {}


def register(name: str, fn: Callable, description: str,
             params: Dict[str, Any], required):
    _REGISTRY[name] = {
        "fn": fn,
        "schema": {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": params,
                    "required": list(required),
                },
            },
        },
    }


NUM = {"type": "number"}
ARR = {"type": "array", "items": {"type": "number"}}
FREQ = {"type": "string", "enum": ["daily", "weekly", "monthly",
                                   "quarterly", "annual"]}

register("simple_return", rr.simple_return,
         "Simple percentage return between two values.",
         {"start": NUM, "end": NUM}, ["start", "end"])

register("log_return", rr.log_return,
         "Natural-log return between two strictly positive prices.",
         {"start": NUM, "end": NUM}, ["start", "end"])

register("cagr", rr.cagr,
         "Compound annual growth rate. Use for multi-year growth, NOT a "
         "simple average.",
         {"start": NUM, "end": NUM, "years": NUM}, ["start", "end", "years"])

register("annualized_return", rr.annualized_return,
         "Geometrically annualize a series of periodic returns.",
         {"returns": ARR, "freq": FREQ}, ["returns"])

register("annualized_volatility", rr.annualized_volatility,
         "Annualized standard deviation of periodic returns.",
         {"returns": ARR, "freq": FREQ}, ["returns"])

register("sharpe_ratio", rr.sharpe_ratio,
         "Sharpe ratio. risk_free_rate is the ANNUAL rate and is "
         "de-annualized internally.",
         {"returns": ARR, "risk_free_rate": NUM, "freq": FREQ}, ["returns"])

register("sortino_ratio", rr.sortino_ratio,
         "Sortino ratio; penalizes downside deviation only.",
         {"returns": ARR, "risk_free_rate": NUM, "freq": FREQ,
          "target": NUM}, ["returns"])

register("max_drawdown", rr.max_drawdown,
         "Largest peak-to-trough decline. Takes an EQUITY CURVE, not returns.",
         {"equity": ARR}, ["equity"])

register("calmar_ratio", rr.calmar_ratio,
         "Annualized return divided by absolute maximum drawdown.",
         {"returns": ARR, "equity": ARR, "freq": FREQ}, ["returns", "equity"])

register("beta", rr.beta,
         "Beta of an asset's returns against market returns.",
         {"asset": ARR, "market": ARR}, ["asset", "market"])

register("alpha", rr.alpha,
         "Jensen's alpha, annualized.",
         {"asset": ARR, "market": ARR, "risk_free_rate": NUM, "freq": FREQ},
         ["asset", "market"])

register("correlation", rr.correlation,
         "Pearson correlation between two return series.",
         {"a": ARR, "b": ARR}, ["a", "b"])

register("covariance", rr.covariance,
         "Sample covariance between two return series.",
         {"a": ARR, "b": ARR}, ["a", "b"])

register("tracking_error", rr.tracking_error,
         "Annualized standard deviation of active returns vs a benchmark.",
         {"asset": ARR, "benchmark": ARR, "freq": FREQ},
         ["asset", "benchmark"])

register("information_ratio", rr.information_ratio,
         "Annualized active return divided by tracking error.",
         {"asset": ARR, "benchmark": ARR, "freq": FREQ},
         ["asset", "benchmark"])

register("value_at_risk", rr.value_at_risk,
         "Historical Value at Risk. Returns a negative number (a loss).",
         {"returns": ARR, "confidence": NUM}, ["returns"])

register("conditional_value_at_risk", rr.conditional_value_at_risk,
         "Expected shortfall: mean loss beyond the VaR threshold.",
         {"returns": ARR, "confidence": NUM}, ["returns"])

register("position_size", rr.position_size,
         "Units to trade so a stop-out loses exactly risk_pct of equity. "
         "risk_pct is a FRACTION (0.01 = 1%).",
         {"account_equity": NUM, "risk_pct": NUM, "entry": NUM, "stop": NUM},
         ["account_equity", "risk_pct", "entry", "stop"])

register("risk_reward", rr.risk_reward,
         "Reward-to-risk ratio for a trade setup.",
         {"entry": NUM, "stop": NUM, "target": NUM},
         ["entry", "stop", "target"])

register("portfolio_leverage", rr.portfolio_leverage,
         "Gross exposure divided by net equity.",
         {"gross_exposure": NUM, "net_equity": NUM},
         ["gross_exposure", "net_equity"])

register("concentration", rr.concentration,
         "Herfindahl concentration index of portfolio weights.",
         {"weights": ARR}, ["weights"])


# ==========================================================================
# VALUATION AND ACCOUNTING (R14)
# ==========================================================================

INT = {"type": "integer"}
BOOL = {"type": "boolean"}
OPT_TYPE = {"type": "string", "enum": ["call", "put"]}
SIDE = {"type": "string", "enum": ["long", "short"]}

register("dcf", val.dcf,
         "Discounted cash flow with optional Gordon terminal value. "
         "discount_rate and terminal_growth are FRACTIONS. Refuses "
         "terminal_growth >= discount_rate.",
         {"cash_flows": ARR, "discount_rate": NUM, "terminal_growth": NUM,
          "net_debt": NUM, "shares_outstanding": NUM, "mid_year": BOOL},
         ["cash_flows", "discount_rate"])

register("dividend_discount_model", val.dividend_discount_model,
         "Gordon growth model P0 = D1/(r-g). Set dividend_is_next_period "
         "true if supplying D1 rather than D0.",
         {"dividend": NUM, "discount_rate": NUM, "growth_rate": NUM,
          "dividend_is_next_period": BOOL}, ["dividend", "discount_rate"])

register("pe_ratio", val.pe_ratio,
         "Price / earnings per share. Refuses non-positive EPS: a negative "
         "P/E is undefined, not cheap.",
         {"price": NUM, "eps": NUM}, ["price", "eps"])

register("forward_pe", val.forward_pe,
         "Price / forecast EPS. Forecast is an ESTIMATE, not a measured fact.",
         {"price": NUM, "forward_eps": NUM}, ["price", "forward_eps"])

register("ps_ratio", val.ps_ratio, "Market cap / revenue.",
         {"market_cap": NUM, "revenue": NUM}, ["market_cap", "revenue"])

register("pb_ratio", val.pb_ratio, "Market cap / book value of equity.",
         {"market_cap": NUM, "book_value_equity": NUM},
         ["market_cap", "book_value_equity"])

register("enterprise_value", val.enterprise_value,
         "EV = market cap + debt - cash + minority + preferred. Supply debt "
         "and cash as positive magnitudes.",
         {"market_cap": NUM, "total_debt": NUM, "cash_and_equivalents": NUM,
          "minority_interest": NUM, "preferred_equity": NUM},
         ["market_cap", "total_debt", "cash_and_equivalents"])

register("ev_ebitda", val.ev_ebitda, "Enterprise value / EBITDA.",
         {"enterprise_value_": NUM, "ebitda": NUM},
         ["enterprise_value_", "ebitda"])

register("ev_sales", val.ev_sales, "Enterprise value / revenue.",
         {"enterprise_value_": NUM, "revenue": NUM},
         ["enterprise_value_", "revenue"])

register("peg_ratio", val.peg_ratio,
         "P/E divided by growth IN PERCENTAGE POINTS (15 for 15%, not 0.15).",
         {"pe": NUM, "growth_rate_pct": NUM}, ["pe", "growth_rate_pct"])

register("roe", val.roe, "Return on equity = net income / shareholders equity.",
         {"net_income": NUM, "shareholders_equity": NUM},
         ["net_income", "shareholders_equity"])

register("roa", val.roa, "Return on assets = net income / total assets.",
         {"net_income": NUM, "total_assets": NUM},
         ["net_income", "total_assets"])

register("roic", val.roic,
         "Return on invested capital = EBIT(1-tax) / invested capital. "
         "tax_rate is a fraction.",
         {"ebit": NUM, "tax_rate": NUM, "invested_capital": NUM},
         ["ebit", "tax_rate", "invested_capital"])

register("free_cash_flow", val.free_cash_flow,
         "FCF = CFO - capex. Supply capex as a POSITIVE magnitude.",
         {"cash_flow_operations": NUM, "capital_expenditure": NUM},
         ["cash_flow_operations", "capital_expenditure"])

register("fcf_conversion", val.fcf_conversion,
         "FCF divided by net_income, ebitda or revenue (state which).",
         {"free_cash_flow_": NUM, "denominator": NUM,
          "denominator_kind": {"type": "string",
                               "enum": ["net_income", "ebitda", "revenue"]}},
         ["free_cash_flow_", "denominator"])

register("gross_margin", val.gross_margin, "(revenue - COGS) / revenue.",
         {"revenue": NUM, "cost_of_goods_sold": NUM},
         ["revenue", "cost_of_goods_sold"])

register("operating_margin", val.operating_margin,
         "Operating income / revenue.",
         {"operating_income": NUM, "revenue": NUM},
         ["operating_income", "revenue"])

register("net_margin", val.net_margin, "Net income / revenue.",
         {"net_income": NUM, "revenue": NUM}, ["net_income", "revenue"])

register("debt_to_equity", val.debt_to_equity, "Total debt / equity.",
         {"total_debt": NUM, "shareholders_equity": NUM},
         ["total_debt", "shareholders_equity"])

register("debt_to_assets", val.debt_to_assets, "Total debt / total assets.",
         {"total_debt": NUM, "total_assets": NUM},
         ["total_debt", "total_assets"])

register("net_debt_to_ebitda", val.net_debt_to_ebitda,
         "(debt - cash) / EBITDA. Negative means net cash, which is a "
         "strength.",
         {"total_debt": NUM, "cash_and_equivalents": NUM, "ebitda": NUM},
         ["total_debt", "cash_and_equivalents", "ebitda"])

register("interest_coverage", val.interest_coverage,
         "EBIT / interest expense.",
         {"ebit": NUM, "interest_expense": NUM}, ["ebit", "interest_expense"])

register("current_ratio", val.current_ratio,
         "Current assets / current liabilities.",
         {"current_assets": NUM, "current_liabilities": NUM},
         ["current_assets", "current_liabilities"])

register("quick_ratio", val.quick_ratio,
         "Acid test: (current assets - inventory) / current liabilities.",
         {"current_assets": NUM, "inventory": NUM,
          "current_liabilities": NUM},
         ["current_assets", "inventory", "current_liabilities"])

register("working_capital", val.working_capital,
         "Current assets - current liabilities.",
         {"current_assets": NUM, "current_liabilities": NUM},
         ["current_assets", "current_liabilities"])

register("cash_conversion_cycle", val.cash_conversion_cycle,
         "DSO + DIO - DPO, in days. Negative is supplier-financed.",
         {"days_sales_outstanding": NUM, "days_inventory_outstanding": NUM,
          "days_payables_outstanding": NUM},
         ["days_sales_outstanding", "days_inventory_outstanding",
          "days_payables_outstanding"])


# ==========================================================================
# TECHNICAL INDICATORS (R14)
# ==========================================================================

register("sma", tech.sma, "Simple moving average; returns the latest value.",
         {"prices": ARR, "period": INT}, ["prices", "period"])

register("ema", tech.ema,
         "Exponential moving average, alpha = 2/(period+1), SMA-seeded.",
         {"prices": ARR, "period": INT}, ["prices", "period"])

register("wma", tech.wma,
         "Linearly weighted moving average; most recent bar weighs most.",
         {"prices": ARR, "period": INT}, ["prices", "period"])

register("rsi", tech.rsi,
         "Relative Strength Index, Wilder-smoothed. Bounded 0-100.",
         {"prices": ARR, "period": INT}, ["prices"])

register("macd", tech.macd,
         "MACD line, signal line and histogram.",
         {"prices": ARR, "fast": INT, "slow": INT, "signal": INT},
         ["prices"])

register("rate_of_change", tech.rate_of_change,
         "Rate of change as a FRACTION over `period` bars.",
         {"prices": ARR, "period": INT}, ["prices"])

register("stochastic_oscillator", tech.stochastic_oscillator,
         "Stochastic %K and %D. Bounded 0-100.",
         {"highs": ARR, "lows": ARR, "closes": ARR, "k_period": INT,
          "d_period": INT}, ["highs", "lows", "closes"])

register("atr", tech.atr,
         "Average True Range, Wilder-smoothed. Absolute price units, NOT "
         "a percentage.",
         {"highs": ARR, "lows": ARR, "closes": ARR, "period": INT},
         ["highs", "lows", "closes"])

register("bollinger_bands", tech.bollinger_bands,
         "Bollinger Bands (population stdev by default).",
         {"prices": ARR, "period": INT, "num_std": NUM, "sample": BOOL},
         ["prices"])

register("adx", tech.adx,
         "ADX with +DI and -DI. Measures trend STRENGTH only; direction is "
         "sign(+DI - -DI).",
         {"highs": ARR, "lows": ARR, "closes": ARR, "period": INT},
         ["highs", "lows", "closes"])

register("donchian_channels", tech.donchian_channels,
         "Highest high and lowest low over the lookback window.",
         {"highs": ARR, "lows": ARR, "period": INT}, ["highs", "lows"])

register("vwap", tech.vwap,
         "Volume-weighted average price using typical price (H+L+C)/3. "
         "Session-anchored measure.",
         {"highs": ARR, "lows": ARR, "closes": ARR, "volumes": ARR},
         ["highs", "lows", "closes", "volumes"])

register("obv", tech.obv,
         "On-Balance Volume. Absolute level is arbitrary; read the slope.",
         {"closes": ARR, "volumes": ARR}, ["closes", "volumes"])


# ==========================================================================
# FIXED INCOME (R14)
# ==========================================================================

register("cash_flow_schedule", fi.cash_flow_schedule,
         "Full coupon schedule with principal at maturity.",
         {"face_value": NUM, "coupon_rate": NUM, "years_to_maturity": NUM,
          "frequency": INT},
         ["face_value", "coupon_rate", "years_to_maturity"])

register("bond_price", fi.bond_price,
         "Clean price of an option-free bond on a coupon date. Rates are "
         "FRACTIONS.",
         {"face_value": NUM, "coupon_rate": NUM, "ytm": NUM,
          "years_to_maturity": NUM, "frequency": INT},
         ["face_value", "coupon_rate", "ytm", "years_to_maturity"])

register("accrued_interest", fi.accrued_interest,
         "Accrued interest between coupon dates.",
         {"face_value": NUM, "coupon_rate": NUM,
          "days_since_last_coupon": NUM, "days_in_period": NUM,
          "frequency": INT,
          "day_count": {"type": "string",
                        "enum": ["30/360", "actual/360", "actual/365"]}},
         ["face_value", "coupon_rate", "days_since_last_coupon",
          "days_in_period"])

register("dirty_price", fi.dirty_price,
         "Dirty (invoice) price = clean + accrued. This is what the buyer "
         "pays.",
         {"clean_price": NUM, "accrued": NUM}, ["clean_price", "accrued"])

register("clean_price", fi.clean_price,
         "Clean price = dirty - accrued. Quoted prices are clean.",
         {"dirty_price_": NUM, "accrued": NUM}, ["dirty_price_", "accrued"])

register("yield_to_maturity", fi.yield_to_maturity,
         "YTM from a CLEAN price by bisection.",
         {"price": NUM, "face_value": NUM, "coupon_rate": NUM,
          "years_to_maturity": NUM, "frequency": INT},
         ["price", "face_value", "coupon_rate", "years_to_maturity"])

register("yield_to_call", fi.yield_to_call,
         "Yield to call. Report the lower of YTM and YTC for callable bonds.",
         {"price": NUM, "face_value": NUM, "coupon_rate": NUM,
          "years_to_call": NUM, "call_price": NUM, "frequency": INT},
         ["price", "face_value", "coupon_rate", "years_to_call",
          "call_price"])

register("macaulay_duration", fi.macaulay_duration,
         "PV-weighted average time to cash flows, in years.",
         {"face_value": NUM, "coupon_rate": NUM, "ytm": NUM,
          "years_to_maturity": NUM, "frequency": INT},
         ["face_value", "coupon_rate", "ytm", "years_to_maturity"])

register("modified_duration", fi.modified_duration,
         "Modified duration in years, reported POSITIVE. dP/P = -ModDur x dy.",
         {"face_value": NUM, "coupon_rate": NUM, "ytm": NUM,
          "years_to_maturity": NUM, "frequency": INT},
         ["face_value", "coupon_rate", "ytm", "years_to_maturity"])

register("convexity", fi.convexity,
         "Convexity in years^2, the second-order price/yield term.",
         {"face_value": NUM, "coupon_rate": NUM, "ytm": NUM,
          "years_to_maturity": NUM, "frequency": INT},
         ["face_value", "coupon_rate", "ytm", "years_to_maturity"])

register("dv01", fi.dv01,
         "Price change in currency for a 1bp yield rise, by full "
         "revaluation. Returned as a positive magnitude.",
         {"face_value": NUM, "coupon_rate": NUM, "ytm": NUM,
          "years_to_maturity": NUM, "frequency": INT},
         ["face_value", "coupon_rate", "ytm", "years_to_maturity"])


# ==========================================================================
# DERIVATIVES (R14)
# ==========================================================================

register("black_scholes", der.black_scholes,
         "European option price. volatility and rates are FRACTIONS; "
         "time_to_expiry is in YEARS (30 days = 0.0822).",
         {"spot": NUM, "strike": NUM, "time_to_expiry": NUM,
          "volatility": NUM, "risk_free_rate": NUM,
          "option_type": OPT_TYPE, "dividend_yield": NUM},
         ["spot", "strike", "time_to_expiry", "volatility",
          "risk_free_rate"])

register("black_76", der.black_76,
         "Option on a FORWARD/FUTURE. First argument is the forward price, "
         "not spot.",
         {"forward": NUM, "strike": NUM, "time_to_expiry": NUM,
          "volatility": NUM, "risk_free_rate": NUM, "option_type": OPT_TYPE},
         ["forward", "strike", "time_to_expiry", "volatility",
          "risk_free_rate"])

register("binomial_price", der.binomial_price,
         "Cox-Ross-Rubinstein tree. Set american true for early exercise.",
         {"spot": NUM, "strike": NUM, "time_to_expiry": NUM,
          "volatility": NUM, "risk_free_rate": NUM, "option_type": OPT_TYPE,
          "steps": INT, "american": BOOL, "dividend_yield": NUM},
         ["spot", "strike", "time_to_expiry", "volatility",
          "risk_free_rate"])

register("implied_volatility", der.implied_volatility,
         "Implied volatility by bisection. Refuses prices outside "
         "no-arbitrage bounds.",
         {"market_price": NUM, "spot": NUM, "strike": NUM,
          "time_to_expiry": NUM, "risk_free_rate": NUM,
          "option_type": OPT_TYPE, "dividend_yield": NUM},
         ["market_price", "spot", "strike", "time_to_expiry",
          "risk_free_rate"])

register("delta", der.delta,
         "Option delta (per share). Multiply by the contract multiplier for "
         "position delta.",
         {"spot": NUM, "strike": NUM, "time_to_expiry": NUM,
          "volatility": NUM, "risk_free_rate": NUM, "option_type": OPT_TYPE,
          "dividend_yield": NUM},
         ["spot", "strike", "time_to_expiry", "volatility",
          "risk_free_rate"])

register("gamma", der.gamma,
         "Option gamma. Identical for calls and puts at the same strike.",
         {"spot": NUM, "strike": NUM, "time_to_expiry": NUM,
          "volatility": NUM, "risk_free_rate": NUM, "dividend_yield": NUM},
         ["spot", "strike", "time_to_expiry", "volatility",
          "risk_free_rate"])

register("vega", der.vega,
         "Option vega per 1.00 of vol (100 vol points). Divide by 100 for "
         "one vol point.",
         {"spot": NUM, "strike": NUM, "time_to_expiry": NUM,
          "volatility": NUM, "risk_free_rate": NUM, "dividend_yield": NUM},
         ["spot", "strike", "time_to_expiry", "volatility",
          "risk_free_rate"])

register("theta", der.theta,
         "Option theta per YEAR; inputs.per_day gives daily decay. Negative "
         "for long options.",
         {"spot": NUM, "strike": NUM, "time_to_expiry": NUM,
          "volatility": NUM, "risk_free_rate": NUM, "option_type": OPT_TYPE,
          "dividend_yield": NUM},
         ["spot", "strike", "time_to_expiry", "volatility",
          "risk_free_rate"])

register("rho", der.rho,
         "Option rho per 1.00 (100%) change in rate.",
         {"spot": NUM, "strike": NUM, "time_to_expiry": NUM,
          "volatility": NUM, "risk_free_rate": NUM, "option_type": OPT_TYPE,
          "dividend_yield": NUM},
         ["spot", "strike", "time_to_expiry", "volatility",
          "risk_free_rate"])

register("contract_payoff", der.contract_payoff,
         "Payoff and profit at expiry for a single-leg option position. "
         "Distinguishes payoff from profit net of premium.",
         {"spot_at_expiry": NUM, "strike": NUM, "premium": NUM,
          "option_type": OPT_TYPE, "position": SIDE, "contracts": NUM,
          "multiplier": NUM}, ["spot_at_expiry", "strike", "premium"])

register("breakeven", der.breakeven,
         "Underlying price at expiry where the position recovers its premium.",
         {"strike": NUM, "premium": NUM, "option_type": OPT_TYPE},
         ["strike", "premium"])

register("margin_estimate", der.margin_estimate,
         "GENERIC initial and maintenance margin ESTIMATE. Not a broker "
         "requirement; confirm before sizing.",
         {"position_value": NUM, "leverage": NUM,
          "maintenance_margin_rate": NUM}, ["position_value", "leverage"])

register("liquidation_estimate", der.liquidation_estimate,
         "GENERIC liquidation price ESTIMATE. Ignores funding and fees, "
         "which move the real trigger closer to entry.",
         {"entry_price": NUM, "leverage": NUM,
          "maintenance_margin_rate": NUM, "side": SIDE},
         ["entry_price", "leverage"])


def tool_schemas():
    """JSON schemas for injection into the model's chat template."""
    return [t["schema"] for t in _REGISTRY.values()]


def tool_names():
    return sorted(_REGISTRY)


def _coerce(value, spec):
    """Coerce model-supplied arguments, accepting Persian numerals."""
    t = spec.get("type")
    if t == "number":
        if isinstance(value, bool):
            raise TypeError("boolean supplied where number expected")
        if isinstance(value, (int, float)):
            return float(value)
        return parse_number(value)          # handles ۸٫۴ , ۱۰۰٬۰۰۰ etc.
    if t == "integer":
        # Periods, steps and coupon frequencies must be whole numbers. A
        # model emitting 14.0 is fine; 14.5 is a real error and is refused
        # here rather than silently truncated inside an indicator.
        if isinstance(value, bool):
            raise TypeError("boolean supplied where integer expected")
        f = (float(value) if isinstance(value, (int, float))
             else parse_number(value))
        if f != int(f):
            raise ValueError("expected a whole number, got %g" % f)
        return int(f)
    if t == "boolean":
        if isinstance(value, bool):
            return value
        raise TypeError("expected a boolean, got %s" % type(value).__name__)
    if t == "array":
        if not isinstance(value, (list, tuple)):
            raise TypeError("expected array, got %s" % type(value).__name__)
        return [_coerce(v, spec["items"]) for v in value]
    if t == "string":
        s = str(value)
        if "enum" in spec and s not in spec["enum"]:
            raise ValueError("invalid value %r; expected one of %s"
                             % (s, spec["enum"]))
        return s
    return value


def call_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a whitelisted tool.

    Always returns a dict. On failure returns {"ok": False, "error": ...}
    rather than raising, so the caller can hand the error back to the model
    verbatim -- the model must report the failure, not paper over it.
    """
    if name not in _REGISTRY:
        return {"ok": False, "error": "unknown_tool",
                "message": "Tool %r is not registered. Available: %s"
                           % (name, ", ".join(tool_names()))}
    entry = _REGISTRY[name]
    props = entry["schema"]["function"]["parameters"]["properties"]
    required = entry["schema"]["function"]["parameters"]["required"]

    if not isinstance(arguments, dict):
        return {"ok": False, "error": "bad_arguments",
                "message": "arguments must be an object"}

    unknown = set(arguments) - set(props)
    if unknown:
        return {"ok": False, "error": "unknown_argument",
                "message": "Unexpected argument(s): %s" % ", ".join(sorted(unknown))}

    missing = [r for r in required if r not in arguments]
    if missing:
        return {"ok": False, "error": "missing_argument",
                "message": "Missing required argument(s): %s" % ", ".join(missing)}

    kwargs = {}
    for k, v in arguments.items():
        try:
            kwargs[k] = _coerce(v, props[k])
        except Exception as e:
            return {"ok": False, "error": "invalid_argument",
                    "message": "Argument %r: %s" % (k, e)}

    # Drop args the function does not accept (schema/impl drift guard).
    sig = inspect.signature(entry["fn"])
    kwargs = {k: v for k, v in kwargs.items() if k in sig.parameters}

    try:
        res = entry["fn"](**kwargs)
    except Exception as e:
        return {"ok": False, "error": type(e).__name__, "message": str(e),
                "guidance": "Report this refusal to the user. Do NOT substitute "
                            "an estimated value."}

    return {"ok": True, "name": res.name, "value": res.value,
            "formula": res.formula, "inputs": res.inputs,
            "units": res.units, "notes": res.notes, "label": res.label}
