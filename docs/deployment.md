# Deployment (Phase 9, D-0126) — Windows 11, i5-12400, CPU only

**1. Model** (VERIFY the checksum before use):
```powershell
Get-FileHash C:\models\Qwen3.5-4B-Q4_K_M.gguf -Algorithm SHA256
# 00FE7986FF5F6B463E62455821146049DB6F9313603938A70800D1FB69EF11A4
```
Source: `unsloth/Qwen3.5-4B-GGUF`, revision `e87f176479d0855a907a41277aca2f8ee7a09523`.

**2. Python 3.12 environment**
```powershell
python -m venv .venv; .venv\Scripts\activate; pip install -r requirements.txt
```

**3. Recommended runtime: in-process llama.cpp** (D-0126; fastest TTFT and lowest RAM, MEASURED in D-0125)
```powershell
python scripts\run_phase4.py --model C:\models\Qwen3.5-4B-Q4_K_M.gguf --arms plain `
  --second-turn --refusal-language --execution-guard --min-trust 80 --display --continue-budget 256 `
  --out evals\results\run.json
```

**Alternatives** (results are per runtime: 7/21 and 2/74 replies are identical to the in-process run):
- **LM Studio:** load the GGUF with ctx 16384 and start the server. Then add `--server lmstudio --model-id <id>`.
- **Ollama** (not recommended on this machine: TTFT 53–58 s, peak 6762 MB):
  ```powershell
  ollama create marfin-q4 -f deploy\ollama\Modelfile
  ollama run marfin-q4 --think=false "..."
  ```

**3a. The web UI** (D-0140): every capability on one right-to-left page, at http://127.0.0.1:8765 (loopback only). Persian guide: `docs/guides/ui-fa.md`.
```powershell
python scripts\ui.py --model C:\models\Qwen3.5-4B-Q4_K_M.gguf
python scripts\ui.py                      # without a model: everything except "ask"
```

**3b. Ask your own question** (D-0135). The same prompts, options and checks as the recommended run above:
```powershell
python scripts\ask.py --model C:\models\Qwen3.5-4B-Q4_K_M.gguf "What was Apple's net income in fiscal 2023?"
python scripts\ask.py --model C:\models\Qwen3.5-4B-Q4_K_M.gguf      # interactive; /quit to leave
```
Live US macro data and central-bank policy rates need `setx FRED_API_KEY <key>` (FRED) and network access
(BIS needs no key). `--no-macro` keeps every question offline. `--server lmstudio --model-id <id>` uses a loopback
server instead of loading the model in-process. On Windows the answer is ALSO opened as a right-to-left HTML page
(`%USERPROFILE%\.marfin\ask_answer.html`), because the Windows console cannot shape Persian (D-0136);
`--no-open` / `--no-html` turn that off. Guide in Persian: `docs/guides/ask-fa.md`.

**4. Execution mode.** No config file means ANALYSIS_ONLY. To enable paper trading, create
`%USERPROFILE%\.marfin\execution.conf`:
```
mode = PAPER_TRADING
i_have_enabled_paper_trading = yes
```
LIVE_TRADING cannot be reached by configuration (SS.6.1).

**5. Verify the installation**
```bash
bash tests/run_all.sh          # 31 suites; no model needed
```

**Secrets:** API keys go in environment variables (see `.env.example`), never in files under version control.
