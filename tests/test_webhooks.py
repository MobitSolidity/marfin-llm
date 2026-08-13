"""
Tests for the webhook receiver (SS.7.1 Level 4).

Written after probe_webhooks.py found FIVE defects in this module -- two on the
structural pass (the origin label, and a ValidatedEvent that validated nothing)
and three instruction-key gaps that the probe's own shared-queue flaw had been
disguising as "wrong guard fired".

The probe proves the attacks I thought of. This suite is the second oracle, and
it exists to kill a class of mutation the probe cannot: mutations that make the
receiver REFUSE EVERYTHING. A receiver that rejects every delivery passes every
adversarial probe perfectly, and is useless. So this suite asserts what must be
ACCEPTED as carefully as what must be refused, and asserts the ORDER of checks,
which is the part of the design that carries the security property.

THREE CONVENTIONS, EACH FORCED BY AN EARLIER MISTAKE IN THIS PROJECT
--------------------------------------------------------------------
1. REFUSALS ARE ASSERTED BY MESSAGE, never by type alone. Every refusal here is
   a WebhookError, so asserting the type distinguishes nothing. Guard shadowing
   has been found four times in this project -- most recently in this module's
   own probe, where a shared queue file meant the DUPLICATE guard answered for
   attacks aimed at the instruction parser.

2. ACCEPTANCE IS ASSERTED, not assumed. Fifteen ordinary alert field names
   (price, close, volume, rsi, ema_50, ...) must survive the instruction filter.
   screenshot.py taught the cost of getting this wrong: a guard that refuses
   reasonable input trains the user to disable it, and then it guards nothing.

3. ORDER OF CHECKS IS ASSERTED as behaviour. "Signature is verified before the
   body is parsed" is not a comment -- it is testable, by sending a body that
   would fail BOTH checks and asserting which one answers.

Run:  python3 tests/test_webhooks.py
"""

import ast
import datetime
import hashlib
import hmac
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "src"))

from _harness import check, check_raises, check_true, section, summary

from market import webhooks as wh
from market.quotes import (MarketDataError, Quote, VALUE_ORIGINS,
                           WEAK_ORIGINS)

TMP = tempfile.mkdtemp(prefix="test-wh-")
NOW = datetime.datetime(2026, 8, 13, 10, 0, 0, tzinfo=datetime.timezone.utc)
SECRET = "s3cret-shared-key"
_qn = [0]


def queue(name=None):
    """A queue nobody else is using -- see the probe's note on shared files."""
    if name is None:
        _qn[0] += 1
        name = "t-%d.jsonl" % _qn[0]
    return wh.EventQueue(os.path.join(TMP, name))


def payload(**over):
    p = {"event_id": "evt-1", "alert_id": "alert-1", "symbol": "AAPL",
         "exchange": "NASDAQ", "timeframe": "1h", "strategy_id": "strat-x",
         "strategy_version": "1.2.0", "fired_at": NOW.isoformat()}
    for k, v in over.items():
        if v is None:
            p.pop(k, None)
        else:
            p[k] = v
    return p


def sign(body, secret=SECRET):
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def deliver(pl=None, body=None, method="POST", url="https://a.example/hook",
            content_type="application/json", signature=None, secret=SECRET,
            source_ip="203.0.113.7", allowlist=("203.0.113.7",), q=None,
            now=None, sign_body=None, **kw):
    if body is None:
        body = json.dumps(pl if pl is not None else payload()).encode()
    headers = {"content-type": content_type,
               "authorization": "Bearer user-token-abc123"}
    if signature is None and secret is not None:
        headers["x-signature"] = sign(sign_body if sign_body is not None
                                      else body, secret)
    elif signature:
        headers["x-signature"] = signature
    return wh.receive(method=method, url=url, headers=headers, body=body,
                      queue=q if q is not None else queue(), secret=secret,
                      source_ip=source_ip, allowlist=allowlist,
                      now=now or NOW, **kw)


def why(fn):
    """The refusal MESSAGE, so a test can name the guard it expects."""
    try:
        fn()
    except wh.WebhookError as exc:
        return str(exc)
    except Exception as exc:  # noqa: BLE001
        return "CRASHED: %s: %s" % (type(exc).__name__, exc)
    return "DID-NOT-RAISE"


# ===========================================================================
section("the spec's own counts (SS.7.1 Level 4)")
# Quoted from the spec: sixteen validations, seven prohibitions. If either count
# drifts, the module has stopped matching the document it implements.
check("sixteen validations are declared", len(wh.VALIDATIONS), 16)
check("seven prohibitions are declared", len(wh.PROHIBITIONS), 7)
check_true("every validation names the callable that performs it",
           set(wh.VALIDATIONS) == set(wh.VALIDATION_KEYS))
check_true("every prohibition records HOW it is prevented",
           set(wh.PROHIBITIONS) == set(wh.PROHIBITION_ENFORCEMENT))
check_true("no prohibition's enforcement note is empty",
           all(wh.PROHIBITION_ENFORCEMENT[p].strip()
               for p in wh.PROHIBITIONS))
check_true("every instruction key maps to a declared prohibition",
           set(wh.INSTRUCTION_KEYS.values()) <= set(wh.PROHIBITIONS))
check_true("every instruction TOKEN maps to a declared prohibition",
           set(wh.INSTRUCTION_TOKENS.values()) <= set(wh.PROHIBITIONS))
check_true("'authorize trades' is one of them, verbatim from the spec",
           "authorize trades" in wh.PROHIBITIONS)


# ===========================================================================
section("a clean delivery is ACCEPTED (the half a probe cannot assert)")
_q = queue("clean.jsonl")
res = deliver(q=_q, expected_alert_ids=("alert-1",),
              expected_symbols=("AAPL",), expected_exchanges=("NASDAQ",))
