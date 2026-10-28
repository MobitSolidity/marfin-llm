# -*- coding: utf-8 -*-
"""
Persian catalogue of the 85 deterministic calculators (D-0141).

For every tool in tools.registry: a category, a Persian title, ONE line saying what it is
for (shown under the title in the UI), and a worked example whose arguments really run.
Plus a Persian label and a short hint for every parameter.

This is DISPLAY data only. The registry stays the single source of truth for names,
schemas and the calculation; tests assert that this catalogue covers every registered
tool and parameter exactly, and that every example returns ok=True through call_tool.
"""
from __future__ import annotations

CATEGORIES = (
    ("returns", "بازده و ریسک پرتفوی"),
    ("trade", "مدیریت معامله و ریسک"),
    ("valuation", "ارزش‌گذاری سهام"),
    ("ratios", "نسبت‌های مالی شرکت"),
    ("technical", "تحلیل تکنیکال"),
    ("bonds", "اوراق با درآمد ثابت"),
    ("options", "اختیار معامله و مشتقات"),
)

_P10 = [100, 102, 101, 105, 107, 106, 110, 108, 111, 115]
_H10 = [101, 103, 102, 106, 108, 107, 111, 109, 112, 116]
_L10 = [99, 100, 99, 103, 105, 104, 107, 106, 109, 112]
_R8 = [0.01, -0.02, 0.015, 0.005, -0.01, 0.02, 0.003, -0.004]
_M8 = [0.008, -0.015, 0.01, 0.004, -0.008, 0.015, 0.002, -0.003]
_OPT = {"spot": 100, "strike": 105, "time_to_expiry": 0.5, "volatility": 0.25, "risk_free_rate": 0.04}
_BOND = {"face_value": 1000, "coupon_rate": 0.05, "ytm": 0.06, "years_to_maturity": 5}

#: name -> (category, Persian title, one-line usage, example arguments)
TOOLS = {}
#: parameter -> (Persian label, short hint)
PARAMS = {}
#: enum value -> Persian label (display only; the submitted value stays the English one)
ENUM_FA = {"daily": "روزانه", "weekly": "هفتگی", "monthly": "ماهانه", "quarterly": "فصلی", "annual": "سالانه",
           "call": "خرید (call)", "put": "فروش (put)", "long": "خرید (long)", "short": "فروش (short)",
           "net_income": "سود خالص", "ebitda": "EBITDA", "revenue": "فروش",
           "to_per_from": "واحد ارز مقصد به ازای ۱ ارز مبدأ", "from_per_to": "واحد ارز مبدأ به ازای ۱ ارز مقصد",
           "30/360": "30/360", "actual/360": "actual/360", "actual/365": "actual/365"}


def _t(name, cat, title, usage, example):
    if name in TOOLS:
        raise ValueError("duplicate catalogue entry %r" % name)
    TOOLS[name] = (cat, title, usage, example)


# == returns and portfolio risk ============================================================
_t("simple_return", "returns", "بازده ساده",
   "درصد سود یا زیان بین قیمت خرید و فروش؛ ساده‌ترین معیار عملکرد.", {"start": 100, "end": 112})
_t("log_return", "returns", "بازده لگاریتمی",
   "بازده پیوسته که برای جمع زدن دوره‌ها و مدل‌های آماری مناسب‌تر است.", {"start": 100, "end": 112})
_t("cagr", "returns", "نرخ رشد مرکب سالانه (CAGR)",
   "رشد چندساله را به یک نرخ سالانهٔ هموار تبدیل می‌کند؛ نه میانگین ساده.",
   {"start": 100000, "end": 161051, "years": 5})
_t("annualized_return", "returns", "بازده سالانه‌شده",
   "میانگین هندسی بازده‌های دوره‌ای (روزانه، ماهانه و ...) را سالانه می‌کند.",
   {"returns": [0.01, 0.02, -0.005, 0.015], "freq": "monthly"})
_t("annualized_volatility", "returns", "نوسان سالانه",
   "انحراف معیار بازده‌ها را سالانه می‌کند؛ معیار اصلی میزان نوسان یک دارایی.", {"returns": _R8, "freq": "daily"})
