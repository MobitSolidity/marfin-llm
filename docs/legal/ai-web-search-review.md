# Can "AI web search" replace APIs for news and social media?

**Question asked (Request 45):** *"Is it possible, instead of using APIs for reading news
and social media, to use the web search capability of AIs? If yes, then use this very
approach in the project."*

**Answer: No — and the reason is not a technical limitation, it is that the proposal
inverts the constraint it is trying to escape.** Every claim below is quoted verbatim
from the provider's own terms, fetched and payload-checked on **2026-08-30**.

**Status of this document:** VERIFIED (licence text read verbatim from each vendor's own
terms page). No provider was registered, no key was obtained, nothing was paid for.

---

## 0. Why the question is a good one

It is worth stating plainly that this was not a naive suggestion. It is the *obvious*
engineering move, and it appears to solve three real problems at once:

- Bloomberg, FT and Reuters are the most authoritative financial sources on earth, and
  `docs/legal/research-and-news-sources.md` §5 had to place all three in TIER C
  (prohibited) — not for quality reasons but because their licences forbid machine use.
- No news API in that review survived both the authority test and the permission test.
- An AI with web search visibly *can* read those sites and answer questions about them.

So the intuition is: if the search tool can read it, let the search tool read it.

The reason that fails is worth encoding, because a future maintainer will re-propose it.

---

## 1. The load-bearing distinction: transport vs. licence

A search tool changes **how you reach** the text. It does not change **what you are
allowed to do with it**.

The prohibitions recorded in this project are written against the *use*, not the *route*:

| Source | Verbatim prohibition | What it binds |
|---|---|---|
| Bloomberg | "may not be used to **construct a database of any kind**. Nor may the Service be stored (in its entirety or in any part) in databases" | the storage/use |
| FT | "any manner for any **machine learning and/or artificial intelligence** purposes" | the purpose |
| Thomson Reuters | §3(f), §3(g)(v)(1) | the use |

None of these say "do not reach this text via a crawler." They say do not build a
database, do not use it for AI. Reaching identical text through a search index and then
storing it in a vector store performs the prohibited act. The route is irrelevant.

**The most useful confirmation of this comes from a search vendor arguing against its own
commercial interest.** Brave's own Search API FAQ, under "What about copyright?":

> "The Brave Search API **does not grant any rights to third-party content** such as
> webpages. Customers who access URLs displayed in the Brave Search API must ensure their
> access to those webpages **complies with the copyright terms of the page publishers**."

And in its Terms of Use §9(d):

> "Third-Party Content may be referenced, linked to or included in Search Results that is
> **proprietary to a third party and not Provider**"

The company selling the search API states that buying it does not buy rights to what it
finds. Tavily says the same thing in §10.2:

> "You are **solely responsible and liable for complying with all terms, conditions and
> policies imposed by Third-Party Service Providers**"

So the licence problem is not routed around. It is inherited.

### 1.1 The one distinction that *is* real

There is a genuine line worth drawing, and it should not be collapsed:

- **A search index's own snippets and metadata** (title, URL, publication date, the
  index's own summary) are the search provider's product, licensed by the search
  provider's terms. This *could* in principle be permissible.
- **The article body**, fetched from the publisher, is the publisher's content under the
  publisher's terms. This is not.

That distinction is why GDELT was reviewed favourably in
`research-and-news-sources.md` §4.1 — it licenses *its own* metadata (events, entities,
tone, URLs) very permissively, and its terms are the best in the whole review.

But the distinction does not rescue the proposal, because of §2.

---

## 2. The search providers themselves forbid the RAG step

This is the part that settles it. Even if publisher rights were somehow not an issue, the
search providers prohibit storing their results — which is the entire mechanism a RAG
corpus needs.

### 2.1 Google — "Grounding with Google Search"

`https://ai.google.dev/gemini-api/terms`, effective **March 23, 2026**, HTTP 200.

**It is a paid service when used programmatically:**

