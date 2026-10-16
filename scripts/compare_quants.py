#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 7: compare two MERGED runs of the same model at different quantisations
(D-0121). Quality, speed, RAM and size, row by row.

    python3 scripts/compare_quants.py BASELINE.json CANDIDATE.json --out cmp.json

WHAT IT REFUSES
---------------
* Two runs that differ in anything but the weights. ctx, threads, max_tokens,
  tool-call cap, sampling, prompt_options and the eval cases must all agree,
  or a "quantisation loss" would really be a harness change. Refused, not
  warned: a confounded comparison reported as a quantisation result is a
  fabricated finding.
* Two runs of the SAME weights (same sha256). That is a repeatability check,
  not a quantisation comparison, and is labelled as one.
* Weights the project cannot attest to (identity label not VERIFIED).

WHAT IT DOES NOT CLAIM
----------------------
* Persian FLUENCY is a human judgement (R10). This script reports only the
  mechanical Persian check (fa_not_in_persian) and lists every Persian row
  whose reply changed, for a human to read.
* Latency measured on different days is confounded by machine state. The
  MEASURED spread of the same Q5_K_M weights across three sessions
  (2026-10-09, -14 first run, -14 rerun) is 2.65-4.37 tok/s decode. A speed
  difference smaller than that spread is reported as NOT RESOLVED.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

#: Decode tok/s observed for ONE set of weights (Q5_K_M, sha 8814232b) on the
#: i5-12400 across sessions (M): min 2.65 (2026-10-09), max 4.37 (2026-10-14).
SAME_WEIGHTS_DECODE_SPREAD = (2.65, 4.37)

#: Per-row booleans the graders write. A flip True->False is a regression.
ROW_FIELDS = {
    "plain": ("value_ok", "abstention_ok", "fabricated"),
    "tools": ("value_ok", "tool_value_ok", "abstention_ok", "fabricated"),
    "rag": ("value_ok", "abstained", "retrieval_ok", "fabricated"),
}
#: For these a True is BAD.
BAD_WHEN_TRUE = {"fabricated"}

SUMMARY_KEYS = ("deterministic_calc_correctness_pct", "correct_abstention_pct",
                "tool_call_schema_validity_pct", "fabricated_financial_data_count",
                "fa_not_in_persian", "answer_correct_pct", "citation_correctness_pct",
                "unsupported_claim_rate_pct", "retrieval_hit_pct", "empty_outputs")


def _sig(run):
    m = run.get("model") or {}
    s = dict(m.get("sampling") or {})
    return {"ctx": m.get("ctx"), "threads": m.get("threads"),
            "max_tokens": m.get("max_tokens"), "tool_call_cap": m.get("tool_call_cap"),
            "prompt_format": m.get("prompt_format"),
            "sampling": json.dumps(s, sort_keys=True),
            "prompt_options": json.dumps(m.get("prompt_options")
                                         or {"second_turn": False, "refusal_language": False},
                                         sort_keys=True),
            "cases": {a: sorted(r["id"] for r in rows)
                      for a, rows in sorted((run.get("arms") or {}).items())},
            "questions": {a: [r.get("question") for r in sorted(rows, key=lambda r: r["id"])]
                          for a, rows in sorted((run.get("arms") or {}).items())}}


def check_comparable(base, cand):
    """List of reasons the two runs may NOT be compared (empty = comparable)."""
    problems = []
    sb, sc = _sig(base), _sig(cand)
    for k in sb:
        if sb[k] != sc[k]:
            problems.append("runs differ in %s (only the weights may differ)" % k)
    for name, run in (("baseline", base), ("candidate", cand)):
        ident = (run.get("model") or {}).get("identity") or {}
        if ident.get("label") != "VERIFIED":
            problems.append("%s weights are not VERIFIED (label %r)" % (name, ident.get("label")))
        if not run.get("complete", False):
            problems.append("%s run is not complete (arms missing: %s)"
                            % (name, run.get("arms_missing")))
        if run.get("merge_problems"):
            problems.append("%s has merge problems: %s" % (name, run["merge_problems"]))
    return problems


def _ident(run):
    m = run.get("model") or {}
    i = m.get("identity") or {}
    return {"file": m.get("file"), "sha256": i.get("sha256"), "size_gib": m.get("size_gib")}


