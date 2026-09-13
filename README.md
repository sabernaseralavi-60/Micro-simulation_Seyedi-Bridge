# مطالعهٔ ساماندهی ترافیکی تقاطع زیرپل سیدی، کرمان
# Seyedi Under-Bridge Intersection Traffic Reorganization Study — Kerman, Iran

> **وضعیت: فاز ۰ (پیش‌پرواز) — در انتظار تأیید Checkpoint ۱.**
> نتایج این نسخه **کالیبره‌نشده** خواهند بود؛ صرفاً برای مقایسهٔ نسبی سناریوها معتبرند، نه پیش‌بینی مقادیر مطلق.

## فارسی

### موضوع
تقاطع زیرپل سیدی (بلوار سیدی × بزرگراه امام‌رضا) در کرمان به‌صورت یک دایرهٔ ترافیکی غیررسمی
(weaving) بدون چراغ و بدون کانالیزاسیون عمل می‌کند. حرکات مستقیم روی عرشهٔ پل مشکلی ندارند؛
گلوگاه، حرکات گردشی **زیر پل** است.

### بازتولید
```bash
git clone <repo-url> && cd seyedi-bridge-study
python -m venv .venv && .venv/Scripts/pip install -e .
source scripts/env.sh   # یا: . scripts/env.ps1  در پاورشل
make all
```

### ساختار
جزئیات کامل روش‌شناسی، فازبندی، و قواعد سخت پروژه در [`CLAUDE.md`](CLAUDE.md) آمده است.
بازبینی تصاویر ماهواره‌ای فاز ۰ در [`docs/imagery_review.md`](docs/imagery_review.md).
تمام فرض‌های ورودی مدل با منبع و بازهٔ حساسیت در [`config/assumptions.yml`](config/assumptions.yml).

---

## English

### Problem
The Seyedi under-bridge intersection (Seyedi Blvd × Imam Reza Highway) in Kerman functions as an
uncontrolled, unchannelized weaving/roundabout-like junction. Through movements on the bridge deck
are not the bottleneck — the **turning movements under the bridge** are.

### Reproduce
```bash
git clone <repo-url> && cd seyedi-bridge-study
python -m venv .venv && .venv/Scripts/pip install -e .
source scripts/env.sh   # or: . scripts/env.ps1 on PowerShell
make all
```

### Structure
Full methodology, phasing, and hard rules are in [`CLAUDE.md`](CLAUDE.md).
Phase-0 imagery review: [`docs/imagery_review.md`](docs/imagery_review.md).
All input assumptions with source and sensitivity range: [`config/assumptions.yml`](config/assumptions.yml).

**Model status: UNCALIBRATED.** Results are valid only for relative scenario comparison, not
absolute value prediction. See the mandatory Limitations section of the report (added in Phase 5).
