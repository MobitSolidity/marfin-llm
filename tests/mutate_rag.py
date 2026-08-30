"""
Mutation battery for the Phase 3 RAG layer.

Python, not bash: the selector battery was first written as a shell script and
quoting mangled 6 of 8 patterns into SKIPs that were indistinguishable from
real results. Never again.

Each mutation seeds ONE defect that a competent implementation must not have.
If test_rag.py still passes, the suite is not verifying that behaviour and the
mutation SURVIVES -- which is a finding about the tests, not the code.
"""

import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "src", "rag")
# Phase 3A added src/market/tradingview.py, which this battery must also mutate.
# A module name is written "market/tradingview.py" and resolved against src/, so
# the battery is not silently confined to one package. Getting this wrong would
# not fail loudly -- every market mutation would SKIP as "pattern absent", and a
# SKIP already proved once in this project that it can hide a real survivor.
SRC_ROOT = os.path.join(ROOT, "src")


def module_path(module):
    """Resolve a mutation's module name to a file under src/."""
    return os.path.join(SRC_ROOT, module) if "/" in module \
        else os.path.join(SRC, module)

# Mutations that CANNOT be killed because a second layer independently enforces
# the same rule. Listed explicitly, with the layer that catches them, so that
# "survived" never becomes a number someone learns to ignore. Anything not in
# this set that survives is a real gap in the tests.
EQUIVALENT = {
    "ingest.py: ingestion accepts documents with no provenance":
        "Passage.__init__ raises the same ValueError; the guard exists to fail "
        "before chunking and to state the SS.5.2 rule at the entry point",
    "rerank.py: abstention is reranked into a hit":
        "iterating an empty hits list already yields no rows; the early return "
        "states the abstention contract where a reader looks for it",
    "ingest.py: caller may claim any trust level for any source":
        "provenance_for already passes trust_level/licence from the registry, "
        "so a caller-supplied one hits Python's duplicate-keyword TypeError "
        "(MEASURED: 'got multiple values for keyword argument'). The explicit "
        "guard converts that into a message naming WHY it is refused",
}

