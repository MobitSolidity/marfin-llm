# -*- coding: utf-8 -*-
"""
D-0125: the answer-style fixes as a DISPLAY LAYER, not as prompt rules.

Two Phase 8 runs (D-0124, D-0125) MEASURED that putting the style rules in the
system prompt fixes the user's three defects but costs accuracy: deterministic
calc 100 -> 87.5 -> 62.5 (plain), tool calls where expected 8/10 -> 2/10 -> 4/10,
12 and then 15 row regressions. The same runs MEASURED that the deterministic
rewrite (style.plain_math) alone removes every LaTeX span and changes no grade.

So this applies ONLY the deterministic part to a RECORDED run whose prompts had
no style rules: the model's text is kept in `output_model`, the user-facing
`output` is the rewritten text, and the prose grading fields are recomputed from
it. Numbers are never altered by plain_math (pinned in tests/test_phase8.py).

Because in-process greedy runs reproduce byte-for-byte (D-0122: 21/21 plain,
32/32 rag), applying this to the Phase 7 Q4_K_M run gives exactly what a live
run with the display layer would produce. The model is NOT re-run.

    python3 scripts/apply_display_layer.py RUN.json --out RUN_display.json
"""
import argparse
import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

import phase4_lib as L                              # noqa: E402
from llm import style as ST                         # noqa: E402
from regrade_eval import GRADING_FIELDS, RAG_GRADING_FIELDS, _schemas_by_name  # noqa: E402


def _ct(metrics):
    m = metrics or {}
    m = m.get("second_turn") or m
    return m.get("completion_tokens")


def apply(run, cases, rag_gold, schemas_by_name=None):
    """(new_run, report). Refuses a run whose prompts already carried style rules."""
    if ((run.get("model") or {}).get("prompt_options") or {}).get("style"):
        raise ValueError("this run's prompts already carried the style rules; the "
                         "display layer is for runs WITHOUT them")
    schemas_by_name = schemas_by_name or _schemas_by_name()
    new = copy.deepcopy(run)
    mt = (run.get("model") or {}).get("max_tokens")
    report = {"rows_rewritten": [], "grade_changes": [], "latex_left": [],
              "latin_runs_fa": [], "hit_budget": []}
    for arm, rows in sorted((new.get("arms") or {}).items()):
        for r in rows:
            key = "%s/%s" % (arm, r["id"])
            text = r.get("output") or ""
            shown, n = ST.plain_math(text)
            lr = ST.latin_runs(shown) if r.get("lang") in ("fa", "mixed") else None
            hb = ST.hit_budget(_ct(r.get("metrics")), mt)
            r["display"] = {"latex_spans_rewritten": n, "latin_runs": lr, "hit_budget": hb}
            if lr:
                report["latin_runs_fa"].append(key)
            if hb:
                report["hit_budget"].append(key)
            if ST.has_latex(shown):
                report["latex_left"].append(key)
            if not n:
                continue
            report["rows_rewritten"].append(key)
            r["output_model"] = text
            r["output"] = shown
            if arm in ("plain", "tools"):
                g = L.grade_case(cases[r["id"]], shown, schemas_by_name)
                fields = GRADING_FIELDS
            else:
                g = L.grade_rag_case(rag_gold[r["id"]], shown, r.get("retrieved"),
                                     r.get("citations"))
                fields = RAG_GRADING_FIELDS
            for k in fields:
                if k in g and r.get(k) != g[k]:
                    report["grade_changes"].append((key, k, r.get(k), g[k]))
                    r[k] = g[k]
    for arm in ("plain", "tools"):
        if (new.get("arms") or {}).get(arm):
            new["summaries"][arm] = L.summarize_eval(new["arms"][arm])
    if (new.get("arms") or {}).get("rag"):
        new["summaries"]["rag"] = L.summarize_rag(new["arms"]["rag"])
    new["label"] = "RECOMPUTED_FROM_RECORDED_OUTPUT_DISPLAY_LAYER"
    new["display_layer"] = {"by": "scripts/apply_display_layer.py", "decision": "D-0125",
                            "from_label": run.get("label"), "model_re_run": False,
                            "prompt_changed": False,
                            "rows_rewritten": len(report["rows_rewritten"]),
                            "grade_changes": len(report["grade_changes"])}
    new.pop("threshold_verdicts", None)
    return new, report


def _load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("run")
    ap.add_argument("--eval", default=os.path.join(ROOT, "evals", "bilingual_eval_v1.jsonl"))
    ap.add_argument("--rag-gold", default=os.path.join(ROOT, "evals", "rag_gold_combined.jsonl"))
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    run = json.load(open(a.run, encoding="utf-8"))
    cases = {c["id"]: c for c in _load_jsonl(a.eval)}
    gold = {g["id"]: g for g in _load_jsonl(a.rag_gold)}
    new, rep = apply(run, cases, gold)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(new, f, ensure_ascii=False, indent=2)
    print("rows rewritten : %d %s" % (len(rep["rows_rewritten"]), rep["rows_rewritten"]))
    print("grade changes  : %d %s" % (len(rep["grade_changes"]), rep["grade_changes"]))
    print("LaTeX left     : %d" % len(rep["latex_left"]))
    print("latin runs (fa): %s" % rep["latin_runs_fa"])
    print("hit budget     : %s" % rep["hit_budget"])
    print("written: %s" % a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
