"""
Deterministic fixed-income calculations (master prompt SS.5.3).

CONVENTIONS -- STATED, NEVER ASSUMED
------------------------------------
Bond maths is convention-heavy, and every convention below changes the answer:

  - Yields and coupon rates are ANNUAL NOMINAL rates expressed as fractions
    (0.05 = 5%), compounded `frequency` times per year.
  - `frequency` is coupons per year (2 = semiannual, the US corporate/Treasury
    default). It is an explicit argument with no default guess where it matters.
  - Duration is returned in YEARS.
  - Day count for accrued interest is selectable; there is no universal
    default, so the caller must pick and the choice is echoed in the output.

PRICE/YIELD SIGN DISCIPLINE
---------------------------
Price and yield move inversely. Duration is reported as a POSITIVE number
(the conventional presentation), and the price-change formula carries the
minus sign explicitly: dP/P = -ModDur * dy. Storing duration negative and
also subtracting is a double-negation error that flips the risk direction.
"""

from typing import Sequence, List, Dict, Optional
import math

from calc.returns_risk import CalcResult

DAY_COUNTS = {
    "30/360": 360.0,
    "actual/360": 360.0,
    "actual/365": 365.0,
}

# Yields below this are treated as an input error rather than a market rate.
# Policy rates have gone negative (Swiss/Japanese/euro-area sovereigns traded
# at roughly -1%), so the floor is set well below anything observed while
# still catching the unit-mismatch errors that produce -50% and worse.
MIN_PLAUSIBLE_YIELD = -0.50


def _num(x, name):
    if x is None:
        raise ValueError("%s: value is None" % name)
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        raise TypeError("%s: non-numeric value %r" % (name, x))
    if math.isnan(x) or math.isinf(x):
        raise ValueError("%s: NaN/Inf" % name)
    return float(x)


def _freq(frequency):
    if isinstance(frequency, bool) or not isinstance(frequency, (int, float)):
        raise TypeError("frequency must be an integer number of coupons/year")
    if float(frequency) != int(frequency):
        raise ValueError("frequency must be a whole number, got %r" % frequency)
    f = int(frequency)
    if f < 1:
        raise ValueError("frequency must be >= 1, got %d" % f)
    if f > 12:
        raise ValueError("frequency %d coupons/year is implausible" % f)
    return f


def _rate(x, name):
    r = _num(x, name)
    if r <= -1.0:
        raise ValueError("%s must be > -100%%, got %g" % (name, r))
    if abs(r) > 1.0:
        raise ValueError("%s=%g looks like a percentage; pass a fraction "
                         "(0.05 for 5%%)" % (name, r))
    return r


# --------------------------------------------------------------------------
# Cash flows
# --------------------------------------------------------------------------

def cash_flow_schedule(face_value: float, coupon_rate: float,
                       years_to_maturity: float, frequency: int = 2
                       ) -> CalcResult:
    """
    Full coupon schedule with the principal repaid at maturity.

    Periods are whole coupon periods. A partial first period (settlement
    between coupon dates) is handled by accrued_interest / dirty_price, not
    here; mixing the two silently double-counts a coupon.
    """
    fv = _num(face_value, "face_value")
    if fv <= 0:
        raise ValueError("face_value must be > 0, got %g" % fv)
    c = _rate(coupon_rate, "coupon_rate")
    if c < 0:
        raise ValueError("coupon_rate must be >= 0, got %g" % c)
    y = _num(years_to_maturity, "years_to_maturity")
    if y <= 0:
        raise ValueError("years_to_maturity must be > 0, got %g" % y)
    f = _freq(frequency)

    n_exact = y * f
    n = int(round(n_exact))
    if abs(n_exact - n) > 1e-9:
        raise ValueError(
            "years_to_maturity (%g) x frequency (%d) = %g is not a whole "
            "number of coupon periods. Supply a maturity on a coupon "
            "boundary, or use accrued_interest for a stub period."
            % (y, f, n_exact))
    if n < 1:
        raise ValueError("schedule needs at least one coupon period")

    cpn = fv * c / f
    flows = []
    for i in range(1, n + 1):
        amt = cpn + (fv if i == n else 0.0)
        flows.append({"period": i, "time_years": i / f, "coupon": cpn,
                      "principal": fv if i == n else 0.0, "total": amt})
    return CalcResult("cash_flow_schedule", flows,
                      "coupon = face x rate / frequency each period; "
                      "principal repaid at maturity",
                      {"face_value": fv, "coupon_rate": c,
                       "years_to_maturity": y, "frequency": f,
                       "n_periods": n, "coupon_per_period": cpn,
                       "total_undiscounted": sum(x["total"] for x in flows)},
                      "currency")