# (module, description, find, replace)
MUTATIONS = [
    # --- normalization -----------------------------------------------------
    ("normalize.py", "ZWNJ no longer folds to a space",
     'ZWNJ: " ",            # zero-width non-joiner -> space',
     'ZWNJ: ZWNJ,'),
    ("normalize.py", "Persian compound variants dropped",
     "    return base + compound_variants(base)",
     "    return base"),
    ("normalize.py", "compound variants pollute base token count",
     "    base = tokenize(text)\n    return base + compound_variants(base)",
     "    base = tokenize(text) + compound_variants(tokenize(text))\n"
     "    return base + compound_variants(base)"),
    ("normalize.py", "Persian digits not folded",
     "    _FOLD[chr(0x06f0 + _i)] = str(_i)   # extended (persian)",
     "    pass"),

    # --- ingestion: the heading defect that deleted content ----------------
    ("ingest.py", "heading regex case-insensitive again (eats prose)",
     '_HEADING_CAPS_RE = re.compile(r"^\\s*[A-Z][A-Z0-9 ,\'&/()\\u2014-]{5,79}\\s*$")',
     '_HEADING_CAPS_RE = re.compile(r"^\\s*[A-Z][A-Z0-9 ,\'&/()\\u2014-]{5,79}\\s*$",\n'
     '                              re.IGNORECASE)'),
    ("ingest.py", "sibling headings nest again",
     "            while stack and stack[-1][0] >= lvl:\n                stack.pop()",
     "            while stack and stack[-1][0] > lvl + 90:\n                stack.pop()"),
    ("ingest.py", "tables are split like prose",
     '            pieces = [body]          # never split a table',
     '            pieces = _split_prose(body, max_chars)'),
    ("ingest.py", "units note not attached to passages",
     "                units_note=block.units_note,",
     "                units_note=None,"),
    ("ingest.py", "scale leaks across sibling sections",
     "            while scale_stack and scale_stack[-1][0] >= lvl:\n"
     "                scale_stack.pop()",
     "            pass"),
    ("ingest.py", "millions read as thousands",
     '    "million": 1e6, "millions": 1e6,',
     '    "million": 1e3, "millions": 1e3,'),
    ("ingest.py", "unresolved-scale flag never fires",
     "    return [p for p in passages\n"
     "            if contains_number(p.text) and not p.units_note]",
     "    return []"),
    ("ingest.py", "EDGAR facts given a millions scale",
     "                scale=1,                 # EDGAR XBRL is already in base units",
     "                scale=1e6,"),
    ("ingest.py", "XBRL period dates dropped (kills period_kind)",
     "                period_start=row.get(\"start\"),",
     "                period_start=None,"),
    ("ingest.py", "ingestion accepts documents with no provenance",
     '    if not isinstance(provenance, Provenance):',
     '    if False:'),

    # --- retrieval ---------------------------------------------------------
    ("retrieval.py", "empty result reports ok=True",
     "    @property\n    def ok(self) -> bool:\n        return bool(self.hits)",
     "    @property\n    def ok(self) -> bool:\n        return True"),
    ("retrieval.py", "as_of filter disabled (lookahead leak)",
     "                if eff is None or eff > cutoff:\n"
     "                    n_filtered += 1\n                    continue",
     "                pass"),
    ("retrieval.py", "entity filter disabled",
     '            if entity and (p.entity or "").lower() != entity.lower():\n'
     "                n_filtered += 1\n                continue",
     "            pass"),
    ("retrieval.py", "min_trust filter disabled",
     "            if min_trust and p.provenance.authority < min_trust:\n"
     "                n_filtered += 1\n                continue",
     "            pass"),
    ("retrieval.py", "BM25 becomes a constant (no ranking)",
     "                score += self._idf(t) * (f * (BM25_K1 + 1)) / denom",
     "                score += 1.0"),
    ("retrieval.py", "query uses raw text, index uses normalized",
     "        q_terms = index_terms(query)",
     "        q_terms = (query or '').split()"),
    ("retrieval.py", "index stores raw text, query normalized",
     "        terms = index_terms(passage.text)",
     "        terms = (passage.text or '').split()"),
    ("retrieval.py", "period_kind filter disabled on facts",
     "            if period_kind and f.period_kind != period_kind:\n"
     "                continue",
     "            pass"),
    ("retrieval.py", "facts returned oldest filing first",
     "        hits.sort(key=lambda f: (\n"
     "            -( f.provenance.effective_date or datetime.date.min).toordinal(),",
     "        hits.sort(key=lambda f: (\n"
     "            +( f.provenance.effective_date or datetime.date.min).toordinal(),"),
    ("retrieval.py", "index accepts bare strings",
     "        if not isinstance(passage, Passage):",
     "        if False:"),

    # --- reranking ---------------------------------------------------------
    ("rerank.py", "min-max normalization restored (inflates near-ties)",
     "    hi = max(scores)\n    if hi <= 1e-12:\n        return [1.0] * len(scores)\n"
     "    return [s / hi for s in scores]",
     "    lo, hi = min(scores), max(scores)\n"
     "    if hi - lo < 1e-12:\n        return [1.0] * len(scores)\n"
     "    return [(s - lo) / (hi - lo) for s in scores]"),
    ("rerank.py", "authority weight zeroed",
     "W_AUTHORITY = 0.30",
     "W_AUTHORITY = 0.0"),
    ("rerank.py", "authority weight dominates lexical relevance",
     "W_AUTHORITY = 0.30",
     "W_AUTHORITY = 30.0"),
    ("rerank.py", "recency weight zeroed",
     "W_RECENCY = 0.20",
     "W_RECENCY = 0.0"),
    ("rerank.py", "units bonus zeroed",
     "W_UNITS = 0.10",
     "W_UNITS = 0.0"),
    ("rerank.py", "future documents get a negative recency bonus",
     "    if age < 0:",
     "    if False:"),
    ("rerank.py", "abstention is reranked into a hit",
     "    if not result.ok:\n        return []",
     "    if False:\n        return []"),
    ("rerank.py", "rerank accepts a bare list",
     '    if not isinstance(result, RetrievalResult) or not hasattr(result, "ok"):',
     "    if False:"),
    ("rerank.py", "ordering is not total (nondeterministic)",
     "    rows.sort(key=lambda r: (-r[0], -r[2].provenance.authority,\n"
     "                             r[2].passage_id))",
     "    rows.sort(key=lambda r: -round(r[0], 3))"),

    # --- citations: the scale trap -----------------------------------------
    ("citations.py", "fixed 0.5% tolerance restored",
     "    digits = cn.raw.split(\".\")\n"
     "    decimals = len(digits[1]) if len(digits) > 1 else 0\n"
     "    half_ulp = 0.5 * (10.0 ** -decimals) * cn.scale\n"
     "    return max(half_ulp, abs(cn.magnitude) * rel_floor)",
     "    return abs(cn.magnitude) * 0.005"),
    ("citations.py", "tolerance ignores the claim's decimals",
     "    decimals = len(digits[1]) if len(digits) > 1 else 0",
     "    decimals = 0"),
    ("citations.py", "claim scale word ignored (10^6 error passes)",
     "        sm = _CLAIM_SCALE_RE.match(tail.lstrip())",
     "        sm = None"),
    ("citations.py", "passage units note ignored when scaling evidence",
     "            scale = SCALE_WORDS.get(evidence.units_note, 1.0)",
     "            scale = 1.0"),
    ("citations.py", "unscaled evidence silently assumed base units",
     "        if unscaled and not cn.scale_word:",
     "        if False:"),
    ("citations.py", "a claim with no numbers is treated as verified",
     '        return Citation(claim, evidence, "UNSUPPORTED",\n'
     '                        "claim asserts no numeric magnitude to verify")',
     '        return Citation(claim, evidence, "SUPPORTED", "nothing to check")'),
    ("citations.py", "evidence without provenance is citable",
     "    if prov is None:",
     "    if False:"),
    ("citations.py", "percentages treated as magnitudes",
     '        if tail.lstrip().startswith("%") or tail.lstrip().startswith(\n'
     '                "\\u066a"):\n            continue',
     "        pass"),
    ("citations.py", "one failed claim no longer invalidates the answer",
     '    return {"ok": not bad, "n_claims": len(results),',
     '    return {"ok": True, "n_claims": len(results),'),

    # --- conflicts ---------------------------------------------------------
    ("conflicts.py", "period mixing silently resolved instead of refused",
     "    if require_single_period and len(kinds) > 1:",
     "    if False:"),
    ("conflicts.py", "oldest filing chosen instead of newest",
     "    group.sort(key=lambda f: (\n        -f.provenance.authority,\n"
     "        -(f.provenance.effective_date or datetime.date.min).toordinal(),\n    ))",
     "    group.sort(key=lambda f: (\n        -f.provenance.authority,\n"
     "        +(f.provenance.effective_date or datetime.date.min).toordinal(),\n    ))"),
    ("conflicts.py", "superseded figures hidden from the caller",
     "    disagreeing = [f for f in group[1:] if _values_differ(chosen, f)]",
     "    disagreeing = []"),
    ("conflicts.py", "authority ignored when choosing a source",
     "        -f.provenance.authority,\n"
     "        -(f.provenance.effective_date or datetime.date.min).toordinal(),",
     "        -(f.provenance.effective_date or datetime.date.min).toordinal(),"),
    ("conflicts.py", "unbreakable tie silently resolved",
     "        if same_auth and same_date:",
     "        if False:"),
    ("conflicts.py", "different concepts collapsed into one answer",
     "    if len(groups) > 1:",
     "    if False:"),
    ("conflicts.py", "staleness measured from filing date, not period end",
     "    age = (ref - end).days",
     "    age = (ref - (fact.provenance.filed or end)).days"),
    ("conflicts.py", "missing period end assumed fresh",
     '        return {"age_days": None, "stale": True, "as_of": ref.isoformat(),',
     '        return {"age_days": None, "stale": False, "as_of": ref.isoformat(),'),
    ("conflicts.py", "staleness never flagged",
     "    return {\"age_days\": age, \"stale\": age > limit,",
     "    return {\"age_days\": age, \"stale\": False,"),
    ("conflicts.py", "empty fact set resolves instead of abstaining",
     "    if not facts:",
     "    if False:"),

    # --- the abstention gate ----------------------------------------------
    ("answer.py", "gate answers anyway when retrieval failed",
     "        if not retrieval.ok:",
     "        if False:"),
    ("answer.py", "gate ignores a failed claim verification",
     "        if not cit.ok:",
     "        if False:"),
    ("answer.py", "gate ignores the trust floor",
     "    if chosen.provenance.authority < min_trust:",
     "    if False:"),
    ("answer.py", "gate quotes stale evidence by default",
     "    if stale_warn and not allow_stale:",
     "    if False:"),
    ("answer.py", "gate answers through a CONFLICT",
     '    if res.status == "CONFLICT":',
     "    if False:"),
    ("answer.py", "gate answers through a REFUSED resolution",
     '    if res.status == "REFUSED":',
     "    if False:"),
    ("answer.py", "gate answers with no evidence at all",
     "        if not facts:",
     "        if False:"),
    ("answer.py", "trust floor lowered to accept news",
     "                min_trust: int = 80,",
     "                min_trust: int = 0,"),

    # -----------------------------------------------------------------------
    # sources.py -- access terms. Every one of these was a LIVE exploit on the
    # first execution of the module, before it had any tests at all.
    # -----------------------------------------------------------------------
    ("sources.py", "descoped source (Codal/TSETMC) is fetched anyway",
     "    if not src.enabled:",
     "    if False:"),
    ("sources.py", "contact User-Agent requirement dropped (MEASURED 403)",
     "    if src.requires_contact_ua and not _is_contact_ua(user_agent):",
     "    if False:"),
    ("sources.py", "API key requirement dropped (MEASURED 400)",
     '    if src.requires_api_key and not (api_key or "").strip():',
     "    if False:"),
    ("sources.py", "whitespace-only API key accepted",
     '    if src.requires_api_key and not (api_key or "").strip():',
     "    if src.requires_api_key and not api_key:"),
    ("sources.py", "UA check back to naive '@' substring test",
     '    if "@" not in user_agent:\n        return False\n    local, _, rest = user_agent.rpartition("@")',
     '    if "@" not in user_agent:\n        return False\n    return True\n    local, _, rest = user_agent.rpartition("@")'),
    ("sources.py", "UA accepted with an empty local part ('@example.com')",
     "    if not local.strip():\n        return False",
     "    if False:\n        return False"),
    ("sources.py", "UA accepted with a dotless domain ('me@localhost')",
     '    if "." not in domain:\n        return False',
     "    if False:\n        return False"),
    ("sources.py", "source terms become mutable again at runtime",
     '        if getattr(self, "_frozen", False):',
     "        if False:"),
    ("sources.py", "registry handed out as a mutable dict",
     "SOURCES: Mapping[str, Source] = MappingProxyType(_SOURCES)",
     "SOURCES: Mapping[str, Source] = _SOURCES"),
    ("sources.py", "re-registering a key silently replaces its terms",
     "    if src.key in _SOURCES:",
     "    if False:"),
    ("sources.py", "register_source accepts a non-Source object",
     "    if not isinstance(src, Source):",
     "    if False:"),
    ("sources.py", "unknown trust level accepted at construction",
     "        if trust_level not in TRUST_LEVELS:",
     "        if False:"),
    ("sources.py", "source disabled with no recorded reason accepted",
     "        if not enabled and not descope_reason:",
     "        if False:"),
    # Pattern includes the return line above it: `except KeyError:` appears
    # twice in the module (also in Source.authority), and an ambiguous pattern
    # SKIPS -- which silently hides whether the defect is detectable at all.
    ("sources.py", "unregistered source resolves instead of refusing",
     "        return SOURCES[key]\n    except KeyError:",
     "        return SOURCES.get(key)\n    except KeyError:"),

    # -----------------------------------------------------------------------
    # ingest.py -- the gating wiring. Declaring terms is not enforcing them.
    # -----------------------------------------------------------------------
    ("ingest.py", "document ingestion no longer checks access",
     "    src = check_access(source_key, user_agent=user_agent, api_key=api_key)\n    if provenance is None:",
     "    src = get_source(source_key)\n    if provenance is None:"),
    ("ingest.py", "XBRL ingestion no longer checks access",
     "    src = check_access(source_key, user_agent=user_agent, api_key=api_key)\n\n    concept =",
     "    src = get_source(source_key)\n\n    concept ="),
    ("ingest.py", "caller may claim any trust level for any source",
     '    for reserved in ("trust_level", "licence"):',
     "    for reserved in ():"),
    ("ingest.py", "passage may overstate its source's authority",
     "    elif provenance.trust_level != src.trust_level:",
     "    elif False:"),
    # Anchored on the surrounding XBRL call, since `trust_level=src.trust_level`
    # also appears in provenance_for.
    ("ingest.py", "trust level hardcoded again instead of read from registry",
     '                source_id="xbrl/companyconcept",\n                url=url,\n                trust_level=src.trust_level,',
     '                source_id="xbrl/companyconcept",\n                url=url,\n                trust_level="VERIFIED_PRIMARY",'),
    ("ingest.py", "XBRL licence text no longer read from the registry",
     "                accession=accn,\n                licence=src.licence,",
     '                accession=accn,\n                licence="public domain",'),

    # --- TradingView display-only wall (Phase 3A, SS.7) --------------------
    # These matter more than most. The whole phase rests on one legal finding,
    # and a wall nothing tests is a wall made of prose. Each mutation is a way a
    # future contributor could reopen machine use -- deliberately or by
    # "cleaning up" something that looked redundant.
    ("market/tradingview.py", "the licence verdict is flipped to permitted",
     "MACHINE_USE_PERMITTED = False",
     "MACHINE_USE_PERMITTED = True"),
    ("market/tradingview.py", "assert_display_only_use silently permits use",
     "    raise TradingViewLicenceError(",
     "    return None\n    raise TradingViewLicenceError("),
    ("market/tradingview.py", "the wall consults a mutable flag instead of "
                              "always refusing",
     '    if not isinstance(purpose, str) or not purpose.strip():',
     '    if MACHINE_USE_PERMITTED:\n        return None\n    if not isinstance(purpose, str) or not purpose.strip():'),
    ("market/tradingview.py", "an unlabelled refusal is accepted",
     "        raise ValueError(\"purpose must be a non-empty string describing the \"",
     "        purpose = \"unspecified\"\n        _ = (\"purpose must be a non-empty string describing the \""),
    ("market/tradingview.py", "mechanism records become mutable",
     "        if getattr(self, \"_frozen\", False):\n            raise ValueError(\n                \"mechanism records are immutable",
     "        if False:\n            raise ValueError(\n                \"mechanism records are immutable"),
    ("market/tradingview.py", "a mechanism may be deleted",
     "    def __delattr__(self, name):\n        raise ValueError(\"mechanism records are immutable: refusing to delete \"",
     "    def __delattr__(self, name):\n        object.__delattr__(self, name)\n        _ = (\"mechanism records are immutable: refusing to delete \""),
    ("market/tradingview.py", "a mechanism may claim machine usability",
     "        if usable_for_machine_data:",
     "        if False:"),
    ("market/tradingview.py", "a mechanism may be registered with no reason",
     "        if not note:",
     "        if False:"),
    ("market/tradingview.py", "MECHANISMS is a writable dict, not a proxy",
     "MECHANISMS: Mapping[str, Mechanism] = MappingProxyType(_MECHANISMS)",
     "MECHANISMS: Mapping[str, Mechanism] = _MECHANISMS"),
    ("market/tradingview.py", "a verified mechanism record may be overwritten",
     "    if mech.key in _MECHANISMS:",
     "    if False:"),
    ("market/tradingview.py", "_add accepts any object as a mechanism",
     "    if not isinstance(mech, Mechanism):",
     "    if False:"),
    ("market/tradingview.py", "an unknown mechanism is assumed permitted",
     "        raise ValueError(\n            \"unknown TradingView mechanism %r.",
     "        return None\n        raise ValueError(\n            \"unknown TradingView mechanism %r."),
    ("market/tradingview.py", "the prohibited-use list becomes editable",
     "PROHIBITED_USES: Tuple[str, ...] = (",
     "PROHIBITED_USES: Tuple[str, ...] = list_ = ["),
    # NOTE ON A NO-OP MUTATION I ALMOST SHIPPED. The first version of this used
    # `usable_for_machine_data=bool([])`, believing it looked like an obfuscated
    # True. bool([]) is False. The mutation changed nothing and "survived"
    # trivially -- the "factor equals 1" blind spot for the fifth time in this
    # project. A mutation whose replacement is semantically identical to the
    # original tests the battery's optimism, not the code. Verified by hand:
    # bool([1]) is True.
    ("market/tradingview.py", "the webhook mechanism is quietly marked usable",
     '    key="webhooks",\n    name="Webhook alerts",\n    exists=True,\n    direction="outbound HTTP POST to a URL we control",\n    usable_for_machine_data=False,',
     '    key="webhooks",\n    name="Webhook alerts",\n    exists=True,\n    direction="outbound HTTP POST to a URL we control",\n    usable_for_machine_data=bool([1]),'),
    ("market/tradingview.py", "the desktop app is claimed to expose a local API",
     '    note="NO LOCAL API IS DOCUMENTED.',
     '    note="Exposes a local automation API on localhost.'),
    ("market/tradingview.py", "the broker REST API is described as an inbound "
                              "feed we can consume",
     '    direction="INBOUND to the broker -- TradingView calls the broker\'s endpoints",',
     '    direction="outbound data feed we can poll",'),

    # --- the registry-level block on TradingView ---------------------------
    ("sources.py", "TradingView is re-enabled for machine ingestion",
     '    key="tradingview",\n    name="TradingView (display-only; machine use prohibited)",\n    base_url="https://www.tradingview.com",\n    trust_level="UNVERIFIED",\n    enabled=False,',
     '    key="tradingview",\n    name="TradingView (display-only; machine use prohibited)",\n    base_url="https://www.tradingview.com",\n    trust_level="UNVERIFIED",\n    enabled=True,'),
    ("sources.py", "TradingView is given borrowed authority",
     '    trust_level="UNVERIFIED",\n    enabled=False,\n    licence="Display-only.',
     '    trust_level="EXCHANGE",\n    enabled=False,\n    licence="Display-only.'),
    ("sources.py", "the TradingView refusal no longer names the licence",
     '    descope_reason="Machine use is PROHIBITED BY LICENCE, not by our choice. "',
     '    descope_reason="Not currently used. "'),

    # --- R20: the permitted-research / permitted-news tiers ----------------
    # These mutants attack the tiers that were EMPTY until 2026-08-30. An empty
    # tier produced NO test failure at all before this work -- which is exactly
    # why "the tier is populated" now has to be an assertion a mutant can kill.
    ("sources.py", "arXiv's ToS rate ceiling relaxed to a round 1 qps",
     '    rate_limit_qps=0.333,',
     '    rate_limit_qps=1,'),
    ("sources.py", "a permitted-research source is quietly disabled",
     '    key="fed_board_working_papers",',
     '    enabled=False,\n    descope_reason="x",\n    key="fed_board_working_papers",'),
    ("sources.py", "arXiv's local-storage licence basis is dropped",
     '    licence="ToS EXPLICITLY PERMITS local use:',
     '    licence="Assumed fine because it is a preprint server:'),
    ("sources.py", "an unprobed source is claimed as MEASURED",
     '    verified_status="MEASURED: HTTP 200, payload parsed -- opensearch "',
     '    verified_status="assumed reachable; not probed. "'),

    # --- TIER B: licence-permitted but unreachable --------------------------
    # The dangerous mutation is not "GDELT is disabled" but "GDELT is enabled
    # because its licence is excellent" -- conflating permission with
    # reachability. That is the mistake the entry exists to prevent.
    ("sources.py", "GDELT enabled on the strength of its licence alone",
     '    trust_level="PERMITTED_NEWS",\n    enabled=False,',
     '    trust_level="PERMITTED_NEWS",\n    enabled=True,'),
    ("sources.py", "GDELT's refusal is reworded as a licence prohibition",
     '    descope_reason="NOT a licence refusal -- the licence is the best in this "',
     '    descope_reason="Prohibited by licence. "'),
    ("sources.py", "the measured HTTP 000 is softened to 'service down'",
     '    verified_status="ToS-VERIFIED / ENDPOINT-UNVERIFIED. MEASURED: HTTP 000 "',
     '    verified_status="GDELT is down. "'),
    ("sources.py", "BIS re-enabled despite the 400-word extract cap",
     '    trust_level="PERMITTED_RESEARCH",\n    enabled=False,\n    rate_limit_qps=1,\n    licence="PARTIALLY permitted',
     '    trust_level="PERMITTED_RESEARCH",\n    enabled=True,\n    rate_limit_qps=1,\n    licence="PARTIALLY permitted'),
    ("sources.py", "the '404 body size proves nothing' lesson is deleted",
     '                    "IS NOT EVIDENCE OF SUCCESS.",',
     '                    "returned large HTML bodies.",'),

    # --- R45: the AI-web-search refusal ------------------------------------
    ("sources.py", "AI web search is registered as an ingestible news source",
     '    key="ai_web_search",\n    name="AI web-search / grounding services (machine ingestion prohibited)",\n    base_url="",',
     '    key="ai_web_search",\n    name="AI web search",\n    base_url="",\n    enabled=True,'),
    ("sources.py", "AI web search is given borrowed authority",
     '    trust_level="UNVERIFIED",\n    enabled=False,\n    licence="PROHIBITED by every provider',
     '    trust_level="PERMITTED_NEWS",\n    enabled=False,\n    licence="PROHIBITED by every provider'),
    ("sources.py", "the transport-is-not-licence reason is dropped",
     '    descope_reason="A search tool changes the TRANSPORT, not the LICENCE: "',
     '    descope_reason="Not currently wired up. "'),

    # --- the FRED attribution obligation -----------------------------------
    # This is the mutation class that matters most, because the ORIGINAL defect
    # was not a wrong notice -- it was a MISSING one, in a source that already
    # recorded part of its licence correctly and therefore looked reviewed.
    ("sources.py", "the mandatory FRED notice is deleted entirely",
     '    "fred": "This product uses the FRED\\u00ae API but is not endorsed or "\n            "certified by the Federal Reserve Bank of St. Louis.",',
     ''),
    ("sources.py", "the prescribed FRED wording is paraphrased",
     '    "fred": "This product uses the FRED\\u00ae API but is not endorsed or "\n            "certified by the Federal Reserve Bank of St. Louis.",',
     '    "fred": "Data from FRED, St. Louis Fed.",'),
    ("sources.py", "notices are silently duplicated per series",
     '        if notice and notice not in out:',
     '        if notice:'),
    ("sources.py", "attribution over-claims for sources never used",
     '    if keys is None:\n        keys = [k for k, s in SOURCES.items() if s.enabled]',
     '    keys = [k for k, s in SOURCES.items() if s.enabled]'),
    ("sources.py", "REQUIRED_NOTICES handed out as a mutable dict",
     'REQUIRED_NOTICES: Mapping[str, str] = MappingProxyType({',
     'REQUIRED_NOTICES: Mapping[str, str] = ({'),
]


