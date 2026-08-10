#!/usr/bin/env python3
"""
throughput_ceiling.py -- what the target machine CAN'T exceed, and why.

This computes an UPPER BOUND on decode speed from memory bandwidth. It is
ESTIMATED, not MEASURED. Its purpose is to set a defensible Phase 2 acceptance
threshold instead of an arbitrary one, and to make an unrealistic expectation
visible before time is spent chasing it.

WHY BANDWIDTH AND NOT FLOPS
On a GPU-less machine, autoregressive decode must read every weight of the
model from RAM to produce ONE token. At batch size 1 there is almost no
arithmetic intensity to exploit, so the CPU stalls waiting on memory. Decode
speed is therefore bounded by:

    tokens/sec <= memory_bandwidth / bytes_of_weights_read_per_token

Prefill (prompt processing) is different: it processes many tokens at once,
becomes compute-bound, and runs far faster per token. The two are reported
separately because conflating them produces nonsense expectations.

Target (VERIFIED, user-supplied): i5-12400, DDR4-3200, 16 GiB, Windows 11.
"""

import argparse
import sys

GIB = 1024 ** 3
GB = 1000 ** 3

# VERIFIED from user (Q6): DDR4-3200.
# Theoretical peak = MT/s * 8 bytes/transfer * channels.
MEM_PROFILES = {
    "DDR4-3200": {"mts": 3200, "channels": 2},
    "DDR4-2666": {"mts": 2666, "channels": 2},
    "DDR5-4800": {"mts": 4800, "channels": 2},
}

# ESTIMATED. Fraction of theoretical peak bandwidth that llama.cpp actually
# realizes on a desktop CPU. Real STREAM-triad results on dual-channel DDR4
# typically land in this band; llama.cpp's GGUF reads are near-sequential,
# which is the favourable case.
EFFICIENCY_BAND = {"conservative": 0.60, "typical": 0.70, "optimistic": 0.80}

# Candidates from Phase 1, with Q4_K_M weight sizes (COMPUTED in Phase 1).
MODELS = [
    ("Qwen3-4B-Instruct-2507 (primary)", 2.27),
    ("Phi-4-mini-instruct",              2.17),
    ("SmolLM3-3B",                       1.74),
    ("Qwen3-1.7B (fallback)",            1.15),
]


def peak_bandwidth_gbs(profile):
    p = MEM_PROFILES[profile]
    return p["mts"] * 8 * p["channels"] / 1000.0  # GB/s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mem", default="DDR4-3200", choices=list(MEM_PROFILES))
    ap.add_argument("--ctx", type=int, default=16384)
    a = ap.parse_args()

    peak = peak_bandwidth_gbs(a.mem)

    print("=" * 92)
    print("DECODE THROUGHPUT CEILING -- ESTIMATED (bandwidth-bound upper bound)")
    print("=" * 92)
    print("Memory: %s dual-channel  ->  %.1f GB/s theoretical peak" % (a.mem, peak))
    print("CPU: i5-12400 (6 P-cores / 12 threads, no E-cores, no GPU)")
    print()
    print("At batch=1 every generated token requires reading ALL weights from RAM.")
    print("This is an UPPER BOUND. Real output will be at or below it, never above.")
    print()

    print("%-34s %9s %10s %10s %10s" % ("model (Q4_K_M)", "wt GiB",
                                        "cons.", "typical", "optim."))
    print("-" * 92)
    for name, w_gib in MODELS:
        w_gb = w_gib * GIB / GB  # convert GiB -> GB to match bandwidth units
        row = []
        for k in ("conservative", "typical", "optimistic"):
            row.append(peak * EFFICIENCY_BAND[k] / w_gb)
        print("%-34s %9.2f %10.1f %10.1f %10.1f" % (name, w_gib, row[0], row[1], row[2]))

    print()
    print("Columns are tokens/sec at %.0f%% / %.0f%% / %.0f%% of peak bandwidth."
          % tuple(EFFICIENCY_BAND[k] * 100 for k in
                  ("conservative", "typical", "optimistic")))
    print()

    # --- what that feels like -------------------------------------------
    print("=" * 92)
    print("WHAT THAT MEANS IN PRACTICE (primary model, typical efficiency)")
    print("=" * 92)
    w_gb = MODELS[0][1] * GIB / GB
    tps = peak * EFFICIENCY_BAND["typical"] / w_gb
    print("Primary decode estimate: %.1f tok/s" % tps)
    print()
    for label, toks in (("short answer", 150), ("paragraph", 400),
                        ("full analysis", 1200)):
        print("  %-16s %5d tokens  ->  %5.0f s" % (label, toks, toks / tps))
    print()
    print("Reading speed is ~5-8 tok/s, so %.0f tok/s outpaces reading." % tps)
    print("The cost is felt on LONG outputs, not on chat-length replies.")
    print()

    # --- prefill --------------------------------------------------------
    print("=" * 92)
    print("PREFILL IS A SEPARATE PROBLEM")
    print("=" * 92)
    print("Prompt processing is compute-bound, not bandwidth-bound, and is")
    print("typically 5-20x faster per token than decode on CPU. But a full %s-token" % f"{a.ctx:,}")
    print("context still has to be processed before the first token appears.")
    print()
    print("This is the strongest argument for RAG discipline (Phase 3):")
    print("retrieving 2K relevant tokens instead of stuffing %s changes" % f"{a.ctx:,}")
    print("time-to-first-token by roughly the same ratio. Context is not free")
    print("just because it fits in RAM.")
    print()

    print("=" * 92)
    print("PROPOSED PHASE 2 ACCEPTANCE THRESHOLD")
    print("=" * 92)
    cons = peak * EFFICIENCY_BAND["conservative"] / w_gb
    print("Ceiling (100%% of peak, unattainable): %.1f tok/s" % (peak / w_gb))
    print("Conservative estimate:                %.1f tok/s" % cons)
    print()
    print("Proposed PASS threshold: >= %.0f tok/s decode on the primary model." % (cons * 0.75))
    print("Rationale: 75% of the conservative estimate leaves room for Windows")
    print("overhead and thread contention while still flagging a genuinely")
    print("misconfigured build (wrong thread count, no AVX2, swapping).")
    print()
    print("If MEASURED speed on the target lands far below this, the fallback")
    print("(Qwen3-1.7B, %.2f GiB) roughly doubles throughput for the same"
          % MODELS[3][1])
    print("tokenizer and prompt format.")
    print()
    print("ESTIMATED, not MEASURED. Confirm on the i5-12400 before relying on it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
