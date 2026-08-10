"""
Deterministic returns and risk calculations (master prompt SS.5.3).

DESIGN RULES (these are what make the engine trustworthy):
  1. Pure Python stdlib. No numpy/scipy. The target is a Windows box with no
     build toolchain; a dependency that fails to install is a broken tool.
  2. Every function raises on invalid input rather than returning a wrong
     number. A silent NaN in a risk calculation is worse than a crash.
  3. Every function returns a CalcResult carrying the formula, the inputs, and
     the result -- SS.5.3 requires material calculations to show their working,
     and the LLM must never restate a number without provenance.
  4. No function guesses a convention. Periods-per-year, risk-free rate, and
     population-vs-sample are explicit arguments, because getting them wrong
     silently is the single most common source of wrong finance numbers.

The LLM's job is to CHOOSE these functions and INTERPRET their output.
It must never compute these quantities itself.
"""

from dataclasses import dataclass, field
from typing import Sequence, Optional, Dict, Any
import math

# Common periods-per-year conventions. Passed explicitly, never inferred.
PERIODS = {"daily": 252, "weekly": 52, "monthly": 12, "quarterly": 4, "annual": 1}


@dataclass
class CalcResult:
    """A calculation plus its provenance. Required by SS.5.3."""
    name: str
    value: Any
    formula: str
    inputs: Dict[str, Any] = field(default_factory=dict)
    units: str = ""
    notes: str = ""
    label: str = "COMPUTED"

    def __repr__(self):
        v = self.value
        vs = "%.6g" % v if isinstance(v, float) else str(v)
        return "%s = %s %s  [%s]" % (self.name, vs, self.units, self.label)


# --------------------------------------------------------------------------
# validation helpers
# --------------------------------------------------------------------------

def _check_series(xs: Sequence[float], name: str, minlen: int = 2):
    if xs is None:
        raise ValueError("%s: series is None" % name)
    if len(xs) < minlen:
        raise ValueError("%s: need at least %d points, got %d"
                         % (name, minlen, len(xs)))
    for i, x in enumerate(xs):
        if x is None:
            raise ValueError("%s: None at index %d" % (name, i))
        if isinstance(x, bool) or not isinstance(x, (int, float)):
            raise TypeError("%s: non-numeric at index %d: %r" % (name, i, x))
        if math.isnan(x) or math.isinf(x):
            raise ValueError("%s: NaN/Inf at index %d" % (name, i))


def _periods_per_year(freq) -> int:
    if isinstance(freq, (int, float)):
        if freq <= 0:
            raise ValueError("periods_per_year must be > 0")
        return int(freq)
    if freq not in PERIODS:
        raise ValueError("unknown frequency %r; use one of %s or an integer"
                         % (freq, sorted(PERIODS)))
    return PERIODS[freq]


def mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs)


def stdev(xs: Sequence[float], sample: bool = True) -> float:
    """Standard deviation. sample=True uses n-1 (Bessel), the finance default."""
    _check_series(xs, "stdev", minlen=2)
    n = len(xs)
    m = mean(xs)
    denom = n - 1 if sample else n
    if denom <= 0:
        raise ValueError("stdev: insufficient data for chosen convention")
    return math.sqrt(sum((x - m) ** 2 for x in xs) / denom)


# --------------------------------------------------------------------------
# returns
# --------------------------------------------------------------------------

def simple_return(start: float, end: float) -> CalcResult:
    if start == 0:
        raise ZeroDivisionError("simple_return: start value is zero")
    if start < 0:
        raise ValueError("simple_return: negative start value is undefined")
    v = (end - start) / start
    return CalcResult("simple_return", v, "(end - start) / start",
                      {"start": start, "end": end}, "fraction")


def log_return(start: float, end: float) -> CalcResult:
    if start <= 0 or end <= 0:
        raise ValueError("log_return: requires strictly positive prices")
    v = math.log(end / start)
    return CalcResult("log_return", v, "ln(end / start)",
                      {"start": start, "end": end}, "fraction")


