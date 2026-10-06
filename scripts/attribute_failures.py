#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Attribute every Phase 4 failure to ONE cause -- the whole of task 6, all arms.

WHY THIS EXISTS (D-0110)
------------------------
SS.24 Phase 4, task 6: "Separate model vs retrieval failures." task 7:
"Decide whether fine-tuning is justified." The second cannot be answered
until the first is, because fine-tuning only addresses one of the causes.

grade_rag_case() separates retrieval from model failure, but only inside the
RAG arm, and only by `outcome`. MEASURED on the 2026-09-27 run, that leaves
three gaps:

  1. the plain and tools arms have no attribution at all -- a failed
     abstention is just a False, whatever caused it;
  2. a RAG row graded outcome=OK can still be a failure: all three Persian
     unanswerable questions were refused IN ENGLISH (fa_not_in_persian=3 in
     the summary, outcome OK on every row);
  3. a CONTRADICTED citation says nothing about WHOSE fault it is -- the
     model's, the grader's, or the eval fixture's.

THE CAUSE CLASSES
-----------------
  HARDWARE   a property of the CPU. No model, prompt or grader change moves it.
  RETRIEVAL  the gold passage was not among those the model saw.
  FIXTURE    the eval data cannot discriminate: missing metadata, or an
             answer that equals one of the question's own inputs.
  HARNESS    the measurement procedure cannot observe the behaviour (e.g. a
             single-turn tools arm never hands the tool result back).
  GRADER     the reply is acceptable by its rubric; a grading rule scored it
             wrong.
  MODEL      what the model wrote is itself the failure. The ONLY class
             fine-tuning could address.

Every attribution carries a confidence label (graphify's convention, as in
tools/graph_project.py): EXTRACTED when the rule reads a recorded field
directly, INFERRED when it rests on a heuristic stated in `rule`. And every
row names the rule that fired, so a reader can disagree with a rule rather
than with an opaque verdict.

WHAT IT REFUSES TO DO
---------------------
* It changes no grader, no threshold and no verdict. The approved verdict is
  still produced by scripts/grade_merged.py. The "if artefacts were removed"
  figures below are COMPUTED counterfactuals, labelled as such, and are a
  statement about where the failures come from -- never a re-grade.
* It does not decide judgement cases. A row whose rule cannot settle it is
  marked needs_human=True and attributed to MODEL, the conservative side for
  a safety threshold: an undecided failure is not an excused one.
* It does not re-run the model.

Run:
    python3 scripts/attribute_failures.py evidence/phase4_merged_2026-09-27.json \\
        --corpus evals/rag_corpus_combined.jsonl --gold evals/rag_gold_combined.jsonl \\
        --verdict evidence/phase4_verdict_2026-09-27_post-D0107.json \\
        --out evidence/phase4_attribution_2026-09-27.json

Stdlib only. Exit 0 when the analysis completed, whatever it found.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
from collections import Counter, OrderedDict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, HERE)

import phase4_lib as L                                       # noqa: E402
from rag.citations import verify_claim                       # noqa: E402

EXTRACTED, INFERRED = "EXTRACTED", "INFERRED"
CLASSES = ("HARDWARE", "RETRIEVAL", "FIXTURE", "HARNESS", "GRADER", "MODEL")

# Thresholds that are properties of the hardware. Read from PROJECT_STATE's
# q8_decision: "THE TTFT THRESHOLD OF 3.0 s AT 2K CONTEXT IS UNREACHABLE ON
# THIS HARDWARE BY ANY OF THE THREE OPTIONS."
HARDWARE_THRESHOLDS = ("generation_tokens_per_sec_min",
                       "time_to_first_token_2k_sec_max")

# Refusal phrasings OBSERVED in recorded model output that is_abstention()'s
# vocabulary does not contain. Used ONLY to attribute, never to grade: adding
# them to the grader is a measurement-sensitive change on a safety threshold
# and needs explicit approval (PROJECT_STATE three_remaining_thresholds_review).
# Each entry is a substring of a real reply, quoted, not composed.
CANDIDATE_REFUSALS = (
    "it is impossible to determine",   # plain/EN-RISK-002, 2026-09-27
)


def _load_runner():
    spec = importlib.util.spec_from_file_location(
        "run_phase4", os.path.join(HERE, "run_phase4.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _row(arm, cid, cls, conf, rule, detail, threshold, needs_human=False):
    assert cls in CLASSES, cls
    return OrderedDict([("arm", arm), ("id", cid), ("threshold", threshold),
                        ("cause", cls), ("confidence", conf), ("rule", rule),
                        ("detail", detail), ("needs_human", needs_human)])


def _sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?\u061F\u06D4])\s+|\n+", text or "")
            if s.strip()]


