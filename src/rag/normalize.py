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
    # U+060C ARABIC COMMA is deliberately ABSENT from this table -- see the
    # note added 2026-08-31 (D-0089b) at the foot of this dict's comment block.
}

# WHY U+060C IS NOT FOLDED HERE, THOUGH IT IS THE COMMA THE MODEL WRITES.
#
# D-0089b (2026-08-31, MEASURED) found that the model emits U+060C where the
# fixture uses U+066C, and that the grader's separator table did not know it.
# The grader was fixed. This table was NOT, and the difference is deliberate.
#
# _FOLD is applied CHARACTER-BY-CHARACTER with no lookaround, so an entry here
# would delete every U+060C in the corpus, including the ones that are ordinary
# sentence punctuation. `tokenize()` already handles the grouping case with a
# guarded rule that only fires BETWEEN digits, which is where the equivalent
# fix belongs and where it was applied.
#
# Folding it unconditionally would silently merge two different Persian
# sentences' tokens ("درآمد، سود" -> "درآمدسود"), which is a retrieval defect
# rather than an arithmetic one, and therefore much harder to see.

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
    #
    # U+060C ARABIC COMMA added 2026-08-31 (D-0089b). MEASURED before the fix:
    #     tokenize('۳۸۳،۲۸۵') -> ['383', '،', '285']
    # i.e. a Persian figure the MODEL wrote indexed as two unrelated numbers
    # plus a punctuation token, so a query for that figure could not retrieve
    # the passage stating it. The fixture's U+066C form was folded correctly by
    # _FOLD, which is exactly why this went unnoticed: the only Persian numbers
    # ever indexed came from fixtures.
    #
    # This is guarded by BETWEEN-DIGITS, unlike a _FOLD entry, so Persian
    # sentence punctuation is untouched.
    folded = re.sub(r"(?<=\d)[,\u060c](?=\d)", "", folded)
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


# ---------------------------------------------------------------------------
# Non-quantity masking, shared by the indexer, the graders AND the citation
# verifier (D-0092).
#
# WHY THIS LIVES HERE AND NOT IN scripts/phase4_lib.py
# ----------------------------------------------------
# phase4_lib already had mask_years, and src/rag/citations.py needed it. But
# phase4_lib imports FROM rag.ingest, so citations.py cannot import phase4_lib
# without a cycle. Duplicating the regex was the other option and is the exact
# mistake this module's own docstring was written to prevent: two copies of a
# normalization rule drift, and the drift is silent.
#
# So the rule lands in the one module BOTH sides already depend on, and
# phase4_lib.mask_years now delegates here.
#
# THE DEFECT THIS FIXES, MEASURED 2026-09-05 on the user's real 52-case run
# -------------------------------------------------------------------------
# 8 of 12 graded RAG claims were checked against a number that is not a
# financial magnitude at all:
#
#   RAG-EN-001    "claimed 2"      was the citation marker [2]
#   RAG-EN-005    "claimed 1"      was the citation marker [1]
#   RAG-ABST-001  "claimed 2 / 3"  were the markers [2] and [3]
#   RAG-ABST-003  "claimed 1"      was [1]; "claimed 1402" was the year ۱۴۰۲
#   RAG-FA-001    "claimed 2023"   was the year ۲۰۲۳
#   RAG-FA-002    "claimed 2023"   was the year ۲۰۲۳
#
# producing details like "claimed 2 does not appear in the evidence; nearest is
# 1.69148e+11 (ratio 1.1824e-11 -- a power-of-ten ratio means a scale error)".
# citation_correctness_pct read 25.0 and unsupported_claim_rate_pct read 75.0
# while the ANSWERS WERE CORRECT: RAG-EN-001 said $383,285 million and
# RAG-FA-001 said ۳۸۳,۲۸۵ میلیون, both right.
#
# Two independent causes, and BOTH are needed:
#   1. citations.py performed no masking whatsoever.
#   2. the year pattern matched ASCII digits only, so a Persian-digit year
#      survived masking even where masking DID run -- R43 recurring for the
#      fourth time: a regex written against text the fixture author typed
#      rather than text the model emits.
# ---------------------------------------------------------------------------

# Digits in every script this project reads: ASCII, Arabic-Indic (U+0660) and
# Extended/Persian (U+06F0). Written as an explicit class rather than \d
# because Python's \d is Unicode-aware but the SURROUNDING guards below must
# reject the same set, and mixing \d with an explicit class made the two
# disagree -- which is how the Persian-digit hole survived in the first place.
_D = "0-9\u0660-\u0669\u06f0-\u06f9"

