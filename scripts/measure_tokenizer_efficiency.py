#!/usr/bin/env python3
"""
Persian/English tokenizer efficiency measurement.

Addresses risk R5 (SYSTEM_PROMPT.md Sections 3.27-3.28, 20.3): a tokenizer that
fragments Persian inflates the effective cost of every Persian token, shrinking
usable context and slowing generation for the same visible text.

Results here are MEASURED (real tokenizers, deterministic counts) -- unlike
model speed, which cannot be measured without loading weights.

Metric: tokens-per-character (lower is better) and the Persian/English ratio
(closer to 1.0 is better -- it means Persian is not penalized vs English).

Usage:
    python3 scripts/measure_tokenizer_efficiency.py --dir /tmp/tok
"""

import argparse
import glob
import os
import sys

# Parallel Persian/English financial texts. Same semantic content in both
# languages so the ratio is meaningful rather than comparing unlike content.
SAMPLES = [
    (
        "سود خالص شرکت در سه‌ماهه چهارم سال مالی ۱۴۰۳ با رشد ۲۳ درصدی نسبت به "
        "دوره مشابه سال قبل به ۱۲٬۴۵۰ میلیارد ریال رسید.",
        "The company's net profit in Q4 of fiscal year 1403 reached 12,450 "
        "billion rials, a 23 percent increase compared to the same period last year.",
    ),
    (
        "نسبت قیمت به درآمد سهم در حال حاضر ۸.۴ است که پایین‌تر از میانگین "
        "صنعت یعنی ۱۱.۲ قرار دارد.",
        "The stock's price-to-earnings ratio is currently 8.4, which is below "
        "the industry average of 11.2.",
    ),
    (
        "جریان نقد آزاد منفی و افزایش بدهی کوتاه‌مدت، ریسک نقدینگی را در "
        "میان‌مدت افزایش می‌دهد.",
        "Negative free cash flow and rising short-term debt increase liquidity "
        "risk over the medium term.",
    ),
    (
        "بانک مرکزی نرخ بهره را بدون تغییر نگه داشت و بر مهار تورم تاکید کرد.",
        "The central bank kept interest rates unchanged and emphasized "
        "containing inflation.",
    ),
    (
        "شاخص قدرت نسبی به ناحیه اشباع فروش وارد شده و واگرایی مثبت با قیمت "
        "نشان می‌دهد.",
        "The relative strength index has entered oversold territory and shows "
        "positive divergence with price.",
    ),
]

# Persian-specific characters that a poor tokenizer often splits badly:
# ZWNJ (U+200C) used in compound words, and Persian-Indic digits.
EDGE_CASES = [
    ("ZWNJ compound", "می‌شود سه‌ماهه پیش‌بینی"),
    ("Persian digits", "۱۲۳۴۵۶۷۸۹۰"),
    ("Persian decimal", "۸٫۴ درصد"),
    ("Thousands sep", "۱٬۲۳۴٬۵۶۷"),
    ("Mixed script", "سهام AAPL در NASDAQ"),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="/tmp/tok",
                    help="Directory of <name>.json tokenizer files")
    args = ap.parse_args()

    try:
        from tokenizers import Tokenizer
    except ImportError:
        sys.exit("ERROR: pip install tokenizers")

    files = sorted(glob.glob(os.path.join(args.dir, "*.json")))
    if not files:
        sys.exit(f"ERROR: no tokenizer .json files in {args.dir}")

    fa_text = " ".join(s[0] for s in SAMPLES)
    en_text = " ".join(s[1] for s in SAMPLES)

    print("=" * 92)
    print("TOKENIZER EFFICIENCY -- MEASURED (real tokenizers, deterministic counts)")
    print("=" * 92)
    print(f"\nCorpus: {len(SAMPLES)} parallel financial sentences")
    print(f"  Persian: {len(fa_text)} chars | English: {len(en_text)} chars\n")

    print(f"{'tokenizer':<26}{'vocab':>8}{'fa_tok':>8}{'en_tok':>8}"
          f"{'fa/char':>9}{'en/char':>9}{'ratio':>8}  verdict")
    print("-" * 92)

    rows = []
    for path in files:
        name = os.path.basename(path)[:-5]
        try:
            tok = Tokenizer.from_file(path)
        except Exception as exc:
            print(f"{name:<26}  LOAD FAILED: {str(exc)[:40]}")
            continue

        fa_n = len(tok.encode(fa_text).ids)
        en_n = len(tok.encode(en_text).ids)
        fa_pc = fa_n / len(fa_text)
        en_pc = en_n / len(en_text)
        ratio = fa_pc / en_pc

        # Ratio = how much more expensive a Persian character is vs an English
        # one for this tokenizer. <1.5 good, <2.0 acceptable, >=2.0 costly.
        if ratio < 1.5:
            verdict = "excellent"
        elif ratio < 2.0:
            verdict = "acceptable"
        else:
            verdict = "COSTLY"

        rows.append((name, fa_n, en_n, fa_pc, en_pc, ratio))
        print(f"{name:<26}{tok.get_vocab_size():>8}{fa_n:>8}{en_n:>8}"
              f"{fa_pc:>9.3f}{en_pc:>9.3f}{ratio:>8.2f}  {verdict}")

    if not rows:
        sys.exit("No tokenizers loaded.")

    print("\nratio = Persian tokens/char divided by English tokens/char.")
    print("Lower is better: 1.00 would mean Persian costs the same as English.")

    print("\n" + "=" * 92)
    print("EDGE CASES -- Persian-specific constructs (token count, lower is better)")
    print("=" * 92)
    hdr = f"{'case':<18}" + "".join(f"{os.path.basename(p)[:-5][:13]:>15}" for p in files)
    print(hdr)
    print("-" * len(hdr))
    for label, text in EDGE_CASES:
        line = f"{label:<18}"
        for path in files:
            try:
                t = Tokenizer.from_file(path)
                line += f"{len(t.encode(text).ids):>15}"
            except Exception:
                line += f"{'-':>15}"
        print(line)
    print(f"\n(reference: '{EDGE_CASES[1][1]}' is 10 Persian digits -- "
          "a tokenizer needing >10 tokens is fragmenting them)")

    print("\n" + "=" * 92)
    print("CONTEXT-COST IMPLICATION @ 16K (user's Q2 target)")
    print("=" * 92)
    print(f"{'tokenizer':<26}{'fa chars in 16K':>18}{'en chars in 16K':>18}")
    print("-" * 62)
    for name, _fa_n, _en_n, fa_pc, en_pc, _r in sorted(rows, key=lambda r: r[5]):
        print(f"{name:<26}{int(16384/fa_pc):>18,}{int(16384/en_pc):>18,}")
    print("\nHow much real text fits in the 16K window, by language.")

    best = min(rows, key=lambda r: r[5])
    worst = max(rows, key=lambda r: r[5])
    print(f"\nBest Persian efficiency : {best[0]} (ratio {best[5]:.2f})")
    print(f"Worst Persian efficiency: {worst[0]} (ratio {worst[5]:.2f})")
    spread = (worst[3] / best[3] - 1) * 100
    print(f"Spread: {spread:.0f}% more Persian tokens for the same text on the worst.")


if __name__ == "__main__":
    main()
