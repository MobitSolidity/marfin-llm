"""
Source registry: what may be ingested, under what terms (SS.5.2, Phase 3).

WHY THE TERMS LIVE IN CODE
--------------------------
Phase 3 requires "define sources" and "verify terms", and the acceptance
criterion is "restricted data handled correctly". A prose note in a README
cannot enforce anything. So each source carries its access requirements as
DATA, and `check_access()` refuses a request that would violate them.

MEASURED, by live probe on 2026-08-10 (not remembered, not assumed):
  - data.sec.gov/submissions/CIK0000320193.json
        with a contact User-Agent -> HTTP 200
        with an empty User-Agent   -> HTTP 403
  - data.sec.gov/api/xbrl/companyconcept/.../Revenue...json -> HTTP 200
  - api.stlouisfed.org/fred/series/observations (no key) -> HTTP 400,
        "Variable api_key is not set"

The SEC 403 is the important one: the access rule is not advisory. Code that
omits the contact User-Agent does not degrade, it fails outright -- so the
requirement is encoded as `requires_contact_ua`.

IRANIAN MARKET DATA IS OUT OF SCOPE
-----------------------------------
Codal (codal.ir) and TSETMC are listed as DESCOPED, not as available. The user
descoped Iranian market data in Phase 0 (Q3), and sanctions/terms status was
never verified. A descoped source that stays in the registry with
`enabled=False` is safer than one silently absent: a later reader can see it
was considered and why it is off, rather than assuming it was forgotten.

Stdlib only.
"""

from types import MappingProxyType
from typing import Any, Dict, List, Mapping, Optional

# Trust levels are defined in documents.py; referenced here by name.
from rag.documents import TRUST_LEVELS


class Source(object):
    """
    A data source and the terms under which it may be used.

    IMMUTABLE AFTER CONSTRUCTION -- and that is a finding, not a style choice.
    The first execution of this module proved that with a plain mutable object
    one line re-enables a source the user descoped:

        SOURCES["codal"].enabled = True   # -> check_access("codal") passes

    The same line could drop `requires_contact_ua` (turning a MEASURED 403 into
    a mystery), or set `trust_level` to a string that is not a trust level, at
    which point `.authority` raised KeyError -- a crash, not a refusal. Terms
    that a later caller can quietly edit are not terms. So every field is fixed
    at construction, where it is validated, and nowhere else.
    """

    _FIELDS = ("key", "name", "base_url", "trust_level", "enabled",
               "requires_contact_ua", "requires_api_key", "rate_limit_qps",
               "licence", "verified_on", "verified_status", "scale_note",
               "descope_reason", "doc_url")

    __slots__ = _FIELDS + ("_frozen",)

    def __init__(self, key, name, base_url, trust_level, enabled=True,
                 requires_contact_ua=False, requires_api_key=False,
                 rate_limit_qps=None, licence="", verified_on=None,
                 verified_status="", scale_note="", descope_reason="",
                 doc_url=""):
        object.__setattr__(self, "_frozen", False)
        if not key or not isinstance(key, str):
            raise ValueError("source key must be a non-empty string, got %r"
                             % (key,))
        if trust_level not in TRUST_LEVELS:
            raise ValueError("unknown trust level %r for source %r; allowed: %s"
                             % (trust_level, key, sorted(TRUST_LEVELS)))
        if not enabled and not descope_reason:
            # A source that is off for no recorded reason is indistinguishable
            # from one that is off by accident.
            raise ValueError("source %r is disabled but records no "
                             "descope_reason" % (key,))
        self.key = key
        self.name = name
        self.base_url = base_url
        self.trust_level = trust_level
        self.enabled = enabled
        self.requires_contact_ua = requires_contact_ua
        self.requires_api_key = requires_api_key
        self.rate_limit_qps = rate_limit_qps
        self.licence = licence
        self.verified_on = verified_on
        self.verified_status = verified_status
        self.scale_note = scale_note
        self.descope_reason = descope_reason
        self.doc_url = doc_url
        object.__setattr__(self, "_frozen", True)

    def __setattr__(self, name, value):
        if getattr(self, "_frozen", False):
            raise ValueError(
                "source terms are immutable: refusing to set %r on source %r. "
                "Access terms a caller can edit at runtime are not terms. "
                "Construct a new Source if a term genuinely changed."
                % (name, self.key))
        object.__setattr__(self, name, value)

    def __delattr__(self, name):
        raise ValueError("source terms are immutable: refusing to delete %r "
                         "on source %r" % (name, self.key))

    def __repr__(self) -> str:
        return ("Source(%r, trust=%s, enabled=%s)"
                % (self.key, self.trust_level, self.enabled))

    @property
    def authority(self) -> int:
        # Explicit, because a KeyError escaping here would be a crash rather
        # than a refusal. Construction validates trust_level and the object is
        # frozen, so this cannot fire -- it guards against a future edit.
        try:
            return TRUST_LEVELS[self.trust_level]
        except KeyError:
            raise ValueError("source %r carries unknown trust level %r"
                             % (self.key, self.trust_level))

    def to_dict(self) -> Dict[str, Any]:
        return {k: getattr(self, k) for k in self._FIELDS}