def run_tests():
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run(
        [sys.executable, os.path.join(HERE, "test_rag.py")],
        cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return proc.returncode == 0, proc.stdout.decode("utf-8", "replace")


def main():
    # Clear stale bytecode: a cached .pyc can make a mutated module appear
    # unchanged and turn a real survivor into a false kill.
    for dirpath, dirnames, _ in os.walk(ROOT):
        for d in list(dirnames):
            if d == "__pycache__":
                shutil.rmtree(os.path.join(dirpath, d), ignore_errors=True)

    ok, out = run_tests()
    if not ok:
        print("ABORT: the suite fails BEFORE any mutation is applied.")
        print(out[-3000:])
        return 1
    print("baseline: suite passes, %d mutations to apply\n" % len(MUTATIONS))

    # Back up EVERY module any mutation touches, not just src/rag/. If a
    # market/*.py mutation were applied without a backup entry, the per-mutation
    # `finally` would still restore it, but a crash between write and restore
    # would leave a sabotaged file on disk -- and the next run's baseline check
    # would fail mysteriously rather than naming the cause.
    backup = tempfile.mkdtemp(prefix="rag_orig_")
    _backed_up = {}
    for name in os.listdir(SRC):
        if name.endswith(".py"):
            shutil.copy2(os.path.join(SRC, name), os.path.join(backup, name))
            _backed_up[name] = os.path.join(SRC, name)
    for module in sorted({m for (m, _, _, _) in MUTATIONS if "/" in m}):
        flat = module.replace("/", "__")
        shutil.copy2(module_path(module), os.path.join(backup, flat))
        _backed_up[flat] = module_path(module)

    killed = survived = skipped = equivalent = 0
    survivors, skips, unexpected_kills = [], [], []
    try:
        for i, (module, desc, find, repl) in enumerate(MUTATIONS, 1):
            path = module_path(module)
            with open(path, "r", encoding="utf-8") as fh:
                original = fh.read()
            if find not in original:
                skipped += 1
                skips.append("%s: %s" % (module, desc))
                print("  %2d. SKIP     %-58s (pattern absent)" % (i, desc[:58]))
                continue
            if original.count(find) > 1:
                skipped += 1
                skips.append("%s: %s (ambiguous)" % (module, desc))
                print("  %2d. SKIP     %-58s (ambiguous)" % (i, desc[:58]))
                continue
            try:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(original.replace(find, repl, 1))
                passed, _ = run_tests()
                key = "%s: %s" % (module, desc)
                if passed and key in EQUIVALENT:
                    equivalent += 1
                    print("  %2d. equiv    %-58s (%s)"
                          % (i, desc[:58], EQUIVALENT[key][:40]))
                elif passed:
                    survived += 1
                    survivors.append(key)
                    print("  %2d. SURVIVED %-58s <-- NOT TESTED" % (i, desc[:58]))
                else:
                    killed += 1
                    if key in EQUIVALENT:
                        unexpected_kills.append(key)
                    print("  %2d. killed   %s" % (i, desc[:58]))
            finally:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(original)
    finally:
        for name, dest in _backed_up.items():
            shutil.copy2(os.path.join(backup, name), dest)
        shutil.rmtree(backup, ignore_errors=True)

    intact, _ = run_tests()
    print("\n" + "=" * 78)
    print("  seeded:     %d" % len(MUTATIONS))
    print("  killed:     %d" % killed)
    print("  equivalent: %d (documented redundant guards)" % equivalent)
    print("  survived:   %d" % survived)
    print("  skipped:    %d" % skipped)
    print("  source restored and suite green: %s" % intact)
    for s in survivors:
        print("  SURVIVOR: %s" % s)
    for s in skips:
        print("  SKIPPED:  %s" % s)
    # An equivalent mutant that starts dying means the redundancy is gone --
    # the note is now false and must be re-checked rather than trusted.
    for s in unexpected_kills:
        print("  RECHECK:  %s was listed as equivalent but was KILLED" % s)
    print("=" * 78)
    return 0 if (survived == 0 and skipped == 0 and not unexpected_kills
                 and intact) else 1


if __name__ == "__main__":
    sys.exit(main())