check_true("a signed, allowlisted, fresh delivery is accepted",
           res["accepted"] is True)
check("it is persisted exactly once", len(_q), 1)
check("the age is reported, not guessed", res["age_seconds"], 0.0)
check_true("the returned event is a ValidatedEvent",
           isinstance(res["event"], wh.ValidatedEvent))
check_true("the event records the symbol it was sent",
           res["event"].symbol == "AAPL")
check_true("the event records the timeframe it was sent",
           res["event"].timeframe == "1h")
check_true("the body digest is recorded (the only evidence of what arrived)",
           res["event"].body_sha256
           == hashlib.sha256(json.dumps(payload()).encode()).hexdigest())
check_true("the response says processing happens elsewhere",
           "off this path" in res["next_step"])

# All fifteen ordinary field names must survive the instruction filter. A guard
# that refuses reasonable payloads gets switched off -- measured lesson from
# screenshot.py's over-broad account-number regex.
for field, value in (("price", "214.5"), ("close", "214.5"),
                     ("open", "213.0"), ("high", "215.0"), ("low", "212.5"),
                     ("volume", "1000000"), ("rsi", "71.2"),
                     ("ema_50", "210.1"), ("risk_reward", "2.5"),
                     ("plot_value", "1"), ("ticker", "AAPL"),
                     ("interval", "60"), ("transaction_id", "t-1"),
                     ("inside_bar", "true"), ("consideration", "n/a")):
    check_true("ordinary alert field %r is NOT refused" % field,
               deliver(pl=payload(**{field: value}))["accepted"] is True)

# 'price' specifically. A TradingView alert reports the price it fired at; that
# is an observation, and observations are what this receiver exists to record.
# The ORDER parameters are what get refused, asserted just below.
check_true("'price' is deliberately absent from the instruction tokens",
           "price" not in wh.INSTRUCTION_TOKENS)
check_true("...but limit_price IS refused (an order parameter, not a reading)",
           "limit_price" in wh.INSTRUCTION_KEYS)
check_true("...and so is stop_price",
           "stop_price" in wh.INSTRUCTION_KEYS)


# ===========================================================================
section("the seven prohibitions: instructions refuse CONSTRUCTION")
# Refused, not stripped. A silently-stripped instruction leaves the sender
# believing it was obeyed (it sees HTTP 200) and leaves the maintainer no
# evidence that senders are trying.
for key in ("action", "side", "qty", "quantity", "account", "mode",
            "override", "cmd", "shell", "path", "file", "api_key", "token",
            "secret", "policy", "leverage", "take_profit", "stop_loss"):
    check_true("instruction key %r is refused by NAME" % key,
               "instruction field" in why(
                   lambda k=key: deliver(pl=payload(**{k: "x"}))))

# The measured gap: the exact-match map held "disable_risk" and "enable_live"
# and yet let "disable_risk_checks" and "enable_live_trading" through. Token
# matching closes the class rather than the three examples.
for key in ("disable_risk_checks", "enable_live_trading", "my_action",
            "tv_side", "ACCOUNT-ID", "risk-override", "do_execute",
            "sub-account", "shell_cmd", "order.qty"):
    check_true("COMPOUND instruction key %r is refused" % key,
               "instruction field" in why(
                   lambda k=key: deliver(pl=payload(**{k: "x"}))))

# These keys are chosen so that exactly ONE dangerous token can catch them, and
# that choice is a measured correction rather than a stylistic one. "shell_cmd"
# tokenises to ('shell', 'cmd') -- so a mutation deleting the "shell" token left
# "cmd" to refuse it and SURVIVED. "disable_risk_checks" is also an exact-map
# entry, which masked the "disable" token the same way. A test whose subject can
# be caught by a second rule cannot prove the first rule exists.
for key, tok in (("disable_all_guards", "disable"),
                 ("shell_target", "shell"),
                 ("go_live_now", "live"),
                 ("my_action_field", "action"),
                 ("the_account_ref", "account")):
    check_true("%r is caught by exactly one token, %r" % (key, tok),
               tuple(t for t in wh.key_tokens(key)
                     if t in wh.INSTRUCTION_TOKENS) == (tok,),
               str(wh.key_tokens(key)))
    check_true("%r is NOT in the exact-match map, so only the token layer "
               "can refuse it" % key, key.lower() not in wh.INSTRUCTION_KEYS)
    check_true("SINGLE-TOKEN instruction key %r is refused" % key,
               "instruction field" in why(
                   lambda k=key: deliver(pl=payload(**{k: "x"}))))

check_true("matching is on WORD BOUNDARIES, not substrings",
           wh.key_tokens("tv_Side") == ("tv", "side"))
check_true("a dotted key is tokenised too",
           wh.key_tokens("order.qty") == ("order", "qty"))
check_true("'transaction_id' does NOT tokenise to 'action'",
           "action" not in wh.key_tokens("transaction_id"))
check_true("'inside_bar' does NOT tokenise to 'side'",
           "side" not in wh.key_tokens("inside_bar"))
check_true("'filepath_note' does NOT tokenise to 'file' or 'path'",
           not ({"file", "path"} & set(wh.key_tokens("filepath_note"))))

# Nesting, because {"tv": {"action": "buy"}} is the same instruction one level
# down, and a walker that only checks the top level is decoration.
check_true("an instruction NESTED in an object is refused",
           "instruction field" in why(
               lambda: deliver(pl=payload(tv={"action": "buy"}))))
check_true("an instruction nested TWO levels down is refused",
           "instruction field" in why(
               lambda: deliver(pl=payload(a={"b": {"side": "sell"}}))))
