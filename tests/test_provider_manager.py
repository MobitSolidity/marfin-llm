# -*- coding: utf-8 -*-
"""
D-0142: the providers manager -- user-defined providers, the settings store,
the no-cost connection test, redirect refusal, and the online/offline engine on
the ask page.

Offline: no test here opens a socket to the internet. The redirect tests use two
LOOPBACK servers started in this process. (V) verified invariant, (A)
adversarial -- must refuse, (M) measured on a live loopback socket.
"""
import datetime
import http.server
import json
import os
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from _harness import check, check_raises, check_true, section, summary  # noqa: E402
import _fake_data as FD                                                  # noqa: E402
from llm import clients as C                                             # noqa: E402
from llm import providers as P                                           # noqa: E402
from llm import settings as S                                            # noqa: E402

TMP = tempfile.mkdtemp(prefix="marfin_provmgr_")
NOW = datetime.datetime(2026, 10, 28, tzinfo=datetime.timezone.utc)
_SAVED_ENV = dict(os.environ)
GOOD = {"label": "My Lab", "wire": "openai", "base_url": "https://api.mylab.example/v1/",
        "env_key": "MYLAB_API_KEY", "model_id": "llama-x"}


def fresh(name="s.json"):
    d = tempfile.mkdtemp(dir=TMP)
    return os.path.join(d, "sub", name)


# ===========================================================================
section("registry: user-defined providers beside the reviewed built-ins")
# ===========================================================================
check("built-in census unchanged (user entries never enter PROVIDERS)", len(P.PROVIDERS), 14, method="(V)")
P.register_user_providers({"mylab": GOOD})
spec = P.get_provider("mylab")
check_true("a registered user provider resolves, trailing slash stripped",
           spec["base_url"] == "https://api.mylab.example/v1" and spec["user_defined"] is True, "(V)")
check_true("a user provider's cost is UNKNOWN, never free", spec["free_tier"] is None, "(V)")
check_true("PROVIDERS still has 14 after registration", len(P.PROVIDERS) == 14, "(V)")
check_raises("the spend gate treats a remote user provider as billable",
             lambda: C.spend_gate("mylab", base_url=spec["base_url"]), P.ProviderError)
check_true("... but a loopback user endpoint is not billable",
           C.spend_gate("mylab", base_url="http://localhost:1234/v1")["billable"] is False, "(V)")
for bad, why in (({"wire": "openai", "base_url": "http://evil.example/v1", "env_key": "A_API_KEY"}, "plain http to a remote host"),
                 ({"wire": "openai", "base_url": "ftp://a/b", "env_key": "A_API_KEY"}, "non-http scheme"),
                 ({"wire": "openai", "base_url": "https://a.example/\"><x>", "env_key": "A_API_KEY"}, "markup in the URL"),
                 ({"wire": "grpc", "base_url": "https://a.example", "env_key": "A_API_KEY"}, "unknown dialect"),
                 ({"wire": "openai", "base_url": "https://a.example", "env_key": None}, "remote endpoint without a key variable"),
                 ({"wire": "openai", "base_url": "https://a.example", "env_key": "lower"}, "malformed variable name"),
                 ({"wire": "openai", "base_url": "https://a.example", "env_key": "FRED_API_KEY"}, "a data-source key"),
                 ({"wire": "openai", "base_url": "https://a.example", "env_key": "ALPHAVANTAGE_API_KEY"}, "the market-data key")):
    check_raises("refused: %s" % why, lambda b=bad: P.validate_user_provider("x1", b), P.ProviderError)
check_raises("refused: a user entry named like a built-in (no shadowing)",
             lambda: P.validate_user_provider("openai", GOOD), P.ProviderError)
