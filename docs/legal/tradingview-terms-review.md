# Source and License Registry — TradingView

**Review type:** §7 mandatory data-use legal review (Phase 3A)
**Reviewed on:** 2026-08-12 (UTC)
**Reviewed by:** live HTTP probe of official TradingView URLs, not from memory
**Verdict:** ❌ **MACHINE USE NOT PERMITTED — EXPLICITLY PROHIBITED**
**Consequence:** §7 fallback posture is MANDATORY (see "Resulting posture" below)

> §7 of the master prompt requires TradingView terms to be "rechecked at execution
> time" and the review to be "recorded in the Source and License Registry." This
> file is that record. `src/market/tradingview.py` encodes the same conclusion as
> enforceable data so the constraint cannot be forgotten in prose.

---

## 1. Probe evidence (VERIFIED)

All URLs fetched with `User-Agent: marfin-llm/0.1 (compliance-review; contact@example.com)`.

| Document | URL | HTTP | Bytes | sha256 (first 16) |
|---|---|---|---|---|
| Terms of Use | `https://www.tradingview.com/policies/` | 200 | 218,818 | `9720fa512068bff2` |
| Privacy Policy | `https://www.tradingview.com/privacy-policy/` | 200 | 203,029 | `f5dbe90251aae03e` |
| House Rules | `https://www.tradingview.com/house-rules/` | 200 | 160,971 | `9c51ad0b33ed4988` |
| Webhooks help | `.../support/solutions/43000529348-about-webhooks/` | 200 (redirect → `-how-to-configure-webhook-alerts/`) | 538,615 | `4abf81b6872f8dad` |
| Alerts help | `.../support/solutions/43000520149-about-tradingview-alerts/` | 200 (redirect → `-introduction-to-tradingview-alerts/`) | 550,573 | `f4d7950c2c43969c` |
| Widget docs | `https://www.tradingview.com/widget-docs/` | 200 | 14,004 gzip → 124,669 | `d280e447260bebd1` (decompressed) |

### Two honest caveats about this evidence

1. **The byte hash of the terms page is NOT a stable fingerprint.** Three probes of
   the same page on the same day returned **three different** byte counts and
   hashes: 218,813 / `adac9516b1dbde35`, 218,818 / `9720fa512068bff2`, and
   218,812 / `d46ca82204f5cb9e`. The page embeds per-response variable markup.
   Across all three, the **extracted §3 clause block was byte-identical** — *that*
   is the baseline to compare. A page-hash "change" alarm therefore means nothing
   on its own, and an engineer who learns to ignore a noisy alarm has lost the
   check entirely. (A fourth probe repeated 218,812 / `d46ca822`, so the variation
   is intermittent rather than per-request — which makes it *more* misleading, not
   less: it would look stable long enough to be trusted.)

   **Baseline clause block:** 3,976 chars, sha256
   `78d348b188a0ce180d44e1babe926c90126efff08951dc6d53ac756959d8679a`
   (`tools/verify_tradingview_terms.py` recomputes and compares this).
2. **Two help URLs 302-redirected** to different slugs. The §7 URL list is stale in
   its slugs but the destinations resolve. Recorded so nobody later reports the
   original URLs as dead.

---

## 2. Verbatim controlling language (Terms of Use §3)

Section heading: *"3. Ownership of information; license to use TradingView;
redistribution of data; non-display usage"*

> "The content and market data provided on the TradingView platform, **including but
> not limited to charts, alerts, webhooks**, and any other forms of information, are
> licensed for **exclusive display-only use**. This license is strictly limited to
> personal or internal business purposes and **explicitly prohibits any form of
> non-display usage**. Such prohibited uses include, but are not limited to, any form
> of **automated trading, automated order generation, price referencing, order
> verification, algorithmic decision-making, algorithmic trading, smart order
> routing, using data in operations control or risk management programs, or any
> machine-driven processes that do not involve the direct, human-readable display of
> such data**. Such prohibited cases also include **creating products or services
> based on TradingView content, any processing of TradingView's content**, or any
> other use cases that undermine the restrictions in place by the Data Providers."

Third-party extension (this project is a third-party product, so it applies directly):

> "Notwithstanding the foregoing, we expressly forbid direct non-display usage by our
> users, as well as **the development, offering, or utilization of any third-party
> products, tools, or services designed to facilitate or enable such non-display
> usage**… it is hereby explicitly prohibited for any third party to create, offer, or
> operate any product or service that: Utilizes, repurposes, or relies upon
> TradingView's market data… for any form of automated trading, algorithmic
> decision-making, or any other non-display purposes. **Facilitates, enables, or
> encourages** TradingView users or any other parties to engage in activities that
> would constitute a breach of this policy… **Claims compatibility with, or advertises
> the use of, TradingView's features (such as webhooks) for purposes that are
> explicitly prohibited**…"

> "The provision of features by TradingView, **such as webhooks, is intended solely for
> permissible uses within the scope of display** and personal or internal business
> purposes… Any attempt by a third-party provider to claim non-usage of TradingView's
> services as a defense for facilitating prohibited uses of TradingView's data is
> hereby declared null and void."

Commercial use:

> "Except as otherwise expressly permitted by separate agreement, **we do not permit
> commercial usage of any of our services or APIs**."

Enforcement (why this is not a theoretical risk):

> "TradingView reserves the right to take any and all necessary actions, including
> legal measures… conducting audits or investigations into suspected violations, as
> well as initiating legal proceedings against any parties — whether users or
> third-party providers — found to be in breach… Consequences… include… blocking of
> the user or visitor, termination of their account, and potential legal penalties."

