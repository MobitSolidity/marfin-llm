"""
Deterministic derivatives pricing and Greeks (master prompt SS.5.3).

Stdlib only. The normal CDF uses math.erf, which is exact to double precision
-- no approximation table, no scipy.

CONVENTIONS -- ALL EXPLICIT
---------------------------
  - rate (r), dividend yield (q) and volatility (sigma) are ANNUAL fractions
    with CONTINUOUS compounding (0.20 = 20% vol).
  - time_to_expiry (T) is in YEARS. 30 days = 30/365.
  - Theta is returned BOTH per year and per calendar day. Quoting the annual
    figure as if it were daily overstates decay by ~365x, and this is one of
    the most common option-quoting errors, so both are always present.
  - Vega is returned per 1.00 of vol (per 100 vol points) AND per 1 vol point.
    "Vega = 0.15" is meaningless without that unit.

WHAT THIS MODULE DOES NOT DO
----------------------------
American early exercise is priced by the binomial tree only; Black-Scholes
here is European. Margin and liquidation functions are GENERIC estimates and
are labelled ESTIMATED, because real requirements are broker- and
regime-specific. They must never be presented as a broker's actual number.
"""

from typing import Optional, Dict
import math

from calc.returns_risk import CalcResult

SQRT_2PI = math.sqrt(2.0 * math.pi)
DAYS_PER_YEAR = 365.0


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / SQRT_2PI


def _num(x, name):
    if x is None:
        raise ValueError("%s: value is None" % name)
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        raise TypeError("%s: non-numeric value %r" % (name, x))
    if math.isnan(x) or math.isinf(x):
        raise ValueError("%s: NaN/Inf" % name)
    return float(x)


def _pos(x, name):
    v = _num(x, name)
    if v <= 0:
        raise ValueError("%s must be > 0, got %g" % (name, v))
    return v


def _opt_type(kind):
    k = str(kind).lower().strip()
    if k in ("c", "call"):
        return "call"
    if k in ("p", "put"):
        return "put"
    raise ValueError("option_type must be 'call' or 'put', got %r" % kind)


def _d1_d2(s, k, r, q, sigma, t):
    v = sigma * math.sqrt(t)
    d1 = (math.log(s / k) + (r - q + 0.5 * sigma * sigma) * t) / v
    return d1, d1 - v


# --------------------------------------------------------------------------
# Pricing
# --------------------------------------------------------------------------

def black_scholes(spot: float, strike: float, time_to_expiry: float,
                  volatility: float, risk_free_rate: float,
                  option_type: str = "call",
                  dividend_yield: float = 0.0) -> CalcResult:
    """
    European option price (Black-Scholes-Merton, continuous dividend yield).

    Refuses T <= 0 and sigma <= 0 rather than returning intrinsic value
    silently: an expired or zero-vol option is a different object, and
    quietly substituting intrinsic hides an input error.
    """
    s = _pos(spot, "spot")
    k = _pos(strike, "strike")
    t = _pos(time_to_expiry, "time_to_expiry")
    sigma = _pos(volatility, "volatility")
    r = _num(risk_free_rate, "risk_free_rate")
    q = _num(dividend_yield, "dividend_yield")
    kind = _opt_type(option_type)
    if sigma > 5.0:
        raise ValueError("volatility %g = %g%% is implausible; pass a "
                         "fraction (0.20 for 20%%)" % (sigma, sigma * 100))
    if t > 100:
        raise ValueError("time_to_expiry %g years is implausible; T is in "
                         "YEARS (30 days = 0.0822)" % t)

    d1, d2 = _d1_d2(s, k, r, q, sigma, t)
    df_r = math.exp(-r * t)
    df_q = math.exp(-q * t)
    if kind == "call":
        price = s * df_q * _norm_cdf(d1) - k * df_r * _norm_cdf(d2)
    else:
        price = k * df_r * _norm_cdf(-d2) - s * df_q * _norm_cdf(-d1)
    return CalcResult("black_scholes", price,
                      "call = S e^-qT N(d1) - K e^-rT N(d2); "
                      "put = K e^-rT N(-d2) - S e^-qT N(-d1)",
                      {"spot": s, "strike": k, "time_to_expiry_years": t,
                       "volatility": sigma, "risk_free_rate": r,
                       "dividend_yield": q, "option_type": kind,
                       "d1": d1, "d2": d2}, "currency per share",
                      "European exercise. Model output, not a market quote.")


