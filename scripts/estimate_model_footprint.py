#!/usr/bin/env python3
"""
Deterministic GGUF footprint estimator.

Per SYSTEM_PROMPT.md Sections 5.3 and 27, sizing must be reproducible and
explicitly labeled. Every number this script prints is ESTIMATED or COMPUTED --
never MEASURED. Real sizes are only known after Phase 7 produces actual
artifacts, and real speed only after Phase 8 runs on target hardware.

Usage:
    python3 scripts/estimate_model_footprint.py
    python3 scripts/estimate_model_footprint.py --ram 16 --ctx 8192
"""

import argparse

GIB = 1024 ** 3

# llama.cpp k-quant nominal average bits-per-weight.
# ESTIMATED: k-quants mix precision per tensor, so effective bpw varies a few
# percent by architecture. Verified against real artifacts in Phase 7.
BITS_PER_WEIGHT = {
    "Q4_K_M": 4.85,
    "Q5_K_M": 5.70,
    "Q8_0": 8.50,
}

# Runtime overhead beyond weights + KV cache: activations, compute buffers,
# tokenizer, allocator slack. ESTIMATED.
RUNTIME_OVERHEAD_GIB = 0.6

# Representative configs for the size classes named in prompt Section 3.
# Layer / kv-head counts are TYPICAL for each class, not any specific model.
# Exact per-model values are VERIFIED in Phase 1.
#   (label, params, n_layer, n_kv_head, head_dim)
MODEL_CLASSES = [
    ("~1.5B class", 1.5e9, 28, 2, 128),
    ("~3B class",   3.0e9, 36, 4, 128),
    ("~4B class",   4.0e9, 36, 8, 128),
    ("~7B class",   7.0e9, 32, 8, 128),
]


def weight_size_gib(params: float, quant: str) -> float:
    """COMPUTED: bytes = params * bits_per_weight / 8."""
    return params * BITS_PER_WEIGHT[quant] / 8 / GIB


def kv_cache_gib(ctx: int, n_layer: int, n_kv_head: int,
                 head_dim: int, bytes_per_elem: int = 2) -> float:
    """COMPUTED: KV cache = 2 * layers * kv_heads * head_dim * ctx * dtype.

    Factor 2 covers the separate K and V tensors. bytes_per_elem=2 assumes an
    fp16 cache (llama.cpp default). Quantized KV (q8_0/q4_0) reduces this
    roughly proportionally at some quality cost.
    """
    return 2 * n_layer * n_kv_head * head_dim * ctx * bytes_per_elem / GIB


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ram", type=float, default=16.0,
                    help="Target machine RAM in GiB (default: 16, per Sec 2 fallback)")
    ap.add_argument("--ctx", type=int, default=8192,
                    help="Primary context length to highlight (default: 8192)")
    args = ap.parse_args()

    contexts = sorted({2048, 8192, 16384, 32768, args.ctx})

    print("=" * 78)
    print("GGUF FOOTPRINT ESTIMATE  --  ALL VALUES ESTIMATED/COMPUTED, NOT MEASURED")
    print("=" * 78)

    print("\n[1] Weight size by quantization (COMPUTED)\n")
    print(f"{'Class':<14}" + "".join(f"{q:>10}" for q in BITS_PER_WEIGHT))
    print("-" * 78)
    for label, params, *_ in MODEL_CLASSES:
        row = "".join(f"{weight_size_gib(params, q):>10.2f}" for q in BITS_PER_WEIGHT)
        print(f"{label:<14}{row}")
    print("\n(GiB. bpw: " +
          ", ".join(f"{q}={b}" for q, b in BITS_PER_WEIGHT.items()) + ")")

    print(f"\n[2] KV cache, fp16 (COMPUTED)\n")
    print(f"{'Class':<14}" + "".join(f"{str(c):>10}" for c in contexts))
    print("-" * 78)
    for label, _p, L, kvh, hd in MODEL_CLASSES:
        row = "".join(f"{kv_cache_gib(c, L, kvh, hd):>10.2f}" for c in contexts)
        print(f"{label:<14}{row}")
    print("\n(GiB. Layer/kv-head counts are TYPICAL for the class, not model-specific.)")

    print(f"\n[3] Total resident @ Q4_K_M, incl. {RUNTIME_OVERHEAD_GIB} GiB overhead "
          f"(ESTIMATED)\n")
    print(f"{'Class':<14}" + "".join(f"{str(c):>10}" for c in contexts) + "   verdict")
    print("-" * 78)
    for label, params, L, kvh, hd in MODEL_CLASSES:
        w = weight_size_gib(params, "Q4_K_M")
        totals = [w + kv_cache_gib(c, L, kvh, hd) + RUNTIME_OVERHEAD_GIB
                  for c in contexts]
        at_primary = w + kv_cache_gib(args.ctx, L, kvh, hd) + RUNTIME_OVERHEAD_GIB
        # Leave headroom for the OS and other processes; 70% of RAM is the cap.
        if at_primary <= args.ram * 0.55:
            verdict = "comfortable"
        elif at_primary <= args.ram * 0.70:
            verdict = "workable"
        else:
            verdict = "TOO LARGE"
        print(f"{label:<14}" + "".join(f"{t:>10.2f}" for t in totals) + f"   {verdict}")

    print(f"\nVerdict column evaluated at ctx={args.ctx} against {args.ram:g} GiB RAM.")
    print("\nCaveats (Sec 20.4):")
    print("  * Sizes are ESTIMATED until Phase 7 emits real GGUF artifacts.")
    print("  * Speed is NOT modeled here. CPU tok/s depends on memory bandwidth,")
    print("    core count, and thread config, and is only known by MEASURING")
    print("    on target hardware in Phase 8.")
    print("  * Quantized KV cache would cut section [2] materially; evaluate in Phase 8.")


if __name__ == "__main__":
    main()
