"""Adversarial probes for citations.py. The scale trap is the main event."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rag.documents import Passage, Provenance                      # noqa: E402
from rag.citations import (extract_numbers, verify_answer,          # noqa: E402
                           verify_claim)
from rag.ingest import chunk_document, facts_from_xbrl_companyconcept  # noqa

PROV = Provenance(source="SEC EDGAR", trust_level="VERIFIED_PRIMARY",
                  filed="2026-07-31", accession="0000320193-26-000020")

FILING = """\
# Consolidated Statements of Operations (in millions)

| Item | Q3 2026 |
| --- | --- |
| Net sales | 109,417 |
"""
row = [p for p in chunk_document(FILING, PROV, doc_id="d")
       if "109,417" in p.text][0]
print("evidence: units_note=%r table=%s" % (row.units_note, row.table))

print("\n=== C1. number extraction with scale words ===")
for t in ("Revenue was $109,417 million", "Revenue was 109.4 billion",
          "Revenue was 109,417", "Revenue grew 12%",
          "\u062f\u0631\u0622\u0645\u062f \u06f1\u06f2\u06f3 \u0645\u06cc\u0644\u06cc\u0648\u0646 \u0631\u06cc\u0627\u0644 \u0628\u0648\u062f"):
    print("  %-34r -> %s" % (t, extract_numbers(t)))

print("\n=== C2. THE SCALE TRAP: same digits, 10^6 apart ===")
good = verify_claim("Revenue was $109,417 million", row)
bad = verify_claim("Revenue was $109,417", row)
print("  'in millions' claim :", good.status)
print("     ", good.detail[:70])
print("  bare-dollars claim  :", bad.status)
print("     ", bad.detail[:100])
print("  -> digits match in BOTH; only one is true:",
      good.ok and not bad.ok)

print("\n=== C3. rounded claim is SUPPORTED, wrong number is not ===")
for c in ("Revenue was 109.4 billion", "Revenue was 109.5 billion",
          "Revenue was 120,000 million"):
    r = verify_claim(c, row)
    print("  %-32s %-13s %s" % (c, r.status, r.detail[:52]))

print("\n=== C3b. tolerance follows the claim's own precision ===")
# evidence = 109,417 million. Correct roundings vs nearby wrong figures.
for c, want in (("Revenue was 109.4 billion", "SUPPORTED"),     # 109.35-109.45
                ("Revenue was 109.5 billion", "CONTRADICTED"),  # excludes .417
                ("Revenue was 109.42 billion", "SUPPORTED"),    # 2dp rounding
                ("Revenue was 109.41 billion", "CONTRADICTED"),
                ("Revenue was 109 billion", "SUPPORTED"),       # 0dp: +-0.5
                ("Revenue was 110 billion", "CONTRADICTED"),
                ("Revenue was 109,417 million", "SUPPORTED"),
                ("Revenue was 109,418 million", "CONTRADICTED")):
    r = verify_claim(c, row)
    flag = "OK " if r.status == want else "!! "
    print("  %s%-32s %-13s (want %s)" % (flag, c, r.status, want))

print("\n=== C4. a claim with NO number is not silently passed ===")
r = verify_claim("Revenue increased substantially", row)
print("  status=%s ok=%s" % (r.status, r.ok))
print("  ", r.detail[:70])

print("\n=== C5. evidence with no units note cannot confirm a magnitude ===")
naked = Passage(text="Net sales were 109,417 for the quarter",
                provenance=PROV, doc_id="d2", chunk_index=0)
print("  units_note:", naked.units_note)
for c in ("Revenue was $109,417 million", "Revenue was $109,417"):
    r = verify_claim(c, naked)
    print("  %-32s %-13s %s" % (c, r.status, r.detail[:58]))
print("  SYMMETRY: neither reading may be SUPPORTED:",
      not verify_claim("Revenue was $109,417 million", naked).ok
      and not verify_claim("Revenue was $109,417", naked).ok)

print("\n=== C6. verify against a real EDGAR Fact ===")
with open("/tmp/xbrl.json") as fh:
    payload = json.load(fh)
facts = facts_from_xbrl_companyconcept(payload, retrieved_at="2026-08-10", user_agent="probe/0.1 (me@example.com)")
f = [x for x in facts
     if x.value == 109417000000.0 and x.period_kind == "quarter"][0]
print("  fact: %s %s scale=%s" % (f.value, f.unit, f.scale))
for c in ("Revenue was $109,417 million",
          "Revenue was 109.4 billion",
          "Revenue was $109,417",
          "Revenue was 109,417,000,000"):
    r = verify_claim(c, f)
    print("  %-32s %-13s" % (c, r.status))

print("\n=== C7. citation string is traceable ===")
print(" ", verify_claim("Revenue was $109,417 million", f).render()[:110])

print("\n=== C8. refusals ===")
for desc, ev in (("no evidence", None),
                 ("no provenance", "just a string")):
    try:
        r = verify_claim("Revenue was 5 million", ev)
        print("  %-14s -> %-13s %s" % (desc, r.status, r.detail[:50]))
    except Exception as exc:
        print("  %-14s raised -> %s" % (desc, str(exc)[:50]))

print("\n=== C9. one bad claim invalidates the whole answer ===")
ans = verify_answer([("Revenue was $109,417 million", row),
                     ("Revenue was $109,417", row)])
print("  ok=%s n=%d failed=%d must_abstain=%s"
      % (ans["ok"], ans["n_claims"], ans["n_failed"], ans["must_abstain"]))
print("  reason:", ans["reason"][:90])
allgood = verify_answer([("Revenue was $109,417 million", row),
                         ("Revenue was 109.4 billion", row)])
print("  all-good ok=%s must_abstain=%s"
      % (allgood["ok"], allgood["must_abstain"]))

print("\n=== C10. Persian claim against Persian evidence ===")
FA = """\
## \u0635\u0648\u0631\u062a \u0633\u0648\u062f \u0648 \u0632\u06cc\u0627\u0646 (\u0627\u0631\u0642\u0627\u0645 \u0628\u0647 \u0645\u06cc\u0644\u06cc\u0648\u0646 \u0631\u06cc\u0627\u0644)

| \u0634\u0631\u062d | \u0645\u0628\u0644\u063a |
| --- | --- |
| \u062f\u0631\u0622\u0645\u062f \u0639\u0645\u0644\u06cc\u0627\u062a\u06cc | \u06f1\u06f2\u06f3\u066c\u06f4\u06f5\u06f6 |
"""
fa_row = [p for p in chunk_document(FA, PROV, doc_id="d3") if p.table][0]
print("  units_note:", fa_row.units_note)
for c in ("\u062f\u0631\u0622\u0645\u062f \u06f1\u06f2\u06f3\u066c\u06f4\u06f5\u06f6 \u0645\u06cc\u0644\u06cc\u0648\u0646 \u0631\u06cc\u0627\u0644 \u0628\u0648\u062f",
          "\u062f\u0631\u0622\u0645\u062f \u06f1\u06f2\u06f3\u066c\u06f4\u06f5\u06f6 \u0631\u06cc\u0627\u0644 \u0628\u0648\u062f"):
    r = verify_claim(c, fa_row)
    print("  %-30s %-13s" % (c, r.status))
