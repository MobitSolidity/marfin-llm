#!/usr/bin/env python3
"""
Mutation battery for scripts/attribute_failures.py, tools/impact.py and the
D-0109 change to tools/graph_project.py.

ORACLE: test_attribution.py alone. It carries both directions: every rule is
asserted on its positive case AND on a near miss, so a mutant that makes a
rule fire everywhere dies as surely as one that makes it fire nowhere.

The mutants that matter most are the ones that would make a failure look like
somebody else's fault. Attribution is only useful if MODEL is never quietly
relabelled GRADER: that would make the fine-tuning question look settled when
it is not.

Same protocol as the other batteries: a mutant whose anchor is absent or not
unique is SKIPPED and counted, never silently dropped; source is restored in
`finally` and verified after.

Stdlib only.
"""

import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

ORACLES = ("test_attribution.py",)
ORACLE_TIMEOUT = 300

ATTR = "scripts/attribute_failures.py"
IMPACT = "tools/impact.py"
GRAPH = "tools/graph_project.py"

EQUIVALENT = {
    # MEASURED 2026-10-04: verify_claim never returns UNSUPPORTED for a
    # numeric claim against a passage that DECLARES a scale -- 213 claims
    # built from every number in all 15 scaled passages of the combined
    # corpus, bare, with "million", and year-masked: 0 UNSUPPORTED. The
    # units_note guard is therefore redundant with verify_claim's own logic
    # today; it is kept so the FIXTURE rule stays correct if verify_claim
    # ever grows a new UNSUPPORTED path for scaled evidence.
    "scripts/attribute_failures.py: rag: FIXTURE rule no longer requires a "
    "missing units_note": "redundant with verify_claim (213/0 measured)",
}

