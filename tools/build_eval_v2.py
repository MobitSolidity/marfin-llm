"""Build the v2 corpus and gold set from the REAL facts fetched from EDGAR.

DESIGN RULES, each with a reason:

1. NOTHING IS INVENTED. Every magnitude, accession, filing date and period
   comes from data.sec.gov. The existing v1 fixtures used real numbers with
   FIXTURE- accessions; v2 keeps the numbers real AND makes the accessions
   real, so provenance is traceable to an actual filing.

2. ONE FIGURE PER PASSAGE IS NOT ENOUGH. The v1 passages carry several figures
   on one line ("Total net sales | 383,285 -- Total cost of sales | 214,137"),
   which is what makes the retrieval task non-trivial: the model must pick the
   right row, not just the right document. v2 keeps that shape.

3. THE DISTRACTOR MUST BE A NEIGHBOURING YEAR. A wrong-year answer is the
   single most common real failure, and it is only detectable if the wrong year
   is present in the corpus. So each company gets two adjacent fiscal years.

4. ABSTAIN CASES MUST BE ABSENT, NOT MERELY OBSCURE. A question about a company
   with no document is the only clean test of refusal.

5. IDS ARE NEW, NOT REUSED. v1 ids stay meaningful in the recorded evidence;
   reusing one would make two different questions share an id across runs.
"""
import json

F = json.load(open("/tmp/r20/facts2.json", encoding="utf-8"))

M = 1_000_000


def mm(v):
    """Whole millions, as filings state them."""
    q = round(float(v) / M)
    return q, "{:,}".format(q)


# (doc_id, entity, cik, fiscal label, period_start, period_end, accession,
#  filed, [(row label, key, end)])
SPECS = [
    ("SEC-AAPL-10K-FY2023", "Apple Inc.", "0000320193", "fiscal 2023",
     "2022-09-25", "2023-09-30",
     ("aapl_netincome", "2023-09-30"),
     [("Net income", "aapl_netincome", "2023-09-30"),
      ("Total assets", "aapl_assets", "2023-09-30"),
      ("Total shareholders' equity", "aapl_equity", "2023-09-30")]),
    ("SEC-AAPL-10K-FY2024", "Apple Inc.", "0000320193", "fiscal 2024",
     "2023-10-01", "2024-09-28",
     ("aapl_netincome", "2024-09-28"),
     [("Net income", "aapl_netincome", "2024-09-28"),
      ("Total assets", "aapl_assets", "2024-09-28"),
      ("Total shareholders' equity", "aapl_equity", "2024-09-28")]),
    ("SEC-MSFT-10K-FY2024", "Microsoft Corporation", "0000789019",
     "the fiscal year ended June 30 2024", "2023-07-01", "2024-06-30",
     ("msft_revenue", "2024-06-30"),
     [("Total revenue", "msft_revenue", "2024-06-30"),
      ("Net income", "msft_netincome", "2024-06-30"),
      ("Total assets", "msft_assets", "2024-06-30")]),
    ("SEC-MSFT-10K-FY2025", "Microsoft Corporation", "0000789019",
     "the fiscal year ended June 30 2025", "2024-07-01", "2025-06-30",
     ("msft_revenue", "2025-06-30"),
     [("Total revenue", "msft_revenue", "2025-06-30"),
      ("Net income", "msft_netincome", "2025-06-30"),
      ("Total assets", "msft_assets", "2025-06-30")]),
    ("SEC-GOOGL-10K-FY2023", "Alphabet Inc.", "0001652044", "fiscal 2023",
     "2023-01-01", "2023-12-31",
     ("goog_revenue", "2023-12-31"),
     [("Total revenues", "goog_revenue", "2023-12-31"),
      ("Net income", "goog_netincome", "2023-12-31")]),
    ("SEC-GOOGL-10K-FY2024", "Alphabet Inc.", "0001652044", "fiscal 2024",
     "2024-01-01", "2024-12-31",
     ("goog_revenue", "2024-12-31"),
     [("Total revenues", "goog_revenue", "2024-12-31"),
      ("Net income", "goog_netincome", "2024-12-31")]),
    ("SEC-JNJ-10K-FY2023", "Johnson & Johnson", "0000200406", "fiscal 2023",
     "2023-01-02", "2023-12-31",
     ("jnj_revenue", "2023-12-31"),
     [("Sales to customers", "jnj_revenue", "2023-12-31"),
      ("Net earnings", "jnj_netincome", "2023-12-31")]),
    ("SEC-JNJ-10K-FY2024", "Johnson & Johnson", "0000200406", "fiscal 2024",
     "2024-01-01", "2024-12-29",
     ("jnj_revenue", "2024-12-29"),
     [("Sales to customers", "jnj_revenue", "2024-12-29"),
      ("Net earnings", "jnj_netincome", "2024-12-29")]),
    ("SEC-WMT-10K-FY2024", "Walmart Inc.", "0000104169",
     "the fiscal year ended January 31 2024", "2023-02-01", "2024-01-31",
     ("wmt_revenues", "2024-01-31"),
     [("Total revenues", "wmt_revenues", "2024-01-31"),
      ("Consolidated net income", "wmt_netincome", "2024-01-31")]),
    ("SEC-WMT-10K-FY2025", "Walmart Inc.", "0000104169",
     "the fiscal year ended January 31 2025", "2024-02-01", "2025-01-31",
     ("wmt_revenues", "2025-01-31"),
     [("Total revenues", "wmt_revenues", "2025-01-31"),
      ("Consolidated net income", "wmt_netincome", "2025-01-31")]),
]

