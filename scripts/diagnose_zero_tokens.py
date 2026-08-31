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

COST -- CORRECTED 2026-08-31 AFTER THE FIRST REAL RUN
-----------------------------------------------------
The first version claimed "~10 minutes" on a 512-token budget and a carried-
over 4.03 tok/s. Both numbers were wrong in the same direction:

  * MEASURED on the i5-12400: 3.32 tok/s, not 4.03 (17.5% slower).
  * 512 tokens was not enough for ANY of the three cases to finish. All six
    generations returned exactly 512 tokens with no visible answer -- each one
    still inside its <think> block. The run cost 15.4 minutes and could not
    discriminate between the two prompt shapes in either direction.

The default budget is now 3072, chosen because the 2026-08-30 rag arm's
truncated cases used ~2031, ~2636 and ~2510 reasoning tokens. At 3.32 tok/s
that is ~15 min per generation: ~46 min with --skip-old, ~92 min for the full
comparison. The script prints this projection before loading the weights and
refuses to start above 20 projected minutes without --yes.

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

# MEASURED 2026-08-31 on the user's i5-12400: six generations of exactly 512
# tokens took 157.4 / 157.9 / 151.1 / 151.0 / 154.0 / 153.2 s, i.e. 3.24-3.39
# tok/s, mean 3.32. That REPLACES the 4.03 tok/s carried over from 2026-08-30
# as the basis for every cost figure this script prints: it is 17.5% slower,
# and quoting the older, friendlier number would understate every estimate.
MEASURED_DECODE_TPS = 3.32

# Above this projected wall-clock, the script refuses to start without --yes.
LONG_RUN_MINUTES = 20


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
  # ChatML side only, 3 generations, ~46 min PROJECTED at a MEASURED 3.32 tok/s
  python scripts\\diagnose_zero_tokens.py --model C:\\models\\Qwen3.5-4B-Q5_K_M.gguf --skip-old --yes

  # full comparison, 6 generations, ~92 min PROJECTED
  python scripts\\diagnose_zero_tokens.py --model C:\\models\\Qwen3.5-4B-Q5_K_M.gguf --yes

note:
  --max-tokens defaults to 3072. The earlier default of 512 was MEASURED to be
  too small: every reply was cut off inside its <think> block, so the run
  proved nothing. Do not lower it without reading the COST section above.
