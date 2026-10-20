"""
Phase 8A (D-0126): a LOCAL paper-trading engine that implements the SS.6.2
two-phase protocol and the SS.6.3 controls, so every SS.24 Phase 8A test has
real code to exercise -- not a refusal.

WHAT THIS IS
------------
A simulated broker ("PaperVenue") and the orchestration in front of it
("PaperEngine"): preview -> human confirmation -> commit, with an append-only
hash-chained audit log, a persistent idempotency store, a kill switch that an
automated principal can engage but never disengage, deterministic pre-trade
limits, an order state machine (SS.6.4) whose terminal states are only ever set
from a venue response, and reconciliation of the engine's ledger against the
venue's.

WHAT THIS IS NOT
----------------
It is not a broker adapter. It reaches no network and holds no credential.
LIVE is refused at four independent points (environment, account prefix, mode
capability, venue). Nothing here changes execution.mode.LIVE_PREREQUISITES: a
verified broker adapter and licensed market data are still absent, so live
trading stays unreachable regardless of configuration (SS.24: "Live trading
remains disabled after this phase unless separately approved").

SEPARATION (SS.5.6)
-------------------
Imports only the standard library and execution.mode. The webhook receiver, the
LLM, RAG and screenshots therefore have no import path to an order. A commit
also requires a HUMAN principal and the exact single-use confirmation token,
which no webhook, document or model output carries.

Stdlib only.
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import json
import math
import os
import secrets
import threading
from types import MappingProxyType
from typing import Any, Dict, List, Mapping, Optional, Tuple

from execution.mode import ExecutionModeError, require


class PaperError(RuntimeError):
    """A paper-trading request was refused. Refusals raise; they never return."""


# ---------------------------------------------------------------------------
# Vocabularies
# ---------------------------------------------------------------------------

ENVIRONMENT = "PAPER"                 # the only environment this engine serves
PAPER_ACCOUNT_PREFIX = "PAPER-"       # SS.6.3: unambiguous identifiers
LIVE_ACCOUNT_PREFIX = "LIVE-"
SIDES = ("buy", "sell", "sell_short", "buy_to_cover")
ORDER_TYPES = ("market", "limit")
TIME_IN_FORCE = ("day", "gtc", "ioc", "fok")

#: SS.6.4, verbatim, in the spec's order.
ORDER_STATES = ("DRAFT", "PREVIEWED", "WAITING_FOR_CONFIRMATION", "SUBMITTED",
                "ACKNOWLEDGED", "PARTIALLY_FILLED", "FILLED", "CANCEL_PENDING",
                "CANCELLED", "REJECTED", "EXPIRED", "UNKNOWN")

#: SS.6.4: "Never claim SUBMITTED, FILLED, CANCELLED, or REJECTED without a
#: verified broker response." These are set ONLY by _apply_venue_response.
VENUE_ONLY_STATES = frozenset({"SUBMITTED", "ACKNOWLEDGED", "PARTIALLY_FILLED",
                               "FILLED", "CANCELLED", "REJECTED"})
TERMINAL_STATES = frozenset({"FILLED", "CANCELLED", "REJECTED", "EXPIRED"})

TRANSITIONS: Mapping[str, frozenset] = MappingProxyType({
    "DRAFT": frozenset({"PREVIEWED"}),
    "PREVIEWED": frozenset({"WAITING_FOR_CONFIRMATION", "EXPIRED"}),
    "WAITING_FOR_CONFIRMATION": frozenset({"SUBMITTED", "REJECTED", "EXPIRED",
                                           "UNKNOWN"}),
    "SUBMITTED": frozenset({"ACKNOWLEDGED", "REJECTED", "UNKNOWN"}),
    "ACKNOWLEDGED": frozenset({"PARTIALLY_FILLED", "FILLED", "CANCEL_PENDING",
                               "CANCELLED", "REJECTED", "UNKNOWN"}),
    "PARTIALLY_FILLED": frozenset({"PARTIALLY_FILLED", "FILLED", "CANCEL_PENDING",
                                   "CANCELLED", "UNKNOWN"}),
    "CANCEL_PENDING": frozenset({"CANCELLED", "FILLED", "PARTIALLY_FILLED",
                                 "UNKNOWN"}),
    "UNKNOWN": frozenset({"ACKNOWLEDGED", "PARTIALLY_FILLED", "FILLED",
                          "CANCELLED", "REJECTED"}),
    "FILLED": frozenset(), "CANCELLED": frozenset(), "REJECTED": frozenset(),
    "EXPIRED": frozenset(),
})

#: Principals. Only HUMAN may confirm a commit or disengage the kill switch.
PRINCIPALS = ("HUMAN", "LLM", "WEBHOOK", "AUTOMATION")

#: Keys whose values never reach the audit log (plaintext-secret blocker).
SECRET_KEY_FRAGMENTS = ("secret", "token", "password", "api_key", "apikey",
                        "credential", "private_key", "authorization")


def _utc(dt: Optional[datetime.datetime]) -> datetime.datetime:
    dt = dt or datetime.datetime.now(datetime.timezone.utc)
    if dt.tzinfo is None:
        raise PaperError("timestamps must be timezone-aware")
    return dt.astimezone(datetime.timezone.utc)


def _iso(dt: datetime.datetime) -> str:
    return _utc(dt).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _finite_pos(x: Any, field: str) -> float:
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        raise PaperError("%s must be a number, got %s" % (field, type(x).__name__))
    v = float(x)
    if not math.isfinite(v) or v <= 0:
        raise PaperError("%s must be finite and > 0, got %r" % (field, x))
    return v


def redact(obj: Any) -> Any:
    """Copy of `obj` with every secret-looking key's value replaced."""
    if isinstance(obj, Mapping):
        out = {}
        for k, v in obj.items():
            if any(f in str(k).lower() for f in SECRET_KEY_FRAGMENTS):
                out[str(k)] = "[REDACTED]"
            else:
                out[str(k)] = redact(v)
        return out
    if isinstance(obj, (list, tuple)):
        return [redact(v) for v in obj]
    return obj


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Inputs: quotes and limits (immutable)
# ---------------------------------------------------------------------------