def black_76(forward: float, strike: float, time_to_expiry: float,
             volatility: float, risk_free_rate: float,
             option_type: str = "call") -> CalcResult:
    """
    Black-76: options on FORWARDS/FUTURES.

    The first argument is the FORWARD price, not spot. Passing spot into
    Black-76 silently misprices by the cost of carry -- the discount factor
    applies to the whole payoff, and there is no separate dividend term.
    """
    f = _pos(forward, "forward")
    k = _pos(strike, "strike")
    t = _pos(time_to_expiry, "time_to_expiry")
    sigma = _pos(volatility, "volatility")
    r = _num(risk_free_rate, "risk_free_rate")
    kind = _opt_type(option_type)
    v = sigma * math.sqrt(t)
    d1 = (math.log(f / k) + 0.5 * sigma * sigma * t) / v
    d2 = d1 - v
    df = math.exp(-r * t)
    if kind == "call":
        price = df * (f * _norm_cdf(d1) - k * _norm_cdf(d2))
    else:
        price = df * (k * _norm_cdf(-d2) - f * _norm_cdf(-d1))
    return CalcResult("black_76", price,
                      "call = e^-rT [F N(d1) - K N(d2)]; "
                      "put = e^-rT [K N(-d2) - F N(-d1)]",
                      {"forward": f, "strike": k, "time_to_expiry_years": t,
                       "volatility": sigma, "risk_free_rate": r,
                       "option_type": kind, "d1": d1, "d2": d2},
                      "currency per unit",
                      "Input is the FORWARD price, not spot.")


def binomial_price(spot: float, strike: float, time_to_expiry: float,
                   volatility: float, risk_free_rate: float,
                   option_type: str = "call", steps: int = 200,
                   american: bool = False,
                   dividend_yield: float = 0.0) -> CalcResult:
    """
    Cox-Ross-Rubinstein binomial tree. american=True allows early exercise.

    With american=False and enough steps this converges to Black-Scholes;
    the test suite uses exactly that as an independent cross-check of both
    implementations.
    """
    s = _pos(spot, "spot")
    k = _pos(strike, "strike")
    t = _pos(time_to_expiry, "time_to_expiry")
    sigma = _pos(volatility, "volatility")
    r = _num(risk_free_rate, "risk_free_rate")
    q = _num(dividend_yield, "dividend_yield")
    kind = _opt_type(option_type)
    if isinstance(steps, bool) or not isinstance(steps, (int, float)):
        raise TypeError("steps must be an integer")
    if float(steps) != int(steps):
        raise ValueError("steps must be a whole number, got %r" % steps)
    steps = int(steps)
    if steps < 1:
        raise ValueError("steps must be >= 1, got %d" % steps)
    if steps > 5000:
        raise ValueError("steps=%d exceeds the 5000 cap (CPU budget)" % steps)

    dt = t / steps
    u = math.exp(sigma * math.sqrt(dt))
    d = 1.0 / u
    disc = math.exp(-r * dt)
    p = (math.exp((r - q) * dt) - d) / (u - d)
    if not (0.0 < p < 1.0):
        raise ValueError(
            "risk-neutral probability p=%g is outside (0,1); the tree is "
            "arbitrage-inconsistent. Increase steps or check that "
            "volatility is not too small for the rate." % p)

    values = []
    for i in range(steps + 1):
        st = s * (u ** (steps - i)) * (d ** i)
        values.append(max(st - k, 0.0) if kind == "call"
                      else max(k - st, 0.0))
    for step in range(steps - 1, -1, -1):
        for i in range(step + 1):
            cont = disc * (p * values[i] + (1.0 - p) * values[i + 1])
            if american:
                st = s * (u ** (step - i)) * (d ** i)
                ex = (st - k) if kind == "call" else (k - st)
                cont = max(cont, ex, 0.0)
            values[i] = cont
    return CalcResult("binomial_price", values[0],
                      "Cox-Ross-Rubinstein tree; u = e^(sigma sqrt(dt)), "
                      "d = 1/u, p = (e^((r-q)dt) - d)/(u - d)",
                      {"spot": s, "strike": k, "time_to_expiry_years": t,
                       "volatility": sigma, "risk_free_rate": r,
                       "dividend_yield": q, "option_type": kind,
                       "steps": steps,
                       "exercise": "american" if american else "european",
                       "up_factor": u, "risk_neutral_p": p},
                      "currency per share")