_SOURCES: Dict[str, Source] = {}

# Read-only view. Handing out the mutable dict would reopen the hole that
# freezing Source just closed: SOURCES["codal"] = Source(..., enabled=True).
SOURCES: Mapping[str, Source] = MappingProxyType(_SOURCES)


def register_source(src: Source) -> Source:
    """
    Add a source. Refuses to overwrite an existing key.

    Silently replacing a registered source would change the terms attached to
    data already ingested under the old ones.
    """
    if not isinstance(src, Source):
        raise TypeError("register_source expects a Source, got %s"
                        % type(src).__name__)
    if src.key in _SOURCES:
        raise ValueError("source %r is already registered; refusing to "
                         "replace its terms" % (src.key,))
    _SOURCES[src.key] = src
    return src


_register = register_source  # internal alias used by the definitions below


_register(Source(
    key="sec_edgar_submissions",
    name="SEC EDGAR company submissions",
    base_url="https://data.sec.gov/submissions",
    trust_level="VERIFIED_PRIMARY",
    requires_contact_ua=True,
    rate_limit_qps=10,
    licence="US government work, public domain. Access conditional on a "
            "declared contact User-Agent and <=10 requests/second.",
    verified_on="2026-08-10",
    verified_status="MEASURED: HTTP 200 with contact UA; HTTP 403 without",
    doc_url="https://www.sec.gov/os/webmaster-faq",
))

_register(Source(
    key="sec_edgar_xbrl",
    name="SEC EDGAR XBRL company concept API",
    base_url="https://data.sec.gov/api/xbrl",
    trust_level="VERIFIED_PRIMARY",
    requires_contact_ua=True,
    rate_limit_qps=10,
    licence="US government work, public domain. Same UA and rate conditions.",
    verified_on="2026-08-10",
    verified_status="MEASURED: HTTP 200; one revenue tag returned 117 facts "
                    "across 4 period lengths, 46 periods multiply reported",
    scale_note="Returns RAW units (109417000000), unlike the filing text which "
               "says 'in millions' (109417). Facts from this path carry "
               "scale=1; facts parsed from filing tables do not.",
    doc_url="https://www.sec.gov/edgar/sec-api-documentation",
))

_register(Source(
    key="fred",
    name="FRED (Federal Reserve Bank of St. Louis)",
    base_url="https://api.stlouisfed.org/fred",
    trust_level="OFFICIAL_DATA",
    requires_api_key=True,
    licence="Free API key required. Most series are public domain, but SOME "
            "series are copyrighted by their original provider and may not be "
            "redistributed -- check per-series terms before caching. "
            "MANDATORY ATTRIBUTION, added 2026-08-30: the FRED API terms "
            "require the verbatim notice in REQUIRED_NOTICES['fred'] to be "
            "displayed. Recording the per-series caveat above while omitting "
            "this flat, unconditional obligation is how the gap arose: "
            "capturing PART of a licence is not complying with it.",
    verified_on="2026-08-10",
    verified_status="MEASURED: HTTP 400 'Variable api_key is not set' without "
                    "a key; key not yet supplied, so UNVERIFIED end to end",
    doc_url="https://fred.stlouisfed.org/docs/api/fred/",
))