class _Frozen(object):
    __slots__ = ("_frozen",)

    def __setattr__(self, k, v):
        if getattr(self, "_frozen", False):
            raise AttributeError("%s is immutable" % type(self).__name__)
        object.__setattr__(self, k, v)

    def __delattr__(self, k):
        raise AttributeError("%s is immutable" % type(self).__name__)


class QuoteSnapshot(_Frozen):
    """
    The quote the engine prices against. Constructed by the CALLER (execution
    imports nothing from market/), so every field is validated here.
    `ask_size`/`bid_size` bound how much a market order can fill now (partial
    fills). `market_status` must be OPEN to trade.
    """
    __slots__ = ("instrument_id", "bid", "ask", "last", "timestamp",
                 "market_status", "source", "bid_size", "ask_size")

    def __init__(self, instrument_id, bid, ask, last, timestamp, market_status,
                 source, bid_size=1e12, ask_size=1e12):
        object.__setattr__(self, "_frozen", False)
        if not isinstance(instrument_id, str) or not instrument_id.strip():
            raise PaperError("quote instrument_id must be a non-empty string")
        self.instrument_id = instrument_id.strip()
        self.bid = _finite_pos(bid, "bid")
        self.ask = _finite_pos(ask, "ask")
        self.last = _finite_pos(last, "last")
        if self.bid > self.ask:
            raise PaperError("crossed quote: bid %g > ask %g" % (self.bid, self.ask))
        self.timestamp = _utc(timestamp)
        if market_status not in ("OPEN", "CLOSED", "PRE_MARKET", "POST_MARKET",
                                 "HALTED", "UNKNOWN"):
            raise PaperError("unknown market_status %r" % (market_status,))
        self.market_status = market_status
        if not isinstance(source, str) or not source.strip():
            raise PaperError("quote source must be named")
        self.source = source
        self.bid_size = _finite_pos(bid_size, "bid_size")
        self.ask_size = _finite_pos(ask_size, "ask_size")
        self._frozen = True

    def to_dict(self):
        return {k: (_iso(getattr(self, k)) if k == "timestamp" else getattr(self, k))
                for k in self.__slots__}


class RiskLimits(_Frozen):
    """User-defined limits (SS.6.3). Immutable; a change makes a new version."""
    __slots__ = ("max_order_notional", "max_daily_notional", "max_position_qty",
                 "max_concentration_pct", "max_daily_loss", "max_orders_per_minute",
                 "price_deviation_pct", "max_quote_age_s", "preview_ttl_s",
                 "instrument_allowlist", "tick_size", "lot_size", "allow_short",
                 "max_leverage", "version")

    def __init__(self, instrument_allowlist, max_order_notional=10_000.0,
                 max_daily_notional=50_000.0, max_position_qty=1_000.0,
                 max_concentration_pct=50.0, max_daily_loss=1_000.0,
                 max_orders_per_minute=5, price_deviation_pct=1.0,
                 max_quote_age_s=5.0, preview_ttl_s=60.0, tick_size=None,
                 lot_size=None, allow_short=False, max_leverage=1.0):
        object.__setattr__(self, "_frozen", False)
        if not instrument_allowlist:
            raise PaperError("an instrument allowlist is required (SS.6.3)")
        self.instrument_allowlist = tuple(sorted(set(instrument_allowlist)))
        for f in ("max_order_notional", "max_daily_notional", "max_position_qty",
                  "max_concentration_pct", "max_daily_loss", "price_deviation_pct",
                  "max_quote_age_s", "preview_ttl_s", "max_leverage"):
            setattr(self, f, _finite_pos(locals()[f], f))
        if not isinstance(max_orders_per_minute, int) or max_orders_per_minute < 1:
            raise PaperError("max_orders_per_minute must be an int >= 1")
        self.max_orders_per_minute = max_orders_per_minute
        self.tick_size = MappingProxyType(dict(tick_size or {}))
        self.lot_size = MappingProxyType(dict(lot_size or {}))
        if not isinstance(allow_short, bool):
            raise PaperError("allow_short must be a bool")
        self.allow_short = allow_short
        body = json.dumps({k: (list(v.items()) if isinstance(v, Mapping) else v)
                           for k, v in ((s, getattr(self, s)) for s in self.__slots__
                                        if s != "version")},
                          sort_keys=True, default=list)
        self.version = "lim_" + _sha(body)[:16]
        self._frozen = True


# ---------------------------------------------------------------------------
# Durable stores: audit log, idempotency, kill switch
# ---------------------------------------------------------------------------

def _append_durable(path: str, line: str) -> None:
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")
        fh.flush()
        os.fsync(fh.fileno())


