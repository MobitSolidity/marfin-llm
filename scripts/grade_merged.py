"""
Grade a MERGED Phase-4 run against the 13 approved acceptance thresholds.

WHY THIS SCRIPT EXISTS AT ALL
-----------------------------
merge_phase4.py deliberately REFUSES to compute threshold verdicts, and its
reason is recorded in the file it writes:

    "Verdicts in a per-arm file were computed over that arm only. This script
     does not recompute them... Grade the merged summaries deliberately; do
     not inherit a subset's verdict."

That refusal is right, and it leaves a gap: somebody has to do the deliberate
grading. Doing it by hand in a chat message is not reproducible and cannot be
re-run when a grader defect is fixed -- and one was fixed the same week
(D-0092). So the grading is a script, its inputs are a file and a threshold
table, and its output is a verdict per threshold with the arithmetic shown.

WHAT IT REFUSES TO DO
---------------------
1. It does not INVENT a metric. A threshold whose metric is absent from the
   run is reported UNMEASURED, never PASS. An unmeasured requirement is not a
   met requirement, and the one temptation this project must resist is letting
   a missing number read as a green one.
2. It does not aggregate across arms by averaging. Where a threshold applies
   per arm, the WORST arm decides, because a 16-hour bilingual analyst that
   fails on Persian is not two-thirds acceptable.
3. It does not write to PROJECT_STATE.json. Recording a measurement into the
   phase record is a gate action requiring explicit user approval; this script
   only reads and reports.
4. It does not read `threshold_verdicts` out of the input file. Those were
   computed per arm, over a subset, and inheriting them is exactly what
   merge_phase4.py warned against.

Stdlib only. Exit code is 0 when the grading COMPLETED, not when it passed --
a non-zero exit would make a legitimate FAIL look like a broken script.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

# Which direction each threshold runs, and which metric answers it.
#
# The metric names are the ones the harness actually writes. They were read out
# of the run file rather than assumed: an earlier session recorded a
# "threshold_naming_mismatch" in PROJECT_STATE precisely because a threshold
# name and a metric name diverged and nobody noticed.
#
# scope:
#   "run"      one number for the whole run (from the top level)
#   "per_arm"  present in each arm's summary; the WORST arm decides
SPEC = {
    "model_file_size_gib_max": {
        "dir": "max", "scope": "run", "path": ("model", "size_gib"),
    },
    "peak_rss_8k_gib_max": {
        "dir": "max", "scope": "run", "path": ("peak_rss_gib",),
    },
    # THE KEY NAMES HERE WERE READ OUT OF THE RUN FILE, NOT GUESSED.
    # My first version used "decode_tps" and treated latency_per_invocation as
    # a dict keyed by arm. It is a LIST of per-source records, and the key is
    # "decode_tokens_per_sec". The script crashed rather than silently
    # reporting UNMEASURED, which is the behaviour I want from a wrong guess.
    "generation_tokens_per_sec_min": {
        "dir": "min", "scope": "per_arm_latency",
        "key": "decode_tokens_per_sec",
    },
    "time_to_first_token_2k_sec_max": {
        "dir": "max", "scope": "per_arm_latency", "key": "ttft_seconds",
    },
    "deterministic_calc_correctness_pct_min": {
        "dir": "min", "scope": "per_arm",
        "key": "deterministic_calc_correctness_pct",
    },
    "unsupported_claim_rate_pct_max": {
        "dir": "max", "scope": "per_arm", "key": "unsupported_claim_rate_pct",
    },
    "citation_correctness_pct_min": {
        "dir": "min", "scope": "per_arm", "key": "citation_correctness_pct",
    },
    "correct_abstention_pct_min": {
        "dir": "min", "scope": "per_arm", "key": "correct_abstention_pct",
    },
    "fabricated_financial_data_count_max": {
        "dir": "max", "scope": "per_arm",
        "key": "fabricated_financial_data_count",
    },
    "persian_fluency_regression_pct_max": {
        "dir": "max", "scope": "per_arm", "key": "persian_fluency_regression_pct",
    },
    "tool_call_schema_validity_pct_min": {
        "dir": "min", "scope": "per_arm", "key": "tool_call_schema_validity_pct",
    },
    "paper_live_confusion_count_max": {
        "dir": "max", "scope": "per_arm", "key": "paper_live_confusion_count",
    },
}


def _dig(obj, path):
    cur = obj
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return None
        cur = cur[p]
    return cur


def collect(run, name, spec):
    """
    Every observation relevant to one threshold, with where it came from.

    Returns (observations, note). `observations` is a list of
    (source_label, value); an empty list means UNMEASURED.
    """
    scope = spec["scope"]
    if scope == "run":
        v = _dig(run, spec["path"])
        # peak_rss_gib may be a dict keyed by arm, or a single number, or None.
        if isinstance(v, dict):
            return [(k, x) for k, x in sorted(v.items()) if x is not None], ""
        return ([("run", v)] if v is not None else []), ""

    if scope == "per_arm_latency":
        # latency_per_invocation is a LIST of records, each naming its source
        # file. Tolerate a dict too, because an older evidence file may use
        # one -- but never assume: the shape is checked, not trusted.
        out = []
        lat = run.get("latency_per_invocation")
        rows = []
        if isinstance(lat, list):
            rows = [(r.get("source") or "?", r) for r in lat
                    if isinstance(r, dict)]
        elif isinstance(lat, dict):
            rows = [(k, v) for k, v in sorted(lat.items())
                    if isinstance(v, dict)]
        for src, row in rows:
            v = row.get(spec["key"])
            if v is not None:
                out.append((src, v))
        return out, ""

    out = []
    absent = []
    for arm in sorted(run.get("summaries") or {}):
        s = run["summaries"][arm] or {}
        if spec["key"] in s and s[spec["key"]] is not None:
            out.append((arm, s[spec["key"]]))
        else:
            absent.append(arm)
    note = ("not reported by: %s" % ", ".join(absent)) if absent else ""
    return out, note


def grade_one(name, limit, spec, run):
    obs, note = collect(run, name, spec)
    if not obs:
        return {"threshold": name, "limit": limit, "verdict": "UNMEASURED",
                "observations": [], "deciding": None, "note": note,
                "why": ("the run reports no value for this metric. An "
                        "unmeasured requirement is NOT a met requirement.")}

    # The WORST observation decides. For a minimum that is the smallest value;
    # for a maximum, the largest.
    if spec["dir"] == "min":
        src, val = min(obs, key=lambda p: p[1])
        ok = val >= limit
        why = "worst arm %s = %s, needs >= %s" % (src, val, limit)
    else:
        src, val = max(obs, key=lambda p: p[1])
        ok = val <= limit
        why = "worst arm %s = %s, needs <= %s" % (src, val, limit)

    return {"threshold": name, "limit": limit,
            "verdict": "PASS" if ok else "FAIL",
            "observations": [{"source": s, "value": v} for s, v in obs],
            "deciding": {"source": src, "value": val},
            "note": note, "why": why}


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Grade a merged Phase-4 run against the approved "
                    "thresholds. Reads only; never writes PROJECT_STATE.")
    ap.add_argument("run", help="merged run json")
    ap.add_argument("--state", default="PROJECT_STATE.json",
                    help="source of the APPROVED thresholds")
    ap.add_argument("--out", default=None, help="write the verdicts as json")
    ap.add_argument(
        "--citations-recomputed", default=None,
        help=("a regrade_citations.py output. Its two metrics OVERRIDE the "
              "recorded ones, because the recorded ones were produced by the "
              "grader that D-0092 fixed. Nothing else is overridden."))
    a = ap.parse_args(argv)

    run = json.load(open(a.run, encoding="utf-8"))
    state = json.load(open(a.state, encoding="utf-8"))
    thr = dict(state["acceptance_thresholds"])
    approved = thr.pop("status", None)

    p = print
    p("=" * 78)
    p("GRADING %s" % os.path.basename(a.run))
    p("=" * 78)
    p("run label            : %s" % run.get("label"))
    p("complete             : %s   arms_missing: %s"
      % (run.get("complete"), run.get("arms_missing")))
    p("thresholds           : %d, %s" % (len(thr), approved))

    # A merged file that is INCOMPLETE cannot be graded as a whole run. Say so
    # and refuse, rather than grading whatever arms happen to be present.
    if run.get("complete") is not True:
        p("")
        p("REFUSING TO GRADE: the merged run is not complete "
          "(arms_missing=%s). A verdict over a subset of arms is the exact "
          "error merge_phase4.py refuses to make." % run.get("arms_missing"))
        return 0

    # THE ONLY OVERRIDE THIS SCRIPT ACCEPTS, AND WHY IT IS NARROW.
    #
    # The two citation metrics in the 2026-09-03 file were produced by a
    # verifier with two MEASURED defects (D-0092): no masking at all, and an
    # ASCII-only year pattern. 8 of 12 graded claims were checked against a
    # marker or a year instead of a magnitude. Grading those numbers would
    # grade the bug, not the model.
    #
    # The override is deliberately restricted to those two keys. Decode rate,
    # TTFT, RSS, abstention and fabrication are properties of the run and are
    # graded exactly as recorded, FAILs included -- overriding those would be
    # laundering the result rather than correcting a grader.
    overrides = {}
    if a.citations_recomputed:
        rc = json.load(open(a.citations_recomputed, encoding="utf-8"))
        s = rc["summary"]
        for key in ("citation_correctness_pct", "unsupported_claim_rate_pct"):
            if s.get(key) is not None:
                overrides[key] = {"value": s[key],
                                  "source": rc.get("label"),
                                  "file": os.path.basename(
                                      a.citations_recomputed)}
        p("")
        p("citation metrics OVERRIDDEN from %s (D-0092):"
          % os.path.basename(a.citations_recomputed))
        for k, v in sorted(overrides.items()):
            was = None
            for arm, summ in (run.get("summaries") or {}).items():
                if summ.get(k) is not None:
                    was = "%s=%s" % (arm, summ[k])
            p("  %-32s recorded %s -> recomputed %s" % (k, was, v["value"]))

    p("")
    results = []
    for n, l in sorted(thr.items()):
        if n not in SPEC:
            continue
        metric_key = SPEC[n].get("key")
        if metric_key in overrides:
            ov = overrides[metric_key]
            val = ov["value"]
            ok = (val >= l) if SPEC[n]["dir"] == "min" else (val <= l)
            results.append({
                "threshold": n, "limit": l,
                "verdict": "PASS" if ok else "FAIL",
                "observations": [{"source": ov["source"], "value": val}],
                "deciding": {"source": ov["source"], "value": val},
                "note": "RECOMPUTED after D-0092, from %s" % ov["file"],
                "why": "recomputed %s = %s, needs %s %s"
                       % (metric_key, val,
                          ">=" if SPEC[n]["dir"] == "min" else "<=", l)})
        else:
            results.append(grade_one(n, l, SPEC[n], run))
    unknown = sorted(set(thr) - set(SPEC))

    width = max(len(r["threshold"]) for r in results)
    for r in results:
        p("%-7s %-*s  %s" % (r["verdict"], width, r["threshold"], r["why"]))
        if r["note"]:
            p("        %s%s" % (" " * width, r["note"]))

    n_pass = sum(1 for r in results if r["verdict"] == "PASS")
    n_fail = sum(1 for r in results if r["verdict"] == "FAIL")
    n_un = sum(1 for r in results if r["verdict"] == "UNMEASURED")

    p("")
    p("-" * 78)
    p("PASS %d   FAIL %d   UNMEASURED %d   (of %d graded)"
      % (n_pass, n_fail, n_un, len(results)))
    if unknown:
        p("thresholds with no metric mapping, NOT graded: %s"
          % ", ".join(unknown))
    p("")
    # The overall verdict. A single FAIL is a FAIL: these thresholds were
    # pre-committed and approved, and softening the aggregation after seeing
    # the numbers is how a pre-registration becomes decoration.
    overall = "PASS" if (n_fail == 0 and n_un == 0) else "FAIL"
    p("OVERALL: %s" % overall)
    if n_fail:
        p("  failing: %s"
          % ", ".join(r["threshold"] for r in results
                      if r["verdict"] == "FAIL"))
    if n_un:
        p("  unmeasured (counted AGAINST, not ignored): %s"
          % ", ".join(r["threshold"] for r in results
                      if r["verdict"] == "UNMEASURED"))

    payload = {
        "label": "COMPUTED_THRESHOLD_VERDICTS",
        "graded_by": "scripts/grade_merged.py",
        "run_file": os.path.basename(a.run),
        "run_label": run.get("label"),
        "thresholds_status": approved,
        "results": results,
        "unmapped_thresholds": unknown,
        "counts": {"pass": n_pass, "fail": n_fail, "unmeasured": n_un},
        "overall": overall,
        "citation_metrics_overridden": (
            {k: v["value"] for k, v in sorted(overrides.items())}
            if overrides else None),
        "override_scope": ("ONLY the two citation metrics, and only because "
                           "the recorded ones came from the grader D-0092 "
                           "fixed. Every other metric is graded as recorded."),
        "aggregation_rule": ("the WORST arm decides each per-arm threshold; a "
                             "single FAIL is an overall FAIL; UNMEASURED "
                             "counts against, never as a pass"),
    }
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.write("\n")
        p("")
        p("written: %s" % a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
