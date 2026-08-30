# Source and License Registry — Research and News Sources

**Review type:** SS.5.2 "Permitted research" and "Permitted financial news" — the two
`TRUST_LEVELS` tiers that have **zero** registered sources (this is risk **R20**).
**Reviewed on:** 2026-08-30 (UTC), by reading each provider's live terms and probing
each candidate endpoint.
**Also closes:** **R22** — "Alpha Vantage permitted storage timeframe UNKNOWN". See §6.
**Requested by:** the user, who asked me to choose the sources myself and to include
websites, channels, social-media accounts and influential market figures.

---

## 0. The ranking rule, stated before any names

The user asked which sources are "the most credible". Credibility alone is not a
usable criterion here, because **the most credible financial outlets in the world are
the ones whose licences forbid exactly what this project does.** Bloomberg, the FT and
Reuters are at the top of any journalist's ranking and at the bottom of ours.

So a source is ranked by **two** conditions, and it must satisfy both:

> **(i) AUTHORITY** — is it primary/official, or peer-reviewable, rather than commentary?
> **(ii) PERMISSION** — do its terms permit **machine** ingestion by a local,
> non-commercial research tool?

A source failing (ii) scores **zero for ingestion** no matter how authoritative it is.
It may still be excellent for a human to read; that is a different list, and §5 keeps
it separate on purpose.

**A third criterion, inherited from `market-data-providers.md` §0 and not weakened
here:** the answer must be *findable*. Silence is recorded as UNKNOWN, never as
permission.

**A fourth, added by this review:** a favourable licence is not enough — the endpoint
must be **reachable and its payload parsed**. Two candidates passed the licence test
and failed the reachability test (§4), and they are recorded as such rather than
registered as if they worked.

---

## 1. What the tiers already mean in code

From `src/rag/documents.py`, via `src/rag/sources.py` (MEASURED by import, 2026-08-30):

```
TRUST_LEVELS = {'VERIFIED_PRIMARY': 100, 'OFFICIAL_DATA': 90, 'EXCHANGE': 80,
                'PERMITTED_RESEARCH': 50, 'PERMITTED_NEWS': 30, 'UNVERIFIED': 0}
```

Registered sources before this review (6): `sec_edgar_submissions`,
`sec_edgar_xbrl`, `fred` (enabled); `codal`, `tsetmc`, `tradingview` (disabled).

Counted by trust level: `VERIFIED_PRIMARY` 3, `OFFICIAL_DATA` 1, `EXCHANGE` 1,
`UNVERIFIED` 1 — and **`PERMITTED_RESEARCH` 0, `PERMITTED_NEWS` 0.**

That zero is the whole of R20. It is not a missing feature; it is a required SS.5.2
category with nothing serving it.

---

## 2. TIER A — permitted AND payload-verified

Probes used `-A "marfin-llm/0.1 research (contact: moham)"`. "Payload" means the
response body was parsed and real records were read out — not that a status code
was 200. (§4 explains why that distinction is not pedantry.)

| # | Candidate | Proposed tier | Licence basis (verbatim in §3) | Endpoint evidence |
|---|---|---|---|---|
| 1 | **Fed Board working papers** (FEDS/IFDP) | `PERMITTED_RESEARCH` | **public domain** | 200; channel `FRB: Working Papers`, 15 items, newest 24 Aug 2026 |
| 2 | **OFR working papers** (US Treasury) | `PERMITTED_RESEARCH` | **no copyright claimed** | 200; channel `Office of Financial Research - Working Papers`, 10 items, newest 25 Aug 2026 |
| 3 | **arXiv q-fin** | `PERMITTED_RESEARCH` | ToS **explicitly permits** local storage for research; metadata **CC0** | 200; `totalResults` **2260** for `cat:q-fin.PR` |
| 4 | **ECB Data Portal API** | `OFFICIAL_DATA` | free use with citation | 200; SDMX CSV, EUR/USD **1.1643** on 2026-08-28 |
| 5 | **IMF SDMX data API** | `OFFICIAL_DATA` | **Data** carve-out permits reuse | 200; dataflow list 445,712 bytes |
| 6 | **World Bank Indicators API** | `OFFICIAL_DATA` | personal/non-commercial | 200; US GDP **30,769,700,000,000** (2025) |
| 7 | **NY Fed** staff reports | `PERMITTED_RESEARCH` | ToS **explicitly permits** automated access + "download, store, and use" | licence read; endpoint **not probed** |

