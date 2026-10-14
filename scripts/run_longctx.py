#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 6 long-context test (SS.24 Phase 6 "Long-context tests"; SS.20.4
"2K / 8K / 16K context", "Long-context degradation"). D-0116.

WHAT IT MEASURES
----------------
One true figure (the NEEDLE) is buried in a RAG-style evidence block padded with
financially-flavoured filler to about 2K, 8K, and 14K prompt tokens, at three
depths (10 %, 50 %, 90 %). Every prompt ALSO carries a DECOY: the same concept
for a different fiscal year with a different value. That way "found a number" and
"found the right number" cannot be confused. This is the period-confusion failure
SS.20.2 names, made harder by distance.

Graded by phase4_lib.value_matches (the Phase 4 grader, unchanged), plus a
decoy check. A reply that states the decoy's value is a PERIOD_CONFUSION, not
a miss.

14K, not 16K: the model's ctx is 16384 and the reply needs room. A prompt
that does not fit would be truncated silently by the runtime, and its result
would describe the truncation, not the model.

RUN (the i5-12400; this sandbox cannot load the model):

    python scripts/run_longctx.py --model C:\\models\\Qwen3.5-4B-Q5_K_M.gguf \\
        --out evals/results/p6_longctx.json

Without --model, `--dry-run` builds and checks every prompt and exits, so the
instrument itself is testable here.

Stdlib + llama-cpp-python (for the real run only).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "src"))
sys.path.insert(0, _HERE)

import phase4_lib as L                                       # noqa: E402
import run_phase4 as RP                                      # noqa: E402

#: The needle: Microsoft FY2023 total revenue, as in the combined corpus
#: (FIX-MSFT-10K-2023: "Total revenue | 211,915", figures in million).
NEEDLE = ("[N] (SEC 10-K, Microsoft Corporation, fiscal year ended 2023-06-30) "
          "[entity: Microsoft Corporation] [figures in million] "
          "Total revenue | 211,915 -- Operating income | 88,523")
#: The decoy: same concept and entity, a DIFFERENT fiscal year and value.
#: FY2022 total revenue was 198,270 million (Microsoft 10-K FY2023 comparative).
DECOY = ("[D] (SEC 10-K, Microsoft Corporation, fiscal year ended 2022-06-30) "
         "[entity: Microsoft Corporation] [figures in million] "
         "Total revenue | 198,270 -- Operating income | 83,383")
QUESTION = ("What was Microsoft's total revenue for the fiscal year ended "
            "June 30, 2023? Answer with the figure and its unit.")
EXPECTED = 211915e6
DECOY_VALUE = 198270e6
TOL = max(EXPECTED * 1e-6, 0.5)     # grade_rag_case's own rule

#: Filler: governance and risk-factor prose with NO figures for Microsoft, and
#: no other revenue number, so the only two candidate answers are N and D.
FILLER = (
    "[F] (SEC 10-K, risk factors) The Company faces competition across its "
    "markets, and changes in technology, regulation, and customer preferences "
    "could adversely affect results. Cybersecurity incidents could disrupt "
    "operations. Supply chain concentration may affect product availability. "
    "Management reviews these risks with the Board at least annually. ")

TARGETS = (2048, 8192, 14336)
DEPTHS = (0.10, 0.50, 0.90)


def build_prompt(n_filler, depth, decoy_first=True):
    """Evidence block with the needle at `depth` of `n_filler` filler blocks."""
    blocks = [FILLER.strip()] * n_filler
    at = int(round(depth * n_filler))
    blocks.insert(at, NEEDLE)
    # The decoy goes at the OPPOSITE end, so recency or primacy alone cannot
    # pick the right one.
    if decoy_first:
        blocks.insert(0 if depth >= 0.5 else len(blocks), DECOY)
    user = "Evidence:\n%s\n\nQuestion: %s" % ("\n".join(blocks), QUESTION)
    return RP._prompt(RP.SYSTEM_RAG, user)


def fit_filler(target, counter):
    """Smallest n_filler whose full prompt reaches `target` tokens (counter: str->int)."""
    lo, hi = 1, 4096
    while lo < hi:
        mid = (lo + hi) // 2
        if counter(str(build_prompt(mid, 0.5))) >= target:
            hi = mid
        else:
            lo = mid + 1
    return lo


