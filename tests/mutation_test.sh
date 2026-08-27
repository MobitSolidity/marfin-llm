#!/bin/bash
# Mutation harness for the full calculation engine (Phase 2 + R14).
#
# WHY THIS EXISTS
# A test suite that passes proves nothing on its own -- it may simply be
# asserting things that are true of any implementation. This harness seeds a
# realistic defect into the source, re-runs the suite, and requires the suite
# to FAIL. A mutation that survives is a gap in the tests, not a success.
#
# In Phase 2 this found two real gaps (the Sortino divisor and a missing abs()
# that returned NEGATIVE position sizes on short trades). Neither was findable
# by reading the code.
#
# STALE .pyc HAZARD
# Clears __pycache__ around every run. A same-size edit restored within the
# same second defeats Python's mtime+size cache validation, which silently
# corrupted an earlier mutation run and briefly made the results meaningless.
cd "$(dirname "$0")/.."

TMP=/tmp/mutate_orig
mkdir -p "$TMP"
MUTATED=""
for m in returns_risk valuation technicals fixed_income derivatives; do
  cp "src/calc/$m.py" "$TMP/$m.py"
done

# R23 KILL-SAFETY. Added 2026-08-27.
#
# This script PATCHES SOURCE IN PLACE (`sed -i` in run_mut) and restores it a
# few lines later. Everything between those two points is a window in which the
# working tree holds MUTATED source. Before this change there was NO trap and
# NO time limit, so any interruption in that window -- Ctrl-C, an outer tool
# killing the process at its own limit, or a mutant that simply never
# terminates -- left a patched calculation module on disk.
#
# That is not hypothetical. MEASURED this session: an equivalent gap in
# tests/mutate_llm_providers.py left src/llm/console.py mutated after an outer
# 120s cut, and the same class of incident previously hit src/tools/selector.py.
# The corruption is SILENT: the next run tests mutated source and reports green.
#
# The trap fires on ordinary exit and on the three interruption signals, and
# restores every module from the pristine copies taken above. It is
# unconditional and idempotent -- restoring an unmutated file is a no-op, which
# is far cheaper than reasoning about whether a restore is needed.
#
# WHAT THE TRAP DOES *NOT* DO -- MEASURED, NOT ASSUMED.
# A trap is NOT sufficient on its own, and it would be dangerous to believe it
# were. bash DEFERS a trap while a foreground child is running. Tested on this
# machine with a replica of this script that mutates a file and then sleeps:
#
#   kill -TERM <script pid>   -> file left at MAGIC_VALUE = 999  (NOT restored)
#   kill -TERM -<process grp>  -> file left at MAGIC_VALUE = 999  (NOT restored)
#
# In both cases the signal reached the shell but the child kept running, so the
# handler stayed PENDING and the mutated file survived on disk.
#
# What actually works is removing the unbounded child, which is what
# MUT_TIMEOUT below does. Same replica, oracle wrapped in `timeout`:
#
#   timeout -s INT --kill-after=5 3 sleep 600
#     -> child rc=124, script continues to normal exit, EXIT trap runs,
#        file restored to MAGIC_VALUE = 1  (md5 bb428a11 == original)
#
# So the two halves are NOT redundant and neither is decoration:
#   * MUT_TIMEOUT guarantees the script REACHES its exit rather than hanging.
#   * the EXIT trap guarantees that reaching the exit RESTORES the source,
#     including on the `set -e`-style early exits and on Ctrl-C typed between
#     two mutants rather than during one.
# The residual hole is an outer SIGKILL, which no in-process mechanism can
# survive; that is why the run should be launched in the background rather than
# under a tool with its own hard cut.
restore_all() {
  for m in returns_risk valuation technicals fixed_income derivatives; do
    [ -f "$TMP/$m.py" ] && cp "$TMP/$m.py" "src/calc/$m.py"
  done
}
on_interrupt() {
  echo
  echo "  INTERRUPTED: restoring all calculation sources from $TMP"
  restore_all
  echo "  source restored. Verify with: git status && git diff --stat"
  exit 130
}
trap on_interrupt INT TERM HUP
trap restore_all EXIT

# Budget for ONE mutant's oracle run. Generous, because the point is not to be
# tight -- it is that no value is INFINITE. A mutant that stops the suite from
# terminating is the case that orphaned mutated source before.
MUT_TIMEOUT=300

TOTAL=0
KILLED=0
SURVIVED=0
TIMEDOUT=0
SKIPPED=0

clear_cache() {
  find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
}