_register(Source(
    key="codal",
    name="Codal (Iranian issuer disclosures)",
    base_url="https://codal.ir",
    trust_level="VERIFIED_PRIMARY",
    enabled=False,
    licence="UNKNOWN -- not verified.",
    verified_status="UNKNOWN: never probed",
    descope_reason="Iranian market data was descoped by the user in Phase 0 "
                   "(Q3). Terms and sanctions status unverified. Kept in the "
                   "registry disabled so the decision stays visible.",
))

_register(Source(
    key="tsetmc",
    name="Tehran Securities Exchange (TSETMC)",
    base_url="http://www.tsetmc.com",
    trust_level="EXCHANGE",
    enabled=False,
    licence="UNKNOWN -- not verified.",
    verified_status="UNKNOWN: never probed",
    descope_reason="Same Phase 0 Q3 descope as Codal.",
))

# TradingView is registered DISABLED for a different reason than Codal/TSETMC, and
# the distinction matters. Codal is descoped by user scope decision (Q3) and could
# be re-enabled by the user tomorrow. TradingView is disabled because its terms
# forbid the use -- no decision of ours can re-enable it.
#
# Note the trust level: UNVERIFIED. That is NOT a claim that TradingView's data is
# poor. It is deliberately meaningless here, because this is a LICENCE refusal, not
# a quality one, and the two must not be conflated. A source can be perfectly
# accurate and still legally unusable. If trust level were set high, a future
# maintainer would reasonably read "authority 80, disabled" as an oversight worth
# correcting. "UNVERIFIED, disabled, reason: prohibited" cannot be misread that way.
#
# Registering it at all (rather than omitting it) is the same argument as Codal:
# an absent source looks forgotten, a disabled one with a recorded reason looks
# decided. And it means ingest_document(source_key="tradingview") REFUSES rather
# than raising a confusing "unknown source" -- the error names the actual problem.
_register(Source(
    key="tradingview",
    name="TradingView (display-only; machine use prohibited)",
    base_url="https://www.tradingview.com",
    trust_level="UNVERIFIED",
    enabled=False,
    licence="Display-only. Terms of Use s3 licenses content for 'exclusive "
            "display-only use' and 'explicitly prohibits any form of "
            "non-display usage', naming automated trading, price referencing, "
            "order verification, algorithmic decision-making, smart order "
            "routing and risk management programs. Extends to third-party "
            "products that facilitate such use. No commercial usage without a "
            "separate agreement (this project has none).",
    verified_on="2026-08-12",
    verified_status="VERIFIED by live probe: HTTP 200, 12/12 relied-upon "
                    "prohibition clauses present; clause block sha256 "
                    "78d348b1...679a. Re-check with "
                    "tools/verify_tradingview_terms.py.",
    descope_reason="Machine use is PROHIBITED BY LICENCE, not by our choice. "
                   "See docs/legal/tradingview-terms-review.md. Ingestion, "
                   "fact extraction, price referencing and risk use are all "
                   "refused. A human may still read a TradingView chart or "
                   "alert on screen -- that is outside this registry, which "
                   "governs only what enters the machine.",
    doc_url="https://www.tradingview.com/policies/",
))


# ---------------------------------------------------------------------------
# PERMITTED_RESEARCH and PERMITTED_NEWS (R20)
# ---------------------------------------------------------------------------
# SS.5.2 requires "Permitted research" and "Permitted financial news". Before
# this block both tiers were EMPTY -- that gap was R20.
#
# THE SELECTION RULE, and it is not the obvious one:
# credibility is NOT a usable criterion. A source must satisfy BOTH
#   (i)  AUTHORITY   -- primary/official, not a summary of someone else, AND
#   (ii) PERMISSION  -- its terms permit MACHINE ingestion by a local,
#                       non-commercial research tool.
# Failing (ii) scores ZERO for ingestion regardless of reputation. That is why
# the most authoritative financial outlets on earth (Bloomberg, FT, Reuters)
# appear NOWHERE below: their licences forbid exactly this use. See
# docs/legal/research-and-news-sources.md for the verbatim clauses.
#
# Every entry below was verified on BOTH axes on 2026-08-30: the licence read
# verbatim from the publisher's own terms page, AND the endpoint probed with the
# STATUS CODE AND PARSED PAYLOAD BOTH CHECKED. That second condition is not
# pedantry: three probes this session returned HTTP 404 carrying 60-112 KB of
# HTML error page. A large response body is not evidence of success.

