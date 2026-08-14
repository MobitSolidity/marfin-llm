# Source and License Registry — Market Data Providers

**Review type:** §5.5 "Use licensed or otherwise authorized providers for machine-use market data"
**Reviewed on:** 2026-08-12 (UTC), by live probe
**Amended on:** 2026-08-14 (UTC) — see **§7**, which supersedes the conclusion in
§5. One provider (Alpha Vantage) is now **enabled**, on a recorded
`USER_ACCEPTED_RISK` basis rather than on a found permission. §§1–6 are left
exactly as written on 2026-08-12: they are the record of what was known then, and
rewriting them to match the current state would destroy the evidence that the
decision was made under acknowledged uncertainty.
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

> **SUPERSEDED 2026-08-14 by §7.** Both blocking questions below were answered by
> the user, and one provider is now enabled. This section is preserved unedited
> because it states the position *before* those answers, and because its second
> question turned out to be the one that mattered.

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

---

## 7. Amendment, 2026-08-14 — the two blocking questions, answered

Recorded on the day the answers were given, and separated into what the **user
stated**, what was **re-measured**, and what was **decided** as a consequence.
Those three are different kinds of fact and are labelled as such throughout.

### 7.1 The terms were re-probed BEFORE the old analysis was relied on

The 2026-08-12 reading is only usable if the document it read has not changed.
Re-probed on 2026-08-14:

| Item | 2026-08-12 | 2026-08-14 | Verdict |
|---|---|---|---|
| Alpha Vantage terms, sha256 (first 16) | `2282b2a77e9fa981` | `2282b2a77e9fa981` | **byte-identical** |
| `non-display` occurrences | 0 | 0 | unchanged |

**VERIFIED.** The clause-level analysis in §3 therefore still applies to the
document actually published today, rather than to a remembered version of it. Had
the hash moved, the whole of §3 would have had to be re-read before any decision.

### 7.2 Question 2 (user affiliation) — answered, and it unblocks

**User's answer, quoted:** no affiliation with any institution or person; building
the project alone.

This is the answer criterion (iv) needs. Verbatim from the terms, usage falls
outside "personal" if *"You are currently employed or have an active affiliation
with a financial planning advisor, insurance company, investment advisor,
investment bank…"* — and criteria (ii) and (iii) likewise turn on acting for an
organisation or providing access to others.

**Status: VERIFIED as a statement by the user** — not independently verifiable by
this system, and it does not need to be. It is a fact about the user, which is why
§3 recorded that it *must be asked and not assumed*. The eligibility conclusion is
**COMPUTED** from that statement plus the quoted clauses:

- (ii) not acting as or for a corporation, firm, partnership or trust → satisfied
- (iii) no commercial activity giving others access to the data → satisfied
- (iv) no employment or active affiliation with an advisor, bank or insurer → satisfied

So the *personal, non-commercial* grant in §2.a fits this user. **This is the one
question that was genuinely blocking, and it is now closed.**

### 7.3 Question 1 (paying for a Twelve Data tier) — answered: no

**User's answer, quoted (Persian):** «فقط از بخش رایگان استفاده کن و هزینه ای نکن
یعنی از Alpha Vantage استفاده کن» — *use only the free part, spend nothing, i.e.
use Alpha Vantage.*

**Consequence, and it is a real loss rather than a formality:** Twelve Data was the
*stronger* candidate on licence grounds — §2 recorded it as having an **explicit**
non-display permission at some tier, which is affirmative authorisation of exactly
the kind this project prefers. Alpha Vantage has no such clause; it is merely
**silent**. Choosing the free option therefore means accepting **weaker legal
ground in exchange for zero cost**, and that trade is the user's to make and is
recorded here as theirs.

**Twelve Data is closed** for the duration of this decision — not disqualified. If
the user ever chooses to pay, §2's blocking item (verify *which* tier carries the
non-display right, in writing) is still the correct next step.

### 7.4 What is still NOT permitted, and why silence did not become permission

The user's answers resolve *who may use* Alpha Vantage. They do **not** create a
machine-use grant, because no such grant exists in the document:

- `non-display` still occurs **0 times** (MEASURED, twice, two days apart).
- Therefore `permits_machine_use` is recorded as **`None` (UNKNOWN)** in the
  provider registry — *not* `True`.

This is enforced in code and not merely written here. `Provider.__init__` refuses a
provider whose `permits_machine_use` is `None` unless a **separate**
`activation_basis` field carries an explicit decision; the authorisation is *not*
smuggled into the permission field. The distinction is the whole point:

> **A provider that is silent stays silent in the registry. What changes is that a
> named person has accepted the risk of proceeding anyway.**

Two limits are absolute and unaffected by any user consent:

1. **A PROHIBITION cannot be consented past.** `assert_provider_usable` checks for
   prohibition *before* it checks for an accepted risk, so no `USER_ACCEPTED_RISK`
   flag can enable TradingView. A user may accept an UNKNOWN; a user may **not**
   authorise what a licence forbids. This ordering is mutation-tested.
2. **Storage timeframes remain UNKNOWN**, so fetched market data stays
   **non-persistable**. The in-memory request budget is explicitly *not* a cache,
   and says so in its own docstring.

### 7.5 The free tier's MEASURED limits — enforced, not documented

Probed 2026-08-14 and recorded in `FREE_TIER_LIMITS`, which is *executable* rather
than advisory:

| Limit | Value | Status |
|---|---|---|
| Requests per **day** | **25** | MEASURED |
| Permitted delay status | `END_OF_DAY`, `UNKNOWN` | MEASURED |
| Realtime / 15-minute delayed | **premium only** | VERIFIED, quoted |

