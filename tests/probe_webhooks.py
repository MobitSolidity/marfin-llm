"""
Adversarial probe of the webhook receiver (SS.7.1 Level 4).

The spec sentence this file exists to defend is one clause of the Phase 3A
acceptance criteria:

    "Webhooks cannot authorize trades"

and the sentence in SS.7.1 Level 4 that makes it a design constraint rather than
a warning: "Webhook payloads are untrusted data."

WHY THIS PROBE IS SHAPED THE WAY IT IS
--------------------------------------
Every module written in this phase revealed a defect on its first execution, and
in this module the first execution was not enough. The attack sweep passed
completely -- forty-odd attacks, all refused, clean delivery accepted, no secret
in the durable file -- and TWO defects were still present, both found afterwards
by probing the CLEAN passes rather than the refusals:

  DEFECT 1  ValidatedEvent set origin="WEBHOOK", which is not a member of
            quotes.VALUE_ORIGINS, so every consumer that ranks origins was blind
            to it. The obvious repair -- add "WEBHOOK" to that tuple -- was
            measured first and turned out to be the DANGEROUS one: the absence
            of that member is what makes a webhook-derived number impossible to
            construct as a Quote. See webhooks.ORIGIN_RATIONALE.

  DEFECT 2  ValidatedEvent validated NOTHING. It trusted receive() to have done
            it. A hand-built event with event_id="../../etc/passwd",
            timeframe="NOT-A-TIMEFRAME", n_bytes=-1 and
            extra={"action": "buy", "qty": "100"} was accepted by EventQueue,
            and the instruction reached the durable JSONL file. MEASURED, not
            supposed.

So this probe has FOUR attack classes, and the last one is where the real
defects were found:

  A. TRANSPORT/AUTH  -- HTTP, GET, missing/wrong signature, body modified after
     signing, wrong content type, oversize body, non-allowlisted source. Must
     refuse, and the signature must be computed over the RAW body: a receiver
     that re-serializes the parse before verifying fails on valid payloads and
     can be made to pass on modified ones.

  B. SCHEMA/REPLAY   -- missing fields, unknown timeframe, path traversal in an
     id, naive timestamp, epoch number, stale, future, duplicate, and replay
     ACROSS A RESTART. The last matters most: an in-memory nonce set re-opens
     the entire replay window every time the process starts.

  C. AUTHORITY       -- the seven prohibitions, and the question the acceptance
     criterion actually asks: can anything reachable from a delivery authorize a
     trade? Checked by attribute inspection as well as by call, because "there
     is no method that submits" is a claim about the object, not about my
     memory of writing it.

  D. STRUCTURAL      -- the claims no attack above can test: is the origin label
     in the project's vocabulary, does the type enforce its own name, does
     VALIDATION_KEYS cover all sixteen VALIDATIONS, is the module free of
     eval/exec/subprocess.

An attack that is refused proves a guard fires. It does not prove the guard is
the one I think, so refusals are matched BY MESSAGE wherever two guards could
plausibly both fire -- this project has now hit guard shadowing four times.

Run:  python3 tests/probe_webhooks.py
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

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "src"))

from market import webhooks as wh
from market.quotes import VALUE_ORIGINS, WEAK_ORIGINS, Quote, MarketDataError

TMP = tempfile.mkdtemp(prefix="probe-wh-")
NOW = datetime.datetime(2026, 8, 13, 10, 0, 0, tzinfo=datetime.timezone.utc)
SECRET = "s3cret-shared-key"
MODULE_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                          "src", "market", "webhooks.py")

#: Outcome of every class A/B/C attack. Anything but "refused" is a defect.
out = []
#: Structural results. Anything but "ok" is a defect.
structural = []


_qn = [0]


def _queue(name=None):
    """
    A queue nobody else is using.

    The default is UNIQUE PER CALL, and that is a fix for a defect in this probe
    rather than a stylistic choice. Every deliver() below used to share one file,
    so the moment an attack was NOT refused, its payload was queued -- and the
    next attacks were then refused by the DUPLICATE guard instead of the guard
    under test. That is guard shadowing inside the test harness: it disguised two
    real instruction-key gaps ('live', 'disable_risk_checks') as
    "wrong guard fired" and hid one entirely.
    """
    if name is None:
        _qn[0] += 1
        name = "auto-%d.jsonl" % _qn[0]
    return wh.EventQueue(os.path.join(TMP, name))


def clean_payload(**over):
    """A delivery that MUST be accepted. The positive control."""
    p = {"event_id": "evt-1",
         "alert_id": "alert-1",
         "symbol": "AAPL",
         "exchange": "NASDAQ",
         "timeframe": "1h",
         "strategy_id": "strat-x",
         "strategy_version": "1.2.0",
         "fired_at": NOW.isoformat(),
         "comment": "price crossed the 50 EMA"}
    for k, v in over.items():
        if v is None:
            p.pop(k, None)
        else:
            p[k] = v
    return p


def sign(body, secret=SECRET):
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def deliver(payload=None, body=None, method="POST",
            url="https://alerts.example/hook", content_type="application/json",
            signature=None, secret=SECRET, source_ip="203.0.113.7",
            allowlist=("203.0.113.7",), queue=None, now=None,
            sign_body=None, **kw):
    """
    One delivery through the real entry point.

    `sign_body` exists to attack the signature specifically: it signs bytes
    OTHER than the ones sent, which is what "modified after signing" means.
    """
    if body is None:
        body = json.dumps(payload if payload is not None
                          else clean_payload()).encode()
    headers = {"content-type": content_type,
               "authorization": "Bearer user-token-abc123"}
    if signature is None and secret is not None:
        headers["x-signature"] = sign(sign_body if sign_body is not None
                                      else body, secret)
    elif signature:
        headers["x-signature"] = signature
    return wh.receive(method=method, url=url, headers=headers, body=body,
                      queue=queue if queue is not None else _queue(),
                      secret=secret, source_ip=source_ip, allowlist=allowlist,
                      now=now or NOW, **kw)


def attack(name, fn, expect_in=""):
    """
    The call MUST be refused, and by the guard named in `expect_in`.

    A WebhookError from the age check and one from the signature check are the
    same type and completely different facts. Where the expected substring is
    given, a refusal from the wrong guard is recorded as a defect -- that is how
    three of five broker guards were found unexecuted earlier in this project.
    """
    try:
        fn()
    except wh.WebhookError as exc:
        if expect_in and expect_in.lower() not in str(exc).lower():
            out.append("wrong_guard")
            print("  ** WRONG GUARD %-42s expected %r, got: %s"
                  % (name[:42], expect_in, str(exc)[:70]))
            return
        out.append("refused")
        print("  refused  %-46s %s" % (name[:46], str(exc).split(".")[0][:70]))
        return
    except (AttributeError, IndexError, KeyError, NameError,
            TypeError) as exc:
        # A crash is not a refusal, however much it looks like one from outside.
        out.append("crashed")
        print("  !! CRASHED %-44s %s: %s" % (name[:44], type(exc).__name__, exc))
        return
    except Exception as exc:  # noqa: BLE001
        out.append("crashed")
        print("  !! WRONG EXC %-42s %r" % (name[:42], exc))
        return
    out.append("ALLOWED")
    print("  ** ALLOWED %-44s <-- NOT REFUSED" % (name[:44],))


def note(label, ok, detail=""):
    structural.append("ok" if ok else "DEFECT")
    print("  %-10s %-46s %s" % ("ok" if ok else "** DEFECT", label[:46],
                                detail[:60]))


# ---------------------------------------------------------------------------
print("=" * 78)
print("POSITIVE CONTROL -- a clean delivery must be ACCEPTED")
print("=" * 78)
_q = _queue("control.jsonl")
res = deliver(queue=_q, expected_alert_ids=("alert-1",),
              expected_symbols=("AAPL",), expected_exchanges=("NASDAQ",))
note("a clean, signed, allowlisted delivery is accepted",
     res.get("accepted") is True, repr(res.get("event")))
note("it was persisted", len(_q) == 1, "queue length %d" % len(_q))
note("the durable record round-trips", len(_q.read_all()) == 1)

_file = open(os.path.join(TMP, "control.jsonl"), encoding="utf-8").read()
note("the shared secret is NOT in the durable file", SECRET not in _file)
note("the bearer token is NOT in the durable file", "abc123" not in _file)
note("the signature hex is NOT in the durable file",
     sign(json.dumps(clean_payload()).encode()) not in _file)
note("headers are redacted with a CONSTANT, not a hash/prefix",
     all(v == "[REDACTED]"
         for k, v in res["event"].headers.items()
         if k.lower() in ("authorization", "x-signature")),
     str(dict(res["event"].headers)))

# ---------------------------------------------------------------------------
print()
print("=" * 78)
print("CLASS A -- transport and authentication")
print("=" * 78)
attack("http:// instead of https", lambda: deliver(url="http://x/h"), "http")
attack("no scheme at all", lambda: deliver(url="alerts.example/hook"), "http")
attack("a non-http scheme", lambda: deliver(url="ftp://alerts.example/h"),
       "http")
attack("GET", lambda: deliver(method="GET"), "post")
attack("PUT", lambda: deliver(method="PUT"), "post")
attack("no shared secret configured", lambda: deliver(secret=None), "secret")
attack("no signature header", lambda: deliver(secret=SECRET, signature=""),
       "signature")
attack("wrong signature", lambda: deliver(signature="0" * 64), "signature")
attack("signature made with a DIFFERENT secret",
       lambda: deliver(signature=sign(json.dumps(clean_payload()).encode(),
                                      "wrong-secret")), "signature")
attack("body modified AFTER signing",
       lambda: deliver(body=json.dumps(clean_payload(symbol="TSLA")).encode(),
                       sign_body=json.dumps(clean_payload()).encode()),
       "signature")
attack("form content type",
       lambda: deliver(content_type="application/x-www-form-urlencoded"),
       "content type")
attack("no content type", lambda: deliver(content_type=""), "content-type")
attack("oversize body (70 KB)",
       lambda: deliver(payload=clean_payload(pad="x" * 70000)), "limit")
attack("source not in allowlist", lambda: deliver(source_ip="198.51.100.9"),
       "allowlist")
attack("empty source ip when an allowlist is set",
       lambda: deliver(source_ip=""), "allowlist")

print()
print("  -- the signature must cover the RAW body, not a re-serialization --")
_asis = json.dumps(clean_payload()).encode()
_reser = json.dumps(json.loads(_asis), sort_keys=True).encode()
note("re-serializing a valid body CHANGES the bytes", _asis != _reser,
     "so verifying a reparse would fail on valid payloads")
try:
    r = deliver(body=_asis, queue=_queue("raw.jsonl"))
    note("a signature over the EXACT bytes sent verifies",
         r.get("accepted") is True)
except wh.WebhookError as e:
    note("a signature over the EXACT bytes sent verifies", False, str(e)[:60])
attack("a signature over the RE-SERIALIZED bytes is refused",
       lambda: deliver(body=_asis, sign_body=_reser), "signature")

# ---------------------------------------------------------------------------
print()
print("=" * 78)
print("CLASS B -- schema, timestamps, duplicates and replay")
print("=" * 78)
for field in ("event_id", "alert_id", "symbol", "exchange", "timeframe",
              "strategy_id", "strategy_version"):
    attack("missing %s" % field,
           lambda f=field: deliver(payload=clean_payload(**{f: None})),
           "required")
attack("blank symbol", lambda: deliver(payload=clean_payload(symbol="   ")),
       "required")
attack("unknown timeframe 3h",
       lambda: deliver(payload=clean_payload(timeframe="3h")), "recognised")
attack("path traversal in event_id",
       lambda: deliver(payload=clean_payload(event_id="../../etc/passwd")),
       "outside")
attack("newline injected into an id",
       lambda: deliver(payload=clean_payload(event_id="a\nb")), "outside")
attack("over-long strategy_version",
       lambda: deliver(payload=clean_payload(strategy_version="v" * 300)),
       "limit")
attack("body is a JSON array", lambda: deliver(body=b'[{"a":1}]'), "object")
attack("body is a JSON string", lambda: deliver(body=b'"hello"'), "object")
attack("body is not JSON", lambda: deliver(body=b"not json at all"), "json")
attack("body is empty", lambda: deliver(body=b""), "")
attack("alert id not expected",
       lambda: deliver(expected_alert_ids=("other-alert",)), "expect")
attack("symbol not expected", lambda: deliver(expected_symbols=("MSFT",)),
       "expect")
attack("exchange not expected", lambda: deliver(expected_exchanges=("NYSE",)),
       "expect")

print()
attack("no timestamp at all",
       lambda: deliver(payload=clean_payload(fired_at=None)), "timestamp")
attack("naive timestamp (no offset)",
       lambda: deliver(payload=clean_payload(
           fired_at=NOW.replace(tzinfo=None).isoformat())), "timezone")
attack("epoch seconds as a number",
       lambda: deliver(payload=clean_payload(fired_at=1755079200)),
       "iso-8601")
attack("unparseable timestamp",
       lambda: deliver(payload=clean_payload(fired_at="yesterday")), "iso")
attack("one hour stale",
       lambda: deliver(payload=clean_payload(
           fired_at=(NOW - datetime.timedelta(hours=1)).isoformat())), "age")
attack("one hour in the FUTURE",
       lambda: deliver(payload=clean_payload(
           fired_at=(NOW + datetime.timedelta(hours=1)).isoformat())),
       "future")

print()
print("  -- duplicate and replay, the second across a RESTART --")
_rq = _queue("replay.jsonl")
_rp = clean_payload(event_id="evt-replay")
r1 = deliver(payload=_rp, queue=_rq)
note("first delivery of evt-replay accepted", r1.get("accepted") is True)
attack("the SAME event_id delivered twice",
       lambda: deliver(payload=_rp, queue=_rq), "already")

_fresh = wh.EventQueue(os.path.join(TMP, "replay.jsonl"))
note("a fresh queue on the same path RELOADS the seen-set", len(_fresh) == 1,
     "reloaded %d id(s) from disk" % len(_fresh))
attack("replay AFTER A RESTART (new queue, same file)",
       lambda: deliver(payload=_rp, queue=_fresh), "already")
note("has_seen survives the restart", _fresh.has_seen("evt-replay"),
     "an in-memory-only set re-opens the whole replay window")

_torn = os.path.join(TMP, "torn.jsonl")
with open(_torn, "w", encoding="utf-8") as fh:
    fh.write(json.dumps({"event_id": "evt-ok", "received_at": "x"}) + "\n")
    fh.write('{"event_id": "evt-tr')          # power failed mid-write
_tq = wh.EventQueue(_torn)
note("a torn final line does not stop the queue loading",
     _tq.has_seen("evt-ok"), "loaded %d id(s)" % len(_tq))

# ---------------------------------------------------------------------------
print()
print("=" * 78)
print("CLASS C -- authority: the seven prohibitions")
print("=" * 78)
print("  (refused at the PARSER, not stripped: a silently-stripped instruction")
print("   leaves the sender believing it was obeyed -- it sees HTTP 200)")
for key in ("action", "side", "qty", "quantity", "account",
            "account_id", "mode", "live", "override", "disable_risk_checks",
            "cmd", "command", "shell", "path", "file", "api_key", "token",
            "secret", "policy", "limit_price", "stop_price", "take_profit",
            "leverage", "enable_live"):
    attack("instruction key %r at top level" % key,
           lambda k=key: deliver(payload=clean_payload(**{k: "x"})),
           "instruction")

print()
print("  -- the COMPOUND keys the exact-match map missed (measured) --")
print("     ('disable_risk' was listed and 'disable_risk_checks' was not;")
print("      a blocklist of exact spellings fails on the next naming choice)")
for key in ("disable_risk_checks", "enable_live_trading", "my_action",
            "tv_side", "ACCOUNT-ID", "risk-override", "do_execute",
            "sub-account", "shell_cmd", "order.qty"):
    attack("compound instruction key %r" % key,
           lambda k=key: deliver(payload=clean_payload(**{k: "x"})),
           "instruction")

print()
print("  -- keys catchable by exactly ONE token (measured, not stylistic) --")
print("     ('shell_cmd' tokenises to ('shell','cmd'), so it survives the")
print("      deletion of the 'shell' token; these cannot be masked)")
for key in ("disable_all_guards", "shell_target", "go_live_now",
            "my_action_field", "the_account_ref"):
    dangerous = tuple(t for t in wh.key_tokens(key)
                      if t in wh.INSTRUCTION_TOKENS)
    note("%r has exactly one dangerous token" % key, len(dangerous) == 1,
         str(wh.key_tokens(key)))
    attack("single-token instruction key %r" % key,
           lambda k=key: deliver(payload=clean_payload(**{k: "x"})),
           "instruction")

print()
print("  -- ORDINARY alert fields must NOT be refused --")
print("     (a guard that refuses reasonable payloads gets switched off; that")
print("      is why matching is on WORD BOUNDARIES, not substrings. 'price' is")
print("      deliberately allowed: an alert reporting the price it fired at is")
print("      an OBSERVATION. The order parameters are what is refused.)")
for key, value in (("price", "214.5"), ("close", "214.5"), ("volume", "1000"),
                   ("rsi", "71.2"), ("ema_50", "210.1"),
                   ("risk_reward", "2.5"), ("plot_value", "1"),
                   ("bar_time", NOW.isoformat()), ("ticker", "AAPL"),
                   ("interval", "60"), ("alert_name", "EMA cross"),
                   ("transaction_id", "t-1"), ("inside_bar", "true"),
                   ("filepath_note", "none"), ("consideration", "n/a")):
    try:
        r = deliver(payload=clean_payload(**{key: value}))
        note("ordinary field %r is accepted" % key, r.get("accepted") is True)
    except wh.WebhookError as e:
        note("ordinary field %r is accepted" % key, False,
             "FALSE POSITIVE: %s" % str(e)[:50])
attack("instruction NESTED one level down",
       lambda: deliver(payload=clean_payload(tv={"action": "buy"})),
       "instruction")
attack("instruction nested TWO levels down",
       lambda: deliver(payload=clean_payload(a={"b": {"side": "sell"}})),
       "instruction")
attack("instruction inside a LIST",
       lambda: deliver(payload=clean_payload(orders=[{"action": "buy"}])),
       "instruction")
attack("instruction key with padding/case",
       lambda: deliver(payload=clean_payload(**{"  ACTION  ": "buy"})),
       "instruction")

print()
print("  -- can ANYTHING reachable from a delivery authorize a trade? --")
_ev = res["event"]
for purpose in ("live_order", "paper_order", "submit_order", "order_preview",
                "position_sizing", "material_calculation"):
    attack("assert_usable_for(%r)" % purpose,
           lambda p=purpose: _ev.assert_usable_for(p), "")
for purpose in ("notify", "display", "audit", "trigger_analysis"):
    try:
        _ev.assert_usable_for(purpose)
        note("assert_usable_for(%r) is allowed" % purpose, True)
    except wh.WebhookError as e:
        note("assert_usable_for(%r) is allowed" % purpose, False, str(e)[:60])
attack("an UNRECOGNISED purpose is not assumed permitted",
       lambda: _ev.assert_usable_for("something_new"), "unknown purpose")

_acting = [a for a in dir(_ev)
           if any(w in a.lower() for w in
                  ("submit", "send", "execute", "order", "trade", "buy",
                   "sell", "authorize", "enable"))
           and a != "assert_usable_for"]
note("the event exposes NO acting method", not _acting, str(_acting))
_fields = [f for f in wh.ValidatedEvent._FIELDS
           if f in ("side", "qty", "quantity", "price", "account",
                    "account_id", "mode")]
note("the event carries NO side/qty/price/account field", not _fields,
     "the absence IS the security property")
attack("the event is immutable (cannot edit symbol)",
       lambda: setattr(_ev, "symbol", "TSLA"), "immutable")
attack("the event cannot be partially deleted",
       lambda: delattr(_ev, "symbol"), "immutable")
attack("a raw dict cannot be queued",
       lambda: _queue("raw2.jsonl").append({"event_id": "x"}),
       "ValidatedEvent")

# ---------------------------------------------------------------------------
print()
print("=" * 78)
print("CLASS D -- the structural claims no attack above can test")
print("=" * 78)
print("  (BOTH real defects in this module were found HERE, after the attack")
print("   sweep above passed completely)")

print()
print("  -- D1: is the origin label visible to the consumers that rank it? --")
note("the origin label is IN quotes.VALUE_ORIGINS",
     wh.WEBHOOK_ORIGIN in VALUE_ORIGINS, "%r" % (wh.WEBHOOK_ORIGIN,))
note("the origin label is IN quotes.WEAK_ORIGINS",
     wh.WEBHOOK_ORIGIN in WEAK_ORIGINS,
     "a webhook must not outrank a screenshot")
note("the delivered event carries that label", _ev.origin == wh.WEBHOOK_ORIGIN,
     _ev.origin)
# The measured reason the OBVIOUS fix was the wrong one. Adding a "WEBHOOK"
# member to VALUE_ORIGINS would make a webhook-derived number constructible as
# a Quote, which is precisely the laundering the absence prevents.
note("'WEBHOOK' is deliberately ABSENT from VALUE_ORIGINS",
     "WEBHOOK" not in VALUE_ORIGINS, "see webhooks.ORIGIN_RATIONALE")
_launder = False
try:
    Quote(provider="tradingview-alert", symbol="AAPL",
          instrument_id="NASDAQ:AAPL", exchange="NASDAQ", asset_class="EQUITY",
          currency="USD", timestamp=NOW, timezone="UTC",
          delay_status="UNKNOWN", market_status="UNKNOWN",
          adjustment_status="UNKNOWN", trust_level="UNVERIFIED",
          origin="WEBHOOK", last=214.5)
    _launder = True
except MarketDataError:
    pass
note("a Quote with origin='WEBHOOK' cannot be constructed", not _launder,
     "the vocabulary refusal IS the structural block")
note("the rationale for that absence is recorded in the module",
     "Do not add it" in wh.ORIGIN_RATIONALE,
     "so the next maintainer finds the reason before removing it")

print()
print("  -- D2: does ValidatedEvent enforce what its NAME claims? --")


def built(**over):
    kw = dict(event_id="evt-hand", alert_id="alert-1", symbol="AAPL",
              exchange="NASDAQ", timeframe="1h", strategy_id="strat-x",
              strategy_version="1.2.0", fired_at=NOW, received_at=NOW,
              source_ip="203.0.113.7", body_sha256="a" * 64, n_bytes=120,
              headers={}, extra={})
    kw.update(over)
    return wh.ValidatedEvent(**kw)


note("the clean hand-built event IS constructible (positive control)",
     built().event_id == "evt-hand")

# The exact object that reached the durable file before the fix.
_bq = _queue("bypass.jsonl")
_bypassed = None
try:
    _bad = wh.ValidatedEvent(
        event_id="../../etc/passwd", alert_id="", symbol="", exchange="",
        timeframe="NOT-A-TIMEFRAME", strategy_id="", strategy_version="",
        fired_at="not-a-datetime", received_at=NOW, source_ip="",
        body_sha256="nope", n_bytes=-1,
        headers={"authorization": "Bearer LEAKED-TOKEN"},
        extra={"action": "buy", "qty": "100"})
    _bq.append(_bad)
    _bypassed = True
except wh.WebhookError:
    _bypassed = False
note("the measured bypass event is REFUSED at construction", not _bypassed)
note("nothing was written to the queue by the bypass", len(_bq) == 0,
     "queue length %d" % len(_bq))
_bpath = os.path.join(TMP, "bypass.jsonl")
note("no instruction reached a durable file",
     (not os.path.exists(_bpath)
      or "action" not in open(_bpath, encoding="utf-8").read()))

# One bad field at a time. The combined object above could be refused by any
# single guard, which would leave the other guards unexercised -- the guard
# shadowing defect this project has now hit four times.
for label, over, expect in (
        ("event_id path traversal", {"event_id": "../../etc/passwd"},
         "outside"),
        ("event_id empty", {"event_id": ""}, "required"),
        ("alert_id empty", {"alert_id": ""}, "required"),
        ("strategy_id empty", {"strategy_id": ""}, "required"),
        ("symbol empty", {"symbol": ""}, "required"),
        ("exchange empty", {"exchange": ""}, "required"),
        ("strategy_version empty", {"strategy_version": ""}, "required"),
        ("timeframe unknown", {"timeframe": "NOT-A-TIMEFRAME"}, "recognised"),
        ("fired_at is a string", {"fired_at": NOW.isoformat()},
         "must be a datetime"),
        ("fired_at naive", {"fired_at": NOW.replace(tzinfo=None)}, "naive"),
        ("received_at naive", {"received_at": NOW.replace(tzinfo=None)},
         "naive"),
        ("n_bytes negative", {"n_bytes": -1}, "positive integer"),
        ("n_bytes zero", {"n_bytes": 0}, "positive integer"),
        ("n_bytes a bool", {"n_bytes": True}, "positive integer"),
        ("n_bytes a string", {"n_bytes": "120"}, "positive integer"),
        ("body_sha256 not a digest", {"body_sha256": "nope"}, "hex"),
        ("body_sha256 uppercase", {"body_sha256": "A" * 64}, "hex"),
        ("body_sha256 wrong length", {"body_sha256": "a" * 63}, "hex"),
        ("an INSTRUCTION in extra", {"extra": {"action": "buy"}},
         "instruction"),
        ("a nested instruction in extra", {"extra": {"x": {"side": "sell"}}},
         "instruction"),
):
    attack("hand-built: %s" % label, lambda o=over: built(**o), expect)

print()
print("  -- D3: does VALIDATION_KEYS actually cover all sixteen? --")
_declared = set(wh.VALIDATIONS)
_mapped = set(wh.VALIDATION_KEYS)
note("every declared validation names its callable",
     not (_declared - _mapped), str(sorted(_declared - _mapped)))
note("no mapping entry refers to an undeclared validation",
     not (_mapped - _declared), str(sorted(_mapped - _declared)))
note("there are exactly 16 validations, as the spec lists",
     len(wh.VALIDATIONS) == 16, "%d" % len(wh.VALIDATIONS))
note("there are exactly 7 prohibitions, as the spec lists",
     len(wh.PROHIBITIONS) == 7, "%d" % len(wh.PROHIBITIONS))
note("every prohibition records HOW it is prevented",
     set(wh.PROHIBITIONS) == set(wh.PROHIBITION_ENFORCEMENT),
     "a declared item with no enforcement entry looks forgotten")
note("every instruction key maps to one of the 7 prohibitions",
     set(wh.INSTRUCTION_KEYS.values()) <= set(wh.PROHIBITIONS),
     str(sorted(set(wh.INSTRUCTION_KEYS.values()) - set(wh.PROHIBITIONS))))

print()
print("  -- D4: is the module really free of execution primitives? --")
_tree = ast.parse(open(MODULE_SRC, encoding="utf-8").read())
_danger = set()
_imports = set()
for node in ast.walk(_tree):
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
            and node.func.id in ("eval", "exec", "compile", "__import__"):
        _danger.add(node.func.id)
    if isinstance(node, ast.Import):
        for a in node.names:
            _imports.add(a.name.split(".")[0])
    if isinstance(node, ast.ImportFrom) and node.module:
        _imports.add(node.module.split(".")[0])
note("no eval/exec/compile/__import__ in the module", not _danger,
     str(sorted(_danger)))
note("no subprocess import", "subprocess" not in _imports)
note("the execution-mode module is NOT imported",
     "execution" not in _imports,
     "imports: %s" % ", ".join(sorted(_imports)))

# ---------------------------------------------------------------------------
print()
print("=" * 78)
allowed = out.count("ALLOWED")
crashed = out.count("crashed")
wrong = out.count("wrong_guard")
defects = structural.count("DEFECT")
print("attacks: %d  refused=%d  ALLOWED=%d  CRASHED=%d  WRONG-GUARD=%d"
      % (len(out), out.count("refused"), allowed, crashed, wrong))
print("structural checks: %d  ok=%d  DEFECT=%d"
      % (len(structural), structural.count("ok"), defects))
shutil.rmtree(TMP, ignore_errors=True)
if allowed or crashed or wrong or defects:
    print("RESULT: defects present. Fix before proceeding.")
    sys.exit(1)
print("RESULT: every attack refused by the guard that should refuse it; the "
      "origin label is visible to the ranking that distrusts it; the type "
      "enforces its own name; a webhook cannot authorize a trade.")
sys.exit(0)