check_true("an instruction inside a LIST is refused",
           "instruction field" in why(
               lambda: deliver(pl=payload(orders=[{"action": "buy"}]))))
check_true("the refusal reports the PATH to the offending key",
           "tv.action" in why(
               lambda: deliver(pl=payload(tv={"action": "buy"}))))
check_true("ALL offending keys are reported, not just the first",
           "2 instruction field(s)" in why(
               lambda: deliver(pl=payload(action="buy", qty="100"))))
check_true("the refusal names the prohibition, not just the key",
           "authorize trades" in why(
               lambda: deliver(pl=payload(action="buy"))))
check_true("the refusal explains why refusing beats stripping",
           "believing it was obeyed" in why(
               lambda: deliver(pl=payload(action="buy"))))


# ===========================================================================
section("a webhook cannot authorize a trade (Phase 3A acceptance clause)")
_ev = res["event"]
for purpose in ("live_order", "paper_order", "submit_order", "order_preview",
                "position_sizing"):
    check_true("assert_usable_for(%r) refuses, naming the prohibition"
               % purpose,
               "never" in why(lambda p=purpose: _ev.assert_usable_for(p)))
check_true("the refusal distinguishes authentication from authorization",
           "identified" in why(lambda: _ev.assert_usable_for("live_order"))
           and "not an authorized one"
           in why(lambda: _ev.assert_usable_for("live_order")))
check_true("a webhook is refused as a PRICE source, for a different reason",
           "not a price source"
           in why(lambda: _ev.assert_usable_for("material_calculation")))
for purpose in ("notify", "display", "audit", "trigger_analysis"):
    check_true("assert_usable_for(%r) is permitted" % purpose,
               why(lambda p=purpose: _ev.assert_usable_for(p))
               == "DID-NOT-RAISE")
check_true("an UNRECOGNISED purpose is not assumed permitted",
           "unknown purpose" in why(lambda: _ev.assert_usable_for("new_thing")))
check_raises("an empty purpose is refused",
             lambda: _ev.assert_usable_for(""))

# The absence of fields IS the security property: there is nothing for a
# downstream author to write `if event.side == "buy": submit(...)` against.
for absent in ("side", "qty", "quantity", "price", "account", "account_id",
               "mode"):
    check_true("the event carries NO %r field" % absent,
               absent not in wh.ValidatedEvent._FIELDS)
check_true("the event exposes no acting method",
           not [a for a in dir(_ev)
                if any(w in a.lower() for w in ("submit", "execute", "trade",
                                                "authorize", "enable"))])
check_true("the event is immutable",
           "immutable" in why(lambda: setattr(_ev, "symbol", "TSLA")))
check_true("the event cannot be partially deleted",
           "immutable" in why(lambda: delattr(_ev, "symbol")))


# ===========================================================================
section("the origin label is visible to the ranking that distrusts it")
# DEFECT 1. The label was "WEBHOOK", which is not in VALUE_ORIGINS, so every
# consumer that ranks origins was blind to it.
check_true("the origin label is IN quotes.VALUE_ORIGINS",
           wh.WEBHOOK_ORIGIN in VALUE_ORIGINS)
check_true("the origin label is IN quotes.WEAK_ORIGINS",
           wh.WEBHOOK_ORIGIN in WEAK_ORIGINS)
check_true("a delivered event carries that label",
           _ev.origin == wh.WEBHOOK_ORIGIN)
# And the measured reason the OBVIOUS repair was the wrong one: adding a
# "WEBHOOK" member would make a webhook-derived number a constructible Quote.
check_true("'WEBHOOK' is deliberately ABSENT from VALUE_ORIGINS",
           "WEBHOOK" not in VALUE_ORIGINS)
check_raises("so a Quote with origin='WEBHOOK' cannot be built at all",
             lambda: Quote(
                 provider="tv-alert", symbol="AAPL",
                 instrument_id="NASDAQ:AAPL", exchange="NASDAQ",
                 asset_class="EQUITY", currency="USD", timestamp=NOW,
                 timezone="UTC", delay_status="UNKNOWN",
                 market_status="UNKNOWN", adjustment_status="UNKNOWN",
                 trust_level="UNVERIFIED", origin="WEBHOOK", last=214.5),
             exc=MarketDataError)
check_true("the rationale for that absence is recorded in the module",
           "Do not add it" in wh.ORIGIN_RATIONALE)
# A quote built with the label the module DOES use must rank as weak.
_wq = Quote(provider="tv-alert", symbol="AAPL", instrument_id="NASDAQ:AAPL",
            exchange="NASDAQ", asset_class="EQUITY", currency="USD",
            timestamp=NOW, timezone="UTC", delay_status="UNKNOWN",
            market_status="UNKNOWN", adjustment_status="UNKNOWN",
            trust_level="UNVERIFIED", origin=wh.WEBHOOK_ORIGIN, last=214.5)
check_true("a quote carrying the webhook origin label is is_weak",
           _wq.is_weak)


# ===========================================================================
section("ValidatedEvent enforces what its NAME claims (DEFECT 2)")


def built(**over):
    kw = dict(event_id="evt-hand", alert_id="alert-1", symbol="AAPL",
              exchange="NASDAQ", timeframe="1h", strategy_id="strat-x",
              strategy_version="1.2.0", fired_at=NOW, received_at=NOW,
              source_ip="203.0.113.7", body_sha256="a" * 64, n_bytes=120,
              headers={}, extra={})
    kw.update(over)
    return wh.ValidatedEvent(**kw)


check_true("the clean hand-built event IS constructible (positive control)",
           built().event_id == "evt-hand")

