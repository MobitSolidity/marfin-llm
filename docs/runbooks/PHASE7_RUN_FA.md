# فاز ۷ — مقایسهٔ کوانتیزاسیون‌ها روی i5-12400 (D-0121)

**تاریخ آماده‌سازی:** ۲۰۲۶-۱۰-۱۶ · **شاخه:** `genspark_ai_developer` (پس از `git pull`)

مدل در این sandbox اجرا نمی‌شود. هیچ عددی در این فایل از اجرای جدید نیامده است.

## چرا این اجرا

fine-tuning فعلاً انجام نمی‌شود (D-0115). پس در فاز ۷ چیزی برای «تبدیل» نداریم. فاز ۷
به این سؤال کوچک می‌شود: **آیا Q4_K_M (کوچک‌تر و احتمالاً سریع‌تر) به اندازهٔ Q5_K_M
فعلی خوب است؟** Q8_0 فقط مرجع کیفیت است. حجمش ۴٫۱۷ GiB است و از سقف مصوب ۴٫۰ بالاتر
است، پس هرگز گزینهٔ استقرار نیست.

آنچه در sandbox انجام و **اندازه‌گیری** شد:

| فایل | sha256 (کامل دانلود و هش شد) | حجم |
|---|---|---|
| `Qwen3.5-4B-Q5_K_M.gguf` (فعلی) | `8814232b85594dcd46c50e5b8b29324a7efe9e746edbe8a3d1df3d3fce7aad39` | ۲٫۹۲۸ GiB |
| `Qwen3.5-4B-Q4_K_M.gguf` | `00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4` | ۲٫۵۵۳ GiB |
| `Qwen3.5-4B-Q8_0.gguf` (اختیاری، فقط مرجع) | `10cc391b403021dd11c614679d2fd92f611c3681d29e29651b717316965d61e1` | ۴٫۱۷۵ GiB |

قالب چت، واژگان، merges، شناسه‌های توکن ویژه و مجموعهٔ تنسورها در هر سه فایل
**بایت‌به‌بایت یکسان** است (`evidence/phase7_gguf_headers_2026-10-16.json`). پس هر
تفاوتی در نتیجه فقط از دقت وزن‌ها می‌آید.

## ۱. دانلود و بررسی checksum (PowerShell)

```powershell
cd C:\models
curl.exe -L -o Qwen3.5-4B-Q4_K_M.gguf https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/resolve/e87f176479d0855a907a41277aca2f8ee7a09523/Qwen3.5-4B-Q4_K_M.gguf
Get-FileHash C:\models\Qwen3.5-4B-Q4_K_M.gguf -Algorithm SHA256
```

خروجی باید دقیقاً `00FE7986FF5F6B463E62455821146049DB6F9313603938A70800D1FB69EF11A4` باشد.
**اگر نبود، ادامه ندهید.** `run_phase4.py` هم خودش هش را بررسی می‌کند و در سرآیند
`identity : VERIFIED` نشان می‌دهد.

## ۲. اجرا — Q4_K_M (شش فرمان، هر کدام جدا)

همان مجموعهٔ ترکیبی فاز ۴ و همان پرچم‌های فاز ۶ استفاده می‌شوند. چون Q5_K_M با این
پرچم‌ها روی این مجموعه اجرا نشده بود، **Q5_K_M هم باید دوباره اجرا شود** تا مقایسه
فقط وزن‌ها را عوض کند.

```powershell
# Q4_K_M
python scripts\run_phase4.py --model C:\models\Qwen3.5-4B-Q4_K_M.gguf --arms rag --corpus evals\rag_corpus_combined.jsonl --gold evals\rag_gold_combined.jsonl --second-turn --refusal-language --execution-guard --min-trust 80 --out evals\results\p7q4_rag.json
python scripts\run_phase4.py --model C:\models\Qwen3.5-4B-Q4_K_M.gguf --arms tools --second-turn --refusal-language --execution-guard --min-trust 80 --out evals\results\p7q4_tools.json
python scripts\run_phase4.py --model C:\models\Qwen3.5-4B-Q4_K_M.gguf --arms plain --second-turn --refusal-language --execution-guard --min-trust 80 --out evals\results\p7q4_plain.json
# Q5_K_M (همان پرچم‌ها، همان روز)
python scripts\run_phase4.py --model C:\models\Qwen3.5-4B-Q5_K_M.gguf --arms rag --corpus evals\rag_corpus_combined.jsonl --gold evals\rag_gold_combined.jsonl --second-turn --refusal-language --execution-guard --min-trust 80 --out evals\results\p7q5_rag.json
python scripts\run_phase4.py --model C:\models\Qwen3.5-4B-Q5_K_M.gguf --arms tools --second-turn --refusal-language --execution-guard --min-trust 80 --out evals\results\p7q5_tools.json
python scripts\run_phase4.py --model C:\models\Qwen3.5-4B-Q5_K_M.gguf --arms plain --second-turn --refusal-language --execution-guard --min-trust 80 --out evals\results\p7q5_plain.json
```

### ادغام

```powershell
python scripts\merge_phase4.py evals\results\p7q4_rag.json evals\results\p7q4_tools.json evals\results\p7q4_plain.json --out evals\results\phase7_q4km_merged.json
python scripts\merge_phase4.py evals\results\p7q5_rag.json evals\results\p7q5_tools.json evals\results\p7q5_plain.json --out evals\results\phase7_q5km_merged.json
```

**زمان (ESTIMATED):** هر کوانت حدود ۷۰ تا ۹۰ دقیقه است، یعنی برای دو کوانت حدود ۲٫۵ تا ۳
ساعت. مبنای برآورد اجرای Q14 در ۲۰۲۶-۱۰-۰۹ است: ۸۹ دقیقه مدل‌گردانی. اگر بخواهید، Q8_0
را با همین سه فرمان و پیشوند `p7q8_` اجرا کنید (حدود ۴٫۵ GB دانلود). این اجرا اختیاری
است.

**ترتیب پیشنهادی:** Q4 و Q5 را در یک جلسه، پشت سر هم و بدون اجرای برنامهٔ سنگین دیگر
اجرا کنید. سرعت همین Q5_K_M در سه جلسهٔ مختلف بین ۲٫۶۵ و ۴٫۳۷ توکن بر ثانیه نوسان
داشته است (M). مقایسهٔ اسکریپت تفاوت کمتر از این نوسان را «حل‌نشده» گزارش می‌کند.

## ۳. چه بفرستید

`phase7_q4km_merged.json` و `phase7_q5km_merged.json` (و در صورت اجرا،
`phase7_q8_merged.json`).

## من با آن چه می‌کنم (آماده و آزموده)

```text
python3 scripts/compare_quants.py phase7_q5km_merged.json phase7_q4km_merged.json --out evidence/phase7_compare_q5_vs_q4.json
```

این اسکریپت مقایسه را **رد می‌کند** اگر دو اجرا در هر چیزی جز وزن‌ها فرق داشته باشند:
ctx، threads، max_tokens، نمونه‌گیری، پرچم‌ها یا متن سؤال‌ها. سطرهایی را که بدتر شده‌اند
یکی‌یکی فهرست می‌کند. پاسخ‌های فارسی را که تغییر کرده‌اند هم جدا فهرست می‌کند، چون
روانی فارسی را فقط انسان می‌تواند قضاوت کند (R10). تصمیم اینکه کدام کوانت بماند با
شماست.