""")
    ap.add_argument("--model", required=True, help="path to the GGUF file")
    ap.add_argument("--ctx", type=int, default=16384)
    ap.add_argument("--threads", type=int, default=6)
    # THE FIRST DEFAULT (512) WAS WRONG, AND THE USER'S RUN PROVED IT.
    #
    # The reasoning was: "a case that emits ANY token has already answered the
    # question this script asks." That is false for a thinking model. MEASURED
    # 2026-08-31 on the i5-12400: all six generations returned exactly 512
    # tokens and NONE produced a visible answer -- every one was still inside
    # its <think> block when the budget ran out. The 2026-08-30 run's rag arm
    # shows why that was foreseeable: its truncated cases used ~2031, ~2636 and
    # ~2510 reasoning tokens. 512 was never going to be enough.
    #
    # 3072 is chosen from that MEASURED distribution: it exceeds the largest
    # observed reasoning block (~2636 tok) with room for an answer after it.
    # COST at the newly MEASURED 3.32 tok/s: ~15.4 min per generation, so
    # ~46 min for three cases with --skip-old, ~92 min for the full comparison.
    # That is no longer a "10-minute" diagnostic and must not be described as
    # one.
    ap.add_argument("--max-tokens", type=int, default=3072)
    ap.add_argument("--corpus",
                    default=os.path.join(_ROOT, "evals", "rag_corpus_v1.jsonl"))
    ap.add_argument("--gold",
                    default=os.path.join(_ROOT, "evals", "rag_gold_v1.jsonl"))
    ap.add_argument("--top-k", type=int, default=4)
    ap.add_argument("--skip-old", action="store_true",
                    help="do not run the old raw-completion prompt")
    ap.add_argument("--yes", action="store_true",
                    help="confirm a run whose PROJECTED cost exceeds "
                         "%d minutes. Required, because raising --max-tokens "
                         "silently turned a 15-minute script into a "
                         "90-minute one." % LONG_RUN_MINUTES)
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

    # ---- the cost gate ----------------------------------------------------
    # A diagnostic whose whole justification is "it is cheap" must state its
    # projected cost BEFORE loading the weights, and must refuse to run when
    # that projection stops being cheap. The 512-token version was described
    # as "~10 minutes"; it took 15.4 minutes of the user's evening and
    # answered nothing. The projection is ESTIMATED from a MEASURED rate --
    # both labels stated, neither dropped.
    n_gen = len(ZERO_TOKEN_CASES) * (1 if a.skip_old else 2)
    proj_min = n_gen * a.max_tokens / MEASURED_DECODE_TPS / 60.0
    p("projected  : %d generations x %d tok at %.2f tok/s (MEASURED "
      "2026-08-31)" % (n_gen, a.max_tokens, MEASURED_DECODE_TPS))
    p("             = ~%.0f minutes of wall clock  [ESTIMATED from a "
      "MEASURED rate]" % proj_min)
    p("             this is an UPPER bound: a reply that finishes early costs")
    p("             less. Nothing here is a recorded measurement.")
    p("")
    if proj_min > LONG_RUN_MINUTES and not a.yes:
        raise SystemExit(
            "REFUSING TO START: the projection above (~%.0f min) exceeds the "
            "%d-minute\n"
            "  threshold this script holds itself to. Re-run with --yes if "
            "you accept\n"
            "  that cost, or lower --max-tokens. (A smaller budget risks the "
            "2026-08-31\n"
            "  outcome: every reply cut off inside <think>, proving nothing.)"
            % (proj_min, LONG_RUN_MINUTES))

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
    # The budget the generations are bound by, kept in one name so the
    # at-ceiling test cannot drift away from the value actually passed.
    n_budget = a.max_tokens

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
        # Say how long the silence will last. At 3072 tokens and a MEASURED
        # 3.32 tok/s one generation is ~15 minutes with nothing printed, and a
        # long silence with no stated duration is indistinguishable from a hang
        # -- which invites the user to kill a run that is working.
        p("  (up to ~%.0f min per generation at %.2f tok/s; no output until it "
          "finishes)" % (a.max_tokens / MEASURED_DECODE_TPS / 60.0,
                         MEASURED_DECODE_TPS))

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
            # DEFECT FOUND 2026-08-31 BY THE USER'S OWN RUN, MEASURED.
            #
            # This label used to read `"PRODUCED OUTPUT" if
            # completion_tokens != 0`, and the whole summary was computed the
            # same way. On the real i5-12400 run all SIX generations returned
            # exactly tokens=512 -- the ceiling -- and not one of them printed
            # an answer preview, because the preview is guarded by
            # `if text.strip()`. So the visible answer was empty every time,
            # and every one of them was labelled PRODUCED OUTPUT.
            #
            # `completion_tokens > 0` is NOT the same fact as "answered". A
            # reply that spends its entire budget inside an unterminated
            # <think> block emits the maximum number of tokens and says
            # nothing: strip_thinking() correctly returns answer="" for it.
            # Conflating the two turned a run that could not discriminate
            # between the two prompt shapes into three lines reading as if it
            # had. Same hazard class as a test that cannot fail.
            #
            # The label is therefore derived from THREE facts -- tokens,
            # visible answer, and whether thinking was cut off -- and the
            # ceiling is reported, because ctok == max_tokens means the budget
            # bound the reply and the result says nothing about the prompt.
            row[label]["hit_ceiling"] = (m["completion_tokens"] >= n_budget)
            row[label]["answered"] = bool(text.strip())
            if m["completion_tokens"] == 0:
                verdict = "ZERO TOKENS  <-- reproduces the 2026-08-30 defect"
            elif text.strip():
                verdict = "ANSWERED (%d chars)" % len(text.strip())
            elif m["thinking_truncated"]:
                verdict = ("NO ANSWER -- unterminated <think>, budget "
                           "exhausted")
            else:
                verdict = "NO ANSWER -- tokens emitted, nothing visible"
            p("  %-15s tokens=%-5d %-7.1fs  %s%s"
              % (label, m["completion_tokens"], m["seconds"], verdict,
                 "  [AT CEILING]" if row[label]["hit_ceiling"] else ""))
            if text.strip():
                p("      %s" % text.strip()[:200].replace("\n", " "))
            else:
                # Print a slice of the REASONING when there is no answer. The
                # previous version printed nothing at all here, which is how a
                # run with six empty answers looked like a run with six good
                # ones.
                raw = (m.get("raw_output") or "").strip()
                p("      (no visible answer; reasoning %d chars) %s"
                  % (m["reasoning_chars"],
                     raw[:120].replace("\n", " ") if raw else ""))

        results.append(row)
        p("")

    # ---- the verdict, stated as a comparison rather than as a pass/fail ----
    p("=" * 70)
    p("SUMMARY  [MEASURED]")
    p("=" * 70)
    # Counted on the VISIBLE ANSWER, not on completion_tokens. See the defect
    # note at the per-case print.
    answered = [r for r in results if r.get("chatml", {}).get("answered")]
    zero = [r for r in results
            if r.get("chatml", {}).get("completion_tokens", 0) == 0]
    ceiling = [r for r in results
               if r.get("chatml", {}).get("hit_ceiling")
               and not r.get("chatml", {}).get("answered")]
    p("with ChatML, VISIBLE ANSWER  : %d of %d  %s"
      % (len(answered), len(results), [r["id"] for r in answered]))
    p("with ChatML, ZERO tokens     : %d of %d  %s"
      % (len(zero), len(results), [r["id"] for r in zero]))
    p("with ChatML, budget-bound    : %d of %d  %s"
      % (len(ceiling), len(results), [r["id"] for r in ceiling]))

    if not a.skip_old:
        # THE SAME DEFECT LIVES ON THIS SIDE TOO, AND A DRY-RUN CAUGHT IT.
        #
        # `old_empty` alone was keyed on completion_tokens, so the scenario
        # "ChatML answered all three; the old prompt burned its entire budget
        # inside <think> and said nothing" printed "the old prompt ALSO
        # produced output" -- i.e. the strongest possible evidence FOR the
        # template was reported as evidence that the run proves nothing.
        # Found 2026-08-31 by dry-running that exact scenario against a fake
        # model, AFTER fixing the ChatML side. Fixing one side of a comparison
        # and not the other leaves the comparison broken.
        old_empty = [r["id"] for r in results
                     if r.get("raw_completion", {})
                          .get("completion_tokens", 0) == 0]
        old_answered = [r["id"] for r in results
                        if r.get("raw_completion", {}).get("answered")]
        old_ceiling = [r["id"] for r in results
                       if r.get("raw_completion", {}).get("hit_ceiling")
                       and not r.get("raw_completion", {}).get("answered")]
        p("with the OLD prompt, ANSWER  : %d of %d  %s"
          % (len(old_answered), len(results), old_answered))
        p("with the OLD prompt, ZERO    : %d of %d  %s"
          % (len(old_empty), len(results), old_empty))
        p("with the OLD prompt, bound   : %d of %d  %s"
          % (len(old_ceiling), len(results), old_ceiling))
        p("")

        # INCONCLUSIVE IS A RESULT, AND IT MUST BE REPORTED FIRST.
        #
        # When every generation on BOTH sides was stopped by the token budget
        # and none of them produced a visible answer, the run compared nothing:
        # both arms were cut off at the same artificial bound before either had
        # a chance to finish. The 2026-08-31 run on the user's i5-12400 was
        # exactly this case, and the previous version of this block described
        # it as "the old prompt also produced output" -- true about tokens,
        # misleading about the comparison. So this branch precedes all others.
        both_all_bound = (len(ceiling) == len(results)
                          and len(old_ceiling) == len(results))
        if both_all_bound:
            p("READING: INCONCLUSIVE. Every generation on BOTH sides hit the")
            p("--max-tokens ceiling (%d) with no visible answer, i.e. each one"
              % n_budget)
            p("was still inside its <think> block when the budget ran out.")
            p("This run therefore cannot discriminate between the two prompt")
            p("shapes at all, in either direction. Re-run with a budget large")
            p("enough to let a reply finish before drawing any conclusion.")
            p("It also does NOT reproduce the 2026-08-30 zero-token cases,")
            p("which emitted 0 tokens in ~5-10 s, not %d tokens in ~150 s."
              % n_budget)
            p("")
        # BRANCH ORDER IS LOAD-BEARING. My first version tested
        # `len(fixed) > len(old_empty)` before `not old_empty`, which made the
        # "old prompt also worked" case UNREACHABLE: with 3 fixed and 0 old
        # empties, 3 > 0 caught first and the script reported "the template
        # helps but does not explain every case" -- the opposite of the truth,
        # in the one scenario where the whole diagnosis is unproven. Caught by
        # dry-running all four scenarios against a fake model, 2026-08-31.
        # The reproducibility check therefore comes FIRST.
        elif len(answered) == len(results) and not old_answered:
            p("READING: the template was the cause. Same weights, same budget,")
            p("same machine -- only the prompt shape differed, and only the")
            p("ChatML side produced a VISIBLE answer. (The old side failed by")
            p("%d zero-token and %d budget-bound generations.)"
              % (len(old_empty), len(old_ceiling)))
        elif len(old_answered) == len(results):
            p("READING: the old prompt ALSO produced visible answers this")
            p("time, so this run does NOT reproduce the 2026-08-30 emptiness")
            p("and cannot attribute it to the prompt shape. Most likely cause:")
            p("that run's seed was random and unrecorded. The template fix is")
            p("still correct, but it is not proven to be THE cause here.")
        elif len(answered) > len(old_answered):
            p("READING: the template helps but does not explain every case.")
            p("ChatML answered %d of %d against the old prompt's %d. The cases"
              % (len(answered), len(results), len(old_answered)))
            p("with no visible answer need their own diagnosis.")
        elif not answered:
            p("READING: the template did not fix these. Do NOT spend hours on")
            p("a re-run; the cause is still unidentified.")
        else:
            p("READING: MIXED and not attributable. ChatML answered %d of %d,"
              % (len(answered), len(results)))
            p("the old prompt %d of %d -- no clean separation. Treat this as"
              % (len(old_answered), len(results)))
            p("INCONCLUSIVE rather than as support for either shape.")
    else:
        # DEFECT FOUND 2026-08-31, BEFORE HANDING THE COMMAND OVER.
        #
        # All six READING branches lived inside `if not a.skip_old:`. So the
        # ONE mode I was about to recommend -- --skip-old, the 46-minute run --
        # was the only mode that printed no interpretation at all: a table of
        # numbers and nothing telling the reader what they mean. That is
        # precisely the state that made the user's 2026-08-31 run unreadable,
        # reintroduced through a different door. Caught by dry-running the mode
        # I was about to recommend, rather than the mode I had already tested.
        #
        # --skip-old cannot attribute a cause -- there is no comparison arm --
        # so these readings say what the run DOES establish and refuse to
        # overclaim.
        if len(answered) == len(results):
            p("READING: at this budget the model DOES produce a visible answer")
            p("on all %d cases. That establishes the cases are answerable with"
              % len(results))
            p("enough tokens, and that the 2026-08-30 emptiness is not a")
            p("permanent property of them. It does NOT identify the cause of")
            p("that emptiness: with --skip-old there is no comparison arm, so")
            p("no claim about the prompt shape can be made from this run.")
        elif not answered and len(ceiling) == len(results):
            p("READING: every generation hit the ceiling (%d tokens) with no"
              % n_budget)
            p("visible answer -- the model never finished thinking. This is a")
            p("REAL finding and an important one: raising the budget further is")
            p("unlikely to help, and a %d-case full re-run at this budget would"
              % 52)
            p("repeat this outcome %d times. Consider it evidence against"
              % 52)
            p("spending those hours, not evidence about the prompt shape.")
        elif zero:
            p("READING: %d of %d cases emitted ZERO tokens again, which DOES"
              % (len(zero), len(results)))
            p("reproduce the 2026-08-30 defect -- at a budget that rules out")
            p("the token limit as the explanation. Re-run WITHOUT --skip-old to")
            p("test the prompt shape against it.")
        else:
            p("READING: MIXED -- %d of %d answered, %d bound by the budget, %d"
              % (len(answered), len(results), len(ceiling), len(zero)))
            p("at zero tokens. No single cause is indicated. Do not draw a")
            p("conclusion about the prompt shape from a run with no comparison")
            p("arm; re-run without --skip-old if attribution is needed.")
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