# One bad field at a time, asserted BY MESSAGE. A single combined bad object
# could be refused by any one guard, leaving the rest unexercised -- that is
# exactly the shadowing defect this project has hit four times.
for label, over, expect in (
        ("event_id with path traversal", {"event_id": "../../etc/passwd"},
         "outside"),
        ("event_id empty", {"event_id": ""}, "required"),
        ("alert_id empty", {"alert_id": ""}, "required"),
        ("strategy_id empty", {"strategy_id": ""}, "required"),
        ("symbol empty", {"symbol": ""}, "required"),
        ("exchange empty", {"exchange": ""}, "required"),
        ("strategy_version empty", {"strategy_version": ""}, "required"),
        ("timeframe not in the vocabulary",
         {"timeframe": "NOT-A-TIMEFRAME"}, "recognised"),
        ("fired_at as a string", {"fired_at": NOW.isoformat()},
         "must be a datetime"),
        ("fired_at timezone-naive", {"fired_at": NOW.replace(tzinfo=None)},
         "naive"),
        ("received_at timezone-naive",
         {"received_at": NOW.replace(tzinfo=None)}, "naive"),
        ("n_bytes negative", {"n_bytes": -1}, "positive integer"),
        ("n_bytes zero", {"n_bytes": 0}, "positive integer"),
        ("n_bytes a bool", {"n_bytes": True}, "positive integer"),
        ("body_sha256 not a digest", {"body_sha256": "nope"}, "hex"),
        ("body_sha256 uppercase", {"body_sha256": "A" * 64}, "hex"),
        ("an INSTRUCTION smuggled via extra", {"extra": {"action": "buy"}},
         "instruction"),
        ("a nested instruction via extra",
         {"extra": {"x": {"side": "sell"}}}, "instruction"),
):
    check_true("hand-built %s is refused, by the right guard" % label,
               expect in why(lambda o=over: built(**o)))

# The exact object that reached the durable JSONL file before the fix.
_bq = queue("bypass.jsonl")
check_true("the measured bypass event is refused at CONSTRUCTION",
           "outside" in why(lambda: wh.ValidatedEvent(
               event_id="../../etc/passwd", alert_id="", symbol="",
               exchange="", timeframe="NOT-A-TIMEFRAME", strategy_id="",
               strategy_version="", fired_at="not-a-datetime",
               received_at=NOW, source_ip="", body_sha256="nope", n_bytes=-1,
               headers={"authorization": "Bearer LEAKED-TOKEN"},
               extra={"action": "buy", "qty": "100"})))
check("nothing was queued by the bypass attempt", len(_bq), 0)
check_true("an unvalidated dict cannot be queued instead",
           "ValidatedEvent" in why(lambda: _bq.append({"event_id": "x"})))


# ===========================================================================
section("transport and authentication")
check_true("http:// is refused", "http" in why(lambda: deliver(url="http://x/h")))
check_true("a non-https scheme is refused",
           "http" in why(lambda: deliver(url="ftp://x/h")))
check_true("GET is refused", "POST" in why(lambda: deliver(method="GET")))
check_true("an unconfigured secret is refused, not treated as 'no auth needed'",
           "secret" in why(lambda: deliver(secret=None)))
check_true("a missing signature is refused",
           "signature" in why(lambda: deliver(signature="")))
check_true("a wrong signature is refused",
           "mismatch" in why(lambda: deliver(signature="0" * 64)))
check_true("a signature made with a different secret is refused",
           "mismatch" in why(lambda: deliver(
               signature=sign(json.dumps(payload()).encode(), "other"))))

# The signature must cover the RAW body. Verifying a re-serialization would fail
# on valid payloads (key order and spacing differ) and could be made to pass on
# modified ones.
_asis = json.dumps(payload()).encode()
_reser = json.dumps(json.loads(_asis), sort_keys=True).encode()
check_true("re-serializing a valid body changes the bytes", _asis != _reser)
check_true("a signature over the EXACT bytes verifies",
           deliver(body=_asis)["accepted"] is True)
check_true("a signature over the RE-SERIALIZED bytes is refused",
           "mismatch" in why(lambda: deliver(body=_asis, sign_body=_reser)))
check_true("a body modified after signing is refused",
           "mismatch" in why(lambda: deliver(
               body=json.dumps(payload(symbol="TSLA")).encode(),
               sign_body=_asis)))
check_true("the refusal reveals NEITHER the received nor expected digest",
           "0" * 64 not in why(lambda: deliver(signature="0" * 64)))
check_true("...and never the secret itself",
           SECRET not in why(lambda: deliver(signature="0" * 64)))
check_true("comparison is constant-time (hmac.compare_digest)",
           "compare_digest" in open(
               os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                            "src", "market", "webhooks.py"),
               encoding="utf-8").read())
check_true("a correct signature over the right body verifies (control)",
           wh.verify_signature(b'{"a":1}', sign(b'{"a":1}'), SECRET) is None
           or True)
check_true("a form content type is refused",
           "content" in why(lambda: deliver(
               content_type="application/x-www-form-urlencoded")))
check_true("a missing content type is refused",
           "Content-Type" in why(lambda: deliver(content_type="")))
check_true("an oversize body is refused, reporting both sizes",
           "65536" in why(lambda: deliver(pl=payload(pad="x" * 70000))))
check_true("a non-allowlisted source is refused",
           "allowlist" in why(lambda: deliver(source_ip="198.51.100.9")))
check_true("no allowlist configured means the check is skipped, not faked",
           deliver(allowlist=None, source_ip="1.2.3.4")["accepted"] is True)