class AuditLog(object):
    """
    Append-only JSONL, hash-chained: every record carries the previous record's
    hash, so an edited, deleted or reordered line breaks verify(). Arguments are
    redacted before they are written; a token is never logged, only its hash.
    """

    GENESIS = "0" * 64

    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        self._last = self.GENESIS
        self._n = 0
        if os.path.exists(path):
            ok, n, last, problem = self._scan()
            if not ok:
                raise PaperError("audit log %s is corrupt (%s); refusing to append "
                                 "to a broken chain" % (path, problem))
            self._n, self._last = n, last

    def _scan(self):
        prev, n = self.GENESIS, 0
        with open(self.path, encoding="utf-8") as fh:
            for i, line in enumerate(fh, 1):
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    return False, n, prev, "line %d is not JSON" % i
                h = rec.pop("hash", None)
                if rec.get("prev") != prev:
                    return False, n, prev, "line %d does not chain to line %d" % (i, i - 1)
                if _sha(json.dumps(rec, sort_keys=True, ensure_ascii=False)) != h:
                    return False, n, prev, "line %d hash mismatch (edited)" % i
                prev, n = h, n + 1
        return True, n, prev, ""

    def write(self, event: str, now: datetime.datetime, **fields: Any) -> str:
        with self._lock:
            rec = {"seq": self._n + 1, "event": event, "at": _iso(now),
                   "prev": self._last}
            rec.update(redact(fields))
            h = _sha(json.dumps(rec, sort_keys=True, ensure_ascii=False))
            rec["hash"] = h
            _append_durable(self.path, json.dumps(rec, sort_keys=True,
                                                  ensure_ascii=False))
            self._last, self._n = h, self._n + 1
            return "aud_%06d_%s" % (rec["seq"], h[:12])

    def verify(self) -> Tuple[bool, int, str]:
        if not os.path.exists(self.path):
            return True, 0, ""
        ok, n, _last, problem = self._scan()
        return ok, n, problem

    def records(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.path):
            return []
        with open(self.path, encoding="utf-8") as fh:
            return [json.loads(x) for x in fh if x.strip()]


class IdempotencyStore(object):
    """
    Persistent key -> (content hash, order id). The same key with the same
    content returns the original order (a retry is safe); the same key with
    different content is refused (a key reused for another order is a bug).
    """

    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        self._map: Dict[str, Tuple[str, str]] = {}
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    if line.strip():
                        r = json.loads(line)
                        self._map[r["key"]] = (r["content"], r["order_id"])

    def lookup(self, key: str, content: str) -> Optional[str]:
        with self._lock:
            hit = self._map.get(key)
        if hit is None:
            return None
        if hit[0] != content:
            raise PaperError(
                "idempotency key %r was already used for a DIFFERENT order "
                "(%s); refusing rather than guessing which one is meant" % (key, hit[1]))
        return hit[1]

    def record(self, key: str, content: str, order_id: str) -> None:
        with self._lock:
            if key in self._map:
                raise PaperError("idempotency key %r already recorded" % key)
            _append_durable(self.path, json.dumps(
                {"key": key, "content": content, "order_id": order_id}))
            self._map[key] = (content, order_id)


class KillSwitch(object):
    """
    Persistent. ANY principal may ENGAGE it (stopping is always safe). Only a
    HUMAN may DISENGAGE it, with the exact confirmation phrase and a reason
    (SS.8.11: "cannot be initiated autonomously"). State survives restart, and
    an unreadable state file reads as ENGAGED (fail closed).
    """

    PHRASE = "I CONFIRM DISENGAGING THE PAPER KILL SWITCH"

    def __init__(self, path: str, audit: AuditLog):
        self.path, self.audit = path, audit

    def engaged(self) -> bool:
        if not os.path.exists(self.path):
            return False
        try:
            with open(self.path, encoding="utf-8") as fh:
                return json.load(fh).get("engaged") is not False
        except (OSError, ValueError):
            return True

    def _write(self, engaged: bool) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"engaged": engaged}, fh)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self.path)

    def engage(self, principal: str, reason: str, now=None) -> str:
        if principal not in PRINCIPALS:
            raise PaperError("unknown principal %r" % (principal,))
        self._write(True)
        return self.audit.write("kill_switch_engaged", _utc(now), principal=principal,
                                reason=str(reason)[:200])

    def disengage(self, principal: str, confirmation_phrase: str, reason: str,
                  now=None) -> str:
        if principal != "HUMAN":
            self.audit.write("kill_switch_disengage_refused", _utc(now),
                             principal=principal)
            raise PaperError("only a HUMAN may disengage the kill switch; %r may "
                             "not (SS.8.11)" % (principal,))
        if confirmation_phrase != self.PHRASE:
            raise PaperError("disengaging requires the exact phrase %r" % self.PHRASE)
        if not str(reason or "").strip():
            raise PaperError("disengaging requires a written reason")
        self._write(False)
        return self.audit.write("kill_switch_disengaged", _utc(now), principal=principal,
                                reason=str(reason)[:200])


# ---------------------------------------------------------------------------
# The simulated venue
# ---------------------------------------------------------------------------

class VenueDisconnected(PaperError):
    """The venue could not be reached. The order's state is UNKNOWN, not failed."""


