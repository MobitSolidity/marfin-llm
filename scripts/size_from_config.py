#!/usr/bin/env python3
"""
size_from_config.py -- Phase 1 sizing, driven by OFFICIAL model configs.

Supersedes the generic MODEL_CLASSES table in estimate_model_footprint.py.
Every architectural number here is READ FROM configs/model-cards/*.json,
which are verbatim copies of each model's official config.json.

Parameter counts come from the HuggingFace safetensors index (authoritative),
not from a re-derivation, and are recorded in REGISTRY below.

LABELLING (per master prompt SS.0B):
  VERIFIED  -- config/license fields fetched from the vendor's own repo
  COMPUTED  -- arithmetic on VERIFIED inputs (weights, KV cache)
  MEASURED  -- tokenizer ratios, from scripts/measure_tokenizer_efficiency.py
  ESTIMATED -- quantization bpw, runtime overhead (see caveats)

NOT MEASURED HERE: tokens/sec. This sandbox cannot load these models
(Phase 0 finding F1: 0.60 GiB available). Speed must be measured on the
target machine in Phase 2.
"""

import argparse
import json
import os
import sys

GIB = 1024 ** 3

# ESTIMATED: effective bits-per-weight for llama.cpp k-quants. Real GGUF files
# vary +/- a few percent because token_embd / output tensors are often kept at
# a higher precision than the body of the model.
BITS_PER_WEIGHT = {"Q4_K_M": 4.85, "Q5_K_M": 5.70, "Q8_0": 8.50}

# ESTIMATED: llama.cpp process overhead beyond weights + KV (compute buffers,
# logits, allocator slack). Empirical rule of thumb, to be replaced by a
# MEASURED value in Phase 2.
RUNTIME_OVERHEAD_GIB = 0.6

# VERIFIED fields: params (safetensors total), license, gated, tokenizer ratio.
# tok_ratio is MEASURED -- Persian tokens/char divided by English tokens/char.
REGISTRY = {
    "Qwen_Qwen3-4B-Instruct-2507": {
        "repo": "Qwen/Qwen3-4B-Instruct-2507",
        "params": 4_022_468_096, "license": "apache-2.0", "gated": False,
        "tok_ratio": 2.81,
    },
    "microsoft_Phi-4-mini-instruct": {
        "repo": "microsoft/Phi-4-mini-instruct",
        "params": 3_836_021_760, "license": "mit", "gated": False,
        "tok_ratio": 1.60,
    },
    "HuggingFaceTB_SmolLM3-3B": {
        "repo": "HuggingFaceTB/SmolLM3-3B",
        "params": 3_075_098_624, "license": "apache-2.0", "gated": False,
        "tok_ratio": 1.61,
    },
    "ibm-granite_granite-3.3-2b-instruct": {
        "repo": "ibm-granite/granite-3.3-2b-instruct",
        "params": 2_533_539_840, "license": "apache-2.0", "gated": False,
        "tok_ratio": 3.16,
    },
    "Qwen_Qwen3-1.7B": {
        "repo": "Qwen/Qwen3-1.7B",
        "params": 2_031_739_904, "license": "apache-2.0", "gated": False,
        "tok_ratio": 2.81,
    },
    "Qwen_Qwen2.5-1.5B-Instruct": {
        "repo": "Qwen/Qwen2.5-1.5B-Instruct",
        "params": 1_543_714_304, "license": "apache-2.0", "gated": False,
        "tok_ratio": 2.81,
    },
    # Retained ONLY to document the disqualification, not as a candidate.
    "Qwen_Qwen2.5-3B-Instruct": {
        "repo": "Qwen/Qwen2.5-3B-Instruct",
        "params": 3_085_938_688, "license": "qwen-research (NON-COMMERCIAL)",
        "gated": False, "tok_ratio": 2.81, "disqualified": "license",
    },
}


def head_dim_of(cfg):
    """Return (head_dim, source). Explicit config value wins; else derive."""
    hd = cfg.get("head_dim")
    if hd:
        return hd, "config"
    hidden = cfg["hidden_size"]
    heads = cfg["num_attention_heads"]
    if hidden % heads != 0:
        raise ValueError("hidden_size not divisible by num_attention_heads")
    return hidden // heads, "derived"


def weight_gib(params, quant):
    return params * BITS_PER_WEIGHT[quant] / 8 / GIB


def kv_cache_gib(ctx, n_layer, n_kv_head, head_dim, bytes_per_elem=2):
    """2 (K and V) * layers * kv_heads * head_dim * ctx * bytes."""
    return 2 * n_layer * n_kv_head * head_dim * ctx * bytes_per_elem / GIB


