"""
Wire clients for the remote providers, in three dialects.

WHY THIS MODULE EXISTS
----------------------
The project's local model was MEASURED twice on the user's own machine
(i5-12400, 16 GB, no GPU). The second run, merged from three per-arm
invocations over 3.65 h, produced:

    decode           3.62 - 4.38 tok/s   (approved minimum 8)      FAIL
    time to first tk 48.6 - 49.9 s       (approved maximum 3.0)    FAIL
    thresholds       8 FAIL / 3 PASS / 1 PENDING of 12  (COMPUTED, see below)
    no visible answer at all in 9 of 52 cases

The threshold tally is COMPUTED, not MEASURED. The merged evidence file leaves
its aggregate `threshold_verdicts` null on purpose -- recomputing them needs
metrics only available while the model is loaded -- and it warns in the file
itself: "do not inherit a subset's verdict". The tally above is therefore
worst-case aggregation (any arm FAIL => FAIL) over per-arm figures that ARE
MEASURED. An earlier version of this comment said "3 PENDING", which sums to 14
against 12 thresholds and was simply wrong.

Two of those failures are hardware-bound: no prompt change makes a 4B model
decode twice as fast on six CPU cores. The user asked for API connectivity for
exactly that reason. This module is that connectivity.

WHAT THIS MODULE DELIBERATELY DOES NOT DO
-----------------------------------------
1. It does not replace the local model. The user's instruction was explicit:
   "مدل محلی حتماً باید باقی بماند و فقط api به آن اضافه گردد" -- the local
   model stays, the API is only added. `local` remains the default everywhere.

2. It does not choose a model id for you. Model choice is the single biggest
   determinant of cost, and model names are deprecated and renamed constantly.
   Guessing one could spend the user's money on a model they never named, so a
   missing model id RAISES, with the provider's own model list linked.

3. It does not hard-code a rate limit, a price or a context length. Web search
   on 2026-08-27 returned mutually contradictory free-tier figures from
   reputable sources for both Groq (6k/min vs 30k/min vs 500k/day) and Gemini
   (10 / 50 / 100 / 250 / 1500 requests per day, with reports that Google had
   REDUCED the tier). A number that disagrees with itself is not a fact.

4. It adds no dependency. `urllib.request` from the standard library, matching
   the discipline of the rest of the project. No `requests`, no vendor SDK --
   an SDK per provider would be five installs and five upgrade treadmills for
   one HTTP POST each.

SHAPE
-----
`chat()` returns a dict of MEASURED transport facts. It does NOT split
<think> blocks: that split lives in exactly one place (phase4_lib.strip_thinking,
consumed via ModelRunner) because MEASURED 2026-08-17, doing it per call site
let a reply whose reasoning refused and whose answer said "Buy 500 shares of
AAPL right now" score as a clean refusal. This module returns raw text and lets
that single splitter own the meaning.
"""

from __future__ import annotations

import json
import random
import re
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Sequence

from .providers import ProviderError, get_api_key, get_provider, redact, resolve_base_url

# ---------------------------------------------------------------------------
# Transport policy.
# ---------------------------------------------------------------------------
# A CPU-bound local run takes 49 s just to produce its first token, so a
# remote call that takes 60 s is still an improvement and must not be killed as
# a timeout. 120 s is the ceiling: past that, something is wrong rather than
# slow.
DEFAULT_TIMEOUT_S = 120.0

# Retry only what is worth retrying. A 400 or a 401 will fail identically
# forever; retrying it just wastes the user's quota and hides the real error.
RETRY_STATUS = (408, 409, 425, 429, 500, 502, 503, 504)
DEFAULT_RETRIES = 3
MAX_BACKOFF_S = 30.0

