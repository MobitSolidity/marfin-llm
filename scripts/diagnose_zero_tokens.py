#!/usr/bin/env python3
"""
Prove -- or disprove -- that the chat template fixes the zero-token cases.

WHY THIS EXISTS
---------------
The 2026-08-30 run produced FOUR cases in which the model returned
completion_tokens=0 and raw_output="". They were originally assumed to be a
token-budget problem, and the plan of record was to re-run the whole rag arm at
a higher --max-tokens (~1.4 h MEASURED at 4.03 tok/s).

That plan was wrong, and the timing proved it. The four cases are, from
evidence/phase4_merged.json:

    rag::RAG-EN-005     430 prompt tok / 10.355 s -> 41.53 tok/s
    rag::RAG-FA-002     202 prompt tok /  4.862 s -> 41.55 tok/s
    rag::RAG-ABST-002   315 prompt tok /  7.509 s -> 41.95 tok/s
    tools::FA-ABST-001  525 prompt tok / 13.763 s -> 38.15 tok/s

Those rates are prefill throughput with ZERO decode steps. The model emitted
its end-of-turn token FIRST. No value of --max-tokens repairs a case that never
emitted a token; the diagnosis had to be the prompt, not the budget.

It was. Until 2026-08-31 the harness called the model as a raw text completion
with a prompt shaped "SYSTEM...\\n\\nQuestion: ...\\nAnswer:". Qwen3 is
instruction-tuned on ChatML and was never trained on that shape.

WHAT THIS SCRIPT DOES
---------------------
Runs ONLY those cases, and by default runs each one TWICE -- once with the
ChatML prompt the harness now builds, and once with the old raw-completion
prompt. That comparison is the entire point: a single passing run would show
the model answering, but not that the template is why. Same weights, same
budget, same machine, one variable.

COST: ~10 minutes, not the 1.4 hours a full rag re-run costs. MEASURED basis:
4.03 tok/s decode (mean of the 7 decode_tps values in the 2026-08-30 run), so
a 300-token answer is ~75 s. Six generations plus model load is well under 15
minutes even if every answer runs long.

WHAT IT DOES NOT DO
-------------------
It writes NO file that any grader or threshold reads, and it touches neither
PROJECT_STATE.json nor evidence/phase4_merged.json. It is a diagnostic, not a
measurement: its output cannot become a recorded result by accident. Deciding
what to re-run, and recording any verdict, stays a separate approved step.

USAGE (Windows PowerShell, from the project root)
    python scripts\\diagnose_zero_tokens.py --model C:\\models\\Qwen3.5-4B-Q5_K_M.gguf
"""
import argparse
import json
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "src"))
sys.path.insert(0, _HERE)

import phase4_lib as L  # noqa: E402
import run_phase4 as RP  # noqa: E402

CONSOLE_UTF8 = L.make_console_safe()

# The cases that produced zero tokens, with the arm each belongs to. Kept as
# data rather than rediscovered by scanning the evidence file: this script must
# run on a machine that has the weights, which is not necessarily a machine
# with a current checkout of the evidence.
ZERO_TOKEN_CASES = (
    ("rag", "RAG-EN-005"),
    ("rag", "RAG-FA-002"),
    ("rag", "RAG-ABST-002"),
)


def p(s=""):
    sys.stdout.write(str(s) + "\n")
    sys.stdout.flush()


def build_old_style_rag_prompt(question, passages):
    """
    The PRE-FIX prompt, reproduced verbatim for the comparison arm.

    This is a deliberate copy of the defective builder rather than a call into
    it: the fixed builder no longer produces this shape, and a comparison that
    silently used the new shape for both halves would report "no difference"
    and look like evidence that the template does not matter.
    """
    ev = []
    for i, ps in enumerate(passages, 1):
        ev.append("[%d] (%s) %s" % (i, ps.provenance.citation(), ps.text))
    return "%s\n\nEvidence:\n%s\n\nQuestion: %s\nAnswer:" % (
        RP.SYSTEM_RAG, "\n".join(ev) if ev else "(no evidence retrieved)",
        question)


