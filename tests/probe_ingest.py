"""Adversarial probes for ingest.py: inputs NOT used to build it."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rag.documents import Provenance                     # noqa: E402
from rag.ingest import (chunk_document, split_blocks,    # noqa: E402
                        unresolved_scale_passages, _is_heading)

prov = Provenance(source="test", trust_level="VERIFIED_PRIMARY")

print("=== P1. is a plain prose line misread as a heading? ===")
LINES = [
    "Net sales increased primarily due to higher iPhone revenue",
    "The Company is exposed to credit risk",
    "we expect margins to improve",
    "## Risk Factors",
    "Item 1A. Risk Factors",
    "PART II",
    "CONSOLIDATED BALANCE SHEETS",
    "\u0635\u0648\u0631\u062a \u0633\u0648\u062f \u0648 \u0632\u06cc\u0627\u0646",
    "| Net sales | 109,417 |",
]
for ln in LINES:
    print("  heading=%-5s  %r" % (_is_heading(ln), ln))

print("\n=== P2. CONTENT LOSS: does prose survive chunking? ===")
DOC = """\
## Management Discussion

Net sales increased primarily due to higher iPhone revenue
Gross margin was flat year over year

## Liquidity

The Company had cash of 28,408
"""
ps = chunk_document(DOC, prov, doc_id="d")
print("  input prose lines: 3 | passages:", len(ps))
for p in ps:
    print("    section=%-28s %r" % ("/".join(p.section_path), p.text[:55]))
joined = " ".join(p.text for p in ps)
for needle in ("iPhone revenue", "Gross margin", "28,408"):
    print("  survives %-16s : %s" % (needle, needle in joined))

print("\n=== P3. flag fires when numbers have no scale ===")
NOSCALE = """\
## Liquidity

The Company had cash and equivalents of 28,408 at quarter end.
"""
ps3 = chunk_document(NOSCALE, prov, doc_id="d3")
flagged = unresolved_scale_passages(ps3)
print("  passages:", len(ps3), "| flagged:", len(flagged))
for f in flagged:
    print("    FLAG %r" % f.text[:60])

print("\n=== P4. scale note on the line directly above a table ===")
ABOVE = """\
## Statements of Operations

(in thousands)

| Item | Amount |
| --- | --- |
| Net sales | 109,417 |
"""
for b in split_blocks(ABOVE):
    print("  %-6s scale=%-10s %r" % (b.kind, b.scale, b.text[:40]))

print("\n=== P5. Persian filing ===")
FA = """\
## \u0635\u0648\u0631\u062a \u0633\u0648\u062f \u0648 \u0632\u06cc\u0627\u0646 (\u0627\u0631\u0642\u0627\u0645 \u0628\u0647 \u0645\u06cc\u0644\u06cc\u0648\u0646 \u0631\u06cc\u0627\u0644)

| \u0634\u0631\u062d | \u0645\u0628\u0644\u063a |
| --- | --- |
| \u062f\u0631\u0622\u0645\u062f \u0639\u0645\u0644\u06cc\u0627\u062a\u06cc | \u06f1\u06f2\u06f3\u066c\u06f4\u06f5\u06f6 |

\u062f\u0631\u0622\u0645\u062f \u0646\u0633\u0628\u062a \u0628\u0647 \u062f\u0648\u0631\u0647 \u0642\u0628\u0644 \u0631\u0634\u062f \u062f\u0627\u0634\u062a
"""
ps5 = chunk_document(FA, prov, doc_id="d5")
print("  passages:", len(ps5))
for p in ps5:
    print("    table=%-5s units=%-9s lang=%-3s %r"
          % (p.table, p.units_note, p.lang, p.text[:40]))

print("\n=== P5b. heading nesting: siblings vs children ===")
NEST = """\
# PART II

## Item 7. MD&A

### Liquidity

cash was tight

## Item 8. Financial Statements

see notes

# PART III

nothing here
"""
for p in chunk_document(NEST, prov, doc_id="d5b"):
    print("  %-45s %r" % (" / ".join(p.section_path), p.text[:25]))

print("\n=== P5c. scale inherited by SUBsection, cleared by sibling ===")
INHERIT = """\
## Operations (in millions)

### Segment A

revenue was 1,234

### Segment B

revenue was 5,678

## Employees

we had 164,000 people
"""
for p in chunk_document(INHERIT, prov, doc_id="d5c"):
    print("  units=%-9s %-34s %r"
          % (p.units_note, " / ".join(p.section_path), p.text[:22]))

print("\n=== P6. scale must NOT leak across sections ===")
LEAK = """\
## Operations (in millions)

| a | 1 |
| --- | --- |

## Employees

We had 164,000 employees
"""
for b in split_blocks(LEAK):
    print("  scale=%-10s section=%-22s %r"
          % (b.scale, "/".join(b.section_path), b.text[:35]))