def implied_volatility(market_price: float, spot: float, strike: float,
                       time_to_expiry: float, risk_free_rate: float,
                       option_type: str = "call",
                       dividend_yield: float = 0.0) -> CalcResult:
    """
    Implied volatility by bisection on the Black-Scholes price.

    Bisection, not Newton: vega collapses toward zero for deep in/out-of-the-
    money options, and Newton then diverges or returns nonsense. Bisection is
    slower and always right, which is the correct trade here.

    Arbitrage bounds are checked FIRST. A price below intrinsic or above the
    spot has no implied vol at all, and returning a number for it would be
    fabrication.
    """
    p = _pos(market_price, "market_price")
    s = _pos(spot, "spot")
    k = _pos(strike, "strike")
    t = _pos(time_to_expiry, "time_to_expiry")
    r = _num(risk_free_rate, "risk_free_rate")
    q = _num(dividend_yield, "dividend_yield")
    kind = _opt_type(option_type)

    df_r = math.exp(-r * t)
    df_q = math.exp(-q * t)
    if kind == "call":
        lo_bound = max(s * df_q - k * df_r, 0.0)
        hi_bound = s * df_q
    else:
        lo_bound = max(k * df_r - s * df_q, 0.0)
        hi_bound = k * df_r
    if p < lo_bound - 1e-12:
        raise ValueError(
            "market_price %g is below the no-arbitrage lower bound %g; no "
            "implied volatility exists. Check the price, or that the option "
            "type and expiry are right." % (p, lo_bound))
    if p > hi_bound + 1e-12:
        raise ValueError(
            "market_price %g exceeds the no-arbitrage upper bound %g; no "
            "implied volatility exists." % (p, hi_bound))

    lo, hi = 1e-6, 5.0
    f_lo = black_scholes(s, k, t, lo, r, kind, q).value - p
    f_hi = black_scholes(s, k, t, hi, r, kind, q).value - p
    if f_lo > 0:
        raise ValueError("market_price %g is below the price at ~0%% vol; "
                         "no solution" % p)
    if f_hi < 0:
        raise ValueError("market_price %g implies volatility above 500%%; "
                         "refusing to extrapolate" % p)
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if black_scholes(s, k, t, mid, r, kind, q).value - p < 0:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-12:
            break
    iv = (lo + hi) / 2.0
    return CalcResult("implied_volatility", iv,
                      "solve BS(sigma) = market_price for sigma (bisection)",
                      {"market_price": p, "spot": s, "strike": k,
                       "time_to_expiry_years": t, "risk_free_rate": r,
                       "dividend_yield": q, "option_type": kind,
                       "method": "bisection", "bracket": [1e-6, 5.0],
                       "lower_arb_bound": lo_bound,
                       "upper_arb_bound": hi_bound},
                      "fraction (annualized)",
                      "IV is model-dependent: it is the vol that makes THIS "
                      "model match the quote, not a measured property.")


# --------------------------------------------------------------------------
# Greeks
# --------------------------------------------------------------------------

def _greek_inputs(spot, strike, time_to_expiry, volatility, risk_free_rate,
                  option_type, dividend_yield):
    s = _pos(spot, "spot")
    k = _pos(strike, "strike")
    t = _pos(time_to_expiry, "time_to_expiry")
    sigma = _pos(volatility, "volatility")
    r = _num(risk_free_rate, "risk_free_rate")
    q = _num(dividend_yield, "dividend_yield")
    kind = _opt_type(option_type)
    d1, d2 = _d1_d2(s, k, r, q, sigma, t)
    return s, k, t, sigma, r, q, kind, d1, d2


def delta(spot: float, strike: float, time_to_expiry: float,
          volatility: float, risk_free_rate: float,
          option_type: str = "call",
          dividend_yield: float = 0.0) -> CalcResult:
    """dPrice/dSpot. Call in (0,1); put in (-1,0)."""
    s, k, t, sg, r, q, kind, d1, d2 = _greek_inputs(
        spot, strike, time_to_expiry, volatility, risk_free_rate,
        option_type, dividend_yield)
    df_q = math.exp(-q * t)
    v = df_q * _norm_cdf(d1) if kind == "call" else -df_q * _norm_cdf(-d1)
    return CalcResult("delta", v,
                      "call: e^-qT N(d1); put: -e^-qT N(-d1)",
                      {"spot": s, "strike": k, "time_to_expiry_years": t,
                       "volatility": sg, "risk_free_rate": r,
                       "dividend_yield": q, "option_type": kind, "d1": d1},
                      "per 1.00 move in spot",
                      "Delta is per SHARE. Multiply by contract multiplier "
                      "(typically 100) for position delta.")


