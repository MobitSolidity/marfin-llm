#!/bin/bash
# Run the full deterministic-calculation verification suite.
#   ./tests/run_all.sh          unit tests only
#   ./tests/run_all.sh --mutate unit tests + mutation battery (slower)
cd "$(dirname "$0")/.."

# Stale bytecode has silently invalidated a mutation run before; always clear.
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null

fail=0
total_pass=0
total_skip=0

# ---------------------------------------------------------------------------
# R23 KILL-SAFETY. Added 2026-08-27.
#
# WHY THIS EXISTS. Every python3 call in this driver used to run with NO time
# limit. MEASURED consequence, from a real incident this session: a mutation
# battery seeded a console mutant that stopped the read loop from ever seeing
# EOF (`if raw == "":` -> `if False:`). The child never returned, the OUTER
# tool killed the whole process tree at its own limit, the battery's `finally`
# block therefore never ran (a `finally` does not run on SIGKILL), and
# src/llm/console.py was left MUTATED ON DISK.
#
# That is the dangerous case: the batteries PATCH SOURCE FILES in place and
# rely on cleanup to put them back. A driver that can be killed from outside
# is a driver that can leave the working tree corrupted, and the corruption is
# silent -- the next run tests mutated source and calls it green.
#
# The batteries' own subprocess calls are now guarded internally
# (ORACLE_TIMEOUT in tests/mutate_llm_providers.py). This guards the OTHER
# half: the shell driver that launches them.
#
# WHY `-s INT` AND NOT THE DEFAULT SIGTERM. An earlier version of this comment
# claimed SIGTERM unwinds Python into its `finally` blocks. That was WRONG, and
# it was corrected only because it was tested instead of believed. MEASURED:
#
#   timeout    2 python3 -c 'try: sleep(30)
#                            finally: print("FINALLY RAN")'   -> prints NOTHING
#   timeout -s INT 2 python3 -c '...same...'                  -> prints FINALLY RAN
#
# Default SIGTERM has NO Python-level handler, so the interpreter dies where it
# stands and `finally` never executes. SIGINT raises KeyboardInterrupt, which
# unwinds normally and RUNS `finally`. VERIFIED it still works through command
# substitution, which is how every call site here invokes it.
#
# This distinction is the whole point of the guard, not a detail: VERIFIED that
# all 11 mutation batteries restore patched source in a `finally` block
# (grep -c finally tests/mutate_*.py -> every file >= 1). A guard that killed
# them with SIGTERM would have TERMINATED THEM MID-MUTATION AND LEFT THE SOURCE
# PATCHED -- reproducing by design the exact incident it was written to prevent,
# while appearing in the log as a clean, handled timeout. That is worse than no
# guard, because it would be trusted.
#
# `--kill-after=20` is the backstop for a child that ignores SIGINT: it gets 20
# more seconds, then SIGKILL. Reaching SIGKILL means cleanup did NOT run, which
# is why that case is reported loudly below rather than folded into the
# ordinary failure count.
#
# BUDGETS. Suites and probes are fast (MEASURED: the console suite is well
# under a second). Batteries are slow by nature -- they re-run whole oracle
# suites once per mutant -- so they get a much larger budget. The point is not
# to be tight; it is that no value is INFINITE.
SUITE_TIMEOUT=300
BATTERY_TIMEOUT=1800

# run_guarded <seconds> <command...>
# Echoes the child's combined output, and returns the child's own exit status
# so every existing `$?` check keeps working unchanged. On timeout it appends
# a TIMEOUT marker line and returns 124.
#
# WHY A FILE AND NOT A SHELL VARIABLE. The first version recorded timeouts in a
# `timed_out` variable. MEASURED: it stayed EMPTY even on a confirmed timeout,
# because every call site invokes this function inside `$(...)`, which runs in a
# SUBSHELL -- assignments there cannot reach the parent. The end-of-run summary
# would therefore have reported "no timeouts" immediately after timing out: a
# silent under-report, which is the failure mode this whole section exists to
# stop. A file crosses the subshell boundary; a variable does not.
TIMEOUT_LOG="$(mktemp -t marfin_timeouts.XXXXXX)"
trap 'rm -f "$TIMEOUT_LOG"' EXIT

