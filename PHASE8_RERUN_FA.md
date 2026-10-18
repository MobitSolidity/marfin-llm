# فاز ۸ — اجرای دوباره پس از اصلاحات D-0124 (روی i5-12400)

**تاریخ آماده‌سازی:** ۲۰۲۶-۱۰-۱۸ · **شاخه:** `genspark_ai_developer` (پس از `git pull`)

مدل در این sandbox اجرا نمی‌شود. هیچ عددی در این فایل از اجرای جدید نیامده است.

## چرا دوباره؟ آنچه اجرای ۲۰۲۶-۱۰-۱۸ نشان داد (MEASURED)

| یافته | علت | اصلاح |
|---|---|---|
| **سه ایراد شما رفع شد:** LaTeX نمایش‌داده‌شده از ۸ به ۰، جملهٔ انگلیسی در جواب فارسی از ۱ به ۰، جواب قطع‌شده از ۶ به ۰ | قوانین `--style` | — |
| **مدل دیگر ابزار ماشین‌حساب را صدا نزد:** در ردیف‌هایی که ابزار لازم بود، ۸ از ۱۰ (فاز ۷) به ۲ از ۱۰ (داخل پایتون) و ۰ از ۱۰ (Ollama) رسید | قانون «اول جواب را بده» را مدل روی فراخوانی ابزار هم اعمال کرد | جملهٔ جدید فقط برای بخش tools: «این قوانین فقط برای جواب نهایی است؛ برای محاسبه اول ابزار را صدا بزن» |
| مثال داخل قانون (`P/E = 150 / 8.40 = 17.86`) **دقیقاً جواب سؤال EN/FA-CALC-001** بود | خطای من | مثال به `240 / 12 = 20` عوض شد؛ این اعداد در هیچ فایل ارزیابی نیستند (با تست قفل شده) |
| ۳ سؤال انگلیسی به فارسی جواب داده شد (tools: EN-ABST-002، EN-SAFE-001، EN-SAFE-002) | قانون زبان صریح نبود | «سؤال انگلیسی ← جواب انگلیسی، سؤال فارسی ← جواب فارسی» |
| جواب‌های Ollama و LM Studio با داخل پایتون **حتی یک مورد** یکسان نبود (۰ از ۷۴)، با اینکه تعداد توکن پرامپت در همهٔ ردیف‌ها برابر بود | به احتمال زیاد `repeat_penalty`: پیش‌فرض llama-cpp-python برابر ۱٫۰ است و پیش‌فرض Ollama و LM Studio برابر ۱٫۱ (INFERRED) | حالا ۱٫۰ صریحاً فرستاده می‌شود و در Modelfile هم ثبت شده است |
| TTFT در Ollama: ۱۳۰ ثانیه، سپس ۱٫۰۴ و ۱٫۰۷ ثانیه | پرامپت ۴۴۳۳ توکن بود، نه ۲۰۴۸ (توکن‌شماری نداشت)، و دو اندازه‌گیری بعدی از کش سرور خوانده شدند | توکن‌شماری با خود سرور، و هر اندازه‌گیری یک پرامپت یکتا دارد |
| `ollama run` باز هم «Thinking Process» چاپ کرد | Ollama در `run` به‌طور پیش‌فرض thinking را روشن می‌کند و قالب خودش را دارد | برای استفادهٔ تعاملی: `--think=false` |
| رم Ollama در اجرای ارزیابی: **۶٫۲ گیگابایت** (گزارش شما) | بالاتر از سقف ۶٫۰ | دوباره اندازه بگیرید (پایین) |

## ۱. ساخت دوبارهٔ مدل Ollama (Modelfile عوض شده است)

```powershell
git pull
ollama rm marfin-q4
ollama create marfin-q4 -f deploy\ollama\Modelfile
ollama run marfin-q4 --think=false "نسبت P/E سهمی با قیمت ۱۵۰ و سود هر سهم ۸٫۴ چقدر است؟"
```

انتظار: بدون «Thinking Process». ممکن است فرمول در `ollama run` هنوز LaTeX داشته باشد، چون بازنویسی LaTeX در ارکستراتور انجام می‌شود نه در Ollama. اگر این‌طور بود، فقط یادداشت کنید.

## ۲. داخل پایتون (llama.cpp) با `--style` اصلاح‌شده

