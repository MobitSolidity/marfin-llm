"""
Provider registry and credential handling for remote LLM APIs.

WHY THIS MODULE EXISTS
----------------------
MEASURED on the target machine 2026-08-26/27 (phase4_merged.json, 3.65 h of the
user's own CPU): the local Qwen3.5-4B-Q5_K_M run FAILED 8 of 12 approved
thresholds, including two that are hardware-bound and cannot be fixed by
prompting or by raising the token budget:

    generation_tokens_per_sec   3.62 .. 4.38   approved minimum 8
    time_to_first_token_2k_sec  48.58 .. 49.89 approved maximum 3.0

Raising --max-tokens from 768 to 2048 cut truncation from 20/52 to 11/52 but did
not eliminate it: the 11 survivors now emit 6,000-8,700 characters of reasoning
and STILL never reach an answer. The budget was never the binding constraint.

So a remote API becomes an option. This module does NOT remove the local model
(the user was explicit: "مدل محلی حتما باید باقی بماند") -- local remains a
first-class provider and the default.

THE DESIGN RULE THAT SHAPES EVERYTHING BELOW
--------------------------------------------
No rate limit, no price, and no context length is hard-coded as a fact.

That is not laziness; it is a MEASURED conclusion. Searching for the free-tier
limits on 2026-08-27 returned mutually contradictory figures from sources of
similar apparent authority:

    Groq   free tier: "6,000 tokens/min" / "30,000 tokens/min" /
                      "500,000 tokens/day" -- three different answers
    Gemini free tier: "10 RPD" / "50 RPD" / "100 RPD" / "250 RPD" / "1,500 RPD",
                      with multiple sources reporting that Google *reduced* the
                      free tier during 2026

A number written into this file would be stale within weeks and would then be
quoted by the project as if it were verified. Every quota field below is
therefore UNKNOWN, with the provider's own limits page as the only citation, and
the code reads real limits from response headers when a provider sends them.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional


class ProviderError(Exception):
    """A provider could not be used. Never carries a credential."""


# ---------------------------------------------------------------------------
# The registry
# ---------------------------------------------------------------------------
# `wire` is the request/response dialect, NOT the company. Most providers speak
# the OpenAI chat-completions dialect, so one implementation serves them all;
# Anthropic and Google speak their own.
#
# `free_tier` is a tri-state and MUST NOT be read as a quota:
#   True    the provider documents a no-credit-card free tier
#   False   documented as paid-only
#   None    UNKNOWN / changes too often to assert
PROVIDERS: Dict[str, Dict[str, Any]] = {
    "local": {
        "label": "Local llama.cpp (no network, no key, no cost)",
        "wire": "local",
        "env_key": None,
        "base_url": None,
        "free_tier": True,
        "cost": "zero marginal cost; costs your CPU time instead",
        "note": "The project's original design and still the default. MEASURED "
                "3.62-4.38 tok/s and 48.6-49.9 s TTFT on an i5-12400, which "
                "fails the approved speed thresholds. Kept because it is the "
                "only provider that never transmits your financial data.",
        "docs": None,
    },
    "openai": {
        "label": "OpenAI",
        "wire": "openai",
        "env_key": "OPENAI_API_KEY",
        "base_url": "https://api.openai.com/v1",
        "free_tier": False,
        "cost": "paid per token; see the pricing page",
        "docs": "https://platform.openai.com/docs/pricing",
    },
    "anthropic": {
        "label": "Anthropic (Claude)",
        "wire": "anthropic",
        "env_key": "ANTHROPIC_API_KEY",
        "base_url": "https://api.anthropic.com/v1",
        "free_tier": False,
        "cost": "paid per token; see the pricing page",
        "docs": "https://docs.anthropic.com/en/docs/about-claude/pricing",
    },
    "google": {
        "label": "Google Gemini (AI Studio)",
        "wire": "google",
        "env_key": "GEMINI_API_KEY",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "free_tier": True,
        "cost": "documents a free tier, but the quota has been REDUCED during "
                "2026 and published figures disagree (10/50/100/250/1500 "
                "requests per day). Treat the number as UNKNOWN and read the "
                "limits page.",
        "docs": "https://ai.google.dev/gemini-api/docs/rate-limits",
    },
    "groq": {
        "label": "Groq (OpenAI-compatible)",
        "wire": "openai",
        "env_key": "GROQ_API_KEY",
        "base_url": "https://api.groq.com/openai/v1",
        "free_tier": True,
        "cost": "documents a no-credit-card free tier. Published token limits "
                "disagree across sources (6k/min, 30k/min, 500k/day); UNKNOWN.",
        "docs": "https://console.groq.com/docs/rate-limits",
    },
    "openrouter": {
        "label": "OpenRouter (one key, many models)",
        "wire": "openai",
        "env_key": "OPENROUTER_API_KEY",
        "base_url": "https://openrouter.ai/api/v1",
        "free_tier": None,
        "cost": "routes to both free and paid models; the cost depends entirely "
                "on the model id you choose, so it cannot be stated here.",
        "docs": "https://openrouter.ai/docs",
    },
    "mistral": {
        "label": "Mistral AI",
        "wire": "openai",
        "env_key": "MISTRAL_API_KEY",
        "base_url": "https://api.mistral.ai/v1",
        "free_tier": None,
        "cost": "UNKNOWN; check the pricing page",
        "docs": "https://docs.mistral.ai/deployment/laplateforme/tier/",
    },
    "deepseek": {
        "label": "DeepSeek",
        "wire": "openai",
        "env_key": "DEEPSEEK_API_KEY",
        "base_url": "https://api.deepseek.com/v1",
        "free_tier": None,
        "cost": "UNKNOWN; check the pricing page",
        "docs": "https://api-docs.deepseek.com/quick_start/pricing",
    },
    "together": {
        "label": "Together AI",
        "wire": "openai",
        "env_key": "TOGETHER_API_KEY",
        "base_url": "https://api.together.xyz/v1",
        "free_tier": None,
        "cost": "UNKNOWN; check the pricing page",
        "docs": "https://docs.together.ai/docs/pricing",
    },
    "cerebras": {
        "label": "Cerebras",
        "wire": "openai",
        "env_key": "CEREBRAS_API_KEY",
        "base_url": "https://api.cerebras.ai/v1",
        "free_tier": True,
        "cost": "documents a free tier; the quota is UNKNOWN here",
        "docs": "https://inference-docs.cerebras.ai/support/pricing",
    },
    "xai": {
        "label": "xAI (Grok)",
        "wire": "openai",
        "env_key": "XAI_API_KEY",
        "base_url": "https://api.x.ai/v1",
        "free_tier": False,
        "cost": "paid per token; see the pricing page",
        "docs": "https://docs.x.ai/docs/models",
    },
    # AgentRouter is an AGGREGATOR, like OpenRouter: one key, many upstream
    # models. It is registered TWICE on purpose, because its own documentation
    # (co.agentrouter.org/portal, read 2026-08-27) states two DIFFERENT base
    # URLs and forbids mixing them:
    #
    #   OpenAI-compatible   https://co.agentrouter.org/v1     (/v1 REQUIRED)
    #   Anthropic-compatible https://co.agentrouter.org       (/v1 FORBIDDEN)
    #
    # VERBATIM from the FAQ: "Anthropic compatible (Claude family):
    # https://co.agentrouter.org, no /v1. OpenAI compatible (GPT etc.):
    # https://co.agentrouter.org/v1, /v1 required. Do not mix them." Its own
    # troubleshooting note says the wrong one 404s. One entry per dialect makes
    # the mistake unreachable instead of documenting it and hoping.
    #
    # free_tier is None, NOT True. Third-party write-ups advertise "$200 free
    # credits"; those are AFFILIATE pages with referral links, not the
    # provider's own documentation, and sign-up credit is not a free tier. The
    # official portal publishes no quota at all. UNKNOWN is the honest value,
    # and the spend gate therefore treats it as billable.
    "agentrouter": {
        "label": "AgentRouter (aggregator, OpenAI dialect)",
        "wire": "openai",
        "env_key": "AGENTROUTER_API_KEY",
        "base_url": "https://co.agentrouter.org/v1",
        "free_tier": None,
        "cost": "UNKNOWN. An aggregator: the cost depends entirely on the "
                "upstream model id you choose, and it publishes no quota. "
                "Sign-up credit advertised by third-party affiliate pages is "
                "NOT a free tier. Treated as billable.",
        "note": "This entry is the OpenAI dialect and its base URL ENDS IN "
                "/v1 -- required. For Claude models through the same key use "
                "the `agentrouter-anthropic` entry, whose URL has NO /v1. "
                "Mixing the two 404s, per the provider's own FAQ.",
        "docs": "https://co.agentrouter.org/portal",
    },
    "agentrouter-anthropic": {
        "label": "AgentRouter (aggregator, Anthropic dialect)",
        "wire": "anthropic",
        "env_key": "AGENTROUTER_API_KEY",
        "base_url": "https://co.agentrouter.org",
        "free_tier": None,
        "cost": "UNKNOWN, as for the OpenAI dialect. Same key, same balance.",
        "note": "Claude-family models. The base URL has NO /v1 -- the "
                "provider's FAQ states the Anthropic dialect 404s if /v1 is "
                "appended. Shares AGENTROUTER_API_KEY with the OpenAI entry: "
                "one key, unified quota metering, per the portal.",
        "docs": "https://co.agentrouter.org/portal",
    },
    "custom": {
        "label": "Any OpenAI-compatible endpoint (LM Studio, Ollama, vLLM, ...)",
        "wire": "openai",
        "env_key": "CUSTOM_API_KEY",
        "base_url": None,          # supplied by the user; there is no default
        "free_tier": None,
        "cost": "depends entirely on what you point it at",
        "note": "Set --base-url. This is also how you drive a SECOND local "
                "server (llama.cpp --server, Ollama, LM Studio) without "
                "leaving your machine.",
        "docs": None,
    },
}

# Providers that are free of charge with certainty, for the panel's default sort.
# `openrouter` is deliberately absent: it can be free or paid depending on the
# model id, and a list that implied otherwise would be a false claim.
KNOWN_FREE_TIER = tuple(
    sorted(k for k, v in PROVIDERS.items() if v.get("free_tier") is True))


def provider_names() -> List[str]:
    """Registry keys, `local` first and the rest alphabetical."""
    rest = sorted(k for k in PROVIDERS if k != "local")
    return ["local"] + rest


def get_provider(name: str) -> Dict[str, Any]:
    """
    The registry entry for `name`.

    Raises rather than falling back to a default. A typo that silently selected
    a different provider could send financial data somewhere the user did not
    choose, or spend money on an account they did not mean to use.
    """
    if not isinstance(name, str) or not name.strip():
        raise ProviderError("no provider named. Choose one of: %s"
                            % ", ".join(provider_names()))
    key = name.strip().lower()
    if key not in PROVIDERS:
        raise ProviderError(
            "unknown provider %r. Known providers: %s. Refusing to guess, "
            "because guessing could transmit your data to a service you did "
            "not choose." % (name, ", ".join(provider_names())))
    return dict(PROVIDERS[key])


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------
# Deliberately the same shape as src/market/alpha_vantage.py:get_api_key -- read
# from the environment, never from a file in the repository, and refuse a
# malformed value rather than transmit it.
_KEY_RE = re.compile(r"^[\x21-\x7e]{16,512}$")


def get_api_key(provider: str, explicit: Optional[str] = None) -> Optional[str]:
    """
    The credential for `provider`, from the argument or its environment
    variable. Returns None for providers that need no key (`local`).

    Never read from a file in the repository. `.env` is in .gitignore and is not
    consulted by this function; the caller loads it if it wants to.
    """
    spec = get_provider(provider)
    env = spec.get("env_key")
    if env is None:
        return None

    key = explicit if explicit is not None else os.environ.get(env, "")
    key = str(key).strip()

    if not key:
        raise ProviderError(
            "no API key for %s. Set %s in the environment. Free key: %s. It is "
            "read from the environment and never stored in the repository."
            % (spec["label"], env, spec.get("docs") or "see the provider docs"))

    # A placeholder that reaches the wire produces an authentication error that
    # reads like an outage, and the user then debugs the network instead of the
    # copy-paste. Refuse the well-known placeholders by name.
    low = key.lower()
    for bad in ("your_api_key", "your-api-key", "sk-xxx", "changeme",
                "paste_here", "todo", "<your", "demo", "test"):
        if low == bad or low.startswith(bad):
            raise ProviderError(
                "the value of %s looks like a placeholder, not a key. Refusing "
                "to send it: a placeholder returns an auth error that is hard "
                "to tell apart from a provider outage." % env)

    if not _KEY_RE.match(key):
        raise ProviderError(
            "the value of %s does not look like an API key (expected 16-512 "
            "printable non-space characters, got %d character(s)). Refusing to "
            "send it rather than have the failure look like a provider problem. "
            "A stray newline or quote from copy-paste is the usual cause."
            % (env, len(key)))
    return key


def redact(text: Any, *keys: Optional[str]) -> str:
    """
    Remove credentials from anything about to be logged, printed or raised.

    Takes several keys because a merged panel view may hold more than one, and
    an error message assembled from two providers must not leak either.
    """
    out = str(text)
    for key in keys:
        if key and len(str(key)) >= 8:
            out = out.replace(str(key), "[REDACTED-API-KEY]")
    # Belt and braces: catch anything that LOOKS like a key even if it was not
    # passed in, so a mistake in the caller cannot leak a credential.
    #
    # DEFECT FOUND BY ADVERSARIAL TEST 2026-08-27. The first version of this
    # pattern was `(sk|gsk|xai|sk-or|sk-ant)-...` -- hyphen only. MEASURED: a
    # Groq key of the real shape `gsk_abcdefghij1234567890XYZ` passed through
    # UNREDACTED, because Groq separates its prefix with an UNDERSCORE. That is
    # a live credential leak into any log line, and it was invisible until a
    # test asserted on a realistically shaped key rather than a made-up one.
    # Both separators are now accepted, and the prefix list is anchored so a
    # bare "sk" inside another word cannot match.
    # The prefix list is VERIFIED against provider documentation and multiple
    # independent examples (2026-08-27), not guessed: sk- / sk-proj- (OpenAI),
    # sk-ant- (Anthropic), sk-or- (OpenRouter), gsk_ (Groq, UNDERSCORE),
    # csk- (Cerebras), xai- (xAI), fw_ (Fireworks), hf_ (Hugging Face),
    # r8_ (Replicate).
    out = re.sub(r"(?<![A-Za-z0-9])"
                 r"(sk|gsk|csk|xai|fw|hf|r8|sk-or|sk-ant|sk-proj)"
                 r"[-_][A-Za-z0-9_\-]{12,}", "[REDACTED-API-KEY]", out)
    out = re.sub(r"(?<![A-Za-z0-9])AIza[A-Za-z0-9_\-]{20,}",
                 "[REDACTED-API-KEY]", out)
    # Anthropic admin keys and OpenRouter both use long opaque tails; catch any
    # long high-entropy token that follows an obvious key label.
    out = re.sub(r"(?i)\b(api[-_]?key|authorization|bearer|x-api-key)"
                 r"(\s*[:=]\s*|\s+)([A-Za-z0-9_\-]{16,})",
                 r"\1\2[REDACTED-API-KEY]", out)
    return out


def credential_status() -> List[Dict[str, Any]]:
    """
    Which providers are configured, WITHOUT revealing any key.

    Reports only presence and length. `local` is always ready. This is what the
    panel renders, so it must never carry key material.
    """
    rows = []
    for name in provider_names():
        spec = PROVIDERS[name]
        env = spec.get("env_key")
        if env is None:
            rows.append({"provider": name, "label": spec["label"],
                         "env_key": None, "configured": True,
                         "key_length": None, "free_tier": spec.get("free_tier"),
                         "needs_base_url": False})
            continue
        raw = str(os.environ.get(env, "")).strip()
        rows.append({
            "provider": name,
            "label": spec["label"],
            "env_key": env,
            "configured": bool(raw),
            "key_length": len(raw) if raw else 0,
            "free_tier": spec.get("free_tier"),
            "needs_base_url": spec.get("base_url") is None,
        })
    return rows


def resolve_base_url(provider: str, explicit: Optional[str] = None) -> Optional[str]:
    """
    The endpoint for `provider`.

    `custom` has no default on purpose: a default would silently send a request
    somewhere the user never named.
    """
    spec = get_provider(provider)
    url = (explicit or "").strip() or spec.get("base_url")
    if spec["wire"] == "local":
        return None
    if not url:
        raise ProviderError(
            "provider %r has no endpoint. Pass --base-url. There is no default, "
            "because a default here would send your prompt to a host you did "
            "not choose." % provider)
    if not (url.startswith("https://") or url.startswith("http://")):
        raise ProviderError(
            "endpoint %r is not an http(s) URL" % url)
    if url.startswith("http://") and not re.match(
            r"^http://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?(/|$)", url):
        raise ProviderError(
            "refusing plaintext http:// to a non-local host (%r). An API key "
            "sent over http is readable in transit. Use https, or point at "
            "localhost for a local server." % url)
    return url.rstrip("/")