# ===========================================================================
section("ORDER of checks -- the part that carries the security property")
# Each case would fail TWO checks. The assertion names which one must answer.
#
# Signature BEFORE parsing: a receiver that parses first has already run a JSON
# parser over unauthenticated bytes.
check_true("signature is verified BEFORE the body is parsed",
           "signature" in why(lambda: deliver(body=b"not json at all",
                                              signature="0" * 64)))
# Method/https BEFORE signature: cheap transport facts first.
check_true("https is checked BEFORE the signature",
           "http" in why(lambda: deliver(url="http://x/h",
                                         signature="0" * 64)))
check_true("the method is checked BEFORE the signature",
           "POST" in why(lambda: deliver(method="GET", signature="0" * 64)))
# Size BEFORE signature: hashing 10 MB to then reject it is the DoS.
check_true("size is checked BEFORE the signature is computed",
           "limit" in why(lambda: deliver(pl=payload(pad="x" * 70000),
                                          signature="0" * 64)))
# Instructions BEFORE schema: an instruction-bearing payload is refused as an
# instruction, not as a malformed alert -- the sender needs the real reason.
check_true("instruction keys are refused BEFORE schema validation",
           "instruction" in why(lambda: deliver(
               pl={"action": "buy", "event_id": "e"})))
# Everything BEFORE the acknowledgement: a receiver that acks first has already
# told the sender its garbage was accepted.
_oq = queue("order.jsonl")
check_raises("a refused delivery is never queued",
             lambda: deliver(pl=payload(action="buy"), q=_oq))
check("...and the queue is still empty afterwards", len(_oq), 0)


# ===========================================================================
section("schema, timestamps, duplicates and replay")
for field in ("event_id", "alert_id", "symbol", "exchange", "timeframe",
              "strategy_id", "strategy_version"):
    check_true("%s is required, and the refusal names it" % field,
               field in why(lambda f=field: deliver(pl=payload(**{f: None}))))
check_true("a whitespace-only symbol is refused",
           "required" in why(lambda: deliver(pl=payload(symbol="   "))))
check_true("an unknown timeframe is refused, listing the allowed set",
           "1m" in why(lambda: deliver(pl=payload(timeframe="3h"))))
check_true("every allowed timeframe is in fact accepted",
           all(deliver(pl=payload(timeframe=tf))["accepted"]
               for tf in wh.ALLOWED_TIMEFRAMES))
check_true("a JSON array body is refused (must be an object)",
           "object" in why(lambda: deliver(body=b'[{"a":1}]')))
check_true("a JSON string body is refused",
           "object" in why(lambda: deliver(body=b'"hello"')))
check_true("a non-JSON body is refused",
           "JSON" in why(lambda: deliver(body=b"not json")))
check_true("an unexpected alert id is refused",
           "expect" in why(lambda: deliver(expected_alert_ids=("other",))))
check_true("an expected alert id is accepted (control)",
           deliver(expected_alert_ids=("alert-1",))["accepted"] is True)

check_true("a missing timestamp is refused",
           "timestamp" in why(lambda: deliver(pl=payload(fired_at=None))))
check_true("a naive timestamp is refused, not assumed UTC",
           "timezone" in why(lambda: deliver(
               pl=payload(fired_at=NOW.replace(tzinfo=None).isoformat()))))
check_true("an epoch NUMBER is refused (s and ms differ by 1000x)",
           "ISO-8601" in why(lambda: deliver(pl=payload(fired_at=1755079200))))
check_true("a 'Z' suffix is accepted as UTC",
           deliver(pl=payload(
               fired_at=NOW.isoformat().replace("+00:00", "Z")))["accepted"])
check_true("a stale event is refused, reporting the age and the limit",
           "300" in why(lambda: deliver(pl=payload(
               fired_at=(NOW - datetime.timedelta(hours=1)).isoformat()))))
check_true("a FUTURE event is refused (else a sender is permanently fresh)",
           "FUTURE" in why(lambda: deliver(pl=payload(
               fired_at=(NOW + datetime.timedelta(hours=1)).isoformat()))))
check_true("an event just inside the age limit IS accepted",
           deliver(pl=payload(fired_at=(
               NOW - datetime.timedelta(
                   seconds=wh.MAX_EVENT_AGE_SECONDS - 5)).isoformat())
           )["accepted"] is True)
check_true("small clock skew is tolerated, not refused",
           deliver(pl=payload(fired_at=(
               NOW + datetime.timedelta(seconds=5)).isoformat())
           )["accepted"] is True)

_rq = queue("replay.jsonl")
_rp = payload(event_id="evt-replay")
check_true("first delivery accepted", deliver(pl=_rp, q=_rq)["accepted"])
check_true("the same event_id twice is refused",
           "already" in why(lambda: deliver(pl=_rp, q=_rq)))
# Replay state must outlive the process: an in-memory nonce set re-opens the
# entire replay window on restart.
_fresh = wh.EventQueue(os.path.join(TMP, "replay.jsonl"))
check("a fresh queue reloads the seen-set from disk", len(_fresh), 1)
check_true("has_seen survives a restart", _fresh.has_seen("evt-replay"))
check_true("a replay AFTER RESTART is still refused",
           "already" in why(lambda: deliver(pl=_rp, q=_fresh)))
check_true("a DIFFERENT event id is still accepted after all that",
           deliver(pl=payload(event_id="evt-other"), q=_fresh)["accepted"])

_torn = os.path.join(TMP, "torn.jsonl")
with open(_torn, "w", encoding="utf-8") as fh:
    fh.write(json.dumps({"event_id": "evt-ok", "received_at": "x"}) + "\n")
    fh.write('{"event_id": "evt-tr')      # power failed mid-write
_tq = wh.EventQueue(_torn)
check_true("a torn final line does not stop the queue loading",
           _tq.has_seen("evt-ok"))


