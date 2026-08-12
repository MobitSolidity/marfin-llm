"""
TradingView posture: display-only, enforced in code (SS.7, Phase 3A).

WHY THIS MODULE IS MOSTLY REFUSALS
----------------------------------
Section 7 requires the TradingView terms to be verified at execution time and the
review recorded in the Source and License Registry. That review was done by live
probe on 2026-08-12 and is recorded in docs/legal/tradingview-terms-review.md.

The finding was not "unclear". TradingView's Terms of Use section 3 licenses its
content for "exclusive display-only use" and "explicitly prohibits any form of
non-display usage", naming: automated trading, automated order generation, price
referencing, order verification, algorithmic decision-making, algorithmic trading,
smart order routing, "using data in operations control or risk management
programs", and "any machine-driven processes that do not involve the direct,
human-readable display of such data". It names "charts, alerts, webhooks"
specifically, and extends the prohibition to third-party products that facilitate
such use -- which is exactly what this project would be.

So the honest interface to TradingView is not a client. It is a wall with a
labelled door: a human may look at a chart; no value may cross into computation.

WHY A WALL IN CODE AND NOT A NOTE IN A README
---------------------------------------------
Phase 3 established the lesson the hard way: sources.py DECLARED access terms and
nothing called check_access(), so the terms were decoration. A prose warning in a
report has the same defect. Here the prohibited-use list is data, and
assert_display_only_use() refuses by raising. A future contributor who wires a
TradingView quote into a risk check does not get a code review comment six months
later; they get a refusal the first time they run it.

WHAT THIS MODULE DELIBERATELY DOES NOT CONTAIN
----------------------------------------------
  - No HTTP client for TradingView. There is no client data API to call, and
    building one would be the prohibited "any processing" of their content.
  - No Desktop API. Probed 2026-08-12: the desktop page documents no local API
    (localhost x0, "local API" x0, plugin x0, automation x0). Section 7's
    acceptance criterion is "no unsupported Desktop API claimed"; the way to
    satisfy it is to claim none, on evidence.
  - No use of the "REST API for Brokers". VERIFIED from its own manual: it "lets
    brokers connect their backend systems to the TradingView interface" -- the
    broker implements endpoints TradingView calls. It is inbound to a broker. We
    are not a broker; it grants this project nothing.

Stdlib only.
"""

from types import MappingProxyType
from typing import Iterable, List, Mapping, Optional, Tuple

# ---------------------------------------------------------------------------
# The review, as data.
# ---------------------------------------------------------------------------

TERMS_URL = "https://www.tradingview.com/policies/"
TERMS_REVIEWED_ON = "2026-08-12"
TERMS_REVIEW_RECORD = "docs/legal/tradingview-terms-review.md"
TERMS_REVERIFY_TOOL = "tools/verify_tradingview_terms.py"

# sha256 of the extracted section 3 clause block (3,976 chars). NOT the page hash:
# four probes of the page on one day yielded three different page hashes while this
# block stayed byte-identical. See the review, caveat 1.
TERMS_CLAUSE_SHA256 = (
    "78d348b188a0ce180d44e1babe926c90126efff08951dc6d53ac756959d8679a")

#: Machine use is prohibited. This is a licence fact, not a data-quality opinion:
#: TradingView's numbers may be perfectly accurate and still legally unusable.
#: Keeping the two ideas separate matters, because a maintainer who "fixes" a
#: trust level must not thereby believe the block is lifted.
MACHINE_USE_PERMITTED = False

#: Verbatim, from the Terms of Use section 3. Each entry is a use the terms name
#: as prohibited. Kept as their words, not paraphrased, so a reader comparing this
#: list against the terms can see it is faithful.
PROHIBITED_USES: Tuple[str, ...] = (
    "automated trading",
    "automated order generation",
    "price referencing",
    "order verification",
    "algorithmic decision-making",
    "algorithmic trading",
    "smart order routing",
    "using data in operations control or risk management programs",
    "machine-driven processes that do not involve the direct, human-readable "
    "display of such data",
    "creating products or services based on TradingView content",
    "any processing of TradingView's content",
)

#: What a human may still do. Short by design.
PERMITTED_USES: Tuple[str, ...] = (
    "a human looking at a chart on screen",
    "a human reading an alert notification",
    "embedding an official TradingView widget in a page for a human to read",
    "rendering OUR OWN licensed data with the Lightweight Charts / Advanced "
    "Charts libraries (the library is a renderer; the data is ours)",
)


class TradingViewLicenceError(RuntimeError):
    """
    Raised when an operation would use TradingView content for machine purposes.

    A distinct type, because this is not a bug and not a bad input: it is a
    refusal on licence grounds. Calling code must not be able to catch it by
    accident alongside a parsing error, and a reader of a traceback should see
    immediately that nothing is broken -- something was correctly forbidden.
    """