def char_counter(text):
    """ESTIMATE used only when no tokenizer is available (dry run): ~3.6 chars/token."""
    return int(len(text) / 3.6)


def grade(answer):
    found = L.value_matches(EXPECTED, answer, TOL, scaled=True)
    decoy = L.value_matches(DECOY_VALUE, answer, max(DECOY_VALUE * 1e-6, 0.5),
                            scaled=True)
    if found and not decoy:
        outcome = "OK"
    elif decoy and not found:
        outcome = "PERIOD_CONFUSION"
    elif found and decoy:
        outcome = "BOTH_STATED"
    elif L.is_abstention(answer):
        outcome = "OVER_ABSTENTION"
    else:
        outcome = "MISS"
    return {"value_ok": found, "stated_decoy": decoy, "outcome": outcome}


def plan(counter, how):
    rows = []
    for t in TARGETS:
        n = fit_filler(t, counter)
        for d in DEPTHS:
            p = build_prompt(n, d)
            rows.append({"target_tokens": t, "depth": d, "n_filler": n,
                         "prompt_tokens": counter(str(p)), "counted_by": how,
                         "prompt": p})
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description="Phase 6 long-context needle test")
    ap.add_argument("--model")
    ap.add_argument("--ctx", type=int, default=16384)
    ap.add_argument("--threads", type=int, default=6)
    ap.add_argument("--max-tokens", type=int, default=RP.DEFAULT_MAX_TOKENS)
    ap.add_argument("--out", default="evals/results/p6_longctx.json")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    if a.dry_run or not a.model:
        rows = plan(char_counter, "ESTIMATED_chars")
        for r in rows:
            s = str(r["prompt"])
            print("target %5d depth %.2f  n_filler %4d  ~%5d tok  im_end=%d  "
                  "needle=%s decoy=%s" % (r["target_tokens"], r["depth"],
                                          r["n_filler"], r["prompt_tokens"],
                                          s.count(RP.IM_END), NEEDLE in s, DECOY in s))
        print("dry run: %d prompts built; no model loaded" % len(rows))
        return 0

    from llama_cpp import Llama
    ident = L.identify_model(a.model)
    t0 = time.time()
    llm = Llama(model_path=a.model, n_ctx=a.ctx, n_threads=a.threads, verbose=False)
    load_s = round(time.time() - t0, 2)
    counter = RP._token_counter_for(llm)
    how = "tokenized" if counter else "ESTIMATED_chars"
    counter = counter or char_counter
    runner = RP.ModelRunner(llm, max_tokens=a.max_tokens)
    rows = plan(counter, how)
    out = []
    for r in rows:
        if r["prompt_tokens"] + a.max_tokens > a.ctx:
            out.append(dict({k: v for k, v in r.items() if k != "prompt"},
                            outcome="NOT_RUN_WOULD_TRUNCATE"))
            continue
        ans, m = runner.generate(r["prompt"])
        g = grade(ans)
        row = {k: v for k, v in r.items() if k != "prompt"}
        row.update(g, output=ans, metrics={k: m.get(k) for k in
                                           ("seconds", "prompt_tokens",
                                            "completion_tokens", "decode_tps")})
        out.append(row)
        print("%5d tok depth %.2f -> %s (%.1fs)" % (r["prompt_tokens"], r["depth"],
                                                    g["outcome"], m.get("seconds", 0)))
    by = {}
    for r in out:
        by.setdefault(str(r["target_tokens"]), []).append(r.get("outcome"))
    payload = {"label": "MEASURED", "phase": "6", "test": "long_context_needle",
               "model": {"file": os.path.basename(a.model), "identity": ident,
                         "ctx": a.ctx, "threads": a.threads,
                         "max_tokens": a.max_tokens, "load_seconds": load_s},
               "counted_by": how, "rows": out,
               "summary": {t: {"n": len(v), "ok": v.count("OK"),
                               "period_confusion": v.count("PERIOD_CONFUSION")}
                           for t, v in by.items()}}
    L.ensure_parent_dir(a.out)
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
    print("written: %s" % a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
