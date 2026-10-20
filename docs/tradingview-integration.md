# TradingView — what is and is not supported (Phase 9, D-0126)

**Verdict (V):** machine use is **prohibited** by TradingView's Terms of Use §3. See
`docs/legal/tradingview-terms-review.md` and `tools/verify_tradingview_terms.py`.

| Level | Supported? | How |
|---|---|---|
| Scraping or the charting API for data | **No** | prohibited; `rag.sources.tradingview` is disabled |
| CSV the user exports | Yes | `src/market/csv_import.py`; values labelled USER_EXPORTED and validated |
| Webhook alerts | Yes, **as notifications only** | `src/market/webhooks.py`: 16 validations (HTTPS, HMAC, size, age, replay, schema, instruction refusal). Events carry no side, quantity or account; execution has no import path from webhooks. |
| Screenshots | Yes, as unverified context | `src/market/screenshot.py`: every value UNVERIFIED / VISUALLY_EXTRACTED; never an order input |
| Order execution from alerts | **No** | SS.6.5: an alert is not standing authorization |
