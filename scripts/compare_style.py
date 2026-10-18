#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 8: measure what --style changed (D-0123). Same weights, same runtime;
the ONLY permitted difference is prompt_options.style. compare_quants refuses
this pair on purpose (the prompts differ), so this is the instrument for it.

    python3 scripts/compare_style.py BEFORE.json AFTER.json --out cmp.json

Reports, on the REPLIES (whatever the harness did to them afterwards):
  * LaTeX: replies still containing it (the user's defect 1)
  * English sentences inside Persian replies (defect 2)
  * replies that hit the token budget (defect 3: incomplete)
and, per row, every grading regression and improvement, so a style rule
that costs correctness is visible rather than averaged away.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(os.path.dirname(HERE), "src"), HERE]

from llm import style as ST                      # noqa: E402
import compare_quants as CQ                      # noqa: E402


def _raw(r):
    """The model's own final text, before the harness's LaTeX rewrite."""
    m = r.get("metrics") or {}
    m = m.get("second_turn") or m
    return m.get("raw_output") if m.get("raw_output") is not None else (r.get("output") or "")


def _ct(r):
    m = r.get("metrics") or {}
    return (m.get("second_turn") or m).get("completion_tokens")


def defects(run):
    mt = (run.get("model") or {}).get("max_tokens")
    out = {"latex_in_model_text": [], "latex_shown_to_user": [], "latin_runs_fa": [],
           "hit_budget": [], "n": 0}
    for arm, rows in sorted((run.get("arms") or {}).items()):
        for r in rows:
            out["n"] += 1
            key = "%s/%s" % (arm, r["id"])
            if ST.has_latex(_raw(r)):
                out["latex_in_model_text"].append(key)
            if ST.has_latex(r.get("output") or ""):
                out["latex_shown_to_user"].append(key)
            if r.get("lang") in ("fa", "mixed") and ST.latin_runs(r.get("output")):
                out["latin_runs_fa"].append(key)
            if ST.hit_budget(_ct(r), mt):
                out["hit_budget"].append(key)
    return out


def check_comparable(before, after):
    problems = []
    for name, run in (("before", before), ("after", after)):
        if not run.get("complete", False):
            problems.append("%s run is not complete" % name)
        if ((run.get("model") or {}).get("identity") or {}).get("label") != "VERIFIED":
            problems.append("%s weights are not VERIFIED" % name)
    ib = ((before.get("model") or {}).get("identity") or {}).get("sha256")
    ia = ((after.get("model") or {}).get("identity") or {}).get("sha256")
    if ib != ia:
        problems.append("weights differ: a style comparison needs the same weights")
    if (before.get("server") or {}).get("backend") != (after.get("server") or {}).get("backend"):
        problems.append("runtime differs: a style comparison needs the same runtime")
    pb = dict((before.get("model") or {}).get("prompt_options") or {})
    pa = dict((after.get("model") or {}).get("prompt_options") or {})
    if pb.pop("style", False) or not pa.pop("style", False):
        problems.append("expected BEFORE without style and AFTER with style")
    if pb != pa:
        problems.append("prompt options other than style differ: %r vs %r" % (pb, pa))
    for k in ("ctx", "threads", "max_tokens", "tool_call_cap"):
        if (before.get("model") or {}).get(k) != (after.get("model") or {}).get(k):
            problems.append("runs differ in %s" % k)
    ids = lambda run: {a: sorted(r["id"] for r in rows) for a, rows in (run.get("arms") or {}).items()}
    if ids(before) != ids(after):
        problems.append("runs differ in eval cases")
    return problems


def compare(before, after):
    problems = check_comparable(before, after)
    if problems:
        return {"label": "REFUSED", "problems": problems}
    regs, imps = [], []
    for arm in sorted(before["arms"]):
        rb = {r["id"]: r for r in before["arms"][arm]}
        ra = {r["id"]: r for r in after["arms"][arm]}
        for cid in sorted(rb):
            for f in CQ.ROW_FIELDS.get(arm, ()):
                vb, va = rb[cid].get(f), ra[cid].get(f)
                if vb is None or va is None or vb == va:
                    continue
                gb = (not vb) if f in CQ.BAD_WHEN_TRUE else bool(vb)
                ga = (not va) if f in CQ.BAD_WHEN_TRUE else bool(va)
                if arm == "rag" and f == "abstained":
                    want = not rb[cid].get("answerable", True)
                    gb, ga = (vb == want), (va == want)
                if gb == ga:
                    continue
                e = {"row": "%s/%s" % (arm, cid), "field": f, "before": vb, "after": va}
                (regs if gb and not ga else imps).append(e)
    db, da = defects(before), defects(after)
    return {"label": "COMPUTED_FROM_MEASURED", "kind": "STYLE (same weights, same runtime)",
            "defects_before": db, "defects_after": da,
            "defect_counts": {k: [len(db[k]), len(da[k])] for k in db if k != "n"},
            "regressions": regs, "improvements": imps,
            "verdict": ("NO ROW REGRESSED" if not regs else "%d ROW(S) REGRESSED" % len(regs))}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("before")
    ap.add_argument("after")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    res = compare(json.load(open(a.before, encoding="utf-8")),
                  json.load(open(a.after, encoding="utf-8")))
    res["sources"] = [os.path.basename(a.before), os.path.basename(a.after)]
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(res, f, indent=2, ensure_ascii=False)
    print(json.dumps({k: res.get(k) for k in ("label", "kind", "problems", "verdict",
                                              "defect_counts", "regressions", "improvements")
                      if k in res}, indent=1, ensure_ascii=False))
    return 0 if res["label"] != "REFUSED" else 2


if __name__ == "__main__":
    sys.exit(main())
