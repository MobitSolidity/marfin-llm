"""Adversarial probes for retrieval.py."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rag.documents import Passage, Provenance                     # noqa: E402
from rag.ingest import chunk_document, facts_from_xbrl_companyconcept  # noqa
from rag.retrieval import (FactStore, HybridRetriever,            # noqa: E402
                           PassageIndex)

P_OLD = Provenance(source="SEC EDGAR", trust_level="VERIFIED_PRIMARY",
                   filed="2024-02-01", accession="acc-old")
P_NEW = Provenance(source="SEC EDGAR", trust_level="VERIFIED_PRIMARY",
                   filed="2026-07-31", accession="acc-new")
P_NEWS = Provenance(source="SomeBlog", trust_level="PERMITTED_NEWS",
                    published="2026-07-01")


def mk(text, prov=P_NEW, entity="Apple Inc.", i=0, units=None):
    return Passage(text=text, provenance=prov, entity=entity,
                   doc_id="d", chunk_index=i, units_note=units)


print("=== R1. abstention on an empty index ===")
idx = PassageIndex()
r = idx.search("revenue")
print("  ok=%s reason=%r" % (r.ok, r.reason))

print("\n=== R2. abstention when nothing matches ===")
idx.add(mk("The Company is exposed to credit risk", i=0))
idx.add(mk("Net sales increased due to higher iPhone revenue", i=1))
r = idx.search("cryptocurrency mining hashrate")
print("  ok=%s reason=%r" % (r.ok, r.reason))

print("\n=== R3. does BM25 actually rank, or just return input order? ===")
idx2 = PassageIndex()
idx2.add(mk("Weather was mild in the quarter", i=0))
idx2.add(mk("Revenue revenue revenue growth was strong", i=1))
idx2.add(mk("Revenue was mentioned once here", i=2))
r = idx2.search("revenue")
for p, s in zip(r.hits, r.scores):
    print("  %.4f  %r" % (s, p.text[:45]))

print("\n=== R4. HARD filters: entity, lang, trust, as_of ===")
idx3 = PassageIndex()
idx3.add(mk("Apple revenue rose", entity="Apple Inc.", i=0))
idx3.add(mk("Microsoft revenue rose", entity="Microsoft Corp", i=1))
idx3.add(mk("\u062f\u0631\u0622\u0645\u062f \u0631\u0634\u062f \u06a9\u0631\u062f", entity="Apple Inc.", i=2))
idx3.add(mk("Apple revenue will moon", prov=P_NEWS, entity="Apple Inc.", i=3))
print("  no filter      :", len(idx3.search("revenue \u062f\u0631\u0622\u0645\u062f")))
print("  entity=Apple   :", len(idx3.search("revenue \u062f\u0631\u0622\u0645\u062f", entity="Apple Inc.")))
print("  lang=fa        :", len(idx3.search("revenue \u062f\u0631\u0622\u0645\u062f", lang="fa")))
print("  min_trust=90   :", len(idx3.search("revenue", min_trust=90)))
rr = idx3.search("revenue", min_trust=90)
print("    kept trust   :", [p.provenance.trust_level for p in rr])

print("\n=== R5. as_of must exclude documents filed later (leak test) ===")
idx4 = PassageIndex()
idx4.add(mk("guidance raised", prov=P_OLD, i=0))
idx4.add(mk("guidance raised again", prov=P_NEW, i=1))
r_all = idx4.search("guidance")
r_cut = idx4.search("guidance", as_of="2025-01-01")
print("  all      :", len(r_all))
print("  as_of2025:", len(r_cut), "->",
      [p.provenance.accession for p in r_cut])
print("  no future leak:", all(
    p.provenance.filed.isoformat() <= "2025-01-01" for p in r_cut))

print("\n=== R6. Persian query finds Persian passage (3 spellings) ===")
idx5 = PassageIndex()
idx5.add(mk("\u0631\u0648\u0634 \u0627\u0631\u0632\u0634\u200c\u06af\u0630\u0627\u0631\u06cc \u0634\u0631\u06a9\u062a", i=0))
for q in ("\u0627\u0631\u0632\u0634\u200c\u06af\u0630\u0627\u0631\u06cc", "\u0627\u0631\u0632\u0634 \u06af\u0630\u0627\u0631\u06cc", "\u0627\u0631\u0632\u0634\u06af\u0630\u0627\u0631\u06cc"):
    print("  %r -> %d hits" % (q, len(idx5.search(q))))

print("\n=== R7. structured facts: period_kind is a HARD filter ===")
with open("/tmp/xbrl.json") as fh:
    payload = json.load(fh)
fs = FactStore()
fs.add_all(facts_from_xbrl_companyconcept(payload, retrieved_at="2026-08-10", user_agent="probe/0.1 (me@example.com)"))
concept = fs.concepts()[0]
print("  facts:", len(fs), "| concept:", concept[:45])
allf = fs.query(concept)
q_only = fs.query(concept, period_kind="quarter")
a_only = fs.query(concept, period_kind="annual")
print("  all=%d quarter=%d annual=%d" % (len(allf), len(q_only), len(a_only)))
print("  quarter set is pure:",
      {f.period_kind for f in q_only} == {"quarter"})
print("  annual set is pure :",
      {f.period_kind for f in a_only} == {"annual"})

print("\n=== R8. newest filing first (restatement ordering) ===")
top = allf.hits[:3]
for f in top:
    print("  filed=%s end=%s val=%s accn=%s"
          % (f.provenance.filed, f.period_end, f.value,
             f.provenance.accession))
dates = [f.provenance.effective_date for f in allf.hits]
print("  monotonically non-increasing:",
      all(dates[i] >= dates[i + 1] for i in range(len(dates) - 1)))

print("\n=== R9. structured abstains on unknown concept ===")
r = fs.query("NotARealTag")
print("  ok=%s reason=%r" % (r.ok, r.reason))
r = fs.query(concept, fiscal_year=1999)
print("  ok=%s reason=%r" % (r.ok, r.reason))

print("\n=== R10. a number is NOT retrievable by text similarity ===")
idxn = PassageIndex()
idxn.add(mk("Revenue was strong and revenue trends were excellent", i=0))
r = idxn.search("revenue")
print("  lexical hit contains a figure:",
      any(ch.isdigit() for ch in r.hits[0].text))
print("  -> lexical text must never be quoted AS the number")

print("\n=== R11. hybrid keeps the two modes separate ===")
hyb = HybridRetriever(idxn, fs)
out = hyb.retrieve("revenue", concept=concept, period_kind="quarter")
for mode, res in sorted(out.items()):
    print("  %-11s ok=%-5s n=%-3d reason=%r"
          % (mode, res.ok, len(res), res.reason[:40]))
out2 = hyb.retrieve("revenue")
print("  no concept -> structured ok=%s reason=%r"
      % (out2["structured"].ok, out2["structured"].reason[:50]))

print("\n=== R12. refuses to index a bare string ===")
for desc, fn in (("passage", lambda: PassageIndex().add("just text")),
                 ("fact", lambda: FactStore().add({"val": 1}))):
    try:
        fn()
        print("  NOT REFUSED:", desc)
    except Exception as exc:
        print("  refused %-8s -> %s" % (desc, str(exc)[:55]))