def cagr(start: float, end: float, years: float) -> CalcResult:
    if start <= 0:
        raise ValueError("cagr: start must be > 0")
    if years <= 0:
        raise ValueError("cagr: years must be > 0")
    if end < 0:
        raise ValueError("cagr: end must be >= 0")
    v = (end / start) ** (1.0 / years) - 1.0
    return CalcResult("cagr", v, "(end/start)^(1/years) - 1",
                      {"start": start, "end": end, "years": years}, "fraction/yr")


def annualized_return(returns: Sequence[float], freq="daily") -> CalcResult:
    """Geometric annualization -- compounds, does not average."""
    _check_series(returns, "annualized_return", minlen=1)
    ppy = _periods_per_year(freq)
    growth = 1.0
    for r in returns:
        if r <= -1.0:
            raise ValueError("annualized_return: return <= -100% wipes the "
                             "series; geometric compounding is undefined")
        growth *= (1.0 + r)
    n = len(returns)
    v = growth ** (ppy / n) - 1.0
    return CalcResult("annualized_return", v,
                      "(prod(1+r))^(periods_per_year/n) - 1",
                      {"n": n, "periods_per_year": ppy}, "fraction/yr")


def annualized_volatility(returns: Sequence[float], freq="daily",
                          sample: bool = True) -> CalcResult:
    _check_series(returns, "annualized_volatility", minlen=2)
    ppy = _periods_per_year(freq)
    sd = stdev(returns, sample)
    v = sd * math.sqrt(ppy)
    return CalcResult("annualized_volatility", v,
                      "stdev(returns) * sqrt(periods_per_year)",
                      {"n": len(returns), "periods_per_year": ppy,
                       "period_stdev": sd, "sample": sample}, "fraction/yr",
                      notes="sqrt-of-time scaling assumes i.i.d. returns; it "
                            "understates risk under autocorrelation or "
                            "volatility clustering.")


# --------------------------------------------------------------------------
# risk-adjusted performance
# --------------------------------------------------------------------------

def sharpe_ratio(returns: Sequence[float], risk_free_rate: float = 0.0,
                 freq="daily", sample: bool = True) -> CalcResult:
    """
    risk_free_rate is the ANNUAL rate; it is de-annualized internally so the
    caller cannot accidentally mix an annual rate with daily returns -- a
    classic and very quiet error.
    """
    _check_series(returns, "sharpe_ratio", minlen=2)
    ppy = _periods_per_year(freq)
    rf_period = (1.0 + risk_free_rate) ** (1.0 / ppy) - 1.0
    excess = [r - rf_period for r in returns]
    sd = stdev(excess, sample)
    if sd == 0:
        raise ZeroDivisionError("sharpe_ratio: zero volatility in excess "
                                "returns; ratio is undefined")
    v = mean(excess) / sd * math.sqrt(ppy)
    return CalcResult("sharpe_ratio", v,
                      "mean(excess) / stdev(excess) * sqrt(periods_per_year)",
                      {"n": len(returns), "annual_risk_free": risk_free_rate,
                       "period_risk_free": rf_period,
                       "periods_per_year": ppy}, "ratio")


def sortino_ratio(returns: Sequence[float], risk_free_rate: float = 0.0,
                  freq="daily", target: float = 0.0) -> CalcResult:
    """
    Downside deviation divides by the FULL count n, not the number of
    downside observations. This is Sortino's original definition; dividing by
    the downside count instead is a widespread implementation bug that
    inflates the ratio.
    """
    _check_series(returns, "sortino_ratio", minlen=2)
    ppy = _periods_per_year(freq)
    rf_period = (1.0 + risk_free_rate) ** (1.0 / ppy) - 1.0
    excess = [r - rf_period for r in returns]
    downside = [min(0.0, r - target) for r in excess]
    dd = math.sqrt(sum(d * d for d in downside) / len(excess))
    if dd == 0:
        raise ZeroDivisionError("sortino_ratio: no downside deviation; "
                                "ratio is undefined (no observed downside)")
    v = mean(excess) / dd * math.sqrt(ppy)
    return CalcResult("sortino_ratio", v,
                      "mean(excess) / downside_deviation * sqrt(ppy)",
                      {"n": len(returns), "target": target,
                       "downside_deviation": dd,
                       "periods_per_year": ppy}, "ratio",
                      notes="downside deviation divides by n (full sample), "
                            "per Sortino's definition.")