run_guarded() {
  local budget="$1"; shift
  local output status
  output=$(timeout -s INT --kill-after=20 "$budget" "$@" 2>&1)
  status=$?
  echo "$output"
  if [ $status -eq 124 ] || [ $status -eq 137 ]; then
    echo "  TIMEOUT: '$*' exceeded ${budget}s and was terminated"
    if [ $status -eq 137 ]; then
      echo "  WARNING: it ignored SIGINT and was SIGKILLed, so its cleanup did"
      echo "           NOT run. The working tree may hold PATCHED SOURCE."
      echo "           Check immediately with: git status && git diff --stat"
    fi
    echo "$* (${budget}s)" >> "$TIMEOUT_LOG"
  fi
  return $status
}
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
tests/test_webhooks.py \
tests/test_alpha_vantage.py \
tests/test_broker_tools.py \
tests/test_screenshot.py \
tests/test_phase4_harness.py \
tests/test_llm_providers.py \
tests/test_console.py"

for t in $SUITES; do
  echo
  echo ">>> $t"
  # Run ONCE and keep the output. Running twice doubled the cost and could
  # mask a nondeterministic failure by reporting a different run than it tested.
  out=$(run_guarded "$SUITE_TIMEOUT" python3 "$t")
  status=$?
  echo "$out" | grep -E "^  FAIL|^  SKIP|^  INFO"
  echo "$out" | grep "^RESULT"
  n=$(echo "$out" | sed -n 's/^RESULT: \([0-9]*\) passed.*/\1/p')
  total_pass=$((total_pass + ${n:-0}))
  # AUDIT FINDING 2026-08-21. A SKIP was printed here but changed NOTHING: the
  # run still ended "ALL GREEN". MEASURED consequence: with the Qwen3 tokenizer
  # absent, test_selector.py skipped its one rendered-cost assertion and the
  # selector battery reported 2 SURVIVORS ("family token cost understated",
  # "estimate under-predicts") -- an under-predicting token budget, which
  # authorises a prompt that then overflows the context. Supplying the real
  # tokenizer took both to 15/15 killed. So a skipped assertion is not a
  # cosmetic gap; it was the whole protection. Counted and surfaced from here on.
  s=$(echo "$out" | grep -c "^  SKIP")
  total_skip=$((total_skip + s))
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
# Printed UNCONDITIONALLY, including the zero. A line that appears only when it
# is non-zero teaches the reader that its absence means nothing.
echo "  SKIPPED: $total_skip assertions did not run"
if [ $total_skip -ne 0 ]; then
  echo "  WARNING: a skipped assertion protects nothing. This suite has already"
  echo "           hidden 2 mutation survivors behind one skip. Fetch the real"
  echo "           tokenizer (see README) and re-run before trusting a green run."
fi

# The TradingView wall is the one thing in this project whose failure mode is
# legal rather than numerical, so its adversarial probe runs on every pass rather
# than by hand. It is offline (no network) and takes milliseconds.
echo
echo ">>> TradingView display-only wall (adversarial probe)"
tvout=$(run_guarded "$SUITE_TIMEOUT" python3 tests/probe_tradingview.py)
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
mqout=$(run_guarded "$SUITE_TIMEOUT" python3 tests/probe_quotes.py)
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
csvout=$(run_guarded "$SUITE_TIMEOUT" python3 tests/probe_csv_import.py)
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
whout=$(run_guarded "$SUITE_TIMEOUT" python3 tests/probe_webhooks.py)
wh_status=$?
whout_bad=$(echo "$whout" | grep -E "\*\* ALLOWED|!! CRASHED|\*\* WRONG EXC|\*\* WRONG GUARD|\*\* DEFECT")
[ -n "$whout_bad" ] && echo "$whout_bad"
echo "$whout" | grep -E "^(attacks|structural checks):"
if [ $wh_status -ne 0 ]; then
  echo "  ERROR: a webhook attack was accepted, or refused by the wrong guard"
  fail=1
fi

# The Alpha Vantage connector probe. This is the first module in the project that
# talks to a real third-party API, and the measurement that shaped it is the
# reason this gate exists: EVERY failure that API has arrives as HTTP 200 with an
# explanatory string and no data. Bad symbol, unknown function, missing
# parameter, demo-key misuse -- four probes, four HTTP 200s, one identical body
# shape. A connector that checked the status code would treat all four as
# success. Worse, an INVALID key still returns a full real series, so a
# successful response proves nothing about authorisation either. The probe runs
# entirely from saved payloads and spends none of the 25-per-day allowance.
echo
echo ">>> Alpha Vantage connector guards (adversarial probe)"
avout=$(run_guarded "$SUITE_TIMEOUT" python3 tests/probe_alpha_vantage.py)
av_status=$?
avout_bad=$(echo "$avout" | grep -E "\*\* ALLOWED|!! CRASHED|\*\* BROKEN")
[ -n "$avout_bad" ] && echo "$avout_bad"
echo "$avout" | grep -E "^attempts="
if [ $av_status -ne 0 ]; then
  echo "  ERROR: an unusable Alpha Vantage response was accepted, or a"
  echo "         structural guarantee of the connector no longer holds"
  fail=1
