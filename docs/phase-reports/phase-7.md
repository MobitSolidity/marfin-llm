# Phase 7 Review — GGUF Validation and Quantisation

Project: marfin-llm · Date: 2026-10-16 · Governing prompt: SYSTEM_PROMPT.md v2.0 (SS.24 Phase 7)
Mode: `ANALYSIS_ONLY` · Live trading: `DISABLED` · Label key: (V) VERIFIED · (M) MEASURED · (C) COMPUTED · (E) ESTIMATED

## Status: **IN PROGRESS** — sandbox half done; the quality/speed/RAM comparison needs the i5-12400

Approved by the user 2026-10-14 ("3: yes i approve and go to phase 7"), D-0121.

## Scope, given D-0115 (fine-tuning "not now")

There are no trained weights, so four of the SS.24 tasks have nothing to act on. This is stated, not
glossed over:

| SS.24 Phase 7 task | Status |
|---|---|
| Save model/tokenizer | **N/A**: no fine-tuned weights exist |
| Merge if permitted | **N/A**: no adapter to merge |
| Convert to GGUF | **N/A**: upstream already publishes GGUF of the base model (Apache-2.0, V from the GGUF header `general.license`) |
| Produce Q4_K_M and Q5_K_M (optionally Q8_0) | **Done by sourcing**, not by quantising here: the upstream files from `unsloth/Qwen3.5-4B-GGUF` at revision `e87f1764`. Requantising from BF16 in the sandbox is impossible (an 8.4 GB source and 0.35 GiB of RAM) and would only reproduce them |
| Validate template and tokens | **Done (M)**, below |
| Generate checksums | **Done (M)**: full streamed sha256 of Q4_K_M and Q8_0; Q5_K_M was already VERIFIED (2026-08-17) |
| Compare quality, speed, RAM, size | Size **done (M)**. Quality, speed and RAM are **pending** the i5-12400 run (`PHASE7_RUN_FA.md`) |

If fine-tuning is approved later, this phase reruns in full: convert, quantise, validate with the same tools.

## Checksums (M)

Each file was streamed in full from the pinned revision and hashed with hashlib. The first 4 bytes were `GGUF`
and the byte count was taken. The HF LFS oid agrees, but it was not the source.

| File | sha256 | Bytes | GiB |
|---|---|---|---|
| Q4_K_M | `00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4` | 2,740,937,888 | 2.553 |
| Q5_K_M (in use) | `8814232b85594dcd46c50e5b8b29324a7efe9e746edbe8a3d1df3d3fce7aad39` | 3,143,656,608 | 2.928 |
| Q8_0 (reference) | `10cc391b403021dd11c614679d2fd92f611c3681d29e29651b717316965d61e1` | 4,482,403,488 | **4.175: above the 4.0 GiB cap** |

Q4_K_M and Q8_0 are registered in `KNOWN_MODEL_FILES`, so a run on either reports `identity: VERIFIED`.

## Template and token validation (M)

`tools/gguf_inspect.py` reads the GGUF header (metadata and tensor table, never the weights) over HTTP
Range requests: at most 16 MiB per file. Six upstream files were compared: BF16, Q4_K_M, Q5_K_M, Q6_K, Q8_0
and UD-Q4_K_XL. Evidence: `evidence/phase7_gguf_headers_2026-10-16.json`.

- **Identical across all six:** architecture `qwen35`, every hyperparameter, the chat template (sha
  `7f0e5290…`), tokenizer model and pre-tokenizer, the 248,320-token vocabulary, token types, 247,587 merges,
  the special-token ids (eos `<|im_end|>` 248046, pad `<|vision_pad|>` 248055), and the set of 426 tensor
  names and shapes.
- **What differs is only precision.** From Q5_K_M to Q4_K_M, 131 tensors go Q5_K → Q4_K and 48 go Q6_K → Q5_K.
  The other 247 are unchanged (177 F32, 48 Q8_0, 22 Q6_K).
- BF16 lists its tensors in a different order. That is a writer detail, so the tool compares the tensor set,
  not the order. My first comparison treated order as identity and flagged BF16, which was a false alarm.

**Finding: the embedded template differs from the HF `tokenizer_config.json` template.** Earlier phases
pinned the prompt against the HF config. The two templates differ in 2 places:

1. The tool-argument loop (`|items` vs a `mapping` check).
2. The **default** thinking mode. The HF template opens `<think>` unless `enable_thinking=false`. The
   GGUF template pre-closes it unless `enable_thinking=true`.

**Effect on recorded runs: none (V).** The harness always sends the `enable_thinking=false` form
(`chatml_prompt_no_think`, D-0087), and both templates render that byte-identically. Pinned in the tests for
the first turn and for the tool second turn. The difference would matter only to a client that uses the
embedded template's default, such as Ollama or LM Studio in Phase 8. There, Qwen3.5 would **not** think by
default. That is recorded for Phase 8.

## Comparison instrument (ready, tested)

`scripts/compare_quants.py BASELINE CANDIDATE`:

- **Refuses** two runs that differ in anything but the weights: ctx, threads, max_tokens, cap, sampling,
  prompt_options, case ids, or question text. It also refuses UNKNOWN weights and incomplete runs. Two runs
  of the same weights are labelled REPEATABILITY.
- Lists every per-row regression and improvement. `fabricated` is bad-when-true, and RAG abstention is judged
  against answerability.
- Lists every changed Persian reply for a human (R10). Fluency is not scored mechanically.
- Calls a speed difference **NOT RESOLVED** unless it exceeds the measured session-to-session spread of the
  same Q5_K_M weights: 2.65–4.37 tok/s (M, 2026-10-09 vs 2026-10-14).

Tests: `tests/test_phase7.py` has 63 assertions, run on GGUF files built byte by byte from the format spec.
`tests/mutate_phase7.py` has 31 mutants, all killed. The first pass had 1 survivor (a reshape keeping the
parameter count), now pinned. A mutant that made the reader loop forever exposed a battery crash on timeout,
which is fixed.

## What I expect, labelled ESTIMATED, so the run can falsify it

- Size −0.375 GiB (C, exact).
- Decode speed: CPU decode is memory-bandwidth bound, so it should scale roughly with bytes read per token,
  about 2.93/2.55 ≈ **+15 %** (E). Even so, it would stay far below the 8 tok/s threshold.
- Quality: unknown. The model is small, so 4-bit loss is plausible on Persian and on numbers. That is what the
  run measures.

## Acceptance criteria (SS.24 Phase 7)

| Criterion | Status |
|---|---|
| Artefacts load | **Pending** (i5-12400). Headers parse and match (M) |
| Persian remains acceptable | **Pending** (needs the run, then a human read of changed rows) |
| Tool format remains acceptable | **Pending** (schema validity per quant). The template is identical (M) |
| Quantisation loss acceptable | **Pending** |

## Next step

Run `PHASE7_RUN_FA.md` on the i5-12400 and send `phase7_q4km_merged.json` and `phase7_q5km_merged.json`.
Q5_K_M is run again under the same flags in the same session, so only the weights differ.
