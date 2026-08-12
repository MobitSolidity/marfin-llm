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
            "redistributed -- check per-series terms before caching.",
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