# run_mut <module> <test-file> <description> <sed-pattern> <replacement>
run_mut() {
  mod="$1"; testfile="$2"; desc="$3"; pat="$4"; rep="$5"
  TOTAL=$((TOTAL + 1))
  src="src/calc/$mod.py"
  sed -i "s|$pat|$rep|" "$src"
  if ! diff -q "$TMP/$mod.py" "$src" >/dev/null; then
    clear_cache
    # `-s INT`, not the default SIGTERM. MEASURED: SIGTERM kills Python where
    # it stands and `finally` does NOT run, while SIGINT raises
    # KeyboardInterrupt and unwinds normally. Here it also means the oracle
    # child cannot be left holding a half-written temp file.
    raw=$(timeout -s INT --kill-after=20 "$MUT_TIMEOUT" \
          python3 "tests/$testfile" 2>&1)
    rc=$?
    out=$(echo "$raw" | grep "^RESULT")
    if [ $rc -eq 124 ] || [ $rc -eq 137 ]; then
      # A TIMEOUT COUNTS AS A KILL, not as an error. "The suite no longer
      # finishes" IS the suite noticing the defect. Treating it as a harness
      # failure instead would let a non-terminating mutant abort the whole run
      # and be reported as nothing at all.
      echo "  killed    $desc  (oracle exceeded ${MUT_TIMEOUT}s)"
      KILLED=$((KILLED + 1))
      TIMEDOUT=$((TIMEDOUT + 1))
    elif echo "$out" | grep -q "0 failed"; then
      echo "  SURVIVED  $desc  <-- GAP"
      SURVIVED=$((SURVIVED + 1))
    else
      echo "  killed    $desc"
      KILLED=$((KILLED + 1))
    fi
  else
    echo "  SKIPPED   $desc  (pattern did not match)"
    SKIPPED=$((SKIPPED + 1))
  fi
  cp "$TMP/$mod.py" "$src"
  clear_cache
}

echo "=== RETURNS AND RISK (13 seeded defects) ==="
run_mut returns_risk test_returns_risk.py "sortino: downside-count divisor" 'dd = math.sqrt(sum(d \* d for d in downside) / len(excess))' 'dd = math.sqrt(sum(d*d for d in downside)/max(1,len([d for d in downside if d<0])))'
run_mut returns_risk test_returns_risk.py "stdev: population not sample" 'denom = n - 1 if sample else n' 'denom = n'
run_mut returns_risk test_returns_risk.py "cvar: mean of all not tail" '    v = mean(tail)' '    v = mean(s)'
run_mut returns_risk test_returns_risk.py "position_size: drop abs()" 'per_unit = abs(entry - stop)' 'per_unit = entry - stop'
run_mut returns_risk test_returns_risk.py "risk_reward: drop abs()" 'reward = abs(target - entry)' 'reward = target - entry'
run_mut returns_risk test_returns_risk.py "vol: forget sqrt" 'v = sd \* math.sqrt(ppy)' 'v = sd * ppy'
run_mut returns_risk test_returns_risk.py "beta: stdev not variance" 'v = cov / var_m' 'v = cov / math.sqrt(var_m)'
run_mut returns_risk test_returns_risk.py "cagr: arithmetic not geometric" 'v = (end / start) \*\* (1.0 / years) - 1.0' 'v = (end/start - 1.0)/years'
run_mut returns_risk test_returns_risk.py "sharpe: skip rf de-annualize" 'rf_period = (1.0 + risk_free_rate) \*\* (1.0 / ppy) - 1.0' 'rf_period = risk_free_rate'
run_mut returns_risk test_returns_risk.py "hhi: sum w not w^2" 'v = sum(w \* w for w in norm)' 'v = sum(norm)'
run_mut returns_risk test_returns_risk.py "var: wrong quantile" 'idx = int(math.floor((1.0 - confidence) \* len(s)))' 'idx = int(math.floor(confidence*len(s)))'
run_mut returns_risk test_returns_risk.py "maxdd: best not worst" 'if dd < mdd:' 'if dd > mdd:'
run_mut returns_risk test_returns_risk.py "annret: drop compounding" 'growth \*= (1.0 + r)' 'growth += r'

