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
    ("family token cost understated",
     '"returns_risk": 2079,', '"returns_risk": 1000,'),
    ("all-tools baseline understated",
     "MEASURED_ALL_TOKENS = 8920", "MEASURED_ALL_TOKENS = 3000"),
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
]


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
