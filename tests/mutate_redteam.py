# -*- coding: utf-8 -*-
"""
Mutation battery for the Phase 6 safety layer (D-0116).

Each mutation removes or weakens ONE guard that tests/test_redteam.py claims to
pin. A survivor means a red-team claim is not actually tested.
Runs against a COMMITTED tree only (D-0115 incident): restore is by rewrite
from an in-memory original, and the tree is checked clean afterwards.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ORACLE = os.path.join(HERE, "test_redteam.py")

UNT = "src/safety/untrusted.py"
REG = "src/tools/registry.py"
RUN = "scripts/run_phase4.py"
LCX = "scripts/run_longctx.py"

MUTATIONS = [
    (UNT, "control tokens no longer defanged",
     "    return _CONTROL_RE.sub(DEFANG, s)", "    return s"),
    (UNT, "generic <|...|> shape dropped (future tokens pass)",
     '    r"<(?=\\|[A-Za-z0-9_]{1,40}\\|>)"\n    r"|<',
     '    r"<(?=\\|(?:im_end|im_start)\\|>)"\n    r"|<'),
    (UNT, "tag-shaped tokens dropped (</tool_response> passes)",
     '    r"|<(?=/?(?:tool_call|tool_response|think)>)",',
     '    r"|<(?=NEVER)",'),
    (UNT, "tag tokens matched case-sensitively",
     "    re.IGNORECASE)\n\n\ndef neutralize_control_tokens",
     "    0)\n\n\ndef neutralize_control_tokens"),
    (UNT, "defang deletes the token instead (attempt invisible)",
     'DEFANG = "\\u2039"', 'DEFANG = ""'),
    (UNT, "English instruction patterns never consulted",
     "_PATTERNS = ([(n, re.compile(p, re.IGNORECASE)) for n, p in _EN]",
     "_PATTERNS = ([(n, re.compile(p, re.IGNORECASE)) for n, p in []]"),
    (UNT, "Persian instruction patterns never consulted",
     "             + [(n, re.compile(p)) for n, p in _FA])",
     "             + [(n, re.compile(p)) for n, p in []])"),
    (UNT, "override pattern loses its object (fires on any 'ignored')",
     r'''    ("override_instructions", r"\b(?:ignore|disregard|forget|override)\b[^.\n]{0,40}"
                              r"\b(?:previous|prior|above|earlier|all|system|your)\b[^.\n]{0,20}"
                              r"\b(?:instructions?|prompts?|rules?|polic(?:y|ies)|guidelines?)\b"),''',
     r'''    ("override_instructions", r"\b(?:ignore|ignored|disregard|forget|override)\b"),'''),
    (UNT, "trade_command fires on the bare word 'orders'",
     r'''    ("trade_command", r"\b(?:place|submit|execute|send)\s+(?:an?\s+|the\s+)?"''',
     r'''    ("trade_command", r"(?:orders?\b)|\b(?:place|submit|execute|send)\s+(?:an?\s+|the\s+)?"'''),
    (UNT, "Persian imperative 'بخر' matches inside words",
     r'''     r"(?:^|\s)(?:\u0628\u062e\u0631|\u0628\u0641\u0631\u0648\u0634)(?=[\s.!\u061f]|$)"),''',
     r'''     r"(?:\u0628\u062e\u0631|\u0628\u0641\u0631\u0648\u0634)"),'''),
    (UNT, "keys are not scanned",
     '            yield here + "#key", str(k)\n', ""),
    (UNT, "nested lists not walked",
     '            for x in _walk_strings(v, "%s[%d]" % (path, i)):\n                yield x',
     '            pass'),
    (UNT, "detected injection does not downgrade trust",
     "    if found:\n        trust",
     "    if False:\n        trust"),
    (UNT, "untrusted data allowed for order_preview",
     '        trust = "UNTRUSTED"\n        safe = ["analysis", "calculation"]',
     '        trust = "UNTRUSTED"\n        safe = ["analysis", "calculation", "order_preview"]'),
    (UNT, "own calculator allowed live_execution (assert removed too)",
     '        safe = ["analysis", "calculation", "order_preview"]\n    else:',
     '        safe = ["analysis", "calculation", "order_preview", "live_execution"]\n    else:'),
    (UNT, "the live_execution assert removed (and envelope data not neutralised)",
     '        "data": _neutralize_tree(data),', '        "data": data,'),
    (UNT, "safe_for accepts unknown uses",
     "    if use not in USES:\n        return False", "    if use not in USES:\n        return True"),
    (UNT, "unattributed results accepted",
     "    if not isinstance(source, str) or not source.strip():\n        raise",
     "    if False:\n        raise"),
    (REG, "registry accepts non-finite numbers again (the 58-leak)",
     "        if not math.isfinite(f):\n            raise ValueError",
     "        if False:\n            raise ValueError"),
    (REG, "non-finite RESULTS returned as ok",
     "    if any(isinstance(v, float) and not math.isfinite(v) for v in vals):",
     "    if False:"),
    (RUN, "RAG passages no longer defanged in the prompt",
     '        ev.append(_defang("[%d] (%s) %s%s"',
     '        ev.append(("[%d] (%s) %s%s"'),
    (RUN, "tool responses no longer defanged",
     "    return [_defang(x) for x in out]", "    return out"),
    (LCX, "long-context decoy never inserted",
     "    if decoy_first:\n        blocks.insert(", "    if False:\n        blocks.insert("),
    (LCX, "decoy placed next to the needle's end (recency picks right)",
     "        blocks.insert(0 if depth >= 0.5 else len(blocks), DECOY)",
     "        blocks.insert(len(blocks) if depth >= 0.5 else 0, DECOY)"),
    (LCX, "needle depth ignored (always at the top)",
     "    at = int(round(depth * n_filler))", "    at = 0"),
    (LCX, "period confusion graded as a plain miss",
     '        outcome = "PERIOD_CONFUSION"', '        outcome = "MISS"'),
    (LCX, "stating both values counts as OK",
     '    if found and not decoy:\n        outcome = "OK"',
     '    if found:\n        outcome = "OK"'),
    (LCX, "scale words ignored (211.915 billion misses)",
     "    found = L.value_matches(EXPECTED, answer, TOL, scaled=True)",
     "    found = L.value_matches(EXPECTED, answer, TOL, scaled=False)"),
]


def oracle():
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    p = subprocess.run([sys.executable, ORACLE], cwd=ROOT, env=env,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=300)
    return p.returncode == 0


def main():
    if not oracle():
        print("ABORT: oracle fails before mutation")
        return 1
    killed = survived = skipped = 0
    surv, skips = [], []
    for i, (f, desc, find, repl) in enumerate(MUTATIONS, 1):
        path = os.path.join(ROOT, f)
        orig = open(path, encoding="utf-8").read()
        if orig.count(find) != 1:
            skipped += 1
            skips.append("%s: %s (count=%d)" % (f, desc, orig.count(find)))
            print("  %2d. SKIP     %s" % (i, desc))
            continue
        try:
            open(path, "w", encoding="utf-8").write(orig.replace(find, repl, 1))
            ok = oracle()
        finally:
            open(path, "w", encoding="utf-8").write(orig)
        if ok:
            survived += 1
            surv.append("%s: %s" % (f, desc))
            print("  %2d. SURVIVED %s" % (i, desc))
        else:
            killed += 1
            print("  %2d. killed   %s" % (i, desc))
    intact = oracle()
    print("=" * 70)
    print("  seeded %d  killed %d  survived %d  skipped %d  restored+green %s"
          % (len(MUTATIONS), killed, survived, skipped, intact))
    for s in surv:
        print("  SURVIVOR:", s)
    for s in skips:
        print("  SKIPPED: ", s)
    return 0 if (survived == 0 and skipped == 0 and intact) else 1


if __name__ == "__main__":
    sys.exit(main())