check_raises("refused: a malformed provider name", lambda: P.validate_user_provider("My Lab", GOOD), P.ProviderError)
# D-0142 mutation round: each of these let a weakened guard survive the first battery run.
for url, why in (("https://", "an https URL with no host"),
                 ("https://user:pw@api.example/v1", "credentials inside the URL"),
                 ("http://localhost.evil.example/v1", "a remote host whose name starts with 'localhost'"),
                 ("http://127.0.0.1.evil.example/v1", "a remote host whose name starts with '127.0.0.1'")):
    check_raises("refused endpoint: %s" % why,
                 lambda u=url: P.validate_user_provider("x1", {"wire": "openai", "base_url": u, "env_key": "A_API_KEY"}),
                 P.ProviderError)
check_true("'localhost.evil.example' is not loopback (the match is anchored at the host's end)",
           not P.is_loopback_url("http://localhost.evil.example/") and P.is_loopback_url("http://localhost:1234/v1"), "(A)")
P._USER_PROVIDERS["openai"] = dict(P.validate_user_provider("evil1", GOOD), label="Evil")
try:
    _o = P.get_provider("openai")
    check_true("even a polluted user registry cannot shadow a built-in (built-ins resolve first)",
               _o["label"] != "Evil" and _o.get("user_defined") is not True, "(A) defence in depth")
finally:
    P._USER_PROVIDERS.pop("openai", None)
check_raises("register is all-or-nothing: one bad entry keeps the old set",
             lambda: P.register_user_providers({"ok1": GOOD, "bad": {"wire": "x"}}), P.ProviderError)
check_true("... and the previous registration survived", P.user_provider_names() == ["mylab"], "(A)")
check_true("loopback endpoint needs no key variable",
           P.validate_user_provider("lm", {"wire": "openai", "base_url": "http://localhost:1234/v1"})["env_key"] is None, "(V)")
P.register_user_providers({})
check_raises("an unregistered name is refused, never guessed", lambda: P.get_provider("mylab"), P.ProviderError)

# ===========================================================================
section("settings store: keys never stored, atomic, validated, corrupt file kept")
# ===========================================================================
path = fresh()
check_true("a missing file is the defaults (local engine), not an error", S.load(path) == S.defaults(), "(V)")
good = {"active": {"engine": "remote", "provider": "mylab", "model_id": "llama-x", "allow_paid": False},
        "custom": {"mylab": GOOD}, "overrides": {"groq": {"base_url": "https://proxy.example/v1", "model_id": "m"}}}
w = S.save(good, path)
check_true("save round-trips through load", S.load(path) == w, "(V)")
check_true("no temp file left behind", not [f for f in os.listdir(os.path.dirname(path)) if f.startswith(".providers")], "(V)")
if os.name != "nt":
    check("file mode is 0600 (owner only)", os.stat(path).st_mode & 0o777, 0o600, method="(V)")
before = open(path).read()
for where, bad in (("model id", dict(good, active=dict(good["active"], model_id="sk-proj-AAAAAAAAAAAAAAAAAAAAAAAA"))),
                   ("label", {"custom": {"x1": dict(GOOD, label="gsk_abcdefghij1234567890XYZ")}}),
                   ("base url", {"custom": {"x1": dict(GOOD, base_url="https://a.example/v1?key=AIzaSyAAAAAAAAAAAAAAAAAAAAAA")}})):
    check_raises("an API key typed into the %s is refused" % where, lambda b=bad: S.save(b, path), S.SettingsError)
check_raises("an unknown field (api_key) is refused", lambda: S.save({"custom": {"x1": dict(GOOD, api_key="v")}}, path),
             S.SettingsError)
check_raises("an unknown top-level field is refused", lambda: S.save({"keys": {}}, path), S.SettingsError)
check_raises("override on local is refused", lambda: S.save({"overrides": {"local": {"model_id": "a"}}}, path), S.SettingsError)
check_raises("override on an unknown provider is refused",
             lambda: S.save({"overrides": {"nosuch": {"model_id": "a"}}}, path), S.SettingsError)
check_raises("override on a user-defined provider is refused (edit the provider itself)",
             lambda: S.save({"custom": {"mylab": GOOD}, "overrides": {"mylab": {"model_id": "a"}}}, path), S.SettingsError)
