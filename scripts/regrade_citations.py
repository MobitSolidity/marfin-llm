"""
Re-compute the CITATION metrics of a recorded run with the CURRENT grader.

WHY THIS IS NECESSARY, AND WHY IT IS NOT CHEATING
-------------------------------------------------
The run of 2026-09-03 was graded by a citation verifier that had two defects
(D-0092): it applied no masking at all, and its year pattern was ASCII-only.
MEASURED consequence: 8 of the 12 graded claims were checked against a citation
marker or a year rather than a magnitude, producing details such as

    claimed 2 does not appear in the evidence; nearest is 1.69148e+11

against answers that were CORRECT. So `citation_correctness_pct 25.0` and
`unsupported_claim_rate_pct 75.0` in that file are artefacts of the grader, not
measurements of the model.

Grading the fixed metric is therefore not a softening of the result. It is the
difference between measuring the model and measuring a bug. The distinction
that keeps it honest:

  * THE MODEL'S OUTPUT IS NOT RE-GENERATED. Every answer text comes from the
    recorded file, byte for byte. No model runs.
  * THE EVIDENCE IS REBUILT WITH THE RUNNER'S OWN build_index, so each answer
    is checked against the passages the model actually saw -- not against the
    gold passage, which would measure the gold set instead of the model.
  * THE VERDICT LOGIC IS THE RUNNER'S, copied in shape from run_arm_rag: one
    SUPPORTED passage grounds one claim; any CONTRADICTED claim decides the
    answer.
  * THE OUTPUT IS LABELLED RECOMPUTED_FROM_RECORDED_OUTPUT, never MEASURED,
    because the number did not come out of a run.

WHAT IT CANNOT REPAIR
---------------------
Only the two citation metrics are recomputed. Decode rate, TTFT, RSS,
abstention and fabrication are properties of the run itself and are left
exactly as recorded -- including the FAILs. A script that "recomputed" those
would be laundering the result.

Stdlib only.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for _p in (os.path.join(ROOT, "src"), HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import phase4_lib as L                                       # noqa: E402
from rag.citations import verify_claim                       # noqa: E402


def _load_runner():
    spec = importlib.util.spec_from_file_location(
        "run_phase4", os.path.join(HERE, "run_phase4.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def regrade(run, corpus_path, gold_path, top_k):
    RP = _load_runner()
    index = RP.build_index(RP.load_jsonl(corpus_path))
    gold = {g["id"]: g for g in RP.load_jsonl(gold_path)}

    rows = []
    for r in run["arms"]["rag"]:
        cid = r["id"]
        text = r.get("output") or ""
        g = gold[cid]
        passages = list(index.search(g["query"], top_k=top_k).hits)

        claims = L.split_claims(text)
        per_claim = []
        if text.strip() and not L.is_abstention(text) and claims:
            for claim in claims:
                stats = [verify_claim(claim, ps).status for ps in passages]
                if "SUPPORTED" in stats:
                    per_claim.append("SUPPORTED")
                elif "CONTRADICTED" in stats:
                    per_claim.append("CONTRADICTED")
                else:
                    per_claim.append("UNSUPPORTED")
            if "CONTRADICTED" in per_claim:
                status = "CONTRADICTED"
            elif all(s == "SUPPORTED" for s in per_claim):
                status = "SUPPORTED"
            elif "SUPPORTED" in per_claim:
                status = "PARTIALLY_SUPPORTED"
            else:
                status = "UNSUPPORTED"
        else:
            status = "NOT_CHECKED"

        old = r.get("citations") or []
        old_status = (old[0].get("status") if old and isinstance(old[0], dict)
                      else None) or "NOT_CHECKED"
        rows.append({"id": cid, "old": old_status, "new": status,
                     "n_claims": len(per_claim),
                     "per_claim": per_claim})
    return rows


def summarise(rows):
    checked = [r for r in rows if r["new"] != "NOT_CHECKED"]
    n = len(checked)
    supported = sum(1 for r in checked if r["new"] == "SUPPORTED")
    # unsupported_claim_rate is over CLAIMS, not answers: an answer with three
    # claims and one bad claim is not "one third unsupported".
    all_claims = [s for r in rows for s in r["per_claim"]]
    bad = [s for s in all_claims if s != "SUPPORTED"]
    return {
        "answers_checked": n,
        "answers_supported": supported,
        "citation_correctness_pct": (round(100.0 * supported / n, 2)
                                     if n else None),
        "claims_checked": len(all_claims),
        "claims_not_supported": len(bad),
        "unsupported_claim_rate_pct": (round(100.0 * len(bad) / len(all_claims), 2)
                                       if all_claims else None),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Recompute citation metrics of a recorded run with the "
                    "current grader. The model is NOT re-run.")
    ap.add_argument("run")
    ap.add_argument("--corpus", default=os.path.join(ROOT, "evals",
                                                     "rag_corpus_v1.jsonl"))
    ap.add_argument("--gold", default=os.path.join(ROOT, "evals",
                                                   "rag_gold_v1.jsonl"))
    ap.add_argument("--top-k", type=int, default=4)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)

    run = json.load(open(a.run, encoding="utf-8"))
    rows = regrade(run, a.corpus, a.gold, a.top_k)
    summ = summarise(rows)

    p = print
    p("=" * 78)
    p("RECOMPUTED CITATION VERDICTS -- model NOT re-run")
    p("=" * 78)
    for r in rows:
        flag = "  <== CHANGED" if r["old"] != r["new"] else ""
        p("  %-14s old=%-20s new=%-20s claims=%d%s"
          % (r["id"], r["old"], r["new"], r["n_claims"], flag))
    p("")
    for k, v in summ.items():
        p("  %-32s %s" % (k, v))

    old_reported = {}
    for arm, s in (run.get("summaries") or {}).items():
        for k in ("citation_correctness_pct", "unsupported_claim_rate_pct"):
            if s.get(k) is not None:
                old_reported["%s.%s" % (arm, k)] = s[k]
    p("")
    p("  as RECORDED by the defective grader: %s"
      % json.dumps(old_reported, sort_keys=True))

    payload = {
        "label": "RECOMPUTED_FROM_RECORDED_OUTPUT",
        "computed_by": "scripts/regrade_citations.py",
        "run_file": os.path.basename(a.run),
        "model_re_run": False,
        "grader_fix": "D-0092",
        "top_k": a.top_k,
        "rows": rows,
        "summary": summ,
        "as_recorded_by_defective_grader": old_reported,
        "scope_limit": ("ONLY the two citation metrics are recomputed. "
                        "Decode rate, TTFT, RSS, abstention and fabrication "
                        "are properties of the run and are left as recorded, "
                        "including their FAILs."),
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