def load(cfg_dir):
    rows = []
    for key, meta in REGISTRY.items():
        path = os.path.join(cfg_dir, key + ".json")
        if not os.path.exists(path):
            print("MISSING config: %s" % path, file=sys.stderr)
            continue
        cfg = json.load(open(path))
        hd, hd_src = head_dim_of(cfg)
        rows.append({
            "key": key, "meta": meta, "cfg": cfg,
            "n_layer": cfg["num_hidden_layers"],
            "n_kv": cfg["num_key_value_heads"],
            "head_dim": hd, "hd_src": hd_src,
            "vocab": cfg["vocab_size"],
            "train_ctx": cfg["max_position_embeddings"],
        })
    rows.sort(key=lambda r: -r["meta"]["params"])
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="configs/model-cards")
    ap.add_argument("--ram", type=float, default=16.0, help="total system RAM (GiB)")
    ap.add_argument("--ctx", type=int, default=16384)
    ap.add_argument("--os-reserve", type=float, default=4.0,
                    help="RAM reserved for Windows 11 + apps (GiB)")
    ap.add_argument("--quant", default="Q4_K_M", choices=list(BITS_PER_WEIGHT))
    ap.add_argument("--kv-bytes", type=int, default=2, choices=[1, 2],
                    help="2=fp16 KV (default), 1=q8_0 KV cache")
    a = ap.parse_args()

    rows = load(a.dir)
    if not rows:
        print("No configs found. Run the Phase 1 fetch step first.", file=sys.stderr)
        return 1

    budget = a.ram - a.os_reserve

    print("=" * 108)
    print("PHASE 1 SIZING -- from official configs (COMPUTED from VERIFIED inputs)")
    print("=" * 108)
    print("Target: %.0f GiB RAM, Windows 11, CPU-only (i5-12400)" % a.ram)
    print("Quant: %s (%.2f bpw, ESTIMATED)  |  ctx: %s  |  KV dtype: %s"
          % (a.quant, BITS_PER_WEIGHT[a.quant], f"{a.ctx:,}",
             "fp16" if a.kv_bytes == 2 else "q8_0"))
    print("Usable budget: %.1f GiB (%.0f GiB RAM minus %.0f GiB OS/apps reserve)"
          % (budget, a.ram, a.os_reserve))
    print()

    hdr = ("model", "params", "L", "kv", "hd", "wt GiB", "KV GiB", "total", "%budget", "verdict")
    print("%-30s %7s %4s %4s %4s %8s %8s %8s %8s  %s" % hdr)
    print("-" * 108)

    results = []
    for r in rows:
        m = r["meta"]
        w = weight_gib(m["params"], a.quant)
        kv = kv_cache_gib(a.ctx, r["n_layer"], r["n_kv"], r["head_dim"], a.kv_bytes)
        total = w + kv + RUNTIME_OVERHEAD_GIB
        pct = total / budget * 100
        if m.get("disqualified"):
            verdict = "DISQUALIFIED (%s)" % m["disqualified"]
        elif pct <= 55:
            verdict = "comfortable"
        elif pct <= 80:
            verdict = "workable"
        elif pct <= 100:
            verdict = "tight"
        else:
            verdict = "EXCEEDS BUDGET"
        results.append((r, w, kv, total, pct, verdict))
        print("%-30s %6.2fB %4d %4d %4d %8.2f %8.2f %8.2f %7.0f%%  %s"
              % (m["repo"].split("/")[-1][:30], m["params"] / 1e9,
                 r["n_layer"], r["n_kv"], r["head_dim"], w, kv, total, pct, verdict))

    print()
    print("L=layers, kv=num_key_value_heads (GQA), hd=head_dim")
    print("total = weights + KV cache + %.1f GiB runtime overhead (ESTIMATED)"
          % RUNTIME_OVERHEAD_GIB)

    # --- Effective Persian capacity -------------------------------------
    print()
    print("=" * 108)
    print("EFFECTIVE PERSIAN CAPACITY -- memory fit is not the real constraint")
    print("=" * 108)
    print("%-30s %10s %14s %16s" % ("model", "tok_ratio", "fits budget?", "Persian chars@ctx"))
    print("-" * 108)
    # English baseline tokens/char measured at ~0.21 for the efficient tokenizers.
    EN_TOK_PER_CHAR = 0.21
    for r, w, kv, total, pct, verdict in results:
        m = r["meta"]
        fa_tok_per_char = EN_TOK_PER_CHAR * m["tok_ratio"]
        fa_chars = int(a.ctx / fa_tok_per_char)
        fits = "no" if pct > 100 else ("yes" if not m.get("disqualified") else "n/a")
        print("%-30s %10.2f %14s %16s"
              % (m["repo"].split("/")[-1][:30], m["tok_ratio"], fits, f"{fa_chars:,}"))

    print()
    print("tok_ratio is MEASURED (scripts/measure_tokenizer_efficiency.py).")
    print("Persian chars@ctx uses an English baseline of %.2f tok/char." % EN_TOK_PER_CHAR)

    # --- Licensing ------------------------------------------------------
    print()
    print("=" * 108)
    print("LICENSING (VERIFIED from vendor repo)")
    print("=" * 108)
    for r in rows:
        m = r["meta"]
        flag = "  <-- BLOCKS COMMERCIAL USE" if m.get("disqualified") else ""
        print("%-32s %-34s gated=%s%s"
              % (m["repo"], m["license"], m["gated"], flag))

    print()
    print("NOT MEASURED: tokens/sec. Phase 0 finding F1 -- this sandbox has")
    print("0.60 GiB available and cannot load any of these models. Throughput")
    print("must be measured on the target i5-12400 in Phase 2.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