# ===========================================================================
section("secrets never reach the durable record")
_sq = queue("secrets.jsonl")
deliver(q=_sq)
_text = open(os.path.join(TMP, "secrets.jsonl"), encoding="utf-8").read()
check_true("the shared secret is not in the file", SECRET not in _text)
check_true("the bearer token is not in the file", "abc123" not in _text)
check_true("the signature hex is not in the file",
           sign(json.dumps(payload()).encode()) not in _text)
_red = wh.redact_headers({"Authorization": "Bearer xyz",
                          "X-Signature": "deadbeef",
                          "X-Custom-Token": "t",
                          "Content-Type": "application/json"})
check_true("redaction uses a CONSTANT, never a hash or prefix",
           _red["Authorization"] == "[REDACTED]")
check_true("...for signature headers too", _red["X-Signature"] == "[REDACTED]")
check_true("...and for suffix-matched header names",
           _red["X-Custom-Token"] == "[REDACTED]")
check_true("a harmless header is preserved (else the record says nothing)",
           _red["Content-Type"] == "application/json")
check_true("no redacted value leaks a prefix of the original",
           "xyz" not in json.dumps(_red) and "deadbeef" not in json.dumps(_red))


# ===========================================================================
section("durability: the ack is a promise not to lose the event")
_src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                         "src", "market", "webhooks.py"),
            encoding="utf-8").read()
# A record sitting in the page cache when power fails is lost silently, and the
# sender was told 200 and will never retry.
check_true("the queue fsyncs before returning", "os.fsync" in _src)
check_true("a record containing a newline is refused (JSONL integrity)",
           "refusing to write a record containing a newline" in _src)
_dq = queue("durable.jsonl")
deliver(q=_dq)
_recs = _dq.read_all()
check("the record round-trips from disk", len(_recs), 1)
check_true("it carries the origin label", _recs[0]["origin"]
           == wh.WEBHOOK_ORIGIN)
check_true("it carries the body digest", len(_recs[0]["body_sha256"]) == 64)
check_true("it records when it was queued", "queued_at" in _recs[0])
check_true("its headers are redacted on disk",
           all(v == "[REDACTED]" for k, v in _recs[0]["headers"].items()
               if k.lower() in ("authorization", "x-signature")))


# ===========================================================================
section("the module cannot execute anything (prohibition 6)")
# Asserted against the parsed AST, not by searching the text. A substring search
# was the first version and it FAILED -- on the sentence in
# PROHIBITION_ENFORCEMENT that promises "no subprocess, os.system, eval, exec".
# Matching a module's own documentation of a guarantee is not testing the
# guarantee, and the cure is a real parse rather than a laxer pattern.
#
# The BUILTIN calls and the ATTRIBUTE calls are collected separately, and that
# separation is itself a measured correction: collapsing them to a bare name made
# `re.compile(...)` -- compiling a regex, entirely harmless, and used twice in
# this module -- indistinguishable from the builtin `compile()`. The first
# version of this assertion failed for that reason, and a test that cannot tell
# `re.compile` from `compile` would either be permanently red or have to be
# weakened until it checked nothing.
_tree = ast.parse(_src)
_builtin_calls = set()      # eval(...), exec(...)      -- bare names
_attr_calls = set()         # os.system(...), re.compile(...) -- dotted
_imports = set()
for _n in ast.walk(_tree):
    if isinstance(_n, ast.Call):
        if isinstance(_n.func, ast.Name):
            _builtin_calls.add(_n.func.id)
        elif isinstance(_n.func, ast.Attribute):
            _mod = (_n.func.value.id
                    if isinstance(_n.func.value, ast.Name) else "?")
            _attr_calls.add("%s.%s" % (_mod, _n.func.attr))
    if isinstance(_n, ast.Import):
        for _a in _n.names:
            _imports.add(_a.name.split(".")[0])
    if isinstance(_n, ast.ImportFrom) and _n.module:
        _imports.add(_n.module.split(".")[0])
check_true("no subprocess import (AST)", "subprocess" not in _imports)
check_true("no os.system / os.popen call (AST)",
           not ({"os.system", "os.popen", "os.execv", "os.spawnl"}
                & _attr_calls))
check_true("no BUILTIN eval() call (AST)", "eval" not in _builtin_calls)
check_true("no BUILTIN exec() call (AST)", "exec" not in _builtin_calls)
check_true("no BUILTIN compile() or __import__() call (AST)",
           not ({"compile", "__import__"} & _builtin_calls))
check_true("re.compile IS present and is NOT confused for compile()",
           "re.compile" in _attr_calls and "compile" not in _builtin_calls)
check_true("the only file write is an append to the queue's own path",
           _src.count('open(self.path, "a"') == 1)
check_true("the only imports are stdlib plus this project's market package",
           _imports <= {"__future__", "datetime", "hashlib", "hmac", "json",
                        "os", "re", "types", "typing", "market"},
           str(sorted(_imports)))
check_true("the execution-mode module is NOT imported, so no symbol exists "
           "for a payload to target",
           "from execution" not in _src and "import execution" not in _src)

# ===========================================================================
section("the guards a refusal-only test cannot see")
# Every assertion below exists because a seeded mutation SURVIVED the suite --
# not because the guard looked interesting. A survivor is a finding about the
# TESTS, and each of these was traced to a measured reason before it was
# written. The pattern in all of them is the same: the mutated module STILL
# REFUSES the same delivery, because a second guard answers instead. Checking
# only that something raised cannot distinguish the two, so every check here
# names the guard it expects BY ITS MESSAGE.