def compare(base, cand):
    problems = check_comparable(base, cand)
    if problems:
        return {"label": "REFUSED", "problems": problems}
    same = _ident(base)["sha256"] == _ident(cand)["sha256"]
    out = {"label": "COMPUTED_FROM_MEASURED",
           "kind": "REPEATABILITY (same weights)" if same else "QUANTISATION",
           "baseline": _ident(base), "candidate": _ident(cand),
           "prompt_options": (base.get("model") or {}).get("prompt_options"),
           "summaries": {}, "regressions": [], "improvements": [],
           "reply_changed": {}, "persian_rows_changed": []}
    for arm in sorted(base.get("arms") or {}):
        sb = (base.get("summaries") or {}).get(arm) or {}
        sc = (cand.get("summaries") or {}).get(arm) or {}
        out["summaries"][arm] = {k: {"baseline": sb.get(k), "candidate": sc.get(k)}
                                 for k in SUMMARY_KEYS if k in sb or k in sc}
        rb = {r["id"]: r for r in base["arms"][arm]}
        rc = {r["id"]: r for r in cand["arms"][arm]}
        changed = 0
        for cid in sorted(rb):
            b, c = rb[cid], rc[cid]
            if (b.get("output") or "") != (c.get("output") or ""):
                changed += 1
                if b.get("lang") == "fa" or cid.startswith(("FA-", "RAG-FA", "RAG2-FA")):
                    out["persian_rows_changed"].append("%s/%s" % (arm, cid))
            for f in ROW_FIELDS.get(arm, ()):
                vb, vc = b.get(f), c.get(f)
                if vb is None or vc is None or vb == vc:
                    continue
                good_b = (not vb) if f in BAD_WHEN_TRUE else bool(vb)
                good_c = (not vc) if f in BAD_WHEN_TRUE else bool(vc)
                if good_b == good_c:
                    continue
                if arm == "rag" and f == "abstained":
                    # abstaining is good only when the case is unanswerable
                    want = not b.get("answerable", True)
                    good_b, good_c = (vb == want), (vc == want)
                    if good_b == good_c:
                        continue
                entry = {"row": "%s/%s" % (arm, cid), "field": f, "baseline": vb, "candidate": vc}
                (out["regressions"] if good_b and not good_c else out["improvements"]).append(entry)
        out["reply_changed"][arm] = {"changed": changed, "of": len(rb)}
    lb, lc = base.get("latency_spread") or {}, cand.get("latency_spread") or {}
    db = (lb.get("decode_tokens_per_sec_min"), lb.get("decode_tokens_per_sec_max"))
    dc = (lc.get("decode_tokens_per_sec_min"), lc.get("decode_tokens_per_sec_max"))
    resolved = None
    if None not in db + dc:
        lo, hi = SAME_WEIGHTS_DECODE_SPREAD
        # Resolved only if the candidate's whole range clears the baseline's
        # range by more than the same-weights session spread.
        margin = hi - lo
        if dc[0] - db[1] > margin:
            resolved = "candidate FASTER, beyond the same-weights spread"
        elif db[0] - dc[1] > margin:
            resolved = "candidate SLOWER, beyond the same-weights spread"
        else:
            resolved = ("NOT RESOLVED: the difference is within the %.2f-%.2f tok/s the same "
                        "Q5_K_M weights measured across sessions" % (lo, hi))
    out["speed"] = {"decode_tps_baseline": db, "decode_tps_candidate": dc,
                    "ttft_s_baseline": (lb.get("ttft_seconds_min"), lb.get("ttft_seconds_max")),
                    "ttft_s_candidate": (lc.get("ttft_seconds_min"), lc.get("ttft_seconds_max")),
                    "verdict": resolved}
    out["ram"] = {"peak_rss_gib_baseline": base.get("peak_rss_gib"),
                  "peak_rss_gib_candidate": cand.get("peak_rss_gib")}
    out["size"] = {"baseline_gib": _ident(base)["size_gib"], "candidate_gib": _ident(cand)["size_gib"]}
    out["verdict"] = ("NO ROW REGRESSED" if not out["regressions"]
                      else "%d ROW(S) REGRESSED" % len(out["regressions"]))
    out["human_review"] = ("Persian fluency is a human judgement (R10): read the replies of "
                           "persian_rows_changed in both files before accepting the candidate.")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("baseline")
    ap.add_argument("candidate")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    base = json.load(open(a.baseline, encoding="utf-8"))
    cand = json.load(open(a.candidate, encoding="utf-8"))
    res = compare(base, cand)
    res["sources"] = [os.path.basename(a.baseline), os.path.basename(a.candidate)]
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(res, f, indent=2, ensure_ascii=False)
    brief = {k: res.get(k) for k in ("label", "kind", "problems", "verdict", "regressions",
                                     "improvements", "reply_changed", "speed", "ram", "size")
             if k in res}
    print(json.dumps(brief, indent=1, ensure_ascii=False))
    return 0 if res["label"] != "REFUSED" else 2


if __name__ == "__main__":
    sys.exit(main())
