#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Merge the v1 and v2 RAG fixtures into ONE corpus and ONE gold file.

WHY THIS EXISTS
---------------
`scripts/run_phase4.py` takes a single `--corpus` and a single `--gold`.
D-0096 sized the v2 set so that the COMBINED v1+v2 totals reach the R49
resolution targets:

    citation_correctness_pct_min  needs n >= 20 answerable | v2 alone 15 MISS
    correct_abstention_pct_min    needs n >= 10 abstain    | v2 alone  7 MISS
                                            combined 22 / 10  -> both reached

So running v2 ALONE does not achieve what D-0096 was for. The sets have to be
merged, and merging two independently-validated fixtures is not free.

WHAT MERGING BROKE, MEASURED
----------------------------
Each set retrieves 100% of its own gold documents in isolation. Combined, 3 of
22 answerable questions failed to retrieve their gold document. Three distinct
causes, and they must NOT be treated alike:

  1. RAG2-FA-001 / RAG2-FA-002 -- MY DEFECT, fixed in build_eval_v2.py.
     The Persian questions accepted only the ENGLISH document. They passed v2
     validation solely because that English doc scraped into top_k at rank 4
     of 4; v1's documents took the slot and they flipped to MISS. v1 already
     had this right (RAG-FA-001 accepts both the -FA doc and its twin).
     A pass that depends on one ranking position was never a pass.

  2. RAG-EN-002 -- A DUPLICATE created by the merge, repaired HERE.
     FIX-AAPL-10K-2023 (v1, synthetic) and SEC-AAPL-10K-FY2023 (v2, real SEC
     data) state the SAME fact: Apple FY2023 net income 96,995 million. A model
     that retrieves the v2 document and quotes 96,995 is exactly right, so
     scoring it a retrieval miss measures the fixture and not the model. This
     script therefore lets such a question accept EITHER document -- but only
     after PROVING the two agree on the gold magnitude. If they disagree the
     merge ABORTS, because then it is a contradiction, not a duplicate.

  3. RAG-EN-003 -- A REAL RESULT, deliberately LEFT BROKEN.
     Microsoft FY2023 is outranked by the FY2024 and FY2025 filings that v2
     adds. Nothing about the fixture is wrong: the corpus simply now contains
     near neighbours, which is what a harder retrieval task looks like. The
     honest thing is to let it fail and report it. Repairing this one would be
     tuning the eval until it flatters the system -- the same move as relaxing
     a threshold after seeing the numbers, which was already refused in R49.

This script prints every collision it finds and writes a manifest recording
them, so the run's results can never be read without them.
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Questions whose gold document is duplicated by the other set. Listed
# EXPLICITLY -- never auto-detected -- so that adding a duplicate silently
# cannot silently widen what counts as a correct retrieval.
KNOWN_DUPLICATES = {
    "RAG-EN-002": ["SEC-AAPL-10K-FY2023"],
}

# Questions known to fail retrieval in the combined corpus and deliberately
# NOT repaired. Recorded so the failure is expected and explained rather than
# discovered later and rationalised.
ACCEPTED_REGRESSIONS = {
    "RAG-EN-003": (
        "Microsoft FY2023 is outranked by the FY2024/FY2025 filings v2 adds. "
        "A genuine retrieval degradation from near-neighbour distractors, not "
        "a fixture defect. Left failing on purpose."
    ),
}