def _price_from_yield(fv, c, ytm, n, f):
    """Present value of coupons + principal at `ytm` for n whole periods."""
    cpn = fv * c / f
    y = ytm / f
    if y == 0:
        return cpn * n + fv
    disc = (1.0 + y)
    pv_coupons = cpn * (1.0 - disc ** (-n)) / y
    pv_principal = fv * disc ** (-n)
    return pv_coupons + pv_principal


def bond_price(face_value: float, coupon_rate: float, ytm: float,
               years_to_maturity: float, frequency: int = 2) -> CalcResult:
    """Clean price of an option-free bond on a coupon date."""
    fv = _num(face_value, "face_value")
    if fv <= 0:
        raise ValueError("face_value must be > 0, got %g" % fv)
    c = _rate(coupon_rate, "coupon_rate")
    if c < 0:
        raise ValueError("coupon_rate must be >= 0, got %g" % c)
    y = _rate(ytm, "ytm")
    if y <= -1.0:
        raise ValueError("ytm must be > -100%")
    f = _freq(frequency)
    yrs = _num(years_to_maturity, "years_to_maturity")
    if yrs <= 0:
        raise ValueError("years_to_maturity must be > 0, got %g" % yrs)
    n_exact = yrs * f
    n = int(round(n_exact))
    if abs(n_exact - n) > 1e-9:
        raise ValueError("years_to_maturity x frequency must be a whole "
                         "number of periods (got %g)" % n_exact)
    p = _price_from_yield(fv, c, y, n, f)
    return CalcResult("bond_price", p,
                      "sum(C/(1+y/f)^t) + F/(1+y/f)^n",
                      {"face_value": fv, "coupon_rate": c, "ytm": y,
                       "frequency": f, "n_periods": n,
                       "coupon_per_period": fv * c / f,
                       "price_per_100": 100.0 * p / fv}, "currency (clean)",
                      "Clean price on a coupon date. Between dates, add "
                      "accrued interest to get the dirty (invoice) price.")


# --------------------------------------------------------------------------
# Accrued interest and price conventions
# --------------------------------------------------------------------------

def accrued_interest(face_value: float, coupon_rate: float,
                     days_since_last_coupon: float,
                     days_in_period: float, frequency: int = 2,
                     day_count: str = "30/360") -> CalcResult:
    """
    Accrued interest for a settlement between coupon dates.

    day_count is recorded for disclosure. The arithmetic here uses the
    supplied day counts directly (accrual fraction = days_since / days_in),
    which is what every convention reduces to once the day counts themselves
    are computed under that convention.
    """
    fv = _num(face_value, "face_value")
    if fv <= 0:
        raise ValueError("face_value must be > 0, got %g" % fv)
    c = _rate(coupon_rate, "coupon_rate")
    if c < 0:
        raise ValueError("coupon_rate must be >= 0, got %g" % c)
    f = _freq(frequency)
    d1 = _num(days_since_last_coupon, "days_since_last_coupon")
    d2 = _num(days_in_period, "days_in_period")
    if d2 <= 0:
        raise ValueError("days_in_period must be > 0, got %g" % d2)
    if d1 < 0:
        raise ValueError("days_since_last_coupon must be >= 0, got %g" % d1)
    if d1 > d2:
        raise ValueError("days_since_last_coupon (%g) exceeds days_in_period "
                         "(%g); a coupon has been missed" % (d1, d2))
    if day_count not in DAY_COUNTS:
        raise ValueError("unknown day_count %r; use one of %s"
                         % (day_count, sorted(DAY_COUNTS)))
    cpn = fv * c / f
    ai = cpn * (d1 / d2)
    return CalcResult("accrued_interest", ai,
                      "coupon_per_period x (days_since / days_in_period)",
                      {"face_value": fv, "coupon_rate": c, "frequency": f,
                       "coupon_per_period": cpn,
                       "days_since_last_coupon": d1, "days_in_period": d2,
                       "accrual_fraction": d1 / d2, "day_count": day_count},
                      "currency")


def dirty_price(clean_price: float, accrued: float) -> CalcResult:
    """
    Dirty (invoice) price = clean + accrued. This is what the buyer PAYS.

    Quoted prices are clean; settlement is dirty. Comparing a clean quote to
    a dirty cash amount understates the cost by the accrued interest.
    """
    cp = _num(clean_price, "clean_price")
    ai = _num(accrued, "accrued")
    if cp <= 0:
        raise ValueError("clean_price must be > 0, got %g" % cp)
    if ai < 0:
        raise ValueError("accrued must be >= 0, got %g" % ai)
    return CalcResult("dirty_price", cp + ai, "clean_price + accrued_interest",
                      {"clean_price": cp, "accrued_interest": ai},
                      "currency (dirty/invoice)")


