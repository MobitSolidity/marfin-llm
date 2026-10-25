# -*- coding: utf-8 -*-
"""
Phase 9 (D-0126): the documentation is checked against the code and the
evidence, so a doc cannot silently drift from what the system does.

(V) verified against live code/evidence.
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from _harness import check, check_true, section, summary  # noqa: E402


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


def ev(rel):
    return json.load(open(os.path.join(ROOT, "evidence", rel), encoding="utf-8"))


# ===========================================================================
section("SS.24 Phase 9 deliverables exist")
# ===========================================================================
DOCS = ("README.md", "LICENSES.md", "MODEL_CARD.md", "requirements.txt", ".env.example",
        "docs/architecture.md", "docs/deployment.md", "docs/tradingview-integration.md",
        "docs/execution-safety.md", "docs/known-failures.md", "docs/error-reporting.md")
for d in DOCS:
    check_true("%s exists and is non-trivial" % d,
               os.path.exists(os.path.join(ROOT, d)) and len(read(d)) > 200, "(V)")

# ===========================================================================
section("model card: all SS.23 fields, and its numbers match the evidence")
# ===========================================================================
MC = read("MODEL_CARD.md")
SS23 = ("Model name", "Base model", "Revision", "Architecture", "Version", "License", "Datasets",
        "Dataset licenses", "Date ranges", "Languages", "Intended uses", "Out-of-scope uses",
        "Known limitations", "Financial risks", "RAG dependency", "Tool dependencies",
        "TradingView limitations", "Broker-integration limitations", "Last update", "Benchmarks",
        "Hardware", "Inference settings", "Quantization", "Model size", "Context", "Examples",
        "Citation behaviour", "Failure cases", "Error reporting", "Reproducibility", "Checksums")
# A field must be a table ROW key or a section HEADING, not a word that happens
# to appear somewhere (a first version matched "Context" inside prose and missed
# a dropped row; caught by mutate_phase9).
_keys = {k.strip().lower() for k in re.findall(r"^\| \*\*([^*|]+)\*\* \|", MC, re.M)}
_keys |= {h.strip().lower() for h in re.findall(r"^## ([^(\n]+)", MC, re.M)}
missing = [f for f in SS23 if f.lower() not in _keys]
check_true("all 31 SS.23 fields are present as rows or headings", not missing, "(V) missing %r" % missing)
hdr = ev("phase7_gguf_headers_2026-10-16.json")
q4 = hdr["full_file_hashes"]["Qwen3.5-4B-Q4_K_M.gguf"]
check_true("Q4_K_M sha256 and byte size match the evidence",
           q4["sha256"] in MC and format(q4["size_bytes"], ",") in MC, "(V)")
check_true("revision matches the evidence", hdr["revision"] in MC, "(V)")
check_true("parameter count matches the GGUF header",
           format(hdr["headers"]["Qwen3.5-4B-BF16.gguf"]["n_params"], ",") in MC, "(V)")
check_true("chat template sha256 prefix matches",
           hdr["headers"]["Qwen3.5-4B-BF16.gguf"]["chat_template_sha256"][:8] in MC, "(V)")
VER = {r["threshold"]: r for r in ev("phase7_q4km_verdict_2026-10-17.json")["results"]}
for name, txt in (("citation_correctness_pct_min", "90.48"), ("correct_abstention_pct_min", "88.89"),
                  ("unsupported_claim_rate_pct_max", "7.69"), ("peak_rss_8k_gib_max", "4.73"),
                  ("model_file_size_gib_max", "2.553")):
    check_true("benchmark %s = %s matches the verdict file" % (name, txt),
               str(VER[name]["deciding"]["value"]) == txt and txt in MC, "(V)")
for name, verdict in (("deterministic_calc_correctness_pct_min", "PASS"),
                      ("generation_tokens_per_sec_min", "FAIL"),
                      ("time_to_first_token_2k_sec_max", "FAIL")):
    check_true("%s is %s in the evidence, as the card says" % (name, verdict),
               VER[name]["verdict"] == verdict, "(V)")
from tools.registry import tool_schemas                        # noqa: E402
check_true("the card's tool count (85) is the live registry size",
           len(tool_schemas()) == 85 and "85 deterministic" in MC, "(V) %d" % len(tool_schemas()))
_m = ev("phase7_q4km_merged_2026-10-17.json")
_t = {r["id"]: r for r in _m["arms"]["tools"]}
check_true("example EN-CALC-001 is the recorded reply, and it called pe_ratio",
           "17.86" in _t["EN-CALC-001"]["output"] and _t["EN-CALC-001"]["tool_calls"] == ["pe_ratio"],
           "(V)")
_cut = sum(1 for a in _m["arms"] for r in _m["arms"][a]
           if ((r["metrics"].get("second_turn") or r["metrics"]).get("completion_tokens") or 0) >= 512)
check("the card's '6 of 74 replies hit 512 tokens' is measured", _cut, 6, 0, "(V)")

# ===========================================================================
section("LICENSES.md is generated from the live registries")
# ===========================================================================
import build_licenses as BL                                     # noqa: E402
check_true("LICENSES.md equals tools/build_licenses.py output (no drift)",
           read("LICENSES.md") == BL.render(), "(V) regenerate: python3 tools/build_licenses.py > LICENSES.md")
from rag import sources as S                                    # noqa: E402
check_true("every data source appears in LICENSES.md",
           all("| %s |" % k in read("LICENSES.md") for k in S.SOURCES), "(V)")
# D-0130: the project code is Apache-2.0. The licence file must be the canonical
# text, byte for byte, and every place that states the licence must agree.
import hashlib as _hl                                            # noqa: E402
_lic = open(os.path.join(ROOT, "LICENSE"), "rb").read()
check_true("LICENSE is the canonical Apache-2.0 text (sha256 of apache.org/licenses/LICENSE-2.0.txt)",
           _hl.sha256(_lic).hexdigest() == "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30",
           "(V)")
check_true("LICENSES.md, README and the model card all state Apache-2.0 for the project code",
           "**Apache License 2.0** (`LICENSE`, `NOTICE`)" in read("LICENSES.md")
           and "licensed under the **Apache License 2.0**" in read("README.md")
           and "Project code: Apache-2.0 (`LICENSE`, `NOTICE`" in MC, "(V)")
check_true("no document still says the project code is unlicensed",
           not any(x in read(d) for d in ("LICENSES.md", "README.md", "MODEL_CARD.md")
                   for x in ("No licence has been chosen", "not yet licensed")), "(V)")
_NOTICE = read("NOTICE")
check_true("NOTICE names the copyright holder and the licence", "Copyright 2026 MobitSolidity" in _NOTICE
           and "Apache License, Version 2.0" in _NOTICE, "(V)")
# Third-party material shipped in the repo must be carved out of the grant, by
# path, in NOTICE AND LICENSES.md -- and the carve-out must match what is
# actually tracked (a new third-party directory with no carve-out fails here).
_tracked = subprocess.check_output(["git", "-C", ROOT, "ls-files"]).decode().split()
for _dir in ("tests/fixtures/alpha_vantage/", "configs/model-cards/"):
    check_true("third-party %s is tracked AND carved out of the licence in NOTICE and LICENSES.md" % _dir,
               any(t.startswith(_dir) for t in _tracked) and _dir in _NOTICE and _dir in read("LICENSES.md"),
               "(V)")
check_true("the Alpha Vantage carve-out says the fixtures are NOT licensed by this project",
           "NOT licensed to you by this project" in _NOTICE
           and "Not licensed to you by this project" in read("LICENSES.md"), "(V)")
_FIXDIRS = sorted({t.split("/")[2] for t in _tracked if t.startswith("tests/fixtures/") and t.count("/") >= 3})
# D-0137: tests/fixtures/ask/ holds the project's OWN model output (a reply the
# owner's i5-12400 produced through scripts/ask.py) -- not third-party data, so it
# is Apache-2.0 with the rest of the project and needs no NOTICE carve-out. It is
# listed here so that any OTHER new fixture directory still forces a decision.
_OWN_FIXDIRS = {"ask"}
check_true("every tests/fixtures/ subdirectory is a known carve-out (alpha_vantage) or project-own (ask)",
           set(_FIXDIRS) - _OWN_FIXDIRS == {"alpha_vantage"}, "(V) %r" % _FIXDIRS)
check_true("... and the project-own fixtures carry no third-party source",
           all(not any(w in open(os.path.join(ROOT, t), encoding="utf-8").read().lower()
                       for w in ("alpha vantage", "copyright", "all rights reserved"))
               for t in _tracked if t.startswith("tests/fixtures/ask/")), "(V)")
import ast                                                      # noqa: E402
_third = set()
for dp, _, fs in os.walk(os.path.join(ROOT, "scripts")):
    for f in fs:
        if f.endswith(".py"):
            for n in ast.walk(ast.parse(open(os.path.join(dp, f), encoding="utf-8").read())):
                if isinstance(n, ast.Import):
                    _third |= {a.name.split(".")[0] for a in n.names}
                elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
                    _third.add(n.module.split(".")[0])
_third &= {"llama_cpp", "psutil", "jinja2", "tokenizers", "numpy", "requests", "torch", "transformers"}
_PKG = {"llama_cpp": "llama-cpp-python"}     # import name -> distribution name
_req = {l.split(">")[0].split("=")[0].strip().lower() for l in read("requirements.txt").splitlines()
        if l.strip() and not l.lstrip().startswith("#")}
check_true("every third-party runtime import in scripts/ is in LICENSES.md AND an active requirements.txt line",
           all(_PKG.get(m, m) in read("LICENSES.md").lower() and _PKG.get(m, m) in _req
               for m in _third), "(V) %r vs %r" % (sorted(_third), sorted(_req)))
for dp, _, fs in os.walk(os.path.join(ROOT, "src")):
    for f in fs:
        if f.endswith(".py"):
            for n in ast.walk(ast.parse(open(os.path.join(dp, f), encoding="utf-8").read())):
                mods = ([a.name for a in n.names] if isinstance(n, ast.Import) else
                        [n.module] if isinstance(n, ast.ImportFrom) and n.module and n.level == 0 else [])
                for m in mods:
                    top = m.split(".")[0]
                    if top not in sys.stdlib_module_names and top not in (
                            "calc", "execution", "llm", "maintenance", "market", "rag", "safety", "tools", "phase4_lib"):
                        _third.add("SRC:" + top)
check_true("src/ is stdlib-only, as the docs say", not any(x.startswith("SRC:") for x in _third),
           "(V) %r" % sorted(x for x in _third if x.startswith("SRC:")))

# ===========================================================================
section(".env.example lists exactly the secrets the code reads, and no values")
# ===========================================================================
from llm import providers as P                                  # noqa: E402
_env = read(".env.example")
_keys = {l.split("=")[0] for l in _env.splitlines() if "=" in l and not l.startswith("#")}
_want = {v["env_key"] for v in P.PROVIDERS.values() if isinstance(v, dict) and v.get("env_key")}
_want.add("ALPHAVANTAGE_API_KEY")
_want.add("FRED_API_KEY")
check_true(".env.example names every key the code reads", _want <= _keys, "(V) missing %r" % (_want - _keys))
check_true(".env.example contains no values", all(l.endswith("=") for l in _env.splitlines()
                                                    if "=" in l and not l.startswith("#")), "(V)")
check_true(".env is ignored but .env.example is tracked by .gitignore rules",
           ".env" in read(".gitignore").splitlines() and "!.env.example" in read(".gitignore"), "(V)")

# ===========================================================================
section("safety docs match the code")
# ===========================================================================
from execution import mode as M                                 # noqa: E402
from execution import paper as PP                               # noqa: E402
from execution import broker_tools as B                         # noqa: E402
from market import webhooks as W                                # noqa: E402
_es, _arch = read("docs/execution-safety.md"), read("docs/architecture.md")
_unmet, _tot = len(M.unmet_live_prerequisites()), len(M.LIVE_PREREQUISITES)
check_true("'%d of %d SS.6.1 prerequisites unmet' is the live count" % (_unmet, _tot),
           ("%d of %d" % (_unmet, _tot)) in _es and ("%d of the %d" % (_unmet, _tot)) in _arch
           and _unmet > 0, "(V)")
check_true("live trading is unreachable, as every doc says", not M.live_trading_enabled(), "(V)")
import tempfile                                                 # noqa: E402
import datetime                                                 # noqa: E402
_td = tempfile.mkdtemp()
_eng = PP.PaperEngine(_td, {"PAPER-1": 1e5}, PP.RiskLimits(("X",)))
_now = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
_pv = _eng.preview("PAPER-1", "PAPER", "X", "buy", 1, "market", "c",
                   PP.QuoteSnapshot("X", 9.99, 10.01, 10, _now, "OPEN", "t"), now=_now)
check_true("'17 pre-trade checks' in the doc is the engine's live count",
           len(_pv["risk_checks"]) == 17 and "17 pre-trade checks" in _es, "(V) %d" % len(_pv["risk_checks"]))
check("12 SS.6.4 states", len(PP.ORDER_STATES), 12, 0, "(V)")
check("preview returns 10 SS.8.6 fields", len(B.PREVIEW_FIELDS), 10, 0, "(V)")
check_true("'16 validations' for webhooks is the live count",
           W.manifest().get("n_validations") == 16 and "16 validations" in read("docs/tradingview-integration.md"),
           "(V)")
check_true("TradingView is disabled as a source, as the TradingView doc says",
           not S.SOURCES["tradingview"].enabled, "(V)")

# ===========================================================================
section("deployment and run commands refer to flags that exist")
# ===========================================================================
_src = read("scripts/run_phase4.py")
_ask = read("scripts/ask.py")
for doc in ("docs/deployment.md", "MODEL_CARD.md", "PHASE8_CONFIRM_RUN_FA.md", "docs/guides/ask-fa.md"):
    # D-0135: a flag is checked against the script its OWN line runs, so an
    # ask.py flag is not demanded of run_phase4 (and vice versa).
    for line in read(doc).splitlines():
        prog, src = (("ask.py", _ask) if "ask.py" in line else ("run_phase4", _src))
        for flag in sorted(set(re.findall(r"(--[a-z][a-z-]+)", line))):
            if flag in ("--think", "--version", "--mutate"):
                continue
            if prog == "run_phase4" and ('"%s"' % flag) not in _src and ('"%s"' % flag) in _ask:
                prog, src = "ask.py", _ask          # prose line about an ask.py option
            check_true("%s: flag %s exists in %s" % (doc, flag, prog),
                       ('"%s"' % flag) in src, "(V)")
check_true("the deployment checksum is the Q4_K_M sha256 (upper-case for PowerShell)",
           q4["sha256"].upper() in read("docs/deployment.md"), "(V)")
check_true("the Modelfile FROM line names the documented file", "Qwen3.5-4B-Q4_K_M.gguf" in
           read("deploy/ollama/Modelfile").split("FROM", 1)[1].split("\n", 1)[0], "(V)")

print("")
sys.exit(summary())