corpus = []
lookup = {}
for (doc_id, entity, cik, flabel, p0, p1, acc_src, rows) in SPECS:
    src = F[acc_src[0]]["by_end"][acc_src[1]]
    parts = []
    for label, key, end in rows:
        rec = F[key]["by_end"][end]
        q, txt = mm(rec["val"])
        parts.append("%s | %s" % (label, txt))
        lookup[(doc_id, label)] = {"exact": float(rec["val"]),
                                   "millions": q,
                                   "accn": rec.get("accn"),
                                   "filed": rec.get("filed")}
    # THE PASSAGE MUST NAME ITS OWN COMPANY AND PERIOD.
    #
    # DEFECT CAUGHT BY MY OWN VALIDATOR, and it would have wasted a model run.
    # My first version put only the numeric rows in `text`
    # ("Net income | 96,995 -- Total assets | 352,583"). MEASURED: 5 of 15
    # questions then failed to retrieve their own gold document, and
    # SEC-NOISE-PROPERTIES outranked it -- because the words "Apple" and
    # "2023" appear in the QUERY and nowhere in the passage, so BM25 had
    # nothing to match on.
    #
    # v1 hid this: with 8 documents and one per company, near-random ranking
    # still put the right one in the top 4. At 13 documents it collapsed.
    #
    # A real filing page carries its own heading, so adding one is not a
    # concession to the retriever -- it is the fixture becoming more faithful,
    # not less.
    heading = ("%s (CIK %s) -- Form 10-K, %s, consolidated financial "
               "statements (in millions)" % (entity, cik, flabel))
    corpus.append({
        "doc_id": doc_id,
        "source_key": "sec_edgar_xbrl",
        "entity": entity,
        "entity_id": cik,
        "section_path": ["Item 8", "Consolidated Financial Statements"],
        "period_start": p0,
        "period_end": p1,
        "lang": "en",
        "units_note": "million",
        "accession": src.get("accn"),
        "filed": src.get("filed"),
        "text": heading + " -- " + " -- ".join(parts),
    })

# A Persian passage over the same real Apple FY2024 figures. Persian is not a
# decoration here: the FA arm is the only place the digit-folding and
# separator handling are exercised on text the model must read, and v1 had a
# single Persian document.
FA_DIGITS = str.maketrans("0123456789", "\u06f0\u06f1\u06f2\u06f3\u06f4"
                                        "\u06f5\u06f6\u06f7\u06f8\u06f9")
a24_ni = lookup[("SEC-AAPL-10K-FY2024", "Net income")]
a24_as = lookup[("SEC-AAPL-10K-FY2024", "Total assets")]
corpus.append({
    "doc_id": "SEC-AAPL-10K-FY2024-FA",
    "source_key": "sec_edgar_xbrl",
    "entity": "Apple Inc.",
    "entity_id": "0000320193",
    "section_path": ["\u0628\u062e\u0634 \u06f8",
                     "\u0635\u0648\u0631\u062a\u200c\u0647\u0627\u06cc "
                     "\u0645\u0627\u0644\u06cc"],
    "period_start": "2023-10-01",
    "period_end": "2024-09-28",
    "lang": "fa",
    "units_note": "million",
    "accession": corpus[1]["accession"],
    "filed": corpus[1]["filed"],
    "text": ("\u0627\u067e\u0644 (Apple Inc.) -- "
             "\u0641\u0631\u0645 \u06f1\u06f0-K\u060c "
             "\u0633\u0627\u0644 \u0645\u0627\u0644\u06cc "
             "\u06f2\u06f0\u06f2\u06f4\u060c "
             "\u0635\u0648\u0631\u062a\u200c\u0647\u0627\u06cc "
             "\u0645\u0627\u0644\u06cc "
             "(\u0645\u06cc\u0644\u06cc\u0648\u0646) -- "
             "\u0633\u0648\u062f \u062e\u0627\u0644\u0635 | %s -- "
             "\u062c\u0645\u0639 \u062f\u0627\u0631\u0627\u06cc\u06cc\u200c"
             "\u0647\u0627 | %s"
             % ("{:,}".format(a24_ni["millions"]).translate(FA_DIGITS)
                .replace(",", "\u060c"),
                "{:,}".format(a24_as["millions"]).translate(FA_DIGITS)
                .replace(",", "\u060c"))),
})

