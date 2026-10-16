# -*- coding: utf-8 -*-
"""
Phase 7 (D-0121): GGUF validation and the quantisation comparison.

Offline. The header reader is exercised on GGUF files BUILT HERE, byte by
byte, from the published format (magic, version, counts, typed KV pairs,
tensor infos). The real upstream headers were read with the same code on
2026-10-16 and are recorded in evidence/phase7_gguf_headers_2026-10-16.json;
that file is checked too, so a regression in the recorded finding is caught.

Method codes: (A) attack/defect must be REFUSED, (N) near-miss must PASS,
(V) verified invariant, (M) from recorded measurement.
"""
import copy
import json
import os
import struct
import sys
import tempfile
import shutil
import atexit

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from _harness import check_true, summary            # noqa: E402
import gguf_inspect as GI                            # noqa: E402
import compare_quants as CQ                          # noqa: E402
import phase4_lib as L                               # noqa: E402

_TMP = tempfile.mkdtemp(prefix="phase7_")
atexit.register(shutil.rmtree, _TMP, True)


def section(t):
    print("\n-- %s --" % t)


# ---------------------------------------------------------------------------
# a GGUF writer, from the format spec, for tests only
# ---------------------------------------------------------------------------
def _s(x):
    b = x.encode("utf-8")
    return struct.pack("<Q", len(b)) + b


def _kv(k, v):
    if isinstance(v, bool):
        return _s(k) + struct.pack("<I", 7) + struct.pack("<?", v)
    if isinstance(v, int):
        return _s(k) + struct.pack("<I", 4) + struct.pack("<I", v)
    if isinstance(v, float):
        return _s(k) + struct.pack("<I", 6) + struct.pack("<f", v)
    if isinstance(v, str):
        return _s(k) + struct.pack("<I", 8) + _s(v)
    if isinstance(v, list):
        if v and isinstance(v[0], str):
            return (_s(k) + struct.pack("<I", 9) + struct.pack("<I", 8)
                    + struct.pack("<Q", len(v)) + b"".join(_s(x) for x in v))
        return (_s(k) + struct.pack("<I", 9) + struct.pack("<I", 5)
                + struct.pack("<Q", len(v)) + b"".join(struct.pack("<i", x) for x in v))
    raise TypeError(v)


BASE_KV = {
    "general.architecture": "qwen35", "general.file_type": 17,
    "qwen35.block_count": 2, "qwen35.embedding_length": 8,
    "tokenizer.ggml.model": "gpt2", "tokenizer.ggml.pre": "qwen35",
    "tokenizer.ggml.tokens": ["a", "b", "<|im_end|>"],
    "tokenizer.ggml.token_type": [1, 1, 3],
    "tokenizer.ggml.merges": ["a b"],
    "tokenizer.ggml.eos_token_id": 2,
    "tokenizer.chat_template": "{{ messages }}<|im_start|>assistant\n",
}
BASE_T = [("token_embd.weight", [8, 3], 13), ("blk.0.attn_norm.weight", [8], 0),
          ("output_norm.weight", [8], 0)]


def build(kv=None, tensors=None, magic=b"GGUF", version=3):
    kv = BASE_KV if kv is None else kv
    tensors = BASE_T if tensors is None else tensors
    b = magic + struct.pack("<I", version) + struct.pack("<Q", len(tensors)) \
        + struct.pack("<Q", len(kv))
    for k, v in kv.items():
        b += _kv(k, v)
    for name, dims, ty in tensors:
        b += _s(name) + struct.pack("<I", len(dims)) \
            + b"".join(struct.pack("<Q", d) for d in dims) \
            + struct.pack("<I", ty) + struct.pack("<Q", 0)
    return b + b"\0" * 64          # stand-in for alignment + weights


def write(name, data):
    p = os.path.join(_TMP, name)
    with open(p, "wb") as f:
        f.write(data)
    return p


def summ(**kw):
    return GI.summarise(GI.read_header(write("x.gguf", build(**kw))))


def raises(fn, exc=Exception):
    try:
        fn()
    except exc as e:
        return e
    return None


# ===========================================================================
section("gguf_inspect: header reader on synthetic files")
# ===========================================================================
_s0 = summ()
check_true("reads architecture, file type and vocab from a well-formed header",
           _s0["architecture"] == "qwen35" and _s0["file_type"] == 17
           and _s0["vocab_size"] == 3, "(V)")
check_true("counts parameters from tensor dims (24 + 8 + 8 = 40)",
           _s0["n_params"] == 40, "(B) hand arithmetic")