echo ""
echo "=== VALUATION (10 seeded defects) ==="
run_mut valuation test_valuation.py "dcf: discount from period 0" 't = (i - 0.5) if mid_year else float(i)' 't = (i - 0.5) if mid_year else float(i - 1)'
run_mut valuation test_valuation.py "dcf: terminal growth in wrong place" 'tv = cash_flows\[-1\] \* (1.0 + g) / (r - g)' 'tv = cash_flows[-1] / (r - g)'
run_mut valuation test_valuation.py "dcf: add net debt instead of subtract" 'equity = enterprise - _num(net_debt, "net_debt")' 'equity = enterprise + _num(net_debt, "net_debt")'
run_mut valuation test_valuation.py "ddm: forget to grow D0" 'd1 = d if dividend_is_next_period else d \* (1.0 + g)' 'd1 = d'
run_mut valuation test_valuation.py "pe: allow negative EPS" 'if e <= 0:' 'if False:'
run_mut valuation test_valuation.py "ev: add cash instead of subtract" 'ev = mc + d - c + mi + pf' 'ev = mc + d + c + mi + pf'
run_mut valuation test_valuation.py "peg: accept fraction growth" 'if g < 1.0:' 'if False:'
run_mut valuation test_valuation.py "roic: forget the tax shield" 'nopat = e \* (1.0 - t)' 'nopat = e'
run_mut valuation test_valuation.py "fcf: add capex instead of subtract" 'return CalcResult("free_cash_flow", cfo - capex' 'return CalcResult("free_cash_flow", cfo + capex'
run_mut valuation test_valuation.py "quick ratio: forget to exclude inventory" 'return CalcResult("quick_ratio", (ca - inv) / cl' 'return CalcResult("quick_ratio", ca / cl'

echo ""
echo "=== TECHNICALS (11 seeded defects) ==="
run_mut technicals test_technicals.py "wilder: use SMA smoothing instead" 'out.append((out\[-1\] \* (period - 1) + v) / period)' 'out.append(v)'
run_mut technicals test_technicals.py "ema: seed with first price" 'seed = sum(prices\[:period\]) / period' 'seed = prices[0]'
run_mut technicals test_technicals.py "ema: wrong alpha" 'alpha = 2.0 / (period + 1.0)' 'alpha = 1.0 / period'
run_mut technicals test_technicals.py "wma: reverse the weights" 'weights = list(range(1, period + 1))' 'weights = list(range(period, 0, -1))'
run_mut technicals test_technicals.py "rsi: invert the formula" 'out.append(100.0 - 100.0 / (1.0 + rs))' 'out.append(100.0 / (1.0 + rs))'
run_mut technicals test_technicals.py "macd: subtract in wrong order" 'macd_line = \[f - s for f, s in zip(fast_s\[offset:\], slow_s)\]' 'macd_line = [s - f for f, s in zip(fast_s[offset:], slow_s)]'
run_mut technicals test_technicals.py "bollinger: sample stdev by default" 'sd = _sstdev(window) if sample else _pstdev(window)' 'sd = _sstdev(window)'
run_mut technicals test_technicals.py "bollinger: bands on wrong side" 'out.append((mid\[j\] + num_std \* sd, mid\[j\], mid\[j\] - num_std \* sd, sd))' 'out.append((mid[j] - num_std * sd, mid[j], mid[j] + num_std * sd, sd))'
run_mut technicals test_technicals.py "true range: ignore the gap" 'out.append(max(highs\[i\] - lows\[i\], abs(highs\[i\] - pc),' 'out.append(max(highs[i] - lows[i], 0.0, abs(0.0)*abs(highs[i] - pc),'
run_mut technicals test_technicals.py "adx: leak direction into index" 'dx.append(0.0 if s == 0 else 100.0 \* abs(dp - dm) / s)' 'dx.append(0.0 if s == 0 else 100.0 * (dp - dm) / s)'
run_mut technicals test_technicals.py "obv: add volume on down closes" 'out.append(out\[-1\] - volumes\[i\])' 'out.append(out[-1] + volumes[i])'

echo ""
echo "=== FIXED INCOME (10 seeded defects) ==="
run_mut fixed_income test_fixed_income.py "price: forget principal repayment" 'pv_principal = fv \* disc \*\* (-n)' 'pv_principal = 0.0'
run_mut fixed_income test_fixed_income.py "price: annual coupon, ignore frequency" 'cpn = fv \* c / f' 'cpn = fv * c'
run_mut fixed_income test_fixed_income.py "price: do not de-annualize yield" '    y = ytm / f' '    y = ytm'
run_mut fixed_income test_fixed_income.py "accrued: invert the accrual fraction" 'ai = cpn \* (d1 / d2)' 'ai = cpn * (d2 / d1)'
run_mut fixed_income test_fixed_income.py "dirty: subtract accrued instead of add" 'return CalcResult("dirty_price", cp + ai' 'return CalcResult("dirty_price", cp - ai'
run_mut fixed_income test_fixed_income.py "duration: weight in periods not years" 'weighted += pv \* (t / f)' 'weighted += pv * t'
run_mut fixed_income test_fixed_income.py "modified: divide by (1+y) not (1+y/f)" 'md = mac.value / (1.0 + y / f)' 'md = mac.value / (1.0 + y)'
run_mut fixed_income test_fixed_income.py "modified: return macaulay unchanged" 'md = mac.value / (1.0 + y / f)' 'md = mac.value'
run_mut fixed_income test_fixed_income.py "dv01: wrong sign direction" 'v = (p_dn - p_up)' 'v = (p_up - p_dn)'
run_mut fixed_income test_fixed_income.py "convexity: drop the f^2 scaling" 'cx = acc / (price \* f \* f)' 'cx = acc / price'