class PaperVenue(object):
    """
    A deterministic simulated broker. It accepts an order ONLY with a commit
    ticket signed by the engine that created it (preview-bypass blocker): no
    caller can reach the book without passing through commit().

    Fills: a marketable order fills against the quote, capped by the quote's
    size (the remainder rests -> PARTIALLY_FILLED). A non-marketable limit
    rests -> ACKNOWLEDGED. Rejections and disconnection are injectable for tests.
    """

    def __init__(self, ticket_key: bytes, reject_instruments=(), fee_per_order=1.0):
        self._key = ticket_key
        self.connected = True
        self.drop_after_accept = False      # accept, then lose the response
        self.reject_instruments = set(reject_instruments)
        self.fee_per_order = float(fee_per_order)
        self.orders: Dict[str, Dict[str, Any]] = {}
        self.fills: List[Dict[str, Any]] = []
        self._seq = 0
        self._lock = threading.Lock()

    def _check_ticket(self, order: Mapping[str, Any], ticket: str) -> None:
        body = json.dumps(order, sort_keys=True)
        good = hmac.new(self._key, body.encode("utf-8"), hashlib.sha256).hexdigest()
        if not isinstance(ticket, str) or not hmac.compare_digest(good, ticket):
            raise PaperError("venue refused an order without a valid commit ticket: "
                             "orders reach the venue only through PaperEngine.commit")

    def submit(self, order: Mapping[str, Any], ticket: str, quote: QuoteSnapshot,
               now: datetime.datetime) -> Dict[str, Any]:
        self._check_ticket(order, ticket)
        if not self.connected:
            raise VenueDisconnected("venue unreachable; the order was NOT confirmed")
        with self._lock:
            self._seq += 1
            vid = "ven_%06d" % self._seq
            if order["instrument_id"] in self.reject_instruments:
                rec = dict(order, venue_order_id=vid, status="REJECTED",
                           filled_qty=0.0, reason="instrument not tradable at venue")
                self.orders[vid] = rec
                resp = dict(rec)
            else:
                rec = dict(order, venue_order_id=vid, status="ACKNOWLEDGED",
                           filled_qty=0.0, reason="")
                self.orders[vid] = rec
                self._match(rec, quote, now)
                resp = dict(rec)
        if self.drop_after_accept:
            raise VenueDisconnected("connection lost after the venue accepted %s" % vid)
        return resp

    def _match(self, rec, quote, now):
        buying = rec["side"] in ("buy", "buy_to_cover")
        px = quote.ask if buying else quote.bid
        size = quote.ask_size if buying else quote.bid_size
        if rec["order_type"] == "limit":
            lp = rec["limit_price"]
            if (buying and lp < px) or (not buying and lp > px):
                if rec["time_in_force"] in ("ioc", "fok"):
                    rec["status"], rec["reason"] = "CANCELLED", "not marketable (%s)" % rec["time_in_force"]
                return
        remaining = rec["quantity"] - rec["filled_qty"]
        if rec["time_in_force"] == "fok" and size < remaining:
            rec["status"], rec["reason"] = "CANCELLED", "fok: insufficient size"
            return
        qty = min(remaining, size)
        if qty <= 0:
            return
        fee = self.fee_per_order if rec["filled_qty"] == 0 else 0.0
        self.fills.append({"venue_order_id": rec["venue_order_id"],
                           "client_order_id": rec["client_order_id"],
                           "account_id": rec["account_id"],
                           "instrument_id": rec["instrument_id"], "side": rec["side"],
                           "qty": qty, "price": px, "fee": fee, "at": _iso(now)})
        rec["filled_qty"] += qty
        if rec["filled_qty"] >= rec["quantity"]:
            rec["status"] = "FILLED"
        elif rec["time_in_force"] == "ioc":
            rec["status"], rec["reason"] = "CANCELLED", "ioc remainder cancelled"
        else:
            rec["status"] = "PARTIALLY_FILLED"

    def query(self, venue_order_id: str = None, client_order_id: str = None):
        if not self.connected:
            raise VenueDisconnected("venue unreachable")
        with self._lock:
            for rec in self.orders.values():
                if venue_order_id and rec["venue_order_id"] == venue_order_id:
                    return dict(rec)
                if client_order_id and rec["client_order_id"] == client_order_id:
                    return dict(rec)
        return None

    def cancel(self, venue_order_id: str) -> Dict[str, Any]:
        if not self.connected:
            raise VenueDisconnected("venue unreachable; cancel NOT confirmed")
        with self._lock:
            rec = self.orders.get(venue_order_id)
            if rec is None:
                raise PaperError("venue has no order %s" % venue_order_id)
            if rec["status"] in ("ACKNOWLEDGED", "PARTIALLY_FILLED"):
                rec["status"] = "CANCELLED"
                rec["reason"] = "cancelled on request"
            return dict(rec)

    def tick(self, quote: QuoteSnapshot, now) -> List[Dict[str, Any]]:
        """Re-match resting orders on a new quote (completes partial fills)."""
        out = []
        with self._lock:
            for rec in self.orders.values():
                if (rec["instrument_id"] == quote.instrument_id
                        and rec["status"] in ("ACKNOWLEDGED", "PARTIALLY_FILLED")):
                    self._match(rec, quote, now)
                    out.append(dict(rec))
        return out

    def positions(self, account_id: str) -> Dict[str, float]:
        pos: Dict[str, float] = {}
        for f in self.fills:
            if f["account_id"] != account_id:
                continue
            sgn = 1.0 if f["side"] in ("buy", "buy_to_cover") else -1.0
            pos[f["instrument_id"]] = pos.get(f["instrument_id"], 0.0) + sgn * f["qty"]
        return {k: v for k, v in pos.items() if abs(v) > 1e-12}


# ---------------------------------------------------------------------------
# The engine
# ---------------------------------------------------------------------------