def gamma(spot: float, strike: float, time_to_expiry: float,
          volatility: float, risk_free_rate: float,
          dividend_yield: float = 0.0) -> CalcResult:
    """
    d2Price/dSpot2. Identical for calls and puts, so option_type is not an
    argument -- offering one would imply a difference that does not exist.
    """
    s, k, t, sg, r, q, _, d1, _ = _greek_inputs(
        spot, strike, time_to_expiry, volatility, risk_free_rate,
        "call", dividend_yield)
    v = math.exp(-q * t) * _norm_pdf(d1) / (s * sg * math.sqrt(t))
    return CalcResult("gamma", v, "e^-qT n(d1) / (S sigma sqrt(T))",
                      {"spot": s, "strike": k, "time_to_expiry_years": t,
                       "volatility": sg, "risk_free_rate": r,
                       "dividend_yield": q, "d1": d1},
                      "delta change per 1.00 move in spot",
                      "Same value for calls and puts at the same strike.")


def vega(spot: float, strike: float, time_to_expiry: float,
         volatility: float, risk_free_rate: float,
         dividend_yield: float = 0.0) -> CalcResult:
    """
    dPrice/dVol. Identical for calls and puts.

    Returned per 1.00 of vol (i.e. per 100 vol points); `per_vol_point` in the
    inputs gives the per-1%-move figure traders usually quote.
    """
    s, k, t, sg, r, q, _, d1, _ = _greek_inputs(
        spot, strike, time_to_expiry, volatility, risk_free_rate,
        "call", dividend_yield)
    v = s * math.exp(-q * t) * _norm_pdf(d1) * math.sqrt(t)
    return CalcResult("vega", v, "S e^-qT n(d1) sqrt(T)",
                      {"spot": s, "strike": k, "time_to_expiry_years": t,
                       "volatility": sg, "risk_free_rate": r,
                       "dividend_yield": q, "d1": d1,
                       "per_vol_point": v / 100.0},
                      "currency per 1.00 (100 vol points) change in vol",
                      "Divide by 100 for the change per one vol point.")


def theta(spot: float, strike: float, time_to_expiry: float,
          volatility: float, risk_free_rate: float,
          option_type: str = "call",
          dividend_yield: float = 0.0) -> CalcResult:
    """
    dPrice/dTime. NEGATIVE for long options in the normal case.

    Value is the ANNUAL theta; `per_day` (annual/365) is also supplied.
    Quoting annual theta as daily overstates decay by ~365x.
    """
    s, k, t, sg, r, q, kind, d1, d2 = _greek_inputs(
        spot, strike, time_to_expiry, volatility, risk_free_rate,
        option_type, dividend_yield)
    df_q = math.exp(-q * t)
    df_r = math.exp(-r * t)
    term1 = -(s * df_q * _norm_pdf(d1) * sg) / (2.0 * math.sqrt(t))
    if kind == "call":
        v = (term1 - r * k * df_r * _norm_cdf(d2)
             + q * s * df_q * _norm_cdf(d1))
    else:
        v = (term1 + r * k * df_r * _norm_cdf(-d2)
             - q * s * df_q * _norm_cdf(-d1))
    return CalcResult("theta", v,
                      "-(S e^-qT n(d1) sigma)/(2 sqrt(T)) -/+ rK e^-rT N(+/-d2) "
                      "+/- qS e^-qT N(+/-d1)",
                      {"spot": s, "strike": k, "time_to_expiry_years": t,
                       "volatility": sg, "risk_free_rate": r,
                       "dividend_yield": q, "option_type": kind,
                       "per_day": v / DAYS_PER_YEAR,
                       "days_per_year": DAYS_PER_YEAR},
                      "currency per YEAR",
                      "Value is ANNUAL. Use inputs.per_day for daily decay.")