Quoted from the support page: *"Realtime and 15-minute delayed US market data is
regulated by the stock exchanges, FINRA, and the SEC"* — and is premium-only. This
is a **regulatory** boundary, not a rate limit: there is no clever request that
gets around it, and pretending otherwise would produce a quote labelled `REALTIME`
that is nothing of the kind. `assert_tier_supports` refuses such a request
**before** the budget is spent, so asking for data the tier cannot lawfully supply
does not cost one of the 25.

### 7.6 The five risks accepted, with an owner and a date

Recorded in the registry itself (`decided_by`, `decided_on`), not only in prose,
because Phase 3 established that unenforced declarations drift:

- **decided_by:** project owner (sole individual, no institutional affiliation)
- **decided_on:** 2026-08-14

Quoted **verbatim from `accepted_risks` in the registry**, in registry order, so
that this document cannot drift from the code it describes. (An earlier draft of
this section paraphrased them and got the order wrong; the paraphrase was replaced
with the actual strings after reading them back out of `PROVIDERS`.)

1. *"The terms are SILENT on non-display/machine use (0 occurrences of
   'non-display'); absence of a prohibition is not an affirmative grant, so machine
   processing is UNKNOWN-leaning-permitted, not permitted."*
2. *"MEASURED 2026-08-14 from alphavantage.co/support/: the free tier is '25 API
   requests per day'. Not 25 per minute. This is a hard design constraint, not a
   footnote."*
3. *"MEASURED 2026-08-14, quoted: 'Realtime and 15-minute delayed US market data is
   regulated by the stock exchanges, FINRA, and the SEC' and is premium-only. The
   free tier therefore CANNOT supply realtime or 15-minute-delayed quotes -- a
   regulatory limit, not a paywall to be worked around."*
4. *"Whether a local analytical assistant counts as 'personal, non-commercial use'
   if its output were ever sold or published is a lawyer's question and is NOT
   resolved. If this project stops being personal, this activation must be
   revisited."*
5. *"Cache/storage timeframes: UNKNOWN for this provider too. Market data remains
   non-persistable until read."*

Two further constraints are enforced in code but are **not** in that list, because
they are labels rather than accepted risks: every quote is stamped
`delay_status="END_OF_DAY"` (risk 3 makes anything else unavailable), and every
quote carries `trust_level="UNVERIFIED"` — usable for analysis, **never citable as
fact**, and refused outright for a material calculation.

Each quote produced by the connector carries this in its own `licence` field:
`"Alpha Vantage free tier, personal non-commercial use; terms SILENT on machine
use; enabled on USER_ACCEPTED_RISK (see docs/legal/market-data-providers.md)"` —
so a number that travels away from this document still carries the caveat, and
every clause of that string is separately asserted in the test suite.

### 7.7 What the connector measured about the API itself

Recorded here because two of these findings bear directly on whether a *licence*
is being respected, not merely on whether the code works.

1. **Every failure returns HTTP 200.** Bad symbol, unknown function, missing
   parameter and demo-key misuse: four probes, four HTTP 200s, one identical
   `Information` body. Refusal keys on the **shape of the body**; a status-code
   check would treat all four as success.
2. **An invalid API key still returns real data.** `apikey=INVALIDKEY999` returned
   a full 100-day IBM series. A successful response therefore proves **nothing**
   about authorisation — which is precisely why the licence gate lives in the code
   and cannot be inferred from the API's behaviour.
3. **A defect was found and fixed:** `adjusted=True` returned the *unadjusted*
   close while labelling the quote `ADJUSTED`. On IBM's 100-day window 96 of 100
   days differ, the relative gap peaking at **1.4351%** (largest absolute gap
   3.6692 on 2026-04-21: raw 255.6800 vs adjusted 252.0108), caused by two real
   dividend events. A wrong price wearing a correct-looking label is the exact
   failure this layer exists to prevent.
4. **A suspected second defect was measured and was not one.** Both
   `TIME_SERIES_DAILY` and `TIME_SERIES_DAILY_ADJUSTED` return the same container
   key, `"Time Series (Daily)"`. "Fixing" the identical-looking branches to the
   tidier `"Time Series (Daily Adjusted)"` would have broken every adjusted call.

### 7.8 Status labels for this amendment

- Terms hash unchanged, `non-display` count, all HTTP statuses, the 25/day limit,
  the four HTTP-200 failure bodies, the adjusted-close divergence: **MEASURED /
  VERIFIED** (2026-08-14)
- "This user qualifies as *personal, non-commercial*": **COMPUTED** from the user's
  stated non-affiliation plus the quoted clauses — *not* independently verified
- "Alpha Vantage permits machine use": **UNKNOWN**, unchanged, and deliberately
  left so in the registry
- Permitted storage timeframes, professional-use status, pricing: **UNKNOWN** —
  hence non-persistable data
- Twelve Data's specific non-display tier: **UNKNOWN** — closed by the
  no-payment decision, not resolved by it

### 7.9 Revisit conditions

This authorisation is not permanent. It must be re-examined if **any** of these
change:

- The user takes employment with, or an affiliation with, an advisor, bank,
  insurer or investment firm → criterion (iv) fails and the provider must be
  **disabled**, not re-argued.
- The project stops being a single individual's personal tool, or any output is
  provided to another person or entity → criteria (ii) and (iii) fail.
- The terms document's hash changes → §3 must be re-read from the new text before
  the provider is used again.
- The user decides to pay for data → Twelve Data's explicit non-display tier is the
  better ground and should be preferred over this accepted risk.
