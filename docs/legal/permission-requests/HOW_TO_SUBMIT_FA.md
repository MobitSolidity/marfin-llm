# راهنمای ارسال درخواست مجوز: ECB با فرم وب و IMF از طریق CCC

> **بایگانی (2026-10-26، D-0140):** هر دو مسیر بسته شدند. درخواست ECB به تصمیم مالک لغو شد، و IMF/CCC در شرایط تحریم در دسترس نیست. این راهنما فقط برای سابقه نگه داشته شده است. مقاله‌های ECB و IMF خاموش می‌مانند.

ثبت: 2026-10-23. پاسخ خودکار هر دو نهاد نشان داد که ایمیل مسیر درستی نیست:
- **ECB**: صندوق info@ecb.europa.eu خوانده نمی‌شود. درخواست باید با فرم رسمی ثبت شود.
- **IMF**: صدور مجوز استفادهٔ مجدد از طریق Copyright Clearance Center (CCC) انجام می‌شود.

برچسب‌ها: **VERIFIED** یعنی امروز از خود فرم یا صفحهٔ رسمی خوانده شده است. **ESTIMATED** یعنی برداشت من است و تأیید نشده.

---

## ۱) ECB: فرم Information Request

نشانی: https://form.ecb.europa.eu/services/rest/publicinformationrequest/?lang=en

برای این فرم **حساب کاربری یا ثبت‌نام لازم نیست**. فقط فرم را پر و ارسال می‌کنید (VERIFIED: فرم هیچ فیلد رمز عبور یا ورود ندارد).

| فیلد در فرم | اجباری؟ | چه بزنید |
|---|---|---|
| Prefix | خیر | `Mr` یا `Ms`، یا خالی |
| First name | بله (حداکثر ۵۰ نویسه) | نام کوچک شما به انگلیسی |
| Last name | بله (حداکثر ۵۰ نویسه) | نام خانوادگی به انگلیسی |
| Country | بله | کشور محل سکونت شما (مثلاً `Iran` در فهرست هست) |
| Email | بله | ایمیلی که واقعاً چک می‌کنید. پاسخ به همین ایمیل می‌آید |
| Organisation | خیر | خالی بگذارید یا بنویسید `Individual (personal project)` |
| **Category** | بله | **`Copyright and autographs`** |
| **Sub-Category** | خیر (بعد از انتخاب Category ظاهر می‌شود) | **`Copyright and Permissions`** |
| Subject | بله | `Permission request: non-commercial local research use of ECB Working Papers and Occasional Papers` |
| Details | بله (حداکثر **۴۰۰۰** نویسه) | متن کادر پایین (حدود ۱۹۰۰ نویسه) |
| Attachment | خیر | لازم نیست |
| Privacy statement | بله | تیک بزنید |
| Captcha | بله | نویسه‌های تصویر را وارد کنید |

بعد از ارسال، باید پیام «Thank you for your information request.» را ببینید. اگر ایمیل تأیید آمد، شماره پیگیری‌اش را نگه دارید.

**متن Details:** این نسخه بدون علامت‌های Markdown است. فرم آن‌ها را به‌صورت `**` نشان می‌دهد، پس از این نسخه کپی کنید و سه جای خالی را پر کنید:

```
Dear ECB copyright and permissions team,

I am requesting written permission to use ECB Working Papers and ECB Occasional Papers in a personal research tool.

Why I am asking: your disclaimer states that reproduction of documents bearing the name of their authors, such as ECB Working Papers and Occasional Papers, "is permitted only with the explicit prior written authorisation of the ECB or the authors."

The project: "marfin-llm" is a personal, non-commercial financial-research assistant. It runs entirely on my own computer (a single user, no server, no public access). It answers my questions by retrieving short passages from official sources and always cites the source and links to the original document.

The use I am requesting permission for:
1. Download ECB Working Papers and ECB Occasional Papers (publicly available on your website) at a polite rate, no more than one request per second.
2. Store them locally and split them into passages for search (retrieval-augmented generation).
3. Show short quoted passages to me, each with a full citation and a link to the original on your website.

What I will not do:
- I will not use the papers to train or fine-tune any language model.
- I will not redistribute, republish, sell or make the papers available to anyone else.
- I will not alter the content, imply endorsement by or affiliation with the ECB, or present any output as investment advice from the ECB.
- If my use ever becomes commercial or public, I will stop and ask again.

Attribution will appear with every passage shown, in whatever form you prefer. By default: "Source: European Central Bank, <title>, <year>, <URL>."

I would be grateful for your permission, or for guidance on the conditions under which this use is acceptable.

Kind regards,
<YOUR FULL NAME>
<YOUR EMAIL>
<COUNTRY>
```