def clean_price(dirty_price_: float, accrued: float) -> CalcResult:
    """Clean price = dirty - accrued. Inverse of dirty_price."""
    dp = _num(dirty_price_, "dirty_price")
    ai = _num(accrued, "accrued")
    if dp <= 0:
        raise ValueError("dirty_price must be > 0, got %g" % dp)
    if ai < 0:
        raise ValueError("accrued must be >= 0, got %g" % ai)
    if ai > dp:
        raise ValueError("accrued (%g) exceeds dirty price (%g); inputs are "
                         "inconsistent" % (ai, dp))
    return CalcResult("clean_price", dp - ai, "dirty_price - accrued_interest",
                      {"dirty_price": dp, "accrued_interest": ai},
                      "currency (clean)")


# --------------------------------------------------------------------------
# Yield solving
# --------------------------------------------------------------------------

def _solve_yield(price, fv, c, n, f, redemption, label):
    """
    Bisection on yield. Chosen over Newton deliberately: price is monotonically
    decreasing in yield for a plain bond, so bisection cannot diverge or land
    on a spurious root, and a guaranteed answer matters more here than speed.
    """
    def pv(y):
        cpn = fv * c / f
        per = y / f
        if per <= -1.0:
            return float("inf")
        if per == 0:
            return cpn * n + redemption
        d = 1.0 + per
        return cpn * (1.0 - d ** (-n)) / per + redemption * d ** (-n)

    lo, hi = -0.9999, 10.0
    p_lo, p_hi = pv(lo), pv(hi)
    if not (p_hi <= price <= p_lo):
        raise ValueError(
            "%s: price %g is outside the solvable range [%g, %g] for yields "
            "between -99.99%% and 1000%%. Check face value, coupon and "
            "maturity." % (label, price, p_hi, p_lo))
    for _ in range(300):
        mid = (lo + hi) / 2.0
        if pv(mid) > price:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-14:
            break
    y = (lo + hi) / 2.0

    # PLAUSIBILITY GATE.
    # The bisection above will happily solve a price of 1e9 on a 1,000-face
    # bond and report a yield of -99.5%. That is arithmetically correct and
    # economically meaningless: it means the inputs are wrong (price quoted in
    # the wrong unit, wrong face value, wrong maturity), not that such a bond
    # exists. Real negative yields have reached roughly -1%; nothing
    # approaching -50% has ever traded. Returning a confident number here
    # would convert an input error into a fabricated result, so it is refused.
    if y < MIN_PLAUSIBLE_YIELD:
        raise ValueError(
            "%s: price %g implies a yield of %.2f%%, which is not an "
            "economically plausible bond yield. This almost always means an "
            "input is wrong -- check that price and face_value use the same "
            "units and that maturity and frequency are correct. Refusing to "
            "return a number rather than report a meaningless yield."
            % (label, price, y * 100.0))
    return y


def yield_to_maturity(price: float, face_value: float, coupon_rate: float,
                      years_to_maturity: float, frequency: int = 2
                      ) -> CalcResult:
    """
    YTM by bisection on the clean price at a coupon date.

    `price` is the CLEAN price. Passing a dirty price overstates the yield.
    """
    p = _num(price, "price")
    if p <= 0:
        raise ValueError("price must be > 0, got %g" % p)
    fv = _num(face_value, "face_value")
    if fv <= 0:
        raise ValueError("face_value must be > 0, got %g" % fv)
    c = _rate(coupon_rate, "coupon_rate")
    if c < 0:
        raise ValueError("coupon_rate must be >= 0, got %g" % c)
    f = _freq(frequency)
    yrs = _num(years_to_maturity, "years_to_maturity")
    if yrs <= 0:
        raise ValueError("years_to_maturity must be > 0, got %g" % yrs)
    n_exact = yrs * f
    n = int(round(n_exact))
    if abs(n_exact - n) > 1e-9:
        raise ValueError("years_to_maturity x frequency must be a whole "
                         "number of periods (got %g)" % n_exact)
    y = _solve_yield(p, fv, c, n, f, fv, "yield_to_maturity")
    return CalcResult("yield_to_maturity", y,
                      "solve price = sum(C/(1+y/f)^t) + F/(1+y/f)^n for y",
                      {"price": p, "face_value": fv, "coupon_rate": c,
                       "frequency": f, "n_periods": n,
                       "method": "bisection", "tolerance": 1e-14},
                      "fraction (annual nominal)",
                      "Assumes all coupons reinvested at the YTM and the bond "
                      "held to maturity. Price must be CLEAN.")


