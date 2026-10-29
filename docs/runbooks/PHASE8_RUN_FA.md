# فاز ۸ — Ollama و LM Studio روی i5-12400 (D-0123)

**تاریخ آماده‌سازی:** ۲۰۲۶-۱۰-۱۷ · **شاخه:** `genspark_ai_developer` (پس از `git pull`)

مدل در این sandbox اجرا نمی‌شود. هیچ عددی در این فایل از اجرای جدید نیامده است.

## پیش از شروع: دو اصلاحی که خواستید انجام شده‌اند

| | اصلاح | چطور |
|---|---|---|
| **۱. داوری فارسی شما** | ثبت شد: Q4 بهتر در ۱۰ سطر، Q5 بهتر در ۷ سطر، برابر در ۷ سطر. سه ایرادی که گفتید با پرچم `--style` رفع می‌شوند: (الف) **فرمول ساده** — LaTeX مثل `\frac` و `\text` پیش از نمایش به متن ساده تبدیل می‌شود (۱۵۰ / ۸٫۴۰) و هیچ عددی تغییر نمی‌کند؛ (ب) **یک زبان** — جوابِ کامل به زبان سؤال، و فقط اصطلاح کلیدی یک بار داخل پرانتز به زبان دیگر؛ (ج) **جواب ناقص** — همهٔ جواب‌هایی که «ناقص» دانستید به سقف ۵۱۲ توکن رسیده و قطع شده بودند. حالا از مدل خواسته می‌شود اول جواب را بدهد و کوتاه بنویسد، و هر جوابی که به سقف برسد علامت `hit_budget` می‌گیرد. | `--style` |
| **۲. انتخاب کوانت** | **Q4_K_M**. داوری شما (۱۰ در برابر ۷) و همهٔ معیارهای خودکار به نفع آن است: محاسبه ۱۰۰٪ در برابر ۷۵٪، ۴ آستانهٔ PASS در برابر ۳، و اولین توکن حدود ۳۰ ثانیه در برابر ۴۸ تا ۷۱ ثانیه. در برابرش: حدود ۰٫۹ GiB رم بیشتر (هنوز زیر سقف ۶)، و ۵ مورد از ۷ موردی که Q5 بهتر بود. این‌ها را پایین‌تر فهرست کرده‌ام. | `Qwen3.5-4B-Q4_K_M.gguf` |

## ۱. Ollama

### نصب و ساخت مدل

`deploy\ollama\Modelfile` آماده است. این فایل همان قالب ChatML اجراهای اندازه‌گیری‌شده، همان پرامپت سیستمی (با قوانین سبک) و همان تنظیمات را دارد: حریصانه، seed ثابت، ctx 16384 و ۵۱۲ توکن.

```powershell
Get-FileHash C:\models\Qwen3.5-4B-Q4_K_M.gguf -Algorithm SHA256
# باید 00FE7986FF5F6B463E62455821146049DB6F9313603938A70800D1FB69EF11A4 باشد
ollama create marfin-q4 -f deploy\ollama\Modelfile
ollama run marfin-q4 "نسبت P/E سهمی با قیمت ۱۵۰ و سود هر سهم ۸٫۴ چقدر است؟"
```

### اجرای ارزیابی: دو اجرا، تا در هر مقایسه فقط یک چیز عوض شود

**الف) Q4_K_M داخل پایتون (llama.cpp) با `--style`.** این اجرا اثر **سبک** را جدا می‌سنجد: مقایسه با فاز ۷ که همان وزن‌ها و همان اجراکننده بود، فقط بدون `--style`.

```powershell
python scripts\run_phase4.py --model C:\models\Qwen3.5-4B-Q4_K_M.gguf --arms rag --corpus evals\rag_corpus_combined.jsonl --gold evals\rag_gold_combined.jsonl --second-turn --refusal-language --execution-guard --min-trust 80 --style --out evals\results\p8st_rag.json
python scripts\run_phase4.py --model C:\models\Qwen3.5-4B-Q4_K_M.gguf --arms tools --second-turn --refusal-language --execution-guard --min-trust 80 --style --out evals\results\p8st_tools.json
python scripts\run_phase4.py --model C:\models\Qwen3.5-4B-Q4_K_M.gguf --arms plain --second-turn --refusal-language --execution-guard --min-trust 80 --style --out evals\results\p8st_plain.json
python scripts\merge_phase4.py evals\results\p8st_rag.json evals\results\p8st_tools.json evals\results\p8st_plain.json --out evals\results\phase8_style_merged.json
```