def max_drawdown(equity: Sequence[float]) -> CalcResult:
    """Largest peak-to-trough decline. Takes an EQUITY CURVE, not returns."""
    _check_series(equity, "max_drawdown", minlen=2)
    if any(e <= 0 for e in equity):
        raise ValueError("max_drawdown: equity curve must be strictly positive")
    peak = equity[0]
    mdd = 0.0
    peak_i = trough_i = 0
    cur_peak_i = 0
    for i, e in enumerate(equity):
        if e > peak:
            peak, cur_peak_i = e, i
        dd = (e - peak) / peak
        if dd < mdd:
            mdd, peak_i, trough_i = dd, cur_peak_i, i
    return CalcResult("max_drawdown", mdd, "min((V_t - running_peak)/running_peak)",
                      {"n": len(equity), "peak_index": peak_i,
                       "trough_index": trough_i}, "fraction",
                      notes="negative value; -0.20 means a 20% decline.")


def calmar_ratio(returns: Sequence[float], equity: Sequence[float],
                 freq="daily") -> CalcResult:
    ann = annualized_return(returns, freq).value
    mdd = max_drawdown(equity).value
    if mdd == 0:
        raise ZeroDivisionError("calmar_ratio: zero drawdown; undefined")
    v = ann / abs(mdd)
    return CalcResult("calmar_ratio", v, "annualized_return / |max_drawdown|",
                      {"annualized_return": ann, "max_drawdown": mdd}, "ratio")


# --------------------------------------------------------------------------
# relative / market risk
# --------------------------------------------------------------------------

def covariance(a: Sequence[float], b: Sequence[float],
               sample: bool = True) -> CalcResult:
    _check_series(a, "covariance.a", 2)
    _check_series(b, "covariance.b", 2)
    if len(a) != len(b):
        raise ValueError("covariance: length mismatch %d vs %d" % (len(a), len(b)))
    ma, mb = mean(a), mean(b)
    denom = len(a) - 1 if sample else len(a)
    v = sum((x - ma) * (y - mb) for x, y in zip(a, b)) / denom
    return CalcResult("covariance", v, "sum((a-mean_a)(b-mean_b))/(n-1)",
                      {"n": len(a), "sample": sample}, "variance units")


def correlation(a: Sequence[float], b: Sequence[float]) -> CalcResult:
    cov = covariance(a, b).value
    sa, sb = stdev(a), stdev(b)
    if sa == 0 or sb == 0:
        raise ZeroDivisionError("correlation: zero variance in a series")
    v = cov / (sa * sb)
    v = max(-1.0, min(1.0, v))  # clamp float drift only
    return CalcResult("correlation", v, "cov(a,b) / (stdev(a)*stdev(b))",
                      {"n": len(a)}, "coefficient")


def beta(asset: Sequence[float], market: Sequence[float]) -> CalcResult:
    cov = covariance(asset, market).value
    var_m = stdev(market) ** 2
    if var_m == 0:
        raise ZeroDivisionError("beta: market has zero variance")
    v = cov / var_m
    return CalcResult("beta", v, "cov(asset, market) / var(market)",
                      {"n": len(asset)}, "coefficient")