_t("sharpe_ratio", "returns", "نسبت شارپ",
   "بازده مازاد بر نرخ بدون ریسک به ازای هر واحد نوسان؛ بالاتر یعنی بازده بهتر نسبت به ریسک.",
   {"returns": _R8, "risk_free_rate": 0.04, "freq": "daily"})
_t("sortino_ratio", "returns", "نسبت سورتینو",
   "مثل شارپ، اما فقط نوسان رو به پایین (زیان) را ریسک حساب می‌کند.",
   {"returns": _R8, "risk_free_rate": 0.0, "freq": "daily"})
_t("max_drawdown", "returns", "بیشترین افت سرمایه",
   "بزرگ‌ترین افت از قله تا دره در منحنی ارزش حساب؛ بدترین تجربهٔ زیان.",
   {"equity": [100, 110, 105, 120, 90, 95, 130]})
_t("calmar_ratio", "returns", "نسبت کالمار",
   "بازده سالانه تقسیم بر بیشترین افت؛ بازده در برابر بدترین زیان.",
   {"returns": _R8, "equity": [100, 101, 99, 100.5, 101, 100, 102, 102.3, 101.9], "freq": "daily"})
_t("beta", "returns", "بتا",
   "حساسیت بازده دارایی به بازار؛ بتای ۱٫۲ یعنی حدود ۲۰٪ پرنوسان‌تر از بازار.", {"asset": _R8, "market": _M8})
_t("alpha", "returns", "آلفای جنسن",
   "بازده اضافه بر آنچه بتا و بازار توضیح می‌دهند؛ معیار مهارت مدیر سرمایه.",
   {"asset": _R8, "market": _M8, "risk_free_rate": 0.0, "freq": "daily"})
_t("correlation", "returns", "همبستگی",
   "میزان هم‌جهتی دو سری بازده بین ۱- و ۱؛ پایهٔ تنوع‌بخشی پرتفوی.", {"a": _R8, "b": _M8})
_t("covariance", "returns", "کوواریانس",
   "هم‌تغییری دو سری بازده؛ ورودی محاسبهٔ ریسک پرتفوی.", {"a": _R8, "b": _M8})
_t("tracking_error", "returns", "خطای ردیابی",
   "نوسان تفاوت بازده با شاخص مبنا؛ چقدر صندوق از شاخص فاصله می‌گیرد.",
   {"asset": _R8, "benchmark": _M8, "freq": "daily"})
_t("information_ratio", "returns", "نسبت اطلاعات",
   "بازده اضافه بر شاخص تقسیم بر خطای ردیابی؛ کیفیت مدیریت فعال.",
   {"asset": _R8, "benchmark": _M8, "freq": "daily"})
_t("value_at_risk", "returns", "ارزش در معرض ریسک (VaR)",
   "زیانی که با اطمینان مشخص (مثلاً ۹۵٪) از آن بیشتر نمی‌شود، از روی تاریخچه.",
   {"returns": _R8, "confidence": 0.95})
_t("conditional_value_at_risk", "returns", "ریزش مورد انتظار (CVaR)",
   "میانگین زیان در بدترین روزهایی که از VaR فراتر می‌روند.", {"returns": _R8, "confidence": 0.9})
_t("concentration", "returns", "تمرکز پرتفوی (هرفیندال)",
   "عددی بین ۰ و ۱ که نشان می‌دهد پرتفوی چقدر روی چند دارایی متمرکز است.", {"weights": [0.5, 0.3, 0.2]})

# == trade management ======================================================================
_t("position_size", "trade", "اندازهٔ پوزیشن",
   "چند سهم بخرید تا اگر حد ضرر فعال شد دقیقاً درصد مشخصی از حساب را از دست بدهید.",
   {"account_equity": 50000, "risk_pct": 0.02, "entry": 80, "stop": 76})
_t("risk_reward", "trade", "نسبت سود به ریسک",
   "سود هدف را با زیان تا حد ضرر مقایسه می‌کند؛ ۲ یعنی سود دو برابر ریسک.",
   {"entry": 100, "stop": 95, "target": 110})
_t("portfolio_leverage", "trade", "اهرم پرتفوی",
   "کل حجم پوزیشن‌ها تقسیم بر سرمایهٔ خالص؛ بیشتر از ۱ یعنی معامله با پول قرضی.",
   {"gross_exposure": 150000, "net_equity": 100000})
