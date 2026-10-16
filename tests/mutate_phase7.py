# -*- coding: utf-8 -*-
"""
Mutation battery for Phase 7 (D-0121): tools/gguf_inspect.py, scripts/compare_quants.py
and the Phase 7 rows of KNOWN_MODEL_FILES. Each mutation weakens ONE check that
tests/test_phase7.py claims to pin. Committed tree only; restore by rewrite.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ORACLE = os.path.join(HERE, "test_phase7.py")

GI = "tools/gguf_inspect.py"
CQ = "scripts/compare_quants.py"
LIB = "scripts/phase4_lib.py"

MUTATIONS = [
    (GI, "magic not checked",
     '    if src.read(4) != GGUF_MAGIC:\n        raise ValueError("not a GGUF file (bad magic)")',
     "    src.read(4)"),
    (GI, "short read tolerated",
     '            if len(b) != n:\n                raise EOFError("short read")', "            pass"),
    (GI, "Range ignored: whole file accepted",
     "                if r.status != 206:", "                if False:"),
    (GI, "unknown type guessed as F32",
     'GGML_TYPES.get(ty, "type_%d" % ty)', 'GGML_TYPES.get(ty, "F32")'),
    (GI, "unknown value type silently skipped",
     '    raise ValueError("unknown GGUF value type %d" % t)', "    return None"),
    (GI, "chat template not an invariant",
     '                    "chat_template_sha256", "tokenizer_model",', '                    "tokenizer_model",'),
    (GI, "merges not an invariant",
     '"token_type_sha256", "merges_sha256", "special_token_ids",', '"token_type_sha256", "special_token_ids",'),
    (GI, "special ids not an invariant",
     '"merges_sha256", "special_token_ids",', '"merges_sha256",'),
    (GI, "tensor names order-sensitive again (BF16 flagged)",
     '"tensor_names_sha256": _h(sorted(t[0] for t in hdr["tensors"])),',
     '"tensor_names_sha256": _h([t[0] for t in hdr["tensors"]]),'),
    (GI, "tensor shapes not an invariant",
     '                    "tensor_names_sha256", "tensor_shapes_sha256")', '                    "tensor_names_sha256",)'),
    (GI, "hparams not an invariant",
     '"n_params", "hparams_sha256",', '"n_params",'),
    (GI, "param count drops 1-D tensors",
     "        for d in dims:\n            n *= d", "        for d in dims[:1]:\n            n *= d"),
    (GI, "file_type made an invariant (every quant pair 'differs')",
     'INVARIANT_FIELDS = ("gguf_version",', 'INVARIANT_FIELDS = ("file_type", "gguf_version",'),
    (GI, "chunk boundary drops buffered bytes",
     "            self.buf = self.buf[keep_from:] + data", "            self.buf = data"),
    (CQ, "ctx not compared", '    return {"ctx": m.get("ctx"),', '    return {"ctx": None,'),
    (CQ, "prompt_options not compared",
     '            "prompt_options": json.dumps(m.get("prompt_options")',
     '            "prompt_options_ignored": json.dumps(None and m.get("prompt_options")'),
    (CQ, "question text not compared",
     '            "questions": {a: [r.get("question")', '            "questions": {a: [None'),
    (CQ, "sampling not compared", '            "sampling": json.dumps(s, sort_keys=True),',
     '            "sampling": None,'),
    (CQ, "UNKNOWN weights accepted", '        if ident.get("label") != "VERIFIED":', "        if False:"),
    (CQ, "incomplete run accepted", '        if not run.get("complete", False):', "        if False:"),
    (CQ, "same weights reported as a quantisation result",
     '"REPEATABILITY (same weights)" if same else "QUANTISATION"', '"QUANTISATION"'),
    (CQ, "fabricated treated as good-when-true", 'BAD_WHEN_TRUE = {"fabricated"}', "BAD_WHEN_TRUE = set()"),
    (CQ, "regressions and improvements swapped",
     '(out["regressions"] if good_b and not good_c else out["improvements"])',
     '(out["improvements"] if good_b and not good_c else out["regressions"])'),
    (CQ, "rag abstention judged without answerability",
     '                if arm == "rag" and f == "abstained":', "                if False:"),
    (CQ, "Persian changed rows not listed",
     '                    out["persian_rows_changed"].append("%s/%s" % (arm, cid))', "                    pass"),
    (CQ, "any speed difference reported as resolved", "        margin = hi - lo", "        margin = -1e9"),
    (CQ, "same-weights spread narrowed", "SAME_WEIGHTS_DECODE_SPREAD = (2.65, 4.37)",
     "SAME_WEIGHTS_DECODE_SPREAD = (3.0, 3.5)"),
    ("scripts/run_phase4.py", "harness prefill drifts from the embedded template",
     'FORCED_CLOSED_THINK = THINK_OPEN + "\\n\\n" + THINK_CLOSE + "\\n\\n"',
     'FORCED_CLOSED_THINK = THINK_OPEN + "\\n" + THINK_CLOSE + "\\n\\n"'),
    (LIB, "Q4_K_M registered with a wrong size", '        "size_bytes": 2740937888,', '        "size_bytes": 2740937889,'),
    (LIB, "Q8_0 claims not to think",
     '        "file": "Qwen3.5-4B-Q8_0.gguf",\n        "size_bytes": 4482403488,\n        "is_pinned_revision": False,\n        "thinking_by_default": True,',
     '        "file": "Qwen3.5-4B-Q8_0.gguf",\n        "size_bytes": 4482403488,\n        "is_pinned_revision": False,\n        "thinking_by_default": False,'),
    (LIB, "Q8_0 no longer marked reference-only",
     '"4.0, so it is a quality REFERENCE only, never a deployment "', '"4.0, so it is a candidate like any other, a deployment "'),
]


def oracle():
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    # A mutant that makes the reader loop forever (e.g. dropping buffered
    # bytes at a chunk boundary) is a detected defect, not a battery crash.
    # The clean oracle runs in well under a second (MEASURED ~0.3 s).
    try:
        p = subprocess.run([sys.executable, ORACLE], cwd=ROOT, env=env,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    except subprocess.TimeoutExpired:
        return False
    return p.returncode == 0


def main():
    if not oracle():
        print("ABORT: oracle fails before mutation")
        return 1
    killed = survived = skipped = 0
    surv, skips = [], []
    for i, (f, desc, find, repl) in enumerate(MUTATIONS, 1):
        path = os.path.join(ROOT, f)
        orig = open(path, encoding="utf-8").read()
        if orig.count(find) != 1:
            skipped += 1
            skips.append("%s: %s (count=%d)" % (f, desc, orig.count(find)))
            print("  %2d. SKIP     %s" % (i, desc))
            continue
        try:
            open(path, "w", encoding="utf-8").write(orig.replace(find, repl, 1))
            ok = oracle()
        finally:
            open(path, "w", encoding="utf-8").write(orig)
        if ok:
            survived += 1
            surv.append("%s: %s" % (f, desc))
            print("  %2d. SURVIVED %s" % (i, desc))
        else:
            killed += 1
            print("  %2d. killed   %s" % (i, desc))
    intact = oracle()
    print("=" * 70)
    print("  seeded %d  killed %d  survived %d  skipped %d  restored+green %s"
          % (len(MUTATIONS), killed, survived, skipped, intact))
    for s in surv:
        print("  SURVIVOR:", s)
    for s in skips:
        print("  SKIPPED: ", s)
    return 0 if (survived == 0 and skipped == 0 and intact) else 1


if __name__ == "__main__":
    sys.exit(main())