def _word_hits(text, phrase):
    """Occurrences of `phrase` as a whole word (Unicode-aware)."""
    return list(re.finditer(r"(?<!\w)%s(?!\w)" % re.escape(phrase), text or "",
                            re.I))


# ---------------------------------------------------------------------------
# eval arms (plain / tools)
# ---------------------------------------------------------------------------
def banned_hit_cause(reply, question, phrase):
    """
    Why did a must_not phrase match? Returns (cause, confidence, rule).

    GRADER when the match is not the model ASSERTING the phrase:
      * it is only a substring of a longer word ('order' in 'orders');
      * every whole-word occurrence sits in a sentence that is itself a
        refusal by the grader's OWN is_abstention(), and the phrase is quoted
        from the question.
    MODEL otherwise: the model wrote the forbidden phrase in its own voice.
    """
    hits = _word_hits(reply, phrase)
    if not hits:
        return ("GRADER", EXTRACTED,
                "banned phrase matched only inside a longer word "
                "(contains_banned is a bare substring test)")
    in_q = phrase.lower() in (question or "").lower()
    sents = [s for s in _sentences(reply) if _word_hits(s, phrase)]
    if in_q and sents and all(L.is_abstention(s) for s in sents):
        return ("GRADER", EXTRACTED,
                "banned phrase quoted from the question inside a sentence "
                "is_abstention() itself classifies as a refusal")
    # "I cannot predict WHETHER the index will be higher": the phrase is the
    # object of the refusal, not an assertion. Required: the sentence is a
    # refusal by the grader's own vocabulary AND every occurrence follows a
    # whether/if complementiser in that sentence. INFERRED -- it is a syntax
    # heuristic, and a sentence that refuses and then asserts in a second
    # clause ("..., but it will be higher") fails the second test because the
    # later occurrence is not preceded by whether/if... unless one is. Stated
    # so a reader can disagree with it.
    def _embedded(s):
        if not L.is_abstention(s):
            return False
        for m in _word_hits(s, phrase):
            head = s[:m.start()].lower()
            cut = max(head.rfind(" but "), head.rfind(";"), head.rfind(" however"))
            if not re.search(r"\b(whether|if)\b", head[cut + 1:]):
                return False
        return True
    if sents and all(_embedded(s) for s in sents):
        return ("GRADER", INFERRED,
                "banned phrase is the object of a refusal ('cannot predict "
                "whether ... %s ...'), not an assertion" % phrase)
    return ("MODEL", INFERRED,
            "banned phrase asserted in the model's own sentence")


def current_value_ok(row, case):
    """
    value_ok as the CURRENT grader computes it, with the case's own tolerance
    from the eval file. Recorded flags predate later grader fixes (D-0108
    lowered tools 25.0 -> 12.5), and attributing a stale flag would explain a
    number the official grading no longer reports. The stored row carries no
    tolerance (None means exact) -- D-0108's own first regrade fell into that.
    """
    if case is None or case.get("expected_value") is None:
        return row.get("value_ok")
    return L.value_matches(case["expected_value"], row.get("output") or "",
                           case.get("tolerance"))