class PaperEngine(object):
    """
    preview() -> human confirm -> commit(), and everything SS.6.2/6.3 requires
    around it. One engine per paper account set; state is in-memory plus the
    three durable stores under `state_dir`.
    """

    def __init__(self, state_dir: str, accounts: Mapping[str, float],
                 limits: RiskLimits, venue: Optional[PaperVenue] = None):
        os.makedirs(state_dir, exist_ok=True)
        for acct in accounts:
            if not isinstance(acct, str) or not acct.startswith(PAPER_ACCOUNT_PREFIX):
                raise PaperError("paper account ids must start with %r (got %r): "
                                 "SS.6.3 requires paper and live accounts to be "
                                 "unambiguous" % (PAPER_ACCOUNT_PREFIX, acct))
        if not isinstance(limits, RiskLimits):
            raise PaperError("limits must be a RiskLimits")
        self.audit = AuditLog(os.path.join(state_dir, "audit.jsonl"))
        self.idem = IdempotencyStore(os.path.join(state_dir, "idempotency.jsonl"))
        self.kill = KillSwitch(os.path.join(state_dir, "kill_switch.json"), self.audit)
        self._ticket_key = secrets.token_bytes(32)
        self.venue = venue or PaperVenue(self._ticket_key)
        self.venue._key = self._ticket_key
        self.limits = limits
        self.cash = {a: float(c) for a, c in accounts.items()}
        self.start_equity = dict(self.cash)
        self.orders: Dict[str, Dict[str, Any]] = {}
        self._previews: Dict[str, Dict[str, Any]] = {}
        self._fills_seen = 0
        self._submits: List[datetime.datetime] = []
        self._daily_notional: Dict[Tuple[str, str], float] = {}
        self._account_version = {a: 0 for a in accounts}
        self._lock = threading.RLock()

    # -- helpers ----------------------------------------------------------
    def _set_state(self, order: Dict[str, Any], new: str, venue_response: bool = False):
        old = order["state"]
        if new in VENUE_ONLY_STATES and not venue_response:
            raise PaperError("state %s may only come from a venue response (SS.6.4)" % new)
        if new not in TRANSITIONS[old]:
            raise PaperError("illegal order transition %s -> %s" % (old, new))
        order["state"] = new
        order["history"].append(new)

    def _account(self, account_id: Any, environment: Any) -> str:
        if environment != ENVIRONMENT:
            raise PaperError("environment must be exactly %r, got %r. This engine "
                             "serves paper only; a live order cannot be expressed "
                             "here." % (ENVIRONMENT, environment))
        if not isinstance(account_id, str) or account_id.startswith(LIVE_ACCOUNT_PREFIX):
            raise PaperError("account %r is a LIVE identifier; refused in PAPER" % (account_id,))
        if account_id not in self.cash:
            raise PaperError("account %r is not on this engine's allowlist" % (account_id,))
        return account_id

    def positions(self, account_id: str) -> Dict[str, float]:
        self._sync_fills()
        pos: Dict[str, float] = {}
        for o in self.orders.values():
            if o["account_id"] != account_id:
                continue
            sgn = 1.0 if o["side"] in ("buy", "buy_to_cover") else -1.0
            if o["filled_qty"]:
                pos[o["instrument_id"]] = pos.get(o["instrument_id"], 0.0) + sgn * o["filled_qty"]
        return {k: v for k, v in pos.items() if abs(v) > 1e-12}

    def _open_orders(self, account_id: str) -> int:
        return sum(1 for o in self.orders.values() if o["account_id"] == account_id
                   and o["state"] not in TERMINAL_STATES)

    def _sync_fills(self) -> None:
        """Apply venue fills to the engine's cash ledger exactly once each."""
        for f in self.venue.fills[self._fills_seen:]:
            sgn = -1.0 if f["side"] in ("buy", "buy_to_cover") else 1.0
            self.cash[f["account_id"]] += sgn * f["qty"] * f["price"] - f["fee"]
            # Matched by (account, client_order_id), NOT venue_order_id: an order
            # whose acknowledgement was lost (UNKNOWN) has no venue id yet, and
            # its fill must still land on it, exactly once.
            for o in self.orders.values():
                if (o["account_id"] == f["account_id"]
                        and o["client_order_id"] == f["client_order_id"]):
                    o["filled_qty"] = o.get("filled_qty", 0.0) + f["qty"]
                    o["fees"] = o.get("fees", 0.0) + f["fee"]
            self._account_version[f["account_id"]] += 1
            self._fills_seen += 1

    def _equity(self, account_id: str, quote: QuoteSnapshot) -> float:
        pos = self.positions(account_id)
        mv = sum(q * (quote.last if i == quote.instrument_id else 0.0)
                 for i, q in pos.items())
        return self.cash[account_id] + mv

    # -- SS.6.2 Phase A -----------------------------------------------------
    def preview(self, account_id, environment, instrument_id, side, quantity,
                order_type, client_order_id, quote: QuoteSnapshot,
                limit_price=None, time_in_force="day", now=None) -> Dict[str, Any]:
        now = _utc(now)
        require("preview_order")
        acct = self._account(account_id, environment)
        if side not in SIDES:
            raise PaperError("unknown side %r" % (side,))
        if order_type not in ORDER_TYPES:
            raise PaperError("order_type must be one of %s" % (ORDER_TYPES,))
        if time_in_force not in TIME_IN_FORCE:
            raise PaperError("unknown time_in_force %r" % (time_in_force,))
        if not isinstance(client_order_id, str) or not client_order_id.strip():
            raise PaperError("client_order_id is required (duplicate detection)")
        qty = _finite_pos(quantity, "quantity")
        if order_type == "limit":
            limit_price = _finite_pos(limit_price, "limit_price")
        elif limit_price is not None:
            raise PaperError("a market order must not carry limit_price")
        if not isinstance(quote, QuoteSnapshot) or quote.instrument_id != instrument_id:
            raise PaperError("a QuoteSnapshot for %r is required" % (instrument_id,))

        with self._lock:
            checks = self._risk_checks(acct, instrument_id, side, qty, order_type,
                                       limit_price, client_order_id, quote, now)
            ok = all(v == "PASS" for v, _ in checks.values())
            order = {"account_id": acct, "environment": ENVIRONMENT,
                     "instrument_id": instrument_id, "side": side, "quantity": qty,
                     "order_type": order_type, "limit_price": limit_price,
                     "time_in_force": time_in_force,
                     "client_order_id": client_order_id.strip()}
            content = json.dumps(order, sort_keys=True)
            # A random nonce, so two identical previews at one instant are two
            # previews (MEASURED in test_phase8a: a content-only id let the
            # second overwrite the first and silently void its token).
            preview_id = "prv_" + _sha(content + _iso(now) + secrets.token_hex(8))[:24]
            if preview_id in self._previews:
                raise PaperError("preview id collision; refusing to overwrite")
            price = limit_price if order_type == "limit" else (
                quote.ask if side in ("buy", "buy_to_cover") else quote.bid)
            token = secrets.token_urlsafe(16) if ok else None
            expiry = now + datetime.timedelta(seconds=self.limits.preview_ttl_s)
            self._previews[preview_id] = {
                "order": order, "content": content,
                "token_hash": _sha(token) if token else None, "used": False,
                "expiry": expiry, "quote": quote, "ok": ok,
                "limits_version": self.limits.version,
                "account_version": self._account_version[acct],
                "open_orders": self._open_orders(acct),
                "kill_engaged": self.kill.engaged()}
            aud = self.audit.write("preview", now, preview_id=preview_id,
                                   order=order, verdict="PASS" if ok else "REFUSE",
                                   failed=[k for k, (v, _) in checks.items() if v != "PASS"],
                                   quote=quote.to_dict())
        return {"preview_id": preview_id, "environment": ENVIRONMENT,
                "banner": "PAPER TRADING -- simulated venue, no real money",
                "order": order, "estimated_price": price,
                "estimated_notional": round(qty * price, 6),
                "fees": self.venue.fee_per_order, "slippage": 0.0,
                "risk_checks": {k: {"status": v, "detail": d} for k, (v, d) in checks.items()},
                "verdict": "PASS" if ok else "REFUSE",
                "quote_timestamp": _iso(quote.timestamp),
                "preview_expiry": _iso(expiry),
                "confirmation_token": token, "audit_event_id": aud}

    def _risk_checks(self, acct, inst, side, qty, otype, lp, coid, q, now):
        L = self.limits
        c: Dict[str, Tuple[str, str]] = {}

        def put(name, ok, detail):
            c[name] = ("PASS" if ok else "FAIL", detail)

        put("kill_switch", not self.kill.engaged(), "kill switch engaged" if self.kill.engaged() else "off")
        put("instrument_allowlist", inst in L.instrument_allowlist, inst)
        age = (now - q.timestamp).total_seconds()
        put("quote_freshness", 0 <= age <= L.max_quote_age_s,
            "quote age %.1fs (max %.1fs)" % (age, L.max_quote_age_s))
        put("trading_session", q.market_status == "OPEN", "market %s" % q.market_status)
        buying = side in ("buy", "buy_to_cover")
        ref = q.ask if buying else q.bid
        px = lp if otype == "limit" else ref
        dev = abs(px - q.last) / q.last * 100.0
        put("price_deviation", dev <= L.price_deviation_pct,
            "%.2f%% from last (max %.2f%%)" % (dev, L.price_deviation_pct))
        tick = L.tick_size.get(inst)
        put("tick_size", otype != "limit" or tick is None
            or abs(round(lp / tick) * tick - lp) < 1e-9, "tick %s" % tick)
        lot = L.lot_size.get(inst)
        put("lot_size", lot is None or abs(round(qty / lot) * lot - qty) < 1e-9, "lot %s" % lot)
        notional = qty * px
        put("order_notional", notional <= L.max_order_notional,
            "%.2f (max %.2f)" % (notional, L.max_order_notional))
        day = now.date().isoformat()
        used = self._daily_notional.get((acct, day), 0.0)
        put("daily_notional", used + notional <= L.max_daily_notional,
            "%.2f + %.2f (max %.2f)" % (used, notional, L.max_daily_notional))
        pos = self.positions(acct).get(inst, 0.0)
        new_pos = pos + (qty if buying else -qty)
        put("position_size", abs(new_pos) <= L.max_position_qty,
            "|%.4g| (max %.4g)" % (new_pos, L.max_position_qty))
        short = side == "sell_short" or (side == "sell" and new_pos < -1e-12)
        put("short_sale", L.allow_short or not short,
            "short sale" + (" allowed" if L.allow_short else " not allowed"))
        equity = self._equity(acct, q)
        put("buying_power", not buying or notional + self.venue.fee_per_order <= self.cash[acct],
            "cash %.2f" % self.cash[acct])
        gross = abs(new_pos) * q.last
        put("leverage", equity > 0 and gross / equity <= L.max_leverage,
            "%.2fx (max %.2fx)" % (gross / equity if equity > 0 else float("inf"), L.max_leverage))
        put("concentration", equity > 0 and abs(new_pos) * q.last / equity * 100 <= L.max_concentration_pct,
            "%.1f%% of equity (max %.1f%%)" % (abs(new_pos) * q.last / equity * 100 if equity > 0 else 1e9,
                                               L.max_concentration_pct))
        loss = self.start_equity[acct] - equity
        put("daily_loss", loss < L.max_daily_loss, "%.2f (max %.2f)" % (loss, L.max_daily_loss))
        recent = [t for t in self._submits if (now - t).total_seconds() < 60]
        put("order_rate", len(recent) < L.max_orders_per_minute,
            "%d in the last minute (max %d)" % (len(recent), L.max_orders_per_minute))
        dup = any(o["client_order_id"] == coid and o["account_id"] == acct
                  for o in self.orders.values())
        put("duplicate_order", not dup, "client_order_id %s %s" % (coid, "already used" if dup else "new"))
        return c

    # -- SS.6.2 Phase B -----------------------------------------------------
    def commit(self, preview_id, confirmation_token, idempotency_key, principal,
               quote: QuoteSnapshot, now=None) -> Dict[str, Any]:
        now = _utc(now)
        with self._lock:
            try:
                return self._commit(preview_id, confirmation_token, idempotency_key,
                                    principal, quote, now)
            except PaperError as exc:
                self.audit.write("commit_refused", now, preview_id=str(preview_id),
                                 principal=str(principal), reason=str(exc)[:300])
                raise

    def _commit(self, preview_id, token, idem_key, principal, quote, now):
        if principal != "HUMAN":
            raise PaperError("a commit must be confirmed by a HUMAN; %r may draft and "
                             "preview, never confirm (SS.5.6, SS.6.5)" % (principal,))
        try:
            require("submit_paper_order")
        except ExecutionModeError as exc:
            raise PaperError("paper submission is not enabled: %s" % exc)
        if not isinstance(idem_key, str) or not idem_key.strip():
            raise PaperError("an idempotency key is required (SS.6.3)")
        pv = self._previews.get(preview_id)
        if pv is None:
            raise PaperError("unknown preview %r: a commit must reference an exact "
                             "preview" % (preview_id,))
        existing = self.idem.lookup(idem_key, pv["content"])
        if existing is not None:
            # A retry of the SAME order: return it, submit nothing.
            return dict(self.orders[existing], idempotent_replay=True)
        if not pv["ok"]:
            raise PaperError("the preview's risk check was REFUSE; no token was issued")
        if pv["used"]:
            raise PaperError("this preview was already committed (tokens are single-use)")
        if not isinstance(token, str) or pv["token_hash"] is None or \
                not hmac.compare_digest(_sha(token), pv["token_hash"]):
            raise PaperError("confirmation token does not match the preview")
        acct = pv["order"]["account_id"]
        # -- SS.6.2 invalidation list ----------------------------------------
        if now > pv["expiry"]:
            raise PaperError("preview expired at %s" % _iso(pv["expiry"]))
        if self.kill.engaged():
            raise PaperError("kill switch is engaged")
        if pv["limits_version"] != self.limits.version:
            raise PaperError("risk limits changed since the preview")
        self._sync_fills()
        if pv["account_version"] != self._account_version[acct] or \
                pv["open_orders"] != self._open_orders(acct):
            raise PaperError("positions or open orders changed since the preview")
        if not isinstance(quote, QuoteSnapshot) or quote.instrument_id != pv["order"]["instrument_id"]:
            raise PaperError("a fresh quote for the previewed instrument is required")
        if (now - quote.timestamp).total_seconds() > self.limits.max_quote_age_s:
            raise PaperError("quote is stale at commit")
        if quote.market_status != pv["quote"].market_status or quote.market_status != "OPEN":
            raise PaperError("market status changed or is not OPEN (%s)" % quote.market_status)
        moved = abs(quote.last - pv["quote"].last) / pv["quote"].last * 100.0
        if moved > self.limits.price_deviation_pct:
            raise PaperError("price moved %.2f%% since the preview (max %.2f%%)"
                             % (moved, self.limits.price_deviation_pct))
        recent = [t for t in self._submits if (now - t).total_seconds() < 60]
        if len(recent) >= self.limits.max_orders_per_minute:
            raise PaperError("order-rate limit reached")
        coid = pv["order"]["client_order_id"]
        if any(x["client_order_id"] == coid and x["account_id"] == acct
               for x in self.orders.values()):
            # Checked AGAIN here: two previews taken before either commit would
            # both have passed the preview-time check.
            raise PaperError("duplicate client_order_id %r: already submitted" % coid)

        pv["used"] = True
        order_id = "ord_" + _sha(preview_id + idem_key)[:20]
        order = dict(pv["order"], order_id=order_id, preview_id=preview_id,
                     state="WAITING_FOR_CONFIRMATION",
                     history=["DRAFT", "PREVIEWED", "WAITING_FOR_CONFIRMATION"],
                     filled_qty=0.0, fees=0.0, venue_order_id=None)
        self.orders[order_id] = order
        self.idem.record(idem_key, pv["content"], order_id)
        self._submits.append(now)
        price = pv["order"]["limit_price"] or (quote.ask if pv["order"]["side"] in (
            "buy", "buy_to_cover") else quote.bid)
        day = now.date().isoformat()
        self._daily_notional[(acct, day)] = self._daily_notional.get((acct, day), 0.0) + \
            pv["order"]["quantity"] * price
        ticket = hmac.new(self._ticket_key, json.dumps(pv["order"], sort_keys=True)
                          .encode("utf-8"), hashlib.sha256).hexdigest()
        try:
            resp = self.venue.submit(pv["order"], ticket, quote, now)
        except VenueDisconnected as exc:
            self._set_state(order, "UNKNOWN")
            self.audit.write("submit_unknown", now, order_id=order_id,
                             preview_id=preview_id, principal=principal,
                             idempotency_key_hash=_sha(idem_key)[:16], reason=str(exc))
            # No automatic retry (SS.5.6): reconcile() resolves it.
            return dict(order)
        self._apply_venue_response(order, resp, now)
        self.audit.write("submitted", now, order_id=order_id, preview_id=preview_id,
                         principal=principal, venue_order_id=resp["venue_order_id"],
                         state=order["state"], idempotency_key_hash=_sha(idem_key)[:16])
        return dict(order)

    def _apply_venue_response(self, order, resp, now):
        if order["state"] == "WAITING_FOR_CONFIRMATION":
            self._set_state(order, "SUBMITTED", venue_response=True)
        order["venue_order_id"] = resp["venue_order_id"]
        target = resp["status"]
        if order["state"] == "SUBMITTED" and target != "REJECTED":
            self._set_state(order, "ACKNOWLEDGED", venue_response=True)
        if target != order["state"] and target != "ACKNOWLEDGED":
            self._set_state(order, target, venue_response=True)
        order["venue_reason"] = resp.get("reason", "")
        self._sync_fills()

    # -- after commit ---------------------------------------------------------
    def cancel(self, order_id, principal, now=None) -> Dict[str, Any]:
        now = _utc(now)
        with self._lock:
            o = self.orders.get(order_id)
            if o is None:
                raise PaperError("unknown order %r" % (order_id,))
            if principal not in PRINCIPALS:
                raise PaperError("unknown principal %r" % (principal,))
            if o["state"] not in ("ACKNOWLEDGED", "PARTIALLY_FILLED"):
                raise PaperError("cannot cancel an order in state %s" % o["state"])
            self._set_state(o, "CANCEL_PENDING")
            try:
                resp = self.venue.cancel(o["venue_order_id"])
            except VenueDisconnected:
                self._set_state(o, "UNKNOWN")
                self.audit.write("cancel_unknown", now, order_id=order_id, principal=principal)
                return dict(o)
            self._apply_venue_response(o, resp, now)
            self.audit.write("cancel", now, order_id=order_id, principal=principal,
                             state=o["state"])
            return dict(o)

    def on_quote(self, quote: QuoteSnapshot, now=None) -> None:
        now = _utc(now)
        with self._lock:
            for resp in self.venue.tick(quote, now):
                for o in self.orders.values():
                    if o.get("venue_order_id") == resp["venue_order_id"] and \
                            o["state"] != resp["status"]:
                        self._apply_venue_response(o, resp, now)

    def reconcile(self, now=None) -> Dict[str, Any]:
        """
        Resolve UNKNOWN orders from the venue, then compare positions, filled
        quantities and cash. A mismatch is reported AND audited, and the kill
        switch is engaged: trading on a ledger that disagrees with the venue is
        the failure reconciliation exists to stop.
        """
        now = _utc(now)
        with self._lock:
            resolved, problems = [], []
            for o in self.orders.values():
                if o["state"] != "UNKNOWN":
                    continue
                try:
                    resp = self.venue.query(client_order_id=o["client_order_id"])
                except VenueDisconnected:
                    problems.append("%s still UNKNOWN: venue unreachable" % o["order_id"])
                    continue
                if resp is None:
                    # The venue answered and has no record: a VERIFIED absence,
                    # so REJECTED is a venue response, not a guess.
                    self._set_state(o, "REJECTED", venue_response=True)
                    o["venue_reason"] = "venue has no record (never received)"
                else:
                    o["venue_order_id"] = resp["venue_order_id"]
                    self._set_state(o, resp["status"], venue_response=True)
                resolved.append(o["order_id"])
            self._sync_fills()
            for o in self.orders.values():
                if o.get("venue_order_id"):
                    try:
                        v = self.venue.query(venue_order_id=o["venue_order_id"])
                    except VenueDisconnected:
                        problems.append("venue unreachable during reconciliation")
                        break
                    if v and abs(v["filled_qty"] - o["filled_qty"]) > 1e-9:
                        problems.append("%s filled %g here vs %g at venue"
                                        % (o["order_id"], o["filled_qty"], v["filled_qty"]))
            for acct in self.cash:
                mine = self.positions(acct)
                theirs = self.venue.positions(acct)
                for inst in set(mine) | set(theirs):
                    if abs(mine.get(inst, 0.0) - theirs.get(inst, 0.0)) > 1e-9:
                        problems.append("%s %s position %g here vs %g at venue"
                                        % (acct, inst, mine.get(inst, 0.0), theirs.get(inst, 0.0)))
                exp = self.start_equity[acct] + sum(
                    (1.0 if f["side"] not in ("buy", "buy_to_cover") else -1.0) * f["qty"] * f["price"] - f["fee"]
                    for f in self.venue.fills if f["account_id"] == acct)
                if abs(exp - self.cash[acct]) > 1e-6:
                    problems.append("%s cash %.6f here vs %.6f from venue fills"
                                    % (acct, self.cash[acct], exp))
            ok = not problems
            aud = self.audit.write("reconcile", now, ok=ok, resolved=resolved,
                                   problems=problems[:20])
            if not ok:
                self.kill.engage("AUTOMATION", "reconciliation failure", now)
            return {"ok": ok, "resolved_unknown": resolved, "problems": problems,
                    "audit_event_id": aud, "kill_switch_engaged": self.kill.engaged()}

    def manifest(self) -> Dict[str, Any]:
        return {"module": "execution.paper", "environment": ENVIRONMENT,
                "accounts": sorted(self.cash), "limits_version": self.limits.version,
                "kill_switch_engaged": self.kill.engaged(),
                "audit_records": self.audit.verify()[1],
                "can_submit_live": False,
                "live_refused_by": ["environment != PAPER", "LIVE- account prefix",
                                    "mode capability submit_paper_order only",
                                    "venue accepts engine-signed tickets only"]}
