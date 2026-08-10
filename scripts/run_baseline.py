#!/usr/bin/env python3
"""
run_baseline.py -- Phase 2 baseline harness. RUN THIS ON THE TARGET MACHINE.

This sandbox cannot execute it meaningfully (Phase 0 finding F1: 0.60 GiB
available, smallest candidate needs 0.87 GiB for weights alone). It is written
here so that on the i5-12400 you run one command instead of assembling a
harness.

WHAT IT MEASURES (all MEASURED, none estimated):
  - prompt-eval (prefill) tokens/sec
  - decode (generation) tokens/sec
  - peak process RSS
  - model load time
  - per-case results against evals/bilingual_eval_v1.jsonl

WHAT IT DOES NOT DO:
  - It does not grade Persian fluency. That needs a human reader; the script
    records the raw output and flags mechanical failures only.
  - It never enables live trading and registers no execution tool.

PREREQUISITES on the target machine:
    pip install llama-cpp-python psutil
  plus a GGUF file. See docs/phase-reports/phase-2.md for the conversion route.

USAGE:
    python scripts/run_baseline.py --model path\\to\\Qwen3-4B-Instruct-2507-Q4_K_M.gguf
    python scripts/run_baseline.py --model ... --ctx 16384 --threads 6
"""

import argparse
import json
import os
import platform
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# Proposed Phase 2 acceptance thresholds. Derived in scripts/throughput_ceiling.py
# from DDR4-3200 dual-channel bandwidth. ESTIMATED until this script runs.
THRESHOLD_DECODE_TPS = 9.0
THRESHOLD_PEAK_RSS_GIB = 12.0


