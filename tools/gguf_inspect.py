#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Read a GGUF header -- metadata and tensor table, never the weights -- from a
local file OR an https URL, using HTTP Range requests (D-0121, Phase 7).

Phase 7 "validate template and tokens" is a property of the HEADER: the chat
template, the vocabulary, the merges, the special-token ids. Those must be
byte-identical across quantisations of one model, or a "quantisation loss"
measurement would be confounded by a tokenizer or template change. This
reads only the first few MiB of a multi-GiB file, so it runs in the sandbox.

    python3 tools/gguf_inspect.py <path-or-url> [--json out.json]
"""
import argparse
import hashlib
import json
import struct
import sys
import urllib.request

GGUF_MAGIC = b"GGUF"
# ggml_type ids -> names (ggml.h). Only names are reported; unknown ids are
# reported as "type_<n>", never guessed.
GGML_TYPES = {0: "F32", 1: "F16", 2: "Q4_0", 3: "Q4_1", 6: "Q5_0", 7: "Q5_1", 8: "Q8_0",
              9: "Q8_1", 10: "Q2_K", 11: "Q3_K", 12: "Q4_K", 13: "Q5_K", 14: "Q6_K",
              15: "Q8_K", 16: "IQ2_XXS", 17: "IQ2_XS", 18: "IQ3_XXS", 19: "IQ1_S",
              20: "IQ4_NL", 21: "IQ3_S", 22: "IQ2_S", 23: "IQ4_XS", 24: "I8", 25: "I16",
              26: "I32", 27: "I64", 28: "F64", 29: "IQ1_M", 30: "BF16"}
_SCALAR = {0: "<B", 1: "<b", 2: "<H", 3: "<h", 4: "<I", 5: "<i", 6: "<f", 7: "<?",
           10: "<Q", 11: "<q", 12: "<d"}


class _Source:
    """Sequential reader over a file or a URL; URLs are fetched in ranged chunks."""

    def __init__(self, where, chunk=8 << 20):
        self.where, self.chunk, self.pos = where, chunk, 0
        self.buf, self.buf_at = b"", 0
        self.is_url = where.startswith(("http://", "https://"))
        self.fh = None if self.is_url else open(where, "rb")
        self.bytes_fetched = 0

    def _fill(self, need):
        if self.fh is not None:
            return
        while self.buf_at + len(self.buf) < self.pos + need:
            start = self.buf_at + len(self.buf)
            req = urllib.request.Request(self.where, headers={
                "Range": "bytes=%d-%d" % (start, start + self.chunk - 1),
                "User-Agent": "marfin-llm-gguf-inspect"})
            with urllib.request.urlopen(req, timeout=120) as r:
                if r.status != 206:
                    raise IOError("server ignored Range (HTTP %s); refusing to download "
                                  "the whole file" % r.status)
                data = r.read()
            if not data:
                raise EOFError("short read at %d" % start)
            self.bytes_fetched += len(data)
            # keep only what is still ahead of pos
            keep_from = max(0, self.pos - self.buf_at)
            self.buf = self.buf[keep_from:] + data
            self.buf_at += keep_from

    def read(self, n):
        if self.fh is not None:
            b = self.fh.read(n)
            if len(b) != n:
                raise EOFError("short read")
            self.pos += n
            return b
        self._fill(n)
        off = self.pos - self.buf_at
        b = self.buf[off:off + n]
        self.pos += n
        return b

    def unpack(self, fmt):
        return struct.unpack(fmt, self.read(struct.calcsize(fmt)))[0]

    def string(self):
        return self.read(self.unpack("<Q")).decode("utf-8", errors="replace")


def _value(src, t):
    if t in _SCALAR:
        return src.unpack(_SCALAR[t])
    if t == 8:
        return src.string()
    if t == 9:
        it, n = src.unpack("<I"), src.unpack("<Q")
        return [_value(src, it) for _ in range(n)]
    raise ValueError("unknown GGUF value type %d" % t)


def read_header(where, chunk=8 << 20):
    src = _Source(where, chunk=chunk)
    if src.read(4) != GGUF_MAGIC:
        raise ValueError("not a GGUF file (bad magic)")
    version = src.unpack("<I")
    n_tensors, n_kv = src.unpack("<Q"), src.unpack("<Q")
    kv = {}
    for _ in range(n_kv):
        k = src.string()
        kv[k] = _value(src, src.unpack("<I"))
    tensors = []
    for _ in range(n_tensors):
        name = src.string()
        nd = src.unpack("<I")
        dims = [src.unpack("<Q") for _ in range(nd)]
        ty = src.unpack("<I")
        src.unpack("<Q")                         # data offset (not needed)
        tensors.append((name, dims, GGML_TYPES.get(ty, "type_%d" % ty)))
    return {"version": version, "kv": kv, "tensors": tensors,
            "header_bytes": src.pos, "bytes_fetched": src.bytes_fetched}


def _h(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True)
                          .encode("utf-8")).hexdigest()


def summarise(hdr):
    """The comparable facts. Hashes stand in for the big arrays."""
    kv = hdr["kv"]
    arch = kv.get("general.architecture")
    types = {}
    n_params = 0
    for _, dims, ty in hdr["tensors"]:
        n = 1
        for d in dims:
            n *= d
        types[ty] = types.get(ty, 0) + n
        n_params += n
    special = {k: v for k, v in kv.items()
               if k.startswith("tokenizer.ggml.") and k.endswith("_token_id")}
    hparams = {k: v for k, v in kv.items()
               if arch and k.startswith(arch + ".") and not isinstance(v, list)}
    tmpl = kv.get("tokenizer.chat_template")
    return {
        "gguf_version": hdr["version"],
        "architecture": arch,
        "file_type": kv.get("general.file_type"),
        "quantized_by": kv.get("general.quantized_by"),
        "n_tensors": len(hdr["tensors"]),
        "n_params": n_params,
        "params_by_type": dict(sorted(types.items())),
        "hparams": hparams,
        "hparams_sha256": _h(hparams),
        "chat_template_sha256": hashlib.sha256(tmpl.encode("utf-8")).hexdigest() if tmpl else None,
        "chat_template_chars": len(tmpl) if tmpl else 0,
        "tokenizer_model": kv.get("tokenizer.ggml.model"),
        "tokenizer_pre": kv.get("tokenizer.ggml.pre"),
        "vocab_size": len(kv.get("tokenizer.ggml.tokens") or []),
        "tokens_sha256": _h(kv.get("tokenizer.ggml.tokens")),
        "token_type_sha256": _h(kv.get("tokenizer.ggml.token_type")),
        "merges_n": len(kv.get("tokenizer.ggml.merges") or []),
        "merges_sha256": _h(kv.get("tokenizer.ggml.merges")),
        "special_token_ids": special,
        "special_tokens": {k: (kv.get("tokenizer.ggml.tokens") or [None] * (v + 1))[v]
                           for k, v in special.items()
                           if isinstance(v, int) and v < len(kv.get("tokenizer.ggml.tokens") or [])},
        # Order-INSENSITIVE: BF16 lists the same 426 tensors in a different
        # order (MEASURED 2026-10-16), which is a writer detail, not a model
        # difference. The order is still reported, as a non-invariant field.
        "tensor_names_sha256": _h(sorted(t[0] for t in hdr["tensors"])),
        "tensor_shapes_sha256": _h(sorted([t[0], t[1]] for t in hdr["tensors"])),
        "tensor_order_sha256": _h([t[0] for t in hdr["tensors"]]),
        "tensor_types": {t[0]: t[2] for t in hdr["tensors"]},
        "header_bytes": hdr["header_bytes"],
        "bytes_fetched": hdr["bytes_fetched"],
    }


#: Fields that MUST be identical across quantisations of one model. A
#: difference in any of them means two files are not the same model at
#: different precision, and a quality comparison between them is confounded.
INVARIANT_FIELDS = ("gguf_version", "architecture", "n_tensors", "n_params", "hparams_sha256",
                    "chat_template_sha256", "tokenizer_model", "tokenizer_pre", "vocab_size",
                    "tokens_sha256", "token_type_sha256", "merges_sha256", "special_token_ids",
                    "tensor_names_sha256", "tensor_shapes_sha256")


def compare(summaries):
    """{field: {name: value}} for every invariant field that differs."""
    names = list(summaries)
    diffs = {}
    for f in INVARIANT_FIELDS:
        vals = {n: summaries[n].get(f) for n in names}
        if len({json.dumps(v, sort_keys=True) for v in vals.values()}) > 1:
            diffs[f] = vals
    return diffs


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("where", nargs="+", help="GGUF path(s) or URL(s)")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    out = {}
    for w in a.where:
        s = summarise(read_header(w))
        out[w.rsplit("/", 1)[-1]] = s
    res = {"summaries": out, "invariant_differences": compare(out) if len(out) > 1 else None}
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(res, f, indent=2, ensure_ascii=False)
    print(json.dumps({k: {f: v[f] for f in ("architecture", "file_type", "vocab_size",
                                            "chat_template_sha256", "params_by_type",
                                            "bytes_fetched")}
                      for k, v in out.items()}, indent=1))
    print("invariant differences:", json.dumps(res["invariant_differences"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