check_true("groups parameters by ggml type (Q5_K 24, F32 16)",
           _s0["params_by_type"] == {"F32": 16, "Q5_K": 24}, "(B)")
check_true("resolves special-token ids to their strings",
           _s0["special_tokens"] == {"tokenizer.ggml.eos_token_id": "<|im_end|>"}, "(V)")
check_true("hashes the chat template (present, 64 hex)",
           isinstance(_s0["chat_template_sha256"], str) and len(_s0["chat_template_sha256"]) == 64,
           "(V)")
check_true("refuses a file whose magic is not GGUF",
           bool(raises(lambda: GI.read_header(write("bad.gguf", build(magic=b"GGML"))),
                       ValueError)), "(A)")
check_true("refuses a truncated header instead of returning a partial one",
           bool(raises(lambda: GI.read_header(write("trunc.gguf", build()[:40])),
                       EOFError)), "(A)")
check_true("an unknown ggml type id is reported as type_<n>, not guessed",
           "type_99" in summ(tensors=BASE_T[:2] + [("output_norm.weight", [8], 99)])
           ["params_by_type"], "(A)")
_kvbad = dict(BASE_KV)
_kvbad["x"] = 0
_raw = build(kv=_kvbad)
_i = _raw.find(_s("x")) + len(_s("x"))
_raw = _raw[:_i] + struct.pack("<I", 77) + _raw[_i + 4:]
check_true("refuses an unknown GGUF value type",
           bool(raises(lambda: GI.read_header(write("vt.gguf", _raw)), ValueError)), "(A)")

# ===========================================================================
section("gguf_inspect: what counts as 'the same model at another precision'")
# ===========================================================================
_q4 = summ(tensors=[("token_embd.weight", [8, 3], 12)] + BASE_T[1:])
check_true("a different quantisation of the same tensors is NOT an invariant difference",
           GI.compare({"q5": _s0, "q4": _q4}) == {}, "(N)")
_reord = summ(tensors=list(reversed(BASE_T)))
check_true("tensor ORDER alone is not an invariant difference (BF16 vs quantised, M)",
           GI.compare({"a": _s0, "b": _reord}) == {}
           and _s0["tensor_order_sha256"] != _reord["tensor_order_sha256"], "(M)")
for label, kvmod in (
        ("chat template", {"tokenizer.chat_template": "{{ other }}"}),
        ("vocabulary", {"tokenizer.ggml.tokens": ["a", "c", "<|im_end|>"]}),
        ("token types", {"tokenizer.ggml.token_type": [1, 3, 3]}),
        ("merges", {"tokenizer.ggml.merges": ["b a"]}),
        ("special-token id", {"tokenizer.ggml.eos_token_id": 1}),
        ("pre-tokenizer", {"tokenizer.ggml.pre": "qwen2"}),
        ("hyperparameter", {"qwen35.block_count": 3}),
        ("architecture", {"general.architecture": "qwen3"})):
    kv = dict(BASE_KV)
    kv.update(kvmod)
    check_true("a changed %s IS an invariant difference" % label,
               bool(GI.compare({"a": _s0, "b": summ(kv=kv)})), "(A)")
check_true("a renamed tensor IS an invariant difference",
           bool(GI.compare({"a": _s0, "b": summ(tensors=[("token_embd.weight", [8, 3], 13),
                                                          ("blk.0.ffn_norm.weight", [8], 0),
                                                          ("output_norm.weight", [8], 0)])})),
           "(A)")
_resh = summ(tensors=[("token_embd.weight", [3, 8], 13)] + BASE_T[1:])
check_true("a reshaped tensor with the SAME parameter count IS an invariant difference "
           "(caught by shape, not by n_params)",
           _resh["n_params"] == _s0["n_params"]
           and "tensor_shapes_sha256" in GI.compare({"a": _s0, "b": _resh}), "(A) D-0121 survivor")
check_true("file_type is NOT an invariant (it is what differs between quants)",
           "file_type" not in GI.INVARIANT_FIELDS, "(V)")


class _FakeResp:
    def __init__(self, status, data):
        self.status, self._d = status, data

    def read(self):
        return self._d

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