# A citation marker: a 1-2 digit run in square brackets, e.g. [1], [ 12 ].
#
# BOUNDED TO TWO DIGITS ON PURPOSE. A financial magnitude does appear in
# brackets in real filings -- "[1,234]" as a table cell, "[500]" as an
# accounting negative -- and deleting one of those would be the same class of
# error in the opposite direction: hiding a number the model must be held to.
#
# MEASURED before choosing the bound: across all 39 rows of
# rag_corpus_v1 + rag_gold_v1 + bilingual_eval_v1, bracketed runs of 1-2
# digits: 0. Across the user's 52 real outputs: 6 outputs contain one, and
# every one of them is a citation marker. So the bound costs nothing here and
# still refuses [1,234] and [500].
_CITATION_MARKER_RE = re.compile(r"\[\s*[%s]{1,2}\s*\]" % _D)

def _dig(*wanted):
    """
    A character class matching the given decimal VALUES in any digit script.

    CAUGHT BY MY OWN PROBE, 2026-09-05, and worth recording because it is the
    same mistake as the defect being fixed. My first version of the year
    pattern wrote the FIXED digits as ASCII literals -- "20[d][d]" -- and only
    the varying tail as a multi-script class. Result: `۲۰۲۳` still went
    unmasked, because its "2" and "0" are U+06F2 and U+06F0, not "2" and "0".
    The probe showed the Persian cases coming back UNCHANGED, i.e. the fix
    fixed nothing.

    The lesson is the one R43 keeps teaching: EVERY digit position has to be
    script-agnostic, not just the ones that happen to vary.
    """
    chars = []
    for n in wanted:
        chars.append(str(n))
        chars.append(chr(0x0660 + n))
        chars.append(chr(0x06f0 + n))
    return "[" + "".join(chars) + "]"


_ANY = "[%s]" % _D
_SEPS = ".,\u066b\u066c\u060c"

# Year-like bare integers, in any of the three digit scripts.
#
# Ranges: 1200-1499 (Jalali), 1800-2199 (Gregorian). NOT 1000-2199: MEASURED
# that 1000, 1100 and 1500-1799 are NOT masked, which is what keeps the two
# eval cases with expected_value=1000.0 (EN-NUM-001, FA-NUM-001) safe -- and
# they are additionally safe because value_matches never calls this at all.
#
# The lookarounds mirror phase4_lib's original and its recorded lesson: the
# trailing guard must be (?!digit|[.,]digit), not a bare character class, or
# "in 2023, revenue grew" -- the commonest prose form of the very thing being
# masked -- stops being masked. The separator set is widened to the Persian
# ones, because "۱.۲۰۲۳" must be protected exactly as "1.2023" is.
_YEAR_ANY_SCRIPT_RE = re.compile(
    "(?<![%(d)s%(s)s])"
    "(?:%(one)s%(23)s%(any)s%(any)s"
    "|%(one)s%(4)s%(any)s%(any)s"
    "|%(one)s%(89)s%(any)s%(any)s"
    "|%(two)s%(01)s%(any)s%(any)s)"
    "(?![%(d)s]|[%(s)s][%(d)s])"
    % {"d": _D, "s": _SEPS, "any": _ANY,
       "one": _dig(1), "two": _dig(2),
       "23": _dig(2, 3), "4": _dig(4), "89": _dig(8, 9), "01": _dig(0, 1)})


def mask_non_quantities(text):
    """
    Blank out the things in a sentence that LOOK numeric but assert no amount.

    Two kinds, both of which were MEASURED corrupting the citation grader:
      - citation markers  [1] [2] [3]
      - year-like bare integers, in ASCII, Arabic-Indic or Persian digits

    Markers are removed first. I ORIGINALLY DOCUMENTED THIS AS ORDER-CRITICAL,
    claiming a marker's digits would otherwise be consumed by the year
    pattern's lookbehind. A mutant that swapped the two SURVIVED, so I probed
    the claim instead of defending it: on `[2023]`, `[20]`, `in 2023 see [2]`,
    `Evidence [2], states 383,285` and the Persian `مطابق [۲] در سال ۱۴۰۲`, the
    two orders produce IDENTICAL output. The bracket guards mean the patterns
    cannot overlap, so the order is genuinely free.
    The swap mutant was deleted rather than "killed" with an assertion
    manufactured to pin an ordering that does not matter -- that would have
    been a test written to make a battery look complete.

    Masking rather than deleting keeps the sentence readable for the human
    auditor who has to review these claims (R10), and keeps offsets roughly
    stable. The placeholders contain no digits, which is the whole point.

    Returns "" for None. Raises TypeError on a non-string rather than coercing
    it: a silently stringified dict would mask nothing and grade everything.
    """
    if text is None:
        return ""
    if not isinstance(text, str):
        raise TypeError("mask_non_quantities expects str or None, got %s"
                        % type(text).__name__)
    text = _CITATION_MARKER_RE.sub("<CIT>", text)
    return _YEAR_ANY_SCRIPT_RE.sub("<YEAR>", text)
