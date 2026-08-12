# Source and License Registry — Market Data Providers

**Review type:** §5.5 "Use licensed or otherwise authorized providers for machine-use market data"
**Reviewed on:** 2026-08-12 (UTC), by live probe
**Purpose:** §7 requires that when TradingView use is not permitted, market data be
obtained from "an independently authorized provider". This is the search for that
provider, and the record of what each one's terms actually say.

---

## 0. Why this document exists in the form it does

The TradingView review (`tradingview-terms-review.md`) established that a provider's
terms can *name* the exact uses this project needs and forbid them. That makes the
selection criterion sharper than "is there an API?":

> **A provider is usable only if its terms permit NON-DISPLAY / MACHINE use of the
> data, because that is the only kind of use a local LLM makes.**

Every value this system touches is read by a program, not a person. So "free API,
generous limits" is irrelevant if the licence is display-only. This is the single
question asked of each candidate below.

**A second, honest criterion:** the answer must be *findable*. A provider whose
terms are silent on non-display use is recorded as UNKNOWN, not as permitted.
Silence is not permission — that is the mistake this project refuses to make.

---

## 1. Probe results (VERIFIED)

`User-Agent: marfin-llm/0.1 (compliance-review; contact@example.com)`

| Candidate | Terms URL | HTTP | Bytes | sha256₁₆ | Non-display use |
|---|---|---|---|---|---|
| **Twelve Data** | `twelvedata.com/terms` | 200 | 184,690 | — | ✅ **defined and licensed by tier** |
| Alpha Vantage | `alphavantage.co/terms_of_service/` | 200 | 127,102 (**PDF**) | `2282b2a77e9fa981` | ⬜ silent — no non-display clause |
| FRED (St. Louis Fed) | `fred.stlouisfed.org/legal/` | 200 | 117,023 | — | ✅ already registered, `OFFICIAL_DATA` |
| Finnhub | `finnhub.io/terms-of-service` | 200 | 16,098 | — | ⬜ silent; "personal use" ×4 |
| Polygon.io | `polygon.io/terms` | 200 | 198,610 | — | ⬜ not found in extract |
| Yahoo Finance | `legal.yahoo.com/.../otos/` | 200 | 167,944 | — | ⬜ silent; no market-data API terms |
| Stooq | `stooq.com/db/h/` | 200 | **796** | — | ❌ unreadable — JS/bot gate |
| Tiingo | `tiingo.com/about/terms` | **404** | — | — | ❌ URL wrong; not re-probed |
| EODHD | `eodhd.com/.../terms-and-conditions` | **404** | — | — | ❌ URL wrong; not re-probed |

### Probe defects I hit, recorded so nobody trusts the raw numbers

1. **Alpha Vantage's terms page is a PDF, not HTML.** My HTML-stripping extractor
   produced binary garbage that *looked* like text and yielded zero keyword hits.
   Reading meaning into that output would have produced a confident, false
   "no restrictions found". Re-extracted properly (FlateDecode streams →
   52,912 chars). **A zero-hit result from a parser that never parsed anything is
   the most dangerous kind of clean result.**
2. **Stooq returned 796 bytes:** *"This site requires JavaScript to verify your
   browser."* No terms were read. Recorded as UNKNOWN, not as unrestricted.
3. **Two 404s.** The URLs I tried were wrong. Recorded as "not verified" rather
   than guessing alternates — an unverified provider is not a candidate.
4. Keyword-hit counts are a *search aid*, not a finding. Every conclusion below
   quotes clause text.

---

## 2. Twelve Data — the only candidate whose terms affirmatively permit machine use

Verbatim definitions (from §1 of its agreement):

> "**Non-Display Use**" means any use of Data that does not involve displaying the
> Data to natural persons.
> "**Internal Use**" means use solely for Customer's internal business purposes and
> not for redistribution or external commercial purposes.
> "**Derived Data**" means data created by Customer from the Data, provided such data
> cannot be reverse-engineered to arrive at the underlying Data.

Verbatim grant (§2.2 Data license):

> "Customer is granted a limited, non-exclusive license to: (a) **Access, receive,
> process, and store Data solely for Internal Use** (or as otherwise permitted by
> your Subscription Tier or add-ons) (b) Display Data to Authorized Users… (c)
> **Create Derived Data** that cannot be reverse-engineered to recreate the original
> Data (d) **Use Data for Non-Display Use only as permitted by your subscription
> tier** (e) Redistribute… only if and as expressly authorized by a Redistribution
> Rights Add-On…"

Verbatim restrictions (§2.3) that this project must honour:

> "(c) Reverse engineer, decompile… (d) Use the Platform to build competitive
> products or services… (f) **Create derivative financial products without explicit
> written permission** (g) **Store or cache Data beyond permitted timeframes
> specified in the Documentation** (h) Use automated tools to exceed API Rate
> Limits or create excessive load… (k) **Combine Data with other sources to create
> competing products**"

### Why this is the right structural answer

Compare the two licences directly. This is the whole point of the exercise:

| | TradingView | Twelve Data |
|---|---|---|
| Non-display use | "explicitly prohibits any form" | **defined and licensed by tier** |
| Processing the data | "any processing… prohibited" | "Access, receive, **process**, and store" |
| Derived values | "creating products… based on content" prohibited | "**Create Derived Data**" permitted |
| Risk / algo use | named as prohibited | not prohibited; governed by tier |
| Storage | not permitted | permitted, **within documented timeframes** |

TradingView forbids the category of use; Twelve Data **sells** it. That is the
difference between an unusable source and a usable one.

