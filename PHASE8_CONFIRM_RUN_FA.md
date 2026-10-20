# اجرای تأییدی پیکربندی نهایی (D-0126) — اختیاری، روی i5-12400

**تاریخ آماده‌سازی:** ۲۰۲۶-۱۰-۲۰ · **شاخه:** `genspark_ai_developer` (پس از `git pull`)

مدل در این sandbox اجرا نمی‌شود. هیچ عددی در این فایل از اجرای جدید نیامده است.

## چرا؟

تصمیم‌های فاز ۸ را خودم گرفتم (طبق درخواست شما):

- **۱.** قوانین سبک دیگر داخل پرامپت نیستند. به‌جای آن، LaTeX بعد از جواب مدل به متن ساده تبدیل می‌شود (`--display`). دو اجرای قبلی نشان دادند قوانین داخل پرامپت دقت را پایین می‌آورند.
- **۲.** اجراکنندهٔ پیشنهادی: llama.cpp داخل پایتون.
- **۳.** جواب‌های قطع‌شده: فقط وقتی جواب به سقف ۵۱۲ توکن برسد، یک بار ۲۵۶ توکن دیگر ادامه داده می‌شود (`--continue-budget 256`).
- **۴.** فاز ۸ بسته شد و فاز 8A ساخته و آزموده شد.

اثر بند ۳ هنوز **اندازه‌گیری نشده** است. این اجرا آن را می‌سنجد.

## دستورها (حدود ۵۰ دقیقه، ESTIMATED)

```powershell
git pull
python scripts\run_phase4.py --model C:\models\Qwen3.5-4B-Q4_K_M.gguf --arms rag --corpus evals\rag_corpus_combined.jsonl --gold evals\rag_gold_combined.jsonl --second-turn --refusal-language --execution-guard --min-trust 80 --display --continue-budget 256 --out evals\results\p8c_rag.json
python scripts\run_phase4.py --model C:\models\Qwen3.5-4B-Q4_K_M.gguf --arms tools --second-turn --refusal-language --execution-guard --min-trust 80 --display --continue-budget 256 --out evals\results\p8c_tools.json
python scripts\run_phase4.py --model C:\models\Qwen3.5-4B-Q4_K_M.gguf --arms plain --second-turn --refusal-language --execution-guard --min-trust 80 --display --continue-budget 256 --out evals\results\p8c_plain.json
python scripts\merge_phase4.py evals\results\p8c_rag.json evals\results\p8c_tools.json evals\results\p8c_plain.json --out evals\results\phase8c_final_merged.json
```

## انتظار

- پاسخ‌هایی که قطع نشده‌اند باید **دقیقاً همان** پاسخ‌های فاز ۷ باشند، چون پرامپت تغییری نکرده است.
- فقط حدود ۶ پاسخِ قطع‌شده ادامه پیدا می‌کنند.

## چه بفرستید

فایل `phase8c_final_merged.json`.
