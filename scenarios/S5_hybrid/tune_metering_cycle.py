#!/usr/bin/env python
"""
فاز ۴ — تنظیم تجربی سبک سیکل چراغ متردهندهٔ S5-metering (نشست ۴).

این اسکریپت یک **جست‌وجوی طراحی** است، نه یک مقایسهٔ سناریویی که قاعدهٔ سخت ۵
(حداقل ۱۰ seed) بر آن حاکم باشد — دقیقاً هم‌رده با استفادهٔ S1 از فرمول وبستر:
یک روش مستند برای انتخاب یک پارامتر طراحی، نه ادعایی دربارهٔ عملکرد نهایی
سناریو. سیکل نهایی انتخاب‌شده سپس مثل هر نسخهٔ کنترلی دیگر، در خط لولهٔ
رسمی (`src/04_run_experiments.py`) با ۵λ×۱۰seed کامل اجرا و در گزارش با
فاصلهٔ اطمینان ذکر می‌شود.

روش: چند سیکل کاندید در دو سطح تقاضا (λ=۱.۰ طراحی، λ=۱.۴ اوج — دو نقطه‌ای
که در گزارش بیشترین اهمیت را دارند) با ۳ seed سبک (نه ۱۰) ساخته و اجرا
می‌شوند؛ میانگین تلف‌شدگی زمان، برخورد، و حداکثر صف هر ترکیب گزارش می‌شود.
سیکل با بهترین مجموع رتبه (کمترین میانگینِ نرمال‌شدهٔ سه معیار در λ=۱.۴،
چون این تحلیل قبلی نشان داد λ=۱.۴ نقطهٔ تمایزدهندهٔ واقعی است) به‌عنوان
سیکل نهایی در `build_network.py::main` ثبت می‌شود.

**تلهٔ کشف‌شده و رفع‌شده در دور اول این جست‌وجو:** netconvert وقتی سیکل
هدف با حداقل سبز/زرد هر فاز سازگار نیست، **بی‌صدا** (فقط یک هشدار
«cannot be adapted») به سیکل پیش‌فرض خودش برمی‌گردد. کاندید ۱۵ ثانیهٔ دور
اول عملاً هرگز اعمال نشد — سیکل واقعی تولیدشده ۷۲ ثانیه (پیش‌فرض
netconvert) بود، نه ۱۵. برای جلوگیری از تکرار این خطا، این نسخه سیکل
واقعیِ اعمال‌شده را مستقیماً از tlLogic تولیدشده در net.xml می‌خواند و
همان را (نه عدد درخواستی) در جدول نتایج ثبت می‌کند؛ کاندیدها هم به بازهٔ
واقعاً قابل‌اعمال (۲۰ تا ۶۰، به‌علاوه «پیش‌فرض netconvert» با
`cycle_time=None`) اصلاح شدند.

اجرا: `python scenarios/S5_hybrid/tune_metering_cycle.py`
خروجی: `scenarios/S5_hybrid/tune_metering_cycle_result.csv` + چاپ خلاصه.
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys
import xml.etree.ElementTree as ET

import pandas as pd
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCEN_DIR = pathlib.Path(__file__).resolve().parent
ASSUMPTIONS = ROOT / "config" / "assumptions.yml"
VTYPES_CFG = ROOT / "config" / "vtypes.yml"

CANDIDATE_CYCLES = [20, 30, 40, 50, 60, None]  # None = بدون --tls.cycle.time (پیش‌فرض netconvert)
TEST_LAMBDAS = [1.0, 1.4]
TEST_SEEDS = [1, 2, 3]


def actual_cycle_length(net_path: pathlib.Path, tls_id: str) -> float:
    """سیکل واقعاً اعمال‌شده را از خودِ net.xml تولیدشده می‌خواند — چون
    netconvert می‌تواند --tls.cycle.time را بی‌صدا نادیده بگیرد (رجوع به
    توضیح بالا)؛ هرگز به مقدار درخواستی اعتماد نکن، همیشه net.xml را بازرسی کن."""
    root = ET.parse(net_path).getroot()
    for tl in root.findall("tlLogic"):
        if tl.get("id") == tls_id:
            return sum(float(p.get("duration")) for p in tl.findall("phase"))
    return float("nan")


def fix_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def _load_module(name: str, relpath: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relpath)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> None:
    fix_console_encoding()
    s5build = _load_module("s5build", "scenarios/S5_hybrid/build_network.py")
    run_exp = _load_module("run_exp", "src/04_run_experiments.py")
    kpi = _load_module("kpi", "src/05_extract_kpis.py")

    s3 = s5build._load_s3_module()
    with open(ASSUMPTIONS, "r", encoding="utf-8") as f:
        assumptions = yaml.safe_load(f)
    with open(VTYPES_CFG, "r", encoding="utf-8") as f:
        vcfg = yaml.safe_load(f)
    build_demand = run_exp._load_demand_module()

    tune_root = SCEN_DIR / "tune_runs"
    rows = []
    for cycle in CANDIDATE_CYCLES:
        tag = "default" if cycle is None else str(cycle)
        net_path = s5build.build_metering(
            s3, cycle_time=cycle,
            out_name=f"seyedi_S5_metering_tune_c{tag}.net.xml",
            plain_name=f"seyedi_s5_metering_tune_c{tag}",
        )
        actual_cycle = actual_cycle_length(net_path, s3.RING_NODES["W"])
        requested = "پیش‌فرض netconvert" if cycle is None else f"{cycle}s"
        print(f"[cycle candidate] درخواستی={requested} → واقعاً اعمال‌شده={actual_cycle:.0f}s")
        for lam in TEST_LAMBDAS:
            for seed in TEST_SEEDS:
                out_dir = tune_root / f"c{tag}" / f"lambda_{lam}" / f"seed_{seed}"
                run_exp.run_one(build_demand, assumptions, vcfg, net_file=net_path,
                                 lambda_scale=lam, seed=seed, out_dir=out_dir)
                trips = kpi.parse_one_tripinfo(out_dir / "tripinfo.xml", lam, seed)
                df = pd.DataFrame(trips)
                n_col = kpi.count_collisions(out_dir / "stats.xml")
                q_max = kpi.max_queue_length(out_dir / "queue.xml")
                rows.append({
                    "cycle_requested": requested, "cycle_s": actual_cycle, "lambda": lam, "seed": seed,
                    "mean_timeloss_s": df["timeLoss"].mean() if len(df) else float("nan"),
                    "n_collisions": n_col, "max_queue_length_m": q_max,
                })
                print(f"[c={requested} (واقعی {actual_cycle:.0f}s) λ={lam} seed={seed}] "
                      f"timeloss={rows[-1]['mean_timeloss_s']:.1f}s "
                      f"collisions={n_col} queue={q_max:.1f}m")

    raw = pd.DataFrame(rows)
    raw.to_csv(SCEN_DIR / "tune_metering_cycle_result.csv", index=False)

    agg = raw.groupby("cycle_requested")[["cycle_s", "mean_timeloss_s", "n_collisions", "max_queue_length_m"]].mean()
    print("\n=== میانگین روی هر ۲ λ × ۳ seed (۶ اجرا در هر سیکل درخواستی) ===")
    print(agg.round(2).to_string())

    peak = raw[raw["lambda"] == 1.4].groupby("cycle_requested")[
        ["cycle_s", "mean_timeloss_s", "n_collisions", "max_queue_length_m"]].mean()
    norm = (peak[["mean_timeloss_s", "n_collisions", "max_queue_length_m"]]
            - peak[["mean_timeloss_s", "n_collisions", "max_queue_length_m"]].min()) / (
        peak[["mean_timeloss_s", "n_collisions", "max_queue_length_m"]].max()
        - peak[["mean_timeloss_s", "n_collisions", "max_queue_length_m"]].min()).replace(0, 1)
    score = norm.mean(axis=1)
    best_requested = score.idxmin()
    best_actual = peak.loc[best_requested, "cycle_s"]
    print("\n=== فقط λ=۱.۴ (نقطهٔ تمایزدهنده)، نرمال‌شده، رتبه‌بندی ===")
    print(pd.concat([score.rename("score"), peak["cycle_s"].rename("actual_cycle_s")], axis=1)
          .sort_values("score").round(3).to_string())
    print(f"\n[نتیجه] سیکل منتخب (درخواستی برای build_metering): {best_requested} "
          f"→ سیکل واقعی {best_actual:.0f} ثانیه")

    with open(SCEN_DIR / "tune_metering_cycle_choice.txt", "w", encoding="utf-8") as f:
        f.write(f"requested={best_requested}\nactual_s={best_actual:.0f}\n")


if __name__ == "__main__":
    main()