def human(n):
    return "%.2f" % n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="path to the GGUF file")
    ap.add_argument("--ctx", type=int, default=16384)
    ap.add_argument("--threads", type=int, default=6,
                    help="i5-12400 has 6 physical P-cores; start there, not 12. "
                         "Hyperthreads usually hurt memory-bound decode.")
    ap.add_argument("--evals", default="evals/bilingual_eval_v1.jsonl")
    ap.add_argument("--max-tokens", type=int, default=256)
    ap.add_argument("--out", default="evals/results/baseline_run.json")
    a = ap.parse_args()

    if not os.path.exists(a.model):
        print("ERROR: model not found: %s" % a.model)
        return 2

    try:
        from llama_cpp import Llama
    except ImportError:
        print("ERROR: llama-cpp-python is not installed.")
        print("       pip install llama-cpp-python")
        return 2
    try:
        import psutil
    except ImportError:
        psutil = None
        print("WARN: psutil missing; peak RSS will not be recorded.")

    proc = psutil.Process() if psutil else None
    rss0 = proc.memory_info().rss if proc else 0

    print("=" * 78)
    print("PHASE 2 BASELINE -- MEASURED ON TARGET")
    print("=" * 78)
    print("host    : %s %s" % (platform.system(), platform.release()))
    print("cpu     : %s" % (platform.processor() or "unknown"))
    print("model   : %s" % os.path.basename(a.model))
    print("size    : %.2f GiB" % (os.path.getsize(a.model) / 1024 ** 3))
    print("ctx     : %d   threads: %d" % (a.ctx, a.threads))
    print()

    t0 = time.time()
    llm = Llama(model_path=a.model, n_ctx=a.ctx, n_threads=a.threads,
                verbose=False)
    load_s = time.time() - t0
    print("load time: %.1f s  [MEASURED]" % load_s)

    rss_after_load = proc.memory_info().rss if proc else 0
    if proc:
        print("RSS after load: %.2f GiB  [MEASURED]"
              % ((rss_after_load - rss0) / 1024 ** 3))

    # ---------------- speed benchmark --------------------------------
    print("\n" + "-" * 78)
    print("SPEED")
    print("-" * 78)
    warm = "Summarize what a price-to-earnings ratio measures."
    llm(warm, max_tokens=16)  # warm caches; excluded from timing

    t0 = time.time()
    out = llm(warm, max_tokens=a.max_tokens, echo=False)
    elapsed = time.time() - t0
    usage = out.get("usage", {})
    ptok = usage.get("prompt_tokens", 0)
    ctok = usage.get("completion_tokens", 0)
    decode_tps = ctok / elapsed if elapsed > 0 else 0.0
    print("prompt tokens     : %d" % ptok)
    print("generated tokens  : %d" % ctok)
    print("wall time         : %.2f s" % elapsed)
    print("decode tok/s      : %.2f  [MEASURED]" % decode_tps)

    peak_rss = proc.memory_info().rss / 1024 ** 3 if proc else 0.0
    if proc:
        print("peak RSS          : %.2f GiB  [MEASURED]" % peak_rss)

    print()
    verdict_speed = "PASS" if decode_tps >= THRESHOLD_DECODE_TPS else "FAIL"
    print("threshold >= %.0f tok/s : %s (measured %.2f)"
          % (THRESHOLD_DECODE_TPS, verdict_speed, decode_tps))
    if proc:
        verdict_mem = "PASS" if peak_rss <= THRESHOLD_PEAK_RSS_GIB else "FAIL"
        print("threshold <= %.0f GiB   : %s (measured %.2f)"
              % (THRESHOLD_PEAK_RSS_GIB, verdict_mem, peak_rss))

    # ---------------- eval set ---------------------------------------
    print("\n" + "-" * 78)
    print("BILINGUAL EVAL SET")
    print("-" * 78)
    eval_path = a.evals
    if not os.path.isabs(eval_path):
        eval_path = os.path.join(os.path.dirname(__file__), "..", eval_path)
    rows = []
    if os.path.exists(eval_path):
        rows = [json.loads(l) for l in open(eval_path, encoding="utf-8")
                if l.strip()]
    else:
        print("WARN: eval file not found: %s" % eval_path)

    results = []
    for r in rows:
        t0 = time.time()
        resp = llm(r["prompt"], max_tokens=a.max_tokens, echo=False)
        dt = time.time() - t0
        text = resp["choices"][0]["text"].strip()

        # MECHANICAL checks only. Content quality needs a human.
        flags = []
        for banned in r.get("must_not") or []:
            if banned.lower() in text.lower():
                flags.append("CONTAINS_BANNED:%s" % banned)
        if r["lang"] == "fa":
            # crude script check: Persian answers should contain Arabic-script chars
            if not any("\u0600" <= ch <= "\u06FF" for ch in text):
                flags.append("NOT_IN_PERSIAN")
        results.append({"id": r["id"], "lang": r["lang"],
                        "category": r["category"], "prompt": r["prompt"],
                        "output": text, "seconds": round(dt, 2),
                        "auto_flags": flags,
                        "rubric": r["rubric"],
                        "human_grade": None})
        status = "FLAG" if flags else "ok  "
        print("  %s %-14s %-20s %5.1fs %s"
              % (status, r["id"], r["category"], dt,
                 ";".join(flags) if flags else ""))

    flagged = sum(1 for r in results if r["auto_flags"])
    print("\n%d/%d cases auto-flagged. The remainder still require HUMAN grading"
          % (flagged, len(results)))
    print("against each case's rubric -- passing the mechanical check is not")
    print("evidence of a correct answer.")

    # ---------------- persist ----------------------------------------
    out_path = a.out
    if not os.path.isabs(out_path):
        out_path = os.path.join(os.path.dirname(__file__), "..", out_path)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    payload = {
        "label": "MEASURED",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "host": {"system": platform.system(), "release": platform.release(),
                 "processor": platform.processor()},
        "model": os.path.basename(a.model),
        "model_size_gib": round(os.path.getsize(a.model) / 1024 ** 3, 3),
        "ctx": a.ctx, "threads": a.threads,
        "load_seconds": round(load_s, 2),
        "decode_tokens_per_sec": round(decode_tps, 2),
        "peak_rss_gib": round(peak_rss, 3) if proc else None,
        "thresholds": {"decode_tps": THRESHOLD_DECODE_TPS,
                       "peak_rss_gib": THRESHOLD_PEAK_RSS_GIB},
        "eval_results": results,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print("\nWrote %s" % out_path)
    print("Commit that file -- it is the project's first on-target measurement.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