def assert_display_only_use(purpose: str, detail: str = "") -> None:
    """
    Refuse any TradingView-derived value entering computation.

    There is no `permit` flag and no override argument. An override would be the
    first thing reached for under deadline, and the terms admit no exception this
    project can satisfy: "Except as otherwise expressly permitted by separate
    agreement, we do not permit commercial usage of any of our services or APIs."
    This project has no such agreement (recorded UNKNOWN -> assumed absent).

    Always raises. That is the contract.
    """
    if not isinstance(purpose, str) or not purpose.strip():
        # Refuse rather than raise the licence error with an empty reason: an
        # unlabelled refusal teaches the next reader nothing.
        raise ValueError("purpose must be a non-empty string describing the "
                         "intended use that is being refused")
    raise TradingViewLicenceError(
        "TradingView content may not be used for %r%s.\n"
        "  Terms (%s, reviewed %s) license it for 'exclusive display-only use' "
        "and 'explicitly prohibit any form of non-display usage', naming: %s.\n"
        "  Permitted instead: %s.\n"
        "  Required action: obtain this value from an independently authorized "
        "market-data provider (SS.5.5), and account state from the broker (SS.5.6).\n"
        "  Full review: %s"
        % (purpose,
           (" (%s)" % detail) if detail else "",
           TERMS_URL, TERMS_REVIEWED_ON,
           "; ".join(PROHIBITED_USES[:6]) + "; ...",
           "; ".join(PERMITTED_USES[:2]),
           TERMS_REVIEW_RECORD))


# ---------------------------------------------------------------------------
# Mechanism inventory -- what exists, and what it is good for.
# ---------------------------------------------------------------------------

class Mechanism(object):
    """
    A TradingView mechanism, with an honest verdict attached.

    Immutable for the reason established in sources.py: a capability record a
    caller can edit at runtime is not a record. One line
    (`MECHANISMS["webhook"].usable_for_machine_data = True`) would undo the whole
    module, so the attribute cannot be set at all.
    """

    _FIELDS = ("key", "name", "exists", "direction", "usable_for_machine_data",
               "note", "doc_url", "verified_on")
    __slots__ = _FIELDS + ("_frozen",)

    def __init__(self, key, name, exists, direction, usable_for_machine_data,
                 note, doc_url="", verified_on=TERMS_REVIEWED_ON):
        object.__setattr__(self, "_frozen", False)
        if not key or not isinstance(key, str):
            raise ValueError("mechanism key must be a non-empty string, got %r"
                             % (key,))
        if usable_for_machine_data:
            # There is no such mechanism, and if a future edit claims one, the
            # claim must be justified against the terms first. Refusing at
            # construction means the claim cannot be smuggled in as data.
            raise ValueError(
                "refusing to register mechanism %r as usable for machine data: "
                "TradingView's terms prohibit non-display usage of ALL its "
                "content (see %s). If the terms genuinely changed, update the "
                "legal review first and re-run %s."
                % (key, TERMS_REVIEW_RECORD, TERMS_REVERIFY_TOOL))
        if not note:
            raise ValueError("mechanism %r must record why it is unusable; an "
                             "unexplained 'no' is indistinguishable from an "
                             "oversight" % (key,))
        self.key = key
        self.name = name
        self.exists = exists
        self.direction = direction
        self.usable_for_machine_data = usable_for_machine_data
        self.note = note
        self.doc_url = doc_url
        self.verified_on = verified_on
        object.__setattr__(self, "_frozen", True)

    def __setattr__(self, name, value):
        if getattr(self, "_frozen", False):
            raise ValueError(
                "mechanism records are immutable: refusing to set %r on %r. "
                "A capability a caller can edit at runtime is not a capability "
                "record." % (name, self.key))
        object.__setattr__(self, name, value)

    def __delattr__(self, name):
        raise ValueError("mechanism records are immutable: refusing to delete "
                         "%r on %r" % (name, self.key))

    def __repr__(self):
        return ("Mechanism(%r, exists=%s, machine_usable=%s)"
                % (self.key, self.exists, self.usable_for_machine_data))

    def to_dict(self):
        return {k: getattr(self, k) for k in self._FIELDS}


_MECHANISMS = {}


def _add(mech: Mechanism) -> Mechanism:
    if not isinstance(mech, Mechanism):
        raise ValueError("expected a Mechanism, got %r" % (type(mech).__name__,))
    if mech.key in _MECHANISMS:
        raise ValueError("mechanism %r is already registered; refusing to "
                         "overwrite a verified record" % (mech.key,))
    _MECHANISMS[mech.key] = mech
    return mech


# All VERIFIED by live probe on 2026-08-12 (HTTP 200 each). See the review, s3.
_add(Mechanism(
    key="widgets",
    name="TradingView Widgets",
    exists=True,
    direction="browser-rendered embed",
    usable_for_machine_data=False,
    note="Renders in the user's browser and returns nothing to our process. "
         "Display-only by construction as well as by licence -- the one place "
         "where the terms and the mechanics agree.",
    doc_url="https://www.tradingview.com/widget-docs/"))