_register(Source(
    key="fed_board_working_papers",
    name="Federal Reserve Board working papers (FEDS/IFDP)",
    base_url="https://www.federalreserve.gov/feeds/working_papers.xml",
    trust_level="PERMITTED_RESEARCH",
    rate_limit_qps=1,
    licence="PUBLIC DOMAIN. federalreserve.gov/disclaimer.htm: 'information "
            "on Board's website is in the public domain and may be copied and "
            "distributed without permission'. Note the Board's own page "
            "reprints third-party notices (e.g. BEA) verbatim -- material "
            "sourced FROM a third party through a Board page keeps that "
            "party's terms.",
    verified_on="2026-08-30",
    verified_status="MEASURED: HTTP 200, payload parsed -- title 'FRB: "
                    "Working Papers', 15 items, newest 24 Aug 2026",
    doc_url="https://www.federalreserve.gov/disclaimer.htm",
))

_register(Source(
    key="ofr_working_papers",
    name="Office of Financial Research working papers",
    base_url="https://www.financialresearch.gov/working-papers/feed.rss",
    trust_level="PERMITTED_RESEARCH",
    rate_limit_qps=1,
    licence="NO COPYRIGHT CLAIMED. financialresearch.gov/legal-notices/: 'No "
            "copyright may be claimed for any work ... created by a federal "
            "employee in the course of his or her duties'.",
    verified_on="2026-08-30",
    verified_status="MEASURED: HTTP 200, payload parsed -- 10 items, newest "
                    "25 Aug 2026. NOTE the feed URL was FOUND, not guessed: "
                    "the natural guess /working-papers/feed/ returned 404.",
    doc_url="https://www.financialresearch.gov/legal-notices/",
))

# arXiv is the ONLY source in this registry whose terms of use name LOCAL
# STORAGE as permitted -- and only because this project is local, single-user
# and non-public. "Store and serve arXiv e-prints ... from your servers"
# remains prohibited, so IF THIS PROJECT IS EVER PUBLISHED the basis collapses
# and this entry must be re-reviewed. That condition is the whole licence.
_register(Source(
    key="arxiv_qfin",
    name="arXiv q-fin (Quantitative Finance)",
    base_url="https://export.arxiv.org/api/query",
    trust_level="PERMITTED_RESEARCH",
    # 0.333 qps, NOT a round number: info.arxiv.org/help/api/tou.html says
    # "no more than one request every three seconds, and limit requests to a
    # single connection". 1/3 s is the stated ceiling, so 1/3 qps is the rate.
    rate_limit_qps=0.333,
    licence="ToS EXPLICITLY PERMITS local use: 'Retrieve, store, and use the "
            "content of arXiv e-prints for your own personal use, or for "
            "research purposes'. Metadata is CC0 1.0. PROHIBITED: 'Store and "
            "serve arXiv e-prints ... from your servers' -- so this entry is "
            "valid ONLY while the project stays local, single-user and "
            "non-public. Rate condition is part of the licence, not advice.",
    verified_on="2026-08-30",
    verified_status="MEASURED: HTTP 200, payload parsed -- opensearch "
                    "totalResults 2260 for cat:q-fin.PR",
    doc_url="https://info.arxiv.org/help/api/tou.html",
))