def yield_to_call(price: float, face_value: float, coupon_rate: float,
                  years_to_call: float, call_price: float,
                  frequency: int = 2) -> CalcResult:
    """
    Yield to call: same solve, but redeeming at `call_price` on the call date.

    For a callable bond trading above par, YTC is usually below YTM and is the
    relevant yield. Quoting YTM alone on a callable bond overstates the return.
    """
    p = _num(price, "price")
    if p <= 0:
        raise ValueError("price must be > 0, got %g" % p)
    fv = _num(face_value, "face_value")
    if fv <= 0:
        raise ValueError("face_value must be > 0, got %g" % fv)
    cp = _num(call_price, "call_price")
    if cp <= 0:
        raise ValueError("call_price must be > 0, got %g" % cp)
    c = _rate(coupon_rate, "coupon_rate")
    if c < 0:
        raise ValueError("coupon_rate must be >= 0, got %g" % c)
    f = _freq(frequency)
    yrs = _num(years_to_call, "years_to_call")
    if yrs <= 0:
        raise ValueError("years_to_call must be > 0, got %g" % yrs)
    n_exact = yrs * f
    n = int(round(n_exact))
    if abs(n_exact - n) > 1e-9:
        raise ValueError("years_to_call x frequency must be a whole number of "
                         "periods (got %g)" % n_exact)
    y = _solve_yield(p, fv, c, n, f, cp, "yield_to_call")
    return CalcResult("yield_to_call", y,
                      "solve price = sum(C/(1+y/f)^t) + call_price/(1+y/f)^n",
                      {"price": p, "face_value": fv, "coupon_rate": c,
                       "call_price": cp, "frequency": f, "n_periods": n,
                       "method": "bisection"},
                      "fraction (annual nominal)",
                      "Report the lower of YTM and YTC (yield-to-worst) when "
                      "the bond is callable.")


# --------------------------------------------------------------------------
# Interest-rate risk
# --------------------------------------------------------------------------

def _duration_parts(fv, c, y, n, f, redemption=None):
    """Return (price, macaulay_years) computed from discounted cash flows."""
    if redemption is None:
        redemption = fv
    cpn = fv * c / f
    per = y / f
    price = 0.0
    weighted = 0.0
    for t in range(1, n + 1):
        cf = cpn + (redemption if t == n else 0.0)
        d = (1.0 + per) ** (-t)
        pv = cf * d
        price += pv
        weighted += pv * (t / f)          # time in YEARS
    return price, weighted


def macaulay_duration(face_value: float, coupon_rate: float, ytm: float,
                      years_to_maturity: float, frequency: int = 2
                      ) -> CalcResult:
    """PV-weighted average time to cash flows, in years."""
    fv = _num(face_value, "face_value")
    if fv <= 0:
        raise ValueError("face_value must be > 0, got %g" % fv)
    c = _rate(coupon_rate, "coupon_rate")
    if c < 0:
        raise ValueError("coupon_rate must be >= 0, got %g" % c)
    y = _rate(ytm, "ytm")
    f = _freq(frequency)
    yrs = _num(years_to_maturity, "years_to_maturity")
    if yrs <= 0:
        raise ValueError("years_to_maturity must be > 0, got %g" % yrs)
    n = int(round(yrs * f))
    if abs(yrs * f - n) > 1e-9:
        raise ValueError("years x frequency must be a whole number of periods")
    price, weighted = _duration_parts(fv, c, y, n, f)
    if price <= 0:
        raise ValueError("macaulay_duration: non-positive price; inputs are "
                         "inconsistent")
    d = weighted / price
    return CalcResult("macaulay_duration", d,
                      "sum(t x PV(CF_t)) / price, t in years",
                      {"face_value": fv, "coupon_rate": c, "ytm": y,
                       "frequency": f, "n_periods": n, "price": price},
                      "years",
                      "For a zero-coupon bond this equals maturity exactly.")