Ranks 1–3 are the answer to "permitted research". Ranks 4–6 are official data that
the project should hold anyway, and they raise a second point worth stating plainly:
**they are macro data, not company data.** The existing SEC EDGAR sources cover
filings; nothing in the registry covered the euro area, the IMF or the World Bank.

Rank 7 is licence-verified but **not** endpoint-verified, so it must not be
registered with a MEASURED status. Registering it enabled on the strength of its
licence alone would repeat exactly the error §4 exists to prevent.

---

## 3. The licence texts, verbatim

Quoting rather than summarising, because every summary of a licence in this project
has so far turned out to hide the clause that mattered.

### 3.1 Federal Reserve Board — public domain (the strongest licence found)

`https://www.federalreserve.gov/disclaimer.htm` (last update 2024-08-02):

> "Unless otherwise indicated, information on Board's website is in the public domain
> and may be copied and distributed without permission. Please cite to the Board as
> the source of the information."

Carve-out: material "identified as being associated with a non-Board (such as
materials with a copyright or trademark)" needs the third party's permission. Seals
and logos are protected by **18 U.S.C. § 709**.

**Incidental finding that matters for §6:** the Board itself publishes, verbatim,

> "This product uses the Bureau of Economic Analysis (BEA) Data API but is not
> endorsed or certified by BEA."

The Federal Reserve treats an API attribution notice as mandatory boilerplate it
must print. That is the same class of obligation this project is currently in breach
of for FRED (§6).

### 3.2 OFR — no copyright claimed

`https://www.financialresearch.gov/legal-notices/`:

> "No copyright may be claimed for any work on this website that was created by a
> federal employee in the course of his or her duties. However, credit is requested if
> you reproduce or copy any such work. If copyrighted material appears on the site, or
> is reached through a link on this site, the copyright holder must be consulted before
> the material may be reproduced."

Seals/names: 18 U.S.C. § 701, 31 U.S.C. § 333 — nothing may imply Treasury endorsement.

### 3.3 arXiv — the only source that names local storage as permitted

`https://info.arxiv.org/help/api/tou.html`, under "Things that you can (and should!) do":

> "Retrieve, store, and use the **content** of arXiv e-prints for your own personal
> use, or for research purposes."

> "You are free to use descriptive metadata about arXiv e-prints under the terms of the
> Creative Commons Universal (CC0 1.0) Public Domain Declaration."

Hard rate limit — this is a licence term, not a performance hint:

> "When using the legacy APIs (including OAI-PMH, RSS, and the arXiv API), make no more
> than one request every three seconds, and limit requests to a single connection at a
> time."

Under "Things that you must not do":

> "Store and serve arXiv e-prints (PDFs, source files, or other content) from your
> servers, unless you have the permission of the copyright holder"

> "Represent your project as endorsed or supported by arXiv.org without our permission."

**The distinction that makes arXiv usable:** storing locally for research is
permitted; *re-serving* to others is not. This project is a local, single-user,
CPU-only tool, so it sits inside the permitted case — and it must stay there. If the
project is ever published as a service, this source's basis collapses.

`rate_limit_qps` must therefore be **1/3 ≈ 0.333**, not a round number chosen for
convenience.

### 3.4 New York Fed — automated access and storage explicitly granted

`https://www.newyorkfed.org/privacy/termsofuse` (2023-06-09):

> "The New York Fed grants you a non-exclusive license ... to use, copy, and distribute
> Content for your personal or business purposes. You may:
> - Access the Content, manually or **through an automated process or device**, provided
>   your access does not have the effect of disabling, damaging, or interfering with the
>   function of the Website,
> - **Download, store, and use Content in any format or media**, ...
> - Modify and create derivative works from the Content."

Mandatory attribution when no other form is given:

> "[year] Federal Reserve Bank of New York. Content from the New York Fed subject to the
> Terms of Use at newyorkfed.org."

Conditions that bind a RAG system specifically:

> "3. If you modify any of the Content, you must clearly label the modified Content ...
> You may not attribute any modifications or derivative works to the New York Fed."