# Two noise documents with no figures, so retrieval has something to reject.
for did, txt in (
    ("SEC-NOISE-GOVERNANCE",
     "The Board maintains an Audit Committee composed entirely of independent "
     "directors. The committee reviews the scope of the annual audit and the "
     "adequacy of internal control over financial reporting."),
    ("SEC-NOISE-PROPERTIES",
     "The Company's headquarters and certain manufacturing facilities are "
     "owned, while a substantial portion of its retail and office space is "
     "held under operating leases of varying terms."),
):
    corpus.append({
        "doc_id": did, "source_key": "sec_edgar_submissions",
        "entity": "Apple Inc.", "entity_id": "0000320193",
        "section_path": ["Item 3"], "period_start": None,
        "period_end": None, "lang": "en", "units_note": None,
        "accession": corpus[0]["accession"], "filed": corpus[0]["filed"],
        # The noise documents get the SAME kind of heading as the real ones.
        # Leaving them headingless would have made them artificially easy to
        # out-rank, which would flatter the retriever rather than test it.
        "text": ("Apple Inc. (CIK 0000320193) -- Form 10-K, fiscal 2023 -- "
                 + txt),
    })

# ---- the gold questions ----------------------------------------------------
def q(qid, lang, query, doc, label, rubric_extra=""):
    info = lookup[(doc, label)]
    other = ("Answering with the neighbouring fiscal year's figure is a "
             "RETRIEVAL failure, not a model failure. ")
    return {
        "id": qid, "lang": lang, "query": query,
        "gold_doc_ids": [doc],
        "gold_magnitude": info["exact"],
        "answerable": True,
        "rubric": ("Must retrieve %s and quote %s million. %s%s"
                   "Source: SEC EDGAR XBRL, accession %s, filed %s."
                   % (doc, "{:,}".format(info["millions"]), other,
                      rubric_extra, info["accn"], info["filed"])),
    }


gold = [
    q("RAG2-EN-001", "en",
      "What was Apple's net income in fiscal 2023?",
      "SEC-AAPL-10K-FY2023", "Net income"),
    q("RAG2-EN-002", "en",
      "What were Apple's total assets at the end of fiscal 2023?",
      "SEC-AAPL-10K-FY2023", "Total assets"),
    q("RAG2-EN-003", "en",
      "What was Apple's total shareholders' equity at the end of fiscal 2024?",
      "SEC-AAPL-10K-FY2024", "Total shareholders' equity"),
    q("RAG2-EN-004", "en",
      "What was Apple's net income in fiscal 2024?",
      "SEC-AAPL-10K-FY2024", "Net income"),
    q("RAG2-EN-005", "en",
      "What was Microsoft's total revenue for the fiscal year ended "
      "June 30 2024?",
      "SEC-MSFT-10K-FY2024", "Total revenue"),
    q("RAG2-EN-006", "en",
      "What was Microsoft's net income for the fiscal year ended "
      "June 30 2025?",
      "SEC-MSFT-10K-FY2025", "Net income"),
    q("RAG2-EN-007", "en",
      "What were Microsoft's total assets at June 30 2024?",
      "SEC-MSFT-10K-FY2024", "Total assets"),
    q("RAG2-EN-008", "en",
      "What were Alphabet's total revenues in fiscal 2023?",
      "SEC-GOOGL-10K-FY2023", "Total revenues"),
    q("RAG2-EN-009", "en",
      "What was Alphabet's net income in fiscal 2024?",
      "SEC-GOOGL-10K-FY2024", "Net income"),
    q("RAG2-EN-010", "en",
      "What were Johnson & Johnson's sales to customers in fiscal 2023?",
      "SEC-JNJ-10K-FY2023", "Sales to customers"),
    q("RAG2-EN-011", "en",
      "What were Johnson & Johnson's net earnings in fiscal 2024?",
      "SEC-JNJ-10K-FY2024", "Net earnings"),
    q("RAG2-EN-012", "en",
      "What were Walmart's total revenues for the fiscal year ended "
      "January 31 2024?",
      "SEC-WMT-10K-FY2024", "Total revenues"),
    q("RAG2-EN-013", "en",
      "What was Walmart's consolidated net income for the fiscal year ended "
      "January 31 2025?",
      "SEC-WMT-10K-FY2025", "Consolidated net income"),
    q("RAG2-FA-001", "fa",
      "\u0633\u0648\u062f \u062e\u0627\u0644\u0635 \u0627\u067e\u0644 \u062f\u0631 "
      "\u0633\u0627\u0644 \u0645\u0627\u0644\u06cc \u06f2\u06f0\u06f2\u06f4 "
      "\u0686\u0642\u062f\u0631 \u0628\u0648\u062f\u061f",
      "SEC-AAPL-10K-FY2024", "Net income",
      "The answer must be in Persian. "),
    q("RAG2-FA-002", "fa",
      "\u062c\u0645\u0639 \u062f\u0627\u0631\u0627\u06cc\u06cc\u200c\u0647\u0627\u06cc "
      "\u0627\u067e\u0644 \u062f\u0631 \u067e\u0627\u06cc\u0627\u0646 "
      "\u0633\u0627\u0644 \u0645\u0627\u0644\u06cc \u06f2\u06f0\u06f2\u06f4 "
      "\u0686\u0642\u062f\u0631 \u0628\u0648\u062f\u061f",
      "SEC-AAPL-10K-FY2024", "Total assets",
      "The answer must be in Persian. "),
]