# ECB: the licence SPLITS DOWN THE MIDDLE by content type. Data is free to use;
# Working Papers need written authorisation. A reviewer assuming
# "central bank => open" would have registered the papers illegally. This entry
# is the DATA PORTAL ONLY, and the licence field says so explicitly so that a
# later maintainer cannot widen it by accident.
_register(Source(
    key="ecb_data_portal",
    name="ECB Data Portal API (statistical data ONLY, not papers)",
    base_url="https://data-api.ecb.europa.eu/service/data",
    trust_level="OFFICIAL_DATA",
    rate_limit_qps=1,
    licence="Free use WITH CITATION: ecb.europa.eu disclaimer -- 'users of "
            "this website may make free use of the information ... the ECB "
            "must be cited as the source'. CARVE-OUT, and it is why this "
            "entry is data-only: reproduction of 'ECB Working Papers and ECB "
            "Occasional Papers ... is permitted only with the explicit prior "
            "written authorisation' -- which this project does NOT have. ECB "
            "research papers are therefore NOT covered by this source.",
    verified_on="2026-08-30",
    verified_status="MEASURED: HTTP 200, payload parsed -- EUR/USD 1.1643",
    doc_url="https://www.ecb.europa.eu/services/disclaimer/html/index.en.html",
))

# IMF: same split, stated even more sharply -- the general prohibition bans LLM
# use outright, and a "Notwithstanding" clause carves the statistical data back
# out. Reading only the first half would have excluded a permitted source;
# reading only the second half would have licensed a prohibited one.
_register(Source(
    key="imf_sdmx_data",
    name="IMF SDMX statistical data API (data ONLY, not publications)",
    base_url="https://api.imf.org/external/sdmx/2.1",
    trust_level="OFFICIAL_DATA",
    rate_limit_qps=1,
    licence="DATA CARVE-OUT ONLY. imf.org/en/About/copyright-and-terms (eff. "
            "2024-10-11) prohibits generally: 'does not permit use of its "
            "Content or Sites for the training of large language models "
            "(LLMs) without explicit permission' and 'prohibits the bulk "
            "download of information by automated technology'. BUT: "
            "'Notwithstanding the general prohibition ... published "
            "statistical data ... You may download, extract, copy, create "
            "derivative works, publish, distribute, and use Data'. This "
            "entry covers the DATA carve-out ONLY. IMF publications, working "
            "papers and text remain PROHIBITED for machine use.",
    verified_on="2026-08-30",
    verified_status="MEASURED: HTTP 200, payload parsed -- 445,712 bytes of "
                    "SDMX returned",
    doc_url="https://www.imf.org/en/About/copyright-and-terms",
))

_register(Source(
    key="world_bank_indicators",
    name="World Bank Indicators API",
    base_url="https://api.worldbank.org/v2",
    trust_level="OFFICIAL_DATA",
    rate_limit_qps=1,
    licence="Permitted for personal / non-commercial research use with "
            "attribution, per the World Bank dataset terms of use. This "
            "project is non-commercial and single-user.",
    verified_on="2026-08-30",
    verified_status="MEASURED: HTTP 200, payload parsed -- US GDP "
                    "30,769,700,000,000",
    doc_url="https://datacatalog.worldbank.org/public-licenses",
))