> "4. You will avoid modifying the Content or using excerpts of the Content in a manner
> that distorts or misrepresents the Content ... You may not modify the title or
> headline of the Content."

Per-content restriction with a boundary that is easy to cross by accident:

> Liberty Street Economics blog — "Distribution of Blog posts on a regular or serial
> basis and archiving or storing Blog posts in an archive **made available to the
> public** (for free or subject to a subscription) requires a separate written license
> agreement with the New York Fed."

A private local index falls outside that clause. A published archive does not.

### 3.5 ECB — data free, **papers not**

`https://www.ecb.europa.eu/services/disclaimer/html/index.en.html`:

> "users of this website may make free use of the information obtained directly from it
> subject to the following conditions: 1. When such information is distributed or
> reproduced, it must appear accurately and the ECB must be cited as the source."

> "3. If the information is modified by the user (e.g. by seasonal adjustment of
> statistical data or calculation of growth rates) this must be stated explicitly."

The carve-out, which reverses the obvious assumption:

> "As an exception to the above, any reproduction, publication or reprint, in whole or in
> part, of documents that bear the name of their authors, such as **ECB Working Papers**
> and ECB Occasional Papers, in the form of a different publication (whether printed or
> produced electronically) is permitted **only with the explicit prior written
> authorisation** of the ECB or the authors."

So the ECB **data API** is registrable and the ECB **working papers** are not. A
reviewer who had assumed "central bank ⇒ open" would have registered the papers.

### 3.6 IMF — a split verdict, with an explicit LLM prohibition

`https://www.imf.org/en/About/copyright-and-terms` (effective 2024-10-11). General
terms on *Content*:

> "The IMF prohibits the bulk download of information by automated technology without
> explicit permission and reserves the right to terminate access to its Sites or Content."

> "The IMF does not permit use of its Content or Sites for the **training of large
> language models (LLMs)** without explicit permission."

> "fair use is authorized for up to 1000 words or no more than one-quarter of the
> content, whichever is less, from any one source."

But statistical **Data** is carved out, and the carve-out says so explicitly:

> "**Notwithstanding** the general prohibition on the commercial use of IMF Content, with
> respect to published statistical data made available on IMF Sites, the following
> special terms shall govern."

> "You may download, extract, copy, create derivative works, publish, distribute, and use
> Data obtained from IMF Sites, subject to the following conditions:" — accurate
> attribution, e.g. "Source: International Monetary Fund, Database Name, <<link>>";
> integrity preserved; material transformation stated explicitly.

**Therefore: the IMF SDMX data API is registrable; IMF publications and working papers
are not.** Note also that this project *fine-tunes nothing* — it retrieves at inference
time — but the clause is broad enough that IMF prose stays out regardless.

### 3.7 BIS — permitted, with a quantified cap

`https://www.bis.org/terms_conditions.htm`:

> "Users may download, display, print out, photocopy or redistribute any BIS Material for
> non-commercial purposes."

> "Users may reproduce a limited extract of BIS Material (other than the statistics
> published in the BIS Data Portal) in other publications or products free of charge,
> provided the BIS is cited as the source."

> "By way of guidance, a 'limited extract' means any extract of **not more than 400 words
> of text or two tables or graphs** and the underlying data made available by the BIS, and
> in any case **not exceeding 10%** of the relevant publication."

This is the only licence in the review that states a machine-checkable numeric limit.
If BIS is ever enabled, that 400-word / 10% cap belongs in code, not in a comment.

### 3.8 SEC — confirms the two access rules already in the registry

`https://www.sec.gov/about/privacy-information`, "Internet Security Policy":

> "Current guidelines limit users to a total of no more than **10 requests per second**,
> regardless of the number of machines used to submit requests."

> "The SEC does not allow '**unclassified**' bots or automated tools to crawl the site."

That single word "unclassified" is *why* `requires_contact_ua=True` is a licence
condition and not politeness: a declared contact UA is what makes the bot classified.
Both existing SEC records (`rate_limit_qps=10`, `requires_contact_ua=True`) are
confirmed correct and both are load-bearing.

Dissemination:

> "Information presented on sec.gov is considered public information and may be copied or
> further distributed by users of the web site without the SEC's permission."
> "Please do not use the SEC seal or any of the other logos or artwork from this site."

---