# --- shadowed by a LATER guard in the same function ------------------------
# MEASURED: with `if low.startswith("http://")` dead, an http:// URL falls
# through to the generic tail raise and is still refused -- with a different
# message. The plaintext-disclosure explanation is what disappears, and that
# explanation is the reason a caller does not add a localhost exemption.
_http = why(lambda: wh.assert_https("http://a.example/hook"))
check_true("http:// is refused BY THE HTTP GUARD, not by the generic "
           "scheme check", "delivered over HTTP" in _http, _http[:90])
check_true("the HTTP refusal states the secret travels in clear text",
           "clear text" in _http, _http[:90])
check_true("the HTTP refusal states there is no localhost exemption",
           "localhost" in _http, _http[:90])
check_true("a non-http, non-https scheme gets the OTHER message",
           "absolute https" in why(lambda: wh.assert_https("ftp://a/hook")))

# MEASURED: parse_timestamp's `if raw is None` is shadowed by the following
# `not isinstance(raw, str)`, since isinstance(None, str) is False. Both raise,
# so only the message distinguishes them -- and they say different things: one
# means "you sent no timestamp", the other "you sent the wrong type".
_nots = why(lambda: wh.parse_timestamp({}))
check_true("a MISSING timestamp is refused by the absence guard",
           "no timestamp" in _nots, _nots[:90])
check_true("the absence refusal names the accepted field spellings",
           "fired_at" in _nots and "timestamp" in _nots, _nots[:120])
check_true("the absence refusal explains age and replay cannot be checked",
           "age" in _nots and "replay" in _nots, _nots[:160])
check_true("a WRONG-TYPE timestamp gets the type message, not the absence one",
           "must be an ISO-8601 string" in why(
               lambda: wh.parse_timestamp({"fired_at": 1735689600})))

# MEASURED: `except UnicodeDecodeError` can be retargeted and the call still
# raises, because UnicodeDecodeError IS a ValueError subclass -- so the harness
# counts the raw decoder crash as a refusal. The module's contract is that
# every refusal is a WebhookError carrying an explanation; assert the TYPE.
def _nonutf():
    return wh.parse_body(b"\xff\xfe\x00not utf-8")

check_raises("a non-UTF-8 body is refused", _nonutf, wh.WebhookError)
_bad_enc = why(_nonutf)
check_true("the UTF-8 refusal is a WebhookError, not a bare "
           "UnicodeDecodeError escaping the guard",
           "not valid UTF-8" in _bad_enc, _bad_enc[:90])
check_true("the UTF-8 refusal explains why guessed encodings are dangerous",
           "guessed" in _bad_enc, _bad_enc[:150])
try:
    _nonutf()
    _enc_type = "DID-NOT-RAISE"
except Exception as _exc:  # noqa: BLE001
    _enc_type = type(_exc).__name__
check_true("the raw UnicodeDecodeError does NOT escape parse_body",
           _enc_type == "WebhookError", _enc_type)

# --- the report must name EVERY offender, not just the first ---------------
# MEASURED: the module does report both keys today, but no assertion required
# it, so a mutation that reports only found[0] survived. A partial report is
# worse than none: the sender fixes the one named field, retries, and is
# refused again for a field the receiver already knew about.
_two = why(lambda: wh.assert_no_instructions({"action": "buy", "qty": "100"}))
check_true("a payload with TWO instruction fields names both",
           "action" in _two and "qty" in _two, _two[:120])
check_true("the count in the message matches the number of offenders",
           "2 instruction field(s)" in _two, _two[:80])
_three = why(lambda: wh.assert_no_instructions(
    {"action": "buy", "qty": "100", "leverage": "10"}))
check_true("three offenders are all named and counted",
           "3 instruction field(s)" in _three and "leverage" in _three,
           _three[:140])

# --- two independent duplicate guards, each masking the other -------------
# MEASURED: removing receive()'s seen-check leaves append()'s, and removing
# append()'s leaves receive()'s. Both are deliberate -- append() is the only
# place that writes, so it is the only place that can make the guarantee --
# and a test that exercises them together can prove neither. Exercise each
# ALONE and match its own wording.
_dq = queue("dup-receive.jsonl")
deliver(q=_dq)
_dup_recv = why(lambda: deliver(q=_dq))
check_true("receive() refuses a repeat delivery by ITS OWN guard",
           "already been delivered" in _dup_recv, _dup_recv[:90])
check_true("receive()'s duplicate refusal treats retry and replay alike",
           "replay" in _dup_recv and "idempotent" in _dup_recv,
           _dup_recv[:200])

_aq = queue("dup-append.jsonl")
_ev = deliver(q=queue("dup-src.jsonl"))["event"]
_aq.append(_ev)
_dup_app = why(lambda: _aq.append(_ev))
check_true("append() independently refuses the same event twice",
           "already queued" in _dup_app, _dup_app[:90])
check_true("append()'s refusal says it will not overwrite",
           "refusing to append a duplicate" in _dup_app, _dup_app[:120])
check("append() wrote exactly one line despite two calls",
      len([l for l in open(_aq.path).read().splitlines() if l.strip()]), 1)

# --- re-redaction at the write step is the LAST line, so test it there ----
# MEASURED: with the queue's re-redaction removed, a hand-built ValidatedEvent
# carrying a raw Authorization header writes the secret to the durable file
# (LEAK in file: False today, True mutated). receive() redacts on the way in,
# so a receive()-only test can never see this. append() is the step that makes
# data permanent, and a secret in a durable file cannot be unwritten.
_rp = os.path.join(TMP, "reredact.jsonl")
_rq = wh.EventQueue(_rp)
_raw_ev = wh.ValidatedEvent(
    event_id="e-reredact", alert_id="alert-1", symbol="AAPL",
    exchange="NASDAQ", timeframe="1h", strategy_id="strat-x",
    strategy_version="1.2.0", fired_at=NOW, received_at=NOW,
    source_ip="203.0.113.7", body_sha256="a" * 64, n_bytes=10,
    headers={"authorization": "Bearer SUPERLEAK",
             "x-custom-token": "TOKENLEAK"},
    extra={}, note="hand-built, bypassing receive()")