fi

# The broker tool surface is where a defect stops being an analytical error and
# becomes a financial one, so its adversarial probe runs on every pass. It tries
# to reach a write through every route: a preview escalated with its own id, a
# synthetic VERIFIED live-capable adapter, immutable tables edited at runtime.
# Offline, no credential, milliseconds.
echo
echo ">>> broker tool surface (adversarial probe)"
btout=$(run_guarded "$SUITE_TIMEOUT" python3 tests/probe_broker_tools.py)
bt_status=$?
btout_bad=$(echo "$btout" | grep -E "\*\* ALLOWED|!! CRASHED|\*\* BROKEN")
[ -n "$btout_bad" ] && echo "$btout_bad"
echo "$btout" | grep -E "^  attempts:|^  structural:"
if [ $bt_status -ne 0 ]; then
  echo "  ERROR: a broker write or unauthorised read was ALLOWED, or a"
  echo "         structural guarantee of the tool surface no longer holds"
  fail=1
fi

# The SS.7.1 Level 3 visual surface is the module most likely to be quietly
# wrong: it guards a capability this runtime does not have, so nothing exercises
# it in ordinary use and nothing notices when a guard rots. Its probe has already
# earned its place twice -- it found a consent window bounded at one end only
# (an approval dated tomorrow was honoured today) and a writable class ceiling
# that widened every approval granted after it. Offline, no display, no capture.
echo
echo ">>> Level 3 visual surface (adversarial probe)"
ssout=$(run_guarded "$SUITE_TIMEOUT" python3 tests/probe_screenshot.py)
ss_status=$?
ssout_bad=$(echo "$ssout" | grep -E "^  ALLOWED|^  CRASHED|^  BROKEN")
[ -n "$ssout_bad" ] && echo "$ssout_bad"
echo "$ssout" | grep -E "^  attempts:|^  structural:"
if [ $ss_status -ne 0 ]; then
  echo "  ERROR: a forbidden capture, a forged consent, or TradingView"
  echo "         laundering was ALLOWED, or a structural guarantee is gone"
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
  sel=$(run_guarded "$BATTERY_TIMEOUT" python3 tests/mutate_selector.py)
  sel_status=$?
  echo "$sel" | grep -E "^ +(seeded|killed|survived|skipped):"
  echo "$sel" | grep -E "^ +(survived|skipped): +[1-9]" && fail=1
  [ $sel_status -ne 0 ] && fail=1

  echo
  echo ">>> RAG mutation battery"
  rag=$(run_guarded "$BATTERY_TIMEOUT" python3 tests/mutate_rag.py)
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
  mkt=$(run_guarded "$BATTERY_TIMEOUT" python3 tests/mutate_market.py)
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
  exe=$(run_guarded "$BATTERY_TIMEOUT" python3 tests/mutate_execution.py)
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
  csvm=$(run_guarded "$BATTERY_TIMEOUT" python3 tests/mutate_csv_import.py)
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
  whm=$(run_guarded "$BATTERY_TIMEOUT" python3 tests/mutate_webhooks.py)
  whm_status=$?
  echo "$whm" | grep -E "^ +(seeded|killed|equivalent|survived|skipped):"
  echo "$whm" | grep -E "^ +(survived|skipped): +[1-9]" && fail=1
  echo "$whm" | grep -E "^ +RECHECK:" && fail=1
  echo "$whm" | grep -q "source restored and oracles green: True" || {
    echo "  ERROR: webhooks.py not restored, or its oracles are not green"
    fail=1; }
  [ $whm_status -ne 0 ] && fail=1

  echo
  echo ">>> Alpha Vantage connector mutation battery"
  # Two oracles again, and the pairing was VERIFIED rather than assumed: seeding
  # the real adjusted-close defect produced 5 test failures, while disabling the
  # HTTP-200 error-key guard produced 3 probe ALLOWEDs and no test failure at
  # all. Each oracle caught what the other missed.
  #
  # This battery reported 8 survivors and 1 SKIP against a suite printing
  # "131 passed, 0 failed". Every one was a gap in the TESTS, closed without
  # changing the module and without relaxing an assertion -- and seven were the
  # same shape seen in every battery before it: a SECOND guard answered in place
  # of the one under test. A series that was a non-empty list; a coerced empty
  # price caught by the zero-price guard instead of the numeric one; a
  # case-sensitised demo check whose uppercase form was caught by the 8-64
  # character length regex; two gates that always say yes because this provider
  # is enabled and its tier does permit end-of-day. The SKIP was the worst of
  # the nine: its find-string occurred TWICE in the module, so it had silently
  # stopped testing anything while still printing a line.
  avm=$(run_guarded "$BATTERY_TIMEOUT" python3 tests/mutate_alpha_vantage.py)
  avm_status=$?
  echo "$avm" | grep -E "^ +(seeded|killed|equivalent|survived|skipped):"
  echo "$avm" | grep -E "^ +(survived|skipped): +[1-9]" && fail=1
  echo "$avm" | grep -E "^ +RECHECK:" && fail=1
  echo "$avm" | grep -q "source restored and oracles green: True" || {
    echo "  ERROR: alpha_vantage.py not restored, or its oracles are not green"
    fail=1; }
  [ $avm_status -ne 0 ] && fail=1

  echo
  echo ">>> broker tools mutation battery"
  # 86 mutations against the SS.8.4/8.5/8.6 surface, oracles test_broker_tools.py
  # AND probe_broker_tools.py together. Six survived the first run and every one
  # was a finding about the TESTS. Five were the shape this project keeps
  # meeting: a SECOND guard answering for the one under test -- an empty result
  # set that is also a partial one, and four portfolio_risk validation guards
  # standing behind a terminal refusal of the same exception type, so relaxing
  # any of them changed nothing a type-only assertion could see. Two were simply
  # untested entry-point guards in preview_order. The sixth, record()'s status
  # check, is genuinely unreachable by input because verdict_for re-checks every
  # status -- it was NOT filed as equivalent, because that equivalence rests on
  # record() having no external caller today, so its independent existence is
  # asserted structurally instead.
  btm=$(run_guarded "$BATTERY_TIMEOUT" python3 tests/mutate_broker_tools.py)
  btm_status=$?
  echo "$btm" | grep -E "^ +(seeded|killed|equivalent|survived|skipped):"
  echo "$btm" | grep -E "^ +(survived|skipped): +[1-9]" && fail=1
  echo "$btm" | grep -E "^ +RECHECK:" && fail=1
  echo "$btm" | grep -q "source restored and oracles green: True" || {
    echo "  ERROR: broker_tools.py not restored, or its oracles are not green"
    fail=1; }
  [ $btm_status -ne 0 ] && fail=1

  echo
  echo ">>> Level 3 visual surface mutation battery"
  # 89 mutations against SS.7.1 Level 3, oracles test_screenshot.py AND
  # probe_screenshot.py together. Five survived the first run. FOUR were findings
  # about the tests, and all four were one shape: a case that could not
  # distinguish the guard under test from something else answering for it -- a
  # notification title also caught by a neighbouring pattern in the same tuple,
  # an empty window title also caught by the mismatch guard raising the same
  # class, a hyphen rule shadowed by the un-normalised second clause, and a
  # provider expression indistinguishable because every test passed a requested
  # title identical to the approved one.
  #
  # The FIFTH was a finding about the BATTERY: "content screened before consent"
  # swapped two statements but not the raise, so it was a no-op I had written and
  # would have quietly counted as a survivor forever. It is recorded in the file
  # rather than silently corrected, because "the tests are too weak" is only one
  # of the answers a survivor can have.
  ssm=$(run_guarded "$BATTERY_TIMEOUT" python3 tests/mutate_screenshot.py)
  ssm_status=$?
  echo "$ssm" | grep -E "^ +(seeded|killed|equivalent|survived|skipped):"
  echo "$ssm" | grep -E "^ +(survived|skipped): +[1-9]" && fail=1
  echo "$ssm" | grep -E "^ +RECHECK:" && fail=1
  echo "$ssm" | grep -q "source restored and oracles green: True" || {
    echo "  ERROR: screenshot.py not restored, or its oracles are not green"
    fail=1; }
  [ $ssm_status -ne 0 ] && fail=1

  echo
  echo ">>> Phase 4 harness mutation battery"
  # 89 mutations against scripts/phase4_lib.py and scripts/run_phase4.py, the
  # harness the user runs on their OWN i5-12400 under Route A. It gets one
  # evening of their time; a mis-grading harness turns that evening into a file
  # that looks like measurement and is not, so it is mutation-tested before it
  # is ever handed over.
  #
  # Ten survived the first round and the split is the point: THREE were wrong
  # mutations I had written (an alternation order made irrelevant by \b, a
  # .lower() that is a no-op on Persian, an inert assignment), ONE was a real
  # code defect (_DECIMAL_SEPARATORS was declared and never read -- a table
  # documenting a rule it did not enforce), and six were genuine test gaps.
  # A survivor is not automatically a weak test.
  #
  # One survivor deserves its own note: the threshold-direction check read the
  # direction out of the table under test and then probed accordingly, so
  # flipping an entry merely selected the matching probe. A flipped fabrication
  # ceiling survived a 322-assertion suite. The table is now compared against
  # an independently written copy.
  #
  # NOTE the grep below says "oracle", singular. This battery has one oracle;
  # the others have two. Grepping the plural here would never match and the
  # source-integrity check would fail every run.
  p4m=$(run_guarded "$BATTERY_TIMEOUT" python3 tests/mutate_phase4.py)
  p4m_status=$?
  echo "$p4m" | grep -E "^ +(seeded|killed|equivalent|survived|skipped):"
  echo "$p4m" | grep -E "^ +(survived|skipped): +[1-9]" && fail=1
  echo "$p4m" | grep -E "^ +RECHECK:" && fail=1
  echo "$p4m" | grep -q "source restored and oracle green: True" || {
    echo "  ERROR: the Phase 4 harness is not restored, or its oracle is not green"
    fail=1; }
  [ $p4m_status -ne 0 ] && fail=1

  echo
  echo "--- llm provider layer (providers.py, clients.py, panel.py) ---------"
  # 31 mutants across the three modules that added API access to the local
  # model. First run: 21 killed, 10 SURVIVED -- against a suite that printed
  # "195 passed, 0 failed". Every one of the ten was a gap in the TESTS or in a
  # FIXTURE; none required changing the modules.
  #
  # Two survivors are worth remembering. One rewrote the decode row as
  # "3.62-4.38 tok/s PASS" -- turning the user's MEASURED hardware failure into
  # a pass on the panel they read most often. It lived because the assertion
  # searched the whole panel for "FAIL" and for "3.62" separately, and both were
  # still somewhere on screen. Metric rows are now asserted line by line.
  # The other shortened the box border by one column: the exact defect that had
  # already shipped once. It lived because the layout test only asked whether a
  # line was TOO LONG, so a border one column SHORT was invisible -- the test
  # was blind in precisely the direction the real bug went. A width histogram
  # now requires every frame line to be equal, and 5 injected off-by-one faults
  # (top, bottom, separator, content row, and the long direction) were all
  # caught before the assertion was trusted.
  #
  # NOTE this battery prints "oracles", plural: it has three (the assertion
  # suite, panel.py --check exit codes, and an --ascii --no-colour render).
  # Grepping the singular here would never match and would fail every run.
  llmm=$(run_guarded "$BATTERY_TIMEOUT" python3 tests/mutate_llm_providers.py)
  llmm_status=$?
  echo "$llmm" | grep -E "^ +(seeded|killed|equivalent|survived|skipped):"
  echo "$llmm" | grep -E "^ +(survived|skipped): +[1-9]" && fail=1
  echo "$llmm" | grep -E "^ +RECHECK:" && fail=1
  echo "$llmm" | grep -E "^ +INTEGRITY:" && fail=1
  echo "$llmm" | grep -q "source restored and oracles green: True" || {
    echo "  ERROR: the llm provider source is not restored, or an oracle is red"
    fail=1; }
  [ $llmm_status -ne 0 ] && fail=1
fi

echo
# A TIMEOUT MUST NEVER BE ABLE TO REPORT "ALL GREEN". A child killed at its
# budget produced no RESULT line, so its assertions were never counted and its
# grep-based checks matched nothing -- which looks IDENTICAL to a clean pass
# from the driver's point of view. Read unconditionally and printed even when
# the count is zero, for the same reason as the SKIPPED line: a line that
# appears only when non-zero teaches the reader that its absence means nothing.
n_timeout=0
[ -s "$TIMEOUT_LOG" ] && n_timeout=$(wc -l < "$TIMEOUT_LOG")
echo "  TIMED OUT: $n_timeout run(s) exceeded their time budget"
if [ "$n_timeout" -ne 0 ]; then
  sed 's/^/           - /' "$TIMEOUT_LOG"
  echo "  A timed-out run proves NOTHING: it was cut off before reporting, so"
  echo "  its assertions were never counted. Treated as a FAILURE, not a pass."
  fail=1
fi

echo "=============================================================="
[ $fail -eq 0 ] && echo "ALL GREEN" || echo "FAILURES PRESENT"
echo "=============================================================="
exit $fail