_t("margin_estimate", "trade", "برآورد وجه تضمین",
   "برآورد عمومی مارجین اولیه و نگهداری برای پوزیشن اهرمی؛ عدد کارگزار ملاک است.",
   {"position_value": 10000, "leverage": 3, "maintenance_margin_rate": 0.1})
_t("liquidation_estimate", "trade", "برآورد قیمت لیکوئید",
   "قیمتی که در معاملهٔ اهرمی تقریباً پوزیشن بسته می‌شود؛ کارمزدها آن را نزدیک‌تر می‌کنند.",
   {"entry_price": 100, "leverage": 3, "maintenance_margin_rate": 0.1, "side": "long"})
_t("fx_convert", "trade", "تبدیل ارز",
   "مبلغی را با نرخی که خودتان وارد می‌کنید از یک ارز به ارز دیگر تبدیل می‌کند.",
   {"amount": 1000, "rate": 1.08, "from_currency": "EUR", "to_currency": "USD", "rate_quote": "to_per_from"})

# == valuation =============================================================================
_t("pe_ratio", "valuation", "نسبت قیمت به سود (P/E)",
   "قیمت هر سهم چند برابر سود سالانهٔ آن است؛ رایج‌ترین معیار گرانی یا ارزانی.", {"price": 150, "eps": 8.4})
_t("forward_pe", "valuation", "P/E آینده‌نگر",
   "مثل P/E، اما با سود پیش‌بینی‌شده؛ پیش‌بینی همیشه تخمین است.", {"price": 150, "forward_eps": 10})
_t("peg_ratio", "valuation", "نسبت PEG",
   "P/E را با رشد سود مقایسه می‌کند؛ حدود ۱ یعنی قیمت با رشد هماهنگ است.", {"pe": 20, "growth_rate_pct": 15})
_t("ps_ratio", "valuation", "قیمت به فروش (P/S)",
   "ارزش بازار تقسیم بر فروش؛ برای شرکت‌های بی‌سود یا تازه‌کار.",
   {"market_cap": 5000000000, "revenue": 2000000000})
_t("pb_ratio", "valuation", "قیمت به ارزش دفتری (P/B)",
   "ارزش بازار در برابر حقوق صاحبان سهام دفتری؛ مهم برای بانک‌ها و شرکت‌های دارایی‌محور.",
   {"market_cap": 5000000000, "book_value_equity": 2500000000})
_t("enterprise_value", "valuation", "ارزش شرکت (EV)",
   "ارزش بازار به‌علاوهٔ بدهی منهای نقد؛ قیمت خرید کل شرکت.",
   {"market_cap": 5000000000, "total_debt": 1000000000, "cash_and_equivalents": 300000000})
_t("ev_ebitda", "valuation", "EV به EBITDA",
   "ارزش شرکت چند برابر سود عملیاتی پیش از استهلاک است؛ مقایسه بدون اثر ساختار بدهی.",
   {"enterprise_value_": 5700000000, "ebitda": 600000000})
_t("ev_sales", "valuation", "EV به فروش",
   "ارزش کل شرکت نسبت به فروش سالانه.", {"enterprise_value_": 5700000000, "revenue": 2000000000})
_t("dcf", "valuation", "جریان نقد تنزیل‌شده (DCF)",
   "ارزش ذاتی از جمع ارزش فعلی جریان‌های نقد آینده و ارزش پایانی.",
   {"cash_flows": [100, 110, 120, 130, 140], "discount_rate": 0.1, "terminal_growth": 0.02})
_t("dividend_discount_model", "valuation", "مدل تنزیل سود نقدی (گوردون)",
   "ارزش سهم از روی سود نقدی و رشد ثابت آن: P = D1 / (r − g).",
   {"dividend": 2, "discount_rate": 0.08, "growth_rate": 0.03})
_t("free_cash_flow", "valuation", "جریان نقد آزاد",
   "نقد عملیاتی منهای مخارج سرمایه‌ای؛ پولی که واقعاً برای سهامداران می‌ماند.",
   {"cash_flow_operations": 800, "capital_expenditure": 300})
_t("fcf_conversion", "valuation", "نرخ تبدیل به جریان نقد آزاد",
   "چه بخشی از سود (یا EBITDA یا فروش) به نقد آزاد تبدیل می‌شود.",
   {"free_cash_flow_": 500, "denominator": 600, "denominator_kind": "net_income"})

