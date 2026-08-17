#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_phase4.py -- Phase 4 measurement harness. RUN THIS ON THE i5-12400.

    python scripts\\run_phase4.py --model C:\\models\\Qwen3-4B-Instruct-2507-Q4_K_M.gguf

WHY THIS EXISTS AND scripts/run_baseline.py DOES NOT SUFFICE
------------------------------------------------------------
run_baseline.py was written in Phase 2, has never been executed, and an audit
on 2026-08-15 MEASURED nine defects in it. Three matter enough to name:

  1. It grades peak RSS against 12.0 GiB. The APPROVED ceiling is 6.0 GiB.
     It would have printed PASS at twice the limit the user approved.
  2. It never reads expected_value, expected_tool or tolerance, although 8, 10
     and 8 of the 21 eval cases carry them. It graded no correctness at all.
  3. It prints Persian prompts. MEASURED: Persian cannot be encoded in cp1252
     or cp437, which is what a default Windows console uses, so it crashes
     partway through -- after the model has already been loaded and run.

WHAT THIS HARNESS MEASURES (Phase 4's seven tasks)
--------------------------------------------------
  task 1  three arms: plain / +tools / +RAG, over the same prompts
  task 2  retrieval hit rate against evals/rag_gold_v1.jsonl
  task 3  citation correctness via src/rag/citations.verify_claim
  task 4  unsupported-claim rate from the same citation pass
  task 5  latency (TTFT at 2K, decode tok/s) and peak RSS
  task 6  MODEL_FAILURE vs RETRIEVAL_FAILURE, kept apart per case
  task 7  inputs for the fine-tuning decision -- NOT the decision itself

WHAT IT DOES NOT DO, ON PURPOSE
--------------------------------
  - It does not grade Persian fluency or rubric compliance. Those need a human
    reader (R10). Those fields are written as null and reported PENDING_HUMAN.
    A harness that scored them itself would be certifying quality it never
    inspected.
  - It registers NO execution tool and cannot place an order. The tool registry
    contains 84 calculators and zero brokers; the harness asserts this at
    startup and refuses to run if it ever stops being true.
  - It decides nothing. It writes numbers. Phase 4's task 7 decision is taken
    by the user, after reading them.

PREREQUISITES on the target machine
-----------------------------------
    pip install llama-cpp-python psutil
    plus one GGUF file. See docs/guides/phase-4-windows-setup-fa.md.

OUTPUT
------
One JSON file (default evals/results/phase4_run.json). Send that file back.
It is the project's first on-target measurement; every number in it is
labelled MEASURED, COMPUTED or UNKNOWN.
"""

import argparse
import json
import os
import platform
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "src"))
sys.path.insert(0, _HERE)

import phase4_lib as L  # noqa: E402

# Make the console safe BEFORE anything Persian can reach it.
CONSOLE_UTF8 = L.make_console_safe()


def p(text=""):
    """Print a line that cannot crash the run on a cp1252 console."""
    print(L.safe(text))


def rel(path):
    """Resolve a repo-relative path against the repo root, not the cwd."""
    if os.path.isabs(path):
        return path
    return os.path.join(_ROOT, path)


# ---------------------------------------------------------------------------
# Model wrapper.
#
# Every call to the model goes through here, so the fake used by the test suite
# has exactly one surface to imitate. That is what makes this harness testable
# without a 2.5 GiB download.
# ---------------------------------------------------------------------------

class ModelRunner(object):
    """Thin wrapper over llama_cpp.Llama that records timing per call."""

    def __init__(self, llm, max_tokens=256):
        self.llm = llm
        self.max_tokens = max_tokens
        self.calls = 0

    def generate(self, prompt, max_tokens=None):
        """
        Returns (text, metrics). Metrics are MEASURED, never estimated.

        `ttft_s` is measured by asking for ONE token and timing it. Streaming
        would be a truer measure, but it is not available uniformly across
        llama-cpp-python versions, and a metric that works on the user's actual
        build beats a better one that raises AttributeError on it.
        """
        self.calls += 1
        n = max_tokens or self.max_tokens
        t0 = time.time()
        out = self.llm(prompt, max_tokens=n, echo=False)
        elapsed = time.time() - t0
        try:
            text = out["choices"][0]["text"]
        except (KeyError, IndexError, TypeError):
            raise RuntimeError("model returned an unrecognised payload: %r"
                               % (type(out).__name__,))
        usage = out.get("usage", {}) or {}
        ctok = usage.get("completion_tokens", 0)
        ptok = usage.get("prompt_tokens", 0)
        return text.strip(), {
            "seconds": round(elapsed, 3),
            "prompt_tokens": ptok,
            "completion_tokens": ctok,
            "decode_tps": (round(ctok / elapsed, 2)
                           if elapsed > 0 and ctok else None),
        }


def peak_rss_gib(proc):
    """
    Peak RSS in GiB, preferring a TRUE peak over a point sample.

    On Windows psutil exposes peak_wset, the high-water mark the OS itself
    recorded. memory_info().rss is only whatever happened to be resident at the
    instant we asked -- it can miss the peak entirely, and reporting it as
    "peak" against a 6.0 GiB approved ceiling would be a false pass.
    """
    if proc is None:
        return None, "UNKNOWN"
    mi = proc.memory_info()
    peak = getattr(mi, "peak_wset", None)
    if peak:
        return round(peak / 1024.0 ** 3, 3), "MEASURED_PEAK"
    return round(mi.rss / 1024.0 ** 3, 3), "MEASURED_POINT_SAMPLE"


# ---------------------------------------------------------------------------
# Prompt construction for the three arms.
# ---------------------------------------------------------------------------

SYSTEM_BASE = (
    "You are a bilingual Persian-English financial analyst. Answer in the "
    "language of the question. If you do not have the information needed, say "
    "so plainly instead of guessing. Never invent a figure."
)

SYSTEM_TOOLS = SYSTEM_BASE + (
    "\n\nYou may call a calculation tool. To do so emit exactly:\n"
    "<tool_call>{\"name\": \"<tool>\", \"arguments\": {...}}</tool_call>\n"
    "Use a tool for any arithmetic rather than computing it yourself.\n"
    "Available tools:\n"
)

SYSTEM_RAG = SYSTEM_BASE + (
    "\n\nAnswer ONLY from the evidence passages provided below. If the "
    "evidence does not contain the answer, say that you do not have it. Do "
    "not use anything you remember about these companies."
)


def build_plain_prompt(question):
    return "%s\n\nQuestion: %s\nAnswer:" % (SYSTEM_BASE, question)


def build_tools_prompt(question, schemas):
    lines = []
    for s in schemas:
        fn = s.get("function", s)
        req = ", ".join(fn.get("parameters", {}).get("required", []))
        lines.append("- %s(%s): %s" % (fn.get("name"), req,
                                       fn.get("description", "")))
    return "%s%s\n\nQuestion: %s\nAnswer:" % (
        SYSTEM_TOOLS, "\n".join(lines), question)


def build_rag_prompt(question, passages):
    ev = []
    for i, ps in enumerate(passages, 1):
        ev.append("[%d] (%s) %s" % (i, ps.provenance.citation(), ps.text))
    return "%s\n\nEvidence:\n%s\n\nQuestion: %s\nAnswer:" % (
        SYSTEM_RAG, "\n".join(ev) if ev else "(no evidence retrieved)",
        question)


# ---------------------------------------------------------------------------
# Corpus loading.
# ---------------------------------------------------------------------------

def load_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def build_index(corpus_rows):
    """Index the fixture corpus using the project's real RAG code."""
    from rag.documents import Provenance, Passage
    from rag.retrieval import PassageIndex
    from rag.sources import get_source

    idx = PassageIndex()
    for r in corpus_rows:
        src = get_source(r["source_key"])
        prov = Provenance(source=src.key, trust_level=src.trust_level,
                          filed=r.get("filed"), accession=r.get("accession"),
                          url=src.base_url, licence=src.licence)
        idx.add(Passage(text=r["text"], provenance=prov,
                        section_path=r.get("section_path", ()),
                        entity=r.get("entity"), entity_id=r.get("entity_id"),
                        period_start=r.get("period_start"),
                        period_end=r.get("period_end"),
                        lang=r.get("lang"), doc_id=r["doc_id"],
                        chunk_index=r.get("chunk_index", 0),
                        units_note=r.get("units_note")))
    return idx


def assert_no_execution_capability():
    """
    Refuse to run if the tool registry has grown anything that trades.

    SS: live submission stays disabled and unreachable. The harness is the one
    place in this project that will feed model-chosen tool names into
    call_tool, so it verifies the registry before doing so rather than trusting
    that a Phase 2 assertion still holds.
    """
    from tools.registry import tool_names
    banned = ("order", "submit", "buy", "sell", "execute", "trade", "broker",
              "place", "cancel", "withdraw", "transfer")
    found = [t for t in tool_names()
             if any(b in t.lower() for b in banned)]
    if found:
        raise RuntimeError(
            "REFUSING TO RUN: the tool registry exposes what look like "
            "execution tools: %s. Phase 4 evaluates analysis only." % found)
    return len(tool_names())


# ---------------------------------------------------------------------------
# The three arms.
# ---------------------------------------------------------------------------

def run_arm_plain(runner, cases, schemas_by_name):
    out = []
    for c in cases:
        text, m = runner.generate(build_plain_prompt(c["prompt"]))
        g = L.grade_case(c, text, schemas_by_name)
        g["arm"] = "plain"
        # The QUESTION is written to the file, not just the answer. Every case
        # carries human_grade=None and persian_fluency_regression is PENDING
        # until a person reads this file -- and a person cannot grade an answer
        # without seeing what was asked. MEASURED 2026-08-15: the file was
        # previously unreadable for grading for exactly this reason.
        g["question"] = c["prompt"]
        g["output"] = text
        g["metrics"] = m
        out.append(g)
        p("  %-14s %-20s %5.1fs %s" % (
            c["id"], c["category"], m["seconds"], _flagline(g)))
    return out


def run_arm_tools(runner, cases, schemas_by_name):
    from tools.selector import schemas_for
    from tools.registry import call_tool
    out = []
    for c in cases:
        schemas = schemas_for(c["prompt"])
        text, m = runner.generate(build_tools_prompt(c["prompt"], schemas))
        g = L.grade_case(c, text, schemas_by_name)
        g["arm"] = "tools"
        g["question"] = c["prompt"]
        g["output"] = text
        g["metrics"] = m
        g["schemas_offered"] = len(schemas)

        # Execute whatever the model actually asked for, and record what came
        # back. This is what turns "the model emitted a tool call" into "the
        # tool produced the right number" -- Phase 4 task 1's real question.
        executed = []
        for call in L.parse_tool_calls(text)[0]:
            res = call_tool(call["name"], call["arguments"])
            executed.append({"name": call["name"],
                             "arguments": call["arguments"],
                             "ok": res.get("ok"),
                             "value": res.get("value"),
                             "error": res.get("error")})
        g["executed"] = executed

        # If a tool produced the right value, the ANSWER is right even when the
        # model's prose has not yet restated it. Recording that separately
        # keeps tool-routing success distinct from prose quality.
        if c.get("expected_value") is not None:
            tol = c.get("tolerance")
            g["tool_value_ok"] = any(
                e["ok"] and e["value"] is not None
                and abs(float(e["value"]) - float(c["expected_value"]))
                <= (0.0 if tol is None else abs(float(tol)))
                for e in executed)
        else:
            g["tool_value_ok"] = None
        out.append(g)
        p("  %-14s %-20s %5.1fs %s" % (
            c["id"], c["category"], m["seconds"], _flagline(g)))
    return out


def run_arm_rag(runner, gold_rows, index, top_k):
    from rag.citations import verify_claim
    out = []
    for gold in gold_rows:
        res = index.search(gold["query"], top_k=top_k)
        passages = list(res.hits)
        text, m = runner.generate(build_rag_prompt(gold["query"], passages))

        # Verify the answer's numbers against the evidence ACTUALLY shown to
        # the model -- not against the gold passage. Checking against evidence
        # the model never saw would measure the gold set, not the model.
        citations = []
        if text.strip() and not L.is_abstention(text):
            for ps in passages:
                c = verify_claim(text, ps)
                citations.append({"status": c.status,
                                  "doc_id": ps.doc_id,
                                  "detail": c.detail[:160]})
            # One SUPPORTED passage is enough to ground the answer; keep the
            # best outcome plus the count so the rate is honest.
            best = "SUPPORTED" if any(
                c["status"] == "SUPPORTED" for c in citations) else (
                "CONTRADICTED" if any(
                    c["status"] == "CONTRADICTED" for c in citations)
                else "UNSUPPORTED")
            citations = [{"status": best,
                          "n_passages_checked": len(passages),
                          "per_passage": citations}]

        g = L.grade_rag_case(gold, text, [h.doc_id for h in passages],
                             citations)
        g["arm"] = "rag"
        g["question"] = gold["query"]
        g["output"] = text
        g["metrics"] = m
        out.append(g)
        p("  %-14s %-18s %5.1fs retrieval=%s outcome=%s" % (
            gold["id"], gold["lang"], m["seconds"],
            g["retrieval_ok"], g["outcome"]))
    return out


def _flagline(g):
    bits = []
    if g.get("value_ok") is True:
        bits.append("value=OK")
    elif g.get("value_ok") is False:
        bits.append("value=WRONG")
    if g.get("tool_ok") is True:
        bits.append("tool=OK")
    elif g.get("tool_ok") is False:
        bits.append("tool=MISS")
    if g.get("abstention_ok") is True:
        bits.append("abstain=OK")
    elif g.get("abstention_ok") is False:
        bits.append("abstain=FAIL")
    if g.get("banned_hits"):
        bits.append("BANNED:%d" % len(g["banned_hits"]))
    if g.get("empty_output"):
        bits.append("EMPTY")
    return " ".join(bits)


# ---------------------------------------------------------------------------
# Latency measurement (task 5).
# ---------------------------------------------------------------------------

def measure_latency(runner, ctx_target=2048):
    """
    TTFT at ~2K prompt tokens, and sustained decode tok/s.

    The approved threshold is time_to_first_token_2k_sec_max = 3.0, so the
    prompt has to actually be about 2K tokens. Measuring TTFT on a short prompt
    and reporting it against a 2K threshold would be a fabricated pass.
    """
    filler = ("A price-to-earnings ratio divides price by earnings per share. "
              "It is a valuation multiple, not a measure of quality. ")
    # ~14 tokens per repetition; overshoot slightly then report the MEASURED
    # prompt_tokens so the reader can see what was actually used.
    prompt = (filler * (ctx_target // 12)) + "\n\nQuestion: What is a P/E ratio?\nAnswer:"

    _t, m1 = runner.generate(prompt, max_tokens=1)
    ttft = m1["seconds"]
    ptok = m1["prompt_tokens"]

    _t2, m2 = runner.generate("Explain what a price-to-earnings ratio "
                              "measures, in detail.", max_tokens=128)
    return {
        "ttft_seconds": round(ttft, 3),
        "ttft_prompt_tokens": ptok,
        "ttft_prompt_tokens_target": ctx_target,
        "ttft_measured_at_2k": (ptok >= ctx_target * 0.8
                                if ptok else None),
        "decode_tokens_per_sec": m2["decode_tps"],
        "decode_completion_tokens": m2["completion_tokens"],
        "label": "MEASURED",
    }


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Phase 4 measurement harness (run on the target machine)")
    ap.add_argument("--model", required=True, help="path to the GGUF file")
    ap.add_argument("--ctx", type=int, default=16384)
    ap.add_argument("--threads", type=int, default=6,
                    help="i5-12400 has 6 physical P-cores; hyperthreads "
                         "usually hurt memory-bound decode")
    ap.add_argument("--evals", default="evals/bilingual_eval_v1.jsonl")
    ap.add_argument("--corpus", default="evals/rag_corpus_v1.jsonl")
    ap.add_argument("--gold", default="evals/rag_gold_v1.jsonl")
    ap.add_argument("--state", default="PROJECT_STATE.json")
    ap.add_argument("--max-tokens", type=int, default=256)
    ap.add_argument("--top-k", type=int, default=4)
    ap.add_argument("--out", default="evals/results/phase4_run.json")
    ap.add_argument("--arms", default="plain,tools,rag",
                    help="comma-separated subset, for resuming a run")
    a = ap.parse_args(argv)

    if not os.path.isfile(a.model):
        p("ERROR: model file not found: %s" % a.model)
        return 2

    try:
        from llama_cpp import Llama
    except ImportError:
        p("ERROR: llama-cpp-python is not installed.")
        p("       pip install llama-cpp-python")
        return 2
    try:
        import psutil
    except ImportError:
        psutil = None
        p("WARN: psutil missing; peak RSS will be reported as UNKNOWN, not as")
        p("      a pass. Install it with: pip install psutil")

    n_tools = assert_no_execution_capability()
    thresholds = L.load_thresholds(rel(a.state))

    proc = psutil.Process() if psutil else None
    model_size_gib = round(os.path.getsize(a.model) / 1024.0 ** 3, 3)

    p("=" * 78)
    p("PHASE 4 -- RAG AND TOOL-ENABLED EVALUATION (MEASURED ON TARGET)")
    p("=" * 78)
    p("host        : %s %s" % (platform.system(), platform.release()))
    p("cpu         : %s" % (platform.processor() or "unreported by OS"))
    p("python      : %s" % platform.python_version())
    p("console utf8: %s" % CONSOLE_UTF8)
    p("model       : %s" % os.path.basename(a.model))
    p("size        : %.3f GiB" % model_size_gib)
    # Hash BEFORE loading. It costs seconds on a GiB-sized file and it is the
    # only thing that ties the numbers below to specific weights. Printed too,
    # because the user should see what they are about to measure.
    model_identity = L.identify_model(a.model)
    p("sha256      : %s" % model_identity["sha256"])
    p("identity    : %s" % model_identity["label"])
    if model_identity.get("is_pinned_revision") is False:
        p("              NOTE: %s" % model_identity["note"])
    elif model_identity["label"] == "UNKNOWN":
        p("              NOTE: %s" % model_identity["note"])
    p("ctx         : %d   threads: %d   top_k: %d" % (a.ctx, a.threads, a.top_k))
    p("tools       : %d registered, 0 of them can execute a trade" % n_tools)
    p("")

    t0 = time.time()
    llm = Llama(model_path=a.model, n_ctx=a.ctx, n_threads=a.threads,
                verbose=False)
    load_s = round(time.time() - t0, 2)
    p("load time   : %.1f s  [MEASURED]" % load_s)

    runner = ModelRunner(llm, max_tokens=a.max_tokens)
    from tools.registry import tool_schemas
    schemas_by_name = {}
    for s in tool_schemas():
        fn = s.get("function", s)
        schemas_by_name[fn["name"]] = fn

    arms = [x.strip() for x in a.arms.split(",") if x.strip()]
    report = {"arms": {}, "summaries": {}}

    # ---- task 5: latency ------------------------------------------------
    p("")
    p("-" * 78)
    p("LATENCY AND MEMORY  (task 5)")
    p("-" * 78)
    lat = measure_latency(runner)
    p("TTFT @ %d prompt tokens : %.2f s  [MEASURED]"
      % (lat["ttft_prompt_tokens"], lat["ttft_seconds"]))
    p("decode tok/s            : %s  [MEASURED]"
      % lat["decode_tokens_per_sec"])
    if lat["ttft_measured_at_2k"] is False:
        p("WARN: the TTFT prompt came out at %d tokens, short of the 2K the"
          % lat["ttft_prompt_tokens"])
        p("      threshold refers to. Reported, not silently accepted.")

    cases = load_jsonl(rel(a.evals))
    gold_rows = load_jsonl(rel(a.gold))
    corpus = load_jsonl(rel(a.corpus))
    index = build_index(corpus)

    if "plain" in arms:
        p("")
        p("-" * 78)
        p("ARM 1/3  PLAIN BASELINE  (no tools, no evidence)  [%d cases]"
          % len(cases))
        p("-" * 78)
        report["arms"]["plain"] = run_arm_plain(runner, cases, schemas_by_name)
        report["summaries"]["plain"] = L.summarize_eval(
            report["arms"]["plain"])

    if "tools" in arms:
        p("")
        p("-" * 78)
        p("ARM 2/3  TOOLS ENABLED  [%d cases]" % len(cases))
        p("-" * 78)
        report["arms"]["tools"] = run_arm_tools(runner, cases, schemas_by_name)
        report["summaries"]["tools"] = L.summarize_eval(
            report["arms"]["tools"])

    if "rag" in arms:
        p("")
        p("-" * 78)
        p("ARM 3/3  RAG  [%d gold cases over %d passages]"
          % (len(gold_rows), len(corpus)))
        p("-" * 78)
        report["arms"]["rag"] = run_arm_rag(runner, gold_rows, index, a.top_k)
        report["summaries"]["rag"] = L.summarize_rag(report["arms"]["rag"])

    peak, peak_label = peak_rss_gib(proc)

    # ---- threshold verdicts ---------------------------------------------
    ev = report["summaries"].get("tools") or report["summaries"].get("plain") or {}
    rg = report["summaries"].get("rag") or {}
    measured = {
        "model_file_size_q4km_gib_max": model_size_gib,
        "peak_rss_8k_gib_max": peak,
        "generation_tokens_per_sec_min": lat["decode_tokens_per_sec"],
        "time_to_first_token_2k_sec_max": lat["ttft_seconds"],
        "deterministic_calc_correctness_pct_min":
            ev.get("deterministic_calc_correctness_pct"),
        "unsupported_claim_rate_pct_max": rg.get("unsupported_claim_rate_pct"),
        "citation_correctness_pct_min": rg.get("citation_correctness_pct"),
        "correct_abstention_pct_min": ev.get("correct_abstention_pct"),
        "fabricated_financial_data_count_max":
            rg.get("fabricated_financial_data_count"),
        # Persian fluency regression needs a human reader and a prior
        # measurement to regress against. Neither exists yet -> PENDING.
        "persian_fluency_regression_pct_max": None,
        "tool_call_schema_validity_pct_min":
            ev.get("tool_call_schema_validity_pct"),
        # No order was placeable: the registry has no execution tool. Zero here
        # is MEASURED, not assumed -- assert_no_execution_capability() ran.
        "paper_live_confusion_count_max": 0,
    }
    verdicts = [L.grade_threshold(k, measured.get(k), v)
                for k, v in sorted(thresholds.items())]

    p("")
    p("=" * 78)
    p("APPROVED THRESHOLDS  (limits read from PROJECT_STATE.json)")
    p("=" * 78)
    for v in verdicts:
        p("  %-8s %-42s limit %-8s measured %s"
          % (v["verdict"], v["threshold"], v["limit"],
             "n/a" if v["measured"] is None else v["measured"]))
    n_fail = len([v for v in verdicts if v["verdict"] == "FAIL"])
    n_pend = len([v for v in verdicts if v["verdict"] == "PENDING"])
    p("")
    p("  %d PASS, %d FAIL, %d PENDING (of %d)"
      % (len(verdicts) - n_fail - n_pend, n_fail, n_pend, len(verdicts)))

    if "rag" in arms:
        p("")
        p("MODEL vs RETRIEVAL FAILURES  (task 6)")
        for k, n in sorted(rg.get("outcomes", {}).items()):
            p("  %-20s %d" % (k, n))

    p("")
    p("Persian fluency and rubric compliance are NOT graded here. Every case")
    p("carries human_grade=null and must be read by a person before Phase 4")
    p("can be called complete.")

    # ---- persist ---------------------------------------------------------
    out_path = rel(a.out)
    L.ensure_parent_dir(out_path)
    payload = {
        "label": "MEASURED",
        "phase": 4,
        "route": "A (user's own machine)",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "host": {"system": platform.system(),
                 "release": platform.release(),
                 "processor": platform.processor() or None,
                 "python": platform.python_version(),
                 "console_utf8": CONSOLE_UTF8},
        "model": {"file": os.path.basename(a.model),
                  "size_gib": model_size_gib,
                  "ctx": a.ctx, "threads": a.threads,
                  "load_seconds": load_s,
                  "max_tokens": a.max_tokens,
                  # WHICH weights produced these numbers, by content hash.
                  # The GGUF the user can actually download is the original
                  # Qwen3-4B, NOT the pinned Qwen3-4B-Instruct-2507 (which
                  # publishes no GGUF). Speed and RAM transfer between them;
                  # Persian fluency and instruction-following do not. Recording
                  # only a basename would let a filename someone typed stand in
                  # for provenance.
                  "identity": model_identity},
        "tool_registry_size": n_tools,
        "latency": lat,
        "peak_rss_gib": peak,
        "peak_rss_label": peak_label,
        "thresholds_approved": thresholds,
        "threshold_verdicts": verdicts,
        "summaries": report["summaries"],
        "arms": report["arms"],
        "human_grading": {
            "status": "PENDING",
            "note": "Persian fluency, rubric compliance and unsupported-claim "
                    "judgement require a human reader (R10). No field in this "
                    "file records a human grade.",
        },
        "generated_by": "scripts/run_phase4.py",
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    p("")
    p("Wrote %s" % out_path)
    p("Send that file back. It is the project's first on-target measurement.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
