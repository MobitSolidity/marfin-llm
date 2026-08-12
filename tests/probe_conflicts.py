"""Adversarial probes for conflicts.py, incl. the real 46-restatement set."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rag.documents import Fact, Provenance                        # noqa: E402
from rag.conflicts import (detect_period_mixing, resolve_facts,    # noqa: E402
                           resolve_result, staleness)
from rag.ingest import facts_from_xbrl_companyconcept              # noqa: E402
from rag.retrieval import FactStore, RetrievalResult               # noqa: E402


def mkfact(val, filed, end="2026-06-27", start="2026-03-29", kind=None,
           trust="VERIFIED_PRIMARY", accn=None, concept="Revenues"):
    return Fact(concept=concept, value=val, unit="USD",
                provenance=Provenance(source="SEC EDGAR", trust_level=trust,
                                      filed=filed, accession=accn or filed),
                period_start=start, period_end=end, entity="Apple Inc.",
                period_kind=kind)


print("=== F1. empty set abstains ===")
r = resolve_facts([])
print("  status=%s must_abstain=%s reason=%r"
      % (r.status, r.must_abstain, r.reason[:50]))

print("\n=== F2. RESTATEMENT: newest filing wins, older is reported ===")
r = resolve_facts([mkfact(109000000000.0, "2026-05-01", accn="acc-old"),
                   mkfact(109417000000.0, "2026-07-31", accn="acc-new")],
                  as_of="2026-08-10")
print("  status:", r.status)
print("  chosen: %g from %s" % (r.chosen.normalized_value,
                                r.chosen.provenance.accession))
print("  superseded:", [(f.normalized_value, f.provenance.accession)
                        for f in r.superseded])
print("  warnings:", r.warnings)
print("  ** resolution is NOT silent:", bool(r.superseded and r.warnings))

print("\n=== F3. agreeing filings are not reported as a restatement ===")
r = resolve_facts([mkfact(109417000000.0, "2026-05-01"),
                   mkfact(109417000000.0, "2026-07-31")], as_of="2026-08-10")
print("  status=%s superseded=%d warnings=%s"
      % (r.status, len(r.superseded), r.warnings))

print("\n=== F4. PERIOD MIXING is refused, not resolved ===")
mixed = [mkfact(109417000000.0, "2026-07-31", start="2026-03-29",
                end="2026-06-27"),
         mkfact(364357000000.0, "2026-07-31", start="2025-06-29",
                end="2026-06-27")]
print("  kinds:", detect_period_mixing(mixed))
r = resolve_facts(mixed)
print("  status=%s must_abstain=%s" % (r.status, r.must_abstain))
print("  reason:", r.reason[:120])

print("\n=== F5. equal authority + equal date + different value = CONFLICT ===")
r = resolve_facts([mkfact(109417000000.0, "2026-07-31", accn="a"),
                   mkfact(999000000000.0, "2026-07-31", accn="b")])
print("  status=%s must_abstain=%s" % (r.status, r.must_abstain))
print("  reason:", r.reason[:110])

print("\n=== F6. higher authority beats newer low-authority source ===")
r = resolve_facts([mkfact(109417000000.0, "2026-07-31",
                          trust="VERIFIED_PRIMARY", accn="filing"),
                   mkfact(500000000000.0, "2026-08-09",
                          trust="PERMITTED_NEWS", accn="blog")],
                  as_of="2026-08-10")
print("  status=%s chosen=%s (%g)"
      % (r.status, r.chosen.provenance.accession, r.chosen.normalized_value))
print("  newer blog did NOT win:", r.chosen.provenance.accession == "filing")

print("\n=== F7. staleness measured from PERIOD END, not filing date ===")
fresh_filing_old_period = mkfact(1.0, "2026-08-09", start="2023-01-01",
                                 end="2023-03-31")
st = staleness(fresh_filing_old_period, as_of="2026-08-10")
print("  filed 2026-08-09 about Q1-2023 -> age=%d stale=%s"
      % (st["age_days"], st["stale"]))
print("  reason:", st["reason"][:70])
recent = mkfact(1.0, "2026-07-31", start="2026-03-29", end="2026-06-27")
st2 = staleness(recent, as_of="2026-08-10")
print("  current quarter -> age=%d stale=%s" % (st2["age_days"], st2["stale"]))

print("\n=== F8. no period end -> treated as stale, not assumed fresh ===")
nofact = Fact(concept="X", value=1.0, unit="USD",
              provenance=Provenance(source="s", trust_level="OFFICIAL_DATA",
                                    filed="2026-08-01"))
st3 = staleness(nofact, as_of="2026-08-10")
print("  age=%s stale=%s reason=%r"
      % (st3["age_days"], st3["stale"], st3["reason"][:60]))

print("\n=== F9. stale chosen fact still WARNS ===")
r = resolve_facts([mkfact(1.0, "2024-01-31", start="2023-09-30",
                          end="2023-12-31")], as_of="2026-08-10")
print("  status=%s warnings=%s" % (r.status, [w[:58] for w in r.warnings]))

print("\n=== F10. different concepts are not collapsed ===")
r = resolve_facts([mkfact(1.0, "2026-07-31", concept="Revenues"),
                   mkfact(2.0, "2026-07-31", concept="NetIncomeLoss")])
print("  status=%s reason=%r" % (r.status, r.reason[:80]))

print("\n=== F11. REAL DATA: 46 multi-filing periods, one period at a time ===")
with open("/tmp/xbrl.json") as fh:
    payload = json.load(fh)
facts = facts_from_xbrl_companyconcept(payload, retrieved_at="2026-08-10", user_agent="probe/0.1 (me@example.com)")
fs = FactStore()
fs.add_all(facts)
concept = fs.concepts()[0]

# Whole quarterly set = many periods -> must refuse to collapse.
q_all = fs.query(concept, period_kind="quarter")
r = resolve_result(q_all, as_of="2026-08-10")
print("  all %d quarterly facts -> status=%s" % (len(q_all), r.status))
print("    reason:", r.reason[:95])

# Now one specific period that IS multiply reported.
groups = {}
for f in facts:
    if f.period_kind == "quarter":
        groups.setdefault((f.period_start, f.period_end), []).append(f)
multi = {k: v for k, v in groups.items() if len({
    x.provenance.accession for x in v}) > 1}
print("  quarterly periods reported by >1 filing:", len(multi))
key = sorted(multi, key=lambda k: k[1], reverse=True)[0]
grp = multi[key]
print("  period %s..%s has %d filings:" % (key[0], key[1], len(grp)))
for f in grp:
    print("     filed=%s val=%g accn=%s"
          % (f.provenance.filed, f.normalized_value, f.provenance.accession))
r = resolve_facts(grp, as_of="2026-08-10")
print("  ->", r.explain()[:150])

print("\n=== F12. structured abstention passes through ===")
empty = RetrievalResult([], reason="concept not in store", mode="structured")
r = resolve_result(empty)
print("  status=%s must_abstain=%s reason=%r"
      % (r.status, r.must_abstain, r.reason[:40]))
try:
    resolve_result(["not a result"])
    print("  NOT REFUSED")
except Exception as exc:
    print("  refused bare list ->", str(exc)[:50])
