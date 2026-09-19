#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
grade_persian.py -- the R10 human-grading tool.

WHAT R10 IS AND WHY A TOOL CANNOT SETTLE IT
-------------------------------------------
R10 is the one Phase 4 threshold that no automated check can decide.
`persian_generation_quality` reads UNKNOWN in PROJECT_STATE.json with the note
"needs a human reader", and the merged evidence agrees VERBATIM:

    human_grading: {"status": "PENDING", "note": "Persian fluency, rubric
    compliance and unsupported-claim judgement require a human reader (R10).
    No field in this file records a human grade."}

So this tool does NOT grade anything. It is a *presenter and recorder*: it
shows one case at a time with its question, its rubric and the model's actual
output, takes the human's verdict, and writes that verdict back into
`human_grade`. Every judgement in the output file came from a person.

This boundary is the whole design. A tool that scored Persian fluency with a
heuristic would produce a number, that number would be indistinguishable from a
measurement in any later summary, and R10 would silently move from UNKNOWN to a
fabricated PASS. That is precisely the failure this project forbids.

WHAT IS MEASURED, AND WHAT IS THEREFORE ONLY *SHOWN*
----------------------------------------------------
Some facts in the evidence file ARE mechanical, and those are displayed as
context so the human does not have to recompute them by eye:
    * `latin_ratio`, `persian_script`  -- script composition
    * `value_ok`, `tool_ok`            -- did the arithmetic / tool call land
    * `abstained`, `should_abstain`    -- refusal behaviour
    * `banned_hits`, `fabricated`      -- automated red flags
These are shown as ALREADY-MEASURED context, clearly labelled, and are never
mixed into the human's verdict.

MEASURED SHAPE OF THE INPUT (verified against the real file before writing)
--------------------------------------------------------------------------
    total cases            52   (rag 10, tools 21, plain 21 -- NOT 21 overall)
    already graded          0
    cases with output      37
    cases missing a rubric  0
    lang distribution      en 27, fa 23, mixed 2

Two consequences drove the design:

1. 15 of 52 cases have EMPTY output. They are not gradeable for fluency, and
   pretending otherwise would put a human verdict on nothing. They are marked
   `no_output` automatically and skipped, and they are reported separately so
   the gap stays visible instead of being averaged away.

2. The `lang` field is the case's INTENDED language, not the output's. VERIFIED:
   case EN-CALC-001 carries lang='en' and its output is in Persian. That
   mismatch is itself a defect a human must see, so this tool shows both and
   never silently filters by `lang`.

SAFETY
------
* The input file is opened READ-ONLY and never written. Grades go to a separate
  output file, so a mistake can never damage the evidence base.
* Progress is saved after EVERY grade, not at the end. A 52-case session that
  crashed at case 50 and lost everything would simply not be done again.
* Resumable: re-running picks up where it stopped, because a human's time is
  the scarcest input here.
* This tool NEVER writes `phase_4/measurements_recorded` and never computes an
  aggregate verdict for R10. It reports counts; the threshold decision stays a
  separate, explicit human step.

USAGE
-----
    python3 tools/grade_persian.py --input  phase4_merged.json \\
                                   --output phase4_grades.json
    python3 tools/grade_persian.py --input ... --output ... --report
    python3 tools/grade_persian.py --input ... --output ... --arm rag
"""

from __future__ import annotations

import argparse
import json
import os
import sys

# The verdict vocabulary. Deliberately SMALL: a 1-10 fluency score invites
# false precision from a single reader, while these four map onto decisions.
GRADES = {
    "1": ("GOOD", "fluent Persian, follows the rubric, no unsupported claim"),
    "2": ("WEAK", "understandable but clumsy, or partially misses the rubric"),
    "3": ("BAD", "not acceptable Persian, or ignores the rubric"),
    "4": ("WRONG_LANGUAGE", "answered in the wrong language for the question"),
    "5": ("UNSUPPORTED", "fluent, but asserts a figure or fact it cannot support"),
}
SKIP = "s"
QUIT = "q"

# Written into cases whose output is empty. NOT a human grade, and reported
# under its own heading so it can never be read as one.
NO_OUTPUT = "no_output"


def case_key(case):
    """
    The grade key. `arm::id`, NEVER `id` alone.

    WHY. Caught by auditing this tool's own first output: it reported 22 empty
    outputs where a direct count of the file gives 15. MEASURED cause --

        cases: 52   distinct ids: 31   duplicate ids across arms: 21

    The `tools` and `plain` arms deliberately ask the SAME 21 questions, so
    `EN-CALC-001` exists in both. Keying by id alone made the second arm's
    entry collide with the first: 52 cases collapsed to 31, and a verdict on
    the tools arm silently became the verdict for the plain arm too.

    That is the worst possible defect for this file, because comparing arms on
    the same questions is the entire reason the evidence is structured this
    way. A cross-contaminated grade would not look wrong -- it would look like
    a finding.
    """
    return "%s::%s" % (case.get("arm"), case.get("id"))


def load_cases(path):
    """
    Flatten the arms into one ordered list. Read-only.

    The merged file stores cases under `arms` -> {rag, tools, plain} -> [case].
    VERIFIED against the real file: 10 + 21 + 21 = 52.
    """
    # A missing input file is the single most likely first-run problem, and a
    # raw FileNotFoundError traceback tells the user nothing actionable. It is
    # also the SECOND error a user hits: they fix the argparse complaint, then
    # land here. Both need to name the fix, not just the fault.
    if not os.path.exists(path):
        # WHICH FILE TO SUGGEST, AND WHY THE ORDER MATTERS.
        #
        # This block used to name evidence/phase4_merged.json unconditionally.
        # That was right when it was the only merged file; it became a TRAP on
        # 2026-09-05, when the 2026-09-03 run was committed alongside it.
        # MEASURED difference between the two:
        #
        #   phase4_merged.json             2026-08-27  max_tokens 2048  15 EMPTY
        #   phase4_merged_2026-09-03.json  2026-09-03  max_tokens  512   0 EMPTY
        #
        # A human who followed the old suggestion would have spent an hour
        # reading 15 blank pages out of 52, grading the CONTAMINATED run that
        # D-0081's superseded FAIL came from -- and nothing would have told
        # them. So candidates are tried NEWEST FIRST, and the message says
        # plainly what each file is.
        here = os.path.dirname(os.path.abspath(__file__))
        ev = os.path.join(os.path.dirname(here), "evidence")
        candidates = [
            ("phase4_merged_2026-09-03.json",
             "the 2026-09-03 run: 52 cases, 0 empty outputs. USE THIS ONE."),
            ("phase4_merged.json",
             "the SUPERSEDED 2026-08-27 run: 15 of 52 outputs are EMPTY and "
             "cannot be graded for fluency. Do not grade this by mistake."),
        ]
        found = [(n, d) for n, d in candidates
                 if os.path.exists(os.path.join(ev, n))]
        msg = [
            "ERROR: --input file not found: %s" % path,
            "",
            "  (the path is resolved against the CURRENT directory, which is",
            "   %s)" % os.getcwd(),
        ]
        if found:
            name, desc = found[0]
            msg += [
                "",
                "  Run this from the repository root -- the folder holding",
                "  README.md and the .git directory:",
                "",
                "    python %s --input %s --output grades.json"
                % (os.path.join("tools", os.path.basename(__file__)),
                   os.path.join("evidence", name)),
                "",
                "  %s" % desc,
            ]
            if len(found) > 1:
                msg += [
                    "",
                    "  ALSO PRESENT, and NOT the one to use:",
                ]
                for n, d in found[1:]:
                    msg += ["    evidence/%s -- %s" % (n, d)]
        else:
            msg += [
                "",
                "  No merged evidence file is present in this copy of the",
                "  project, so this tool has nothing to read. Backups made",
                "  before 2026-08-31 shipped it without one. Download a",
                "  current backup, or fetch evidence/ from the repository.",
            ]
        raise SystemExit("\n".join(msg))
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    arms = data.get("arms")
    if not isinstance(arms, dict):
        raise SystemExit(
            "ERROR: %s has no `arms` object. This tool reads the MERGED "
            "results file (label MEASURED_PER_ARM_MERGED), not a single-arm "
            "run." % path)
    out = []
    for arm in ("rag", "tools", "plain"):
        for case in arms.get(arm, []) or []:
            case = dict(case)
            case.setdefault("arm", arm)
            out.append(case)

    # WARN ON A FILE WITH EMPTY OUTPUTS, whatever its name.
    #
    # The path-not-found message above can only help someone who typed a wrong
    # path. It cannot help someone who typed a valid path to the SUPERSEDED
    # file -- and the two names differ by one date suffix.
    #
    # MEASURED: the 2026-08-27 run has 15 of 52 outputs empty, because the
    # model spent its whole budget inside an unterminated <think> block. Those
    # cases are not gradeable for fluency at all; a human would be reading
    # blank pages and would have no way to know the newer run exists. The
    # 2026-09-03 run has 0.
    #
    # This is a WARNING, not a refusal. Grading an old run is a legitimate
    # thing to want -- re-reading it, or auditing a past verdict -- and this
    # tool has no business deciding which run the user meant. It only refuses
    # to let that happen SILENTLY.
    empty = sum(1 for c in out if not (c.get("output") or "").strip())
    if empty:
        ts = str(data.get("timestamp") or "")[:10] or "unknown date"
        print("")
        print("  " + "!" * 68)
        print("  WARNING: %d of %d cases in this file have EMPTY output."
              % (empty, len(out)))
        print("  Run timestamp: %s   max_tokens: %s"
              % (ts, (data.get("model") or {}).get("max_tokens")))
        print("")
        print("  Those cases cannot be graded for Persian fluency -- there is")
        print("  no text to read. They are marked %r and skipped." % NO_OUTPUT)
        print("")
        here = os.path.dirname(os.path.abspath(__file__))
        newer = os.path.join(os.path.dirname(here), "evidence",
                             "phase4_merged_2026-09-03.json")
        if os.path.exists(newer) and os.path.abspath(newer) != \
                os.path.abspath(path):
            print("  A LATER RUN IS PRESENT AND HAS NO EMPTY OUTPUTS:")
            print("    evidence/phase4_merged_2026-09-03.json")
            print("")
            print("  If you meant to grade the current run, stop now and")
            print("  point --input at that file instead.")
        print("  " + "!" * 68)
        print("")
    if not out:
        raise SystemExit("ERROR: %s contains no cases." % path)
    return data, out


def load_grades(path):
    """Existing grades, so a session can resume. Missing file is not an error."""
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            saved = json.load(fh)
    except (ValueError, OSError) as exc:
        raise SystemExit(
            "ERROR: could not read existing grades at %s (%s). Refusing to "
            "continue, because overwriting them would destroy human work."
            % (path, exc))
    return {k: v for k, v in (saved.get("grades") or {}).items()}


def save_grades(path, grades, source):
    """
    Write after every single grade.

    `atomic` via a temp file + replace: a process killed mid-write must not be
    able to truncate a file that holds a human's completed work.
    """
    payload = {
        "label": "HUMAN_GRADED",
        "note": "Every grade in this file was entered by a human reader. "
                "Nothing here is machine-scored. Counts are COMPUTED from "
                "those grades; the R10 threshold verdict is NOT set here.",
        "source_file": source,
        "grades": grades,
    }
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _wrap(text, width=76, indent="    "):
    """Wrap on whitespace. Works for Persian because it splits on spaces."""
    words, lines, cur = str(text).split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            lines.append(indent + cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(indent + cur)
    return "\n".join(lines) if lines else indent + "(empty)"


def show_case(case, idx, total):
    """Print one case. Question and rubric FIRST, output last."""
    print()
    print("=" * 78)
    print("CASE %d of %d   id=%s   arm=%s   intended lang=%s"
          % (idx, total, case.get("id"), case.get("arm"), case.get("lang")))
    print("=" * 78)
    print("  QUESTION")
    print(_wrap(case.get("question") or "(none)"))
    print()
    print("  RUBRIC -- what a correct answer must do")
    print(_wrap(case.get("rubric") or "(none)"))
    print()

    # Mechanical facts, clearly fenced off from the human's judgement.
    print("  ALREADY MEASURED (machine facts -- context, not your verdict)")
    for key in ("value_ok", "tool_ok", "abstained", "should_abstain",
                "persian_script", "latin_ratio", "fabricated", "banned_hits",
                "empty_output"):
        if key in case:
            print("      %-16s %s" % (key, case.get(key)))
    print()
    print("  MODEL OUTPUT")
    out = (case.get("output") or "").strip()
    print(_wrap(out) if out else "    (EMPTY -- nothing to grade)")
    print()


def prompt(case):
    """Ask for one verdict. Returns a grade name, SKIP, or QUIT."""
    print("  YOUR VERDICT")
    for key in sorted(GRADES):
        name, desc = GRADES[key]
        print("      %s) %-15s %s" % (key, name, desc))
    print("      %s) skip for now      %s) save and quit" % (SKIP, QUIT))
    while True:
        try:
            raw = input("  choice: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            # Treated as "save and quit", never as a grade. An interrupted
            # reader must not have a verdict invented for them.
            print("\n  (interrupted -- saving and stopping)")
            return QUIT
        if raw in GRADES:
            return GRADES[raw][0]
        if raw in (SKIP, QUIT):
            return raw
        print("  not one of the choices; nothing recorded. Try again.")


def report(cases, grades):
    """
    Counts only. Deliberately does NOT emit an R10 verdict.

    A single aggregate number would be treated as the threshold result, and
    R10 needs a human to make that call with the counts in front of them.
    """
    total = len(cases)
    tally, no_out, ungraded = {}, 0, 0
    for case in cases:
        g = grades.get(case_key(case))
        if g == NO_OUTPUT:
            no_out += 1
        elif g:
            tally[g] = tally.get(g, 0) + 1
        else:
            ungraded += 1

    print()
    print("=" * 78)
    print("R10 PERSIAN GENERATION -- HUMAN GRADING REPORT")
    print("=" * 78)
    print("  cases total                 %d" % total)
    print("  graded by a human           %d" % sum(tally.values()))
    print("  not gradeable (no output)   %d" % no_out)
    print("  still ungraded              %d" % ungraded)
    print()
    for name in ("GOOD", "WEAK", "BAD", "WRONG_LANGUAGE", "UNSUPPORTED"):
        if name in tally:
            print("      %-16s %d" % (name, tally[name]))
    print()
    if ungraded:
        print("  STATUS: PENDING -- %d case(s) have no human verdict, so no"
              % ungraded)
        print("          aggregate can be computed without inventing them.")
    else:
        print("  STATUS: every case with output has a human verdict.")
        print("          The R10 threshold decision is a SEPARATE, explicit")
        print("          step: this tool reports counts and does not set it.")
    if no_out:
        print()
        print("  NOTE: %d case(s) produced no output at all. They are counted"
              % no_out)
        print("        separately, never as passes, because a fluency verdict")
        print("        on an empty string would be a fabricated measurement.")
    print("=" * 78)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Record HUMAN grades for R10 Persian generation quality.",
        epilog=(
            "BOTH --input and --output are required; running this script with "
            "no arguments prints the usage error above and does nothing else.\n"
            "\n"
            "Examples (from the repository root):\n"
            "  python tools/grade_persian.py "
            "--input evidence/phase4_merged.json --output grades.json\n"
            "  python tools/grade_persian.py "
            "--input evidence/phase4_merged.json --output grades.json "
            "--report\n"
            "\n"
            "From inside the tools/ directory, point --input up one level:\n"
            "  python grade_persian.py "
            "--input ../evidence/phase4_merged.json --output grades.json\n"
            "\n"
            "Windows PowerShell uses backslashes but is otherwise identical:\n"
            "  python tools\\grade_persian.py "
            "--input evidence\\phase4_merged.json --output grades.json\n"),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True,
                    help="merged Phase 4 results file (read-only)")
    ap.add_argument("--output", required=True,
                    help="where grades are written (separate from the input)")
    ap.add_argument("--arm", choices=("rag", "tools", "plain"),
                    help="grade only one arm")
    ap.add_argument("--report", action="store_true",
                    help="print the report and exit; grade nothing")
    args = ap.parse_args(argv)

    if os.path.abspath(args.input) == os.path.abspath(args.output):
        raise SystemExit(
            "ERROR: --output must differ from --input. The evidence file is "
            "read-only by design; writing grades into it would mean a bad "
            "session could damage the measurements themselves.")

    data, cases = load_cases(args.input)
    if args.arm:
        cases = [c for c in cases if c.get("arm") == args.arm]
        if not cases:
            raise SystemExit("ERROR: no cases in arm %r." % args.arm)

    grades = load_grades(args.output)

    # Empty outputs are settled mechanically, before any human time is spent.
    changed = False
    for case in cases:
        cid = case_key(case)
        if cid not in grades and not (case.get("output") or "").strip():
            grades[cid] = NO_OUTPUT
            changed = True
    if changed:
        save_grades(args.output, grades, args.input)

    if args.report:
        return report(cases, grades)

    todo = [c for c in cases if case_key(c) not in grades]
    print()
    print("  %d case(s) loaded from %s" % (len(cases), args.input))
    print("  %d already recorded, %d awaiting your verdict"
          % (len(cases) - len(todo), len(todo)))
    print("  grades are saved after EVERY answer, so stopping is safe.")
    if not todo:
        print("  nothing left to grade.")
        return report(cases, grades)

    for n, case in enumerate(todo, 1):
        show_case(case, n, len(todo))
        verdict = prompt(case)
        if verdict == QUIT:
            print("  saved. Re-run the same command to continue.")
            break
        if verdict == SKIP:
            continue
        grades[case_key(case)] = verdict
        save_grades(args.output, grades, args.input)
        print("  recorded: %s" % verdict)

    return report(cases, grades)


if __name__ == "__main__":
    sys.exit(main())