def rho(spot: float, strike: float, time_to_expiry: float,
        volatility: float, risk_free_rate: float,
        option_type: str = "call",
        dividend_yield: float = 0.0) -> CalcResult:
    """dPrice/dRate. Positive for calls, negative for puts."""
    s, k, t, sg, r, q, kind, d1, d2 = _greek_inputs(
        spot, strike, time_to_expiry, volatility, risk_free_rate,
        option_type, dividend_yield)
    df_r = math.exp(-r * t)
    v = (k * t * df_r * _norm_cdf(d2) if kind == "call"
         else -k * t * df_r * _norm_cdf(-d2))
    return CalcResult("rho", v,
                      "call: K T e^-rT N(d2); put: -K T e^-rT N(-d2)",
                      {"spot": s, "strike": k, "time_to_expiry_years": t,
                       "volatility": sg, "risk_free_rate": r,
                       "dividend_yield": q, "option_type": kind, "d2": d2,
                       "per_bp": v / 10000.0},
                      "currency per 1.00 (100%) change in rate",
                      "Divide by 10000 for a 1bp move.")


# --------------------------------------------------------------------------
# Payoff and breakeven
# --------------------------------------------------------------------------

def contract_payoff(spot_at_expiry: float, strike: float, premium: float,
                    option_type: str = "call", position: str = "long",
                    contracts: float = 1.0, multiplier: float = 100.0
                    ) -> CalcResult:
    """
    Payoff and profit/loss at expiry for a single-leg option position.

    Distinguishes PAYOFF (intrinsic value at expiry) from PROFIT (payoff net
    of premium). Reporting one as the other is how a "profitable" trade turns
    out to have lost money.

    A short position's loss is unbounded for calls; the note says so rather
    than letting a single scenario number imply a bounded risk.
    """
    st = _num(spot_at_expiry, "spot_at_expiry")
    if st < 0:
        raise ValueError("spot_at_expiry must be >= 0, got %g" % st)
    k = _pos(strike, "strike")
    prem = _num(premium, "premium")
    if prem < 0:
        raise ValueError("premium must be >= 0 (a magnitude), got %g" % prem)
    kind = _opt_type(option_type)
    pos = str(position).lower().strip()
    if pos not in ("long", "short"):
        raise ValueError("position must be 'long' or 'short', got %r"
                         % position)
    n = _num(contracts, "contracts")
    if n <= 0:
        raise ValueError("contracts must be > 0, got %g" % n)
    m = _pos(multiplier, "multiplier")

    intrinsic = max(st - k, 0.0) if kind == "call" else max(k - st, 0.0)
    sign = 1.0 if pos == "long" else -1.0
    payoff = sign * intrinsic * n * m
    net_premium = sign * -prem * n * m          # long pays, short receives
    profit = payoff + net_premium

    note = ("Payoff is intrinsic value at expiry; profit is net of premium.")
    if pos == "short" and kind == "call":
        note += (" A short call has UNBOUNDED loss above the strike; this is "
                 "one scenario, not a maximum.")
    elif pos == "short" and kind == "put":
        note += (" A short put's maximum loss is (strike - 0) x size, "
                 "realized if the underlying goes to zero.")

    return CalcResult("contract_payoff",
                      {"intrinsic_per_share": intrinsic, "payoff": payoff,
                       "premium_cash_flow": net_premium, "profit": profit},
                      "intrinsic = max(S-K,0) call / max(K-S,0) put; "
                      "profit = +/-intrinsic x n x mult -/+ premium x n x mult",
                      {"spot_at_expiry": st, "strike": k, "premium": prem,
                       "option_type": kind, "position": pos, "contracts": n,
                       "multiplier": m}, "currency", note)


def breakeven(strike: float, premium: float, option_type: str = "call"
              ) -> CalcResult:
    """
    Underlying price at expiry where the position exactly recovers premium.

    Call: K + premium. Put: K - premium. Same for long and short (it is the
    crossover point, not a P/L).
    """
    k = _pos(strike, "strike")
    prem = _num(premium, "premium")
    if prem < 0:
        raise ValueError("premium must be >= 0, got %g" % prem)
    kind = _opt_type(option_type)
    be = k + prem if kind == "call" else k - prem
    if be < 0:
        raise ValueError("computed breakeven %g is negative; premium (%g) "
                         "exceeds the strike (%g), which is not possible for "
                         "a rational put quote" % (be, prem, k))
    return CalcResult("breakeven", be,
                      "call: strike + premium; put: strike - premium",
                      {"strike": k, "premium": prem, "option_type": kind},
                      "underlying price",
                      "Expiry breakeven, ignoring commissions, financing and "
                      "any early assignment.")