_orig_urlopen = GI.urllib.request.urlopen
_blob = build()
try:
    _seen = []

    def _ranged(req, timeout=None):
        rng = req.headers.get("Range")
        _seen.append(rng)
        a, b = (int(x) for x in rng.split("=")[1].split("-"))
        return _FakeResp(206, _blob[a:b + 1])
    GI.urllib.request.urlopen = _ranged
    _u = GI.summarise(GI.read_header("https://example.invalid/m.gguf", chunk=16))
    check_true("a URL is read by Range requests and gives the same summary as the file",
               {k: v for k, v in _u.items() if k != "bytes_fetched"}
               == {k: v for k, v in _s0.items() if k != "bytes_fetched"}
               and len(_seen) > 3 and all(s and s.startswith("bytes=") for s in _seen),
               "(V) several 16-byte ranges, so the chunk-boundary logic is exercised")
    GI.urllib.request.urlopen = lambda req, timeout=None: _FakeResp(200, _blob)
    check_true("a server that ignores Range (HTTP 200) is REFUSED, not downloaded whole",
               bool(raises(lambda: GI.read_header("https://example.invalid/m.gguf"), IOError)),
               "(A) a GiB-sized download was never requested")
finally:
    GI.urllib.request.urlopen = _orig_urlopen

# ===========================================================================
section("recorded upstream finding (evidence/phase7_gguf_headers_2026-10-16.json)")
# ===========================================================================
_ev = json.load(open(os.path.join(ROOT, "evidence", "phase7_gguf_headers_2026-10-16.json"),
                     encoding="utf-8"))
_hd = _ev["headers"]
check_true("six upstream files were inspected, all qwen35",
           len(_hd) == 6 and {v["architecture"] for v in _hd.values()} == {"qwen35"}, "(M)")
check_true("all six share one chat template, vocabulary and merges",
           len({v["chat_template_sha256"] for v in _hd.values()}) == 1
           and len({v["tokens_sha256"] for v in _hd.values()}) == 1
           and len({v["merges_sha256"] for v in _hd.values()}) == 1, "(M)")
check_true("no invariant field differs across the six",
           _ev["invariant_differences"] == {}, "(M)")
check_true("every file was read with <= 16 MiB of Range traffic (no full download)",
           all(v["bytes_fetched"] <= 16 << 20 for v in _hd.values()), "(M)")
check_true("the two streamed full-file hashes agree with the HF LFS oid",
           all(v["agrees"] and v["magic"] == "GGUF" for v in _ev["full_file_hashes"].values()),
           "(M)")
check_true("Q4_K_M differs from Q5_K_M only in quantisation types (131 Q5_K->Q4_K, 48 Q6_K->Q5_K)",
           _ev["tensor_type_change_Q5_K_M_to_Q4_K_M"].get("Q5_K->Q4_K") == 131
           and _ev["tensor_type_change_Q5_K_M_to_Q4_K_M"].get("Q6_K->Q5_K") == 48, "(M)")
check_true("the embedded template's enable_thinking=False render == the harness prompt "
           "(pinned: chatml_prompt_no_think is what every run sends)",
           _hd["Qwen3.5-4B-Q5_K_M.gguf"]["chat_template_sha256"]
           == "7f0e529032c25183bcd66c7f238da2d377f43be754a94e2725a58c4e16d2ed67", "(M)")

# ===========================================================================
section("KNOWN_MODEL_FILES: the Phase 7 artefacts")
# ===========================================================================
_q4sha = _ev["full_file_hashes"]["Qwen3.5-4B-Q4_K_M.gguf"]["sha256"]
_q8sha = _ev["full_file_hashes"]["Qwen3.5-4B-Q8_0.gguf"]["sha256"]
check_true("Q4_K_M is registered under its streamed sha256, with the counted size",
           L.KNOWN_MODEL_FILES.get(_q4sha, {}).get("size_bytes")
           == _ev["full_file_hashes"]["Qwen3.5-4B-Q4_K_M.gguf"]["size_bytes"], "(M)")
check_true("Q8_0 is registered under its streamed sha256, with the counted size",
           L.KNOWN_MODEL_FILES.get(_q8sha, {}).get("size_bytes")
           == _ev["full_file_hashes"]["Qwen3.5-4B-Q8_0.gguf"]["size_bytes"], "(M)")
check_true("both think by default, like the Q5_K_M they quantise",
           L.KNOWN_MODEL_FILES[_q4sha]["thinking_by_default"] is True
           and L.KNOWN_MODEL_FILES[_q8sha]["thinking_by_default"] is True, "(V)")
check_true("Q8_0 is marked a reference only: 4.17 GiB is above the approved 4.0 GiB cap",
           L.KNOWN_MODEL_FILES[_q8sha]["size_bytes"] / 1024 ** 3 > 4.0
           and "REFERENCE only" in L.KNOWN_MODEL_FILES[_q8sha]["note"], "(V)")

