#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mutation battery for the tool selector.

Written in Python rather than bash because the selector's source contains
regexes, quotes and Persian text that shell quoting mangles -- a mangled
pattern reports SKIP, which is indistinguishable at a glance from a real
result and would quietly overstate coverage.

A mutant that SURVIVES means the test suite does not actually check that
behaviour. For a selector, that matters more than usual: the failure it guards
against (dropping the tool a query needed) is silent.

Run: python3 tests/mutate_selector.py
"""

import io
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "src", "tools", "selector.py")
TESTS = os.path.join(HERE, "test_selector.py")

# (description, find, replace)
MUTATIONS = [
    ("core family guarantee removed",
     'CORE_FAMILIES = ("returns_risk",)', 'CORE_FAMILIES = ()'),
    ("weak signals ignored (recall narrowed)",
     "hit = [f for f in FAMILIES if scores[f] > 0]",
     "hit = [f for f in FAMILIES if scores[f] > 1]"),
    ("word-boundary matching disabled",
     'if _WORDY.match(w):', 'if False:'),
    # D-0088: these anchors were '"returns_risk": 2079,' and
    # 'MEASURED_ALL_TOKENS = 8920'. Both constants were corrected to the
    # SHIPPED model's measured values, so the old anchors no longer match any
    # line -- a mutant that cannot be applied is a mutant that proves nothing,
    # and this battery would have reported it as "killed".
    ("family token cost understated",
     '"returns_risk": 2219,', '"returns_risk": 1000,'),
    ("all-tools baseline understated",
     "MEASURED_ALL_TOKENS = 9122", "MEASURED_ALL_TOKENS = 3000"),
    # NEW (D-0088): reverting to the pre-correction constants must be fatal.
    # This is the mutant that reproduces the actual historical defect -- an
    # under-predicting budget calibrated on Qwen3-4B-Instruct-2507.
    ("budget reverted to the wrong model's calibration",
     "MEASURED_ALL_TOKENS = 9122", "MEASURED_ALL_TOKENS = 8920"),
    ("unclassified tools silently dropped",
     "    for n in tool_names():\n        if n not in TOOL_FAMILY and n not in chosen:\n            chosen.append(n)",
     "    pass"),
    ("jargon-free valuation vocabulary removed",
     '"worth", "expensive", "cheap", "overvalued", "undervalued",', ''),
    ("Persian valuation vocabulary removed",
     '"\u06af\u0631\u0627\u0646", "\u0627\u0631\u0632\u0627\u0646", "\u0627\u0631\u0632\u0634 \u0634\u0631\u06a9\u062a", "\u0633\u0648\u062f \u0634\u0631\u06a9\u062a", "\u0628\u06cc\u0634\\u200c\u0627\u0631\u0632\u0634",', ''),
    ("fallback confidence mislabelled as high",
     'confidence = "low"          # nothing matched; CORE fallback in use',
     'confidence = "high"'),
    ("fallback flag never set",
     '"fallback_used": total_signal == 0,', '"fallback_used": False,'),
    ("estimate under-predicts (half the real cost)",
     'est = sum(MEASURED_FAMILY_TOKENS.get(f, 0) for f in families)',
     'est = sum(MEASURED_FAMILY_TOKENS.get(f, 0) for f in families) // 2'),
    ("truncation drops the mandatory core family",
     "        for core in CORE_FAMILIES:\n            if core not in keep:\n                keep[-1] = core",
     "        pass"),
    ("ZWNJ normalisation removed (Persian compounds break)",
     'return (text or "").lower().replace("\\u200c", " ")',
     'return (text or "").lower()'),
    ("technicals vocabulary gutted",
     '"rsi", "macd", "moving average", "sma", "ema", "wma", "bollinger",', ''),
    ("schemas_for diverges from select_tools",
     'return [s for s in tool_schemas() if s["function"]["name"] in keep]',
     'return [s for s in tool_schemas()][:5]'),

    # ---- R18: keywords derived from the registry (D-0075) -------------------
    # These five are the KILLABLE mutants of the derivation added when R18 was
    # closed. They live here, not in a /tmp scratch script, because a guard that
    # only exists in /tmp is erased by a sandbox reset -- and then the fix would
    # be protected by nothing while the log still said "5 killed".
    ("R18 fragment floor raised 4 -> 99 (no fragment ever counts)",
     "_NAME_PART_MIN = 4", "_NAME_PART_MIN = 99"),
    ("R18 fragment floor lowered 4 -> 1 (ev, pe, pb leak in)",
     "_NAME_PART_MIN = 4", "_NAME_PART_MIN = 1"),
    ("R18 fragment loop disabled",
     "            if len(part) >= _NAME_PART_MIN:",
     "            if False:"),
    ("R18 derivation returns nothing",
     "    return derived",
     "    return {f: set() for f in FAMILIES}"),
    ("R18 derived names never merged into _NORM_KEYWORDS",
     "| {_normalize(w) for w in NAME_KEYWORDS.get(fam, ())",
     "| {_normalize(w) for w in ()"),
]

# TWO further mutants were seeded against the R18 derivation and SURVIVED. They
# are NOT listed above, because seeding a mutant that cannot be killed would
# force this battery to report a survivor forever, and the honest reading of
# that survivor is "no behaviour to observe", not "assertions too weak".
#
#   (a) drop the whole-name signal  -- derived[fam].add(tool.replace("_", " "))
#   (b) misroute every derived whole name to returns_risk
#
# Both are EQUIVALENT MUTANTS, PROVEN rather than assumed. All 57 multi-word
# tool names contain at least one underscore fragment of 4+ chars, so the
# fragment signal alone already reaches every family the whole-name signal
# reaches: the two paths are redundant by construction. Each mutant was re-run
# against 569 exhaustive probes -- all 84 tool names, every underscore fragment
# of every name, and 400 name pairs -- and each produced 0 family-set
# differences from the unmutated module.
#
# An equivalent mutant is unkillable by definition. Recording it as a permanent
# SURVIVED line would be a standing false alarm; recording it as a SKIP would
# overstate coverage (D-0036: a skip protects nothing). It is recorded here
# instead, with the evidence, which is the only reading that stays true.
#
# Battery result when the two were included: 7 seeded, 5 killed, 2 equivalent,
# 0 genuine survivors.


def run_tests():
    """True if the suite passes."""
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    p = subprocess.run([sys.executable, TESTS], cwd=ROOT, env=env,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return p.returncode == 0


def main():
    original = io.open(SRC, encoding="utf-8").read()
    backup = os.path.join(tempfile.gettempdir(), "selector_orig.py")
    shutil.copy(SRC, backup)

    # Sanity: the suite must pass BEFORE any mutation, otherwise every "killed"
    # result is meaningless.
    if not run_tests():
        print("ABORT: suite fails on unmutated source")
        return 1

    killed = survived = skipped = 0
    print("=" * 74)
    print("SELECTOR MUTATION BATTERY")
    print("=" * 74)
    try:
        for desc, find, repl in MUTATIONS:
            if find not in original:
                print("  SKIP      %s  (pattern not found)" % desc)
                skipped += 1
                continue
            io.open(SRC, "w", encoding="utf-8").write(
                original.replace(find, repl, 1))
            if run_tests():
                print("  SURVIVED  %s" % desc)
                survived += 1
            else:
                print("  killed    %s" % desc)
                killed += 1
            io.open(SRC, "w", encoding="utf-8").write(original)
    finally:
        io.open(SRC, "w", encoding="utf-8").write(original)

    intact = io.open(SRC, encoding="utf-8").read() == original
    print("-" * 74)
    print("  seeded:   %d" % len(MUTATIONS))
    print("  killed:   %d" % killed)
    print("  survived: %d" % survived)
    print("  skipped:  %d" % skipped)
    print("  source restored intact: %s" % intact)
    print("=" * 74)
    return 0 if (survived == 0 and skipped == 0 and intact) else 1


if __name__ == "__main__":
    sys.exit(main())
