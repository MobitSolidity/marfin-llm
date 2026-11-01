# -*- coding: utf-8 -*-
"""
Crypto token lookup (D-0143): a name, a symbol or a contract address in, one coin
or a ranked list of candidates out. CoinGecko is the only source (owner's choice,
D-0142); "Powered by CoinGecko" is attached to every result.

WHAT IT DOES
------------
classify(text)  normalises the input (NFKC, Persian/Arabic digits to ASCII, ZWNJ and
                other zero-width marks removed, Arabic yeh/kaf to Persian) and decides:
                  evm      0x + 40 hex (any case; compared lower-case, as CoinGecko
                           stores it -- MEASURED in tests/fixtures/coingecko/)
                  tron     base58check, 25 bytes, version byte 0x41, double-SHA256
                           checksum valid (so a mistyped Tron address is refused)
                  solana   base58, decodes to exactly 32 bytes
                  name     anything else with a letter, 1..64 characters
                  invalid  with the reason
resolve(text)   addresses: the chains are tried in the owner's order (Ethereum, BSC,
                Polygon, Base, Arbitrum for EVM; Solana; Tron) and the FIRST chain that
                knows the contract wins -- the others are reported as "not checked", so
                the keyless budget (about 5 calls a minute) is not spent proving a
                negative. Names and symbols: one /search, then
                  one exact id/name match            -> resolved
                  else exactly one exact symbol match -> resolved
                  else any matches                   -> AMBIGUOUS, ranked candidates
                                                        (market-cap rank, then
                                                        CoinGecko's order); never a
                                                        silent pick
                  else                               -> not found, said plainly

NEVER
-----
- No guess: a coin CoinGecko does not return is "not found", never a near miss.
- No retry on a 429 and no work-around for the budget: the result says
  "rate_limited" with the chains already checked, and the UI says when to try again.
- EIP-55 mixed-case checksums are NOT verified: Keccak-256 is not in the standard
  library (hashlib.sha3_256 is a different function). The address is compared
  lower-case, which is how CoinGecko returns it.

PERSIAN NAMES
-------------
ALIASES_FA is a STATIC table written by hand (labelled as such wherever it is used):
it only turns a Persian name into an English search word. The coin itself still
comes from CoinGecko's /search, so a wrong alias can only produce "not found".
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Any, Dict, List, Optional

from market import coingecko as CG

#: STATIC (hand-written, not from CoinGecko): Persian name -> English search word.
ALIASES_FA = {
    "بیت کوین": "bitcoin", "بیتکوین": "bitcoin", "اتریوم": "ethereum", "اتر": "ethereum",
    "تتر": "tether", "سولانا": "solana", "ریپل": "ripple", "دوج کوین": "dogecoin", "دوجکوین": "dogecoin",
    "کاردانو": "cardano", "ترون": "tron", "شیبا": "shiba inu", "شیبا اینو": "shiba inu",
    "تون کوین": "toncoin", "تون": "toncoin", "لایت کوین": "litecoin", "لایتکوین": "litecoin",
    "پولکادات": "polkadot", "یونی سواپ": "uniswap", "یونیسواپ": "uniswap", "چین لینک": "chainlink",
    "چینلینک": "chainlink", "آوالانچ": "avalanche", "اولانچ": "avalanche", "بایننس کوین": "bnb",
    "بی ان بی": "bnb", "یو اس دی سی": "usd coin", "پالیگان": "polygon", "مونرو": "monero",
}
ALIAS_LABEL = "STATIC alias table (hand-written Persian name -> English search word; the coin itself is from CoinGecko)"

_FA_DIGITS = {ord(a): str(i) for i, a in enumerate("۰۱۲۳۴۵۶۷۸۹")}
_FA_DIGITS.update({ord(a): str(i) for i, a in enumerate("٠١٢٣٤٥٦٧٨٩")})
_FA_DIGITS.update({0x064A: "ی", 0x0643: "ک", 0x0649: "ی"})
_ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u200e\u200f\u2066\u2067\u2068\u2069\ufeff"), None)
_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_B58_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]+$")
_EVM_ANY = re.compile(r"^0[xX][0-9a-fA-F]{40}$")
#: Chains per address kind, in the owner's order (CoinGecko platform ids from CG.PLATFORMS).
CHAINS = {"evm": [p for p in CG.PLATFORMS if p[3] == "evm"],
          "solana": [p for p in CG.PLATFORMS if p[3] == "solana"],
          "tron": [p for p in CG.PLATFORMS if p[3] == "tron"]}
MAX_CANDIDATES = 10


def normalise(text: Any) -> str:
    t = unicodedata.normalize("NFKC", str(text or ""))
    t = t.translate(_ZERO_WIDTH).translate(_FA_DIGITS)
    return " ".join(t.split())


def b58decode(s: str) -> Optional[bytes]:
    if not s or not _B58_RE.match(s):
        return None
    n = 0
    for ch in s:
        n = n * 58 + _B58.index(ch)
    body = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\x00" * (len(s) - len(s.lstrip("1"))) + body


def _tron_ok(raw: bytes) -> bool:
    if len(raw) != 25 or raw[0] != 0x41:
        return False
    return hashlib.sha256(hashlib.sha256(raw[:21]).digest()).digest()[:4] == raw[21:]


def classify(text: Any) -> Dict[str, str]:
    """{'kind': evm|tron|solana|name|invalid, 'value': normalised input, 'reason': why invalid}."""
    t = normalise(text)
    if not t:
        return {"kind": "invalid", "value": "", "reason": "empty"}
    if " " not in t and t[:2].lower() == "0x":
        if _EVM_ANY.match(t):
            return {"kind": "evm", "value": t.lower(), "reason": ""}
        return {"kind": "invalid", "value": t, "reason": "starts with 0x but is not 0x followed by 40 hex digits"}
    if " " not in t and 25 <= len(t) <= 50 and _B58_RE.match(t):
        raw = b58decode(t)
        if t[0] == "T" and len(t) == 34:
            if raw is not None and _tron_ok(raw):
                return {"kind": "tron", "value": t, "reason": ""}
            if raw is None or len(raw) != 32:
                return {"kind": "invalid", "value": t, "reason": "looks like a Tron address but its checksum is wrong"}
        if raw is not None and len(raw) == 32 and len(t) >= 32:
            return {"kind": "solana", "value": t, "reason": ""}
        if len(t) >= 32:
            return {"kind": "invalid", "value": t, "reason": "not a valid Solana or Tron address"}
    if " " not in t and 32 <= len(t) <= 50 and t.isascii() and t.isalnum():
        # an address-shaped string that is not valid base58: Solana and Tron addresses are
        # case-sensitive, so a lower-cased or mistyped one is refused, never searched as a name
        return {"kind": "invalid", "value": t, "reason": "looks like an address but is not valid base58 "
                "(Solana and Tron addresses are case-sensitive; paste it exactly)"}
    if len(t) > 64:
        return {"kind": "invalid", "value": t[:64], "reason": "longer than 64 characters"}
    if not any(ch.isalpha() for ch in t):
        return {"kind": "invalid", "value": t, "reason": "a name or symbol needs at least one letter"}
    return {"kind": "name", "value": t, "reason": ""}


def _alias(q: str) -> Optional[str]:
    return ALIASES_FA.get(q) or ALIASES_FA.get(q.replace(" ", ""))


def rank(coins: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Market-cap rank first (unranked last), CoinGecko's own order breaking ties."""
    return [c for _i, c in sorted(enumerate(coins), key=lambda ic: (ic[1].get("rank") is None,
                                                                    ic[1].get("rank") or 0, ic[0]))]