# (file, description, find, replace)
MUTATIONS = [
    # -- banned-phrase attribution -------------------------------------------
    (ATTR, "substring-only banned hit is blamed on the model",
     '        return ("GRADER", EXTRACTED,\n'
     '                "banned phrase matched only inside a longer word "',
     '        return ("MODEL", EXTRACTED,\n'
     '                "banned phrase matched only inside a longer word "'),
    (ATTR, "word-boundary match degrades to a bare substring",
     'return list(re.finditer(r"(?<!\\w)%s(?!\\w)" % re.escape(phrase)',
     'return list(re.finditer(r"%s" % re.escape(phrase)'),
    (ATTR, "'whether' complementiser no longer required",
     '            if not re.search(r"\\b(whether|if)\\b", head[cut + 1:]):\n'
     '                return False',
     '            if False:\n'
     '                return False'),
    (ATTR, "the clause is no longer cut at 'but'",
     '            cut = max(head.rfind(" but "), head.rfind(";"), head.rfind(" however"))',
     '            cut = -1'),
    (ATTR, "the embedded-refusal rule ignores is_abstention",
     '    def _embedded(s):\n        if not L.is_abstention(s):\n            return False',
     '    def _embedded(s):\n        if False:\n            return False'),
    (ATTR, "an asserted banned phrase is excused as GRADER",
     '    return ("MODEL", INFERRED,\n'
     '            "banned phrase asserted in the model\'s own sentence")',
     '    return ("GRADER", INFERRED,\n'
     '            "banned phrase asserted in the model\'s own sentence")'),
    (ATTR, "one genuine assertion no longer outweighs a grader artefact",
     '                cls, conf, rule = model[0] if model else causes[0]',
     '                cls, conf, rule = causes[0]'),

    # -- vocabulary gap ------------------------------------------------------
    (ATTR, "the observed refusal phrase is forgotten",
     '    "it is impossible to determine",   # plain/EN-RISK-002, 2026-09-27',
     '    "zzz never matches zzz",'),
    (ATTR, "a non-refusal on a must-refuse case is excused",
     '                    out.append(_row(arm, cid, "MODEL", EXTRACTED,\n'
     '                                    "should abstain; reply is not a refusal",',
     '                    out.append(_row(arm, cid, "GRADER", EXTRACTED,\n'
     '                                    "should abstain; reply is not a refusal",'),
    (ATTR, "fabrication is always excused by the vocabulary gap",
     '            if cand and not r.get("banned_hits"):',
     '            if True:'),
    (ATTR, "the judgement case is no longer flagged for a human",
     '                needs = any(p in low for p in ("illogical", "غیرمنطقی"))',
     '                needs = False'),

    # -- calculation ---------------------------------------------------------
    (ATTR, "a wrong value with no tool result is blamed on the harness",
     '                    out.append(_row(arm, cid, "MODEL", EXTRACTED,\n'
     '                                    "wrong or missing value, no correct tool "',
     '                    out.append(_row(arm, cid, "HARNESS", EXTRACTED,\n'
     '                                    "wrong or missing value, no correct tool "'),
    (ATTR, "HARNESS no longer requires a correct executed tool",
     '                if r.get("tool_value_ok") and exe:',
     '                if exe or True:'),
    (ATTR, "the recorded (pre-D-0108) value_ok is trusted over the current grader",
     '    return L.value_matches(case["expected_value"], row.get("output") or "",\n'
     '                           case.get("tolerance"))',
     '    return row.get("value_ok")'),
    (ATTR, "non-discriminating passes are no longer detected",
     '                if any(abs(x - exp) <= 1e-9 * max(1.0, abs(exp)) for x in ins):',
     '                if False:'),

    # -- language ------------------------------------------------------------
    (ATTR, "rag: wrong-script replies hidden behind outcome=OK again",
     '        if r.get("persian_script") is False:\n'
     '            out.append(_row("rag", cid, "MODEL", EXTRACTED,',
     '        if False:\n'
     '            out.append(_row("rag", cid, "MODEL", EXTRACTED,'),

    # -- rag claims ----------------------------------------------------------
    (ATTR, "rag: retrieval miss on a claim blamed on the model",
     '        return ("RETRIEVAL", EXTRACTED, "no gold passage among those shown",',
     '        return ("MODEL", EXTRACTED, "no gold passage among those shown",'),
    (ATTR, "rag: FIXTURE rule no longer requires a missing units_note",
     '        if v.status == "UNSUPPORTED" and not p.units_note and nums and all(',
     '        if v.status == "UNSUPPORTED" and nums and all('),
    (ATTR, "rag: unit-restatement rule no longer checks the unit is named",
     '            if said_unit:',
     '            if True:'),
    (ATTR, "rag: a claim supported by any passage is attributed anyway",
     '            if "SUPPORTED" in stats:\n                continue',
     '            if False:\n                continue'),

    # -- thresholds ----------------------------------------------------------
    (ATTR, "hardware thresholds attributed to the cases instead",
     '            if name in HARDWARE_THRESHOLDS:',
     '            if False:'),
    (ATTR, "fine-tuning deemed able to address hardware",
     '                 "MODEL" in causes and "HARDWARE" not in causes)]))',
     '                 bool(causes))]))'),
    (ATTR, "counterfactual removes MODEL failures instead of keeping them",
     '            model = [r for r in miss if r["cause"] == "MODEL"]',
     '            model = [r for r in miss if r["cause"] != "MODEL"]'),

    # -- human rulings (D-0111) ---------------------------------------------
    (ATTR, "a ruling no longer requires the exact reply (hash ignored)",
     '        key = (r["arm"], r["id"], reply_sha256(replies.get((r["arm"], r["id"]))))\n'
     '        if key in rulings:',
     '        key = (r["arm"], r["id"], reply_sha256(replies.get((r["arm"], r["id"]))))\n'
     '        if any(k[:2] == key[:2] for k in rulings):\n'
     '            key = [k for k in rulings if k[:2] == key[:2]][0]'),
    (ATTR, "rulings are never applied",
     '    rulings_applied = apply_rulings(rows, run)',
     '    rulings_applied = []'),
    (ATTR, "a ruled case is still reported as needing a human",
     '            r["rule"], r["needs_human"] = why, False',
     '            r["rule"], r["needs_human"] = why, True'),
    (ATTR, "the ruling flips the case to MODEL instead of the user's cause",
     '            r["cause"], r["confidence"] = cause, "HUMAN"',
     '            r["cause"], r["confidence"] = "MODEL", "HUMAN"'),

    # -- graph_project (D-0109) ----------------------------------------------
    (GRAPH, "submodule imports dropped again (the D-0109 gap)",
     '                    if sub in ours_mods and sub != mod:',
     '                    if False:'),

    # -- impact --------------------------------------------------------------
    (IMPACT, "batteries no longer report the files they PATCH",
     '            elif c in targets:',
     '            elif False:'),
    (IMPACT, "import closure stops after one hop",
     '            if nxt not in seen:\n                seen.add(nxt)\n                stack.append(nxt)',
     '            if nxt not in seen:\n                seen.add(nxt)'),
    (IMPACT, "literal-name reach removed (data files invisible)",
     '        if _mentions(f, base, root):',
     '        if False:'),
    (IMPACT, "name match degrades to a bare substring (over-reach)",
     'return re.search(r"(?<![\\w.])%s(?![\\w])" % re.escape(basename), txt) is not None',
     'return basename.split(".")[0][:3] in txt'),
    (IMPACT, "the shell battery's targets are no longer read",
     '        for loop in re.finditer(r"for m in ([\\w ]+); do", txt):',
     '        for loop in re.finditer(r"NEVER MATCHES", txt):'),
    (IMPACT, "the recorded skip baseline is lost",
     '    "tests/mutate_phase4.py": 9,      # D-0100, D-0108',
     '    "tests/mutate_phase4.py": None,'),
    (IMPACT, "cross-check reports nothing (a gap hides)",
     '            "only_graphify": sorted(theirs - ours),',
     '            "only_graphify": [],'),
]