# -------- DISABLED: permitted by licence, but NOT REACHABLE from here --------
#
# GDELT has the MOST PERMISSIVE licence in the entire review and is still
# disabled. That combination is the finding: a favourable licence does not make
# an endpoint reachable, and the two must be recorded separately. Registering
# it enabled on the strength of its terms alone would have put a source into
# the corpus that returns nothing.
_register(Source(
    key="gdelt_doc",
    name="GDELT 2.0 DOC API (news metadata)",
    base_url="https://api.gdeltproject.org/api/v2/doc/doc",
    trust_level="PERMITTED_NEWS",
    enabled=False,
    rate_limit_qps=1,
    licence="ToS-VERIFIED AND EXCEPTIONALLY PERMISSIVE: "
            "gdeltproject.org/about.html#termsofuse -- 'available for "
            "unlimited and unrestricted use for any academic, commercial, or "
            "governmental use of any kind without fee'; 'may redistribute, "
            "rehost, republish, and mirror' with citation. CRITICAL LIMIT OF "
            "SCOPE: GDELT licenses ITS OWN datasets (events, entities, "
            "themes, tone, article URLs) -- NOT the publishers' article "
            "bodies. Following a URL into an article puts you under THAT "
            "publisher's terms, which for Bloomberg/FT/Reuters is a "
            "prohibition. Metadata only.",
    verified_on="2026-08-30",
    verified_status="ToS-VERIFIED / ENDPOINT-UNVERIFIED. MEASURED: HTTP 000 "
                    "x3, 'Connection timed out after 15002 milliseconds'. DNS "
                    "resolves (104.197.47.124). A SEC control request in the "
                    "SAME command returned 200 in 0.087 s, so the failure is "
                    "not general egress. Independent egress also timed out. "
                    "GDELT's own health is UNKNOWN FROM HERE -- not 'down'.",
    descope_reason="NOT a licence refusal -- the licence is the best in this "
                   "registry. Disabled because the endpoint is UNREACHABLE "
                   "from the build environment (HTTP 000 x3 with a passing "
                   "control). Re-enable ONLY after a probe returns 200 AND a "
                   "parsed payload. Recording it enabled on the strength of "
                   "its terms would claim a capability we measured absent.",
    doc_url="https://www.gdeltproject.org/about.html#termsofuse",
))

_register(Source(
    key="bis_working_papers",
    name="BIS working papers",
    base_url="https://www.bis.org",
    trust_level="PERMITTED_RESEARCH",
    enabled=False,
    rate_limit_qps=1,
    licence="PARTIALLY permitted and the limit is QUANTITATIVE, which is why "
            "this cannot be a normal ingestion source even once reachable. "
            "bis.org/terms_conditions.htm allows 'download, display, print "
            "out, photocopy or redistribute any BIS Material for "
            "non-commercial purposes', but a 'limited extract' means 'any "
            "extract of not more than 400 words of text or two tables or "
            "graphs ... and in any case not exceeding 10%'. A chunked RAG "
            "corpus of full papers would exceed that.",
    verified_on="2026-08-30",
    verified_status="ENDPOINT-UNVERIFIED. MEASURED: three candidate feed URLs "
                    "all returned HTTP 404 -- /doclist/wppubls.rss, "
                    "/list/wppubls/rss.xml, /list/wppubls/index.htm. Each 404 "
                    "carried a ~111,700-byte HTML error page: THE BODY SIZE "
                    "IS NOT EVIDENCE OF SUCCESS.",
    descope_reason="Two independent blockers. (1) No working feed URL found "
                   "(3x 404). (2) Even reachable, the 400-word / two-table / "
                   "10% extract cap conflicts with full-text chunking. "
                   "Re-enable only with a verified URL AND an extract-limit "
                   "enforcement mechanism.",
    doc_url="https://www.bis.org/terms_conditions.htm",
))

# NY Fed is deliberately NOT REGISTERED, and the omission is a decision.
# Its terms are the most generous of any research source reviewed --
# newyorkfed.org/privacy/termsofuse permits 'Access the Content, manually or
# through an automated process or device' and 'Download, store, and use Content
# in any format or media'. But its endpoint was NEVER PROBED this session.
# Registering it on the strength of the licence alone would repeat exactly the
# mistake the GDELT entry above exists to document. Probe first, then register.