# == company ratios ========================================================================
_t("roe", "ratios", "بازده حقوق صاحبان سهام (ROE)",
   "سود خالص به ازای هر واحد سرمایهٔ سهامداران.", {"net_income": 120, "shareholders_equity": 800})
_t("roa", "ratios", "بازده دارایی‌ها (ROA)",
   "سود خالص نسبت به کل دارایی‌ها؛ کارایی استفاده از دارایی.", {"net_income": 120, "total_assets": 2000})
_t("roic", "ratios", "بازده سرمایهٔ به‌کاررفته (ROIC)",
   "سود عملیاتی پس از مالیات نسبت به سرمایهٔ به‌کاررفته؛ معیار خلق ارزش.",
   {"ebit": 200, "tax_rate": 0.21, "invested_capital": 1200})
_t("gross_margin", "ratios", "حاشیهٔ سود ناخالص",
   "چند درصد فروش پس از بهای تمام‌شده باقی می‌ماند؛ نشانهٔ قدرت قیمت‌گذاری.",
   {"revenue": 1000, "cost_of_goods_sold": 600})
_t("operating_margin", "ratios", "حاشیهٔ سود عملیاتی",
   "سود عملیاتی به فروش؛ کارایی هستهٔ کسب‌وکار.", {"operating_income": 150, "revenue": 1000})
_t("net_margin", "ratios", "حاشیهٔ سود خالص",
   "سود نهایی به فروش، پس از همهٔ هزینه‌ها و مالیات.", {"net_income": 100, "revenue": 1000})
_t("debt_to_equity", "ratios", "بدهی به حقوق صاحبان سهام",
   "میزان اتکای شرکت به بدهی نسبت به سرمایهٔ سهامداران.", {"total_debt": 500, "shareholders_equity": 800})
_t("debt_to_assets", "ratios", "بدهی به دارایی",
   "چه سهمی از دارایی‌ها با بدهی تأمین شده است.", {"total_debt": 500, "total_assets": 2000})
_t("net_debt_to_ebitda", "ratios", "بدهی خالص به EBITDA",
   "چند سال سود عملیاتی لازم است تا بدهی خالص صاف شود؛ منفی یعنی نقد خالص.",
   {"total_debt": 500, "cash_and_equivalents": 100, "ebitda": 200})
_t("interest_coverage", "ratios", "پوشش بهره",
   "سود عملیاتی چند برابر هزینهٔ بهره است؛ زیر ۲ زنگ خطر است.", {"ebit": 200, "interest_expense": 25})
_t("current_ratio", "ratios", "نسبت جاری",
   "دارایی‌های جاری در برابر بدهی‌های جاری؛ توان پرداخت تعهدات کوتاه‌مدت.",
   {"current_assets": 600, "current_liabilities": 400})
_t("quick_ratio", "ratios", "نسبت آنی",
   "مثل نسبت جاری، اما بدون موجودی کالا؛ سخت‌گیرانه‌تر.",
   {"current_assets": 600, "inventory": 200, "current_liabilities": 400})
_t("working_capital", "ratios", "سرمایهٔ در گردش",
   "دارایی جاری منهای بدهی جاری؛ پول در دسترس برای عملیات روزمره.",
   {"current_assets": 600, "current_liabilities": 400})
_t("cash_conversion_cycle", "ratios", "چرخهٔ تبدیل نقد",
   "چند روز پول در موجودی و مطالبات گیر می‌کند؛ منفی یعنی تأمین مالی از تأمین‌کننده.",
   {"days_sales_outstanding": 45, "days_inventory_outstanding": 60, "days_payables_outstanding": 30})

# == technical analysis ====================================================================
_t("sma", "technical", "میانگین متحرک ساده (SMA)",
   "میانگین قیمت N دورهٔ اخیر؛ روند کلی را از نویز جدا می‌کند.", {"prices": _P10, "period": 5})
_t("ema", "technical", "میانگین متحرک نمایی (EMA)",
   "میانگینی که به قیمت‌های اخیر وزن بیشتری می‌دهد و سریع‌تر واکنش نشان می‌دهد.", {"prices": _P10, "period": 5})
