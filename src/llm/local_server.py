# -*- coding: utf-8 -*-
"""
Phase 8: drive Ollama or LM Studio with the harness's OWN rendered prompt (D-0123).

Why raw completion and not /chat: a chat endpoint applies the chat template
embedded in the GGUF. That template differs from the HF one (D-0121), its
default does not think, and a client may ship its own. Every recorded result
was produced from prompts this project rendered byte-for-byte (pinned against
both templates in tests/test_phase7.py). So the orchestrator sends that same
string and asks the server NOT to template it:

  ollama    POST {base}/api/generate   {"raw": true, "prompt": ...}
            (documented: "if true no formatting will be applied to the prompt")
  lmstudio  POST {base}/v1/completions {"prompt": ...}   (text completion)

ServerRunner has ModelRunner's exact return contract, (answer, metrics) with
<think> stripped by the same splitter, so every arm and every grader runs
unchanged on a server. Loopback only: these are local servers, and a prompt
carrying financial data must not leave the machine by accident.
"""
import json
import re
import time
import urllib.error
import urllib.request

BACKENDS = ("ollama", "lmstudio")
DEFAULT_BASE = {"ollama": "http://127.0.0.1:11434", "lmstudio": "http://127.0.0.1:1234"}
_LOOPBACK = re.compile(r"^http://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?/?$")


class ServerError(RuntimeError):
    pass


def _post(url, payload, timeout):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise ServerError("HTTP %s from %s: %s" % (e.code, url, e.read()[:300]))
    except urllib.error.URLError as e:
        raise ServerError("cannot reach %s (%s). Is the server running?" % (url, e.reason))


def build_request(backend, base_url, model_id, prompt, max_tokens, temperature, seed,
                  stop, num_ctx=None, num_thread=None):
    """(url, payload). Pure: no network. Raises on anything unsafe or unknown."""
    if backend not in BACKENDS:
        raise ServerError("unknown backend %r (allowed: %s)" % (backend, ", ".join(BACKENDS)))
    base = (base_url or DEFAULT_BASE[backend]).rstrip("/")
    if not _LOOPBACK.match(base + "/"):
        raise ServerError("refusing non-loopback server %r: Phase 8 servers are local" % base)
    if not str(model_id or "").strip():
        raise ServerError("no --model-id: name the model as the server knows it")
    if backend == "ollama":
        opts = {"temperature": float(temperature), "seed": int(seed),
                "num_predict": int(max_tokens), "stop": list(stop)}
        if num_ctx:
            opts["num_ctx"] = int(num_ctx)
        if num_thread:
            opts["num_thread"] = int(num_thread)
        return base + "/api/generate", {"model": model_id, "prompt": str(prompt),
                                        "raw": True, "stream": False, "options": opts}
    return base + "/v1/completions", {"model": model_id, "prompt": str(prompt),
                                      "max_tokens": int(max_tokens),
                                      "temperature": float(temperature),
                                      "seed": int(seed), "stop": list(stop),
                                      "stream": False}


def parse_response(backend, js, elapsed):
    """(text, metrics). Server-reported timings are used when present (M)."""
    if not isinstance(js, dict):
        raise ServerError("server returned %s, not a JSON object" % type(js).__name__)
    if backend == "ollama":
        if "response" not in js:
            raise ServerError("ollama reply has no 'response' field: %r" % list(js)[:8])
        n_out = int(js.get("eval_count") or 0)
        ev_ns = js.get("eval_duration") or 0
        pe_ns = js.get("prompt_eval_duration")
        return js["response"], {
            "prompt_tokens": int(js.get("prompt_eval_count") or 0),
            "completion_tokens": n_out,
            "decode_tps": round(n_out / (ev_ns / 1e9), 2) if ev_ns and n_out else None,
            "prefill_seconds": round(pe_ns / 1e9, 3) if pe_ns else None,
            "finish_reason": js.get("done_reason"),
            "timing_source": "server"}
    ch = (js.get("choices") or [None])[0]
    if not ch or "text" not in ch:
        raise ServerError("completions reply has no choices[0].text")
    u = js.get("usage") or {}
    n_out = int(u.get("completion_tokens") or 0)
    return ch["text"], {
        "prompt_tokens": int(u.get("prompt_tokens") or 0),
        "completion_tokens": n_out,
        "decode_tps": round(n_out / elapsed, 2) if elapsed > 0 and n_out else None,
        "prefill_seconds": None,
        "finish_reason": ch.get("finish_reason"),
        "timing_source": "wall_clock (includes prefill)"}


class ServerRunner(object):
    """ModelRunner's interface over a local Ollama / LM Studio server."""

    def __init__(self, backend, model_id, base_url=None, max_tokens=512,
                 temperature=0.0, seed=20260831, stop=("<|im_end|>", "<|im_start|>user"),
                 num_ctx=None, num_thread=None, timeout=900, post=None):
        self.backend, self.model_id, self.base_url = backend, model_id, base_url
        self.max_tokens, self.temperature, self.seed = max_tokens, temperature, seed
        self.stop, self.num_ctx, self.num_thread = list(stop), num_ctx, num_thread
        self.timeout, self._post = timeout, post or _post
        self.calls = self.thinking_replies = self.truncated_thinking = 0
        self.llm = None          # no in-process model: token counting falls back
        build_request(backend, base_url, model_id, "x", 1, temperature, seed, self.stop)

    def complete_raw(self, prompt, max_tokens):
        """Raw text completion: (text, completion_tokens). For thinking.generate_budgeted."""
        url, payload = build_request(self.backend, self.base_url, self.model_id, prompt,
                                     max_tokens, self.temperature, self.seed, self.stop,
                                     self.num_ctx, self.num_thread)
        t0 = time.time()
        js = self._post(url, payload, self.timeout)
        text, m = parse_response(self.backend, js, time.time() - t0)
        return text, m["completion_tokens"]

    def generate(self, prompt, max_tokens=None):
        import phase4_lib as L          # same splitter as every other runner
        self.calls += 1
        n = max_tokens or self.max_tokens
        url, payload = build_request(self.backend, self.base_url, self.model_id, prompt, n,
                                     self.temperature, self.seed, self.stop,
                                     self.num_ctx, self.num_thread)
        t0 = time.time()
        js = self._post(url, payload, self.timeout)
        elapsed = time.time() - t0
        text, m = parse_response(self.backend, js, elapsed)
        split = L.strip_thinking(text)
        if split["had_thinking"]:
            self.thinking_replies += 1
        if split["truncated"]:
            self.truncated_thinking += 1
        m.update({"seconds": round(elapsed, 3), "had_thinking": split["had_thinking"],
                  "thinking_truncated": split["truncated"],
                  "reasoning_chars": len(split["reasoning"]), "raw_output": text,
                  "backend": self.backend, "model_id": self.model_id})
        return split["answer"], m