Absent terms, checked and recorded as UNKNOWN rather than assumed:
`"scraping"` — 0 occurrences; `"reverse engineer"` — 0 occurrences. Their absence is
**not** permission; the non-display and "any processing" clauses already cover it.

---

## 3. Mechanism inventory — what actually exists (VERIFIED by probe)

The §7 acceptance criterion is *"No unsupported Desktop API claimed."* This required
verifying a **negative**, so each candidate was probed.

| Mechanism | Exists? | Direction / nature | Usable by this project for machine data? |
|---|---|---|---|
| Widgets (`/widget-docs/`) | ✅ 200 | Embeddable **display** components for a web page | ❌ display-only by construction; renders in a browser, returns no data to us |
| Advanced Charts / Lightweight Charts libraries | ✅ 200 | Client-side **charting libraries** — you supply your own data | ✅ *as renderers only*, fed by our own licensed data |
| Alerts + Webhooks | ✅ 200 | Outbound HTTP POST carrying the **user's alert message** | ⚠️ mechanically possible, **contractually prohibited** as a trading/risk input |
| Pine Script | ✅ 200 | Runs **inside** TradingView | ❌ no egress to a local process |
| **REST API for Brokers** | ✅ 200 | **INBOUND to the broker.** "lets brokers connect their **backend systems** to the TradingView interface, so that broker partners can be supported on the TradingView Web Platform" — the broker implements endpoints **TradingView calls** | ❌ **not a client data API.** We are not a broker; this grants us nothing |
| Desktop Application | ✅ 200 | A desktop **chart client** | ❌ **no local/automation API.** Probe of the page found `localhost` ×0, `127.0.0.1` ×0, `"local API"` ×0, `webhook` ×0, `plugin` ×0, `automation` ×0, `"command line"` ×0 |

**Recorded as UNKNOWN (not as absence):** the desktop page is marketing copy, so
"no local API" is COMPUTED from the absence of any documented one, not proven from a
statement that none exists. Either way the §3 non-display clause forbids using one.

> **Therefore: no Desktop API is claimed by this project, because none is documented.**
> This is the single most common false claim in TradingView-integration projects and
> it is refused here on evidence.

---

## 4. Direct conflict with the Phase 3A design space

Phase 3A contemplates market data feeding order preview, risk checks, and webhook
intake. Mapping the prompt's own vocabulary onto the prohibition:

| What Phase 3A wanted to build | Prohibited phrase it lands on | Verdict |
|---|---|---|
| Prices feeding valuation/technicals tools | "price referencing", "any processing" | ❌ |
| Risk-limit checks on live quotes | "using data in operations control or **risk management programs**" | ❌ |
| Webhook → order intent | "automated order generation", "algorithmic trading" | ❌ |
| Order preview validated against TV quotes | "**order verification**" | ❌ |
| Routing to a broker adapter | "smart order routing" | ❌ |
| LLM reasoning over TV quotes | "algorithmic decision-making", "machine-driven processes" | ❌ |
| Advertising TV-webhook trading compatibility | "Claims compatibility with… (such as webhooks)" | ❌ |
| Human reading a chart on screen | "direct, human-readable display" | ✅ permitted |

Every automated use this phase would want is enumerated *by name*. This is not an
ambiguity to be resolved by interpretation.

---

## 5. Resulting posture — MANDATORY

§7 pre-specifies the response when use is not clearly permitted, and this review
found something stronger than "not clearly permitted": explicit prohibition. The
§7 fallback is therefore adopted **in full and without discretion**:

1. TradingView is used **only** as a human-visible chart and alert interface.
2. TradingView data is **never** the authoritative source for automated trading.
3. Market data comes from an **independently authorized provider**.
4. Execution and account state come **directly from the broker**.
5. TradingView alerts are **untrusted analytical events**.
6. Alerts are **never** routed to live-order submission.

Additional constraints this review adds beyond §7's list, because §3 is broader
than §7 anticipated:

7. **No TradingView-derived value may enter a risk calculation** — §3 names "risk
   management programs" explicitly, which §7's list does not mention.
8. **No TradingView-derived value may be persisted as a price fact** in the RAG
   store or fact tables — §3 forbids "any processing" and "creating products…
   based on TradingView content".
9. **No TradingView-derived value may be used for order verification** — named.
10. **The project must not advertise TradingView webhook trading compatibility** —
    named as an independent violation even absent data use.

### The trust level assigned, and why it is not a trust level at all

TradingView is registered with trust level `UNVERIFIED` **and** disabled for
machine use. The important part is that authority ranking is irrelevant here: this
is a **licence** refusal, not a quality refusal. A source can be perfectly accurate
and still be legally unusable. The registry must express those as independent
properties, or a future maintainer will "fix" the trust level and think the block
is lifted.

---

## 6. Re-verification instructions

Terms may change at any time ("we may change these Terms of Use at any time").

- Re-run `python3 tools/verify_tradingview_terms.py` (writes a fresh evidence record).
- **Compare the extracted §3 clause text, not the page hash** (see caveat 1).
- If the non-display prohibition is ever removed, that does **not** by itself permit
  machine use: "we do not permit commercial usage of any of our services or APIs"
  and the Data Provider restrictions are separate barriers, and any permission
  would need to be confirmed by a "separate agreement".
- Record every re-review as a new dated section here. Never overwrite this one.

## 7. Status labels

- Clause text, HTTP statuses, byte counts, hashes, redirect targets: **VERIFIED** (probed 2026-08-12)
- Mechanism directionality (broker API is inbound): **VERIFIED** (quoted from the manual)
- "Desktop app exposes no local API": **COMPUTED** from documented absence — see §3 caveat
- Whether a paid "separate agreement" could license non-display use: **UNKNOWN** — not investigated; requires contacting TradingView. This project assumes NO such agreement exists.