check_raises("override with a bad endpoint is refused",
             lambda: S.save({"overrides": {"groq": {"base_url": "http://evil.example"}}}, path), S.SettingsError)
check_raises("online engine without a provider is refused", lambda: S.save({"active": {"engine": "remote"}}, path), S.SettingsError)
check_raises("an engine typo is refused", lambda: S.save({"active": {"engine": "cloud"}}, path), S.SettingsError)
check_raises("allow_paid must be a real boolean", lambda: S.save({"active": {"allow_paid": "yes"}}, path), S.SettingsError)
check_raises("'local' is not an online provider", lambda: S.save({"active": {"engine": "remote", "provider": "local"}}, path),
             S.SettingsError)
check_raises("a model id with a space is refused", lambda: S.save({"overrides": {"groq": {"model_id": "a b"}}}, path),
             S.SettingsError)
check_raises("an unknown settings version is refused", lambda: S.save({"version": 2}, path), S.SettingsError)
check_true("the file is byte-identical after every refusal", open(path).read() == before, "(A)")
check_true("the saved file carries nothing redact() would change", P.redact(before) == before, "(V)")
src = {"active": {"engine": "local"}}
S.validate(src)
check_true("validate never mutates its argument", src == {"active": {"engine": "local"}}, "(V)")
open(path, "w").write("{broken")
check_raises("a corrupt file raises (it is never silently reset)", lambda: S.load(path), S.SettingsError)
check_true("... and the corrupt file is left exactly as it was", open(path).read() == "{broken", "(A)")
S.apply(w)
eff = S.effective(w, "groq")
check_true("an override wins over the built-in base URL", eff["base_url"] == "https://proxy.example/v1"
           and eff["base_url_origin"] == "override", "(V)")
check_true("the active model wins for the active provider", S.effective(w, "mylab")["model_id"] == "llama-x", "(V)")
os.environ["MYLAB_API_KEY"] = "abcdEFGH12345678wxyz"
rows = {r["provider"]: r for r in S.provider_rows(w)}
check("one row per selectable remote provider (13 built-in + 1 user)", len(rows), 14, method="(V)")
check_true("key presence is reported, the value never is",
           rows["mylab"]["key_set"] is True and "abcdEFGH12345678wxyz" not in json.dumps(list(rows.values())), "(A)")
P.register_user_providers({})

# ===========================================================================
section("connection test: model list, no tokens, no redirect, key redacted")
# ===========================================================================
os.environ["GROQ_API_KEY"] = "gsk_FAKEFAKEFAKEFAKE1234"
seen = {}


def getter(url, headers, timeout, key):
    seen.update(url=url, headers=dict(headers))
    return {"status": 200, "body_json": {"data": [{"id": "b"}, {"id": "a"}, {"id": "a"}, {"x": 1}, "junk"]}}


r = C.list_models("groq", getter=getter)
check_true("OpenAI dialect: GET {base}/models with a bearer key", seen["url"] == "https://api.groq.com/openai/v1/models"
           and seen["headers"]["Authorization"].startswith("Bearer gsk_"), "(V)")
check_true("ids de-duplicated and sorted; junk rows skipped", r["models"] == ["a", "b"] and r["count"] == 2, "(V)")
os.environ["ANTHROPIC_API_KEY"] = "sk-ant-FAKEFAKEFAKEFAKE12"
C.list_models("anthropic", getter=lambda u, h, t, k: seen.update(ah=h) or {"status": 200, "body_json": {"data": [{"id": "c"}]}})
check_true("Anthropic dialect: x-api-key + anthropic-version, no bearer",
           set(seen["ah"]) == {"x-api-key", "anthropic-version"}, "(V)")
os.environ["GEMINI_API_KEY"] = "AIzaFAKEFAKEFAKEFAKEFAKE12"
g = C.list_models("google", getter=lambda u, h, t, k: seen.update(gh=h) or {
    "status": 200, "body_json": {"models": [{"name": "models/gemini-x"}]}})
check_true("Gemini dialect: x-goog-api-key, 'models/' prefix removed", "x-goog-api-key" in seen["gh"]
           and g["models"] == ["gemini-x"], "(V)")