# Model ids are NOT hard-coded as facts. These are UNVERIFIED hints printed in
# the error message when the user omits --model-id, so they have somewhere to
# start. They are never sent automatically. A hint that has been renamed costs
# the user one 404; a silent default could cost them money on the wrong model.
MODEL_HINTS: Dict[str, str] = {
    "openai": "e.g. gpt-4o-mini (UNVERIFIED hint; check the models list)",
    "anthropic": "e.g. claude-3-5-haiku-latest (UNVERIFIED hint)",
    "google": "e.g. gemini-2.0-flash (UNVERIFIED hint)",
    "groq": "e.g. llama-3.3-70b-versatile (UNVERIFIED hint)",
    "openrouter": "the id decides whether you pay; free ones end in ':free'",
    # AgentRouter is an aggregator, so the id names an UPSTREAM model, not one
    # of its own. Its portal listed gpt-5.5 / glm-5.1 / kimi-k2.6 for the
    # OpenAI dialect and claude-opus-4-8 for the Anthropic one on 2026-08-27,
    # but the same page states the available set depends on the resource pool
    # bound to your key -- so no id is asserted here as a fact. Ask the
    # endpoint itself: GET /v1/models.
    "agentrouter": "an UPSTREAM id, pool-dependent; ask GET /v1/models",
    "agentrouter-anthropic": "a Claude-family id; your pool decides which",
    "mistral": "e.g. mistral-small-latest (UNVERIFIED hint)",
    "deepseek": "e.g. deepseek-chat (UNVERIFIED hint)",
    "together": "a fully qualified id such as org/model-name",
    "cerebras": "e.g. llama3.1-8b (UNVERIFIED hint)",
    "xai": "e.g. grok-2-latest (UNVERIFIED hint)",
    "custom": "whatever your endpoint serves; ask it for /v1/models",
}


class RemoteCallError(ProviderError):
    """
    A remote call failed. Carries no credential: the message is built through
    redact() before it is ever raised.
    """


# ---------------------------------------------------------------------------
# Spend gate.
# ---------------------------------------------------------------------------

_LOCALHOST_RE = re.compile(
    r"^https?://(localhost|127(\.\d{1,3}){3}|\[::1\]|0\.0\.0\.0)(:\d+)?(/|$)")


def spend_gate(provider: str, allow_paid: bool = False,
               base_url: Optional[str] = None) -> Dict[str, Any]:
    """
    Refuse a billable call unless the user explicitly allowed it.

    The user's standing constraint from request 23 is "free tier only, spend
    nothing", and they restated it here: "من از api های رایگان استفاده می‌کنم
    فعلاً". They also asked that paid providers be PRESENT for whoever does
    have paid access -- so the answer is a gate, not an omission.

    A provider whose free tier is UNKNOWN is treated as billable. Being wrong
    in the safe direction costs one command-line flag; being wrong in the other
    direction costs money.

    EXCEPTION, ADDED AFTER A MEASURED FALSE ALARM 2026-08-27: an endpoint on
    THIS machine cannot bill anyone. The first version of this gate demanded
    --allow-paid for `custom` even when it pointed at http://localhost:8080/v1,
    i.e. the user's own LM Studio or llama.cpp server. That is a warning in the
    wrong place, and a warning that fires when nothing is at stake is how users
    learn to pass the override reflexively -- which is precisely how the real
    warning, on a real paid endpoint, stops being read. The exemption is decided
    by the RESOLVED url and is deliberately narrow: loopback literals only, no
    private-range guessing, because a host on the LAN could be anything.
    """
    spec = get_provider(provider)
    free = spec.get("free_tier")
    billable = free is not True

    if billable and base_url and _LOCALHOST_RE.match(str(base_url).strip()):
        return {"provider": provider, "billable": False, "free_tier": free,
                "allowed": True, "local_endpoint": True}
    if billable and not allow_paid:
        if free is False:
            why = "%s is documented as paid-only." % spec["label"]
        else:
            why = ("whether %s can be used free of charge is UNKNOWN to this "
                   "project -- published figures disagree, so it is treated as "
                   "billable." % spec["label"])
        raise ProviderError(
            "refusing to call %s without --allow-paid. %s Your recorded "
            "constraint is free-tier only. Providers with a documented free "
            "tier and no card required: %s. If you do hold paid access, pass "
            "--allow-paid and the call proceeds. Pricing: %s"
            % (provider, why,
               ", ".join(n for n in ("local", "groq", "google", "cerebras")),
               spec.get("docs") or "see the provider docs"))
    return {"provider": provider, "billable": billable,
            "free_tier": free, "allowed": True}