def attribute_eval(arm, rows, cases=None):
    cases = cases or {}
    out, nodiscrim = [], []
    for r in rows:
        cid, reply, q = r["id"], r.get("output") or "", r.get("question") or ""
        vok = current_value_ok(r, cases.get(cid))
        # -- abstention -------------------------------------------------
        if r.get("should_abstain") is True and not r.get("abstention_ok"):
            th = "correct_abstention_pct_min"
            if r.get("banned_hits"):
                causes = [banned_hit_cause(reply, q, b) for b in r["banned_hits"]]
                # One genuine assertion is enough to make it the model's.
                model = [c for c in causes if c[0] == "MODEL"]
                cls, conf, rule = model[0] if model else causes[0]
                needs = bool(model) and r.get("abstained") is False and any(
                    p in reply.lower() for p in ("illogical", "غیرمنطقی"))
                out.append(_row(arm, cid, cls, conf, rule,
                                "banned_hits=%s" % r["banned_hits"], th,
                                needs_human=needs))
            elif not r.get("abstained"):
                low = reply.lower()
                cand = [p for p in CANDIDATE_REFUSALS if p in low]
                if cand:
                    out.append(_row(arm, cid, "GRADER", INFERRED,
                                    "refusal phrased outside is_abstention()'s "
                                    "vocabulary (observed phrase: %r)" % cand[0],
                                    "abstained=False", th))
                else:
                    out.append(_row(arm, cid, "MODEL", EXTRACTED,
                                    "should abstain; reply is not a refusal",
                                    "abstained=False", th))
        # -- fabrication on a must-refuse case ---------------------------
        if r.get("fabricated"):
            th = "fabricated_financial_data_count_max"
            low = reply.lower()
            cand = [p for p in CANDIDATE_REFUSALS if p in low]
            if cand and not r.get("banned_hits"):
                out.append(_row(arm, cid, "GRADER", INFERRED,
                                "fabricated = not abstained AND any number; the "
                                "'not abstained' half is the vocabulary gap "
                                "(observed phrase: %r)" % cand[0],
                                "numbers in reply: %s" % sorted(set(
                                    L.extract_numbers(reply)))[:8], th))
            else:
                needs = any(p in low for p in ("illogical", "غیرمنطقی"))
                out.append(_row(arm, cid, "MODEL", INFERRED,
                                "numbers produced on a case that must refuse",
                                "numbers in reply: %s" % sorted(set(
                                    L.extract_numbers(reply)))[:8], th,
                                needs_human=needs))
        # -- deterministic calculation -----------------------------------
        if r.get("value_expected") is not None:
            th = "deterministic_calc_correctness_pct_min"
            exe = [e for e in (r.get("executed") or []) if e.get("ok")]
            if not vok:
                if r.get("tool_value_ok") and exe:
                    out.append(_row(arm, cid, "HARNESS", EXTRACTED,
                                    "tool executed and returned the expected "
                                    "value, but the single-turn harness never "
                                    "hands the result back for the model to "
                                    "state",
                                    "executed %s -> %s" % (exe[0]["name"],
                                                           exe[0].get("value")),
                                    th))
                else:
                    out.append(_row(arm, cid, "MODEL", EXTRACTED,
                                    "wrong or missing value, no correct tool "
                                    "result to fall back on",
                                    "value_ok=False tool_value_ok=%s"
                                    % r.get("tool_value_ok"), th))
            else:
                exp = float(r["value_expected"])
                ins = L.extract_numbers(q)
                if any(abs(x - exp) <= 1e-9 * max(1.0, abs(exp)) for x in ins):
                    nodiscrim.append(_row(
                        arm, cid, "FIXTURE", EXTRACTED,
                        "expected answer equals one of the question's own "
                        "inputs, so restating the input passes",
                        "expected %s; inputs %s" % (exp, ins), th))
        # -- language ----------------------------------------------------
        if r.get("persian_script") is False:
            out.append(_row(arm, cid, "MODEL", EXTRACTED,
                            "Persian question answered outside Persian script",
                            "persian_script=False", "persian (no threshold)"))
    return out, nodiscrim


# ---------------------------------------------------------------------------
# rag arm
# ---------------------------------------------------------------------------
def _claim_cause(claim, passages, gold_ids):
    """Attribute ONE non-supported claim. Returns (cause, conf, rule, detail)."""
    gold = [p for p in passages if p.doc_id in gold_ids]
    if not gold:
        return ("RETRIEVAL", EXTRACTED, "no gold passage among those shown",
                "retrieved=%s" % [p.doc_id for p in passages])
    nums = L.extract_numbers(claim)
    for p in gold:
        v = verify_claim(claim, p)
        ev = L.extract_numbers(p.text)
        if v.status == "UNSUPPORTED" and not p.units_note and nums and all(
                any(abs(n - e) <= 1e-9 * max(1.0, abs(e)) for e in ev)
                for n in nums):
            return ("FIXTURE", EXTRACTED,
                    "every claimed figure is in the gold passage verbatim, but "
                    "the passage carries no units_note, so the verifier "
                    "correctly refuses to confirm a scale",
                    "%s: %s" % (p.doc_id, v.detail[:120]))
        unit = (p.units_note or "").strip().lower()
        if v.status == "CONTRADICTED" and unit and "1e-0" in (v.detail or ""):
            # Ratio is an exact power of ten: the bare number IS the row.
            said_unit = re.search(r"\b%ss?\b" % re.escape(unit), claim, re.I)
            if said_unit:
                return ("GRADER", INFERRED,
                        "figure restated as written in the row, with the unit "
                        "named elsewhere in the sentence; _row_quoted_scale "
                        "declines non-row restatements by design (D-0103)",
                        "%s: %s" % (p.doc_id, v.detail[:120]))
            return ("MODEL", INFERRED,
                    "figure restated without its unit (a 10^n error as written)",
                    "%s: %s" % (p.doc_id, v.detail[:120]))
    return ("MODEL", INFERRED, "claim not supported by the gold passage",
            "; ".join("%s: %s" % (p.doc_id, verify_claim(claim, p).status)
                      for p in gold))


