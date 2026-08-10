"""
Deterministic technical indicators (master prompt SS.5.3).

ARCHITECTURE NOTE
-----------------
Each indicator has two layers:

  _xxx_series(...)  -> plain Python list, the full indicator series
  xxx(...)          -> CalcResult whose value is the LATEST reading

The split exists for two reasons. First, tests hand-verify the series layer
directly, so the arithmetic is checked point by point rather than only at the
final bar. Second, handing a 500-element array back to a 16K-context model
wastes the context budget on numbers it cannot use; a trading decision reads
the current bar, so that is what the tool returns.

CONVENTION WARNINGS (each of these is a real, silent source of wrong numbers):
  - RSI, ATR and ADX use WILDER smoothing, not a simple moving average. An
    SMA-based "RSI" gives different values and is a different indicator.
  - EMA is seeded with the SMA of the first `period` values. Seeding with the
    first price instead shifts the whole early series.
  - Bollinger Bands use the POPULATION standard deviation by default, which is
    the standard convention. `sample=True` is available but changes the bands.
  - Indicators need warm-up. These functions REFUSE short input rather than
    returning a value computed from too few bars.
"""

from typing import Sequence, List, Dict
import math

from calc.returns_risk import CalcResult, _check_series


def _check_period(period, name="period", minimum=1):
    if isinstance(period, bool) or not isinstance(period, (int, float)):
        raise TypeError("%s must be an integer, got %r" % (name, period))
    if float(period) != int(period):
        raise ValueError("%s must be a whole number, got %r" % (name, period))
    period = int(period)
    if period < minimum:
        raise ValueError("%s must be >= %d, got %d" % (name, minimum, period))
    return period


def _need(xs, period, name, extra=0):
    required = period + extra
    if len(xs) < required:
        raise ValueError(
            "%s: need at least %d data points for period=%d, got %d. "
            "Refusing to compute from insufficient warm-up."
            % (name, required, period, len(xs)))


def _pstdev(xs: Sequence[float]) -> float:
    """Population standard deviation (n divisor) -- the Bollinger convention."""
    n = len(xs)
    m = sum(xs) / n
    return math.sqrt(sum((x - m) ** 2 for x in xs) / n)


def _sstdev(xs: Sequence[float]) -> float:
    n = len(xs)
    if n < 2:
        raise ValueError("sample stdev needs >= 2 points")
    m = sum(xs) / n
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))


def _wilder_smooth(values: Sequence[float], period: int) -> List[float]:
    """
    Wilder's smoothing: first value is the simple average of the first
    `period` inputs, then s = (s*(period-1) + x) / period.

    This is NOT an EMA with alpha=2/(n+1); Wilder's is equivalent to
    alpha=1/n. Confusing the two is the classic RSI/ATR discrepancy.
    """
    out = [sum(values[:period]) / period]
    for v in values[period:]:
        out.append((out[-1] * (period - 1) + v) / period)
    return out


# --------------------------------------------------------------------------
# Moving averages
# --------------------------------------------------------------------------

def _sma_series(prices: Sequence[float], period: int) -> List[float]:
    return [sum(prices[i - period + 1:i + 1]) / period
            for i in range(period - 1, len(prices))]


def sma(prices: Sequence[float], period: int) -> CalcResult:
    """Simple moving average."""
    _check_series(prices, "sma.prices", minlen=1)
    period = _check_period(period)
    _need(prices, period, "sma")
    s = _sma_series(prices, period)
    return CalcResult("sma", s[-1], "mean(last `period` prices)",
                      {"period": period, "n_points": len(prices),
                       "n_values": len(s)}, "price")


def _ema_series(prices: Sequence[float], period: int) -> List[float]:
    """EMA seeded with the SMA of the first `period` prices."""
    alpha = 2.0 / (period + 1.0)
    seed = sum(prices[:period]) / period
    out = [seed]
    for p in prices[period:]:
        out.append(alpha * p + (1.0 - alpha) * out[-1])
    return out


def ema(prices: Sequence[float], period: int) -> CalcResult:
    """Exponential moving average, alpha = 2/(period+1), SMA-seeded."""
    _check_series(prices, "ema.prices", minlen=1)
    period = _check_period(period)
    _need(prices, period, "ema")
    s = _ema_series(prices, period)
    return CalcResult("ema", s[-1],
                      "EMA_t = a*P_t + (1-a)*EMA_(t-1), a = 2/(period+1), "
                      "seeded with SMA(period)",
                      {"period": period, "alpha": 2.0 / (period + 1.0),
                       "n_points": len(prices), "seed": "SMA of first period"},
                      "price")


