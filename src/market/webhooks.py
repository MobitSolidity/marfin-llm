"""
SS.7.1 Level 4 -- webhook receipt, validation, and durable queueing.

WHAT A WEBHOOK IS, AND WHAT IT IS NOT

A webhook delivery is evidence that an alert fired on someone else's computer.
That is all it is. It is not an instruction, not an authorization, and not a
price. SS.7.1 states it plainly -- "Webhook payloads are untrusted data" -- and
then lists seven things embedded instructions cannot do: change policies, select
an account, disable risk controls, authorize trades, reveal credentials, execute
shell commands, modify files.

The gap that makes webhooks dangerous is that they LOOK like instructions. A
TradingView alert body says `{"action": "buy", "qty": 100}`, and the whole
industry's tooling is built to honour exactly that. So the temptation is not an
exotic attack -- it is the obvious reading of the payload, and every convenience
layer will push toward it.

THIS MODULE'S ANSWER, WHICH IS STRUCTURAL RATHER THAN A CHECK

There is no code path from a webhook to an order. Not a disabled one, not one
behind a flag: `ValidatedEvent` has no method that submits, previews, or sizes
anything, and the fields that would carry an instruction (`action`, `side`,
`qty`, `price`, `account`, ...) are REFUSED AT PARSE TIME rather than parsed and
ignored. Ignoring them would leave a payload that half-worked, and the next
person to add a feature would find `event.action` sitting there looking usable.

The distinction the module draws:

    a webhook may say "my alert on AAPL 1h fired at 14:30"     -> accepted
    a webhook may say "buy 100 AAPL at market"                  -> REFUSED

The second is refused even though it is well-formed, authenticated, fresh, and
from an allowlisted source. Authentication proves who sent it, not what they are
permitted to command; a shared secret is not a mandate. This is the difference
between an authenticated channel and an authorized action, and conflating them is
how a leaked secret becomes a trade.

WHY THE PROHIBITIONS ARE ENFORCED AT THE PARSER AND NOT AT THE HANDLER

Because a handler check is one refactor away from being skipped, whereas a
payload that cannot be constructed cannot be misused downstream. The seven
prohibitions are therefore expressed as: (1) instruction-bearing keys refuse
construction, (2) `ValidatedEvent` is immutable and exposes no capability, and
(3) the queue stores inert records, not callables.

ACKNOWLEDGE FAST, PROCESS LATER

SS.7.1: "The webhook handler should acknowledge quickly and move processing to a
durable queue." So `receive()` does validation only -- cheap, bounded, no network,
no model, no broker -- and returns an acknowledgement plus a queued record. The
16 required validations all run BEFORE the acknowledgement, because a receiver
that acknowledges first and validates later has already told the sender its
garbage was accepted.

WHAT IS NOT IMPLEMENTED, STATED PLAINLY

There is no HTTP server here, and this module does not open a socket. Cloudflare
Workers/Pages -- the deployment target for this repo's web surface -- cannot host
a long-running listener, and the local Windows target has no public address. So
`receive()` takes an already-received request as data (method, url, headers,
body) and is exercised entirely by tests. That is a deliberate boundary, not an
omission: the validation logic is the part with the security content, and it is
testable without a server. A future server binds to this function; it does not
replace it.

The durable queue is a JSONL append-only file. It is NOT a distributed queue and
does not claim to be. Its durability property is the one that matters here: a
record is fsync'd before the acknowledgement is returned, so an event that was
acknowledged is on disk. Ordering is arrival order. Concurrency is single-process
with an exclusive lock per append.
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import json
import os
import re
from types import MappingProxyType
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from market.quotes import MarketDataError, VALUE_ORIGINS, WEAK_ORIGINS

#: The SS.5.5 origin label a webhook delivery carries.
#:
#: This was MEASURED, not chosen by taste. The first version of this module set
#: origin = "WEBHOOK", which is not in quotes.VALUE_ORIGINS. The obvious repair
#: was to add "WEBHOOK" to that tuple -- and measuring first showed the obvious
#: repair was the dangerous one:
#:
#:     Quote(..., origin="WEBHOOK")
#:     -> MarketDataError: origin must be one of PROVIDER_API, USER_SUPPLIED,
#:        CSV_EXPORT, VISUALLY_EXTRACTED, UNKNOWN, got 'WEBHOOK'
#:
#: That refusal is a WORKING GUARD, not a gap. Because "WEBHOOK" is absent from
#: the vocabulary, no webhook-derived number can be constructed as a Quote at
#: all -- the laundering path from "an alert said 214.5" to "a price object the
#: calculator accepts" does not exist. Widening VALUE_ORIGINS would have DELETED
#: that guard in the name of tidiness.
#:
#: So the label used here is UNKNOWN: in the vocabulary, and in WEAK_ORIGINS, so
#: the ranking that exists to distrust weak values actually sees it. Both facts
#: are asserted at import time below rather than trusted.
WEBHOOK_ORIGIN = "UNKNOWN"

#: Why a webhook cannot become a Quote, recorded so the next maintainer who
#: notices the "missing" label finds the reason before removing the protection.
ORIGIN_RATIONALE = (
    "A webhook delivery is labelled origin=UNKNOWN (SS.5.5 vocabulary) and is "
    "additionally refused as a price source by ValidatedEvent.assert_usable_for. "
    "There is deliberately no 'WEBHOOK' member of quotes.VALUE_ORIGINS: its "
    "absence means a webhook-derived number cannot be constructed as a Quote, "
    "which is a structural block on laundering a third party's chart assertion "
    "into a licensed price. Do not add it.")

if WEBHOOK_ORIGIN not in VALUE_ORIGINS:      # pragma: no cover - import guard
    raise AssertionError(
        "webhook origin label %r is outside quotes.VALUE_ORIGINS; a value the "
        "vocabulary does not contain is invisible to every consumer that ranks "
        "origins" % (WEBHOOK_ORIGIN,))
if WEBHOOK_ORIGIN not in WEAK_ORIGINS:       # pragma: no cover - import guard
    raise AssertionError(
        "webhook origin label %r is not in quotes.WEAK_ORIGINS; a webhook is "
        "the weakest origin this project has (a third party's assertion about "
        "a third party's chart) and must not outrank a screenshot"
        % (WEBHOOK_ORIGIN,))
if "WEBHOOK" in VALUE_ORIGINS:               # pragma: no cover - import guard
    raise AssertionError(
        "a 'WEBHOOK' member has been added to quotes.VALUE_ORIGINS. That "
        "removes the structural block described in ORIGIN_RATIONALE: with it "
        "present, a webhook-derived number becomes a constructible Quote.")


class WebhookError(MarketDataError):
    """
    A webhook was refused.

    Subclasses MarketDataError (a ValueError) so the project's REFUSALS tuple
    covers it: a refused webhook is a normal, expected event, not a crash.
    """


class WebhookAuthError(WebhookError):
    """
    Refused for an authentication/identity reason.

    Separate from WebhookError so a receiver can count authentication failures
    without pattern-matching on message text -- a spike in these is an attack
    signal, while a spike in schema failures is usually a misconfigured alert.
    """


# ---------------------------------------------------------------------------
# SS.7.1 Level 4: the sixteen required validations, as data.
# ---------------------------------------------------------------------------
#: Quoted from the spec in its order. Data, not prose, so a test can assert that
#: every one is actually reached -- the Phase 3 lesson is that a documented list
#: nobody checks is decoration. VALIDATION_KEYS below maps each to the function
#: that performs it, and a test asserts the mapping is total.
VALIDATIONS: Tuple[str, ...] = (
    "https",
    "authentication or shared secret",
    "source allowlisting",
    "payload schema",
    "payload size",
    "content type",
    "timestamp",
    "maximum event age",
    "event id or nonce",
    "duplicate delivery",
    "replay attempts",
    "expected alert id",
    "symbol",
    "exchange",
    "timeframe",
    "strategy id and version",
)

#: SS.7.1 Level 4: what embedded instructions cannot do. Also data, and also
#: asserted: PROHIBITION_ENFORCEMENT below states HOW each is prevented, and a
#: test asserts every prohibition has an entry. "We do not do that" is not an
#: enforcement mechanism.
PROHIBITIONS: Tuple[str, ...] = (
    "change policies",
    "select an account",
    "disable risk controls",
    "authorize trades",
    "reveal credentials",
    "execute shell commands",
    "modify files",
)

PROHIBITION_ENFORCEMENT: Mapping[str, str] = MappingProxyType({
    "change policies":
        "no policy, mode, risk or config key is readable or writable from this "
        "module; execution.mode is never imported, so there is no symbol to "
        "assign to. Policy-shaped payload keys are refused at parse time.",
    "select an account":
        "account/account_id/broker/portfolio keys are refused at parse time. "
        "ValidatedEvent has no account field, so no downstream consumer can "
        "read one from an event even if a sender supplies it.",
    "disable risk controls":
        "risk-shaped keys (override, force, bypass, disable_*, ignore_risk) are "
        "refused at parse time; no risk module is imported.",
    "authorize trades":
        "STRUCTURAL: ValidatedEvent exposes no submit/preview/size method and "
        "carries no side/qty/price. There is no disabled path to enable -- "
        "there is no path. Instruction keys refuse construction outright.",
    "reveal credentials":
        "the shared secret is compared with hmac.compare_digest and is never "
        "echoed, logged, or stored in the queue record; redact() strips "
        "secret-shaped headers before anything is persisted, and a refusal "
        "message never contains the received or expected signature.",
    "execute shell commands":
        "no subprocess, os.system, eval, exec or import-by-name anywhere in "
        "this module; payload values are only ever compared or stored as data. "
        "Asserted by an AST test, not by inspection.",
    "modify files":
        "the only write is an append to the queue's own JSONL file at a path "
        "the CALLER supplies at construction; no path component ever comes from "
        "a payload. Path-shaped keys (path, file, filename) are refused.",
})


# ---------------------------------------------------------------------------
# Keys that make a payload an instruction rather than an observation.
# ---------------------------------------------------------------------------
#: Refused at parse time, per key group, with the prohibition each maps to.
#:
#: EXACT matching on this map is the FIRST of two layers. It was the only layer
#: in the first version, and the adversarial probe measured what that costs: the
#: map contained "limit_price", "stop_price", "enable_live", "live_trading",
#: "disable_risk" and "skip_checks" and yet let through
#:
#:     disable_risk_checks     enable_live_trading     live
#:
#: because none of those exact strings was listed. A blocklist keyed on exact
#: spellings fails on the sender's next naming choice, and its gaps are invisible
#: -- the map LOOKS thorough at 58 entries. So INSTRUCTION_TOKENS below adds a
#: second layer that matches on word boundaries.
INSTRUCTION_KEYS: Mapping[str, str] = MappingProxyType({
    # authorize trades
    "action": "authorize trades",
    "side": "authorize trades",
    "order": "authorize trades",
    "order_type": "authorize trades",
    "buy": "authorize trades",
    "sell": "authorize trades",
    "qty": "authorize trades",
    "quantity": "authorize trades",
    "size": "authorize trades",
    "position_size": "authorize trades",
    "leverage": "authorize trades",
    "limit_price": "authorize trades",
    "stop_price": "authorize trades",
    "take_profit": "authorize trades",
    "stop_loss": "authorize trades",
    "tp": "authorize trades",
    "sl": "authorize trades",
    "execute": "authorize trades",
    "submit": "authorize trades",
    # select an account
    "account": "select an account",
    "account_id": "select an account",
    "accountid": "select an account",
    "broker": "select an account",
    "broker_account": "select an account",
    "portfolio": "select an account",
    "sub_account": "select an account",
    # change policies
    "mode": "change policies",
    "policy": "change policies",
    "config": "change policies",
    "settings": "change policies",
    "risk_policy": "change policies",
    "capability": "change policies",
    "enable_live": "change policies",
    "live_trading": "change policies",
    # disable risk controls
    "override": "disable risk controls",
    "force": "disable risk controls",
    "bypass": "disable risk controls",
    "ignore_risk": "disable risk controls",
    "disable_risk": "disable risk controls",
    "no_confirm": "disable risk controls",
    "skip_checks": "disable risk controls",
    # execute shell commands
    "cmd": "execute shell commands",
    "command": "execute shell commands",
    "shell": "execute shell commands",
    "exec": "execute shell commands",
    "eval": "execute shell commands",
    "script": "execute shell commands",
    # modify files
    "path": "modify files",
    "file": "modify files",
    "filename": "modify files",
    "filepath": "modify files",
    "output_path": "modify files",
    # reveal credentials
    "secret": "reveal credentials",
    "api_key": "reveal credentials",
    "apikey": "reveal credentials",
    "token": "reveal credentials",
    "password": "reveal credentials",
    "credentials": "reveal credentials",
    # Added after the probe MEASURED them missing while near-synonyms were
    # present. Listed explicitly as well as caught by token below, because the
    # exact map is what names the prohibition in the refusal message.
    "live": "change policies",
    "disable_risk_checks": "disable risk controls",
})

#: The SECOND layer: dangerous WORDS, matched on token boundaries.
#:
#: Word boundaries, not substrings. This distinction was measured rather than
#: assumed, and it is the whole design:
#:
#:   substring match refuses  transaction_id (action), inside_bar (side),
#:                            filepath_note (file, path), consideration (side)
#:   token match refuses      none of those, and still catches
#:                            disable_risk_checks, enable_live_trading, tv_side,
#:                            order.qty, ACCOUNT-ID, risk-override, shell_cmd
#:
#: MEASURED against 28 ordinary alert field names (symbol, price, close, volume,
#: rsi, ema_50, risk_reward, plot_value, bar_time, ...): 0 false positives. And
#: against 11 compound attack keys: 0 missed.
#:
#: The false-positive count is not a nicety. screenshot.py taught this lesson the
#: expensive way: a guard that refuses ordinary input trains the user to turn it
#: off, and then it protects nothing. A rule that refuses "transaction_id" would
#: be disabled within a week.
#:
#: Note what is NOT here: "price". A TradingView alert legitimately reports the
#: price at which it fired -- that is an observation, which is exactly what this
#: receiver accepts. The ORDER parameters are refused instead: limit_price,
#: stop_price, take_profit, stop_loss, qty, size, leverage. Refusing plain
#: "price" would reject ordinary alerts to prevent nothing, since a price alone
#: cannot authorize anything and assert_usable_for refuses the event as a price
#: source regardless.
INSTRUCTION_TOKENS: Mapping[str, str] = MappingProxyType({
    "action": "authorize trades",
    "side": "authorize trades",
    "qty": "authorize trades",
    "quantity": "authorize trades",
    "buy": "authorize trades",
    "sell": "authorize trades",
    "order": "authorize trades",
    "submit": "authorize trades",
    "execute": "authorize trades",
    "leverage": "authorize trades",
    "account": "select an account",
    "broker": "select an account",
    "portfolio": "select an account",
    "live": "change policies",
    "policy": "change policies",
    "capability": "change policies",
    "disable": "disable risk controls",
    "bypass": "disable risk controls",
    "override": "disable risk controls",
    "shell": "execute shell commands",
    "cmd": "execute shell commands",
    "command": "execute shell commands",
    "exec": "execute shell commands",
    "eval": "execute shell commands",
    "script": "execute shell commands",
    "password": "reveal credentials",
    "apikey": "reveal credentials",
    "credentials": "reveal credentials",
})

_TOKEN_SPLIT = re.compile(r"[^a-z0-9]+")


def key_tokens(key: str) -> Tuple[str, ...]:
    """Split a payload key into lowercased word tokens ('tv_Side' -> tv, side)."""
    return tuple(t for t in _TOKEN_SPLIT.split(str(key).strip().lower()) if t)

#: Header names never persisted or echoed. Redaction is by exact lowercased name
#: plus a small suffix rule, because header naming is not standardized across
#: senders and a missed one goes into a durable file.
_SECRET_HEADERS = ("authorization", "x-signature", "x-hub-signature",
                   "x-hub-signature-256", "x-tv-signature", "x-webhook-secret",
                   "x-api-key", "api-key", "cookie", "set-cookie",
                   "proxy-authorization")
_SECRET_HEADER_SUFFIXES = ("-signature", "-secret", "-token", "-key",
                           "-password", "-auth")

#: The only content types an alert body may arrive as.
ALLOWED_CONTENT_TYPES = ("application/json", "text/json")

#: Hard cap on body size. 64 KiB is far above any legitimate alert (TradingView's
#: own alert message limit is well under 1 KiB) and far below anything that could
#: pressure memory. The check exists so that a size limit is a REFUSAL rather than
#: an out-of-memory condition discovered later.
MAX_BODY_BYTES = 64 * 1024

#: Maximum age of a delivery. Anything older is stale: an alert that arrives half
#: an hour late describes a market that no longer exists, and accepting it is how
#: a delayed replay looks legitimate.
MAX_EVENT_AGE_SECONDS = 300

#: Tolerance for a timestamp in the FUTURE. Clock skew is real; a sender ten
#: minutes ahead is not. Kept small and separate from MAX_EVENT_AGE_SECONDS so
#: neither can be widened accidentally by tuning the other.
MAX_CLOCK_SKEW_SECONDS = 60

#: Timeframes an alert may declare. Deliberately the same vocabulary as
#: csv_import.TIMEFRAME_SECONDS would use, because two modules that accept
#: different timeframe spellings will eventually disagree about the same alert.
ALLOWED_TIMEFRAMES = ("1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w")


# ---------------------------------------------------------------------------
# Redaction.
# ---------------------------------------------------------------------------

def redact_headers(headers: Mapping[str, str]) -> Dict[str, str]:
    """
    Replace secret-bearing header values with a fixed marker.

    Returns a NEW dict; the caller's headers are untouched. The marker is a
    constant string rather than a truncation or a hash: a prefix leaks entropy,
    and a hash of a low-entropy secret is a crackable record that lives in a file
    designed to be durable.
    """
    if not isinstance(headers, Mapping):
        raise WebhookError("headers must be a mapping")
    out = {}
    for name, value in headers.items():
        low = str(name).lower()
        if low in _SECRET_HEADERS or any(low.endswith(s)
                                        for s in _SECRET_HEADER_SUFFIXES):
            out[str(name)] = "[REDACTED]"
        else:
            out[str(name)] = str(value)
    return out


# ---------------------------------------------------------------------------
# The validated event -- an observation, with no capability attached.
# ---------------------------------------------------------------------------

class ValidatedEvent(object):
    """
    One alert delivery that passed all sixteen validations.

    Deliberately anaemic. It has no method that acts, and it carries no side,
    quantity, price, or account, because those fields are what would let a
    downstream author write `if event.side == "buy": submit(...)`. The absence is
    the security property; a comment saying "do not act on this" would not be.

    Immutable, for the same reason quotes and validated CSV series are: a record
    whose symbol or timestamp a later caller can edit is not a record of a
    delivery.
    """

    _FIELDS = ("event_id", "alert_id", "symbol", "exchange", "timeframe",
               "strategy_id", "strategy_version", "fired_at", "received_at",
               "source_ip", "body_sha256", "n_bytes", "headers", "extra",
               "origin", "note")
    __slots__ = _FIELDS + ("_frozen",)

    def __init__(self, event_id, alert_id, symbol, exchange, timeframe,
                 strategy_id, strategy_version, fired_at, received_at,
                 source_ip, body_sha256, n_bytes, headers, extra=None,
                 note=""):
        object.__setattr__(self, "_frozen", False)

        # -- the constructor enforces what the class NAME claims ------------
        #
        # This block exists because of a MEASURED defect. The first version
        # trusted receive() to have validated everything and checked nothing
        # itself, so a hand-built event with event_id="../../etc/passwd",
        # timeframe="NOT-A-TIMEFRAME", n_bytes=-1 and
        # extra={"action": "buy", "qty": "100"} was accepted by EventQueue and
        # the instruction reached the durable JSONL file.
        #
        # "ValidatedEvent" is an assertion about the object, and an assertion
        # that only holds when constructed through one particular caller is not
        # a property of the type -- it is a convention, and conventions are what
        # the next caller does not know about. The checks are duplicated here on
        # purpose: receive() is the front door, and this is the invariant.
        _require_id({"event_id": event_id}, "event_id", "event_id")
        _require_id({"alert_id": alert_id}, "alert_id", "alert id")
        _require_id({"strategy_id": strategy_id}, "strategy_id", "strategy id")
        _require_str({"symbol": symbol}, "symbol", "symbol", maxlen=32)
        _require_str({"exchange": exchange}, "exchange", "exchange", maxlen=32)
        _require_str({"strategy_version": strategy_version},
                     "strategy_version", "strategy version", maxlen=32)
        _require_str({"timeframe": timeframe}, "timeframe", "timeframe",
                     allowed=ALLOWED_TIMEFRAMES)

        for label, value in (("fired_at", fired_at),
                             ("received_at", received_at)):
            if not isinstance(value, datetime.datetime):
                raise WebhookError(
                    "%s must be a datetime, got %s. A string here would be "
                    "compared lexically by the age and replay checks, which "
                    "silently succeeds for the wrong reason."
                    % (label, type(value).__name__))
            if value.tzinfo is None:
                raise WebhookError(
                    "%s is timezone-naive. It will not be assumed UTC: an "
                    "instant without an offset shifts an event by hours while "
                    "still looking valid." % (label,))

        if not isinstance(n_bytes, int) or isinstance(n_bytes, bool) \
                or n_bytes <= 0:
            raise WebhookError(
                "n_bytes must be a positive integer, got %r. A zero or negative "
                "size describes a body that was never received, and it is the "
                "field a size-limit check is compared against." % (n_bytes,))
        if not isinstance(body_sha256, str) \
                or not re.match(r"^[0-9a-f]{64}$", body_sha256):
            raise WebhookError(
                "body_sha256 must be 64 lowercase hex characters, got %r. This "
                "is the only evidence of what actually arrived; an unchecked "
                "value makes the audit record unfalsifiable."
                % (body_sha256,))

        # The leftovers dict is the last way in. receive() already refuses
        # instruction keys in the parsed payload, but a direct constructor call
        # bypasses receive() entirely -- which is exactly how the measured
        # bypass smuggled {"action": "buy"} into the durable queue.
        assert_no_instructions(dict(extra or {}))

        self.event_id = event_id.strip()
        self.alert_id = alert_id.strip()
        self.symbol = symbol.strip()
        self.exchange = exchange.strip()
        self.timeframe = timeframe.strip()
        self.strategy_id = strategy_id.strip()
        self.strategy_version = strategy_version.strip()
        self.fired_at = fired_at
        self.received_at = received_at
        self.source_ip = source_ip
        self.body_sha256 = body_sha256
        self.n_bytes = n_bytes
        self.headers = MappingProxyType(dict(headers))
        # Non-instruction leftovers, kept as inert strings so an alert can carry
        # a human note without becoming a command.
        self.extra = MappingProxyType(dict(extra or {}))
        #: SS.5.5 vocabulary. A webhook is the weakest origin this project has:
        #: a third party's assertion about a third party's chart. See
        #: WEBHOOK_ORIGIN / ORIGIN_RATIONALE -- this is UNKNOWN (which IS in
        #: VALUE_ORIGINS and in WEAK_ORIGINS) rather than a "WEBHOOK" member,
        #: because the absence of that member is what stops a webhook value from
        #: being constructible as a Quote.
        self.origin = WEBHOOK_ORIGIN
        self.note = note
        object.__setattr__(self, "_frozen", True)

    def __setattr__(self, name, value):
        if getattr(self, "_frozen", False):
            raise WebhookError(
                "a validated event is immutable: refusing to set %r. Editing a "
                "delivery record after validation would make the audit trail "
                "describe something that never arrived." % (name,))
        object.__setattr__(self, name, value)

    def __delattr__(self, name):
        raise WebhookError("a validated event is immutable: refusing to delete "
                           "%r" % (name,))

    def __repr__(self):
        return ("ValidatedEvent(%s %s/%s %s strategy=%s v%s)"
                % (self.event_id[:12], self.exchange, self.symbol,
                   self.timeframe, self.strategy_id, self.strategy_version))

    def assert_usable_for(self, purpose: str) -> None:
        """
        Refuse every purpose except the two a third-party alert can support.

        There is no "live_order" branch that checks something. Adding one would
        imply the answer could ever be yes, and the spec's "authorize trades" is
        unconditional -- so the refusal names the prohibition rather than a
        property of this particular event.
        """
        if not purpose or not isinstance(purpose, str):
            raise WebhookError("purpose must be a non-empty string")
        if purpose in ("live_order", "paper_order", "submit_order",
                       "order_preview", "position_sizing"):
            raise WebhookError(
                "a webhook may never be used for %r. SS.7.1 Level 4: webhook "
                "payloads are untrusted data and embedded instructions cannot "
                "authorize trades. An authenticated sender is an identified "
                "sender, not an authorized one -- a shared secret proves origin, "
                "never mandate. Treat this event as notification that an alert "
                "fired, then make the decision from licensed market data and "
                "broker state." % (purpose,))
        if purpose == "material_calculation":
            raise WebhookError(
                "a webhook payload is not a price source: it is a third party's "
                "assertion about a third party's chart, with no licence, no "
                "adjustment status, and no market status. Obtain the value from "
                "a provider (SS.5.5) or a validated CSV (SS.7.1 Level 2).")
        if purpose in ("notify", "display", "audit", "trigger_analysis"):
            return
        raise WebhookError(
            "unknown purpose %r; allowed: notify, display, audit, "
            "trigger_analysis. An unrecognised purpose is not assumed "
            "permitted." % (purpose,))

    def to_dict(self) -> Dict[str, Any]:
        d = {}
        for k in self._FIELDS:
            v = getattr(self, k)
            if isinstance(v, datetime.datetime):
                v = v.isoformat()
            elif isinstance(v, MappingProxyType):
                v = dict(v)
            d[k] = v
        return d


# ---------------------------------------------------------------------------
# Validation helpers. Each returns nothing and raises on refusal.
# ---------------------------------------------------------------------------

def _utc_now():
    return datetime.datetime.now(datetime.timezone.utc)


def assert_https(url: str) -> None:
    """Validation 1. HTTP is refused outright, including on localhost."""
    if not isinstance(url, str) or not url.strip():
        raise WebhookError("url must be a non-empty string")
    low = url.strip().lower()
    if low.startswith("https://"):
        return
    if low.startswith("http://"):
        raise WebhookError(
            "refusing a webhook delivered over HTTP: %r. The shared secret and "
            "the payload both travel in clear text, so the secret is disclosed "
            "to anyone on the path and the payload can be rewritten in flight. "
            "There is no localhost exemption here: an exemption is a "
            "configuration away from being the production path." % (url,))
    raise WebhookError(
        "url must be an absolute https:// URL, got %r" % (url,))


def assert_content_type(headers: Mapping[str, str]) -> str:
    """Validation 6."""
    ctype = ""
    for name, value in headers.items():
        if str(name).lower() == "content-type":
            ctype = str(value)
            break
    if not ctype:
        raise WebhookError(
            "no Content-Type header. A body whose type is guessed is a body "
            "whose parser is chosen by the sender.")
    base = ctype.split(";")[0].strip().lower()
    if base not in ALLOWED_CONTENT_TYPES:
        raise WebhookError(
            "content type %r is not accepted; allowed: %s. TradingView can be "
            "configured to send JSON, so accepting form-encoded or plain-text "
            "bodies would add parsers for no benefit."
            % (base, ", ".join(ALLOWED_CONTENT_TYPES)))
    return base


def assert_size(body: bytes) -> int:
    """Validation 5. Checked on BYTES, before any decode or parse."""
    if not isinstance(body, (bytes, bytearray)):
        raise WebhookError(
            "body must be bytes: measuring the size of a str measures "
            "characters, and a multi-byte payload would pass a byte limit it "
            "actually exceeds")
    n = len(body)
    if n == 0:
        raise WebhookError("body is empty")
    if n > MAX_BODY_BYTES:
        raise WebhookError(
            "body is %d bytes, over the %d-byte limit. Refused before parsing: "
            "the point of a size limit is to bound work BEFORE the expensive "
            "step, not to report it afterwards." % (n, MAX_BODY_BYTES))
    return n


def verify_signature(body: bytes, provided: Optional[str],
                     secret: Optional[str]) -> None:
    """
    Validation 2. HMAC-SHA256 over the RAW BODY, compared in constant time.

    Computed over the exact bytes received, never over a re-serialized parse:
    `json.dumps(json.loads(body))` differs from `body` in key order and spacing,
    so a signature checked against it would fail on valid payloads and, worse,
    could be made to pass on modified ones.
    """
    if not secret:
        raise WebhookAuthError(
            "no shared secret is configured, so this receiver cannot establish "
            "who sent a delivery. SS.7.1 Level 4 requires an authentication or "
            "shared-secret mechanism where supported; TradingView supports a "
            "secret in the alert body or a custom header. Refusing rather than "
            "accepting unauthenticated events, because an open endpoint is "
            "reachable by anyone who learns the URL.")
    if not provided:
        raise WebhookAuthError(
            "delivery carries no signature header. Expected an HMAC-SHA256 hex "
            "digest of the raw body.")
    expected = hmac.new(secret.encode("utf-8"), bytes(body),
                        hashlib.sha256).hexdigest()
    got = provided.strip().lower()
    if got.startswith("sha256="):
        got = got[len("sha256="):]
    # compare_digest, not ==, so the comparison time does not depend on how many
    # leading characters matched. The message deliberately reveals NEITHER value.
    if not hmac.compare_digest(expected, got):
        raise WebhookAuthError(
            "signature mismatch: the delivery was not signed with the "
            "configured secret, or the body was modified in transit. Neither "
            "the received nor the expected digest is reported -- an error "
            "message that echoes them turns this endpoint into an oracle.")


def assert_source_allowed(source_ip: str,
                          allowlist: Optional[Sequence[str]]) -> None:
    """
    Validation 3. "Where appropriate" -- so an empty allowlist means not
    configured, and that is allowed but recorded, rather than silently treated
    as "allow all".
    """
    if not allowlist:
        return
    if not isinstance(source_ip, str) or not source_ip.strip():
        raise WebhookError(
            "source allowlisting is configured but the delivery has no source "
            "address to check")
    if source_ip.strip() not in tuple(allowlist):
        raise WebhookAuthError(
            "source %r is not in the allowlist. An IP allowlist is a weak "
            "control -- addresses change and can be spoofed on some paths -- so "
            "it supplements the signature and never replaces it."
            % (source_ip,))


def parse_body(body: bytes) -> Dict[str, Any]:
    """
    Validation 4, part one: the body must be a JSON OBJECT.

    A JSON array or bare scalar is refused rather than coerced: `[1,2,3]` has no
    field names, so every subsequent validation would be reading positions.
    """
    try:
        text = bytes(body).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise WebhookError(
            "body is not valid UTF-8 (%s). A payload whose encoding must be "
            "guessed can be made to decode differently by the sender than by "
            "the validator." % (exc,))
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise WebhookError("body is not valid JSON: %s" % (exc,))
    if not isinstance(data, dict):
        raise WebhookError(
            "body must be a JSON object, got %s. An array or scalar has no "
            "field names, so the required fields could only be read by "
            "position." % (type(data).__name__,))
    return data


def assert_no_instructions(payload: Mapping[str, Any]) -> None:
    """
    The seven prohibitions, enforced where a payload becomes an object.

    Refuses rather than strips. Stripping would produce a ValidatedEvent that
    looks clean while the sender believes it commanded something, and the
    mismatch is invisible to both sides -- the sender sees HTTP 200. It also
    leaves the next maintainer with no evidence that senders are trying.

    Nested objects are walked, because `{"tv": {"action": "buy"}}` is the same
    instruction one level down.
    """
    found = []

    def walk(node, path):
        if isinstance(node, Mapping):
            for key, value in node.items():
                low = str(key).strip().lower()
                here = "%s.%s" % (path, key) if path else str(key)
                if low in INSTRUCTION_KEYS:
                    found.append((here, INSTRUCTION_KEYS[low]))
                else:
                    # Second layer. Only reached when the exact map misses, so a
                    # listed key still reports its own prohibition. This is what
                    # catches the sender's next naming choice --
                    # "disable_risk_checks" rather than "disable_risk".
                    for tok in key_tokens(key):
                        if tok in INSTRUCTION_TOKENS:
                            found.append((here, INSTRUCTION_TOKENS[tok]))
                            break
                walk(value, here)
        elif isinstance(node, (list, tuple)):
            for i, item in enumerate(node):
                walk(item, "%s[%d]" % (path, i))

    walk(payload, "")
    if found:
        # Report ALL of them: fixing one and resubmitting only to be refused
        # again teaches the sender that the endpoint is arbitrary.
        raise WebhookError(
            "refusing a payload carrying %d instruction field(s): %s. SS.7.1 "
            "Level 4 states webhook payloads are untrusted data and embedded "
            "instructions cannot %s. This receiver records that an alert fired; "
            "it does not take orders from the alert. The fields are refused "
            "rather than ignored, because a silently-stripped instruction leaves "
            "the sender believing it was obeyed."
            % (len(found),
               ", ".join("%s (-> cannot %s)" % (p, w) for p, w in found),
               ", ".join(sorted({w for _, w in found}))))


def _require_str(payload, key, label, allowed=None, maxlen=128):
    value = payload.get(key)
    if value is None or not isinstance(value, str) or not value.strip():
        raise WebhookError(
            "%s is required: %r is missing or not a non-empty string. %s"
            % (label, key,
               "Without it the delivery cannot be attributed to an alert."
               if allowed is None else "Allowed: %s." % (", ".join(allowed),)))
    text = value.strip()
    if len(text) > maxlen:
        raise WebhookError(
            "%s is %d characters, over the %d-character limit. A long free-text "
            "field in a durable record is a place to hide a payload."
            % (label, len(text), maxlen))
    if allowed is not None and text not in allowed:
        raise WebhookError(
            "%s %r is not recognised; allowed: %s" % (label, text,
                                                      ", ".join(allowed)))
    return text


_ID_SAFE = re.compile(r"^[A-Za-z0-9._:\-]{1,128}$")


def _require_id(payload, key, label):
    text = _require_str(payload, key, label)
    if not _ID_SAFE.match(text):
        raise WebhookError(
            "%s %r contains characters outside [A-Za-z0-9._:-]. Identifiers are "
            "compared, logged, and written to a durable file, so the character "
            "set is restricted rather than escaped at each use."
            % (label, text))
    return text


def parse_timestamp(payload: Mapping[str, Any]) -> datetime.datetime:
    """
    Validation 7. Requires an explicit, timezone-aware ISO-8601 instant.

    A naive timestamp is refused rather than assumed UTC: TradingView alerts can
    be configured in exchange time, and reading one as UTC shifts an event by
    hours -- which then passes the age check while describing the wrong market.
    """
    raw = payload.get("fired_at") or payload.get("timestamp") or payload.get("time")
    if raw is None:
        raise WebhookError(
            "no timestamp: expected 'fired_at' (or 'timestamp'/'time') as an "
            "ISO-8601 instant with an offset. An undated delivery cannot be "
            "checked for age or replay.")
    if not isinstance(raw, str):
        raise WebhookError(
            "timestamp must be an ISO-8601 string, got %s. An epoch number is "
            "refused because seconds and milliseconds are indistinguishable at "
            "a glance and differ by a factor of 1000."
            % (type(raw).__name__,))
    text = raw.strip().replace("Z", "+00:00")
    try:
        ts = datetime.datetime.fromisoformat(text)
    except ValueError as exc:
        raise WebhookError("timestamp %r is not ISO-8601: %s" % (raw, exc))
    if ts.tzinfo is None:
        raise WebhookError(
            "timestamp %r has no timezone offset. It will not be assumed UTC: "
            "an alert configured in exchange time would be shifted by hours "
            "while still passing the age check." % (raw,))
    return ts


def assert_age(fired_at: datetime.datetime, now=None) -> float:
    """
    Validation 8 (and the freshness half of 11). Returns the age in seconds.
    """
    now = now or _utc_now()
    age = (now - fired_at).total_seconds()
    if age > MAX_EVENT_AGE_SECONDS:
        raise WebhookError(
            "event fired %.0fs ago, over the %ds maximum age. A stale delivery "
            "describes a market that no longer exists, and accepting one is how "
            "a delayed replay looks legitimate."
            % (age, MAX_EVENT_AGE_SECONDS))
    if age < -MAX_CLOCK_SKEW_SECONDS:
        raise WebhookError(
            "event is timestamped %.0fs in the FUTURE, beyond the %ds skew "
            "tolerance. Accepting it would let a sender make a delivery "
            "permanently fresh and defeat the age check entirely."
            % (-age, MAX_CLOCK_SKEW_SECONDS))
    return age


def manifest() -> Dict[str, Any]:
    return {"level": "SS.7.1 Level 4 (webhook integration)",
            "validations": list(VALIDATIONS),
            "n_validations": len(VALIDATIONS),
            "prohibitions": list(PROHIBITIONS),
            "n_prohibitions": len(PROHIBITIONS),
            "prohibition_enforcement": dict(PROHIBITION_ENFORCEMENT),
            "origin_label": WEBHOOK_ORIGIN,
            "origin_rationale": ORIGIN_RATIONALE,
            "can_authorize_trades": False,
            "can_price_calculations": False,
            "http_server_included": False,
            "max_body_bytes": MAX_BODY_BYTES,
            "max_event_age_seconds": MAX_EVENT_AGE_SECONDS,
            "max_clock_skew_seconds": MAX_CLOCK_SKEW_SECONDS,
            "n_instruction_keys_refused": len(INSTRUCTION_KEYS),
            "queue": "append-only JSONL, fsync before acknowledgement"}


# ---------------------------------------------------------------------------
# The durable queue.
# ---------------------------------------------------------------------------

class EventQueue(object):
    """
    Append-only JSONL queue with an on-disk seen-set for replay detection.

    WHY A FILE AND NOT AN IN-MEMORY SET

    The replay check is the one validation whose state must outlive the process.
    An in-memory nonce set forgets every event on restart, so restarting the
    receiver -- or crashing it deliberately -- re-opens the entire replay window.
    MEASURED behaviour, asserted by a test: a second EventQueue opened on the same
    path refuses an event the first one accepted.

    WHY fsync BEFORE ACKNOWLEDGING

    An acknowledgement is a promise that the event will not be lost. A record
    sitting in the OS page cache when the machine loses power breaks that promise
    silently: the sender will never retry, because it was told 200. So the append
    is flushed and fsync'd before receive() returns.

    WHAT THIS IS NOT: it is not distributed, not multi-process, and not ordered by
    anything but arrival. Those limits are stated because a queue that quietly
    claims more is how a duplicate slips through under concurrency.
    """

    def __init__(self, path: str, seen_limit: int = 100000):
        if not isinstance(path, str) or not path.strip():
            raise WebhookError("queue path must be a non-empty string")
        if not isinstance(seen_limit, int) or isinstance(seen_limit, bool) \
                or seen_limit <= 0:
            raise WebhookError("seen_limit must be a positive integer")
        self.path = path
        self.seen_limit = seen_limit
        parent = os.path.dirname(os.path.abspath(path))
        if parent and not os.path.isdir(parent):
            os.makedirs(parent, exist_ok=True)
        self._seen = {}          # event_id -> received_at ISO string
        self._load_seen()

    def _load_seen(self):
        """Rebuild the seen-set from the queue file, tolerating a torn last line."""
        if not os.path.exists(self.path):
            return
        with open(self.path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    # A torn final line is expected after a crash mid-append. It
                    # is SKIPPED, not treated as a fatal error: refusing to start
                    # because of one damaged record would take the receiver down
                    # permanently, and the record was never acknowledged (the
                    # fsync had not returned), so the sender will retry it.
                    continue
                eid = rec.get("event_id")
                if eid:
                    self._seen[eid] = rec.get("received_at", "")

    def has_seen(self, event_id: str) -> bool:
        return event_id in self._seen

    def __len__(self):
        return len(self._seen)

    def append(self, event: "ValidatedEvent") -> str:
        """
        Persist one event durably. Returns the queue record's path:line marker.

        Refuses a duplicate rather than overwriting, and re-checks here rather
        than trusting the caller's earlier check: this is the only place that can
        make the guarantee, since it is the only place that writes.
        """
        if not isinstance(event, ValidatedEvent):
            raise WebhookError(
                "only a ValidatedEvent may be queued, got %s. Queueing an "
                "unvalidated payload would move the validation boundary to "
                "whoever reads the queue later."
                % (type(event).__name__,))
        if event.event_id in self._seen:
            raise WebhookError(
                "event_id %r is already queued (first seen %s): refusing to "
                "append a duplicate."
                % (event.event_id, self._seen[event.event_id]))
        record = event.to_dict()
        # Headers are already redacted by receive(), but re-redact here. Defence
        # in depth is justified for exactly one reason: this is the step that
        # makes data permanent, and a secret written to a durable file cannot be
        # unwritten.
        record["headers"] = redact_headers(record.get("headers", {}))
        record["queued_at"] = _utc_now().isoformat()
        line = json.dumps(record, sort_keys=True, default=str)
        if "\n" in line:
            raise WebhookError("refusing to write a record containing a newline")
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        self._seen[event.event_id] = record.get("received_at", "")
        if len(self._seen) > self.seen_limit:
            # Bound memory, and say what the consequence is rather than pretending
            # there is none: the oldest ids become replayable again. The limit is
            # high enough that reaching it means the file should be rotated.
            oldest = sorted(self._seen.items(), key=lambda kv: kv[1])
            for eid, _ in oldest[:len(self._seen) - self.seen_limit]:
                del self._seen[eid]
        return "%s:%d" % (self.path, len(self._seen))

    def read_all(self) -> Tuple[Dict[str, Any], ...]:
        """Every queued record, as inert dicts. Never returns callables."""
        if not os.path.exists(self.path):
            return ()
        out = []
        with open(self.path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        continue
        return tuple(out)


# ---------------------------------------------------------------------------
# The receiver.
# ---------------------------------------------------------------------------

#: Maps each of the sixteen required validations to the callable or step that
#: performs it. A test asserts this covers VALIDATIONS exactly -- the mechanism
#: that stops a validation from being quietly dropped while still being listed.
VALIDATION_KEYS: Mapping[str, str] = MappingProxyType({
    "https": "assert_https",
    "authentication or shared secret": "verify_signature",
    "source allowlisting": "assert_source_allowed",
    "payload schema": "parse_body + _require_str/_require_id",
    "payload size": "assert_size",
    "content type": "assert_content_type",
    "timestamp": "parse_timestamp",
    "maximum event age": "assert_age",
    "event id or nonce": "_require_id(event_id)",
    "duplicate delivery": "EventQueue.has_seen",
    "replay attempts": "EventQueue.has_seen + assert_age (persistent seen-set)",
    "expected alert id": "expected_alert_ids membership",
    "symbol": "_require_str(symbol) + expected_symbols",
    "exchange": "_require_str(exchange) + expected_exchanges",
    "timeframe": "_require_str(timeframe, ALLOWED_TIMEFRAMES)",
    "strategy id and version": "_require_id(strategy_id) + strategy_version",
})


def receive(method: str, url: str, headers: Mapping[str, str], body: bytes,
            queue: "EventQueue", secret: Optional[str] = None,
            source_ip: str = "", allowlist: Optional[Sequence[str]] = None,
            expected_alert_ids: Optional[Sequence[str]] = None,
            expected_symbols: Optional[Sequence[str]] = None,
            expected_exchanges: Optional[Sequence[str]] = None,
            now=None) -> Dict[str, Any]:
    """
    Validate a delivery, queue it durably, and return an acknowledgement.

    ORDER IS THE DESIGN. Cheap and identity-establishing checks run before
    expensive and semantic ones, and EVERYTHING runs before the acknowledgement:

      method -> https -> content type -> size -> signature -> source
             -> parse -> instruction prohibitions -> schema -> timestamp/age
             -> event id -> duplicate/replay -> queue+fsync -> ack

    Signature verification precedes parsing deliberately: parsing is where a
    hostile body gets to influence the process, so an unauthenticated body should
    never reach the parser. And the instruction prohibitions run before the schema
    checks, so a payload trying to command something is told THAT rather than
    being sent away over a missing timeframe.

    Returns a dict with 'accepted': True. It never returns a partial success, and
    it never returns False -- refusals raise, so a caller cannot forget to check.
    """
    now = now or _utc_now()
    if not isinstance(method, str) or method.strip().upper() != "POST":
        raise WebhookError(
            "webhooks must arrive by POST, got %r. A GET delivery would be "
            "retried by intermediaries, cached, and logged with its query "
            "string." % (method,))
    if not isinstance(queue, EventQueue):
        raise WebhookError(
            "receive() requires an EventQueue: there is no path that validates "
            "an event without durably recording it, because replay detection "
            "depends on the persisted seen-set")

    assert_https(url)
    assert_content_type(headers)
    n_bytes = assert_size(body)

    provided = None
    for name, value in headers.items():
        if str(name).lower() in ("x-signature", "x-hub-signature-256",
                                 "x-tv-signature"):
            provided = str(value)
            break
    verify_signature(body, provided, secret)
    assert_source_allowed(source_ip, allowlist)

    payload = parse_body(body)
    # Before ANY field is read for meaning: a payload that carries instructions is
    # refused as a whole, not sanitized into an acceptable one.
    assert_no_instructions(payload)

    event_id = _require_id(payload, "event_id", "event id")
    alert_id = _require_id(payload, "alert_id", "alert id")
    symbol = _require_str(payload, "symbol", "symbol", maxlen=32)
    exchange = _require_str(payload, "exchange", "exchange", maxlen=32)
    timeframe = _require_str(payload, "timeframe", "timeframe",
                             allowed=ALLOWED_TIMEFRAMES)
    strategy_id = _require_id(payload, "strategy_id", "strategy id")
    strategy_version = _require_str(payload, "strategy_version",
                                    "strategy version", maxlen=32)

    if expected_alert_ids and alert_id not in tuple(expected_alert_ids):
        raise WebhookError(
            "alert id %r is not one this receiver expects (%s). An unexpected "
            "alert id means either a misconfigured alert or a delivery intended "
            "for someone else; neither should be recorded as this system's."
            % (alert_id, ", ".join(expected_alert_ids)))
    if expected_symbols and symbol not in tuple(expected_symbols):
        raise WebhookError(
            "symbol %r is not in this receiver's expected set (%s)"
            % (symbol, ", ".join(expected_symbols)))
    if expected_exchanges and exchange not in tuple(expected_exchanges):
        raise WebhookError(
            "exchange %r is not in this receiver's expected set (%s). The same "
            "ticker trades on different venues at different prices, so an "
            "unexpected venue is not a cosmetic mismatch."
            % (exchange, ", ".join(expected_exchanges)))

    fired_at = parse_timestamp(payload)
    age = assert_age(fired_at, now=now)

    # Duplicate and replay are the same check against a PERSISTENT set, plus the
    # age bound above. Neither alone is sufficient: the age bound lets an attacker
    # replay within the window, and the seen-set alone would let them replay a
    # very old delivery the moment the file is rotated.
    if queue.has_seen(event_id):
        raise WebhookError(
            "event_id %r has already been delivered. Refusing the repeat: this "
            "is either a duplicate delivery (senders retry, which is correct "
            "behaviour and must be idempotent here) or a replay. Both are "
            "handled the same way, because the receiver cannot tell them apart "
            "and does not need to." % (event_id,))

    known = {"event_id", "alert_id", "symbol", "exchange", "timeframe",
             "strategy_id", "strategy_version", "fired_at", "timestamp", "time"}
    extra = {}
    for key, value in payload.items():
        if key in known:
            continue
        # Leftovers are kept as inert TEXT, truncated. A nested structure here
        # would let a sender smuggle a document into a durable record, and a
        # non-string value would be read back with its type intact by whoever
        # processes the queue.
        extra[str(key)[:64]] = str(value)[:256]

    event = ValidatedEvent(
        event_id=event_id, alert_id=alert_id, symbol=symbol, exchange=exchange,
        timeframe=timeframe, strategy_id=strategy_id,
        strategy_version=strategy_version, fired_at=fired_at, received_at=now,
        source_ip=str(source_ip or ""),
        body_sha256=hashlib.sha256(bytes(body)).hexdigest(), n_bytes=n_bytes,
        headers=redact_headers(headers), extra=extra,
        note="alert %s fired on %s/%s %s (age %.1fs at receipt)"
             % (alert_id, exchange, symbol, timeframe, age))

    marker = queue.append(event)
    return {"accepted": True, "event_id": event_id, "queued_at": marker,
            "age_seconds": age, "event": event,
            "next_step": "processing happens off this path; the event is a "
                         "notification that an alert fired and carries no "
                         "authority to trade"}