# --------------------------------------------------------------------------
# Margin and liquidation -- ESTIMATES, clearly labelled
# --------------------------------------------------------------------------

def margin_estimate(position_value: float, leverage: float,
                    maintenance_margin_rate: float = 0.25) -> CalcResult:
    """
    Generic initial and maintenance margin ESTIMATE.

    Labelled ESTIMATED, not COMPUTED. Real requirements depend on the broker,
    the instrument, portfolio offsets and current volatility regime. Presenting
    this as a broker's actual requirement would be fabrication, and an
    underestimate is exactly what precedes a forced liquidation.
    """
    pv = _pos(position_value, "position_value")
    lev = _num(leverage, "leverage")
    if lev < 1.0:
        raise ValueError("leverage must be >= 1.0, got %g" % lev)
    if lev > 100.0:
        raise ValueError("leverage %g is implausible" % lev)
    mmr = _num(maintenance_margin_rate, "maintenance_margin_rate")
    if not (0.0 < mmr < 1.0):
        raise ValueError("maintenance_margin_rate must be a fraction in "
                         "(0,1), got %g" % mmr)
    initial = pv / lev
    maintenance = pv * mmr
    if maintenance > initial:
        raise ValueError(
            "maintenance margin (%g) exceeds initial margin (%g) at leverage "
            "%g: this position would be liquidatable the moment it is opened. "
            "Reduce leverage." % (maintenance, initial, lev))
    return CalcResult("margin_estimate",
                      {"initial_margin": initial,
                       "maintenance_margin": maintenance,
                       "buffer": initial - maintenance},
                      "initial = position_value / leverage; "
                      "maintenance = position_value x maintenance_rate",
                      {"position_value": pv, "leverage": lev,
                       "maintenance_margin_rate": mmr}, "currency",
                      "GENERIC estimate. Confirm actual requirements with the "
                      "broker before sizing a position.",
                      label="ESTIMATED")


def liquidation_estimate(entry_price: float, leverage: float,
                         maintenance_margin_rate: float = 0.25,
                         side: str = "long") -> CalcResult:
    """
    Approximate liquidation price for a leveraged position.

    long:  P_liq = entry x (1 - 1/leverage + mmr)
    short: P_liq = entry x (1 + 1/leverage - mmr)

    Labelled ESTIMATED. Ignores funding, fees, partial liquidation and
    auto-deleveraging, all of which move the real trigger ADVERSELY. Treating
    this as the exact trigger is precisely how positions get liquidated a
    little earlier than the trader expected.
    """
    e = _pos(entry_price, "entry_price")
    lev = _num(leverage, "leverage")
    if lev <= 1.0:
        raise ValueError("liquidation only applies to leverage > 1.0, got %g"
                         % lev)
    if lev > 100.0:
        raise ValueError("leverage %g is implausible" % lev)
    mmr = _num(maintenance_margin_rate, "maintenance_margin_rate")
    if not (0.0 <= mmr < 1.0):
        raise ValueError("maintenance_margin_rate must be in [0,1), got %g"
                         % mmr)
    s = str(side).lower().strip()
    if s not in ("long", "short"):
        raise ValueError("side must be 'long' or 'short', got %r" % side)

    if s == "long":
        p = e * (1.0 - 1.0 / lev + mmr)
        if p >= e:
            raise ValueError(
                "computed long liquidation price (%g) is at or above entry "
                "(%g): maintenance rate %g is too high for leverage %g."
                % (p, e, mmr, lev))
        move = (p - e) / e
    else:
        p = e * (1.0 + 1.0 / lev - mmr)
        if p <= e:
            raise ValueError(
                "computed short liquidation price (%g) is at or below entry "
                "(%g): maintenance rate %g is too high for leverage %g."
                % (p, e, mmr, lev))
        move = (p - e) / e

    return CalcResult("liquidation_estimate", p,
                      "long: entry x (1 - 1/leverage + mmr); "
                      "short: entry x (1 + 1/leverage - mmr)",
                      {"entry_price": e, "leverage": lev,
                       "maintenance_margin_rate": mmr, "side": s,
                       "move_to_liquidation": move,
                       "move_to_liquidation_pct": move * 100.0},
                      "underlying price",
                      "GENERIC estimate ignoring funding, fees and partial "
                      "liquidation, all of which move the real trigger "
                      "CLOSER to entry. Never rely on this as the exact "
                      "level.",
                      label="ESTIMATED")