> "'Grounding with Google Search' is a Service that provides Grounded Results and Search
> Suggestions and can be used through Google AI Studio (as an **Unpaid Service**), and
> **via Gemini API as a (Paid Service)**."

That alone ends it under the standing "spend nothing" constraint (Request 23): the free
path is the *interactive web UI*, not the API a program can call.

**It forbids caching, analysis and learning:**

> "You will not, and will not allow your end user or any third party to, **cache**, frame,
> syndicate, resell, **analyze, train on, or otherwise learn from** Grounded Results or
> Search Suggestions."

**And it names index-building as a violation — in language that describes a RAG pipeline
almost exactly:**

> "it is a violation of these terms to use Grounding with Google Search to extract or
> collect one or more of these components for another purpose (for example, using
> programmatic or automated means to collect Links, **using Links to build an index**, or
> **using Links to identify destination pages for crawling or scraping**)."

"Use links to identify destination pages for crawling" is a precise description of the
proposed design. It is the named example of a breach.

The storage carve-out that does exist is display-bound, not corpus-bound: results may be
kept "for up to two (2) years" only "to evaluate and optimize the **display** of the
Grounded Results", or in an end user's chat history, or transiently to refine a prompt.

**A separate problem for a financial assistant on the free tier:**

> "Google uses the content you submit to the Services and any generated responses to
> provide, improve, and develop Google products"
>
> "human reviewers may read, annotate, and process your API input and output"
>
> "**Do not submit sensitive, confidential, or personal information to the Unpaid
> Services.**"

This project handles portfolios and positions. Sending them to the unpaid tier is
contraindicated by the provider itself. Google also states:

> "Don't rely on the Services for medical, mental health, legal, **financial** or other
> professional advice."

### 2.2 Brave Search API

Terms of Use "Last Updated: 11 February 2026", HTTP 200.

**§3(b)(i) prohibits the corpus outright:**

> "Customer shall not ... **store, cache, or create a database of Search Results**, in
> whole or in part, other than **transient storage** required for operation of Customer
> Applications"

A persistent RAG index *is* a database of search results. "Transient" is the opposite of
what a retrieval corpus is for.

**§3(b)(xiii):**

> shall not "use the Search Results to create, evaluate, train, re-train, fine-tune,
> **benchmark** or otherwise improve artificial intelligence models or services"

Note "benchmark" — that would also cover using search results in this project's Phase 4
evaluation harness.

**§13(c), on termination:**

> "cease using, destroy, and **permanently erase all copies** of ... Search Results"

**On cost:** the pricing page advertises "$5 in free credits every month", but the FAQ
states:

> "**Why is a credit card required to subscribe to a free plan?** The credit card
> requirement serves as an anti-fraud measure ... For free plans, the card is only used to
> confirm your identity and will not be charged."

A card on file is not "spend nothing" in the sense the user set, and the free credits are
metered against a billable account.

### 2.3 Tavily — excluded by name for this exact domain

`https://www.tavily.com/terms` (HTTP 200 after a 302 from `tavily.com/terms`).

Tavily is the most frequently recommended "free tier" AI-search API, so it deserved a
careful read. Its §6.4 disqualifies this project explicitly:

> "you specifically agree that you will **not** use the AI Functionality or Outputs in
> connection with safety-critical systems, medical diagnosis or treatment decisions, legal
> proceedings or legal advice, **financial investment decisions**, regulatory compliance
> determinations, or any other context where accuracy and reliability are essential and
> where errors could cause substantial harm."

This project is a financial analysis assistant. "Financial investment decisions" is its
subject matter. §3.2(xvi) repeats the point:

> shall not "use the Services or the Output to make automated decisions without human
> oversight that have a significant adverse impact on individual rights in high-risk areas
> such as employment, healthcare, **finance**, legal, housing, insurance"

**It also trains on the queries you send it** — §6.5:

> "Tavily and its third-party artificial intelligence service providers may use, process,
> analyze, and **retain Customer Input** submitted to the AI Functionality and Outputs ...
> for purposes of **training**, improving, developing, and enhancing artificial
> intelligence models"