# Abstain cases: companies with NO document in this corpus. R49's cheapest
# resolution gain -- correct_abstention was short by exactly one case, so two
# are added rather than one.
# SEVEN abstain cases, not three. correct_abstention_pct_min = 90 needs n>=10
# to tolerate a single failure; v1 has 3, so v2 supplies 7 to reach exactly
# 10. My first draft added 3 and left the gap open -- the validator reported
# "short by 4", which is the whole reason it prints that line rather than
# only pass/fail.
for aid, aq, ent in (
    ("RAG2-ABST-001",
     "What was Nvidia's total revenue in fiscal 2024?", "Nvidia"),
    ("RAG2-ABST-002",
     "What was Amazon's net income in fiscal 2023?", "Amazon"),
    ("RAG2-ABST-003",
     "\u062f\u0631\u0622\u0645\u062f \u062a\u0633\u0644\u0627 \u062f\u0631 "
     "\u0633\u0627\u0644 \u0645\u0627\u0644\u06cc \u06f2\u06f0\u06f2\u06f4 "
     "\u0686\u0642\u062f\u0631 \u0628\u0648\u062f\u061f", "Tesla"),
    ("RAG2-ABST-004",
     "What was Meta Platforms' net income in fiscal 2024?", "Meta"),
    ("RAG2-ABST-005",
     "What were Intel's total revenues in fiscal 2023?", "Intel"),
    ("RAG2-ABST-006",
     "\u0633\u0648\u062f \u062e\u0627\u0644\u0635 "
     "\u0627\u0646\u0648\u06cc\u062f\u06cc\u0627 \u062f\u0631 "
     "\u0633\u0627\u0644 \u0645\u0627\u0644\u06cc \u06f2\u06f0\u06f2\u06f3 "
     "\u0686\u0642\u062f\u0631 \u0628\u0648\u062f\u061f", "Nvidia"),
    # NOT "Apple in fiscal 2019". That was a different KIND of absence --
    # the company IS in the corpus, only the year is missing -- and it is
    # genuinely arguable: a model reciting Apple's 2019 result from
    # pre-training is not fabricating in the same sense as inventing an
    # Nvidia figure. One arguable verdict inside a 10-item all-or-nothing
    # threshold is worse than one fewer case, so it was replaced with a
    # clean absent-entity question.
    ("RAG2-ABST-007",
     "What were Broadcom's total revenues in fiscal 2024?", "Broadcom"),
):
    gold.append({
        "id": aid, "lang": "fa" if aid.endswith("003") else "en",
        "query": aq, "gold_doc_ids": [], "gold_magnitude": None,
        "answerable": False,
        "rubric": ("This corpus contains no %s document. The correct "
                   "behaviour is abstention. Any figure produced here is "
                   "fabricated -- it cannot have come from the evidence."
                   % ent),
    })

with open("/home/user/webapp/evals/rag_corpus_v2.jsonl", "w",
          encoding="utf-8") as f:
    for r in corpus:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
with open("/home/user/webapp/evals/rag_gold_v2.jsonl", "w",
          encoding="utf-8") as f:
    for r in gold:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")

print("corpus rows :", len(corpus))
print("gold rows   :", len(gold),
      "(answerable %d, abstain %d)"
      % (sum(1 for g in gold if g["answerable"]),
         sum(1 for g in gold if not g["answerable"])))
print()
for r in corpus:
    print("  %-26s %-8s acc=%-22s %s"
          % (r["doc_id"], r["lang"], r["accession"], r["text"][:60]))
