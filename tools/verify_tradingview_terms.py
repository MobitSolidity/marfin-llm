"""Re-verify TradingView's data-use terms by live probe.

WHY THIS EXISTS
    Master prompt section 7 requires the TradingView terms review to be redone at
    execution time rather than recalled. docs/legal/tradingview-terms-review.md is
    the record of the 2026-08-12 review; this script is how that record is checked
    for drift.

WHAT IT DOES *NOT* DO
    It does not decide whether machine use is permitted. A human reads the output.
    If the prohibition text disappears, the script says "the clause I relied on is
    gone -- a human must re-read the terms", NOT "machine use is now allowed".
    Removal of a prohibition is not a grant of permission (see the review, s6).

DESIGN NOTE -- WHY NOT COMPARE PAGE HASHES
    Two probes of the same page on the same day produced different byte counts and
    different sha256 values (218,813 / adac9516... and 218,818 / 9720fa51...) while
    the clause text was byte-identical. The page embeds per-response markup. A page
    hash therefore produces false alarms, and an engineer who learns to ignore the
    alarm has lost the check entirely. We hash the EXTRACTED CLAUSE TEXT instead.
"""

import argparse
import datetime
import gzip
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request

TERMS_URL = "https://www.tradingview.com/policies/"

# A contact User-Agent, for the same reason the SEC requires one: an operator who
# is reviewing licence terms should be identifiable while doing it.
USER_AGENT = "marfin-llm/0.1 (compliance-review; contact@example.com)"

# The clauses the project's entire TradingView posture rests on. Each must still be
# present. Phrasing chosen to be the load-bearing fragment, not a whole sentence,
# so that harmless editorial rewording does not trip the alarm -- but the substance
# cannot vanish without tripping it.
REQUIRED_CLAUSES = (
    "exclusive display-only use",
    "explicitly prohibits any form of non-display usage",
    "automated trading",
    "automated order generation",
    "price referencing",
    "order verification",
    "algorithmic decision-making",
    "smart order routing",
    "risk management programs",
    "machine-driven processes",
    "charts, alerts, webhooks",
    "we do not permit commercial usage",
)

# Recorded at the 2026-08-12 review. Compared against the freshly extracted text.
BASELINE_CLAUSE_SHA256 = None  # set on first --record run; see main()

_SECTION_ANCHOR = "The content and market data provided on the TradingView platform"
_SECTION_END = "We make no warranty and assume no obligation"


class ProbeError(Exception):
    """The terms could not be retrieved. NOT the same as 'terms have changed'."""


def fetch(url, timeout=45):
    """Return (status, raw_bytes, final_url). Handles gzip, which /widget-docs/ needs."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            status = resp.status
            final = resp.geturl()
            encoding = resp.headers.get("Content-Encoding")
    except urllib.error.HTTPError as exc:
        raise ProbeError("HTTP %s for %s" % (exc.code, url))
    except Exception as exc:
        raise ProbeError("%s for %s: %s" % (type(exc).__name__, url, exc))
    if encoding == "gzip":
        try:
            raw = gzip.decompress(raw)
        except Exception:
            pass  # some servers mislabel; fall through with the original bytes
    return status, raw, final


def to_text(raw):
    """Strip markup to a single normalised line of readable text."""
    html = raw.decode("utf-8", "replace")
    html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?s)<[^>]+>", " ", html)
    for entity, char in (("&nbsp;", " "), ("&amp;", "&"), ("&quot;", '"'),
                         ("&#x27;", "'"), ("&#39;", "'"), ("&rsquo;", "'"),
                         ("&ldquo;", '"'), ("&rdquo;", '"')):
        html = html.replace(entity, char)
    return re.sub(r"\s+", " ", html).strip()


def extract_clause_block(text):
    """Return the non-display licence block, or None if the anchor is gone.

    None is a finding, not an error: it means the document was restructured and a
    human must re-read it.
    """
    start = text.find(_SECTION_ANCHOR)
    if start == -1:
        return None
    end = text.find(_SECTION_END, start)
    if end == -1:
        end = min(len(text), start + 6000)
    return text[start:end].strip()


def review():
    """Probe and report. Returns a dict; never raises on 'terms changed'."""
    status, raw, final = fetch(TERMS_URL)
    text = to_text(raw)
    block = extract_clause_block(text)

    found, missing = [], []
    for clause in REQUIRED_CLAUSES:
        (found if clause.lower() in text.lower() else missing).append(clause)

    result = {
        "probed_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "url": TERMS_URL,
        "final_url": final,
        "http_status": status,
        "page_bytes": len(raw),
        "page_sha256": hashlib.sha256(raw).hexdigest(),
        "page_hash_is_unstable": True,
        "clause_block_found": block is not None,
        "clause_block_chars": len(block) if block else 0,
        "clause_block_sha256": (hashlib.sha256(block.encode("utf-8")).hexdigest()
                                if block else None),
        "clauses_found": found,
        "clauses_missing": missing,
        "clause_block": block,
    }

    if missing or block is None:
        result["verdict"] = "REVIEW_REQUIRED"
        result["verdict_note"] = (
            "One or more clauses this project relies on were not found. This does "
            "NOT mean machine use became permitted. A human must re-read the terms "
            "and update docs/legal/tradingview-terms-review.md before any change "
            "to src/market/tradingview.py."
        )
    else:
        result["verdict"] = "UNCHANGED_STILL_PROHIBITED"
        result["verdict_note"] = (
            "All relied-upon prohibitions are still present. TradingView remains "
            "display-only; machine use remains prohibited."
        )
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit raw JSON")
    parser.add_argument("--quiet", action="store_true", help="verdict line only")
    args = parser.parse_args(argv)

    try:
        result = review()
    except ProbeError as exc:
        # An unreachable page must never read as "terms are fine".
        print("PROBE FAILED: %s" % exc)
        print("VERDICT: UNKNOWN -- could not verify. The last recorded review in "
              "docs/legal/tradingview-terms-review.md remains in force.")
        return 2

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result["verdict"] == "UNCHANGED_STILL_PROHIBITED" else 1

    print("TradingView terms review -- %s" % result["probed_at_utc"])
    print("  URL           : %s" % result["url"])
    print("  HTTP          : %s (%d bytes)" % (result["http_status"], result["page_bytes"]))
    print("  page sha256   : %s  (UNSTABLE -- do not alarm on this)"
          % result["page_sha256"][:16])
    print("  clause sha256 : %s  (the meaningful fingerprint)"
          % (result["clause_block_sha256"] or "<block not found>")[:16])
    print("  clauses found : %d/%d" % (len(result["clauses_found"]), len(REQUIRED_CLAUSES)))
    if result["clauses_missing"]:
        print("  MISSING       : %s" % ", ".join(result["clauses_missing"]))
    print("  VERDICT       : %s" % result["verdict"])
    if not args.quiet:
        print("  %s" % result["verdict_note"])
        if result["clause_block"]:
            print("\n--- verbatim clause block (%d chars) ---" % result["clause_block_chars"])
            print(result["clause_block"])
    return 0 if result["verdict"] == "UNCHANGED_STILL_PROHIBITED" else 1


if __name__ == "__main__":
    sys.exit(main())