# ---------------------------------------------------------------------------
# "AI web search" as a news/social route: REFUSED, and why (R45)
# ---------------------------------------------------------------------------
# The question asked was whether the web-search capability of AI services could
# replace APIs for reading news and social media. It cannot, and the reason is
# worth encoding rather than leaving in prose, because the idea is intuitive
# and a future maintainer will re-propose it.
#
# 1. A SEARCH TOOL CHANGES THE TRANSPORT, NOT THE LICENCE. Reaching Bloomberg
#    text through a search index does not create a right to it. Bloomberg's
#    terms ('may not be used to construct a database of any kind') and FT's
#    ('any manner for any machine learning and/or artificial intelligence
#    purposes') bind the USE, not the route. Brave's own FAQ states this
#    against its own product: 'The Brave Search API does not grant any rights
#    to third-party content such as webpages.'
# 2. THE SEARCH PROVIDERS THEMSELVES FORBID THE RAG STEP, in writing:
#    - Google Grounding: prohibits 'using Links to build an index'; forbids
#      'cache ... analyze, train on, or otherwise learn from Grounded Results';
#      and programmatic use via Gemini API is a PAID service.
#    - Brave Search API: 'shall not ... store, cache, or create a database of
#      Search Results, in whole or in part, other than transient storage'.
#    - Tavily: forbids use 'in connection with ... FINANCIAL INVESTMENT
#      DECISIONS', which is this project's domain, and trains on submitted
#      queries.
# 3. IT IS NOT EVEN AN ALTERNATIVE TO AN API. The deliverable is a local
#    llama.cpp model with no search tool of its own. Any search capability is
#    itself an HTTP API with a key and terms -- STRICTER terms than the
#    official data APIs it was proposed to replace.
#
# So no source is registered for it. What IS permitted is a HUMAN reading
# whatever they like on screen and choosing to paste an excerpt: that is the
# same boundary the TradingView entry draws ('A human may still read a
# TradingView chart ... that is outside this registry, which governs only what
# enters the machine'). Registering the refusal keeps
# ingest_document(source_key="ai_web_search") a NAMED refusal instead of a
# confusing "unknown source".
_register(Source(
    key="ai_web_search",
    name="AI web-search / grounding services (machine ingestion prohibited)",
    base_url="",
    # UNVERIFIED for the same reason as TradingView: this is a LICENCE refusal,
    # not a quality judgement, and a high trust level would read as an
    # oversight worth correcting.
    trust_level="UNVERIFIED",
    enabled=False,
    licence="PROHIBITED by every provider reviewed on 2026-08-30. Google "
            "Gemini grounding terms: 'You will not ... cache, frame, "
            "syndicate, resell, analyze, train on, or otherwise learn from "
            "Grounded Results', and it is 'a violation of these terms ... "
            "using Links to build an index, or using Links to identify "
            "destination pages for crawling or scraping'; grounding via the "
            "API is a PAID service. Brave Search API s3(b)(i): shall not "
            "'store, cache, or create a database of Search Results'. Tavily "
            "s6.4: shall not use output 'in connection with ... financial "
            "investment decisions'.",
    verified_on="2026-08-30",
    verified_status="VERIFIED by reading each provider's own terms; see "
                    "docs/legal/ai-web-search-review.md",
    descope_reason="A search tool changes the TRANSPORT, not the LICENCE: "
                   "reaching prohibited text through a search index does not "
                   "create a right to it, and every search provider "
                   "separately forbids storing results in a database. Also "
                   "not an alternative to an API -- a search capability IS an "
                   "API, with stricter terms and (for Google) a bill. A HUMAN "
                   "may read and quote anything on screen; that is outside "
                   "this registry, which governs only what enters the "
                   "machine.",
    doc_url="https://ai.google.dev/gemini-api/terms",
))


# ---------------------------------------------------------------------------
# Mandatory attribution notices
# ---------------------------------------------------------------------------
# Some licences do not merely permit use, they REQUIRE a specific sentence to
# be displayed. That obligation is unconditional and cannot be discharged by
# recording it in a `licence` field or quoting it in a legal document -- the
# program has to emit it.
#
# HOW THIS GAP WAS FOUND, because the shape of the mistake matters more than
# the fix: the `fred` entry above already recorded FRED's per-series copyright
# caveat accurately. Recording PART of a licence made the entry look reviewed,
# and the flat, unconditional attribution requirement went missing for weeks
# while `fred` sat ENABLED. MEASURED 2026-08-30:
#
#     $ grep -rln "not endorsed or certified" --include=*.py --include=*.json .
#     (no output -- 0 files)
#
# The text below is VERBATIM from fred.stlouisfed.org/docs/api/terms_of_use.html
# and must not be paraphrased: "FRED(R)" is a registered trademark and the
# sentence is prescribed wording, not a summary we are free to reword.
REQUIRED_NOTICES: Mapping[str, str] = MappingProxyType({
    "fred": "This product uses the FRED\u00ae API but is not endorsed or "
            "certified by the Federal Reserve Bank of St. Louis.",
})


