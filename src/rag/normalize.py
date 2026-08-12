"""
Bilingual text normalization for indexing and querying (Phase 3).

WHY THIS IS A SEPARATE MODULE
-----------------------------
The Q9 selector shipped a bug where the QUERY was normalized but the KEYWORDS
were not, so a Persian compound written with ZWNJ never matched one written
with a space. It was invisible: no error, just a silent miss.

The structural fix is to make normalization a single shared function that BOTH
the indexer and the query path call. If only one side normalizes, the index and
the query speak different alphabets and every lookup quietly under-returns.

Persian orthography variants that must collapse to one form:
  - ZWNJ U+200C:      ارزش‌گذاری / ارزش گذاری / ارزشگذاری
  - Arabic vs Persian yeh:  ي (U+064A) -> ی (U+06CC)
  - Arabic vs Persian kaf:  ك (U+0643) -> ک (U+06A9)
  - alef variants:    أ إ آ ٱ -> ا
  - heh variants:     ة -> ه
  - tatweel U+0640 and combining diacritics: dropped
  - Persian/Arabic-Indic digits: ۰-۹ / ٠-٩ -> 0-9
  - Persian thousands separator ٬ and decimal ٫

Stdlib only.
"""

from typing import List
import re
import unicodedata

ZWNJ = "\u200c"

# Character-level folding table.
_FOLD = {
    "\u064a": "\u06cc",   # arabic yeh   -> persian yeh
    "\u0649": "\u06cc",   # alef maksura -> persian yeh
    "\u0643": "\u06a9",   # arabic kaf   -> persian keheh
    "\u0623": "\u0627",   # alef hamza above
    "\u0625": "\u0627",   # alef hamza below
    "\u0622": "\u0627",   # alef madda
    "\u0671": "\u0627",   # alef wasla
    "\u0629": "\u0647",   # teh marbuta -> heh
    "\u0624": "\u0648",   # waw hamza
    "\u0626": "\u06cc",   # yeh hamza
    "\u0640": "",         # tatweel
    ZWNJ: " ",            # zero-width non-joiner -> space
    "\u200b": " ",        # zero-width space
    "\u200f": " ",        # RTL mark
    "\u200e": " ",        # LTR mark
    "\u066c": "",         # arabic thousands separator
    "\u066b": ".",        # arabic decimal separator
}

# Arabic/Persian-Indic digits.
for _i in range(10):
    _FOLD[chr(0x0660 + _i)] = str(_i)   # arabic-indic
    _FOLD[chr(0x06f0 + _i)] = str(_i)   # extended (persian)

# Combining marks (harakat) to strip entirely.
_DIACRITICS = re.compile(r"[\u064b-\u065f\u0670\u06d6-\u06ed]")

_TOKEN_RE = re.compile(r"[0-9]+(?:\.[0-9]+)?|[a-z]+|[\u0600-\u06ff]+")


def fold(text: str) -> str:
    """Character-level normalization. Idempotent."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = _DIACRITICS.sub("", text)
    out = []
    for ch in text:
        out.append(_FOLD.get(ch, ch))
    return "".join(out).lower()


def tokenize(text: str) -> List[str]:
    """
    Fold, then split into comparable tokens.

    Numbers keep their value but lose grouping punctuation, so a query for
    "109,417" matches a filing row written "109,417" or "109417".
    """
    folded = fold(text or "")
    # Drop thousands separators BETWEEN digits only, so "109,417" -> "109417"
    # while "revenue, cost" still splits into two tokens.
    folded = re.sub(r"(?<=\d),(?=\d)", "", folded)
    return _TOKEN_RE.findall(folded)


_PERSIAN_TOKEN = re.compile(r"^[\u0600-\u06ff]+$")


def compound_variants(tokens: List[str]) -> List[str]:
    """
    Joined forms of adjacent Persian tokens.

    MEASURED problem: folding ZWNJ to a space makes `ارزش‌گذاری` and
    `ارزش گذاری` agree, but a writer who types `ارزشگذاری` with no separator at
    all still produces ONE token that matches neither. Persian compounds are
    written all three ways in practice, including inside a single filing.

    So for every adjacent Persian pair we emit the concatenation as an EXTRA
    posting. `ارزش گذاری` then yields the joined form `ارزشگذاری`, which the
    solid spelling also yields, and the three spellings finally meet.

    These are returned separately, NOT merged into tokenize(), because they
    must not count toward BM25 document length: Persian text would otherwise
    look ~2x longer than equivalent English and be systematically penalised by
    length normalization.
    """
    out: List[str] = []
    for a, b in zip(tokens, tokens[1:]):
        if _PERSIAN_TOKEN.match(a) and _PERSIAN_TOKEN.match(b):
            out.append(a + b)
    return out


def index_terms(text: str) -> List[str]:
    """Base tokens plus Persian compound variants. Used by BOTH sides."""
    base = tokenize(text)
    return base + compound_variants(base)
