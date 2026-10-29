"""
Provider settings the owner edits from the web UI (D-0142).

WHAT IS STORED, AND WHAT NEVER IS
---------------------------------
The owner chose option A on 2026-10-28: settings live in a file in the USER's
home folder (``~/.marfin/providers.json``), outside the repository, and API
KEYS STAY IN ENVIRONMENT VARIABLES. This file holds only:

  * which engine answers questions: ``local`` (the default) or ``remote``
  * for remote: the provider name, the model id and the paid-provider switch
  * per built-in provider: an optional base-URL and model-id override
  * user-defined providers: label, dialect, base URL, the NAME of the variable
    that holds the key, and a model id

A key value is refused at every entry point, not merely "not written": every
string is passed through ``providers.redact`` and a value that redaction would
change is rejected as "looks like an API key". A field whitelist rejects any
other name, so a future form field called ``api_key`` cannot slip through.

FAILURE POLICY
--------------
* A missing file is the default settings (local engine), not an error.
* A corrupt or invalid file RAISES. Silently replacing it with defaults would
  throw away the owner's providers without telling them.
* Writes are atomic (temp file + ``os.replace``) and validated BEFORE writing,
  so a rejected change leaves the previous file untouched.
"""
from __future__ import annotations

import copy
import json
import os
import re
import tempfile
from typing import Any, Dict, List, Optional

from . import providers as P

DEFAULT_PATH = os.path.join(os.path.expanduser("~"), ".marfin", "providers.json")
VERSION = 1
ENGINES = ("local", "remote")
_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+\-]{0,127}$")
_TOP_FIELDS = ("version", "active", "overrides", "custom")
_ACTIVE_FIELDS = ("engine", "provider", "model_id", "allow_paid")
_OVERRIDE_FIELDS = ("base_url", "model_id")
_CUSTOM_FIELDS = ("label", "wire", "base_url", "env_key", "model_id")


class SettingsError(ValueError):
    """The settings are invalid or could not be read. Never carries a key."""


def defaults() -> Dict[str, Any]:
    return {"version": VERSION,
            "active": {"engine": "local", "provider": None, "model_id": None, "allow_paid": False},
            "overrides": {}, "custom": {}}


def _no_secret(where: str, value: Any) -> None:
    if isinstance(value, str) and P.redact(value) != value:
        raise SettingsError("%s looks like an API key. Keys are never saved: put the key in an "
                            "environment variable and enter only the variable's NAME." % where)


def _only(where: str, d: Any, allowed) -> Dict[str, Any]:
    if not isinstance(d, dict):
        raise SettingsError("%s must be an object" % where)
    extra = sorted(set(d) - set(allowed))
    if extra:
        raise SettingsError("%s: unknown field(s) %s" % (where, ", ".join(map(repr, extra))))
    for k, v in d.items():
        _no_secret("%s.%s" % (where, k), v)
    return d


