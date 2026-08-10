#!/bin/bash
# Mutation harness. Clears __pycache__ every run -- a stale .pyc silently
# invalidated an earlier mutation run because same-size edits within the same
# second defeat Python's mtime+size cache check.
cd "$(dirname "$0")/.."
cp src/calc/returns_risk.py /tmp/orig.py
run_mut() {
  desc="$1"; pat="$2"; rep="$3"
  sed -i "s|$pat|$rep|" src/calc/returns_risk.py
  if ! diff -q /tmp/orig.py src/calc/returns_risk.py >/dev/null; then
    find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
    out=$(python3 tests/test_returns_risk.py 2>&1 | grep "^RESULT")
    if echo "$out" | grep -q "0 failed"; then echo "  SURVIVED  $desc  <-- GAP"
    else echo "  killed    $desc"; fi
  else
    echo "  SKIPPED   $desc  (pattern did not match)"
  fi
  cp /tmp/orig.py src/calc/returns_risk.py
  find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
}
echo "=== MUTATION BATTERY (13 seeded defects) ==="
run_mut "sortino: downside-count divisor" 'dd = math.sqrt(sum(d \* d for d in downside) / len(excess))' 'dd = math.sqrt(sum(d*d for d in downside)/max(1,len([d for d in downside if d<0])))'
run_mut "stdev: population not sample" 'denom = n - 1 if sample else n' 'denom = n'
run_mut "cvar: mean of all not tail" '    v = mean(tail)' '    v = mean(s)'
run_mut "position_size: drop abs()" 'per_unit = abs(entry - stop)' 'per_unit = entry - stop'
run_mut "risk_reward: drop abs()" 'reward = abs(target - entry)' 'reward = target - entry'
run_mut "vol: forget sqrt" 'v = sd \* math.sqrt(ppy)' 'v = sd * ppy'
run_mut "beta: stdev not variance" 'v = cov / var_m' 'v = cov / math.sqrt(var_m)'
run_mut "cagr: arithmetic not geometric" 'v = (end / start) \*\* (1.0 / years) - 1.0' 'v = (end/start - 1.0)/years'
run_mut "sharpe: skip rf de-annualize" 'rf_period = (1.0 + risk_free_rate) \*\* (1.0 / ppy) - 1.0' 'rf_period = risk_free_rate'
run_mut "hhi: sum w not w^2" 'v = sum(w \* w for w in norm)' 'v = sum(norm)'
run_mut "var: wrong quantile" 'idx = int(math.floor((1.0 - confidence) \* len(s)))' 'idx = int(math.floor(confidence*len(s)))'
run_mut "maxdd: best not worst" 'if dd < mdd:' 'if dd > mdd:'
run_mut "annret: drop compounding" 'growth \*= (1.0 + r)' 'growth += r'
echo "=== integrity check ==="
diff -q /tmp/orig.py src/calc/returns_risk.py && echo "  source restored intact"
python3 tests/test_returns_risk.py 2>&1 | grep "^RESULT"