_t("wma", "technical", "میانگین متحرک وزنی (WMA)",
   "میانگین با وزن خطی؛ تازه‌ترین قیمت بیشترین وزن را دارد.", {"prices": _P10, "period": 5})
_t("rsi", "technical", "شاخص قدرت نسبی (RSI)",
   "قدرت خرید و فروش بین ۰ و ۱۰۰؛ بالای ۷۰ اشباع خرید و زیر ۳۰ اشباع فروش.", {"prices": _P10, "period": 5})
_t("macd", "technical", "مکدی (MACD)",
   "اختلاف دو میانگین نمایی و خط سیگنال؛ برای تشخیص تغییر روند و قدرت حرکت.",
   {"prices": _P10 + [116, 114, 118, 120, 119, 122], "fast": 3, "slow": 6, "signal": 3})
_t("rate_of_change", "technical", "نرخ تغییر (ROC)",
   "درصد تغییر قیمت نسبت به N دورهٔ قبل؛ شتاب حرکت قیمت.", {"prices": _P10, "period": 5})
_t("stochastic_oscillator", "technical", "نوسانگر استوکاستیک",
   "جایگاه قیمت پایانی در دامنهٔ اخیر بین ۰ و ۱۰۰؛ برای نقاط برگشت.",
   {"highs": _H10, "lows": _L10, "closes": _P10, "k_period": 5, "d_period": 3})
_t("atr", "technical", "میانگین دامنهٔ واقعی (ATR)",
   "نوسان روزانه به واحد قیمت؛ برای تعیین فاصلهٔ حد ضرر.",
   {"highs": _H10, "lows": _L10, "closes": _P10, "period": 5})
_t("bollinger_bands", "technical", "باندهای بولینگر",
   "میانگین متحرک با دو باند انحراف معیار؛ فشردگی باندها خبر از حرکت بزرگ می‌دهد.",
   {"prices": _P10, "period": 5, "num_std": 2})
_t("adx", "technical", "شاخص جهت‌دار میانگین (ADX)",
   "فقط قدرت روند را می‌سنجد، نه جهتش را؛ بالای ۲۵ یعنی روند قوی.",
   {"highs": _H10, "lows": _L10, "closes": _P10, "period": 3})
_t("donchian_channels", "technical", "کانال دانچیان",
   "بالاترین سقف و پایین‌ترین کف N دوره؛ پایهٔ استراتژی‌های شکست.", {"highs": _H10, "lows": _L10, "period": 5})
_t("vwap", "technical", "میانگین قیمت وزنی با حجم (VWAP)",
   "میانگین قیمت با وزن حجم معاملات؛ معیار قیمت منصفانهٔ روز.",
   {"highs": [101, 103, 102], "lows": [99, 100, 99], "closes": [100, 102, 101], "volumes": [1000, 1500, 1200]})
_t("obv", "technical", "حجم تعادلی (OBV)",
   "جمع تجمعی حجم در روزهای مثبت و منفی؛ شیب آن تأیید یا رد روند است.",
   {"closes": [100, 102, 101, 104], "volumes": [1000, 1500, 1200, 1800]})

# == bonds =================================================================================
_t("bond_price", "bonds", "قیمت اوراق",
   "قیمت منصفانهٔ اوراق کوپن‌دار با بازده مشخص تا سررسید.", dict(_BOND))
_t("yield_to_maturity", "bonds", "بازده تا سررسید (YTM)",
   "نرخ بازده سالانه اگر اوراق را با این قیمت بخرید و تا سررسید نگه دارید.",
   {"price": 957.35, "face_value": 1000, "coupon_rate": 0.05, "years_to_maturity": 5})
_t("yield_to_call", "bonds", "بازده تا بازخرید (YTC)",
   "بازده اگر ناشر اوراق را زودتر بازخرید کند؛ برای اوراق قابل بازخرید.",
   {"price": 1050, "face_value": 1000, "coupon_rate": 0.06, "years_to_call": 3, "call_price": 1020})
_t("cash_flow_schedule", "bonds", "جدول جریان نقدی اوراق",
   "مبلغ همهٔ کوپن‌ها و اصل پول در سررسید.", {"face_value": 1000, "coupon_rate": 0.05, "years_to_maturity": 2})
