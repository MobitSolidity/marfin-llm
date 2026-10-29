# فاز ۶ — اجرای دوباره بعد از F1 تا F4 (D-0119)

**تاریخ:** ۲۰۲۶-۱۰-۱۴ · **شاخه:** `genspark_ai_developer` (پس از `git pull`)

مدل در این sandbox اجرا نمی‌شود. هیچ عددی در این فایل از اجرای جدید نیامده است.

## چه چیزی تغییر کرد

| | تغییر | پرچم |
|---|---|---|
| **F1** | هر پاسخی که ادعا کند سفارش یا معامله‌ای «انجام شد»، پیش از نمره‌دهی با یک پیام ثابت امتناع جایگزین می‌شود. متن اصلی در فایل نتیجه نگه داشته می‌شود. | `--execution-guard` |
| **F2** | در RAG فقط سندهایی که اعتبارشان ۸۰ یا بیشتر است به مدل نشان داده می‌شوند. آستانهٔ ۸۰ همان آستانه‌ای است که برای نقل عدد استفاده می‌شود. | `--min-trust 80` |
| **F3** | ابزار جدید `fx_convert` برای تبدیل ارز. جهت نرخ باید صریح گفته شود و هرگز حدس زده نمی‌شود. | خودکار |
| **F4** | gold مجموعهٔ red team درست شد: `evals/redteam_gold_v2.jsonl`. فایل v1 دست‌نخورده می‌ماند. | `--gold …v2` |

بدون این پرچم‌ها، اجرای قبلی بایت‌به‌بایت قابل بازتولید است (با آزمون تثبیت شده).

## فرمان‌ها (PowerShell)

```powershell
python scripts\run_phase4.py --model C:\models\Qwen3.5-4B-Q5_K_M.gguf --arms rag --corpus evals\redteam_corpus_v1.jsonl --gold evals\redteam_gold_v2.jsonl --second-turn --refusal-language --execution-guard --min-trust 80 --out evals\results\p6rt2_rag.json
python scripts\run_phase4.py --model C:\models\Qwen3.5-4B-Q5_K_M.gguf --arms tools --evals evals\redteam_eval_v1.jsonl --second-turn --refusal-language --execution-guard --min-trust 80 --out evals\results\p6rt2_tools.json
python scripts\run_phase4.py --model C:\models\Qwen3.5-4B-Q5_K_M.gguf --arms plain --evals evals\redteam_eval_v1.jsonl --second-turn --refusal-language --execution-guard --min-trust 80 --out evals\results\p6rt2_plain.json
python scripts\merge_phase4.py evals\results\p6rt2_rag.json evals\results\p6rt2_tools.json evals\results\p6rt2_plain.json --out evals\results\phase6_redteam2_merged.json
```

هر سه فرمان باید **همهٔ** پرچم‌ها را داشته باشند، وگرنه ادغام امتناع می‌کند. برای همین
`--min-trust` روی plain و tools هم گذاشته شده، هرچند آنجا اثری ندارد. **زمان
(ESTIMATED):** حدود ۲۰ تا ۲۵ دقیقه. آزمون متن طولانی لازم نیست تکرار شود، چون ۹ از ۹
درست بود.

بعد فایل **`phase6_redteam2_merged.json`** را برای من بفرستید.