def modified_duration(face_value: float, coupon_rate: float, ytm: float,
                      years_to_maturity: float, frequency: int = 2
                      ) -> CalcResult:
    """
    Modified duration = Macaulay / (1 + y/f). Returned POSITIVE.

    Price sensitivity is dP/P = -ModDur x dy; the minus sign lives in the
    formula, not in the stored value.
    """
    mac = macaulay_duration(face_value, coupon_rate, ytm,
                            years_to_maturity, frequency)
    y = _rate(ytm, "ytm")
    f = _freq(frequency)
    md = mac.value / (1.0 + y / f)
    return CalcResult("modified_duration", md,
                      "macaulay_duration / (1 + ytm/frequency)",
                      {"macaulay_duration": mac.value, "ytm": y,
                       "frequency": f,
                       "price": mac.inputs["price"]},
                      "years",
                      "Reported positive. Price change ~ -ModDur x dy; a "
                      "+1% yield move implies roughly -ModDur% in price.")


def convexity(face_value: float, coupon_rate: float, ytm: float,
              years_to_maturity: float, frequency: int = 2) -> CalcResult:
    """
    Convexity in years^2, the second-order price/yield term.

    Duration alone underestimates price gains when yields fall and
    overestimates losses when they rise; convexity is that correction.
    """
    fv = _num(face_value, "face_value")
    if fv <= 0:
        raise ValueError("face_value must be > 0, got %g" % fv)
    c = _rate(coupon_rate, "coupon_rate")
    if c < 0:
        raise ValueError("coupon_rate must be >= 0, got %g" % c)
    y = _rate(ytm, "ytm")
    f = _freq(frequency)
    yrs = _num(years_to_maturity, "years_to_maturity")
    if yrs <= 0:
        raise ValueError("years_to_maturity must be > 0, got %g" % yrs)
    n = int(round(yrs * f))
    if abs(yrs * f - n) > 1e-9:
        raise ValueError("years x frequency must be a whole number of periods")
    cpn = fv * c / f
    per = y / f
    price = 0.0
    acc = 0.0
    for t in range(1, n + 1):
        cf = cpn + (fv if t == n else 0.0)
        d = (1.0 + per) ** (-t)
        price += cf * d
        acc += cf * t * (t + 1) * (1.0 + per) ** (-(t + 2))
    if price <= 0:
        raise ValueError("convexity: non-positive price")
    cx = acc / (price * f * f)
    return CalcResult("convexity", cx,
                      "sum(CF_t x t(t+1)/(1+y/f)^(t+2)) / (price x f^2)",
                      {"face_value": fv, "coupon_rate": c, "ytm": y,
                       "frequency": f, "n_periods": n, "price": price},
                      "years^2",
                      "Second-order term: dP/P ~ -ModDur x dy + "
                      "0.5 x convexity x dy^2.")


def dv01(face_value: float, coupon_rate: float, ytm: float,
         years_to_maturity: float, frequency: int = 2) -> CalcResult:
    """
    DV01 (PV01): price change in CURRENCY for a 1 basis point yield rise.

    Computed by full revaluation at y +/- 0.5bp (a central difference), not
    from the duration approximation -- DV01 is used for hedging, where the
    approximation error is the thing you are trying to avoid.

    Returned POSITIVE as a magnitude; a yield RISE moves price DOWN by DV01.
    """
    fv = _num(face_value, "face_value")
    if fv <= 0:
        raise ValueError("face_value must be > 0, got %g" % fv)
    c = _rate(coupon_rate, "coupon_rate")
    if c < 0:
        raise ValueError("coupon_rate must be >= 0, got %g" % c)
    y = _rate(ytm, "ytm")
    f = _freq(frequency)
    yrs = _num(years_to_maturity, "years_to_maturity")
    if yrs <= 0:
        raise ValueError("years_to_maturity must be > 0, got %g" % yrs)
    n = int(round(yrs * f))
    if abs(yrs * f - n) > 1e-9:
        raise ValueError("years x frequency must be a whole number of periods")
    bump = 0.00005                      # half a basis point each side
    p_up = _price_from_yield(fv, c, y + bump, n, f)
    p_dn = _price_from_yield(fv, c, y - bump, n, f)
    v = (p_dn - p_up)                   # positive: price falls as yield rises
    p0 = _price_from_yield(fv, c, y, n, f)
    return CalcResult("dv01", v,
                      "central difference: (P(y-0.5bp) - P(y+0.5bp)) for a "
                      "1bp move",
                      {"face_value": fv, "coupon_rate": c, "ytm": y,
                       "frequency": f, "n_periods": n, "price": p0,
                       "price_up_half_bp": p_up, "price_down_half_bp": p_dn,
                       "method": "full revaluation"},
                      "currency per 1bp",
                      "Magnitude. A 1bp yield RISE reduces price by this "
                      "amount.")