**ب) همان Q4_K_M از طریق Ollama، با همان پرچم‌ها.** این اجرا اثر **اجراکننده** را جدا می‌سنجد: مقایسه با (الف).

```powershell
python scripts\run_phase4.py --server ollama --model-id marfin-q4 --model C:\models\Qwen3.5-4B-Q4_K_M.gguf --arms rag --corpus evals\rag_corpus_combined.jsonl --gold evals\rag_gold_combined.jsonl --second-turn --refusal-language --execution-guard --min-trust 80 --style --out evals\results\p8ol_rag.json
python scripts\run_phase4.py --server ollama --model-id marfin-q4 --model C:\models\Qwen3.5-4B-Q4_K_M.gguf --arms tools --second-turn --refusal-language --execution-guard --min-trust 80 --style --out evals\results\p8ol_tools.json
python scripts\run_phase4.py --server ollama --model-id marfin-q4 --model C:\models\Qwen3.5-4B-Q4_K_M.gguf --arms plain --second-turn --refusal-language --execution-guard --min-trust 80 --style --out evals\results\p8ol_plain.json
python scripts\merge_phase4.py evals\results\p8ol_rag.json evals\results\p8ol_tools.json evals\results\p8ol_plain.json --out evals\results\phase8_ollama_merged.json
```

- `--model` در اجرای Ollama فقط برای **هش کردن** فایل است، تا نتیجه به وزن‌های VERIFIED گره بخورد. مدل را Ollama اجرا می‌کند.
- پرامپت با `raw=true` فرستاده می‌شود، یعنی Ollama **هیچ قالبی** روی آن اعمال نمی‌کند. مدل دقیقاً همان رشته‌ای را می‌بیند که در (الف) دید.
- **انتظار:** چون رشته و تنظیمات یکی است، پاسخ‌های (ب) باید با (الف) **تقریباً یا کاملاً یکسان** باشند. هر اختلافی یافته است، نه نویز.

## ۲. LM Studio

۱. در LM Studio فایل `Qwen3.5-4B-Q4_K_M.gguf` را بارگذاری کنید. Context Length را **16384** بگذارید.
۲. در تب Developer سرور را روشن کنید (پورت پیش‌فرض 1234).
۳. شناسهٔ مدل را از `http://localhost:1234/v1/models` بردارید، مثلاً `qwen3.5-4b`.

```powershell
python scripts\run_phase4.py --server lmstudio --model-id qwen3.5-4b --model C:\models\Qwen3.5-4B-Q4_K_M.gguf --arms plain --second-turn --refusal-language --execution-guard --min-trust 80 --style --out evals\results\p8lm_plain.json
```

برای LM Studio **فقط تکهٔ plain** کافی است (حدود ۲۰ دقیقه). هدف این است که نشان دهیم همان رشته از طریق LM Studio هم همان رفتار را دارد.

## ۳. زمان (ESTIMATED)

(الف) و (ب) هر کدام حدود ۵۰ تا ۶۰ دقیقه‌اند (Q4 در فاز ۷ حدود ۵۱ دقیقه مدل‌گردانی داشت). LM Studio حدود ۲۰ دقیقه است. جمعاً حدود ۲ تا ۲٫۵ ساعت. پیش از اجرا LM Studio را ببندید تا دو سرور هم‌زمان رم نگیرند.

## ۴. چه بفرستید

`phase8_style_merged.json`، `phase8_ollama_merged.json` و `p8lm_plain.json`. اگر توانستید، رم مصرفی فرآیند `ollama` را هم از Task Manager در طول اجرا یادداشت کنید. اسکریپت رم خودِ سرور را نمی‌بیند و این را صادقانه در فایل نوشته است.

## من با آن چه می‌کنم (آماده و آزموده)

```text
python3 scripts/compare_quants.py phase8_style_merged.json phase8_ollama_merged.json   # RUNTIME: فقط اجراکننده فرق دارد
```

اثر سبک (فاز ۷ در برابر الف) با ابزار جداگانه‌ای سنجیده می‌شود. آن ابزار LaTeX باقی‌مانده، جمله‌های انگلیسی در جواب فارسی و جواب‌های قطع‌شده را می‌شمارد و دقت هر سطر را مقایسه می‌کند. `compare_quants` این مقایسه را رد می‌کند، چون پرامپت‌ها فرق دارند. این رفتار عمدی است.