def run_oracle(name):
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        proc = subprocess.run(
            [sys.executable, os.path.join(HERE, name)], cwd=ROOT, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=ORACLE_TIMEOUT)
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT"
    return proc.returncode == 0, proc.stdout.decode("utf-8", "replace")


def run_tests():
    for name in ORACLES:
        ok, out = run_oracle(name)
        if not ok:
            return False, "%s FAILED\n%s" % (name, out[-2000:])
    return True, ""


def main():
    for dirpath, dirnames, _ in os.walk(ROOT):
        for d in list(dirnames):
            if d == "__pycache__":
                shutil.rmtree(os.path.join(dirpath, d), ignore_errors=True)

    ok, out = run_tests()
    if not ok:
        print("ABORT: the oracle fails BEFORE any mutation is applied.")
        print(out[-3000:])
        return 1
    print("baseline: oracle passes (%s), %d mutations to apply\n"
          % (", ".join(ORACLES), len(MUTATIONS)))

    backup = tempfile.mkdtemp(prefix="attr_orig_")
    saved = {}
    for f in sorted({m for (m, _, _, _) in MUTATIONS}):
        flat = f.replace("/", "__")
        shutil.copy2(os.path.join(ROOT, f), os.path.join(backup, flat))
        saved[flat] = os.path.join(ROOT, f)

    killed = survived = skipped = equivalent = 0
    survivors, skips, unexpected = [], [], []
    try:
        for i, (f, desc, find, repl) in enumerate(MUTATIONS, 1):
            path = os.path.join(ROOT, f)
            original = open(path, encoding="utf-8").read()
            n = original.count(find)
            if n != 1:
                skipped += 1
                why = "pattern absent" if n == 0 else "ambiguous"
                skips.append("%s: %s (%s)" % (f, desc, why))
                print("  %2d. SKIP     %-58s (%s)" % (i, desc[:58], why))
                continue
            mutated = original.replace(find, repl, 1)
            if mutated == original:
                skipped += 1
                skips.append("%s: %s (NO-OP)" % (f, desc))
                print("  %2d. SKIP     %-58s (NO-OP)" % (i, desc[:58]))
                continue
            try:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(mutated)
                passed, _ = run_tests()
                key = "%s: %s" % (f, desc)
                if passed and key in EQUIVALENT:
                    equivalent += 1
                    print("  %2d. equiv    %s" % (i, desc[:58]))
                elif key in EQUIVALENT:
                    killed += 1
                    unexpected.append(key)
                    print("  %2d. killed   %s (listed EQUIVALENT)" % (i, desc[:58]))
                elif passed:
                    survived += 1
                    survivors.append(key)
                    print("  %2d. SURVIVED %-58s <-- NOT TESTED" % (i, desc[:58]))
                else:
                    killed += 1
                    print("  %2d. killed   %s" % (i, desc[:58]))
            finally:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(original)
    finally:
        for name, dest in saved.items():
            shutil.copy2(os.path.join(backup, name), dest)
        shutil.rmtree(backup, ignore_errors=True)

    intact, _ = run_tests()
    print("\n" + "=" * 78)
    print("  seeded:     %d" % len(MUTATIONS))
    print("  killed:     %d" % killed)
    print("  equivalent: %d" % equivalent)
    print("  survived:   %d" % survived)
    print("  skipped:    %d" % skipped)
    print("  source restored and oracle green: %s" % intact)
    for s in survivors:
        print("  SURVIVOR: %s" % s)
    for s in skips:
        print("  SKIPPED:  %s" % s)
    for s in unexpected:
        print("  RECHECK:  %s was listed as equivalent but was KILLED" % s)
    print("=" * 78)
    return 0 if (survived == 0 and skipped == 0 and not unexpected
                 and intact) else 1


if __name__ == "__main__":
    sys.exit(main())