def main():
    ap = argparse.ArgumentParser(
        description="Test whether the ChatML fix repairs the zero-token cases.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  # from the project root, Windows PowerShell
  python scripts\\diagnose_zero_tokens.py --model C:\\models\\Qwen3.5-4B-Q5_K_M.gguf

  # test only the ChatML side (faster, but does not prove WHY)
  python scripts\\diagnose_zero_tokens.py --model C:\\models\\Qwen3.5-4B-Q5_K_M.gguf --skip-old
""")
    ap.add_argument("--model", required=True, help="path to the GGUF file")
    ap.add_argument("--ctx", type=int, default=16384)
    ap.add_argument("--threads", type=int, default=6)
    # 512 is ample: a case that emits ANY token has already answered the
    # question this script asks. The budget is deliberately small so that the
    # diagnostic cannot quietly turn into an hours-long run.
    ap.add_argument("--max-tokens", type=int, default=512)
    ap.add_argument("--corpus",
                    default=os.path.join(_ROOT, "evals", "rag_corpus_v1.jsonl"))
    ap.add_argument("--gold",
                    default=os.path.join(_ROOT, "evals", "rag_gold_v1.jsonl"))
    ap.add_argument("--top-k", type=int, default=4)
    ap.add_argument("--skip-old", action="store_true",
                    help="do not run the old raw-completion prompt")
    ap.add_argument("--out", default=None,
                    help="optional path for a JSON copy of these results. "
                         "NOT read by any grader.")
    a = ap.parse_args()

    if not os.path.exists(a.model):
        raise SystemExit(
            "ERROR: model file not found: %s\n"
            "  (the path is resolved against %s)"
            % (a.model, os.getcwd()))

    p("=" * 70)
    p("ZERO-TOKEN DIAGNOSTIC")
    p("=" * 70)
    p("model      : %s" % a.model)
    p("max_tokens : %d   ctx: %d   threads: %d" % (a.max_tokens, a.ctx,
                                                   a.threads))
    p("cases      : %s" % ", ".join(i for _, i in ZERO_TOKEN_CASES))
    p("comparison : %s" % ("ChatML only" if a.skip_old
                           else "ChatML vs the old raw-completion prompt"))
    p("")
    p("This script does NOT write any file a grader reads, and does not")
    p("modify PROJECT_STATE.json or evidence/phase4_merged.json.")
    p("")

    gold_rows = RP.load_jsonl(a.gold)
    by_id = {}
    for g in gold_rows:
        by_id[g["id"]] = g
    wanted = [i for _, i in ZERO_TOKEN_CASES]
    missing = [i for i in wanted if i not in by_id]
    if missing:
        raise SystemExit("ERROR: gold file lacks these ids: %s"
                         % ", ".join(missing))

    index = RP.build_index(RP.load_jsonl(a.corpus))

    from llama_cpp import Llama
    t0 = time.time()
    llm = Llama(model_path=a.model, n_ctx=a.ctx, n_threads=a.threads,
                verbose=False)
    p("load time  : %.1f s  [MEASURED]" % (time.time() - t0))
    runner = RP.ModelRunner(llm, max_tokens=a.max_tokens)
    p("sampling   : temperature=%s seed=%s applied=%s"
      % (runner.temperature, runner.seed, runner.sampling_supported))
    p("")

    results = []
    for _arm, cid in ZERO_TOKEN_CASES:
        gold = by_id[cid]
        passages = list(index.search(gold["query"], top_k=a.top_k).hits)

        row = {"id": cid, "lang": gold.get("lang"),
               "answerable": gold.get("answerable"),
               "query": gold["query"]}

        p("-" * 70)
        p("%s  (%s, answerable=%s)" % (cid, gold.get("lang"),
                                       gold.get("answerable")))

        for label, prompt in (
                ("chatml", RP.build_rag_prompt(gold["query"], passages)),
                ("raw_completion",
                 build_old_style_rag_prompt(gold["query"], passages))):
            if label == "raw_completion" and a.skip_old:
                continue
            text, m = runner.generate(prompt)
            row[label] = {
                "completion_tokens": m["completion_tokens"],
                "seconds": m["seconds"],
                "decode_tps": m["decode_tps"],
                "answer_chars": len(text),
                "thinking_truncated": m["thinking_truncated"],
                "answer_preview": text[:300],
            }
            verdict = ("EMPTY  <-- still no output"
                       if m["completion_tokens"] == 0 else "PRODUCED OUTPUT")
            p("  %-15s tokens=%-5d %-7.1fs  %s"
              % (label, m["completion_tokens"], m["seconds"], verdict))
            if text.strip():
                p("      %s" % text.strip()[:200].replace("\n", " "))

        results.append(row)
        p("")

    # ---- the verdict, stated as a comparison rather than as a pass/fail ----
    p("=" * 70)
    p("SUMMARY  [MEASURED]")
    p("=" * 70)
    fixed = [r for r in results
             if r.get("chatml", {}).get("completion_tokens", 0) > 0]
    still = [r for r in results
             if r.get("chatml", {}).get("completion_tokens", 0) == 0]
    p("with ChatML, produced output : %d of %d  %s"
      % (len(fixed), len(results), [r["id"] for r in fixed]))
    p("with ChatML, STILL empty     : %d of %d  %s"
      % (len(still), len(results), [r["id"] for r in still]))

    if not a.skip_old:
        old_empty = [r["id"] for r in results
                     if r.get("raw_completion", {})
                          .get("completion_tokens", 0) == 0]
        p("with the OLD prompt, empty   : %d of %d  %s"
          % (len(old_empty), len(results), old_empty))
        p("")
        # BRANCH ORDER IS LOAD-BEARING. My first version tested
        # `len(fixed) > len(old_empty)` before `not old_empty`, which made the
        # "old prompt also worked" case UNREACHABLE: with 3 fixed and 0 old
        # empties, 3 > 0 caught first and the script reported "the template
        # helps but does not explain every case" -- the opposite of the truth,
        # in the one scenario where the whole diagnosis is unproven. Caught by
        # dry-running all four scenarios against a fake model, 2026-08-31.
        # The reproducibility check therefore comes FIRST.
        if not old_empty:
            p("READING: the old prompt ALSO produced output this time, so this")
            p("run does NOT reproduce the 2026-08-30 emptiness and cannot")
            p("attribute it to the prompt shape. Most likely cause: that run's")
            p("seed was random and unrecorded. The template fix is still")
            p("correct, but it is not proven to be THE cause here.")
        elif len(fixed) == len(results) and len(old_empty) == len(results):
            p("READING: the template was the cause. Same weights, same budget,")
            p("same machine -- only the prompt shape differed.")
        elif len(fixed) > len(old_empty):
            p("READING: the template helps but does not explain every case.")
            p("The cases still empty need their own diagnosis.")
        else:
            p("READING: the template did not fix these. Do NOT spend hours on")
            p("a re-run; the cause is still unidentified.")
    p("")
    p("NOTE: this is a DIAGNOSTIC. No threshold has been evaluated and no")
    p("measurement has been recorded. phase_4/measurements_recorded is")
    p("untouched.")

    if a.out:
        payload = {"label": "DIAGNOSTIC_NOT_A_MEASUREMENT",
                   "purpose": "zero-token cause isolation",
                   "not_read_by_graders": True,
                   "model_file": os.path.basename(a.model),
                   "max_tokens": a.max_tokens,
                   "sampling": {"temperature": runner.temperature,
                                "seed": runner.seed,
                                "applied": runner.sampling_supported},
                   "cases": results}
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        p("wrote %s" % a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