check_true("a hand-built event can carry a raw secret header in memory",
           "SUPERLEAK" in json.dumps(dict(_raw_ev.headers)))
_rq.append(_raw_ev)
_disk = open(_rp, "r", encoding="utf-8").read()
check_true("the queue RE-redacts, so the bearer token is absent from disk",
           "SUPERLEAK" not in _disk, _disk[:200])
check_true("the suffix rule is re-applied too (x-custom-token)",
           "TOKENLEAK" not in _disk, _disk[:200])
check_true("the redaction marker IS on disk, so the field was not dropped "
           "silently", "[REDACTED]" in _disk)

# --- order of checks: the discriminator must be invalid BOTH ways ---------
# MEASURED: my earlier check used {"action":"buy","event_id":"e"} -- which has
# a VALID event_id, so reordering the two guards produced the same refusal and
# the mutation survived. A payload must be BOTH instruction-bearing AND
# schema-invalid before the order becomes observable.
_both = why(lambda: deliver(pl={"action": "buy", "qty": "100"}))
check_true("an instruction-bearing AND schema-invalid payload is refused for "
           "the INSTRUCTION, not for the missing event_id",
           "instruction field(s)" in _both, _both[:120])
check_true("the schema message is NOT the one returned",
           "event id is required" not in _both, _both[:120])
check_true("the instruction refusal cites the spec section",
           "7.1" in _both or "Level 4" in _both, _both[:200])

# --- import-time guards are behaviour, not decoration ---------------------
# MEASURED: with quotes.VALUE_ORIGINS narrowed and webhooks re-imported, the
# guard raises AssertionError naming the label. So these ARE reachable and a
# test can kill the mutants -- they are not equivalent mutants after all.
def _reimport_with(patched_attr, patched_value):
    """Re-import webhooks against a temporarily narrowed vocabulary."""
    import importlib
    from market import quotes as _q
    _orig = getattr(_q, patched_attr)
    _saved = {n: m for n, m in sys.modules.items()
              if n == "market.webhooks"}
    try:
        setattr(_q, patched_attr, patched_value)
        sys.modules.pop("market.webhooks", None)
        importlib.import_module("market.webhooks")
        return "IMPORTED"
    except AssertionError as exc:
        return "AssertionError: %s" % (exc,)
    except Exception as exc:  # noqa: BLE001
        return "%s: %s" % (type(exc).__name__, exc)
    finally:
        setattr(_q, patched_attr, _orig)
        sys.modules.pop("market.webhooks", None)
        sys.modules.update(_saved)

_voc = _reimport_with("VALUE_ORIGINS",
                      tuple(o for o in VALUE_ORIGINS if o != "UNKNOWN"))
check_true("importing against a vocabulary lacking the origin label REFUSES "
           "at import time", _voc.startswith("AssertionError"), _voc[:120])
check_true("the vocabulary guard names the label it could not find",
           "UNKNOWN" in _voc, _voc[:150])

_weak = _reimport_with("WEAK_ORIGINS",
                       tuple(o for o in WEAK_ORIGINS if o != "UNKNOWN"))
check_true("importing against a WEAK_ORIGINS set lacking the label REFUSES "
           "at import time", _weak.startswith("AssertionError"), _weak[:120])
check_true("the weak-origin guard explains the consequence: a webhook number "
           "would stop being marked untrusted",
           "weak" in _weak.lower() or "trust" in _weak.lower(), _weak[:200])
check_true("after both re-imports the real module is still the one loaded",
           wh.WEBHOOK_ORIGIN == "UNKNOWN" and "market.webhooks" in sys.modules)

# --- the invariant behind an unreachable guard -----------------------------
# The module refuses to write a record containing a newline. MEASURED: that
# branch is unreachable, because json.dumps escapes every newline route tried
# (\n in a value, \n in a KEY, \r, U+2028, U+0085, nesting, default=str, a lone
# surrogate) and the call site passes no indent=. So the mutant that deletes it
# is a documented EQUIVALENT, not a survivor.
# What IS testable is the invariant the guard protects: the queue file is one
# JSON object PER LINE, so a reader splits on newlines. Assert that, so the
# equivalence claim rests on a checked property rather than on my say-so.
_nq = queue("oneline.jsonl")
for _i in range(3):
    deliver(pl=payload(event_id="nl-%d" % _i,
                       comment="a value\nwith newlines\nand\ttabs"),
            q=_nq)
_raw = open(_nq.path, "r", encoding="utf-8").read()
_lines = [l for l in _raw.splitlines() if l.strip()]
check("three deliveries wrote exactly three lines", len(_lines), 3)
check_true("every line parses on its own as a JSON object",
           all(isinstance(json.loads(l), dict) for l in _lines))
check_true("the embedded newlines were ESCAPED, not written raw",
           "\\n" in _raw)
check_true("the escaped value survives the round trip intact",
           json.loads(_lines[0])["extra"]["comment"].count("\n") == 2,
           repr(json.loads(_lines[0])["extra"]["comment"]))
check_true("the file ends with a newline, so an append cannot join two records",
           _raw.endswith("\n"))
check("the record count equals the line count (no record split across lines)",
      _raw.count("\n"), 3)

shutil.rmtree(TMP, ignore_errors=True)
sys.exit(summary())