§6.7 adds that "certain Third-Party Service Providers **may not be required to maintain
the confidentiality** of any Customer Input or Output." For a tool whose queries would
contain a user's holdings, that is disqualifying independently of the licence.

---

## 3. It is not even an alternative to an API

The framing "use web search **instead of** APIs" contains a category error worth naming,
because it is the part that cannot be fixed by finding a friendlier vendor.

The deliverable is a **local, offline, CPU-only llama.cpp model** —
`Qwen3.5-4B-Q5_K_M.gguf` in `C:\models` on the user's own Windows machine. llama.cpp has
**no built-in web search**. There is no latent capability here waiting to be switched on.

So "the web search capability of AIs" would have to be obtained as:

1. **A hosted search API** — which *is* an API, with a key, a rate limit, a ToS, and (for
   Google's grounding) a bill. Strictly worse than the official data APIs it was meant to
   replace: SEC EDGAR and the ECB/IMF/World Bank endpoints are free, need no card, and
   their terms *permit* what search terms *forbid*.
2. **A hosted LLM with search built in** (Gemini, Perplexity, etc.) — same conclusion,
   plus the free tier trains on input and warns against sending confidential data.
3. **A human pasting results in by hand** — see §4. This is the only route that survives,
   and it is not automation.

The proposal therefore does not remove an API dependency. It **adds** one, with a
stricter licence and a worse privacy posture.

---

## 4. What IS permitted, and it is not nothing

The boundary this registry has always drawn is between what a **human reads** and what
**enters the machine**. It is stated in the TradingView entry in `src/rag/sources.py`:

> "A human may still read a TradingView chart or alert on screen — that is outside this
> registry, which governs only what enters the machine."

The same boundary applies here, and it leaves real capability intact:

- **The user may read anything.** Bloomberg, FT, Reuters, X/Twitter, any influential
  analyst, any AI chatbot with web search. Reading is not ingestion. No licence in this
  review restricts a human reading a page they have lawful access to.
- **The user may paste an excerpt into the tool** as ordinary conversational input. That
  is the user exercising their own access, under their own judgement, for their own
  single-user analysis — not the project building a corpus from a prohibited source. The
  provenance of such text is `UNVERIFIED`, and the answer gate must treat it as such.
- **The tool may cite and link** without ingesting.

The practical consequence: for *news and social sentiment*, this project's honest design is
**human-in-the-loop**, not automated ingestion. For *facts and numbers* — filings,
macro data, research — the automated path is already registered and legal:
SEC EDGAR, FRED, ECB, IMF, World Bank, Fed Board working papers, OFR, arXiv q-fin.

That is not a downgrade of the project's ambition. It is the accurate scope.

---

## 5. Decision recorded in code

`src/rag/sources.py` registers `ai_web_search` as **disabled**, at trust level
`UNVERIFIED` — the same convention as TradingView, because both are **licence** refusals
rather than quality judgements, and a high trust level beside `enabled=False` would read
to a future maintainer as an oversight worth correcting.

Registering the refusal (rather than simply omitting it) means
`ingest_document(source_key="ai_web_search")` produces a refusal that **names the actual
reason**, instead of a confusing "unknown source" error.

---

## 6. Conditions that would reopen this

This conclusion is a reading of terms as they stood on 2026-08-30, not a permanent law.
It should be revisited if:

1. **A search provider publishes a licence that permits persistent storage** for local,
   non-commercial research — the specific clause to look for is an exception to the
   "no database of Search Results" restriction.
2. **The spend constraint is lifted** *and* the storage prohibition is separately resolved
   — note that paying for Google grounding does **not** remove the caching and
   index-building prohibitions, so money alone is not sufficient.
3. **A publisher licenses machine use directly** — that would make the publisher a
   registrable source and remove the need for search as a workaround entirely.
4. **The project stops being local and single-user** — this would make things *worse*, not
   better, and would also invalidate the arXiv entry, whose permission depends on the
   project remaining non-public.

Any such change requires re-reading the terms verbatim, not relying on this document.
