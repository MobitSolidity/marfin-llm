"""Adversarial probes for rerank.py."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rag.documents import Passage, Provenance          # noqa: E402
from rag.rerank import rerank, _normalize_scores       # noqa: E402
from rag.retrieval import PassageIndex, RetrievalResult  # noqa: E402

FILING = Provenance(source="SEC EDGAR", trust_level="VERIFIED_PRIMARY",
                    filed="2026-06-01", accession="acc-f")
OLD_FILING = Provenance(source="SEC EDGAR", trust_level="VERIFIED_PRIMARY",
                        filed="2011-01-01", accession="acc-old")
BLOG = Provenance(source="Blog", trust_level="PERMITTED_NEWS",
                  published="2026-06-01")


def mk(text, prov, i, units=None, table=False):
    return Passage(text=text, provenance=prov, doc_id="d", chunk_index=i,
                   units_note=units, table=table)


print("=== K1. abstention passes through as empty ===")
empty = RetrievalResult([], reason="index is empty")
print("  reranked:", rerank(empty), "| len:", len(rerank(empty)))

print("\n=== K2. authority breaks a lexical tie (blog vs filing) ===")
tie = RetrievalResult([mk("revenue grew", BLOG, 0),
                       mk("revenue grew", FILING, 1)],
                      scores=[1.0, 1.0])
for h in rerank(tie):
    print("  %-16s %s" % (h.passage.provenance.trust_level, h.explain()))

print("\n=== K3. authority must NOT overrule a large lexical gap ===")
gap = RetrievalResult([mk("revenue revenue revenue", BLOG, 0),
                       mk("weather was mild", FILING, 1)],
                      scores=[9.0, 0.4])
top = rerank(gap)[0]
print("  winner:", top.passage.provenance.trust_level,
      "| text:", repr(top.passage.text[:26]))
print("  strongly-matching blog still wins:",
      top.passage.provenance.trust_level == "PERMITTED_NEWS")

print("\n=== K4. recency: old filing loses to new, same words+trust ===")
rec = RetrievalResult([mk("revenue grew", OLD_FILING, 0),
                       mk("revenue grew", FILING, 1)],
                      scores=[1.0, 1.0])
for h in rerank(rec, as_of="2026-08-10"):
    print("  filed=%s %s" % (h.passage.provenance.filed, h.explain()))

print("\n=== K5. recency bonus is BOUNDED, never negative ===")
fut = RetrievalResult([mk("revenue", FILING, 0)], scores=[1.0])
h = rerank(fut, as_of="2020-01-01")[0]   # doc filed AFTER as_of
print("  future doc recency component: %.4f (must be >= 0)"
      % h.components["recency"])
print("  score still positive:", h.score > 0)

print("\n=== K6. units note breaks a tie (quotable beats unquotable) ===")
un = RetrievalResult([mk("net sales 109,417", FILING, 0),
                      mk("net sales 109,417", FILING, 1, units="millions")],
                     scores=[1.0, 1.0])
for h in rerank(un):
    print("  units=%-9s %s" % (h.passage.units_note, h.explain()))

print("\n=== K7. min-max vs divide-by-max on near-ties ===")
print("  near-tie [40.0, 39.9] ->",
      [round(x, 4) for x in _normalize_scores([40.0, 39.9])])
print("  all-equal [5,5,5]     ->", _normalize_scores([5.0, 5.0, 5.0]))
print("  single    [7]         ->", _normalize_scores([7.0]))
near = RetrievalResult([mk("revenue", BLOG, 0), mk("revenue", FILING, 1)],
                       scores=[40.0, 39.9])
print("  near-tie winner is the filing:",
      rerank(near)[0].passage.provenance.trust_level == "VERIFIED_PRIMARY")

print("\n=== K8. reranking actually CHANGES order (not a no-op) ===")
idx = PassageIndex()
idx.add(mk("revenue revenue grew", BLOG, 0))
idx.add(mk("revenue grew steadily", FILING, 1, units="millions"))
res = idx.search("revenue grew")
print("  retriever order:", [p.provenance.source for p in res.hits])
rr = rerank(res, as_of="2026-08-10")
print("  reranked order :", [h.passage.provenance.source for h in rr])
print("  moved:", any(h.rank != h.prior_rank for h in rr))

print("\n=== K9. deterministic across runs ===")
runs = {tuple(h.passage.passage_id for h in rerank(res, as_of="2026-08-10"))
        for _ in range(5)}
print("  identical over 5 runs:", len(runs) == 1)

print("\n=== K10. refuses a bare list (abstention could not be seen) ===")
try:
    rerank([mk("x", FILING, 0)])
    print("  NOT REFUSED")
except Exception as exc:
    print("  refused ->", str(exc)[:60])

print("\n=== K11. top_k truncates after reranking, not before ===")
many = RetrievalResult([mk("revenue a", BLOG, 0), mk("revenue b", FILING, 1),
                        mk("revenue c", OLD_FILING, 2)],
                       scores=[1.0, 1.0, 1.0])
t = rerank(many, top_k=1, as_of="2026-08-10")
print("  n=%d winner trust=%s prior_rank=%d"
      % (len(t), t[0].passage.provenance.trust_level, t[0].prior_rank))