## 4. TIER B — licence fine, endpoint not proven. Recorded, not registered as working

### 4.1 GDELT — an unrestricted licence this project cannot currently reach

`https://www.gdeltproject.org/about.html#termsofuse` is the most permissive text in
the entire review:

> "all datasets released by the GDELT Project are available for **unlimited and
> unrestricted use** for any academic, commercial, or governmental use of any kind
> without fee."

> "You may redistribute, rehost, republish, and mirror any of the GDELT datasets in any
> form. However, any use or redistribution of the data must include a citation to the
> GDELT Project and a link to this website (https://www.gdeltproject.org/)."

It is also the natural candidate for `PERMITTED_NEWS`, because it monitors "hundreds of
thousands of broadcast, print, and online news sources ... in more than 100 languages".

**But the endpoint could not be reached, and that is MEASURED:**

| attempt | command | result |
|---|---|---|
| 1 | `curl --max-time 30` | **HTTP 000** |
| 2 | `curl --max-time 90 --connect-timeout 20` | **HTTP 000** |
| 3 | repeat of 2 | **HTTP 000** |
| 4 | platform crawler (independent egress) | `ConnectionTimeoutError` |

Diagnosis — deliberately not a conclusion about GDELT being down:

- DNS **resolves**: `api.gdeltproject.org` → `104.197.47.124`
- TCP 443: `Connection timed out after 15002 milliseconds`
- **Control in the same command**: `efts.sec.gov` → **HTTP 200 in 0.087 s**

So the network path from this sandbox to that host fails. Whether GDELT itself is
healthy is **UNKNOWN from here**, and the honest record says so. It must be
registered **disabled** with the reason recorded, and re-probed from the user's
Windows machine before it is trusted.

**A second limit on GDELT, independent of reachability, that must not be lost:**
GDELT licenses *its own* datasets — event records, entities, themes, tone, and article
**URLs**. It does not license the publishers' **article body text**. Following a GDELT
URL to fetch a Bloomberg or FT article re-enters the prohibited zone of §5. GDELT is
therefore ingestible at the *headline/entity/tone/URL* level only, and that boundary
belongs in its `licence` and `scale_note` fields where it cannot be quietly forgotten.

### 4.2 BIS — favourable licence, no working endpoint found

| URL tried | result |
|---|---|
| `https://www.bis.org/doclist/wppubls.rss` | **404** (111,766-byte HTML error page) |
| `https://www.bis.org/list/wppubls/rss.xml` | **404** (111,763 bytes) |
| `https://www.bis.org/list/wppubls/index.htm` | **404** (111,763 bytes) |
| `https://www.bis.org/rss/index.htm` (to discover feeds) | fetched; **no `.rss`/`.xml` hrefs found** |

Licence: good. Endpoint: unresolved. Status: **disabled with a recorded reason**.

### 4.3 Why §4 is a section and not a footnote

Three probes in this review returned **HTTP 404 while sending 60–112 KB of HTML**:
`bis.org/doclist/wppubls.rss` (111,766 B), `federalreserve.gov/legal.htm` (82,134 B)
and `nber.org/terms-use` (60,869 B). A large body means a nicely designed error page.

This is the same failure class as the Alpha Vantage terms document, which serves a
**PDF** from a URL that looks like HTML (`market-data-providers.md` §1 records its
hash). In both cases the naive success signal — a 200, a big response — pointed the
wrong way.

The rule this review followed, and which the next one should inherit:

> **A source is "verified" only when the status code *and* the parsed payload both
> agree.** Status alone, and size alone, are each worthless.

The OFR feed is the positive case: the guessed URL `/working-papers/feed/` returned
404, so the real one (`/working-papers/feed.rss`) was found by scraping the index
page, then parsed to 10 dated items before being called verified.

---

## 5. TIER C — prohibited for machine use. Human reading only

All quoted verbatim from the providers' own terms. These are, by any journalistic
measure, among the most credible financial sources in existence. They are listed here
**because** they are credible and **still** unusable — that gap is the finding.

| Source | The clause that closes it |
|---|---|
| **Bloomberg** | "The Service and the information contained therein **may not be used to construct a database of any kind**. Nor may the Service be stored (in its entirety or in any part) in databases" — and "You shall not use ... any scraper, robot, bot, spider, data mining, computer code ... to access, acquire, copy, or monitor any portion of the Service" |
| **Financial Times** (§3.5) | "we expressly prohibit any use of our content or data (including any associated metadata) in any manner for any **machine learning and/or artificial intelligence** purposes" |
| **Thomson Reuters** (Gen. Terms v5.1 §3(f), §3(g)(v)(1)) | "you must not ... **mine, scrape, index**, or otherwise automatically access, collect, copy, download or record the Property"; "use the Property (1) to **develop, train, adapt, fine-tune, modify or improve any artificial intelligence software**" |
| **Reuters Connect** (§2.5) | "No Use in Training AI or Machine Learning Technologies" |
| **IMF publications** | "does not permit use of its Content or Sites for the **training of large language models (LLMs)** without explicit permission" (the *data* API is separately permitted — §3.6) |
| **ECB working papers** | need "explicit prior written authorisation" (the *data* API is separately permitted — §3.5) |
| **TradingView** | machine use prohibited by licence — already disabled in the registry |

Bloomberg deserves the specific note that its clause names **this project's exact
architecture**: a database of retrieved financial content. There is no reading of it
under which a RAG corpus is permitted.

**Consequence for the answer the user asked for:** the "most credible websites" are
mostly in this table. The honest answer is that they are excellent for a human to read
and legally unavailable to the machine — not that they are unimportant.

---

## 6. R22 answered, and a compliance gap found while answering it

### 6.1 Alpha Vantage has no storage clause at all (MEASURED)

R22 asked how long Alpha Vantage data may be stored. Four places in
`market-data-providers.md` record this as **UNKNOWN** (lines 228, 317, 367, 415).
(I first wrote "five places, lines 109, 228, 317, 367, 415" and checked it: line 109 is
a TradingView-vs-Twelve-Data comparison row, not an UNKNOWN record. Corrected here
rather than left as a plausible-looking count.)

The terms document was re-extracted (it is a **PDF**, per §1 of that doc) with `pypdf`
— 4 pages, 9,882 characters — and scanned. Result: **zero occurrences** of
`stor`, `retention`, `cache`, `redistribut`, `archive`, `persist`, `delete`,
`historical`. The only two hits for `retain` are IP-ownership clauses, not data
retention.

> **R22's answer: there is no permitted-storage timeframe, because there is no storage
> clause.** The terms are silent.

Silence is not permission (§0). So the operative constraint is **not** a timeframe but
§2's "personal, **non-commercial** use only", already handled by the recorded
`USER_ACCEPTED_RISK` in `market-data-providers.md` §7. The non-persistable treatment
should stay — but its stated *reason* changes from "the timeframe is unknown" to "no
storage right is granted at all", which is a stronger and more defensible position.

Also recorded from that PDF: **§20 binds the Economic Indicators and Commodities APIs
to the FRED API terms of use.** Which leads directly to §6.2.

### 6.2 A live compliance gap: the FRED notice is missing (MEASURED)

FRED's API terms (`https://fred.stlouisfed.org/docs/api/terms_of_use.html`) require a
**verbatim** notice:

> "This product uses the FRED® API but is not endorsed or certified by the Federal
> Reserve Bank of St. Louis."

Measured on 2026-08-30, **before this document existed**:

```
$ grep -rn "not endorsed or certified" --include=*.py --include=*.md --include=*.json .
(no output)
```

The string appeared **nowhere** in the project.

**Re-running that exact command now will match — this file quotes the notice twice.**
So the check that stays reproducible is the one restricted to code and config, which is
where compliance actually has to live:

```
$ grep -rln "not endorsed or certified" --include=*.py --include=*.json .
(no output — 0 files)
```

Quoting an obligation in a legal review is not discharging it. The notice still has to
be emitted by the program, and it is not. `fred` is a registered, **enabled**
source, so the obligation is live now, not hypothetical. §3.1 shows the Federal
Reserve Board printing the equivalent BEA notice on its own site — this is normal,
expected boilerplate that this project simply has not written.

This is a **new risk**, not part of R20 or R22, and it is filed as such. Note the
shape of it: the registry recorded FRED's per-series copyright caveat correctly and
still missed a flat, unconditional obligation. Recording *some* of a licence is not
the same as complying with it.

FRED also requires that all copies be destroyed on termination, and warns that
"copyrighted series contain the word 'Copyright' in their notes" — a per-series check
no code in the project performs yet.

---

## 7. TIER D — the social-media and influencer question

The user explicitly asked for Twitter/X accounts, channels, and "the world's
influential people in financial markets". This section answers it, and the answer is
not the one the question anticipates.

### 7.1 Three independent blockers, each sufficient on its own

**(1) Cost.** `https://docs.x.com/x-api/getting-started/pricing` — pay-per-usage, no
subscriptions, **no free tier**. Posts: Read **$0.005 per resource**; User: Read
$0.010; Trends $0.010/request; 24-hour UTC deduplication. This collides directly with
the standing constraint "free tier only, spend nothing".

**(2) Access — confirmed by an independent third party.** RePEc/IDEAS maintained the
one ranking of economists that was objective rather than editorial. Its page now says,
verbatim (HTTP 200, confirmed genuine HTML with `file`):

> "This page stopped being updated after **Twitter removed third-party access to its
> API** (Application Programming Interface). The last available one is for the end of the
> year 2022."

A major academic infrastructure project **abandoned** its Twitter ranking because the
API closed. That is evidence independent of price.

**(3) Copyright.** Individual posts are third-party copyrighted works. No X term grants
a licence to ingest them into a retrieval corpus. Even with money, the licence question
would remain open — and under §0, unresolved means UNKNOWN, which means out.

### 7.2 What can honestly be delivered

A **human-reading list** — genuinely useful, and outside the machine's evidence base.
It cannot be registered in `src/rag/sources.py`, and presenting it as ingestible would
be a fabrication of exactly the kind this project's labelling rules exist to prevent.

### 7.3 The ranking principle that replaces follower count

Ranking influencers by reach would be worthless here. The useful ordering is
**institutional verifiability**: *does this person's claim trace back to a document the
system can cite?*

> Every genuinely market-moving statement by a central banker, a regulator, or a filing
> company exists **first** in a Tier-A source this project **can** ingest — the FOMC
> statement, the filing, the ECB or IMF release. The influencer supplies speed and
> interpretation; the primary document supplies the citable fact.

For a system whose stated design goal is **claim-level citation**, the primary document
is strictly better evidence than a post reacting to it. So the influencer list is best
used by the *human* to decide **what to ask about**, while the machine answers from
Tier A. That is not a workaround for the licence problem — it is a better architecture
that the licence problem happens to force.

---

## 8. Status labels

- The trust-level counts, the two empty tiers, the `grep` for the FRED notice, the
  Alpha Vantage zero-hit keyword scan, every HTTP status and every parsed payload in
  §§2/4, the GDELT timeout with its SEC control: **MEASURED** (2026-08-30)
- Every licence quotation in §§3/4.1/5/7: **VERIFIED** verbatim against the live page
  on 2026-08-30
- "This project's use falls inside arXiv's and the NY Fed's permitted case":
  **COMPUTED** from the quoted clauses plus the user's stated non-affiliation and the
  local, single-user, non-public design — *not* independently confirmed by the provider
- NY Fed endpoint behaviour: **UNKNOWN** — licence read, endpoint not probed
- Whether GDELT and BIS are reachable from the user's own machine: **UNKNOWN** — they
  failed from this sandbox only
- NBER, SSRN and World Bank OKR terms: **UNKNOWN** — not established in this review
  (`nber.org/terms-use` returned 404; OKR did not load). They are candidates, not
  findings, and are deliberately left out of §2.

## 9. Revisit conditions

- **The project stops being local, single-user and non-public** → arXiv §3.3 ("store
  and serve ... from your servers" is prohibited) and the NY Fed blog clause (§3.4)
  both fail. Ranks 3 and 7 must be **disabled**, not re-argued.
- **Any output is provided to another person or entity, or any commercial use begins**
  → the World Bank and BIS non-commercial conditions fail, and the Alpha Vantage
  criteria in `market-data-providers.md` §7.9 fail with them.
- **Fine-tuning on retrieved text is ever added** → the IMF LLM-training clause (§3.6)
  bites even on the data carve-out's neighbourhood, and the whole of §5 hardens.
- **A terms document changes** → re-read before further use; do not rely on this
  document's quotations, which are dated 2026-08-30.
