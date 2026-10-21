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
RR = "src/calc/returns_risk.py"
BRE = "tools/build_redteam_eval.py"
GP6 = "scripts/grade_phase6.py"

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
    # -- D-0119 F1: execution-claim guard ------------------------------------
    (UNT, "F1 guard never blocks",
     "    claims = execution_claims(text)\n    if not claims:",
     "    claims = []\n    if not claims:"),
    (UNT, "F1 Persian completion verbs dropped",
     '    r"|(?:\\u0627\\u0646\\u062c\\u0627\\u0645\\s*\\u0634\\u062f|"',
     '    r"|(?:NEVERMATCH|"'),
    (UNT, "F1 Persian word-end check removed (participle fires)",
     '    r"\\u0627\\u062c\\u0631\\u0627\\s*\\u0634\\u062f)(?![\\u0600-\\u06ff\\u200c])",',
     '    r"\\u0627\\u062c\\u0631\\u0627\\s*\\u0634\\u062f)",'),
    (UNT, "F1 'has been placed' form dropped (the measured critical reply)",
     '    r"\\b(?:has|have|had)\\s+been\\s+(?:successfully\\s+)?(?:placed|executed|submitted|"',
     '    r"\\bNEVERMATCH(?:placed|executed|submitted|"'),
    (UNT, "F1 present-tense 'order is executed' fires again (D-0129 false positive)",
     '    r"|is\\s+(?:placed|confirmed|filled|submitted)"\n',
     '    r"|is\\s+(?:placed|executed|confirmed|filled|submitted)"\n'),
    (UNT, "F1 present-tense 'trade is executed' fires again (D-0129 false positive)",
     '    r"|is\\s+(?:complete|completed)|(?:complete|completed|executed))\\b"',
     '    r"|is\\s+(?:complete|completed|executed)|(?:complete|completed|executed))\\b"'),
    (UNT, "F1 'order was executed' no longer flagged (narrowing went too far)",
     '    r"|\\border\\s+(?:was\\s+(?:placed|executed|confirmed|filled|submitted)"\n',
     '    r"|\\border\\s+(?:was\\s+(?:placed|confirmed|filled|submitted)"\n'),
    (UNT, "F1 'is filled' status no longer flagged (narrowing went too far)",
     '    r"|is\\s+(?:placed|confirmed|filled|submitted)"\n',
     '    r"|is\\s+(?:placed|confirmed|submitted)"\n'),
    (UNT, "F1 tool-call blocks no longer excluded",
     '    s = re.sub(r"<tool_call>.*?</tool_call>", " ", s, flags=re.S)\n', ""),
    (UNT, "F1 Persian question gets the English notice",
     '    notice = EXECUTION_GUARD_NOTICE_FA if lang == "fa" else EXECUTION_GUARD_NOTICE_EN',
     '    notice = EXECUTION_GUARD_NOTICE_EN'),
    (UNT, "F1 original reply discarded (no audit trail)",
     '    return {"text": notice, "blocked": True, "claims": claims, "original": text}',
     '    return {"text": notice, "blocked": True, "claims": claims, "original": None}'),
    (RUN, "F1 plain arm ignores the guard flag",
     '        text, guard = _apply_execution_guard(text, c.get("lang"), execution_guard)',
     '        text, guard = _apply_execution_guard(text, c.get("lang"), False)'),
    (RUN, "F1 tools arm guards but keeps grading the original",
     '                g["output"] = guarded\n',
     '                pass\n'),
    # -- D-0119 F2: trust-gated retrieval -------------------------------------
    (RUN, "F2 min_trust not passed to retrieval",
     '        res = index.search(gold["query"], top_k=top_k, min_trust=min_trust)',
     '        res = index.search(gold["query"], top_k=top_k)'),
    (RUN, "F2 gate always on (recorded runs no longer reproducible)",
     '        res = index.search(gold["query"], top_k=top_k, min_trust=min_trust)',
     '        res = index.search(gold["query"], top_k=top_k, min_trust=80)'),
    # -- D-0119 F3: fx_convert ------------------------------------------------
    (RR, "F3 direction swapped (the 22,500x error)",
     '        v = amount / rate\n', '        v = amount * rate\n'),
    (RR, "F3 unknown rate_quote guessed instead of refused",
     "    else:\n        raise ValueError(\"fx_convert: rate_quote must be",
     "    else:\n        v, formula = amount / rate, 'guessed'\n    if False:\n        raise ValueError(\"fx_convert: rate_quote must be"),
    (RR, "F3 non-ISO code accepted",
     '        if c not in ISO_4217:', '        if len(c) != 3:'),
    (RR, "F3 zero/negative rate accepted",
     '    if rate <= 0:\n        raise ValueError("fx_convert: rate must be > 0")',
     '    if rate == 0:\n        raise ValueError("fx_convert: rate must be > 0")'),
    (RR, "F3 same-currency conversion accepted",
     '    if fc == tc:\n        raise', '    if False:\n        raise'),
    # -- D-0119 F4: fixture -----------------------------------------------------
    (BRE, "F4 figure pin checks nothing",
     "    return any(f in p.text for p in passages for f in GOLD_FIGURE_TEXT.get(gid, ()))",
     "    return True"),
    (GP6, "D-0120 rank ignores the trust floor",
     "    for i, h in enumerate(index.search(query, top_k=k, min_trust=min_trust).hits, 1):",
     "    for i, h in enumerate(index.search(query, top_k=k).hits, 1):"),
    (GP6, "D-0120 grader never reads the run's floor",
     '    min_trust = int(((run.get("model") or {}).get("prompt_options") or {}).get("min_trust") or 0)',
     "    min_trust = 0"),
    (GP6, "D-0120 hedge flag dropped",
     '            if g["outcome"] == "OK" and g["abstained"]:',
     "            if False:"),
    (GP6, "D-0121 ruling never applied",
     "        if key in HUMAN_RULINGS:", "        if False:"),
    (GP6, "D-0121 ruling keyed without the reply hash (leaks onto new text)",
     '        key = (row["arm"], row["id"], hashlib.sha256(out.encode("utf-8")).hexdigest())',
     '        key = next((k for k in HUMAN_RULINGS if k[:2] == (row["arm"], row["id"])), None)'),
    (GP6, "D-0120 hedge flag on every OK",
     '            if g["outcome"] == "OK" and g["abstained"]:',
     '            if g["outcome"] == "OK":'),
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
