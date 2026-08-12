#!/bin/bash
# Run the full deterministic-calculation verification suite.
#   ./tests/run_all.sh          unit tests only
#   ./tests/run_all.sh --mutate unit tests + mutation battery (slower)
cd "$(dirname "$0")/.."

# Stale bytecode has silently invalidated a mutation run before; always clear.
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null

fail=0
total_pass=0
echo "=============================================================="
echo "DETERMINISTIC CALCULATION VERIFICATION SUITE"
echo "=============================================================="

SUITES="tests/test_returns_risk.py \
tests/test_valuation.py \
tests/test_technicals.py \
tests/test_fixed_income.py \
tests/test_derivatives.py \
tests/test_tools.py \
tests/test_selector.py \
tests/test_rag.py"

for t in $SUITES; do
  echo
  echo ">>> $t"
  # Run ONCE and keep the output. Running twice doubled the cost and could
  # mask a nondeterministic failure by reporting a different run than it tested.
  out=$(python3 "$t" 2>&1)
  status=$?
  echo "$out" | grep -E "^  FAIL|^  SKIP|^  INFO"
  echo "$out" | grep "^RESULT"
  n=$(echo "$out" | sed -n 's/^RESULT: \([0-9]*\) passed.*/\1/p')
  total_pass=$((total_pass + ${n:-0}))
  if [ $status -ne 0 ]; then
    fail=1
  fi
done

echo
# Count the suites rather than hardcoding a number; a hardcoded "/13" already
# understated one battery, and a stale suite count hides a suite that stopped
# running entirely.
n_suites=$(echo $SUITES | wc -w)
echo "  TOTAL: $total_pass assertions passed across $n_suites suites"

# The TradingView wall is the one thing in this project whose failure mode is
# legal rather than numerical, so its adversarial probe runs on every pass rather
# than by hand. It is offline (no network) and takes milliseconds.
echo
echo ">>> TradingView display-only wall (adversarial probe)"
tvout=$(python3 tests/probe_tradingview.py 2>&1)
tv_status=$?
echo "$tvout" | grep -E "^ +(\*\* ALLOWED|!! CRASHED)"
echo "$tvout" | grep -E "^attempts="
if [ $tv_status -ne 0 ]; then
  echo "  ERROR: a machine use of TradingView content was not refused"
  fail=1
fi

if [ "$1" = "--mutate" ]; then
  echo
  echo ">>> mutation battery"
  out=$(./tests/mutation_test.sh 2>&1)
  mut_status=$?
  # Read the counts the battery itself reports rather than hardcoding them;
  # the previous hardcoded "/13" silently understated a 56-defect battery.
  echo "$out" | grep -E "^ +(seeded|killed|survived|skipped):"
  # A surviving or skipped mutant means the suite did not discriminate.
  echo "$out" | grep -E "^ +(survived|skipped): +[1-9]" && fail=1
  echo "$out" | grep -q "restored intact" || {
    echo "  ERROR: source not restored to original state"; fail=1; }
  [ $mut_status -ne 0 ] && fail=1

  echo
  echo ">>> selector mutation battery"
  sel=$(python3 tests/mutate_selector.py 2>&1)
  sel_status=$?
  echo "$sel" | grep -E "^ +(seeded|killed|survived|skipped):"
  echo "$sel" | grep -E "^ +(survived|skipped): +[1-9]" && fail=1
  [ $sel_status -ne 0 ] && fail=1

  echo
  echo ">>> RAG mutation battery"
  rag=$(python3 tests/mutate_rag.py 2>&1)
  rag_status=$?
  echo "$rag" | grep -E "^ +(seeded|killed|equivalent|survived|skipped):"
  echo "$rag" | grep -E "^ +(survived|skipped): +[1-9]" && fail=1
  # An "equivalent" mutant that starts dying invalidates its own note.
  echo "$rag" | grep -E "^ +RECHECK:" && fail=1
  [ $rag_status -ne 0 ] && fail=1
fi

echo
echo "=============================================================="
[ $fail -eq 0 ] && echo "ALL GREEN" || echo "FAILURES PRESENT"
echo "=============================================================="
exit $fail
