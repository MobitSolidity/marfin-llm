#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Re-grade the RECORDED plain and tools replies with the CURRENT grader.

WHY THIS EXISTS (D-0112)
------------------------
The user approved three grader fixes on 2026-10-06 (whole-word must_not
matching, refusal-aware must_not matching, one observed refusal phrase).
The model is not re-run here -- it cannot be, and a re-run would change two
things at once. So the fixed grader is applied to the replies the model
ALREADY wrote, and the result is graded by scripts/grade_merged.py exactly as
a fresh run would be.

This is the eval-arm counterpart of scripts/regrade_citations.py, with the
same discipline:

* The model's text is used byte for byte. Nothing in `output` changes.
* Only GRADING fields are recomputed (grade_case's own outputs). Fields that
  record what HAPPENED -- executed tool calls and their values, latency,
  RSS, the model identity -- are copied through untouched.
* The rag arm is copied through untouched: its citation metrics already have
  their own regrade path, and its abstention flags are MEASURED unchanged by
  D-0112 (0 of 64 rows across both recorded runs).
* Every row that changes is listed, old -> new, so the regrade can be read
  rather than trusted.
* Per-arm `threshold_verdicts` in the input are dropped, not recomputed --
  merge_phase4.py's own rule: grade the merged summaries deliberately.

Run:
    python3 scripts/regrade_eval.py evidence/phase4_merged_2026-09-27.json \\
        --out evidence/phase4_merged_2026-09-27_regraded_D0112.json

Stdlib only.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, HERE)

import phase4_lib as L                                       # noqa: E402

EVAL_ARMS = ("plain", "tools")

# grade_case's outputs that the fixes can move. Read from grade_case rather
# than listed by hand would be nicer, but grade_case also emits fields that are
# facts about the reply's tool calls (schema validity, capping), and a regrade
# must not silently recompute those under a different cap or registry.
GRADING_FIELDS = ("banned_hits", "abstained", "abstention_ok", "fabricated",
                  "value_ok", "should_abstain", "persian_script",
                  "latin_ratio", "empty_output")


def _schemas_by_name():
    from tools.registry import tool_schemas
    out = {}
    for s in tool_schemas():
        fn = s.get("function", s)
        out[fn["name"]] = fn
    return out


def regrade_run(run, cases, schemas_by_name=None):
    """
    (new_run, changes). `changes` lists every (arm, id, field, old, new).
    """
    schemas_by_name = schemas_by_name or _schemas_by_name()
    new = copy.deepcopy(run)
    changes = []
    for arm in EVAL_ARMS:
        rows = new.get("arms", {}).get(arm)
        if not rows:
            continue
        for r in rows:
            case = cases.get(r["id"])
            if case is None:
                raise KeyError("no eval case for %s::%s" % (arm, r["id"]))
            g = L.grade_case(case, r.get("output") or "", schemas_by_name)
            for k in GRADING_FIELDS:
                if k in g and r.get(k) != g[k]:
                    changes.append((arm, r["id"], k, r.get(k), g[k]))
                    r[k] = g[k]
        summ = L.summarize_eval(rows)
        # summarize_eval reads tool_value_ok / executed from the rows; those
        # were copied through, so the tool-assisted metric is preserved.
        new.setdefault("summaries", {})[arm] = summ
    new.pop("threshold_verdicts", None)
    new["threshold_verdicts_status"] = (
        "DROPPED by scripts/regrade_eval.py: grade the merged summaries with "
        "scripts/grade_merged.py")
    new["label"] = "RECOMPUTED_FROM_RECORDED_OUTPUT"
    new["regraded"] = {
        "by": "scripts/regrade_eval.py",
        "decision": "D-0112",
        "from_label": run.get("label"),
        "model_re_run": False,
        "arms_regraded": [a for a in EVAL_ARMS if (run.get("arms") or {}).get(a)],
        "arms_copied_untouched": sorted(
            a for a in (run.get("arms") or {}) if a not in EVAL_ARMS),
        "fields_recomputed": list(GRADING_FIELDS),
        "n_changes": len(changes),
    }
    return new, changes


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("run")
    ap.add_argument("--eval", default=os.path.join(
        ROOT, "evals", "bilingual_eval_v1.jsonl"))
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)

    run = json.load(open(a.run, encoding="utf-8"))
    cases = {}
    for line in open(a.eval, encoding="utf-8"):
        if line.strip():
            c = json.loads(line)
            cases[c["id"]] = c
    new, changes = regrade_run(run, cases)
    new["regraded"]["source_file"] = os.path.basename(a.run)

    p = print
    p("=" * 78)
    p("EVAL-ARM REGRADE with the current grader -- model NOT re-run")
    p("=" * 78)
    for arm, cid, k, old, nv in changes:
        p("  %-5s %-12s %-14s %r -> %r" % (arm, cid, k, old, nv))
    if not changes:
        p("  no grading field changed")
    p("")
    for arm in EVAL_ARMS:
        o = (run.get("summaries") or {}).get(arm) or {}
        n = new["summaries"].get(arm) or {}
        for k in ("correct_abstention_pct", "fabricated_financial_data_count",
                  "deterministic_calc_correctness_pct",
                  "tool_call_schema_validity_pct", "banned_phrase_cases"):
            flag = "" if o.get(k) == n.get(k) else "   <== CHANGED"
            p("  %-5s %-40s %s -> %s%s" % (arm, k, o.get(k), n.get(k), flag))
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump(new, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        p("\nwritten: %s" % a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