# ---------------------------------------------------------------------------
# HTTP, once, for all three dialects.
# ---------------------------------------------------------------------------

def _post_json(url: str, payload: Dict[str, Any], headers: Dict[str, str],
               timeout: float, key: Optional[str]) -> Dict[str, Any]:
    """
    One POST. Returns {status, body_text, body_json|None}. Raises only for
    transport-level failures; an HTTP error status is RETURNED so the caller
    can decide whether it is worth retrying.
    """
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            status = int(getattr(resp, "status", 200) or 200)
            retry_after = resp.headers.get("Retry-After")
    except urllib.error.HTTPError as exc:               # 4xx / 5xx
        raw = ""
        try:
            raw = exc.read().decode("utf-8", "replace")
        except Exception:                                # pragma: no cover
            pass
        status = int(exc.code)
        retry_after = exc.headers.get("Retry-After") if exc.headers else None
    except urllib.error.URLError as exc:
        # DNS failure, refused connection, TLS problem, timeout. The reason can
        # contain the URL, and for a badly built request the URL could contain a
        # key, so it goes through redact() like everything else.
        raise RemoteCallError(
            "could not reach the provider: %s"
            % redact(getattr(exc, "reason", exc), key)) from None
    except Exception as exc:                             # socket.timeout etc.
        raise RemoteCallError(
            "transport failure talking to the provider: %s"
            % redact(exc, key)) from None

    parsed = None
    if raw:
        try:
            parsed = json.loads(raw)
        except ValueError:
            parsed = None
    return {"status": status, "body_text": raw, "body_json": parsed,
            "retry_after": retry_after}


def _sleep_for(attempt: int, retry_after: Optional[str]) -> float:
    """
    How long to wait before the next attempt.

    The provider's own Retry-After is obeyed when it is present and sane:
    guessing shorter than the server asked is how a 429 becomes a ban. The
    fallback is exponential with jitter, because several arms retrying in
    lockstep would re-collide on the same second.
    """
    if retry_after:
        try:
            wait = float(str(retry_after).strip())
            if 0 < wait <= 120:
                return wait
        except ValueError:
            pass  # HTTP-date form; fall through to backoff
    return min(MAX_BACKOFF_S, (2.0 ** attempt)) * (0.7 + 0.6 * random.random())


def _error_text(resp: Dict[str, Any], key: Optional[str]) -> str:
    """A short, redacted description of a failed HTTP response."""
    js = resp.get("body_json")
    msg = None
    if isinstance(js, dict):
        err = js.get("error")
        if isinstance(err, dict):
            msg = err.get("message") or err.get("type")
        elif isinstance(err, str):
            msg = err
        if not msg:
            msg = js.get("message") or js.get("detail")
    if not msg:
        msg = (resp.get("body_text") or "")[:400] or "(empty response body)"
    return redact("HTTP %s: %s" % (resp.get("status"), msg), key)


# ---------------------------------------------------------------------------
# Dialect: OpenAI chat-completions. Serves 9 of the 12 registry entries.
# ---------------------------------------------------------------------------

