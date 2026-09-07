"""
How much resolution does each approved threshold actually have?

WHY THIS EXISTS (R49)
---------------------
Grading the 2026-09-03 run raised a question the thresholds themselves cannot
answer. `citation_correctness_pct_min = 95` was evaluated over 7 checkable
answers, where 6 of 7 is 85.71 % -- so the threshold is satisfiable ONLY by
perfection. `unsupported_claim_rate_pct_max = 3` was evaluated over 11 claims,
where 1 of 11 is 9.09 % -- also satisfiable only by perfection.

A percentage threshold over a small denominator is not a percentage threshold.
It is a pass/fail-at-perfection gate wearing a percentage's clothes, and the
difference is invisible in the verdict: both read "FAIL against 95".

This script makes it visible. For each percentage threshold it computes the
smallest n at which the threshold can tolerate ONE failure, and reports how far
the current eval set is from that n.

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
It does not propose relaxing anything. The thresholds were pre-committed on
2026-08-10 and approved; loosening one after seeing the numbers would turn a
pre-registration into decoration, which is the single most damaging thing that
could be done to this project's evidence base. The output is a statement about
the EVAL SET, not about the thresholds.

It also does not change any verdict. The FAIL recorded on 2026-09-05 stands
either way: at n=7 the observed 42.86 % fails, and it would fail at n=20 too.
Resolution is about whether a FUTURE good-but-imperfect result could ever be
distinguished from a bad one.

Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

# Which thresholds are percentages over a countable denominator, and what that
# denominator IS. A threshold measured on a continuous quantity (tok/s, GiB,
# seconds) has no such granularity problem and is excluded rather than
# force-fitted.
COUNTED = {
    "citation_correctness_pct_min": {
        "unit": "checkable answers",
        "where": "the rag arm's answerable rows that produced a claim",
        "dir": "min",
    },
    "unsupported_claim_rate_pct_max": {
        "unit": "verifiable claims",
        "where": "sentences asserting a magnitude, across the rag answers",
        "dir": "max",
    },
    "deterministic_calc_correctness_pct_min": {
        "unit": "deterministic calculation cases",
        "where": "eval rows carrying expected_value",
        "dir": "min",
    },
    "correct_abstention_pct_min": {
        "unit": "cases that should abstain",
        "where": "eval rows with must_abstain",
        "dir": "min",
    },
    "tool_call_schema_validity_pct_min": {
        "unit": "attempted tool calls",
        "where": "the tools arm's tool_calls_attempted",
        "dir": "min",
    },
    "persian_fluency_regression_pct_max": {
        "unit": "Persian cases with a human grade",
        "where": "fa-language rows, once R10 grading is done",
        "dir": "max",
    },
}

CONTINUOUS = (
    "model_file_size_gib_max", "peak_rss_8k_gib_max",
    "generation_tokens_per_sec_min", "time_to_first_token_2k_sec_max",
)

# Count thresholds have no percentage at all: 0 means 0.
ABSOLUTE = ("fabricated_financial_data_count_max",
            "paper_live_confusion_count_max")


def min_n_for_one_failure(limit, direction, cap=400):
    """
    Smallest n at which the threshold survives exactly one failure.

    For a minimum: the smallest n where (n-1)/n * 100 >= limit.
    For a maximum: the smallest n where 1/n * 100 <= limit.

    Returns None if no n up to `cap` works, which is itself a finding: a
    threshold that needs more than 400 items is not reachable by hand-built
    fixtures.
    """
    for n in range(1, cap + 1):
        if direction == "min":
            if 100.0 * (n - 1) / n >= limit:
                return n
        else:
            if 100.0 * 1 / n <= limit:
                return n
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Report the resolution of each percentage threshold "
                    "against the current eval size. Proposes no change.")
    ap.add_argument("--state", default="PROJECT_STATE.json")
    ap.add_argument("--observed", default=None,
                    help="optional json of {threshold: current_n}")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)

    thr = dict(json.load(open(a.state, encoding="utf-8"))
               ["acceptance_thresholds"])
    thr.pop("status", None)
    observed = json.load(open(a.observed, encoding="utf-8")) \
        if a.observed else {}

    p = print
    p("=" * 78)
    p("THRESHOLD RESOLUTION (R49)")
    p("=" * 78)
    p("For a percentage threshold, 'resolution' is the smallest denominator at")
    p("which ONE failure does not fail the whole threshold. Below that n, the")
    p("threshold is a pass-at-perfection gate, not a percentage.")
    p("")

    rows = []
    for name in sorted(COUNTED):
        if name not in thr:
            continue
        spec = COUNTED[name]
        limit = thr[name]
        need = min_n_for_one_failure(limit, spec["dir"])
        cur = observed.get(name)
        row = {"threshold": name, "limit": limit, "unit": spec["unit"],
               "counted_over": spec["where"],
               "min_n_to_tolerate_one_failure": need,
               "current_n": cur}
        if cur is None:
            row["status"] = "CURRENT_N_UNKNOWN"
        elif need is None:
            row["status"] = "UNREACHABLE"
        elif cur >= need:
            row["status"] = "HAS_RESOLUTION"
        else:
            row["status"] = "PASS_AT_PERFECTION_ONLY"
            row["shortfall"] = need - cur
        rows.append(row)

        p("%-40s limit %s" % (name, limit))
        p("    counted over : %s (%s)" % (spec["where"], spec["unit"]))
        p("    needs n >= %-4s to tolerate ONE failure"
          % (need if need is not None else ">400"))
        if cur is not None:
            p("    current n    : %d  ->  %s%s"
              % (cur, row["status"],
                 ("  (short by %d)" % row["shortfall"])
                 if "shortfall" in row else ""))
        else:
            p("    current n    : UNKNOWN -- not supplied")
        p("")

    p("-" * 78)
    p("EXCLUDED, and why:")
    for name in CONTINUOUS:
        if name in thr:
            p("  %-40s continuous quantity; no denominator" % name)
    for name in ABSOLUTE:
        if name in thr:
            p("  %-40s a COUNT of 0; no percentage to resolve" % name)
    p("")
    p("This script proposes NO change to any threshold. They were "
      "pre-committed")
    p("and approved on 2026-08-10; relaxing one after seeing the numbers "
      "would")
    p("turn a pre-registration into decoration. What is reported here is a "
      "fact")
    p("about the EVAL SET.")

    payload = {
        "label": "COMPUTED_THRESHOLD_RESOLUTION",
        "computed_by": "scripts/threshold_resolution.py",
        "risk": "R49",
        "rows": rows,
        "excluded_continuous": [n for n in CONTINUOUS if n in thr],
        "excluded_absolute": [n for n in ABSOLUTE if n in thr],
        "proposes_no_threshold_change": True,
        "note": ("Resolution is about whether a future good-but-imperfect "
                 "result could be distinguished from a bad one. It does not "
                 "change the 2026-09-05 FAIL, which stands at any n."),
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