def alpha(asset: Sequence[float], market: Sequence[float],
          risk_free_rate: float = 0.0, freq="daily") -> CalcResult:
    """Jensen's alpha, annualized."""
    ppy = _periods_per_year(freq)
    b = beta(asset, market).value
    ra = annualized_return(asset, freq).value
    rm = annualized_return(market, freq).value
    v = ra - (risk_free_rate + b * (rm - risk_free_rate))
    return CalcResult("alpha", v, "Ra - (Rf + beta*(Rm - Rf))",
                      {"asset_annual": ra, "market_annual": rm,
                       "beta": b, "risk_free": risk_free_rate,
                       "periods_per_year": ppy}, "fraction/yr")


def tracking_error(asset: Sequence[float], benchmark: Sequence[float],
                   freq="daily") -> CalcResult:
    if len(asset) != len(benchmark):
        raise ValueError("tracking_error: length mismatch")
    _check_series(asset, "tracking_error.asset", 2)
    _check_series(benchmark, "tracking_error.benchmark", 2)
    ppy = _periods_per_year(freq)
    diff = [a - b for a, b in zip(asset, benchmark)]
    v = stdev(diff) * math.sqrt(ppy)
    return CalcResult("tracking_error", v,
                      "stdev(asset - benchmark) * sqrt(ppy)",
                      {"n": len(asset), "periods_per_year": ppy}, "fraction/yr")


def information_ratio(asset: Sequence[float], benchmark: Sequence[float],
                      freq="daily") -> CalcResult:
    te = tracking_error(asset, benchmark, freq).value
    if te == 0:
        raise ZeroDivisionError("information_ratio: zero tracking error")
    ppy = _periods_per_year(freq)
    diff = [a - b for a, b in zip(asset, benchmark)]
    active_annual = mean(diff) * ppy
    v = active_annual / te
    return CalcResult("information_ratio", v,
                      "annualized_active_return / tracking_error",
                      {"active_annual": active_annual,
                       "tracking_error": te}, "ratio")


# --------------------------------------------------------------------------
# tail risk
# --------------------------------------------------------------------------

def value_at_risk(returns: Sequence[float], confidence: float = 0.95) -> CalcResult:
    """
    Historical VaR. Non-parametric: no normality assumption.
    Returns a NEGATIVE number representing the loss threshold.
    """
    _check_series(returns, "value_at_risk", minlen=2)
    if not 0.0 < confidence < 1.0:
        raise ValueError("value_at_risk: confidence must be in (0,1)")
    s = sorted(returns)
    idx = int(math.floor((1.0 - confidence) * len(s)))
    idx = min(max(idx, 0), len(s) - 1)
    v = s[idx]
    return CalcResult("value_at_risk", v,
                      "empirical quantile at (1-confidence)",
                      {"n": len(returns), "confidence": confidence,
                       "quantile_index": idx}, "fraction",
                      notes="historical simulation; no distributional "
                            "assumption. Negative = loss.")


def conditional_value_at_risk(returns: Sequence[float],
                              confidence: float = 0.95) -> CalcResult:
    """Expected shortfall: mean of losses AT OR BEYOND the VaR threshold."""
    _check_series(returns, "conditional_value_at_risk", minlen=2)
    if not 0.0 < confidence < 1.0:
        raise ValueError("cvar: confidence must be in (0,1)")
    s = sorted(returns)
    cutoff = int(math.floor((1.0 - confidence) * len(s)))
    tail = s[:cutoff] if cutoff > 0 else s[:1]
    v = mean(tail)
    return CalcResult("conditional_value_at_risk", v,
                      "mean(returns <= VaR threshold)",
                      {"n": len(returns), "confidence": confidence,
                       "tail_count": len(tail)}, "fraction",
                      notes="also called Expected Shortfall. Always <= VaR.")


# --------------------------------------------------------------------------
# position sizing and portfolio structure
# --------------------------------------------------------------------------

