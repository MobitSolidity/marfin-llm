"""Throwaway smoke test for src/rag/ingest.py. Not part of run_all.sh."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rag.documents import Provenance                      # noqa: E402
from rag.ingest import (chunk_document, detect_currency,   # noqa: E402
                        detect_scale, facts_from_xbrl_companyconcept,
                        split_blocks, unresolved_scale_passages)

FILING = """\
# Consolidated Statements of Operations (in millions)

| Item | Q3 2026 |
| --- | --- |
| Net sales | 109,417 |
| Cost of sales | 60,020 |

Net sales increased primarily due to higher iPhone revenue.

# Risk Factors

The Company is exposed to credit risk.
"""

print("=== 1. scale/currency detection ===")
print("  header  :", detect_scale("Consolidated Statements of Operations (in millions)"))
print("  bare    :", detect_scale("All amounts in thousands unless noted"))
print("  persian :", detect_scale("\u0627\u0631\u0642\u0627\u0645 \u0628\u0647 \u0645\u06cc\u0644\u06cc\u0648\u0646 \u0631\u06cc\u0627\u0644"))
print("  none    :", detect_scale("Net sales increased this quarter"))
print("  ccy usd :", detect_currency("in millions of US dollars"))
print("  ccy irr :", detect_currency("\u0645\u0628\u0627\u0644\u063a \u0628\u0647 \u0645\u06cc\u0644\u06cc\u0648\u0646 \u0631\u06cc\u0627\u0644"))

print("\n=== 2. block structure ===")
for b in split_blocks(FILING):
    print("  %-6s scale=%-9s section=%s" % (b.kind, b.scale, b.section_path))
    print("         %r" % b.text[:60])

print("\n=== 3. THE HAZARD: does the row keep its units note? ===")
prov = Provenance(source="SEC EDGAR", trust_level="VERIFIED_PRIMARY",
                  accession="0000320193-26-000020", filed="2026-07-31")
passages = chunk_document(FILING, prov, doc_id="aapl-10q-2026q3",
                          entity="Apple Inc.", period_end="2026-06-27")
for p in passages:
    print("  table=%-5s units=%-8s section=%-45s %r"
          % (p.table, p.units_note, "/".join(p.section_path), p.text[:45]))

row = [p for p in passages if "109,417" in p.text]
print("  -> row found:", len(row) == 1,
      "| units_note:", row[0].units_note if row else None,
      "| row kept with header:", bool(row and "Item" in row[0].text))

print("\n=== 4. flagged: numbers with no scale ===")
for p in unresolved_scale_passages(passages):
    print("  FLAG %r" % p.text[:60])

print("\n=== 5. table is never split even past max_chars ===")
big = "# T (in millions)\n\n" + "| a | b |\n| --- | --- |\n" + \
      "".join("| row%d | %d |\n" % (i, i) for i in range(200))
bigp = chunk_document(big, prov, doc_id="big")
print("  passages:", len(bigp), "| chars:", len(bigp[0].text),
      "| single table:", len(bigp) == 1 and bigp[0].table)

print("\n=== 6. long prose IS split ===")
prose = "# S\n\n" + ("This is a sentence about revenue. " * 120)
pp = chunk_document(prose, prov, doc_id="prose", max_chars=400)
print("  passages:", len(pp), "| max chars:", max(len(x.text) for x in pp))

print("\n=== 7. real EDGAR XBRL -> Facts ===")
with open("/tmp/xbrl.json") as fh:
    payload = json.load(fh)
facts = facts_from_xbrl_companyconcept(
    payload, retrieved_at="2026-08-10",
    base_url="https://www.sec.gov/Archives/edgar/data",
    user_agent="probe/0.1 (me@example.com)")
print("  facts:", len(facts))
kinds = {}
for f in facts:
    kinds[f.period_kind] = kinds.get(f.period_kind, 0) + 1
print("  period kinds:", kinds)
periods = {}
for f in facts:
    periods.setdefault((f.period_start, f.period_end), set()).add(
        f.provenance.accession)
multi = [k for k, v in periods.items() if len(v) > 1]
print("  periods reported by >1 filing:", len(multi))
q = [f for f in facts if f.period_kind == "quarter"][0]
print("  sample:", q.concept[:40], q.value, q.unit, q.scale,
      q.normalized_value == q.value)
print("  citation:", q.provenance.citation())

print("\n=== 8. refusals ===")
for desc, fn in (
    ("no provenance", lambda: chunk_document("x", None, "d")),
    ("not xbrl", lambda: facts_from_xbrl_companyconcept({"nope": 1})),
):
    try:
        fn()
        print("  NOT REFUSED:", desc)
    except Exception as exc:
        print("  refused %-14s -> %s" % (desc, str(exc)[:60]))