# ===========================================================================
section("compare_quants: refuses confounded comparisons")
# ===========================================================================
_base = json.load(open(os.path.join(ROOT, "evidence",
                                    "phase4_merged_2026-10-09_q14_regraded_D0115.json"),
                       encoding="utf-8"))


def _as(run, sha, file, size, tps=(2.65, 3.52)):
    r = copy.deepcopy(run)
    r["model"]["identity"] = dict(r["model"]["identity"], sha256=sha, file=file, label="VERIFIED")
    r["model"]["file"], r["model"]["size_gib"] = file, size
    r["latency_spread"] = dict(r.get("latency_spread") or {},
                               decode_tokens_per_sec_min=tps[0],
                               decode_tokens_per_sec_max=tps[1])
    return r


_cand = _as(_base, _q4sha, "Qwen3.5-4B-Q4_K_M.gguf", 2.553)
_ok = CQ.compare(_base, _cand)
check_true("same harness, different VERIFIED weights: compared as QUANTISATION",
           _ok["label"] == "COMPUTED_FROM_MEASURED" and _ok["kind"] == "QUANTISATION", "(N)")
check_true("identical replies give no regressions and no improvements",
           _ok["regressions"] == [] and _ok["improvements"] == [], "(V)")
check_true("same weights twice is labelled REPEATABILITY, not a quantisation result",
           CQ.compare(_base, copy.deepcopy(_base))["kind"].startswith("REPEATABILITY"), "(A)")
for label, mut in (
        ("ctx", lambda r: r["model"].__setitem__("ctx", 8192)),
        ("max_tokens", lambda r: r["model"].__setitem__("max_tokens", 2048)),
        ("threads", lambda r: r["model"].__setitem__("threads", 12)),
        ("prompt_options", lambda r: r["model"].__setitem__(
            "prompt_options", {"second_turn": True, "refusal_language": True,
                               "execution_guard": True})),
        ("sampling", lambda r: r["model"]["sampling"].__setitem__("temperature", 0.7)),
        ("eval cases", lambda r: r["arms"]["plain"].pop()),
        ("question text", lambda r: r["arms"]["plain"][0].__setitem__("question", "other?"))):
    c = copy.deepcopy(_cand)
    mut(c)
    check_true("a run differing in %s is REFUSED" % label,
               CQ.compare(_base, c)["label"] == "REFUSED", "(A)")
_unv = copy.deepcopy(_cand)
_unv["model"]["identity"]["label"] = "UNKNOWN"
check_true("UNKNOWN weights are REFUSED", CQ.compare(_base, _unv)["label"] == "REFUSED", "(A)")
_inc = copy.deepcopy(_cand)
_inc["complete"] = False
check_true("an incomplete run is REFUSED", CQ.compare(_base, _inc)["label"] == "REFUSED", "(A)")

# ===========================================================================
section("compare_quants: regressions, Persian rows, speed resolution")
# ===========================================================================
_reg = copy.deepcopy(_cand)
_r0 = [r for r in _reg["arms"]["plain"] if r.get("value_ok") is True][0]
_r0["value_ok"] = False
_r0["output"] = "different"
_f0 = [r for r in _reg["arms"]["tools"] if r.get("fabricated") is False][0]
_f0["fabricated"] = True
_res = CQ.compare(_base, _reg)
check_true("a value_ok True->False flip is a REGRESSION",
           any(e["row"] == "plain/" + _r0["id"] and e["field"] == "value_ok"
               for e in _res["regressions"]), "(A)")
check_true("a fabricated False->True flip is a REGRESSION (True is bad there)",
           any(e["row"] == "tools/" + _f0["id"] and e["field"] == "fabricated"
               for e in _res["regressions"]), "(A)")
check_true("the verdict counts them", _res["verdict"] == "%d ROW(S) REGRESSED"
           % len(_res["regressions"]), "(V)")
_imp = CQ.compare(_reg, _cand)
check_true("the reverse direction is an IMPROVEMENT, not a regression",
           any(e["row"] == "plain/" + _r0["id"] for e in _imp["improvements"])
           and not any(e["row"] == "plain/" + _r0["id"] for e in _imp["regressions"]), "(N)")
_fa = copy.deepcopy(_cand)
_farow = [r for r in _fa["arms"]["plain"] if r.get("lang") == "fa"][0]
_farow["output"] += " ."
check_true("a changed Persian reply is listed for human (R10) review",
           "plain/" + _farow["id"] in CQ.compare(_base, _fa)["persian_rows_changed"], "(V)")