for st, body, what in ((401, {}, "a rejected key"), (302, None, "a redirect"), (200, {"error": "x"}, "a non-list body"),
                       (200, "html", "a non-JSON body"), (500, None, "a server error")):
    try:
        C.list_models("groq", getter=lambda u, h, t, k, s=st, b=body: {
            "status": s, "body_json": b, "body_text": "", "location": "https://evil.example/?k=gsk_FAKEFAKEFAKEFAKE1234"})
        check_true("%s is refused" % what, False, "(A) no error")
    except C.RemoteCallError as exc:
        check_true("%s is refused and the key is not in the message" % what, "FAKEFAKE" not in str(exc), "(A)")
check_raises("the local model has no endpoint to test", lambda: C.list_models("local"), P.ProviderError)


def _err(fn):
    try:
        fn()
    except Exception as exc:                                        # noqa: BLE001
        return "%s: %s" % (type(exc).__name__, exc)
    return None


check_true("... and says so (not a confusing 'unsupported dialect')",
           "no network endpoint" in (_err(lambda: C.list_models("local")) or ""), "(A)")
check_true("a 3xx that carries a model list is still refused, and says it was NOT followed",
           "NOT followed" in (_err(lambda: C.list_models("groq", getter=lambda u, h, t, k: {
               "status": 302, "body_json": {"data": [{"id": "x"}]}, "body_text": "",
               "location": "https://evil.example/"})) or ""), "(A)")
_leak = C.list_models("groq", getter=lambda u, h, t, k: {"status": 200, "body_json": {"data": [{"id": "echo-" + k}]}})
check_true("a model id that echoes the key back is redacted",
           "FAKEFAKE" not in json.dumps(_leak) and _leak["count"] == 1, "(A)")

got = {}


class _Target(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        got["auth"] = self.headers.get("Authorization")
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"data":[{"id":"stolen"}]}')
    do_POST = do_GET

    def log_message(self, *a):
        pass