def rows(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def write(path, items):
    with open(path, "w", encoding="utf-8") as fh:
        for it in items:
            fh.write(json.dumps(it, ensure_ascii=False) + "\n")


def main():
    ev = os.path.join(ROOT, "evals")
    c1 = rows(os.path.join(ev, "rag_corpus_v1.jsonl"))
    c2 = rows(os.path.join(ev, "rag_corpus_v2.jsonl"))
    g1 = rows(os.path.join(ev, "rag_gold_v1.jsonl"))
    g2 = rows(os.path.join(ev, "rag_gold_v2.jsonl"))

    print("INPUTS")
    print("  v1: %2d corpus rows, %2d gold rows" % (len(c1), len(g1)))
    print("  v2: %2d corpus rows, %2d gold rows" % (len(c2), len(g2)))

    # --- doc_id collisions would make one document shadow another ---
    d1 = set(r["doc_id"] for r in c1)
    d2 = set(r["doc_id"] for r in c2)
    clash = sorted(d1 & d2)
    if clash:
        print("ABORT: doc_id present in BOTH corpora: %s" % clash)
        return 1

    ids1 = set(r["id"] for r in g1)
    ids2 = set(r["id"] for r in g2)
    clash = sorted(ids1 & ids2)
    if clash:
        print("ABORT: gold id present in BOTH sets: %s" % clash)
        return 1

    corpus = c1 + c2
    by_id = {r["id"]: r for r in g1 + g2}

    # --- widen the duplicated questions, but only on PROOF of agreement ---
    mags = {}
    for r in corpus:
        pass
    gold = []
    for r in g1 + g2:
        r = dict(r)
        extra = KNOWN_DUPLICATES.get(r["id"])
        if extra:
            known = set(r["gold_doc_ids"])
            for doc in extra:
                if doc in known:
                    continue
                # PROVE the duplicate states the same magnitude before
                # accepting it. A "duplicate" that disagrees is a
                # contradiction and must stop the build.
                texts = [x["text"] for x in corpus if x["doc_id"] == doc]
                if not texts:
                    print("ABORT: %s names unknown doc %s" % (r["id"], doc))
                    return 1
                want = r.get("gold_magnitude")
                if want is None:
                    print("ABORT: %s has no gold_magnitude to verify against"
                          % r["id"])
                    return 1
                millions = "{:,}".format(int(round(want / 1e6)))
                if not any(millions in t for t in texts):
                    print("ABORT: %s claims %s duplicates its gold, but %s "
                          "does not contain %s"
                          % (r["id"], doc, doc, millions))
                    return 1
                r["gold_doc_ids"] = list(r["gold_doc_ids"]) + [doc]
                print("  duplicate VERIFIED: %s may also cite %s (both state "
                      "%s million)" % (r["id"], doc, millions))
        gold.append(r)

    ans = sum(1 for r in gold if r["answerable"] is True)
    abst = len(gold) - ans
    print()
    print("COMBINED: %d corpus rows, %d gold rows (%d answerable, %d abstain)"
          % (len(corpus), len(gold), ans, abst))
    print("  citation_correctness_pct_min  needs n>=20 answerable: %d %s"
          % (ans, "OK" if ans >= 20 else "SHORT"))
    print("  correct_abstention_pct_min    needs n>=10 abstain   : %d %s"
          % (abst, "OK" if abst >= 10 else "SHORT"))

    cpath = os.path.join(ev, "rag_corpus_combined.jsonl")
    gpath = os.path.join(ev, "rag_gold_combined.jsonl")
    write(cpath, corpus)
    write(gpath, gold)

    manifest = {
        "label": "GENERATED_BY_build_combined_eval.py",
        "inputs": ["rag_corpus_v1.jsonl", "rag_corpus_v2.jsonl",
                   "rag_gold_v1.jsonl", "rag_gold_v2.jsonl"],
        "corpus_rows": len(corpus),
        "gold_rows": len(gold),
        "answerable": ans,
        "abstain": abst,
        "duplicates_widened": KNOWN_DUPLICATES,
        "accepted_regressions": ACCEPTED_REGRESSIONS,
        "accepted_regressions_note":
            "These questions are EXPECTED to fail retrieval in the combined "
            "corpus. They are not repaired, because repairing them would tune "
            "the eval until it flatters the system.",
    }
    mpath = os.path.join(ev, "rag_combined_manifest.json")
    with open(mpath, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    print()
    print("wrote %s" % os.path.relpath(cpath, ROOT))
    print("wrote %s" % os.path.relpath(gpath, ROOT))
    print("wrote %s" % os.path.relpath(mpath, ROOT))
    print()
    print("DELIBERATELY LEFT FAILING (%d):" % len(ACCEPTED_REGRESSIONS))
    for k, v in sorted(ACCEPTED_REGRESSIONS.items()):
        print("  %s: %s" % (k, v))
    return 0


if __name__ == "__main__":
    sys.exit(main())