_t("accrued_interest", "bonds", "سود تعلق‌گرفته",
   "سهم کوپن از آخرین پرداخت تا امروز که خریدار به فروشنده می‌دهد.",
   {"face_value": 1000, "coupon_rate": 0.05, "days_since_last_coupon": 60, "days_in_period": 180})
_t("dirty_price", "bonds", "قیمت کثیف (پرداختی)",
   "قیمت اعلام‌شده به‌علاوهٔ سود تعلق‌گرفته؛ مبلغی که واقعاً پرداخت می‌شود.", {"clean_price": 980, "accrued": 8.33})
_t("clean_price", "bonds", "قیمت تمیز (اعلامی)",
   "قیمت پرداختی منهای سود تعلق‌گرفته؛ قیمتی که در بازار اعلام می‌شود.", {"dirty_price_": 988.33, "accrued": 8.33})
_t("macaulay_duration", "bonds", "دیرش مکالی",
   "میانگین وزنی زمان دریافت جریان‌های نقدی، به سال.", dict(_BOND))
_t("modified_duration", "bonds", "دیرش تعدیل‌شده",
   "درصد تغییر قیمت اوراق به ازای ۱٪ تغییر بازده؛ معیار اصلی ریسک نرخ بهره.", dict(_BOND))
_t("convexity", "bonds", "تحدب",
   "اصلاح مرتبهٔ دوم دیرش؛ برای تغییرات بزرگ نرخ بهره دقیق‌تر است.", dict(_BOND))
_t("dv01", "bonds", "ارزش یک واحد پایه (DV01)",
   "تغییر قیمت به پول به ازای افزایش ۰٫۰۱٪ در بازده.", dict(_BOND))

# == options and derivatives ===============================================================
_t("black_scholes", "options", "قیمت اختیار (بلک-شولز)",
   "قیمت نظری اختیار اروپایی از روی قیمت، سررسید، نوسان و نرخ بهره.", dict(_OPT, option_type="call"))
_t("black_76", "options", "قیمت اختیار آتی (بلک ۷۶)",
   "قیمت اختیار روی قرارداد آتی؛ ورودی اول قیمت آتی است نه قیمت نقد.",
   {"forward": 100, "strike": 105, "time_to_expiry": 0.5, "volatility": 0.25, "risk_free_rate": 0.04,
    "option_type": "call"})
_t("binomial_price", "options", "قیمت اختیار (درخت دوجمله‌ای)",
   "قیمت اختیار با درخت قیمت؛ اختیار آمریکایی (اعمال زودهنگام) را هم پوشش می‌دهد.",
   dict(_OPT, option_type="put", steps=100, american=True))
_t("implied_volatility", "options", "نوسان ضمنی",
   "نوسانی که بازار در قیمت فعلی اختیار لحاظ کرده است.",
   {"market_price": 5.0, "spot": 100, "strike": 105, "time_to_expiry": 0.5, "risk_free_rate": 0.04,
    "option_type": "call"})
_t("delta", "options", "دلتا",
   "تغییر قیمت اختیار به ازای ۱ واحد تغییر قیمت دارایی پایه.", dict(_OPT, option_type="call"))
_t("gamma", "options", "گاما",
   "سرعت تغییر دلتا؛ نزدیک سررسید و در قیمت اعمال بیشترین است.", dict(_OPT))
_t("vega", "options", "وگا",
   "حساسیت قیمت اختیار به نوسان؛ برای یک واحد درصد بر ۱۰۰ تقسیم کنید.", dict(_OPT))
_t("theta", "options", "تتا",
   "کاهش ارزش زمانی اختیار با گذشت زمان (سالانه؛ مقدار روزانه در ورودی‌ها).", dict(_OPT, option_type="call"))
_t("rho", "options", "رو",
   "حساسیت قیمت اختیار به نرخ بهره.", dict(_OPT, option_type="call"))
_t("contract_payoff", "options", "سود و زیان در سررسید",
   "دریافتی و سود خالص یک موقعیت اختیار در سررسید، با احتساب پرمیوم.",
   {"spot_at_expiry": 115, "strike": 105, "premium": 4, "option_type": "call", "position": "long",
    "contracts": 1, "multiplier": 100})
_t("breakeven", "options", "نقطهٔ سربه‌سر اختیار",
   "قیمتی که در سررسید پرمیوم پرداختی برمی‌گردد.", {"strike": 105, "premium": 4, "option_type": "call"})