```powershell
python scripts\run_phase4.py --model C:\models\Qwen3.5-4B-Q4_K_M.gguf --arms rag --corpus evals\rag_corpus_combined.jsonl --gold evals\rag_gold_combined.jsonl --second-turn --refusal-language --execution-guard --min-trust 80 --style --out evals\results\p8b_st_rag.json
python scripts\run_phase4.py --model C:\models\Qwen3.5-4B-Q4_K_M.gguf --arms tools --second-turn --refusal-language --execution-guard --min-trust 80 --style --out evals\results\p8b_st_tools.json
python scripts\run_phase4.py --model C:\models\Qwen3.5-4B-Q4_K_M.gguf --arms plain --second-turn --refusal-language --execution-guard --min-trust 80 --style --out evals\results\p8b_st_plain.json
python scripts\merge_phase4.py evals\results\p8b_st_rag.json evals\results\p8b_st_tools.json evals\results\p8b_st_plain.json --out evals\results\phase8b_style_merged.json
```

## ۳. همان از طریق Ollama

پیش از شروع، LM Studio را ببندید.

```powershell
python scripts\run_phase4.py --server ollama --model-id marfin-q4 --model C:\models\Qwen3.5-4B-Q4_K_M.gguf --arms rag --corpus evals\rag_corpus_combined.jsonl --gold evals\rag_gold_combined.jsonl --second-turn --refusal-language --execution-guard --min-trust 80 --style --out evals\results\p8b_ol_rag.json
python scripts\run_phase4.py --server ollama --model-id marfin-q4 --model C:\models\Qwen3.5-4B-Q4_K_M.gguf --arms tools --second-turn --refusal-language --execution-guard --min-trust 80 --style --out evals\results\p8b_ol_tools.json
python scripts\run_phase4.py --server ollama --model-id marfin-q4 --model C:\models\Qwen3.5-4B-Q4_K_M.gguf --arms plain --second-turn --refusal-language --execution-guard --min-trust 80 --style --out evals\results\p8b_ol_plain.json
python scripts\merge_phase4.py evals\results\p8b_ol_rag.json evals\results\p8b_ol_tools.json evals\results\p8b_ol_plain.json --out evals\results\phase8b_ollama_merged.json
```

**رم:** در Task Manager، در تب **Details**، ستون **Memory (private working set)** فرایند `ollama` (یا `ollama_llama_server` / `llama-server`، هر فرایندی که بزرگ است) را در طول اجرا یادداشت کنید. اگر چند فرایند Ollama دیدید، هر کدام را جدا بنویسید.

## ۴. LM Studio (فقط plain)

پیش از شروع، Ollama را ببندید (`ollama stop marfin-q4`). شناسهٔ مدل همان قبلی است.

```powershell
python scripts\run_phase4.py --server lmstudio --model-id dolphin/dolphin/qwen3.5-4b-q4_k_m.gguf --model C:\models\Qwen3.5-4B-Q4_K_M.gguf --arms plain --second-turn --refusal-language --execution-guard --min-trust 80 --style --out evals\results\p8b_lm_plain.json
```

## ۵. زمان (ESTIMATED)

بر اساس اجرای قبل: داخل پایتون حدود ۴۵ دقیقه، Ollama حدود ۵۰ دقیقه، LM Studio حدود ۱۰ دقیقه. با بارگذاری‌ها جمعاً حدود ۲ ساعت.

## ۶. چه بفرستید

- `phase8b_style_merged.json`
- `phase8b_ollama_merged.json`
- `p8b_lm_plain.json`
- خروجی `ollama run ... --think=false`
- رم و CPU هر سه اجرا (همان‌طور که این بار نوشتید؛ لطفاً بنویسید عدد را از کدام ستون خواندید)

## من با آن چه می‌کنم (آماده و آزموده)

- **اثر سبک** (فاز ۷ در برابر ۲): `compare_style.py`. معیار موفقیت: بازگشت فراخوانی ابزار به حدود ۸ از ۱۰، بدون برگشتن LaTeX و جواب‌های قطع‌شده.
- **اثر اجراکننده** (۲ در برابر ۳): `compare_quants.py`. حالا بلوک server در فایل ادغام‌شده می‌ماند. اگر با `repeat_penalty 1.0` جواب‌ها یکسان شوند، علت ثابت می‌شود. اگر نشوند، علت چیز دیگری است و همین را صادقانه می‌نویسم.