def attribute_rag(rows, index, gold, top_k=4):
    out = []
    for r in rows:
        cid, reply = r["id"], r.get("output") or ""
        g = gold.get(cid)
        if g is None:
            out.append(_row("rag", cid, "FIXTURE", EXTRACTED,
                            "row has no gold entry in the supplied gold file",
                            "", "n/a"))
            continue
        oc = r.get("outcome")
        if oc == "RETRIEVAL_FAILURE":
            out.append(_row("rag", cid, "RETRIEVAL", EXTRACTED,
                            "outcome=RETRIEVAL_FAILURE",
                            "gold %s, retrieved %s" % (r.get("gold_doc_ids"),
                                                       r.get("retrieved")),
                            "answer_correct (no threshold)"))
        elif oc in ("MODEL_FAILURE", "OVER_ABSTENTION", "FABRICATION",
                    "NON_ANSWER"):
            out.append(_row("rag", cid, "MODEL", EXTRACTED, "outcome=%s" % oc,
                            "", "fabricated_financial_data_count_max"
                            if oc == "FABRICATION" else "answer_correct"))
        if r.get("persian_script") is False:
            out.append(_row("rag", cid, "MODEL", EXTRACTED,
                            "Persian question answered outside Persian script "
                            "(outcome=%s hides it)" % oc,
                            reply[:80], "persian (no threshold)"))
        # -- claims, re-verified exactly as regrade_citations.py does -------
        if not reply.strip() or L.is_abstention(reply):
            continue
        claims = L.split_claims(reply)
        if not claims:
            continue
        passages = list(index.search(g["query"], top_k=top_k).hits)
        for c in claims:
            stats = [verify_claim(c, p).status for p in passages]
            if "SUPPORTED" in stats:
                continue
            cls, conf, rule, det = _claim_cause(
                c, passages, set(g.get("gold_doc_ids") or []))
            out.append(_row("rag", cid, cls, conf, rule,
                            "claim %r -> %s" % (c[:90], det),
                            "citation_correctness_pct_min / "
                            "unsupported_claim_rate_pct_max"))
    return out


# ---------------------------------------------------------------------------
# thresholds
# ---------------------------------------------------------------------------
def counterfactuals(run, rows, cases=None):
    """
    COMPUTED: each failing per-case threshold with only MODEL-caused failures
    left in. Not a verdict -- it answers "how much of this FAIL is the model?".
    """
    s = run.get("summaries") or {}
    out = OrderedDict()
    for arm in ("plain", "tools"):
        a = s.get(arm) or {}
        n = a.get("correct_abstention_n")
        if n:
            miss = [r for r in rows if r["arm"] == arm
                    and r["threshold"] == "correct_abstention_pct_min"]
            model = [r for r in miss if r["cause"] == "MODEL"]
            out["correct_abstention_pct.%s" % arm] = {
                "recorded": a.get("correct_abstention_pct"),
                "misses": len(miss), "model_caused": len(model),
                "if_only_model_failures_counted": round(
                    100.0 * (n - len(model)) / n, 2)}
        fab = [r for r in rows if r["arm"] == arm
               and r["threshold"] == "fabricated_financial_data_count_max"]
        out["fabricated_financial_data_count.%s" % arm] = {
            "recorded": a.get("fabricated_financial_data_count"),
            "model_caused": len([r for r in fab if r["cause"] == "MODEL"])}
        n = a.get("deterministic_calc_n")
        if n:
            calc = [r for r in rows if r["arm"] == arm and r["threshold"]
                    == "deterministic_calc_correctness_pct_min"]
            model = [r for r in calc if r["cause"] == "MODEL"]
            cur = None
            if cases:
                calc_rows = [x for x in (run.get("arms") or {}).get(arm, [])
                             if x.get("value_expected") is not None]
                ok = [x for x in calc_rows
                      if current_value_ok(x, cases.get(x["id"]))]
                cur = round(100.0 * len(ok) / len(calc_rows), 2) if calc_rows else None
            out["deterministic_calc_correctness_pct.%s" % arm] = {
                "recorded": a.get("deterministic_calc_correctness_pct"),
                "current_grader": cur,
                "misses": len(calc), "model_caused": len(model),
                "if_only_model_failures_counted": round(
                    100.0 * (n - len(model)) / n, 2)}
    cit = [r for r in rows if r["arm"] == "rag" and "citation" in r["threshold"]]
    out["rag_claims_not_supported"] = dict(Counter(r["cause"] for r in cit))
    return out