---

## ۲) IMF: از طریق CCC (copyright.com)

### مراحل (ESTIMATED؛ از راهنمای ناشرانی که CCC را به کار می‌برند، مثل Sage)
1. به https://marketplace.copyright.com بروید و عنوان را جست‌وجو کنید. مثلاً `IMF Working Papers` یا عنوان دقیق مقالهٔ مورد نظر.
2. از نتایج، عنوانی را انتخاب کنید که ناشرش International Monetary Fund است، و **Request Permission** را بزنید.
3. **Type of Use** و نوع درخواست‌کننده را انتخاب کنید و Next را بزنید. هیچ گزینه‌ای دقیقاً با کار ما («جست‌وجوی محلی + نقل‌قول کوتاه، بدون training») جور نیست:
   - **AI Summarization** (VERIFIED: از اکتبر ۲۰۲۶ اضافه شده). این گزینه فقط برای «ناشران شرکت‌کننده» و در بخش‌های Pharma/Med Device، MedComms، General Business Use و Academic Course Content Material فعال است. فهرست ناشران منتشر نشده و معلوم نیست IMF جزو آن‌ها باشد.
   - اگر قیمت نشان داده نشد یا گزینهٔ مناسبی نبود، درخواست معمولاً برای بررسی به خود ناشر فرستاده می‌شود (special order). در توضیحات همان متن `IMF_EN.md` را بگذارید.
4. برای تکمیل درخواست باید در https://marketplace.copyright.com/rs-ui-web/mp/registration **حساب بسازید**: ایمیل، رمز عبور، نام و نشانی. نوع حساب را **Individual** بزنید، نه سازمانی.
5. قیمت (اگر داشت) و Terms and Conditions را **قبل از پرداخت** کامل بخوانید. CCC در بیشتر موارد **هزینه** می‌گیرد. اگر هزینه داشت، چیزی نخرید و اول به من خبر دهید.

### محدودیت مهم (UNVERIFIED، ولی احتمال آن زیاد است)
CCC شرکتی آمریکایی است. اگر در ایران هستید، احتمالاً به‌خاطر تحریم‌های OFAC **ساخت حساب یا پرداخت ممکن نیست**. Iran در فهرست کشورهای تحت تحریم جامع آمریکا است. **برای دور زدن این محدودیت از VPN، نشانی یا کارت کشور دیگر استفاده نکنید.** مجوزی که این‌طور گرفته شود از نظر حقوقی پایه ندارد.

### جایگزین‌ها
- **سازمان حق تکثیر محلی (local rights agency):** صفحهٔ IMF eLibrary می‌گوید درخواست‌کنندگان خارج از آمریکا می‌توانند از سازمان محلی کشور خودشان مجوز بگیرند (VERIFIED). من تأیید نکرده‌ام که ایران چنین سازمان طرف قراردادی داشته باشد (UNVERIFIED).
- **پاسخ به copyright@imf.org:** یک بار دیگر و کوتاه بنویسید که استفاده رایگان، شخصی و غیرتجاری است و CCC برای شما در دسترس نیست، و بپرسید آیا امکان مجوز مستقیم وجود دارد. متن پیشنهادی:

```
Thank you for pointing me to the Copyright Clearance Center. My use is personal, non-commercial and local
(no redistribution, no model training; short quoted passages with full citation and link). CCC is not
available to me from my country. Could the IMF grant this limited permission directly, or tell me whether
this use is already covered by the IMF's general terms? My original request is below.
```

### اگر هیچ‌کدام نشد
مقاله‌های IMF **خاموش می‌مانند** و پروژه بدون آن‌ها کامل کار می‌کند. داده‌های آماری IMF (data.imf.org) همین حالا با ذکر منبع فعال است و مجوز جداگانه نمی‌خواهد.

---

## ۳) BIS
بدون تغییر: فرم https://www.bis.org/legal/permissionrequestform.htm با متن `BIS_EN.md`.