def _model(where: str, value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    v = str(value).strip()
    if not _MODEL_RE.match(v):
        raise SettingsError("%s: %r is not a model id (letters, digits and ._:/@+- only, "
                            "up to 128 characters)" % (where, value))
    return v


def validate(data: Any) -> Dict[str, Any]:
    """A clean copy of `data`, or SettingsError. Never mutates its argument."""
    d = copy.deepcopy(data)
    _only("settings", d, _TOP_FIELDS)
    if d.get("version", VERSION) != VERSION:
        raise SettingsError("settings version %r is not supported (expected %d)" % (d.get("version"), VERSION))
    out = defaults()

    custom = _only("custom", d.get("custom") or {}, list(d.get("custom") or {}))
    clean_custom = {}
    for name, spec in custom.items():
        spec = _only("custom.%s" % name, spec, _CUSTOM_FIELDS)
        model = _model("custom.%s.model_id" % name, spec.get("model_id"))
        try:
            P.validate_user_provider(name, {k: spec.get(k) for k in ("label", "wire", "base_url", "env_key")})
        except P.ProviderError as exc:
            raise SettingsError(str(exc))
        clean_custom[name] = {"label": str(spec.get("label") or name).strip(), "wire": spec["wire"],
                              "base_url": str(spec["base_url"]).strip().rstrip("/"),
                              "env_key": (str(spec["env_key"]).strip() if spec.get("env_key") else None),
                              "model_id": model}
    out["custom"] = clean_custom

    overrides = _only("overrides", d.get("overrides") or {}, list(d.get("overrides") or {}))
    clean_over = {}
    for name, ov in overrides.items():
        if name not in P.PROVIDERS or name == "local":
            raise SettingsError("overrides.%s: only built-in remote providers take an override" % name)
        ov = _only("overrides.%s" % name, ov, _OVERRIDE_FIELDS)
        entry = {}
        if ov.get("base_url"):
            why = P.endpoint_problem(ov["base_url"])
            if why:
                raise SettingsError("overrides.%s.base_url: %s" % (name, why))
            entry["base_url"] = str(ov["base_url"]).strip().rstrip("/")
        m = _model("overrides.%s.model_id" % name, ov.get("model_id"))
        if m:
            entry["model_id"] = m
        if entry:
            clean_over[name] = entry
    out["overrides"] = clean_over

    act = _only("active", d.get("active") or {}, _ACTIVE_FIELDS)
    engine = act.get("engine", "local")
    if engine not in ENGINES:
        raise SettingsError("active.engine must be one of %s, got %r" % (", ".join(ENGINES), engine))
    allow_paid = act.get("allow_paid", False)
    if not isinstance(allow_paid, bool):
        raise SettingsError("active.allow_paid must be true or false")
    prov = act.get("provider") or None
    if prov is not None:
        if prov == "local" or (prov not in P.PROVIDERS and prov not in clean_custom):
            raise SettingsError("active.provider %r is not a remote provider" % (prov,))
    if engine == "remote" and prov is None:
        raise SettingsError("the online engine needs a provider")
    out["active"] = {"engine": engine, "provider": prov,
                     "model_id": _model("active.model_id", act.get("model_id")), "allow_paid": allow_paid}
    return out


def load(path: str = DEFAULT_PATH) -> Dict[str, Any]:
    """The settings at `path`; defaults if the file does not exist; SettingsError if it is bad."""
    if not os.path.exists(path):
        return defaults()
    try:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        raise SettingsError("could not read %s: %s. The file was left untouched; fix or delete it."
                            % (path, type(exc).__name__))
    return validate(raw)


def save(data: Dict[str, Any], path: str = DEFAULT_PATH) -> Dict[str, Any]:
    """Validate, then write atomically. Returns what was written."""
    clean = validate(data)
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".providers.", suffix=".tmp", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(clean, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        try:
            os.chmod(tmp, 0o600)
        except OSError:                                  # Windows: ACLs, not mode bits
            pass
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return clean


def apply(settings: Dict[str, Any]) -> List[str]:
    """Register the user-defined providers in the live registry (all or nothing)."""
    return P.register_user_providers({n: {k: s.get(k) for k in ("label", "wire", "base_url", "env_key")}
                                      for n, s in settings.get("custom", {}).items()})


def effective(settings: Dict[str, Any], provider: str) -> Dict[str, Optional[str]]:
    """The base URL and model id that a call to `provider` would use, with their origin."""
    spec = P.get_provider(provider)
    ov = settings.get("overrides", {}).get(provider, {})
    cu = settings.get("custom", {}).get(provider, {})
    base = ov.get("base_url") or spec.get("base_url")
    model = ov.get("model_id") or cu.get("model_id")
    act = settings.get("active", {})
    if act.get("provider") == provider and act.get("model_id"):
        model = act["model_id"]
    return {"base_url": base, "model_id": model,
            "base_url_origin": "override" if ov.get("base_url") else ("user" if cu else "built-in")}


def provider_rows(settings: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Every selectable remote provider with key PRESENCE only (never a value)."""
    rows = []
    for name in [n for n in P.provider_names() if n != "local"] + P.user_provider_names():
        spec = P.get_provider(name)
        env = spec.get("env_key")
        eff = effective(settings, name)
        rows.append({"provider": name, "label": spec["label"], "wire": spec["wire"], "env_key": env,
                     "key_set": bool(env and str(os.environ.get(env, "")).strip()),
                     "key_needed": bool(env), "base_url": eff["base_url"], "model_id": eff["model_id"],
                     "base_url_origin": eff["base_url_origin"], "free_tier": spec.get("free_tier"),
                     "user_defined": bool(spec.get("user_defined"))})
    return rows