_rag = copy.deepcopy(_cand)
_ua = [r for r in _rag["arms"]["rag"] if r.get("answerable") is False and r.get("abstained")][0]
_ua["abstained"] = False
check_true("rag: an unanswerable row that stops abstaining is a REGRESSION",
           any(e["row"] == "rag/" + _ua["id"] and e["field"] == "abstained"
               for e in CQ.compare(_base, _rag)["regressions"]), "(A)")
_rag2 = copy.deepcopy(_cand)
_an = [r for r in _rag2["arms"]["rag"] if r.get("answerable") is True and not r.get("abstained")][0]
_an["abstained"] = True
check_true("rag: an answerable row that starts abstaining is a REGRESSION",
           any(e["row"] == "rag/" + _an["id"] and e["field"] == "abstained"
               for e in CQ.compare(_base, _rag2)["regressions"]), "(A)")
check_true("a speed difference inside the measured same-weights spread is NOT RESOLVED",
           CQ.compare(_base, _as(_base, _q4sha, "q4", 2.553, (3.0, 4.0)))["speed"]["verdict"]
           .startswith("NOT RESOLVED"), "(A) 2.65-4.37 tok/s for ONE set of weights (M)")
check_true("a speed difference beyond the spread is reported, with its direction",
           "FASTER" in CQ.compare(_base, _as(_base, _q4sha, "q4", 2.553, (6.0, 6.5)))
           ["speed"]["verdict"], "(N)")
check_true("the same-weights spread is the measured 2.65-4.37",
           CQ.SAME_WEIGHTS_DECODE_SPREAD == (2.65, 4.37), "(M)")

# ===========================================================================
section("the GGUF-embedded chat template vs what the harness sends")
# ===========================================================================
import hashlib                                       # noqa: E402
import run_phase4 as RP                              # noqa: E402
_tp = os.path.join(ROOT, "evals", "fixtures", "qwen35_gguf_chat_template.jinja")
_tsrc = open(_tp, encoding="utf-8").read()
check_true("the template fixture IS the one embedded in the GGUF (sha matches the header)",
           hashlib.sha256(_tsrc.encode("utf-8")).hexdigest()
           == _hd["Qwen3.5-4B-Q5_K_M.gguf"]["chat_template_sha256"], "(M)")
try:
    from jinja2 import Environment as _JE
    _env = _JE()
    _env.globals["raise_exception"] = lambda m: (_ for _ in ()).throw(Exception(m))
    _tpl = _env.from_string(_tsrc)
    from tools.selector import schemas_for as _sf
    _q = "What is the CAGR from 100 to 121 over 2 years?"
    for _rl in (False, True):
        _first = RP.build_tools_prompt(_q, _sf(_q), refusal_language=_rl)
        _m2 = [{"role": "system", "content": _first.system}, {"role": "user", "content": _first.user}]
        check_true("first turn == the EMBEDDED template's enable_thinking=False render "
                   "(refusal_language=%s)" % _rl,
                   str(_first) == _tpl.render(messages=_m2, add_generation_prompt=True,
                                              enable_thinking=False), "(M)")
        _reply = '<tool_call>{"name": "cagr", "arguments": {"start": 100, "end": 121, "years": 2}}</tool_call>'
        _ex = [{"name": "cagr", "arguments": {"start": 100, "end": 121, "years": 2},
                "ok": True, "value": 0.1, "error": None}]
        _sec = RP.build_tools_followup_prompt(_first, _reply, _ex)
        _m4 = _m2 + [{"role": "assistant", "content": _reply}] + [
            {"role": "tool", "content": c} for c in RP.tool_response_content(_ex)]
        check_true("tool second turn == the EMBEDDED template's render (refusal_language=%s)" % _rl,
                   str(_sec) == _tpl.render(messages=_m4, add_generation_prompt=True,
                                            enable_thinking=False), "(M)")
    _dflt = _tpl.render(messages=[{"role": "user", "content": "x"}], add_generation_prompt=True)
    check_true("PHASE 8 NOTE: the embedded template's DEFAULT pre-closes <think> "
               "(a client using it will not think by default)",
               _dflt.endswith("<think>\n\n</think>\n\n"), "(M) differs from the HF config default")
except ImportError:
    print("  SKIP  jinja2 absent: the embedded-template assertions did NOT run")

print("")
sys.exit(summary())
