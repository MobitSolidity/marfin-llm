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
tests/test_rag.py \
tests/test_market.py \
tests/test_execution.py \
tests/test_csv_import.py \
tests/test_webhooks.py"

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

# The market-data layer's adversarial probe. Runs unconditionally for the same
# reason as the TradingView wall: its failure mode is a plausible-looking wrong
# price rather than a crash. Two defects here (last=0.0 and last=inf, both
# ACCEPTED) survived a probe that reported 45/45 refused, so this gate is what
# stops the next one from surviving a whole session.
echo
echo ">>> market data quote guards (adversarial probe)"
mqout=$(python3 tests/probe_quotes.py 2>&1)
mq_status=$?
echo "$mqout" | grep -E "^ +(\*\* ALLOWED|!! CRASHED)"
echo "$mqout" | grep -E "^attempts="
if [ $mq_status -ne 0 ]; then
  echo "  ERROR: an unusable quote was accepted by the market data layer"
  fail=1
fi

# The CSV ingestion probe. Its failure mode is the quietest one in the project:
# parse_csv returns a REPORT rather than raising, so a defective file does not
# announce itself -- the worst case found here was a file with every close blank
# that carried no finding at all and was therefore usable for a material
# calculation. "Did it refuse?" is the wrong question for such a module, so this
# probe asserts two different things: structural attacks must raise, and semantic
# defects must be RECORDED at the right severity AND actually enforced.
echo
echo ">>> CSV ingestion validation (adversarial probe)"
csvout=$(python3 tests/probe_csv_import.py 2>&1)
csv_status=$?
csvout_bad=$(echo "$csvout" | grep -E "\*\* ALLOWED|!! CRASHED|\*\* NO FINDING|\*\* WRONG SEVERITY|\*\* NOT ENFORCED|\*\* FALSE REASON")
[ -n "$csvout_bad" ] && echo "$csvout_bad"
echo "$csvout" | grep -E "^(class A|class B|invariants)"
if [ $csv_status -ne 0 ]; then
  echo "  ERROR: a defective CSV was accepted, or a finding was not enforced"
  fail=1
fi

# The webhook probe. This is the only module in the project that takes input from
# a party outside it, so it is the one boundary where an attacker chooses the
# bytes. Its failure mode is the worst available here: a payload field taken as
# an ORDER. Three defects survived a clean adversarial sweep in this module --
# a type named ValidatedEvent that validated nothing, an origin label that would
# have been "fixed" by deleting a working guard, and an exact-match blocklist
# that let "disable_risk_checks" through while listing "disable_risk". None was
# found by a test failing; all three were found by attacking the passes.
echo
echo ">>> webhook receiver validation (adversarial probe)"
whout=$(python3 tests/probe_webhooks.py 2>&1)
wh_status=$?
whout_bad=$(echo "$whout" | grep -E "\*\* ALLOWED|!! CRASHED|\*\* WRONG EXC|\*\* WRONG GUARD|\*\* DEFECT")
[ -n "$whout_bad" ] && echo "$whout_bad"
echo "$whout" | grep -E "^(attacks|structural checks):"
if [ $wh_status -ne 0 ]; then
  echo "  ERROR: a webhook attack was accepted, or refused by the wrong guard"
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

  echo
  echo ">>> market data mutation battery"
  # Oracles are test_market.py AND probe_quotes.py together: one catches
  # mutations that make the layer accept garbage, the other catches mutations
  # that make it refuse everything. Running only one lets half the classes
  # through -- MEASURED, not assumed.
  mkt=$(python3 tests/mutate_market.py 2>&1)
  mkt_status=$?
  echo "$mkt" | grep -E "^ +(seeded|killed|equivalent|survived|skipped):"
  echo "$mkt" | grep -E "^ +(survived|skipped): +[1-9]" && fail=1
  echo "$mkt" | grep -E "^ +RECHECK:" && fail=1
  [ $mkt_status -ne 0 ] && fail=1

  echo
  echo ">>> execution mode / broker mutation battery"
  # The battery that matters most: every other module can at worst produce a
  # wrong number for a human to read, while this one decides whether an order can
  # be submitted with real money. It found 17 survivors on a suite that passed
  # 93/93, including a docstring claiming live trading was unreachable when a
  # two-line config file reached it.
  exe=$(python3 tests/mutate_execution.py 2>&1)
  exe_status=$?
  echo "$exe" | grep -E "^ +(seeded|killed|equivalent|survived|skipped):"
  echo "$exe" | grep -E "^ +(survived|skipped): +[1-9]" && fail=1
  echo "$exe" | grep -E "^ +RECHECK:" && fail=1
  [ $exe_status -ne 0 ] && fail=1

  echo
  echo ">>> CSV ingestion mutation battery"
  # This battery earned its place twice over. It reported 23 survivors on a suite
  # that printed "218 passed, 0 failed" -- and 20 of them were one defect in the
  # SUITE, not the module: it ended with a bare summary(), which RETURNS an exit
  # code rather than raising, so the suite always exited 0 and could not report
  # failure at all. A suite that cannot fail manufactures confidence, and only a
  # mutation battery can detect one. The remaining 3 were real test gaps,
  # including a null-close guard shadowed by an earlier guard.
  csvm=$(python3 tests/mutate_csv_import.py 2>&1)
  csvm_status=$?
  echo "$csvm" | grep -E "^ +(seeded|killed|equivalent|survived|skipped):"
  echo "$csvm" | grep -E "^ +(survived|skipped): +[1-9]" && fail=1
  echo "$csvm" | grep -E "^ +RECHECK:" && fail=1
  # A SKIP is worse than a survivor: an ambiguous pattern tests nothing while
  # still counting in "seeded", so it looks like a non-event.
  echo "$csvm" | grep -q "source restored and oracles green: True" || {
    echo "  ERROR: csv_import.py not restored, or its oracles are not green"
    fail=1; }
  [ $csvm_status -ne 0 ] && fail=1

  echo
  echo ">>> webhook receiver mutation battery"
  # Two oracles, and the pairing is required rather than tidy: test_webhooks.py
  # catches mutations that make the receiver ACCEPT an attack, probe_webhooks.py
  # catches mutations that make it refuse everything. This battery went from 13
  # survivors to 0 without one line of the module changing -- every one was a
  # gap in the TESTS, and most were a second guard answering in place of the one
  # under test (an http:// refusal that came from the generic scheme check, a
  # duplicate refused by append() when receive()'s check was gone, a
  # UnicodeDecodeError counted as a refusal because it subclasses ValueError).
  # Exactly one mutant is documented as equivalent, with the eight measurements
  # that failed to reach it; RECHECK below fires if it ever starts dying.
  whm=$(python3 tests/mutate_webhooks.py 2>&1)
  whm_status=$?
  echo "$whm" | grep -E "^ +(seeded|killed|equivalent|survived|skipped):"
  echo "$whm" | grep -E "^ +(survived|skipped): +[1-9]" && fail=1
  echo "$whm" | grep -E "^ +RECHECK:" && fail=1
  echo "$whm" | grep -q "source restored and oracles green: True" || {
    echo "  ERROR: webhooks.py not restored, or its oracles are not green"
    fail=1; }
  [ $whm_status -ne 0 ] && fail=1
fi

echo
echo "=============================================================="
[ $fail -eq 0 ] && echo "ALL GREEN" || echo "FAILURES PRESENT"
echo "=============================================================="
exit $fail