_add(Mechanism(
    key="charting_libraries",
    name="Advanced Charts / Lightweight Charts",
    exists=True,
    direction="client-side renderer; caller supplies the data",
    usable_for_machine_data=False,
    note="These are renderers, not data sources. Usable in this project ONLY to "
         "draw data we are separately licensed for. Drawing our own data with "
         "their library is not use of their content.",
    doc_url="https://www.tradingview.com/charting-library-docs/"))

_add(Mechanism(
    key="alerts",
    name="Alerts",
    exists=True,
    direction="outbound notification to a human",
    usable_for_machine_data=False,
    note="An alert is a human notification. Terms name 'alerts' in the "
         "display-only licence, so its content may not drive computation.",
    doc_url="https://www.tradingview.com/support/solutions/"
            "43000520149-introduction-to-tradingview-alerts/"))

_add(Mechanism(
    key="webhooks",
    name="Webhook alerts",
    exists=True,
    direction="outbound HTTP POST to a URL we control",
    usable_for_machine_data=False,
    note="MECHANICALLY POSSIBLE, CONTRACTUALLY PROHIBITED -- the most dangerous "
         "combination in this inventory, and the reason this module exists. "
         "Terms name webhooks three times, forbid third parties that 'claim "
         "compatibility with... webhooks' for prohibited purposes, and declare "
         "null any defence based on not using TradingView directly. A webhook "
         "may be received and shown to a human; it may never authorize a trade.",
    doc_url="https://www.tradingview.com/support/solutions/"
            "43000529348-how-to-configure-webhook-alerts/"))

_add(Mechanism(
    key="pine_script",
    name="Pine Script",
    exists=True,
    direction="executes inside TradingView; no egress",
    usable_for_machine_data=False,
    note="Runs on their platform. No path to a local CPU-only process, so the "
         "question of licence never even arises.",
    doc_url="https://www.tradingview.com/pine-script-docs/"))

_add(Mechanism(
    key="broker_rest_api",
    name="REST API for Brokers",
    exists=True,
    direction="INBOUND to the broker -- TradingView calls the broker's endpoints",
    usable_for_machine_data=False,
    note="Commonly misread as a client API. Its own manual: it 'lets brokers "
         "connect their backend systems to the TradingView interface, so that "
         "the broker partners can be supported on the TradingView Web "
         "Platform'. The broker implements endpoints; TradingView calls them. "
         "This project is not a broker, so it grants us nothing -- and would "
         "not supply us data even if we were.",
    doc_url="https://www.tradingview.com/broker-api-docs/"))

_add(Mechanism(
    key="desktop_app",
    name="Desktop Application",
    exists=True,
    direction="desktop chart client for a human",
    usable_for_machine_data=False,
    note="NO LOCAL API IS DOCUMENTED. Probed 2026-08-12: the desktop page "
         "mentions localhost x0, 127.0.0.1 x0, 'local API' x0, plugin x0, "
         "automation x0, 'command line' x0. Labelled COMPUTED-from-absence, not "
         "proven: marketing copy is not a specification. Either way section 3 "
         "would forbid using such an API. This project claims no Desktop API.",
    doc_url="https://www.tradingview.com/desktop/"))

#: Read-only view. A plain dict would let a caller inject a mechanism claiming
#: machine usability, bypassing the constructor guard entirely.
MECHANISMS: Mapping[str, Mechanism] = MappingProxyType(_MECHANISMS)


def get_mechanism(key: str) -> Mechanism:
    try:
        return MECHANISMS[key]
    except KeyError:
        raise ValueError(
            "unknown TradingView mechanism %r. Known: %s. An unrecognised "
            "mechanism is not assumed permitted -- it is unverified, and "
            "section 7 requires verification before use."
            % (key, ", ".join(sorted(MECHANISMS))))


def machine_usable_mechanisms() -> List[Mechanism]:
    """
    Returns [] -- and is here precisely so that fact is testable.

    A function that can only return an empty list looks pointless until the day
    someone adds a mechanism with the wrong flag. Then this is the assertion that
    catches it.
    """
    return [m for m in MECHANISMS.values() if m.usable_for_machine_data]


def review_summary() -> dict:
    """The posture as plain data, for the phase report and PROJECT_STATE."""
    return {
        "terms_url": TERMS_URL,
        "reviewed_on": TERMS_REVIEWED_ON,
        "review_record": TERMS_REVIEW_RECORD,
        "reverify_tool": TERMS_REVERIFY_TOOL,
        "clause_sha256": TERMS_CLAUSE_SHA256,
        "machine_use_permitted": MACHINE_USE_PERMITTED,
        "n_mechanisms": len(MECHANISMS),
        "n_machine_usable": len(machine_usable_mechanisms()),
        "prohibited_uses": list(PROHIBITED_USES),
        "permitted_uses": list(PERMITTED_USES),
        "mechanisms": [m.to_dict() for m in MECHANISMS.values()],
    }
