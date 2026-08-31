#!/usr/bin/env python3
"""
Test whether pre-closing the reasoning block makes the model answer at all.

WHY THIS EXISTS
---------------
MEASURED 2026-08-31 on the user's i5-12400, three rag cases, three budgets:

    budget   reasoning characters produced      visible answer
      512    (cut off)                          none
     2048    6,094 / 7,908 / 7,532              none
     3072   10,647 / 11,184 / 11,940            none

Every generation spent its entire budget inside an unterminated <think> block.
The reasoning grows with whatever budget it is given (~3.5 characters per token)
and never closes, so raising --max-tokens is not a route to an answer: at 3072
tokens a 52-case re-run would cost ~10.4 h and, on this evidence, produce
nothing gradeable. See D-0085.

Qwen3.5's /think and /nothink soft switches are documented NOT to work
(phase4_lib.py:212), and the shipped chat_template has no `enable_thinking`
flag. What remains is to prefill the assistant turn with an already-closed empty
reasoning block, so the model's next token is the first token of its answer.

That is what this script tests, and it tests ONLY that.

WHY THERE IS NO CONTROL ARM HERE
--------------------------------
The obvious design would run each case twice -- with and without the prefill --
for the same reason diagnose_zero_tokens.py runs both prompt shapes. It would
also be a waste of an hour of the user's evening. The no-prefill arm has ALREADY
been measured on these exact three cases at three budgets, and produced no
visible answer every single time (the table above). Re-measuring a result that
is already in evidence/phase4_merged.json and in the 2026-08-31 diagnostic
output buys nothing.

So the comparison is against RECORDED MEASUREMENTS, and the honest consequence
is stated in the reading: this run can show that the prefill produces an answer
where nothing else has, but it is a before/after across two sessions, not a
controlled A/B within one. --with-control exists for anyone who wants the strict
version and is willing to pay for it.

WHAT WOULD MAKE THIS RUN INVALID, AND WHY IT IS CHECKED
-------------------------------------------------------
`<think>` and `</think>` must each resolve to ONE DEDICATED token. If llama-cpp
tokenizes the prefill as ordinary text spelling "<think>" instead, the model
never sees a closed reasoning block, and the whole run is meaningless -- while
still printing plausible output. That failure mode is silent, so this script
tokenizes the prefill and REFUSES to interpret the results unless each tag is a
single token that decodes back to itself.

The ids are DISCOVERED from the loaded model, never hardcoded. The first version
of this script hardcoded 151667/151668 from a tokenizer_config in /tmp, and on
its first real run REFUSED a prefill that had tokenized perfectly -- because
that config described Qwen3-4B-Instruct-2507 (vocab 151,936), not the shipped
Qwen3.5-4B (text vocab 248,320), where the same two tags are 248068/248069. The
gate's logic was right and its constant was borrowed; the constant is gone. See
D-0087.

Precision retained from that episode: these are dedicated ADDED tokens, not
special tokens -- their entries carry "special": false, unlike <|im_start|>.
What matters for the design is only that each is ONE id, not a spelling, and
the discovery check establishes that directly rather than by reference.

WHAT THE CHECK STILL CANNOT PROVE
---------------------------------
The check calls tokenize(..., special=True) on the prefill string. That is the
permissive setting, so a FAILURE is conclusive: if the ids are absent even when
the tokenizer is asked to resolve markup, they would be absent under any
stricter setting, and refusing is right.

A PASS is weaker than it looks. It shows the tokenizer CAN resolve the string to
those ids when asked; it does not prove that the completion call's own internal
prompt handling asks for the same thing. If a future run reports OK here and the
model still behaves exactly as it does without the prefill, this gap -- not the
technique -- is the first thing to suspect, and the way to settle it is to
compare prompt_tokens between the prefill and control arms: the prefill should
add roughly 6 tokens, not roughly 12. That comparison needs --with-control, and
is why the flag exists beyond strictness.

WHAT IT DOES NOT DO
-------------------
It writes no file that any grader or threshold reads, and touches neither
PROJECT_STATE.json nor evidence/phase4_merged.json. It is a diagnostic, not a
measurement. Grading, recording and deciding what to re-run stay separate,
separately approved steps.

USAGE (Windows PowerShell, from the project root)
    python scripts\\diagnose_forced_answer.py --model C:\\models\\Qwen3.5-4B-Q5_K_M.gguf
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
from diagnose_zero_tokens import (  # noqa: E402
    ZERO_TOKEN_CASES, FIXED_OVERHEAD_S, ASYMPTOTIC_TPS, SLOW_ARM_MULTIPLIER,
    projected_seconds,
)

CONSOLE_UTF8 = L.make_console_safe()

# THE DEFECT THIS BLOCK USED TO CONTAIN, AND WHY IT IS GONE (D-0087).
#
# This file previously hardcoded THINK_OPEN_ID = 151667 / THINK_CLOSE_ID =
# 151668, read out of /tmp/qwen3_tokcfg.json, and refused to run unless the
# prefill tokenized to exactly those numbers. On 2026-08-31 the user ran it
# against the real C:\models\Qwen3.5-4B-Q5_K_M.gguf and it REFUSED, reporting
#
#     ids=[248068, 271, 248069, 271] (expected 151667 and 151668 present)
#
# That refusal was WRONG. Those four ids are the CORRECT tokenization:
# VERIFIED 2026-08-31 against Qwen/Qwen3.5-4B's own published tokenizer files,
# 248068 = "<think>", 248069 = "</think>" (both added tokens, "special": false)
# and 271 = the byte-level pair "\u010a\u010a", i.e. "\n\n". The prefill had
# resolved perfectly; my CONSTANTS were from a different model. 151667/151668
# belong to Qwen3-4B-Instruct-2507, whose vocabulary is 151,936 -- while
# Qwen3.5-4B's text vocabulary is 248,320. The config file I verified against
# was never this model's config.
#
# THE LESSON, which is the reason this comment is this long: a premise checked
# against a convenient nearby artefact is not a checked premise. The gate was
# sound; the number it compared to was inherited without provenance, and a gate
# that hardcodes an unprovenanced number can only ever be as right as that
# number. So the ids are now DISCOVERED from the loaded model itself and
# round-tripped back to text, which needs no constant and cannot go stale when
# the model changes.
#
# What survives from the old note, and is still true of THIS model:
# <think>/</think> are dedicated ADDED tokens, not special tokens -- their
# entries carry "special": false, unlike <|im_start|> / <|im_end|> /
# <|endoftext|> which carry "special": true. They sit in the same class as
# <tool_call>. What matters for the design is that each is ONE id, not a
# spelling, and that is what the discovery check now establishes directly.
#
# The residual limitation is UNCHANGED and still not papered over: tokenize(
# ..., special=True) is the permissive setting, so a FAILURE here is
# conclusive, but a PASS does not prove llama-cpp's own completion prompt path
# resolves the same string identically. The prompt-token delta printed under
# --with-control is the cross-check on that gap (R38).

# How many token ids a single tag may occupy before the gate calls it
# "spelled out as ordinary text". A dedicated added token is exactly 1. This is
# a threshold, not an id: it carries no assumption about WHICH id.
MAX_IDS_PER_TAG = 1

# Above this projected wall-clock, refuse to start without --yes. Lower than
# diagnose_zero_tokens.py's 20 because this script's entire claim is that it is
# a cheap test: if it is projecting more than a quarter of an hour, that claim
# has stopped being true and the user should be asked again.
LONG_RUN_MINUTES = 15


def p(s=""):
    sys.stdout.write(str(s) + "\n")
    sys.stdout.flush()


def _tok(llm, text):
    """Tokenize one string with markup resolution, or raise _NoTokenizer."""
    try:
        return list(llm.tokenize(text.encode("utf-8"), special=True))
    except TypeError:
        # Older llama-cpp-python without the `special` keyword. Without it
        # markup in the string is escaped rather than resolved, so a negative
        # result would not distinguish "this build cannot do it" from "the
        # prefill is wrong" -- hence UNVERIFIED, not a failure.
        raise _NoTokenizer("this llama-cpp build's tokenize() has no "
                           "`special` argument, so the check cannot be "
                           "performed")
    except Exception as e:  # noqa: BLE001
        raise _NoTokenizer("tokenize() raised %s: %s"
                           % (type(e).__name__, e))


class _NoTokenizer(Exception):
    """The build cannot answer the question. Distinct from answering 'no'."""


def _detok(llm, ids):
    """Detokenize ids back to text, or return None if the build cannot."""
    try:
        out = llm.detokenize(list(ids))
    except Exception:  # noqa: BLE001
        return None
    if isinstance(out, bytes):
        try:
            return out.decode("utf-8")
        except Exception:  # noqa: BLE001
            return None
    return out if isinstance(out, str) else None


def check_prefill_tokenization(llm):
    """
    Return (ok, detail): does the prefill resolve to DEDICATED think tokens?

    DISCOVERS the ids from the loaded model rather than comparing against a
    constant. That is the whole point of this function's existence in its
    current form: the previous version compared against 151667/151668, read
    from a tokenizer_config that turned out to describe a DIFFERENT model, and
    so refused a run whose prefill had tokenized perfectly (D-0087). A gate
    must test the property -- "each tag is one dedicated token, and it decodes
    back to itself" -- not a number it inherited.

    The property checked, in order:
      1. "<think>" alone tokenizes to exactly MAX_IDS_PER_TAG id(s), and
         likewise "</think>". More than that means the tag was spelled out as
         ordinary text, which is the silent failure this gate exists for.
      2. Each id round-trips: detokenizing it returns the tag's own text. This
         is what makes the discovery trustworthy without a hardcoded number --
         a wrong-but-single id would pass step 1 and fail here.
      3. Both discovered ids appear in the tokenization of the FULL prefill,
         so the check cannot pass on the tags in isolation while the assembled
         string does something else.

    Returns ok=None when the build exposes no usable tokenizer, which is NOT
    the same as a failure and must not be reported as one. A None here means
    the run's central premise is unverified, so the reading says UNVERIFIED
    rather than reporting any number as evidence.
    """
    try:
        open_ids = _tok(llm, RP.THINK_OPEN)
        close_ids = _tok(llm, RP.THINK_CLOSE)
        full_ids = _tok(llm, RP.FORCED_CLOSED_THINK)
    except _NoTokenizer as e:
        return None, str(e)

    # --- step 1: one id per tag -------------------------------------------
    for tag, ids in ((RP.THINK_OPEN, open_ids), (RP.THINK_CLOSE, close_ids)):
        if len(ids) != MAX_IDS_PER_TAG:
            return False, (
                "%r tokenizes to %d ids %s, not %d -- it is being spelled out "
                "as ordinary text rather than resolving to a dedicated token "
                "(full prefill: %s)"
                % (tag, len(ids), ids, MAX_IDS_PER_TAG, full_ids))

    open_id = open_ids[0]
    close_id = close_ids[0]
    if open_id == close_id:
        return False, ("%r and %r tokenize to the SAME id %d, so a closed "
                       "block is indistinguishable from an open one "
                       "(full prefill: %s)"
                       % (RP.THINK_OPEN, RP.THINK_CLOSE, open_id, full_ids))

    # --- step 2: round-trip ------------------------------------------------
    # A build with no usable detokenize() cannot confirm identity. That is a
    # gap in the CHECK, not evidence against the prefill, so it degrades to
    # UNVERIFIED rather than refusing a possibly-correct run.
    round_trips = []
    for tag, tid in ((RP.THINK_OPEN, open_id), (RP.THINK_CLOSE, close_id)):
        back = _detok(llm, [tid])
        if back is None:
            return None, ("ids discovered (%r=%d, %r=%d) but this build's "
                          "detokenize() could not confirm they decode back to "
                          "those tags, so the discovery is unverified"
                          % (RP.THINK_OPEN, open_id, RP.THINK_CLOSE, close_id))
        round_trips.append((tag, tid, back))
    for tag, tid, back in round_trips:
        if back.strip() != tag:
            return False, (
                "id %d was discovered for %r but decodes back to %r -- the "
                "tokenizer is not treating that tag as itself "
                "(full prefill: %s)" % (tid, tag, back, full_ids))

    # --- step 3: both ids present in the assembled prefill -----------------
    missing = [t for t, i in ((RP.THINK_OPEN, open_id),
                              (RP.THINK_CLOSE, close_id))
               if i not in full_ids]
    if missing:
        return False, (
            "the tags resolve to dedicated ids in isolation (%r=%d, %r=%d) "
            "but %s absent from the assembled prefill %s"
            % (RP.THINK_OPEN, open_id, RP.THINK_CLOSE, close_id,
               " and ".join(repr(t) for t in missing), full_ids))

    return True, ("%r=%d, %r=%d, both round-tripped; prefill ids=%s"
                  % (RP.THINK_OPEN, open_id, RP.THINK_CLOSE, close_id,
                     full_ids))


def main():
    ap = argparse.ArgumentParser(
        description="Test whether a pre-closed <think> block yields an answer.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  # the cheap test: 3 generations, prefill only
  python scripts\\diagnose_forced_answer.py --model C:\\models\\Qwen3.5-4B-Q5_K_M.gguf

  # strict A/B, 6 generations, roughly 4x the cost
  python scripts\\diagnose_forced_answer.py --model C:\\models\\Qwen3.5-4B-Q5_K_M.gguf --with-control --yes

note:
  --max-tokens defaults to 512, not 3072. The point of the prefill is that the
  model answers INSTEAD of deliberating, so a large budget is not needed -- and
  if 512 tokens are all consumed without finishing, that is itself the finding.
""")
    ap.add_argument("--model", required=True, help="path to the GGUF file")
    ap.add_argument("--ctx", type=int, default=16384)
    ap.add_argument("--threads", type=int, default=6)
    # WHY 512 AND NOT 3072. A forced-closed block means the reply should BE the
    # answer, and the answers this eval expects are short -- the one case that
    # ever answered normally (RAG-EN-002) used 266 tokens. Asking for 3072 would
    # cost 6x for tokens the model should not need. If 512 is exhausted, the
    # reading says so rather than guessing.
    ap.add_argument("--max-tokens", type=int, default=512)
    ap.add_argument("--corpus",
                    default=os.path.join(_ROOT, "evals", "rag_corpus_v1.jsonl"))
    ap.add_argument("--gold",
                    default=os.path.join(_ROOT, "evals", "rag_gold_v1.jsonl"))
    ap.add_argument("--top-k", type=int, default=4)
    ap.add_argument("--with-control", action="store_true",
                    help="also run the ordinary prompt at the same budget, for "
                         "a strict A/B. Costs 2x the generations; the "
                         "no-prefill outcome is already MEASURED at three "
                         "budgets, so this is optional.")
    ap.add_argument("--yes", action="store_true",
                    help="confirm a run whose PROJECTED cost exceeds "
                         "%d minutes" % LONG_RUN_MINUTES)
    ap.add_argument("--out", default=None,
                    help="optional path for a JSON copy of these results. "
                         "NOT read by any grader.")
    a = ap.parse_args()

    if not os.path.exists(a.model):
        raise SystemExit(
            "ERROR: model file not found: %s\n"
            "  (the path is resolved against %s)" % (a.model, os.getcwd()))

    p("=" * 70)
    p("FORCED-ANSWER DIAGNOSTIC  (pre-closed <think> block)")
    p("=" * 70)
    p("model      : %s" % a.model)
    p("max_tokens : %d   ctx: %d   threads: %d" % (a.max_tokens, a.ctx,
                                                   a.threads))
    p("cases      : %s" % ", ".join(i for _, i in ZERO_TOKEN_CASES))
    p("arms       : %s" % ("prefill + no-prefill control" if a.with_control
                           else "prefill only (control is already MEASURED)"))
    p("prefill    : %r" % RP.FORCED_CLOSED_THINK)
    p("")
    p("This script does NOT write any file a grader reads, and does not")
    p("modify PROJECT_STATE.json or evidence/phase4_merged.json.")
    p("")

    n_gen = len(ZERO_TOKEN_CASES) * (2 if a.with_control else 1)
    proj_min = projected_seconds(a.max_tokens, n_gen) / 60.0
    p("projected  : %d generations x %d tok" % (n_gen, a.max_tokens))
    p("             cost model: %.0f s fixed + tokens/%.2f per generation,"
      % (FIXED_OVERHEAD_S, ASYMPTOTIC_TPS))
    p("             fitted to three MEASURED budgets (512/2048/3072)")
    p("             = ~%.0f minutes of wall clock  [ESTIMATED from a "
      "MEASURED fit]" % proj_min)
    p("             up to ~%.0f min at the slower arms' rate (%.2fx spread"
      % (proj_min * SLOW_ARM_MULTIPLIER, SLOW_ARM_MULTIPLIER))
    p("             MEASURED across arms on 2026-08-30).")
    p("             A reply that finishes early costs LESS, and the whole")
    p("             point of this test is that replies should finish early.")
    p("")
    if proj_min > LONG_RUN_MINUTES and not a.yes:
        raise SystemExit(
            "REFUSING TO START: the projection above (~%.0f min) exceeds the "
            "%d-minute\n"
            "  threshold this script holds itself to. Re-run with --yes if you "
            "accept\n"
            "  that cost, or lower --max-tokens." % (proj_min,
                                                     LONG_RUN_MINUTES))

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
    n_budget = a.max_tokens

    from llama_cpp import Llama
    t0 = time.time()
    llm = Llama(model_path=a.model, n_ctx=a.ctx, n_threads=a.threads,
                verbose=False)
    p("load time  : %.1f s  [MEASURED]" % (time.time() - t0))

    # ---- the validity check, BEFORE spending any decode time --------------
    tok_ok, tok_detail = check_prefill_tokenization(llm)
    if tok_ok is True:
        # The ids are REPORTED, not asserted against a constant. Printing what
        # was discovered is what makes a future vocabulary change visible
        # instead of fatal -- the failure mode that produced D-0087.
        p("prefill tok: OK -- %s" % tok_detail)
    elif tok_ok is False:
        p("prefill tok: *** WRONG *** %s" % tok_detail)
        p("")
        raise SystemExit(
            "REFUSING TO RUN: the prefill does not resolve to DEDICATED\n"
            "  <think>/</think> tokens, so the model would never see a closed\n"
            "  reasoning block and any answer it gave would prove nothing "
            "about\n"
            "  this technique. Fix the tokenization before spending decode "
            "time.\n"
            "  Detail: %s" % tok_detail)
    else:
        p("prefill tok: UNVERIFIED -- %s" % tok_detail)
        p("             The run continues, but the reading below will say so:")
        p("             an unverified prefill cannot support a conclusion.")

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
        p("  (~%.0f min per generation [ESTIMATED]; no output until it "
          "finishes)" % (projected_seconds(a.max_tokens) / 60.0,))

        # The control prompt is the project's REAL rag prompt, and the prefill
        # prompt is that exact string plus the pre-closed block -- derived from
        # it, not rebuilt beside it.
        #
        # An earlier version of this reassembled the evidence block inline,
        # duplicating build_rag_prompt()'s body. Two copies of the same
        # formatting is exactly how the prefill/control prompt-token delta
        # stops meaning what the summary says it means: any drift in the
        # duplicate would show up as extra prompt tokens and be misread as the
        # prefill being spelled out as text. Deriving guarantees the ONLY
        # difference between the arms is the block itself.
        control_prompt = RP.build_rag_prompt(gold["query"], passages)
        prefill_prompt = control_prompt + RP.FORCED_CLOSED_THINK
        assert prefill_prompt.startswith(control_prompt)

        arms = [("prefill", prefill_prompt)]
        if a.with_control:
            arms.append(("control", control_prompt))

        for label, prompt in arms:
            text, m = runner.generate(prompt)
            answered = bool(text.strip())
            hit_ceiling = (m["completion_tokens"] >= n_budget)
            # DID THE MODEL START DELIBERATING AGAIN? A pre-closed block does
            # not stop it from opening a NEW one, and if it does, this run has
            # not solved the problem even if some text comes back. Checked on
            # the raw output because the prompt's own tag is not echoed.
            raw = m.get("raw_output") or ""
            reopened = RP.THINK_OPEN in raw
            row[label] = {
                "completion_tokens": m["completion_tokens"],
                # Kept so the prefill/control PROMPT length can be compared.
                # The prefill adds "<think>\n\n</think>\n\n". If those resolve
                # to their own ids it costs ~6 tokens; if it is spelled out as
                # text it costs roughly double, which is the one observable
                # signal that the tokenization gate passed but llama-cpp's own
                # prompt path did something different. See the docstring's
                # "WHAT THE CHECK STILL CANNOT PROVE".
                "prompt_tokens": m["prompt_tokens"],
                "seconds": m["seconds"],
                "decode_tps": m["decode_tps"],
                "answer_chars": len(text.strip()),
                "thinking_truncated": m["thinking_truncated"],
                "reopened_think": reopened,
                "hit_ceiling": hit_ceiling,
                # `answered` is RAW: "some visible text came back". It is true
                # even for a reply truncated at the ceiling mid-sentence, and
                # even for one that re-opened a think block. Anything counting
                # successes must use `complete_answer`, which is the field the
                # summary and the reading are computed from. Both are written
                # so a later reader cannot mistake one for the other.
                "answered": answered,
                "complete_answer": bool(answered and not hit_ceiling
                                        and not reopened),
                "answer_preview": text[:300],
            }
            if m["completion_tokens"] == 0:
                verdict = "ZERO TOKENS"
            elif reopened:
                # THIRD WORDING DEFECT FOUND BY DRY RUN. This read
                # "RE-OPENED <think> -- the prefill did not stop it" for BOTH
                # arms, but the control arm has no prefill to fail: a think
                # block there is the model's ordinary, already-MEASURED
                # behaviour, not evidence about this technique. Printing the
                # prefill's failure text under the control arm would have made
                # the control look like a refutation of the thing it is the
                # baseline for.
                verdict = ("RE-OPENED <think> -- the prefill did not stop it"
                           if label == "prefill"
                           else "OPENED <think> -- expected; this is the "
                                "baseline behaviour")
            elif answered and hit_ceiling:
                # SECOND DEFECT FOUND BEFORE SHIPPING. A reply that consumed
                # the WHOLE budget and still has visible text is almost
                # certainly truncated mid-sentence -- deliberation prose with
                # no <think> tag around it, not a finished answer. Calling that
                # "ANSWERED" would be the same silent over-claim as the
                # branch-order defect below: plausible output, wrong reading.
                verdict = ("TEXT AT CEILING (%d chars) -- truncated, NOT a "
                           "finished answer" % len(text.strip()))
            elif answered:
                verdict = "ANSWERED (%d chars)" % len(text.strip())
            elif m["thinking_truncated"]:
                verdict = "NO ANSWER -- unterminated <think>"
            else:
                verdict = "NO ANSWER -- tokens emitted, nothing visible"
            p("  %-9s tokens=%-5d %-7.1fs  %s%s"
              % (label, m["completion_tokens"], m["seconds"], verdict,
                 "  [AT CEILING]" if hit_ceiling else ""))
            if text.strip():
                p("      %s" % text.strip()[:200].replace("\n", " "))
            else:
                p("      (no visible answer; reasoning %d chars) %s"
                  % (m["reasoning_chars"],
                     raw.strip()[:120].replace("\n", " ") if raw.strip()
                     else ""))

        results.append(row)

    p("")
    p("=" * 70)
    p("SUMMARY  [MEASURED]")
    p("=" * 70)

    pre = [r["prefill"] for r in results]
    # "answered" means a COMPLETE visible answer: text came back, the budget
    # was not exhausted producing it, and no new think block was opened. Text
    # that stops exactly at the ceiling is truncated prose, not an answer, and
    # is counted separately -- see the TEXT AT CEILING verdict above.
    answered = [r["id"] for r in results if r["prefill"]["complete_answer"]]
    truncated_text = [r["id"] for r in results
                      if r["prefill"]["answered"]
                      and r["prefill"]["hit_ceiling"]
                      and not r["prefill"]["reopened_think"]]
    reopened = [r["id"] for r in results if r["prefill"]["reopened_think"]]
    ceiling = [r["id"] for r in results if r["prefill"]["hit_ceiling"]]
    p("prefill, COMPLETE ANSWER: %d of %d  %s"
      % (len(answered), len(results), answered))
    p("prefill, text at ceiling: %d of %d  %s  (truncated, not answers)"
      % (len(truncated_text), len(results), truncated_text))
    p("prefill, re-opened think: %d of %d  %s"
      % (len(reopened), len(results), reopened))
    p("prefill, budget-bound   : %d of %d  %s"
      % (len(ceiling), len(results), ceiling))
    if pre and all(x["completion_tokens"] for x in pre):
        p("prefill, tokens used    : %s (budget %d)"
          % (", ".join(str(x["completion_tokens"]) for x in pre), n_budget))
    # Set only when --with-control makes the comparison possible. None means
    # "not checked", which is different from "checked and fine" -- the reading
    # below must not treat the two alike.
    delta_impossible = None
    delta_spelled = None
    if a.with_control:
        c_ans = [r["id"] for r in results if r["control"]["complete_answer"]]
        p("control, COMPLETE ANSWER: %d of %d  %s"
          % (len(c_ans), len(results), c_ans))
        # The only available evidence on whether llama-cpp's prompt path
        # resolved the prefill to the two ids or spelled it out as text.
        deltas = [r["prefill"]["prompt_tokens"] - r["control"]["prompt_tokens"]
                  for r in results]
        delta_impossible = any(d <= 0 for d in deltas)
        # >= 12 on EVERY case: the 19-character block apparently cost about one
        # token per character, i.e. it was spelled out rather than resolved to
        # ids. Expected is ~4-6 (one id each for <think>, </think>, and the
        # newline runs) -- MEASURED as 4-5 against a character-based estimator
        # in the dry run.
        delta_spelled = bool(deltas) and all(d >= 12 for d in deltas)
        p("prompt-token delta      : %s  (prefill minus control)"
          % (deltas,))
        if delta_impossible:
            # Not a "maybe". The prefill prompt is the control prompt plus 19
            # characters, so a delta of zero or less is arithmetically
            # impossible if both arms were counted honestly -- it means the
            # prefill never reached the model, or prompt_tokens is not being
            # reported per call. Either way the run proves nothing, and this
            # must be louder than the ~6/~12 guidance rather than folded into
            # it. The dry run printed [0, 0, 0] and had nothing to say.
            p("        *** IMPOSSIBLE: the prefill prompt is strictly longer")
            p("        than the control prompt, so a delta <= 0 cannot happen")
            p("        if both arms were counted. The prefill probably never")
            p("        reached the model. TREAT THIS RUN AS INVALID.")
        elif delta_spelled:
            p("        *** the delta is >= 12 on every case, which suggests")
            p("        the block was spelled out as plain text rather than")
            p("        resolved to its dedicated tokens -- the gate above")
            p("        passed but the completion call did something else.")
            p("        Investigate before believing any verdict below.")
        else:
            p("        (~6 expected: the block resolving to its own ids. A")
            p("        delta of ~12+ would suggest it was spelled out as")
            p("        plain text instead -- see the docstring.)")

    # ---- the reading -----------------------------------------------------
    # Ordered so that the states which INVALIDATE the run are reported before
    # any state that could be read as a success. Three diagnostics in this
    # project have now shipped with a verdict that could not say
    # "inconclusive" first; that is the defect being avoided here.
    if delta_impossible:
        # FOURTH DEFECT FOUND BY DRY RUN. This state used to print no reading
        # of its own, so a run whose prompt-token delta was arithmetically
        # impossible still reached "the prefill WORKS" -- the exact
        # invalidating-state-reported-after-a-success-verdict failure this
        # script's branch ordering exists to prevent. The note above the
        # summary was not enough: the READING line is what gets quoted.
        p("READING: INVALID. The prefill prompt is strictly longer than the")
        p("control prompt, yet the reported prompt-token delta is zero or")
        p("negative. That is arithmetically impossible if both arms were")
        p("counted, so the prefill very likely never reached the model. No")
        p("conclusion about this technique can be drawn from this run, "
          "whatever")
        p("the answer counts above show. Investigate the harness first.")
    elif delta_spelled:
        # Same defect class as the impossible delta: the dry run reached "the
        # prefill WORKS" here too. If the block was spelled out as text, the
        # model never saw a CLOSED reasoning block -- it saw a user-style
        # string mentioning one -- so an answer is not evidence for the
        # technique, however good the answer looks.
        p("READING: INVALID. The pre-closed block appears to have been spelled")
        p("out as ordinary text rather than resolved to its dedicated tokens:")
        p("it cost 12+ prompt tokens on every case where ~6 was expected. If")
        p("so the model never saw a closed reasoning block, and any answer is")
        p("not evidence about this technique. Fix the tokenization first.")
    elif tok_ok is None:
        p("READING: UNVERIFIED. The prefill's tokenization could not be")
        p("checked on this llama-cpp build, so it is not known whether the")
        p("model saw a closed reasoning block or six literal characters.")
        p("Whatever the numbers above say, they cannot support a conclusion")
        p("about this technique. Report the llama-cpp version.")
    elif not answered and reopened:
        # DEFECT FOUND BY DRY RUN, BEFORE THIS SCRIPT WAS EVER OFFERED.
        #
        # This branch used to be `elif reopened:` and sat ABOVE every
        # answered-case branch. That made it fire whenever ANY case re-opened
        # a think block -- so a run in which 2 of 3 cases answered perfectly
        # and 1 re-opened printed "the prefill did NOT stop the deliberation,
        # 1 of 3" and NOTHING about the two answers, and the MIXED branch
        # below was unreachable in exactly the situation it was written for.
        # The condition is therefore now "no case answered AND the failures
        # are explained by re-opening", which is the claim the text makes.
        p("READING: the prefill did NOT stop the deliberation. %d of %d"
          % (len(reopened), len(results)))
        p("replies opened a NEW <think> block after the pre-closed one, and")
        p("none produced a visible answer. Pre-closing the block is therefore")
        p("not sufficient on its own; the next thing to try is a prompt-level")
        p("instruction to answer directly, NOT a bigger budget.")
    elif not answered and truncated_text:
        # The ONLY state in this script where raising the budget is the right
        # response. The model was emitting answer prose, with no think block,
        # and ran out of room -- unlike the 512/2048/3072 runs, where the extra
        # room went into reasoning that never closed. Saying "do not raise the
        # budget" here, by reflex from the other branches, would be wrong.
        p("READING: PARTIAL. %d of %d replies contained visible prose with no"
          % (len(truncated_text), len(results)))
        p("think block, but hit the %d-token ceiling, so they are truncated"
          % n_budget)
        p("mid-answer and are NOT gradeable as answers. This is the one")
        p("outcome where a larger budget is the correct next step: the tokens")
        p("went into the answer, not into reasoning. Re-run this same script")
        p("with a higher --max-tokens before concluding anything.")
    elif len(answered) == len(results):
        p("READING: the prefill WORKS. All %d cases produced a visible answer"
          % len(results))
        p("at %d tokens, where the ordinary prompt produced none at 512, 2048"
          % n_budget)
        p("or 3072 (MEASURED). That is the first configuration in which these")
        p("cases answer at all, and it makes a full re-run worth costing.")
        if not a.with_control:
            p("")
            p("LIMIT: the comparison is against measurements from earlier")
            p("sessions, not a control arm run alongside these. It is a")
            p("before/after, not a strict A/B. --with-control buys the strict")
            p("version. Nothing here says the ANSWERS ARE CORRECT -- only that")
            p("answers exist to be graded.")
    elif answered:
        p("READING: MIXED. %d of %d cases produced a complete answer with the"
          % (len(answered), len(results)))
        p("prefill: %s" % (answered,))
        # Name the remainder explicitly. "Some answered" is not a diagnosis --
        # the right next step differs completely depending on whether the rest
        # re-opened a think block (prompt problem) or ran out of room mid-answer
        # (budget problem), and an undifferentiated MIXED verdict hides that.
        if reopened:
            p("%d re-opened a <think> block: %s" % (len(reopened), reopened))
        if truncated_text:
            p("%d ran out of budget mid-answer: %s"
              % (len(truncated_text), truncated_text))
        silent = [r["id"] for r in results
                  if not r["prefill"]["answered"]
                  and not r["prefill"]["reopened_think"]]
        if silent:
            p("%d returned nothing visible: %s" % (len(silent), silent))
        p("Partial success is not a green light: the cases that failed need")
        p("their own diagnosis before any hours are spent, and the ones that")
        p("answered say nothing about the ones that did not.")
    elif ceiling:
        p("READING: the prefill did not help. %d of %d generations consumed"
          % (len(ceiling), len(results)))
        p("the whole %d-token budget with no visible answer, without even" % n_budget)
        p("re-opening a think block. This is a strong argument against the")
        p("full re-run, and against this technique. Do NOT respond by raising")
        p("the budget -- that has now failed at 512, 2048 and 3072.")
    else:
        p("READING: no answers, and not budget-bound either. The model")
        p("emitted tokens that left nothing visible. Inspect --out before")
        p("drawing any conclusion; this state was not anticipated.")

    p("")
    p("NOTE: this is a DIAGNOSTIC. No threshold has been evaluated and no")
    p("measurement has been recorded. phase_4/measurements_recorded is")
    p("untouched.")

    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump({"label": "DIAGNOSTIC -- NOT A MEASUREMENT",
                       "max_tokens": a.max_tokens,
                       "prefill": RP.FORCED_CLOSED_THINK,
                       "prefill_tokenization_ok": tok_ok,
                       "prefill_tokenization_detail": tok_detail,
                       "with_control": bool(a.with_control),
                       "results": results}, f, ensure_ascii=False, indent=2)
        p("")
        p("wrote %s  (not read by any grader)" % a.out)


if __name__ == "__main__":
    main()