def position_size(account_equity: float, risk_pct: float,
                  entry: float, stop: float) -> CalcResult:
    """
    Units to trade so that being stopped out loses exactly risk_pct of equity.
    Refuses stop == entry: that implies infinite size, and returning a huge
    number here would be actively dangerous.
    """
    if account_equity <= 0:
        raise ValueError("position_size: account_equity must be > 0")
    if not 0.0 < risk_pct <= 1.0:
        raise ValueError("position_size: risk_pct must be in (0,1] as a "
                         "fraction (0.01 = 1%)")
    if entry <= 0 or stop < 0:
        raise ValueError("position_size: invalid entry/stop")
    per_unit = abs(entry - stop)
    if per_unit == 0:
        raise ZeroDivisionError("position_size: stop equals entry; risk per "
                                "unit is zero and size is unbounded")
    risk_amount = account_equity * risk_pct
    units = risk_amount / per_unit
    return CalcResult("position_size", units,
                      "(equity * risk_pct) / |entry - stop|",
                      {"equity": account_equity, "risk_pct": risk_pct,
                       "entry": entry, "stop": stop,
                       "risk_amount": risk_amount,
                       "risk_per_unit": per_unit}, "units",
                      notes="ignores slippage, gaps, and fees; actual loss can "
                            "exceed risk_amount if the stop gaps through.")


def risk_reward(entry: float, stop: float, target: float) -> CalcResult:
    risk = abs(entry - stop)
    reward = abs(target - entry)
    if risk == 0:
        raise ZeroDivisionError("risk_reward: zero risk (stop == entry)")
    v = reward / risk
    return CalcResult("risk_reward", v, "|target-entry| / |entry-stop|",
                      {"entry": entry, "stop": stop, "target": target,
                       "risk": risk, "reward": reward}, "ratio")


def portfolio_leverage(gross_exposure: float, net_equity: float) -> CalcResult:
    if net_equity <= 0:
        raise ValueError("portfolio_leverage: net_equity must be > 0")
    v = gross_exposure / net_equity
    return CalcResult("portfolio_leverage", v, "gross_exposure / net_equity",
                      {"gross_exposure": gross_exposure,
                       "net_equity": net_equity}, "x")


def concentration(weights: Sequence[float]) -> CalcResult:
    """Herfindahl-Hirschman index. 1.0 = single position, 1/n = equal weight."""
    _check_series(weights, "concentration", minlen=1)
    total = sum(abs(w) for w in weights)
    if total == 0:
        raise ValueError("concentration: weights sum to zero")
    norm = [abs(w) / total for w in weights]
    v = sum(w * w for w in norm)
    return CalcResult("concentration", v, "sum(w_i^2) (Herfindahl index)",
                      {"n": len(weights), "equal_weight_baseline": 1.0 / len(weights)},
                      "index",
                      notes="1.0 = fully concentrated; 1/n = equally weighted.")


def risk_contribution(weights: Sequence[float],
                      cov_matrix: Sequence[Sequence[float]]) -> CalcResult:
    """Marginal risk contribution per position. Contributions sum to total vol."""
    n = len(weights)
    if len(cov_matrix) != n or any(len(r) != n for r in cov_matrix):
        raise ValueError("risk_contribution: cov_matrix must be n x n")
    port_var = sum(weights[i] * cov_matrix[i][j] * weights[j]
                   for i in range(n) for j in range(n))
    if port_var <= 0:
        raise ValueError("risk_contribution: non-positive portfolio variance")
    port_vol = math.sqrt(port_var)
    contribs = []
    for i in range(n):
        mrc = sum(cov_matrix[i][j] * weights[j] for j in range(n)) / port_vol
        contribs.append(weights[i] * mrc)
    return CalcResult("risk_contribution", contribs,
                      "w_i * (Sigma w)_i / portfolio_vol",
                      {"portfolio_vol": port_vol, "n": n}, "vol units",
                      notes="contributions sum to portfolio volatility.")