def pick(query: str, coins: List[Dict[str, Any]]) -> Dict[str, Any]:
    """The matching rule, pure (tested directly): resolved / ambiguous / not_found."""
    q = query.casefold()
    exact = [c for c in coins if c["id"] == q or c["name"].casefold() == q]
    if len(exact) == 1:
        others = [c for c in coins if c is not exact[0]]
        return {"status": "resolved", "coin_id": exact[0]["id"], "match": "name",
                "candidates": rank(others)[:MAX_CANDIDATES]}
    sym = [c for c in coins if c["symbol"].casefold() == q]
    if not exact and len(sym) == 1:
        others = [c for c in coins if c is not sym[0]]
        return {"status": "resolved", "coin_id": sym[0]["id"], "match": "symbol",
                "candidates": rank(others)[:MAX_CANDIDATES]}
    pool = exact or sym or coins
    if pool:
        return {"status": "ambiguous", "coin_id": None, "match": "exact" if (exact or sym) else "partial",
                "candidates": rank(pool)[:MAX_CANDIDATES]}
    return {"status": "not_found", "coin_id": None, "match": None, "candidates": []}


def _base(text, c, vs):
    from rag.sources import required_notices
    return {"input": str(text or "")[:120], "kind": c["kind"], "query": c["value"], "vs": vs, "status": None,
            "reason": c.get("reason", ""), "coin": None, "candidates": [], "checked": [], "alias": None,
            "label": "RETRIEVED (CoinGecko, aggregated across exchanges; indicative, not real-time)",
            "notices": required_notices(["coingecko"]), "error": None}