def _wma_series(prices: Sequence[float], period: int) -> List[float]:
    weights = list(range(1, period + 1))          # most recent gets weight n
    wsum = float(sum(weights))
    out = []
    for i in range(period - 1, len(prices)):
        window = prices[i - period + 1:i + 1]
        out.append(sum(p * w for p, w in zip(window, weights)) / wsum)
    return out


def wma(prices: Sequence[float], period: int) -> CalcResult:
    """Linearly weighted moving average; the most recent bar carries weight n."""
    _check_series(prices, "wma.prices", minlen=1)
    period = _check_period(period)
    _need(prices, period, "wma")
    s = _wma_series(prices, period)
    return CalcResult("wma", s[-1],
                      "sum(P_i * w_i) / sum(w_i), w = 1..period (recent heaviest)",
                      {"period": period, "n_points": len(prices)}, "price")


# --------------------------------------------------------------------------
# Momentum
# --------------------------------------------------------------------------

def _rsi_series(prices: Sequence[float], period: int) -> List[float]:
    gains, losses = [], []
    for i in range(1, len(prices)):
        d = prices[i] - prices[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    ag = _wilder_smooth(gains, period)
    al = _wilder_smooth(losses, period)
    out = []
    for g, l in zip(ag, al):
        if l == 0:
            out.append(100.0)          # no downside in window
        else:
            rs = g / l
            out.append(100.0 - 100.0 / (1.0 + rs))
    return out


def rsi(prices: Sequence[float], period: int = 14) -> CalcResult:
    """
    Relative Strength Index with Wilder smoothing. Bounded [0, 100].

    A window with no losses yields exactly 100 (RS is infinite); this is
    handled explicitly rather than dividing by zero.
    """
    _check_series(prices, "rsi.prices", minlen=2)
    period = _check_period(period, minimum=2)
    _need(prices, period, "rsi", extra=1)
    s = _rsi_series(prices, period)
    return CalcResult("rsi", s[-1],
                      "100 - 100/(1 + avg_gain/avg_loss), Wilder-smoothed",
                      {"period": period, "n_points": len(prices),
                       "smoothing": "Wilder (alpha = 1/period)"}, "index 0-100",
                      "Overbought/oversold thresholds (70/30) are convention, "
                      "not signals; RSI can stay extended in a trend.")


def _macd_series(prices, fast, slow, signal):
    fast_s = _ema_series(prices, fast)
    slow_s = _ema_series(prices, slow)
    # Align: slow starts later by (slow - fast) bars.
    offset = slow - fast
    macd_line = [f - s for f, s in zip(fast_s[offset:], slow_s)]
    signal_line = _ema_series(macd_line, signal)
    sig_offset = len(macd_line) - len(signal_line)
    hist = [m - g for m, g in zip(macd_line[sig_offset:], signal_line)]
    return macd_line, signal_line, hist


def macd(prices: Sequence[float], fast: int = 12, slow: int = 26,
         signal: int = 9) -> CalcResult:
    """
    MACD line, signal line, and histogram.

    Returns a dict, not a single number, because acting on the MACD line
    without the signal line is a different (and usually wrong) strategy.
    """
    _check_series(prices, "macd.prices", minlen=2)
    fast = _check_period(fast, "fast", minimum=1)
    slow = _check_period(slow, "slow", minimum=2)
    signal = _check_period(signal, "signal", minimum=1)
    if fast >= slow:
        raise ValueError("fast period (%d) must be < slow period (%d)"
                         % (fast, slow))
    _need(prices, slow + signal - 1, "macd")
    m, g, h = _macd_series(prices, fast, slow, signal)
    return CalcResult("macd",
                      {"macd": m[-1], "signal": g[-1], "histogram": h[-1]},
                      "MACD = EMA(fast) - EMA(slow); signal = EMA(MACD, "
                      "signal); histogram = MACD - signal",
                      {"fast": fast, "slow": slow, "signal": signal,
                       "n_points": len(prices)}, "price difference")


def _roc_series(prices: Sequence[float], period: int) -> List[float]:
    out = []
    for i in range(period, len(prices)):
        base = prices[i - period]
        if base == 0:
            raise ZeroDivisionError("roc: zero price at index %d" % (i - period))
        out.append((prices[i] - base) / base)
    return out


def rate_of_change(prices: Sequence[float], period: int = 12) -> CalcResult:
    """Rate of change as a FRACTION (0.05 = +5%), not percentage points."""
    _check_series(prices, "roc.prices", minlen=2)
    period = _check_period(period)
    _need(prices, period, "rate_of_change", extra=1)
    s = _roc_series(prices, period)
    return CalcResult("rate_of_change", s[-1],
                      "(P_t - P_(t-period)) / P_(t-period)",
                      {"period": period, "n_points": len(prices)}, "fraction")


def _stoch_series(highs, lows, closes, k_period, d_period):
    k = []
    for i in range(k_period - 1, len(closes)):
        hh = max(highs[i - k_period + 1:i + 1])
        ll = min(lows[i - k_period + 1:i + 1])
        rng = hh - ll
        if rng == 0:
            k.append(50.0)          # flat range: neutral, not a divide by zero
        else:
            k.append(100.0 * (closes[i] - ll) / rng)
    d = _sma_series(k, d_period) if len(k) >= d_period else []
    return k, d


def stochastic_oscillator(highs: Sequence[float], lows: Sequence[float],
                          closes: Sequence[float], k_period: int = 14,
                          d_period: int = 3) -> CalcResult:
    """Stochastic %K and %D (SMA of %K). Bounded [0, 100]."""
    _check_series(highs, "stoch.highs", minlen=1)
    _check_series(lows, "stoch.lows", minlen=1)
    _check_series(closes, "stoch.closes", minlen=1)
    if not (len(highs) == len(lows) == len(closes)):
        raise ValueError("highs, lows and closes must be the same length "
                         "(%d/%d/%d)" % (len(highs), len(lows), len(closes)))
    _validate_ohlc(highs, lows, closes)
    k_period = _check_period(k_period, "k_period")
    d_period = _check_period(d_period, "d_period")
    _need(closes, k_period + d_period - 1, "stochastic_oscillator")
    k, d = _stoch_series(highs, lows, closes, k_period, d_period)
    return CalcResult("stochastic_oscillator",
                      {"k": k[-1], "d": d[-1]},
                      "%K = 100*(C - LL)/(HH - LL); %D = SMA(%K, d_period)",
                      {"k_period": k_period, "d_period": d_period,
                       "n_points": len(closes)}, "index 0-100")


# --------------------------------------------------------------------------
# Volatility and range
# --------------------------------------------------------------------------

def _validate_ohlc(highs, lows, closes):
    for i, (h, l, c) in enumerate(zip(highs, lows, closes)):
        if h < l:
            raise ValueError("bar %d: high (%g) < low (%g); OHLC data is "
                             "inconsistent" % (i, h, l))
        if not (l <= c <= h):
            raise ValueError("bar %d: close (%g) outside [low %g, high %g]; "
                             "OHLC data is inconsistent" % (i, c, l, h))


def _true_range_series(highs, lows, closes) -> List[float]:
    """TR requires the PREVIOUS close, so the series is one shorter."""
    out = []
    for i in range(1, len(closes)):
        pc = closes[i - 1]
        out.append(max(highs[i] - lows[i], abs(highs[i] - pc),
                       abs(lows[i] - pc)))
    return out


def _atr_series(highs, lows, closes, period) -> List[float]:
    return _wilder_smooth(_true_range_series(highs, lows, closes), period)


def atr(highs: Sequence[float], lows: Sequence[float],
        closes: Sequence[float], period: int = 14) -> CalcResult:
    """
    Average True Range, Wilder-smoothed.

    ATR is an absolute price distance, NOT a percentage. Using it as a stop
    distance requires multiplying by the instrument's price scale, and
    comparing raw ATR across instruments is meaningless.
    """
    _check_series(highs, "atr.highs", minlen=2)
    _check_series(lows, "atr.lows", minlen=2)
    _check_series(closes, "atr.closes", minlen=2)
    if not (len(highs) == len(lows) == len(closes)):
        raise ValueError("highs, lows and closes must be the same length "
                         "(%d/%d/%d)" % (len(highs), len(lows), len(closes)))
    _validate_ohlc(highs, lows, closes)
    period = _check_period(period)
    _need(closes, period, "atr", extra=1)
    s = _atr_series(highs, lows, closes, period)
    return CalcResult("atr", s[-1],
                      "Wilder average of TR; TR = max(H-L, |H-PC|, |L-PC|)",
                      {"period": period, "n_bars": len(closes),
                       "smoothing": "Wilder"}, "price (absolute)",
                      "ATR is in price units, not percent.")


def _bollinger_series(prices, period, num_std, sample):
    mid = _sma_series(prices, period)
    out = []
    for j, i in enumerate(range(period - 1, len(prices))):
        window = prices[i - period + 1:i + 1]
        sd = _sstdev(window) if sample else _pstdev(window)
        out.append((mid[j] + num_std * sd, mid[j], mid[j] - num_std * sd, sd))
    return out


def bollinger_bands(prices: Sequence[float], period: int = 20,
                    num_std: float = 2.0, sample: bool = False) -> CalcResult:
    """
    Bollinger Bands. Default uses the POPULATION standard deviation, which is
    the standard convention; sample=True widens the bands slightly.
    """
    _check_series(prices, "bollinger.prices", minlen=1)
    period = _check_period(period, minimum=2)
    if isinstance(num_std, bool) or not isinstance(num_std, (int, float)):
        raise TypeError("num_std must be a number")
    if num_std <= 0:
        raise ValueError("num_std must be > 0, got %g" % num_std)
    _need(prices, period, "bollinger_bands")
    b = _bollinger_series(prices, period, float(num_std), sample)
    u, m, l, sd = b[-1]
    width = (u - l) / m if m != 0 else float("nan")
    return CalcResult("bollinger_bands",
                      {"upper": u, "middle": m, "lower": l, "bandwidth": width},
                      "middle = SMA(period); upper/lower = middle +/- "
                      "num_std * stdev(window)",
                      {"period": period, "num_std": float(num_std),
                       "stdev_convention": "sample" if sample else "population",
                       "stdev": sd, "n_points": len(prices)}, "price")


def _adx_series(highs, lows, closes, period):
    tr, plus_dm, minus_dm = [], [], []
    for i in range(1, len(closes)):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        plus_dm.append(up if (up > down and up > 0) else 0.0)
        minus_dm.append(down if (down > up and down > 0) else 0.0)
        pc = closes[i - 1]
        tr.append(max(highs[i] - lows[i], abs(highs[i] - pc),
                      abs(lows[i] - pc)))
    str_ = _wilder_smooth(tr, period)
    sp = _wilder_smooth(plus_dm, period)
    sm = _wilder_smooth(minus_dm, period)
    di_plus, di_minus, dx = [], [], []
    for t, p, m in zip(str_, sp, sm):
        if t == 0:
            di_plus.append(0.0)
            di_minus.append(0.0)
            dx.append(0.0)
            continue
        dp = 100.0 * p / t
        dm = 100.0 * m / t
        di_plus.append(dp)
        di_minus.append(dm)
        s = dp + dm
        dx.append(0.0 if s == 0 else 100.0 * abs(dp - dm) / s)
    adx_vals = _wilder_smooth(dx, period) if len(dx) >= period else []
    return di_plus, di_minus, dx, adx_vals


def adx(highs: Sequence[float], lows: Sequence[float],
        closes: Sequence[float], period: int = 14) -> CalcResult:
    """
    Average Directional Index with +DI and -DI.

    ADX measures trend STRENGTH, not direction -- a high ADX in a downtrend is
    still a high ADX. Direction comes from the sign of (+DI - -DI). Reading
    ADX as bullish is a standard misinterpretation.

    Needs roughly 2*period+1 bars: one Wilder pass for DI, a second for ADX.
    """
    _check_series(highs, "adx.highs", minlen=2)
    _check_series(lows, "adx.lows", minlen=2)
    _check_series(closes, "adx.closes", minlen=2)
    if not (len(highs) == len(lows) == len(closes)):
        raise ValueError("highs, lows and closes must be the same length "
                         "(%d/%d/%d)" % (len(highs), len(lows), len(closes)))
    _validate_ohlc(highs, lows, closes)
    period = _check_period(period, minimum=2)
    _need(closes, 2 * period, "adx", extra=1)
    dip, dim, dx, adx_vals = _adx_series(highs, lows, closes, period)
    if not adx_vals:
        raise ValueError("adx: insufficient data after warm-up")
    return CalcResult("adx",
                      {"adx": adx_vals[-1], "di_plus": dip[-1],
                       "di_minus": dim[-1]},
                      "DX = 100*|+DI - -DI|/(+DI + -DI); ADX = Wilder "
                      "average of DX",
                      {"period": period, "n_bars": len(closes)},
                      "index 0-100",
                      "ADX is strength only. Direction = sign(+DI - -DI).")


def donchian_channels(highs: Sequence[float], lows: Sequence[float],
                      period: int = 20) -> CalcResult:
    """Highest high and lowest low over the lookback window."""
    _check_series(highs, "donchian.highs", minlen=1)
    _check_series(lows, "donchian.lows", minlen=1)
    if len(highs) != len(lows):
        raise ValueError("highs and lows must be the same length (%d/%d)"
                         % (len(highs), len(lows)))
    period = _check_period(period)
    _need(highs, period, "donchian_channels")
    u = max(highs[-period:])
    l = min(lows[-period:])
    if u < l:
        raise ValueError("donchian: highest high < lowest low; data is "
                         "inconsistent")
    return CalcResult("donchian_channels",
                      {"upper": u, "middle": (u + l) / 2.0, "lower": l},
                      "upper = max(high, period); lower = min(low, period)",
                      {"period": period, "n_bars": len(highs)}, "price")


# --------------------------------------------------------------------------
# Volume
# --------------------------------------------------------------------------

def vwap(highs: Sequence[float], lows: Sequence[float],
         closes: Sequence[float], volumes: Sequence[float]) -> CalcResult:
    """
    Volume-weighted average price over the supplied bars, using the typical
    price (H+L+C)/3.

    VWAP is an INTRADAY, session-anchored measure. Feeding it multi-day bars
    produces a number that is arithmetically correct and analytically
    meaningless; the caller is responsible for the anchor, and the note says so.
    """
    _check_series(highs, "vwap.highs", minlen=1)
    _check_series(lows, "vwap.lows", minlen=1)
    _check_series(closes, "vwap.closes", minlen=1)
    _check_series(volumes, "vwap.volumes", minlen=1)
    if not (len(highs) == len(lows) == len(closes) == len(volumes)):
        raise ValueError("highs, lows, closes and volumes must be the same "
                         "length (%d/%d/%d/%d)"
                         % (len(highs), len(lows), len(closes), len(volumes)))
    _validate_ohlc(highs, lows, closes)
    for i, v in enumerate(volumes):
        if v < 0:
            raise ValueError("vwap: negative volume at index %d (%g)" % (i, v))
    tv = float(sum(volumes))
    if tv == 0:
        raise ZeroDivisionError("vwap: total volume is zero; VWAP is undefined")
    num = sum(((h + l + c) / 3.0) * vol
              for h, l, c, vol in zip(highs, lows, closes, volumes))
    return CalcResult("vwap", num / tv,
                      "sum(typical_price * volume) / sum(volume), "
                      "typical = (H+L+C)/3",
                      {"n_bars": len(closes), "total_volume": tv},
                      "price",
                      "VWAP is session-anchored. Confirm the bars belong to "
                      "one session before interpreting it.")


def _obv_series(closes: Sequence[float], volumes: Sequence[float]
                ) -> List[float]:
    out = [0.0]
    for i in range(1, len(closes)):
        if closes[i] > closes[i - 1]:
            out.append(out[-1] + volumes[i])
        elif closes[i] < closes[i - 1]:
            out.append(out[-1] - volumes[i])
        else:
            out.append(out[-1])
    return out


def obv(closes: Sequence[float], volumes: Sequence[float]) -> CalcResult:
    """
    On-Balance Volume, starting from zero.

    The ABSOLUTE level is arbitrary (it depends where the series starts);
    only the slope and divergences carry information.
    """
    _check_series(closes, "obv.closes", minlen=2)
    _check_series(volumes, "obv.volumes", minlen=2)
    if len(closes) != len(volumes):
        raise ValueError("closes and volumes must be the same length (%d/%d)"
                         % (len(closes), len(volumes)))
    for i, v in enumerate(volumes):
        if v < 0:
            raise ValueError("obv: negative volume at index %d (%g)" % (i, v))
    s = _obv_series(closes, volumes)
    return CalcResult("obv", s[-1],
                      "cumulative +volume on up closes, -volume on down closes",
                      {"n_bars": len(closes), "start_value": 0.0},
                      "volume (cumulative)",
                      "Absolute level is arbitrary; read the slope, not the "
                      "number.")