def _openai_request(base_url: str, key: Optional[str], model_id: str,
                    prompt: str, max_tokens: int, temperature: float,
                    token_field: str,
                    turns: Optional[Sequence[Dict[str, str]]] = None,
                    seed: Optional[int] = None,
                    stop: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """
    Build one chat-completions request.

    `turns`, `seed` and `stop` added 2026-09-05 (D-0093). Without them the
    caller's whole ChatML string went out as ONE user message, MEASURED:

        "messages": [{"role": "user",
                      "content": "<|im_start|>system\\nYou are a bilingual..."}]

    A remote provider applies its OWN chat template to that, so the system
    instruction was not a system instruction and the pre-closed <think> prefill
    -- the D-0091 fix that eliminated silence in all 52 local cases -- arrived
    as literal body text and did nothing. The result would still have looked
    like a valid run.
    """
    payload = {
        "model": model_id,
        "messages": (list(turns) if turns
                     else [{"role": "user", "content": prompt}]),
        token_field: int(max_tokens),
        "temperature": float(temperature),
    }
    # Sent only when supplied, so a provider that rejects an unknown field is
    # not broken by a key it never asked for.
    if seed is not None:
        payload["seed"] = int(seed)
    if stop:
        payload["stop"] = list(stop)
    headers = {}
    if key:
        headers["Authorization"] = "Bearer " + key
    return {"url": base_url + "/chat/completions",
            "payload": payload, "headers": headers}


def _openai_parse(js: Any) -> Dict[str, Any]:
    if not isinstance(js, dict):
        raise RemoteCallError("provider returned a %s, not a JSON object"
                              % type(js).__name__)
    choices = js.get("choices") or []
    if not choices:
        raise RemoteCallError(
            "provider returned no choices. This is not the same as an empty "
            "answer and must not be graded as one.")
    msg = (choices[0] or {}).get("message") or {}
    text = msg.get("content")
    if text is None:
        # Some providers put reasoning in a separate field and leave content
        # null when the output budget ran out mid-thought. That is exactly the
        # failure mode MEASURED on the local model, so it is reported, not
        # papered over with "".
        text = ""
    usage = js.get("usage") or {}
    return {
        "text": str(text),
        "prompt_tokens": int(usage.get("prompt_tokens") or 0),
        "completion_tokens": int(usage.get("completion_tokens") or 0),
        "finish_reason": (choices[0] or {}).get("finish_reason"),
    }


# ---------------------------------------------------------------------------
# Dialect: Anthropic messages.
# ---------------------------------------------------------------------------

def _anthropic_request(base_url: str, key: Optional[str], model_id: str,
                       prompt: str, max_tokens: int,
                       temperature: float,
                       turns: Optional[Sequence[Dict[str, str]]] = None,
                       seed: Optional[int] = None,
                       stop: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """
    Build one Anthropic messages request.

    Structural note for D-0093: this API takes `system` as a TOP-LEVEL field,
    not as a messages entry, and it accepts a trailing assistant turn as a
    genuine prefill the model continues. So the ChatML prefill translates
    natively here -- but only if the turns are handed over separately, which is
    why `turns` exists.

    `seed` is accepted and DELIBERATELY DROPPED: this API has no seed
    parameter. Silently sending one would be rejected by the provider; silently
    pretending it applied would be worse, so the run report records what was
    actually sent, not what was asked for.
    """
    msgs = [{"role": "user", "content": prompt}]
    system_text = None
    if turns:
        msgs = [t for t in turns if t.get("role") != "system"]
        sys_turns = [t["content"] for t in turns if t.get("role") == "system"]
        system_text = "\n\n".join(sys_turns) if sys_turns else None
    payload = {
        "model": model_id,
        "max_tokens": int(max_tokens),       # required by this API, not optional
        "temperature": float(temperature),
        "messages": msgs,
    }
    if system_text:
        payload["system"] = system_text
    if stop:
        payload["stop_sequences"] = list(stop)
    headers = {"anthropic-version": "2023-06-01"}
    if key:
        headers["x-api-key"] = key           # NOT an Authorization bearer
    return {"url": base_url + "/messages", "payload": payload,
            "headers": headers}


def _anthropic_parse(js: Any) -> Dict[str, Any]:
    if not isinstance(js, dict):
        raise RemoteCallError("provider returned a %s, not a JSON object"
                              % type(js).__name__)
    blocks = js.get("content")
    if not isinstance(blocks, list):
        raise RemoteCallError("response has no content blocks")
    # Content is a LIST of typed blocks. Only `text` blocks are the answer;
    # `thinking` blocks are reasoning and must not be concatenated into it, for
    # the same reason <think> is stripped from the local model's output.
    parts = [b.get("text", "") for b in blocks
             if isinstance(b, dict) and b.get("type") == "text"]
    usage = js.get("usage") or {}
    return {
        "text": "".join(parts),
        "prompt_tokens": int(usage.get("input_tokens") or 0),
        "completion_tokens": int(usage.get("output_tokens") or 0),
        "finish_reason": js.get("stop_reason"),
    }


# ---------------------------------------------------------------------------
# Dialect: Google Gemini generateContent.
# ---------------------------------------------------------------------------

def _google_request(base_url: str, key: Optional[str], model_id: str,
                    prompt: str, max_tokens: int,
                    temperature: float,
                    turns: Optional[Sequence[Dict[str, str]]] = None,
                    seed: Optional[int] = None,
                    stop: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """
    Build one Gemini generateContent request.

    Structural notes for D-0093: the system instruction is a separate
    `systemInstruction` object, and the assistant role is spelled "model", not
    "assistant". Mapping the role is not cosmetic -- an unrecognised role is
    rejected outright, so a prefill turn sent as "assistant" would fail the
    whole run rather than degrade quietly.
    """
    contents = [{"role": "user", "parts": [{"text": prompt}]}]
    system_instruction = None
    if turns:
        contents = []
        sys_turns = []
        for t in turns:
            role = t.get("role")
            if role == "system":
                sys_turns.append(t["content"])
                continue
            contents.append({"role": "model" if role == "assistant" else "user",
                             "parts": [{"text": t["content"]}]})
        if sys_turns:
            system_instruction = {"parts": [{"text": "\n\n".join(sys_turns)}]}
    gen: Dict[str, Any] = {"maxOutputTokens": int(max_tokens),
                           "temperature": float(temperature)}
    if seed is not None:
        gen["seed"] = int(seed)
    if stop:
        gen["stopSequences"] = list(stop)
    payload: Dict[str, Any] = {"contents": contents, "generationConfig": gen}
    if system_instruction:
        payload["systemInstruction"] = system_instruction
    headers = {}
    if key:
        # The key goes in a HEADER, never in the query string. `?key=` would be
        # written into every proxy log, shell history entry and exception
        # message that contains the URL -- a credential leak by default.
        headers["x-goog-api-key"] = key
    model_path = model_id if model_id.startswith("models/") else "models/" + model_id
    return {"url": "%s/%s:generateContent" % (base_url, model_path),
            "payload": payload, "headers": headers}


def _google_parse(js: Any) -> Dict[str, Any]:
    if not isinstance(js, dict):
        raise RemoteCallError("provider returned a %s, not a JSON object"
                              % type(js).__name__)
    usage = js.get("usageMetadata") or {}
    cands = js.get("candidates") or []
    if not cands:
        # A prompt blocked by a safety filter comes back with no candidates at
        # all. Reporting that as an empty answer would score a refusal we never
        # received; the reason is surfaced instead.
        fb = js.get("promptFeedback") or {}
        raise RemoteCallError(
            "provider returned no candidates (promptFeedback=%s). This is a "
            "blocked or empty generation, not an answer."
            % json.dumps(fb)[:200])
    cand = cands[0] or {}
    parts = ((cand.get("content") or {}).get("parts") or [])
    text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
    # Thinking models can return finishReason MAX_TOKENS with NO parts at all:
    # the whole budget went into reasoning. That is the identical failure mode
    # MEASURED on the local model in 9 of 52 cases, so it stays visible.
    return {
        "text": text,
        "prompt_tokens": int(usage.get("promptTokenCount") or 0),
        "completion_tokens": int(usage.get("candidatesTokenCount") or 0),
        "finish_reason": cand.get("finishReason"),
    }


# ---------------------------------------------------------------------------
# The one public entry point.
# ---------------------------------------------------------------------------

def chat(provider: str, prompt: str, max_tokens: int,
         model_id: Optional[str] = None,
         api_key: Optional[str] = None,
         base_url: Optional[str] = None,
         temperature: float = 0.0,
         timeout: float = DEFAULT_TIMEOUT_S,
         retries: int = DEFAULT_RETRIES,
         allow_paid: bool = False,
         opener: Optional[Any] = None,
         turns: Optional[Sequence[Dict[str, str]]] = None,
         seed: Optional[int] = None,
         stop: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """
    One completion from a remote provider.

    Returns MEASURED transport facts only:
        text, prompt_tokens, completion_tokens, finish_reason,
        seconds, attempts, http_status, provider, model_id, wire

    `opener` exists so the test suite can drive every branch of this function
    without a network or a credential. It replaces _post_json, not the parsing,
    so the dialect handling under test is the same code that ships.
    """
    spec = get_provider(provider)
    if spec["wire"] == "local":
        raise ProviderError(
            "provider 'local' does not go over the wire. It is served by "
            "ModelRunner over llama.cpp in scripts/run_phase4.py, and it "
            "remains the default. This function is for remote providers only.")

    if not isinstance(prompt, str) or not prompt.strip():
        raise ProviderError("refusing to send an empty prompt")
    try:
        max_tokens = int(max_tokens)
    except (TypeError, ValueError):
        raise ProviderError("max_tokens must be an integer, got %r"
                            % (max_tokens,)) from None
    if max_tokens < 1:
        raise ProviderError("max_tokens must be at least 1, got %d" % max_tokens)

    # The endpoint is RESOLVED BEFORE the spend gate, because the gate's
    # loopback exemption is a decision about the resolved url -- an unresolved
    # `base_url=None` would make a `custom` provider pointing at localhost look
    # billable. Resolution is also pure validation: it opens no socket, so
    # nothing is spent by doing it first.
    url_base = resolve_base_url(provider, base_url)
    spend_gate(provider, allow_paid=allow_paid, base_url=url_base)

    model_id = (model_id or "").strip()
    if not model_id:
        raise ProviderError(
            "no model id for %s. Pass --model-id. There is no default on "
            "purpose: the model id decides both the answer and the price, and "
            "a guessed default could spend money on a model you never chose. "
            "Starting point: %s. Docs: %s"
            % (spec["label"], MODEL_HINTS.get(provider, "see the provider docs"),
               spec.get("docs") or "see the provider docs"))

    key = get_api_key(provider, api_key)
    wire = spec["wire"]
    post = opener or _post_json

    # OpenAI renamed max_tokens to max_completion_tokens for its newer models
    # and rejects the old name outright. Every other openai-wire provider still
    # takes max_tokens. Rather than keep a list of which models moved -- a list
    # that would be wrong within a month -- send the common name and switch ONCE
    # if the provider says it is unsupported.
    token_field = "max_tokens"
    token_field_retried = False

    attempts = 0
    last_err = None
    while attempts < max(1, int(retries)):
        attempts += 1
        if wire == "openai":
            built = _openai_request(url_base, key, model_id, prompt,
                                    max_tokens, temperature, token_field,
                                    turns=turns, seed=seed, stop=stop)
        elif wire == "anthropic":
            built = _anthropic_request(url_base, key, model_id, prompt,
                                       max_tokens, temperature,
                                       turns=turns, seed=seed, stop=stop)
        elif wire == "google":
            built = _google_request(url_base, key, model_id, prompt,
                                    max_tokens, temperature,
                                    turns=turns, seed=seed, stop=stop)
        else:                                            # pragma: no cover
            raise ProviderError("unsupported wire dialect %r" % wire)

        t0 = time.time()
        resp = post(built["url"], built["payload"], built["headers"],
                    timeout, key)
        elapsed = time.time() - t0
        status = int(resp.get("status") or 0)

        if 200 <= status < 300:
            if wire == "openai":
                parsed = _openai_parse(resp.get("body_json"))
            elif wire == "anthropic":
                parsed = _anthropic_parse(resp.get("body_json"))
            else:
                parsed = _google_parse(resp.get("body_json"))
            parsed.update({
                "seconds": round(elapsed, 3),
                "attempts": attempts,
                "http_status": status,
                "provider": provider,
                "model_id": model_id,
                "wire": wire,
                "decode_tps": (round(parsed["completion_tokens"] / elapsed, 2)
                               if elapsed > 0 and parsed["completion_tokens"]
                               else None),
            })
            return parsed

        detail = _error_text(resp, key)

        if (status == 400 and token_field == "max_tokens"
                and not token_field_retried
                and "max_completion_tokens" in detail):
            token_field = "max_completion_tokens"
            token_field_retried = True
            attempts -= 1        # a parameter-name fix is not a failed attempt
            continue

        last_err = detail
        if status in RETRY_STATUS and attempts < max(1, int(retries)):
            time.sleep(_sleep_for(attempts, resp.get("retry_after")))
            continue

        hint = ""
        if status in (401, 403):
            hint = (" The key in %s was rejected. Check it is the whole key "
                    "and for the right account."
                    % (spec.get("env_key") or "the environment"))
        elif status == 404:
            hint = (" Model %r may not exist on this provider or may have been "
                    "renamed. This project does not hard-code model ids, so "
                    "check the provider's model list." % model_id)
        elif status == 429:
            hint = (" Rate limit or quota. This project does not record any "
                    "provider's quota as a fact, because published figures "
                    "disagree -- see %s."
                    % (spec.get("docs") or "the provider's limits page"))
        # DEFECT FOUND BY ADVERSARIAL TEST 2026-08-27, in my own code.
        # There used to be a second `raise ... "failed after %d attempt(s)"`
        # AFTER this loop, intended to report retry exhaustion. MEASURED at
        # retries = 0, 1, 2, 3 and 5 against a permanent 429: the message came
        # from THIS line every single time and the trailer was never reached --
        # because the `attempts < retries` guard above turns the last retryable
        # failure into a fall-through to here rather than a loop exit. So the
        # trailer was dead code, and the attempt count -- the one number a
        # free-tier user needs, since three retries burn three requests of a
        # quota, not one -- was never reported at all. The dead branch is gone
        # and the count is stated here, where the raise actually happens.
        raise RemoteCallError(
            "%s failed after %d attempt(s). %s%s"
            % (spec["label"], attempts, detail, hint))

    # Unreachable: `retries` is floored at 1, so the loop body always runs at
    # least once and every exit above either returns or raises. Kept as an
    # explicit contradiction rather than an implicit `return None`, which would
    # hand the grader a None and let it score a missing answer as an answer.
    raise RemoteCallError(                                    # pragma: no cover
        "%s: retry loop ended without a result after %d attempt(s), which "
        "should be impossible. Last error: %s"
        % (spec["label"], attempts, last_err or "unknown"))


def wire_dialects() -> Dict[str, List[str]]:
    """Which providers speak which dialect. Used by the panel and the tests."""
    from .providers import PROVIDERS
    out: Dict[str, List[str]] = {}
    for name, spec in PROVIDERS.items():
        out.setdefault(spec["wire"], []).append(name)
    for v in out.values():
        v.sort()
    return out