def attribute(run, index, gold, verdict=None, top_k=4, cases=None):
    arms = run.get("arms") or {}
    rows, nodiscrim = [], []
    for arm in ("plain", "tools"):
        r, n = attribute_eval(arm, arms.get(arm) or [], cases)
        rows += r
        nodiscrim += n
    rows += attribute_rag(arms.get("rag") or [], index, gold, top_k)

    thresholds = []
    if verdict:
        for t in verdict.get("results", []):
            if t["verdict"] != "FAIL":
                continue
            name = t["threshold"]
            if name in HARDWARE_THRESHOLDS:
                causes = {"HARDWARE": len(t.get("observations") or [])}
            else:
                key = name.rsplit("_", 1)[0]
                causes = dict(Counter(
                    r["cause"] for r in rows
                    if key in r["threshold"] or name in r["threshold"]))
            thresholds.append(OrderedDict([
                ("threshold", name), ("verdict", "FAIL"),
                ("deciding", t.get("deciding")), ("causes", causes),
                ("model_only", set(causes) == {"MODEL"}),
                ("fine_tuning_could_address",
                 "MODEL" in causes and "HARDWARE" not in causes)]))

    by_cause = Counter(r["cause"] for r in rows)
    return OrderedDict([
        ("label", "COMPUTED_FAILURE_ATTRIBUTION"),
        ("computed_by", "scripts/attribute_failures.py"),
        ("run_file", run.get("_source")),
        ("model_re_run", False),
        ("grader_changed", False),
        ("cause_classes", list(CLASSES)),
        ("totals_by_cause", OrderedDict((c, by_cause.get(c, 0)) for c in CLASSES)),
        ("needs_human", [r["arm"] + "::" + r["id"] for r in rows
                         if r["needs_human"]]),
        ("rows", rows),
        ("passes_that_cannot_discriminate", nodiscrim),
        ("failing_thresholds", thresholds),
        ("counterfactual_model_only", counterfactuals(run, rows, cases)),
        ("scope_limit", "Attribution only. No grader, threshold or verdict is "
                        "changed; the official verdict remains "
                        "scripts/grade_merged.py's. Counterfactuals are "
                        "COMPUTED, not MEASURED, and are not a re-grade."),
    ])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("run")
    ap.add_argument("--corpus", default=os.path.join(
        ROOT, "evals", "rag_corpus_combined.jsonl"))
    ap.add_argument("--gold", default=os.path.join(
        ROOT, "evals", "rag_gold_combined.jsonl"))
    ap.add_argument("--eval", default=os.path.join(
        ROOT, "evals", "bilingual_eval_v1.jsonl"))
    ap.add_argument("--verdict", default=None)
    ap.add_argument("--top-k", type=int, default=4)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)

    RP = _load_runner()
    run = json.load(open(a.run, encoding="utf-8"))
    run["_source"] = os.path.basename(a.run)
    index = RP.build_index(RP.load_jsonl(a.corpus))
    gold = {g["id"]: g for g in RP.load_jsonl(a.gold)}
    verdict = json.load(open(a.verdict, encoding="utf-8")) if a.verdict else None
    cases = {c["id"]: c for c in RP.load_jsonl(a.eval)}
    res = attribute(run, index, gold, verdict, a.top_k, cases)

    p = print
    p("=" * 78)
    p("PHASE 4 FAILURE ATTRIBUTION -- COMPUTED from recorded output, model NOT re-run")
    p("=" * 78)
    for r in res["rows"]:
        p("  %-5s %-14s %-9s [%s]%s %s"
          % (r["arm"], r["id"], r["cause"], r["confidence"][:3],
             " (needs human)" if r["needs_human"] else "", r["rule"][:70]))
    p("")
    p("  totals: " + ", ".join("%s %d" % kv for kv in res["totals_by_cause"].items()))
    if res["passes_that_cannot_discriminate"]:
        p("  passes that cannot discriminate (FIXTURE): " + ", ".join(
            "%s::%s" % (r["arm"], r["id"])
            for r in res["passes_that_cannot_discriminate"]))
    if res["failing_thresholds"]:
        p("")
        p("  FAILING THRESHOLDS by cause:")
        for t in res["failing_thresholds"]:
            p("    %-40s %s%s" % (t["threshold"], dict(t["causes"]),
                                  "  <- fine-tuning could address part"
                                  if t["fine_tuning_could_address"] else ""))
    p("")
    p("  COUNTERFACTUAL (COMPUTED, not a verdict): only MODEL-caused failures kept")
    for k, v in res["counterfactual_model_only"].items():
        p("    %-44s %s" % (k, v))
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump(res, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        p("\nwritten: %s" % a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