def resolve(text: Any, hub: Any, vs: str = "usd") -> Dict[str, Any]:
    """
    Resolve through the DataHub (cache + per-minute budget). `hub` needs crypto_search,
    crypto_coin and crypto_contract; each returns None for "CoinGecko has no such coin" and
    raises hub.DataError (hub.RateBudget for the budget) for everything else. The exception
    types are read from the hub, not imported: rag.datahub imports this module, and an import
    back would be a cycle (tests/test_attribution.py checks the import graph).
    """
    DataError, RateBudget = hub.DataError, hub.RateBudget
    c = classify(text)
    out = _base(text, c, vs)
    if c["kind"] == "invalid":
        out["status"] = "invalid"
        return out
    try:
        if c["kind"] in CHAINS:
            chains = CHAINS[c["kind"]]
            for i, (_k, pid, label, _kind) in enumerate(chains):
                coin = hub.crypto_contract(pid, c["value"], vs)
                if coin is None:
                    out["checked"].append((label, "not_found"))
                    continue
                out["checked"].append((label, "found"))
                out["checked"] += [(p[2], "not_checked") for p in chains[i + 1:]]
                out["status"], out["coin"] = "resolved", dict(coin, found_on=label)
                return out
            out["status"] = "not_found"
            return out
        q = c["value"]
        alias = _alias(q)
        if alias:
            out["alias"] = {"fa": q, "search": alias, "label": ALIAS_LABEL}
            q = alias
        found = pick(q, hub.crypto_search(q))
        out["candidates"] = found["candidates"]
        out["match"] = found["match"]
        if found["status"] != "resolved":
            out["status"] = found["status"]
            return out
        out["coin_id"] = found["coin_id"]
        coin = hub.crypto_coin(found["coin_id"], vs)
        if coin is None:                      # listed by /search, then 404 on detail: say so
            out["status"] = "not_found"
            out["reason"] = "CoinGecko's search listed %s but has no detail for it" % found["coin_id"]
            return out
        out["status"], out["coin"] = "resolved", coin
        return out
    except RateBudget as exc:
        out["status"], out["error"] = "rate_limited", str(exc)
        out["retry_after_s"] = exc.retry_after_s
        out["checked"] += [(p[2], "not_checked") for p in CHAINS.get(c["kind"], [])
                           if p[2] not in [x[0] for x in out["checked"]]]
        return out
    except DataError as exc:
        msg = str(exc)
        out["status"] = "rate_limited" if "429" in msg else "error"
        out["error"] = msg
        return out