def _p(name, label, hint=""):
    PARAMS[name] = (label, hint)


_FR = "کسر؛ ۰٫۰۵ یعنی ۵٪"
_LIST = "اعداد با کاما، قدیمی به جدید"
for _n, _l, _h in (
        ("a", "سری اول", "بازده‌ها با کاما"), ("b", "سری دوم", "بازده‌ها با کاما"),
        ("account_equity", "موجودی حساب", ""), ("accrued", "سود تعلق‌گرفته", ""),
        ("american", "اختیار آمریکایی؟", "true یعنی اعمال زودهنگام مجاز"), ("amount", "مبلغ", ""),
        ("asset", "بازده دارایی", "بازده‌ها با کاما"), ("benchmark", "بازده شاخص مبنا", "بازده‌ها با کاما"),
        ("book_value_equity", "ارزش دفتری حقوق صاحبان سهام", ""), ("call_price", "قیمت بازخرید", ""),
        ("capital_expenditure", "مخارج سرمایه‌ای", "عدد مثبت"), ("cash_and_equivalents", "وجه نقد و معادل", ""),
        ("cash_flow_operations", "جریان نقد عملیاتی", ""), ("cash_flows", "جریان‌های نقد سالانه", "با کاما، از سال اول"),
        ("clean_price", "قیمت تمیز", ""), ("closes", "قیمت‌های پایانی", _LIST),
        ("confidence", "سطح اطمینان", "کسر؛ ۰٫۹۵ یعنی ۹۵٪"), ("contracts", "تعداد قرارداد", ""),
        ("cost_of_goods_sold", "بهای تمام‌شدهٔ کالا", ""), ("coupon_rate", "نرخ کوپن", _FR),
        ("current_assets", "دارایی‌های جاری", ""), ("current_liabilities", "بدهی‌های جاری", ""),
        ("d_period", "دورهٔ ‎%D", "معمولاً ۳"), ("day_count", "مبنای شمارش روز", ""),
        ("days_in_period", "روزهای دورهٔ کوپن", ""), ("days_inventory_outstanding", "دورهٔ گردش موجودی", "روز"),
        ("days_payables_outstanding", "دورهٔ پرداخت بدهی", "روز"), ("days_sales_outstanding", "دورهٔ وصول مطالبات", "روز"),
        ("days_since_last_coupon", "روز از آخرین کوپن", ""), ("denominator", "مخرج", "سود خالص، EBITDA یا فروش"),
        ("denominator_kind", "نوع مخرج", ""), ("dirty_price_", "قیمت کثیف", ""),
        ("discount_rate", "نرخ تنزیل", "کسر؛ ۰٫۱ یعنی ۱۰٪"), ("dividend", "سود نقدی هر سهم", ""),
        ("dividend_is_next_period", "سود دورهٔ بعد است؟", "true اگر D1 وارد می‌کنید"),
        ("dividend_yield", "بازده سود نقدی", _FR), ("ebit", "سود عملیاتی (EBIT)", ""), ("ebitda", "EBITDA", ""),
        ("end", "مقدار پایانی", ""), ("enterprise_value_", "ارزش شرکت (EV)", ""), ("entry", "قیمت ورود", ""),
        ("entry_price", "قیمت ورود", ""), ("eps", "سود هر سهم (EPS)", ""),
        ("equity", "منحنی ارزش حساب", "ارزش‌ها با کاما"), ("face_value", "ارزش اسمی", ""),
        ("fast", "دورهٔ سریع", "معمولاً ۱۲"), ("forward", "قیمت آتی", ""), ("forward_eps", "EPS پیش‌بینی‌شده", ""),
        ("free_cash_flow_", "جریان نقد آزاد", ""), ("freq", "دورهٔ داده‌ها", ""),
        ("frequency", "دفعات پرداخت در سال", "۲ یعنی شش‌ماهه"), ("from_currency", "از ارز", "مثلاً EUR"),
        ("gross_exposure", "کل حجم پوزیشن‌ها", ""), ("growth_rate", "نرخ رشد", _FR),
        ("growth_rate_pct", "رشد سود (درصد)", "۱۵ یعنی ۱۵٪"), ("highs", "سقف‌ها", _LIST),
        ("interest_expense", "هزینهٔ بهره", ""), ("inventory", "موجودی کالا", ""),
        ("invested_capital", "سرمایهٔ به‌کاررفته", ""), ("k_period", "دورهٔ ‎%K", "معمولاً ۱۴"),
        ("leverage", "اهرم", "مثلاً ۵"), ("lows", "کف‌ها", _LIST),
        ("maintenance_margin_rate", "نرخ مارجین نگهداری", _FR), ("market", "بازده بازار", "بازده‌ها با کاما"),
        ("market_cap", "ارزش بازار", ""), ("market_price", "قیمت بازار اختیار", ""),
        ("mid_year", "قرارداد میانهٔ سال؟", "true یا false"), ("minority_interest", "سهم اقلیت", ""),
        ("multiplier", "ضریب قرارداد", "معمولاً ۱۰۰"), ("net_debt", "بدهی خالص", ""),
        ("net_equity", "سرمایهٔ خالص", ""), ("net_income", "سود خالص", ""),
        ("num_std", "تعداد انحراف معیار", "معمولاً ۲"), ("operating_income", "سود عملیاتی", ""),
        ("option_type", "نوع اختیار", ""), ("pe", "نسبت P/E", ""), ("period", "دوره", "تعداد کندل"),
        ("position", "موقعیت", ""), ("position_value", "ارزش پوزیشن", ""), ("preferred_equity", "سهام ممتاز", ""),
        ("premium", "پرمیوم (قیمت اختیار)", ""), ("price", "قیمت", ""), ("prices", "قیمت‌ها", _LIST),
        ("rate", "نرخ تبدیل", ""), ("rate_quote", "جهت نرخ", ""),
        ("returns", "بازده‌های دوره‌ای", "کسر با کاما؛ ۰٫۰۱ یعنی ۱٪"), ("revenue", "فروش", ""),
        ("risk_free_rate", "نرخ بدون ریسک سالانه", "کسر؛ ۰٫۰۴ یعنی ۴٪"), ("risk_pct", "درصد ریسک", "کسر؛ ۰٫۰۲ یعنی ۲٪"),
        ("sample", "انحراف معیار نمونه؟", "true یا false"), ("shareholders_equity", "حقوق صاحبان سهام", ""),
        ("shares_outstanding", "تعداد سهام", "برای ارزش هر سهم"), ("side", "جهت", ""),
        ("signal", "دورهٔ سیگنال", "معمولاً ۹"), ("slow", "دورهٔ کند", "معمولاً ۲۶"),
        ("spot", "قیمت دارایی پایه", ""), ("spot_at_expiry", "قیمت در سررسید", ""),
        ("start", "مقدار اولیه", ""), ("steps", "تعداد گام درخت", ""), ("stop", "حد ضرر", ""),
        ("strike", "قیمت اعمال", ""), ("target", "هدف", ""), ("tax_rate", "نرخ مالیات", _FR),
        ("terminal_growth", "رشد پایانی", "کسر؛ خالی یعنی بدون ارزش پایانی"),
        ("time_to_expiry", "زمان تا سررسید", "به سال؛ ۳۰ روز ≈ ۰٫۰۸۲"), ("to_currency", "به ارز", "مثلاً USD"),
        ("total_assets", "کل دارایی‌ها", ""), ("total_debt", "کل بدهی", ""),
        ("volatility", "نوسان سالانه", "کسر؛ ۰٫۲۵ یعنی ۲۵٪"), ("volumes", "حجم‌ها", _LIST),
        ("weights", "وزن‌ها", "کسر با کاما؛ جمع = ۱"), ("years", "تعداد سال", ""),
        ("years_to_call", "سال تا بازخرید", ""), ("years_to_maturity", "سال تا سررسید", ""),
        ("ytm", "بازده تا سررسید", _FR)):
    _p(_n, _l, _h)


def category_title(key):
    return dict(CATEGORIES)[key]


def by_category():
    """[(category key, Persian title, [tool names sorted by Persian title])], in CATEGORIES order."""
    return [(key, title, sorted((n for n, t in TOOLS.items() if t[0] == key), key=lambda n: TOOLS[n][1]))
            for key, title in CATEGORIES]


def example_text(value):
    """An example value as the user would type it into the form (lists comma-separated)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return ", ".join(example_text(v) for v in value)
    return str(value)
