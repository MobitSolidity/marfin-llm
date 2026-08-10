#!/bin/bash
# Run the full Phase 2 verification suite.
#   ./tests/run_all.sh          unit tests only
#   ./tests/run_all.sh --mutate unit tests + mutation battery (slower)
cd "$(dirname "$0")/.."

# Stale bytecode has silently invalidated a mutation run before; always clear.
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null

fail=0
echo "=============================================================="
echo "PHASE 2 VERIFICATION SUITE"
echo "=============================================================="

for t in tests/test_returns_risk.py tests/test_tools.py; do
  echo
  echo ">>> $t"
  if python3 "$t" | tail -3 | grep -q "0 failed"; then
    python3 "$t" 2>&1 | grep "^RESULT"
  else
    python3 "$t" 2>&1 | grep -E "^  FAIL|^RESULT"
    fail=1
  fi
done

if [ "$1" = "--mutate" ]; then
  echo
  echo ">>> mutation battery"
  out=$(./tests/mutation_test.sh 2>&1)
  echo "$out" | grep -E "SURVIVED|SKIPPED" && fail=1
  echo "  killed $(echo "$out" | grep -c killed)/13 seeded defects"
  echo "$out" | grep "restored intact" || { echo "  ERROR: source not restored"; fail=1; }
fi

echo
echo "=============================================================="
[ $fail -eq 0 ] && echo "ALL GREEN" || echo "FAILURES PRESENT"
echo "=============================================================="
exit $fail
