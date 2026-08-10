"""
Persian/Arabic numeral normalization (master prompt risk R5).

WHY THIS EXISTS AS A TOOL, NOT A MODEL TASK
Phase 1 MEASURED that Qwen tokenizers spend 2 tokens per Persian digit and
fragment '۱٬۲۳۴٬۵۶۷' into 16 tokens. Digit fragmentation is a known driver of
arithmetic error. Rather than trust the model to read Persian numbers, all
numeric parsing is done deterministically here, before any calculation.

THE DANGEROUS AMBIGUITY
Persian uses U+066B (٫) as the DECIMAL separator and U+066C (٬) as the
THOUSANDS separator. They are visually similar and trivially confusable:
    ۸٫۴  -> 8.4      (decimal)
    ۸٬۴۰۰ -> 8400    (thousands)
Swapping them turns 8.4 into 84000 or vice versa. This module treats them as
distinct and never guesses.
"""

import re
import unicodedata

# U+06F0..U+06F9 Extended Arabic-Indic (Persian) digits
PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
# U+0660..U+0669 Arabic-Indic digits (used in Arabic locales)
ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
ASCII_DIGITS = "0123456789"

DIGIT_MAP = {}
for i in range(10):
    DIGIT_MAP[PERSIAN_DIGITS[i]] = ASCII_DIGITS[i]
    DIGIT_MAP[ARABIC_DIGITS[i]] = ASCII_DIGITS[i]

ARABIC_DECIMAL_SEP = "\u066B"    # ٫
ARABIC_THOUSANDS_SEP = "\u066C"  # ٬
ZWNJ = "\u200C"                  # zero-width non-joiner


def normalize_digits(text: str) -> str:
    """Convert Persian/Arabic-Indic digits to ASCII. Leaves everything else."""
    if text is None:
        raise ValueError("normalize_digits: text is None")
    return "".join(DIGIT_MAP.get(ch, ch) for ch in text)


def strip_zwnj(text: str) -> str:
    """Remove ZWNJ. Use for MATCHING, never for display -- ZWNJ is meaningful."""
    return text.replace(ZWNJ, "")


def parse_number(text: str) -> float:
    """
    Parse a number written in Persian, Arabic, or ASCII form.

    Handles: Persian/Arabic-Indic digits, U+066B decimal, U+066C thousands,
    ASCII comma thousands, Latin decimal point, leading +/-, and percent
    (returns the numeric value, NOT divided by 100 -- see parse_percent).

    Raises ValueError on anything ambiguous rather than guessing.
    """
    if text is None:
        raise ValueError("parse_number: text is None")
    s = normalize_digits(str(text)).strip()
    s = strip_zwnj(s)
    s = s.replace("\u00A0", "").replace(" ", "")
    if not s:
        raise ValueError("parse_number: empty input")

    # Persian separators are unambiguous -- map them directly.
    s = s.replace(ARABIC_THOUSANDS_SEP, "")
    s = s.replace(ARABIC_DECIMAL_SEP, ".")

    s = s.rstrip("%٪")

    # ASCII comma: thousands separator in this project's conventions.
    # Reject the European style (1.234,56) rather than silently misreading it.
    if "," in s and "." in s:
        if s.rindex(",") > s.rindex("."):
            raise ValueError(
                "parse_number: ambiguous separators in %r (looks like "
                "European 1.234,56 format); normalize upstream" % text)
        s = s.replace(",", "")
    elif "," in s:
        parts = s.split(",")
        # 1,234 / 1,234,567 -> thousands. 1,5 -> ambiguous, reject.
        if all(len(p) == 3 for p in parts[1:]) and len(parts[0]) <= 3:
            s = s.replace(",", "")
        else:
            raise ValueError(
                "parse_number: ambiguous comma in %r; cannot tell thousands "
                "from decimal" % text)

    if s.count(".") > 1:
        raise ValueError("parse_number: multiple decimal points in %r" % text)

    try:
        return float(s)
    except ValueError:
        raise ValueError("parse_number: cannot parse %r (normalized to %r)"
                         % (text, s))


def parse_percent(text: str) -> float:
    """
    Parse a percentage into a FRACTION. '۲۵٪' -> 0.25.

    Separated from parse_number deliberately: silently dividing by 100 based on
    the presence of a '%' character is exactly the kind of implicit behaviour
    that produces 100x errors in position sizing.
    """
    v = parse_number(text)
    return v / 100.0


def format_persian(value: float, decimals: int = 2,
                   use_persian_digits: bool = True) -> str:
    """Format a number for Persian display with correct separators."""
    s = "%.*f" % (decimals, value)
    neg = s.startswith("-")
    if neg:
        s = s[1:]
    if "." in s:
        int_part, dec_part = s.split(".")
    else:
        int_part, dec_part = s, ""
    # group thousands
    groups = []
    while len(int_part) > 3:
        groups.insert(0, int_part[-3:])
        int_part = int_part[:-3]
    groups.insert(0, int_part)
    out = ARABIC_THOUSANDS_SEP.join(groups)
    if dec_part:
        out = out + ARABIC_DECIMAL_SEP + dec_part
    if neg:
        out = "-" + out
    if use_persian_digits:
        rev = {v: k for k, v in zip(PERSIAN_DIGITS, ASCII_DIGITS)}
        out = "".join(rev.get(c, c) for c in out)
    return out