class _Redirect(http.server.BaseHTTPRequestHandler):
    def _go(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self.send_response(302)
        self.send_header("Location", "http://127.0.0.1:%d/steal" % TGT.server_port)
        self.end_headers()
    do_GET = do_POST = _go

    def log_message(self, *a):
        pass


TGT = http.server.HTTPServer(("127.0.0.1", 0), _Target)
RED = http.server.HTTPServer(("127.0.0.1", 0), _Redirect)
for _s in (TGT, RED):
    threading.Thread(target=_s.serve_forever, daemon=True).start()
P.register_user_providers({"redir": {"wire": "openai", "base_url": "http://127.0.0.1:%d/v1" % RED.server_port,
                                     "env_key": "REDIR_API_KEY"},
                           "direct": {"wire": "openai", "base_url": "http://127.0.0.1:%d/v1" % TGT.server_port}})
os.environ["REDIR_API_KEY"] = "sk-FAKEFAKEFAKEFAKE9999"
check_raises("a real 302 on the model list is refused", lambda: C.list_models("redir"), C.RemoteCallError)
check_true("... and the key never reached the redirect target", got.get("auth") is None, "(M)")
try:
    C.chat("redir", "hi", 5, model_id="m", allow_paid=True, retries=1)
    check_true("a real 302 on chat is refused", False, "(M) no error")
except C.RemoteCallError as exc:
    check_true("a real 302 on chat is refused, says why, leaks nothing",
               "NOT followed" in str(exc) and "FAKEFAKE" not in str(exc) and got.get("auth") is None, "(M)")
d = C.list_models("direct")
check_true("a loopback server without a key lists its models over a real socket",
           d["models"] == ["stolen"] and d["http_status"] == 200, "(M)")
RED.shutdown()
TGT.shutdown()
P.register_user_providers({})

# ===========================================================================
section("web UI: providers manager and the online/offline engine on the ask page")
# ===========================================================================
import ui as U                                                           # noqa: E402


class Bot(object):
    def __init__(self, tag):
        self.tag, self.asked, self.audit = tag, [], None

    def answer(self, q):
        self.asked.append(q)
        return {"question": q, "lang": "fa", "route": "plain", "data_as_of": None, "warnings": [],
                "reply": self.tag + " reply", "tool_results": [], "evidence": [], "notices": [], "check": None}


remote, local, built, listed = Bot("REMOTE"), Bot("LOCAL"), [], []


def factory(app):
    built.append(1)
    return remote, app.remote_label()


def lister(name, base_url=None):
    listed.append((name, base_url))
    if name == "groq":
        raise P.ProviderError("Groq: model list failed (HTTP 401). key=gsk_abcdefghij1234567890XYZ")
    return {"ok": True, "http_status": 200, "count": 3, "models": ["m1", "<script>x</script>", "m3"]}


sp = fresh("providers.json")


def mk(**kw):
    d = tempfile.mkdtemp(dir=TMP)
    kw.setdefault("paper_dir", os.path.join(d, "paper"))
    kw.setdefault("ask_audit_path", os.path.join(d, "ask.jsonl"))
    kw.setdefault("clock", lambda: NOW)
    kw.setdefault("hub", FD.hub())
    kw.setdefault("settings_path", sp)
    return U.App(**kw)


A = mk(assistant=local, model_label="q.gguf", remote_factory=factory, lister=lister)


def post(path, app=None, **f):
    app = app or A
    f["csrf"] = app.csrf
    return app.handle("POST", path, form=f)


def saved():
    return json.load(open(sp))


b = A.handle("GET", "/providers").body
check("13 built-in remote providers, each with a test button", b.count('value="test"'), 13, method="(V)")
check_true("a GET never creates the settings file", not os.path.exists(sp), "(V)")
r = post("/providers", action="save_custom", name="mylab", label="My Lab", wire="openai",
         base_url="https://api.mylab.example/v1/", env_key="MYLAB_API_KEY", model_id="llama-x")
check_true("a custom provider is saved and listed", "mylab" in r.body and "mylab" in saved()["custom"], "(V)")
r = post("/providers", action="save_custom", name="evil", wire="openai", base_url="http://evil.example/v1",
         env_key="EVIL_API_KEY")
check_true("plain http to a remote host refused on the page, not saved",
           "انجام نشد" in r.body and "evil" not in saved()["custom"], "(A)")
r = post("/providers", action="save_custom", name="k1", wire="openai", base_url="https://a.example/v1",
         env_key="K1_API_KEY", model_id="sk-proj-AAAAAAAAAAAAAAAAAAAAAAAA")
check_true("a key typed into a field is refused and NOT echoed back",
           "looks like an API key" in r.body and "AAAAAAAAAAAAAAAAAAAA" not in r.body, "(A)")
r = post("/providers", action="save_custom", name="x3", wire="openai", base_url='https://a.example/"><img src=x>',
         env_key="X3_API_KEY")
check_true("markup in a URL is refused and escaped", "<img src=x>" not in r.body, "(A)")
r = post("/providers", action="save_override", name="groq", base_url="https://proxy.example/openai/v1", model_id="m70")
check_true("a built-in base URL override is saved and marked as changed",
           "proxy.example" in r.body and "تغییر داده‌اید" in r.body, "(V)")
check_true("override on local refused", "انجام نشد" in post("/providers", action="save_override", name="local",
                                                            model_id="a").body, "(A)")
post("/providers", action="clear_override", name="groq")
check_true("an override is cleared back to the default", "groq" not in saved()["overrides"], "(V)")
r = post("/providers", action="test", name="mylab")
check_true("connection test: count shown, model ids escaped", "3 مدل" in r.body and "<script>x</script>" not in r.body,
           "(A)")
check_true("connection test uses the effective base URL", listed[-1] == ("mylab", "https://api.mylab.example/v1"), "(V)")
r = post("/providers", action="test", name="groq")
check_true("a failed test is shown with the key redacted", "connection test failed" in r.body
           and "gsk_abcdefghij" not in r.body, "(A)")
check_true("test on local refused", "no network endpoint" in post("/providers", action="test", name="local").body, "(A)")
check_true("an unknown action is refused", "unknown action" in post("/providers", action="bogus").body, "(A)")
r = A.handle("POST", "/providers", form={"csrf": "bad", "action": "save_custom", "name": "zz", "wire": "openai",
                                         "base_url": "https://a.example", "env_key": "Z_API_KEY"})
check_true("CSRF enforced on the providers form", r.status == 403 and "zz" not in saved()["custom"], "(A)")
b = A.handle("GET", "/ask").body
check_true("ask: offline is the default; online disabled until a provider is chosen",
           'value="local" checked' in b and 'value="remote" disabled' in b, "(V)")
r = post("/ask", question="سلام", engine="local")
check_true("offline answer comes from the local model and is tagged",
           "LOCAL reply" in r.body and "آفلاین · q.gguf" in r.body and local.asked == ["سلام"], "(V)")
post("/providers", action="set_engine", engine="remote", provider="mylab", model_id="")
check_true("the engine choice is saved", saved()["active"] == {"engine": "remote", "provider": "mylab",
                                                              "model_id": None, "allow_paid": False}, "(V)")
b = A.handle("GET", "/ask").body
check_true("ask: online is now the default and names provider:model",
           'value="remote" checked' in b and "mylab: llama-x" in b, "(V)")
r = post("/ask", question="q2")
check_true("online answer comes from the remote engine and is tagged",
           "REMOTE reply" in r.body and "آنلاین · mylab: llama-x" in r.body and remote.asked == ["q2"], "(V)")
post("/ask", question="q3", engine="local")
check_true("the engine can be switched per question", local.asked[-1] == "q3", "(V)")
post("/ask", question="q4", engine="remote")
check("the remote engine is built once and reused", len(built), 1, method="(V)")
post("/providers", action="save_override", name="groq", model_id="abc")
post("/ask", question="q5", engine="remote")
check("a settings change rebuilds it", len(built), 2, method="(V)")
check_true("an unknown engine is refused", "موتور ناشناخته" in post("/ask", question="q", engine="cloud").body, "(A)")
post("/providers", action="delete_custom", name="mylab")
check_true("deleting the active provider falls back to offline",
           saved()["active"]["engine"] == "local" and "mylab" not in P.user_provider_names(), "(V)")
check_true("a built-in cannot be deleted",
           "no user-defined provider" in post("/providers", action="delete_custom", name="groq").body, "(A)")


def refusing(app):
    raise P.ProviderError("refusing to call x without --allow-paid. key gsk_abcdefghij1234567890XYZ")


B = mk(assistant=None, remote_factory=refusing, lister=lister)
post("/providers", app=B, action="save_custom", name="lab2", wire="openai", base_url="http://localhost:1234/v1",
     env_key="", model_id="m")
post("/providers", app=B, action="set_engine", engine="remote", provider="lab2")
r = post("/ask", app=B, question="q", engine="remote")
check_true("a refusing online engine is shown as a refusal (not a 500), key redacted",
           r.status == 200 and "موتور آنلاین در دسترس نیست" in r.body and "gsk_abcdefghij" not in r.body, "(A)")
check_true("no local model + offline: refused with guidance",
           "بدون مدل" in post("/ask", app=B, question="q", engine="local").body, "(A)")
open(sp, "w").write("{broken")
Cc = mk()
check_true("a corrupt settings file is reported, defaults used, file untouched",
           "خوانده نشد" in Cc.handle("GET", "/providers").body and Cc.settings["active"]["engine"] == "local"
           and open(sp).read() == "{broken", "(A)")
check_true("the UI's online engine shares ONE audit log with the local one (MEASURED: two break the chain)",
           mk(assistant=type("L", (), {"audit": "SHARED"})()).audit() == "SHARED", "(V)")
P.register_user_providers({})
os.environ.clear()
os.environ.update(_SAVED_ENV)

print("")
sys.exit(summary())