### Honest limits on this conclusion — READ BEFORE RELYING ON IT

1. **"only as permitted by your subscription tier" is the operative clause, and I
   have not verified any tier.** No account exists, so which tier permits
   non-display use, and at what price, is **UNKNOWN**. The terms permit the
   *category*; a specific tier grants the *instance*. Labelling this VERIFIED
   would be exactly the "declared ≠ enforced" error Phase 3 caught.
2. **"Store or cache Data beyond permitted timeframes specified in the
   Documentation"** — the timeframes live in documentation I have not read. Until
   read, this project must treat market data as **non-persistable**: usable in a
   request, not written to the fact store. This is a real design constraint, not
   a footnote.
3. **"Create derivative financial products without explicit written permission"**
   is prohibited. A local analytical assistant is not obviously a "derivative
   financial product", but this is a lawyer's question, not mine. Recorded as
   a risk, not resolved.
4. **Professional-use / exchange rates** may apply depending on the user's
   affiliation. Cannot be determined from here; it depends on facts about the
   user. Recorded as UNKNOWN and surfaced to the user.

**Therefore Twelve Data is registered as `enabled=False`, `PROVISIONAL`.** It is
the *selected candidate*, not an active source. It becomes active only when a
human confirms a tier that permits non-display use. Enabling it on the strength of
a definitions section would be presenting ESTIMATED as VERIFIED.

---

## 3. Alpha Vantage — usable in principle, restricted by *who you are*

Verbatim (§2.a Grant of License, from the PDF):

> "Alpha Vantage grants the right to install, use, access, display and run the
> software on any computer or mobile device… **for personal, non-commercial use**,
> unless you and Alpha Vantage have agreed otherwise in writing…"

Usage falls outside "personal" if, verbatim:

> "i. You intend to use the Alpha Vantage Platform for any purpose that goes beyond
> personal usage… ii. You are using the Alpha Vantage Platform as or on behalf of a
> corporation, firm, partnership, trust or any other association and not as an
> individual. iii. You plan to use or provide information accessed through the
> Alpha Vantage Platform as part of any type of **commercial activity that allows
> individuals or entities other than User to access information** directly or
> indirectly… iv. You are currently employed or have an active affiliation with a
> financial planning advisor, insurance company, investment advisor, investment
> bank…"

**Searched for and NOT present** (0 occurrences each): `non-display`,
`redistribut`, `cache`, `store`, `derived`, `scrap`, `attribut`. Also 0 for
`non-commercial` as a single token — it appears hyphenated across the PDF's
character spacing as "non - commercial".

**Reading:** Alpha Vantage restricts **who** may use it and **for what commercial
purpose**. It does **not** prohibit machine processing. For a single individual
running a local analytical assistant, personal use appears to fit. But:

- Criterion (iv) is decisive and **user-specific**: if the user is employed by or
  affiliated with an investment advisor, bank, or insurer, personal-use terms do
  **not** apply. This is a **fact about the user that I cannot know**, so it must
  be asked, not assumed.
- The absence of a non-display clause is **not** an affirmative grant. Compared to
  Twelve Data's explicit licence, this is weaker ground: UNKNOWN-leaning-permitted
  rather than permitted.

Registered `enabled=False`, `PROVISIONAL`, with the user-affiliation question
recorded as a blocking prerequisite.

---

## 4. FRED — already registered, and the one unambiguous case

Registered in Phase 3 (`fred`, `OFFICIAL_DATA`, `requires_api_key=True`, MEASURED
HTTP 400 without a key). US federal-government economic data, and the terms page
was probed again here (HTTP 200, 117,023 B). It remains the project's only
**enabled** numeric-data source, and it covers macro series — **not** equity
quotes. So it does not solve the market-data problem; it solves a different one.

---

## 5. What this means for Phase 3A (the honest conclusion)

**No market-data provider is enabled at the end of this review.** That is the
correct outcome, not a failure to finish:

- TradingView: **prohibited** by licence. Closed.
- Twelve Data: **selected candidate**, blocked on tier verification.
- Alpha Vantage: **fallback candidate**, blocked on a user-affiliation question.
- Stooq / Tiingo / EODHD: **not verified** (JS gate; wrong URLs).
- Polygon / Finnhub / Yahoo: probed, non-display terms **not located**; not pursued.

Consequently the market-data layer is built as an **interface with no live
provider**: the §5.5 field set, the trust labelling, and the refusals are real and
tested; the network fetch is absent. This is deliberate. A connector written
against unverified terms would be a licence violation waiting for an API key, and
Phase 3 already proved that unenforced declarations drift.

**Question for the user (blocking, do not guess):**
1. Are you willing to pay for a Twelve Data tier that permits non-display use?
2. Are you employed by, or affiliated with, a financial advisor, investment
   adviser, bank, or insurance company? (Decides Alpha Vantage eligibility.)

Until answered, the system runs at **Level 0/2**: the user supplies OHLCV, or an
exported CSV. §7.1 Level 0 explicitly contemplates exactly this.

## 6. Status labels

- All HTTP statuses, byte counts, hashes, quoted clauses: **VERIFIED** (probed 2026-08-12)
- "Twelve Data permits non-display use *at some tier*": **VERIFIED** as to the category, **UNKNOWN** as to which tier
- "Alpha Vantage permits personal machine use": **COMPUTED** from the absence of a non-display clause plus the personal-use grant — *not* an affirmative permission
- Cache/storage timeframes, pricing, professional-use status: **UNKNOWN** — not probed
- Stooq, Tiingo, EODHD terms: **UNKNOWN** — could not be read