def required_notices(keys=None) -> List[str]:
    """
    The attribution notices that must be displayed, deduplicated, in order.

    `keys` limits the result to the sources actually used (so a session that
    never touched FRED does not claim to use it). Passing None returns the
    notices for every ENABLED source that has one -- a disabled source imposes
    no obligation because nothing was ingested from it.

    Unknown keys are IGNORED rather than raising: this is called on a display
    path, and an attribution helper that crashes a report is worse than one
    that returns what it knows. Refusal belongs in check_access(), which runs
    first.
    """
    if keys is None:
        keys = [k for k, s in SOURCES.items() if s.enabled]
    out: List[str] = []
    for k in keys:
        notice = REQUIRED_NOTICES.get(k)
        # `not in out`: two FRED-backed series must not print the notice twice.
        if notice and notice not in out:
            out.append(notice)
    return out


class AccessError(RuntimeError):
    """Raised when a request would violate a source's stated terms."""


def get_source(key: str) -> Source:
    try:
        return SOURCES[key]
    except KeyError:
        raise ValueError(
            "unknown source %r. Ingesting from an unregistered source is "
            "refused: a document whose terms were never checked cannot be "
            "shown to be usable. Known: %s"
            % (key, ", ".join(sorted(SOURCES))))


def _is_contact_ua(user_agent: Optional[str]) -> bool:
    """
    Does this User-Agent actually name a contact address?

    The first version tested `"@" in user_agent`, which accepted "@", "me@"
    and "@example.com". A placeholder that satisfies the check but reaches SEC
    as an unusable contact is worse than no check: it converts a refusal I can
    read into a 403 I have to diagnose. So require a local part, an "@", and a
    dotted domain.
    """
    if not user_agent or not isinstance(user_agent, str):
        return False
    if "@" not in user_agent:
        return False
    local, _, rest = user_agent.rpartition("@")
    if not local.strip():
        return False
    rest = rest.strip()
    if not rest:
        return False
    # The domain runs to the next whitespace, then loses any bracketing.
    domain = rest.split()[0].strip("()<>,;\"'")
    if "." not in domain:
        return False
    return not domain.startswith(".") and not domain.endswith(".")


def check_access(key: str, user_agent: Optional[str] = None,
                 api_key: Optional[str] = None) -> Source:
    """
    Verify a fetch is permitted BEFORE making it.

    Refuses rather than warns. MEASURED: SEC returns 403 without a contact
    User-Agent, so a "warn and continue" policy would produce a confusing
    network error instead of naming the actual cause.
    """
    src = get_source(key)
    if not src.enabled:
        raise AccessError(
            "source %r is disabled: %s" % (key, src.descope_reason or
                                           "no reason recorded"))
    if src.requires_contact_ua and not _is_contact_ua(user_agent):
        raise AccessError(
            "source %r requires a User-Agent naming a reachable contact "
            "address, e.g. 'marfin-llm/0.1 (you@example.com)' (MEASURED: "
            "HTTP 403 without one). Got %r." % (key, user_agent))
    if src.requires_api_key and not (api_key or "").strip():
        # .strip(): a whitespace-only key passed the first version of this
        # guard and would have produced the MEASURED HTTP 400 anyway.
        raise AccessError(
            "source %r requires an API key (MEASURED: HTTP 400 'Variable "
            "api_key is not set' without one). Got %r." % (key, api_key))
    return src


def enabled_sources() -> List[Source]:
    return [s for s in SOURCES.values() if s.enabled]


def descoped_sources() -> List[Source]:
    return [s for s in SOURCES.values() if not s.enabled]


def manifest() -> Dict[str, Any]:
    """The registry as plain data, for the phase report and PROJECT_STATE."""
    return {"sources": [s.to_dict() for s in SOURCES.values()],
            "n_enabled": len(enabled_sources()),
            "n_descoped": len(descoped_sources())}