echo ""
echo "=== DERIVATIVES (12 seeded defects) ==="
run_mut derivatives test_derivatives.py "BS: swap d1 and d2" 'price = s \* df_q \* _norm_cdf(d1) - k \* df_r \* _norm_cdf(d2)' 'price = s * df_q * _norm_cdf(d2) - k * df_r * _norm_cdf(d1)'
run_mut derivatives test_derivatives.py "BS: forget to discount the strike" 'price = s \* df_q \* _norm_cdf(d1) - k \* df_r \* _norm_cdf(d2)' 'price = s * df_q * _norm_cdf(d1) - k * _norm_cdf(d2)'
run_mut derivatives test_derivatives.py "BS: wrong sign on vol term in d1" 'd1 = (math.log(s / k) + (r - q + 0.5 \* sigma \* sigma) \* t) / v' 'd1 = (math.log(s / k) + (r - q - 0.5 * sigma * sigma) * t) / v'
run_mut derivatives test_derivatives.py "BS: put formula uses wrong tails" 'price = k \* df_r \* _norm_cdf(-d2) - s \* df_q \* _norm_cdf(-d1)' 'price = k * df_r * _norm_cdf(d2) - s * df_q * _norm_cdf(d1)'
run_mut derivatives test_derivatives.py "black76: drop the discount factor" 'price = df \* (f \* _norm_cdf(d1) - k \* _norm_cdf(d2))' 'price = (f * _norm_cdf(d1) - k * _norm_cdf(d2))'
run_mut derivatives test_derivatives.py "binomial: wrong risk-neutral prob" 'p = (math.exp((r - q) \* dt) - d) / (u - d)' 'p = 0.5'
run_mut derivatives test_derivatives.py "binomial: allow early exercise always" 'if american:' 'if True:'
run_mut derivatives test_derivatives.py "delta: drop the dividend discount" 'v = df_q \* _norm_cdf(d1) if kind == "call" else -df_q \* _norm_cdf(-d1)' 'v = _norm_cdf(d1) if kind == "call" else -_norm_cdf(-d1)'
run_mut derivatives test_derivatives.py "gamma: divide by S only" 'v = math.exp(-q \* t) \* _norm_pdf(d1) / (s \* sg \* math.sqrt(t))' 'v = math.exp(-q * t) * _norm_pdf(d1) / s'
run_mut derivatives test_derivatives.py "vega: forget sqrt(T)" 'v = s \* math.exp(-q \* t) \* _norm_pdf(d1) \* math.sqrt(t)' 'v = s * math.exp(-q * t) * _norm_pdf(d1) * t'
run_mut derivatives test_derivatives.py "theta: return annual as per-day" '"per_day": v / DAYS_PER_YEAR' '"per_day": v'
run_mut derivatives test_derivatives.py "liquidation: wrong side of entry" 'p = e \* (1.0 - 1.0 / lev + mmr)' 'p = e * (1.0 + 1.0 / lev - mmr)'

echo ""
echo "=== integrity check ==="
INTACT=1
for m in returns_risk valuation technicals fixed_income derivatives; do
  if ! diff -q "$TMP/$m.py" "src/calc/$m.py" >/dev/null; then
    echo "  ERROR: src/calc/$m.py NOT restored"
    INTACT=0
  fi
done
[ "$INTACT" = "1" ] && echo "  all sources restored intact"

echo ""
echo "=== MUTATION SUMMARY ==="
echo "  seeded:   $TOTAL"
echo "  killed:   $KILLED"
echo "  survived: $SURVIVED"
echo "  skipped:  $SKIPPED"
# Printed only when non-zero would be the wrong choice here for the same reason
# the SKIPPED line is unconditional: a counter whose absence is ambiguous
# teaches the reader nothing. A timeout was counted as a KILL above, so without
# this line a non-terminating mutant would be indistinguishable from a mutant
# the suite actually detected -- and those are very different facts.
echo "  of which timed out: $TIMEDOUT (counted as kills; see MUT_TIMEOUT)"
if [ "$SURVIVED" != "0" ] || [ "$SKIPPED" != "0" ] || [ "$INTACT" != "1" ]; then
  exit 1
fi
exit 0
