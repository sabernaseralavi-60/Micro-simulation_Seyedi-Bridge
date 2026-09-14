#!/usr/bin/env python
"""
فاز ۴ — آزمون تشخیصی حساسیت رفتاری: سهم «اثر خودِ چراغ (S1)» را از سهم «اثر
رفتار تهاجمی کالیبره‌نشدهٔ ناوگان» جدا می‌کند.

این اسکریپت یک اجرای *تشخیصی* است، نه بخشی از رجیستری رسمی سناریوها
(config/scenarios.yml) — به همین دلیل مستقل نوشته شده و config/scenarios.yml
را تغییر نمی‌دهد. S0 و S1 (نسخهٔ fixed) را دوباره، این‌بار با
config/vtypes_diagnostic_default.yml (پارامترهای رفتاری پیش‌فرض واقعی SUMO،
نه تنظیمات تهاجمی این مطالعه) در همان ۵ سطح λ × ۱۰ seed اجرا می‌کند.

اگر با این تنظیمات هم S1 بدتر از S0 باشد، یافتهٔ فاز ۴ عمدتاً به «سیگنال به
خودی خود» نسبت داده می‌شود، نه رفتار تهاجمی. اگر شکاف به‌شدت کوچک‌تر شود یا
معکوس شود، رفتار تهاجمی مکانیزم غالب تأیید می‌شود (رجوع به بحث فاز ۴ در
report/report-fa.qmd).

خروجی: scenarios/_diagnostics/behavior_default/{s0,s1_fixed}/lambda_*/seed_*/
و outputs/tables/diag_*_lambda_summary.csv

اجرا: `make behavior-diagnostic`
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys
import time
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd
import yaml
from scipy import stats

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSUMPTIONS = ROOT / "config" / "assumptions.yml"
VTYPES_DIAGNOSTIC = ROOT / "config" / "vtypes_diagnostic_default.yml"
DIAG_OUT_ROOT = ROOT / "scenarios" / "_diagnostics" / "behavior_default"
TABLES_DIR = ROOT / "outputs" / "tables"

JOBS = {
    "diag_s0": ROOT / "network" / "seyedi.net.xml",
    "diag_s1_fixed": ROOT / "scenarios" / "S1_signal" / "network" / "seyedi_S1_fixed.net.xml",
}


def fix_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def _load_module(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_experiments(run_experiments_mod, build_demand_mod, assumptions, vcfg) -> None:
    lambdas = assumptions["experiment_design"]["demand_scale_levels"]["value"]
    n_seeds = assumptions["experiment_design"]["n_seeds_per_condition"]["value"]

    total = len(JOBS) * len(lambdas) * n_seeds
    done = 0
    t0 = time.time()
    for label, net_file in JOBS.items():
        if not net_file.exists():
            raise FileNotFoundError(f"شبکهٔ {label} یافت نشد: {net_file}")
        for lam in lambdas:
            for seed in range(1, n_seeds + 1):
                out_dir = DIAG_OUT_ROOT / label / f"lambda_{lam}" / f"seed_{seed}"
                ran = run_experiments_mod.run_one(
                    build_demand_mod, assumptions, vcfg, net_file=net_file,
                    lambda_scale=lam, seed=seed, out_dir=out_dir,
                )
                done += 1
                tag = "done" if ran else "skip (exists)"
                print(f"[{done}/{total}] {label} lambda={lam} seed={seed} {tag} "
                      f"({time.time()-t0:.0f}s elapsed)")
    print(f"[ok] {total} اجرای تشخیصی کامل شد در {time.time()-t0:.0f} ثانیه.")


def count_collisions(stats_path: pathlib.Path) -> int:
    if not stats_path.exists():
        return 0
    root = ET.parse(stats_path).getroot()
    safety = root.find("safety")
    return int(safety.get("collisions", 0)) if safety is not None else 0


def ci95(series: pd.Series) -> tuple[float, float, float]:
    n = len(series)
    m = series.mean()
    if n < 2:
        return m, m, m
    se = series.std(ddof=1) / np.sqrt(n)
    h = se * stats.t.ppf(0.975, n - 1)
    return m, m - h, m + h


def extract(label: str) -> pd.DataFrame:
    out_root = DIAG_OUT_ROOT / label
    rows = []
    for lam_dir in sorted(out_root.glob("lambda_*"), key=lambda p: float(p.name.split("_")[1])):
        lam = float(lam_dir.name.split("_")[1])
        for seed_dir in sorted(lam_dir.glob("seed_*"), key=lambda p: int(p.name.split("_")[1])):
            seed = int(seed_dir.name.split("_")[1])
            tripinfo = seed_dir / "tripinfo.xml"
            if not tripinfo.exists():
                continue
            durations, timelosses, waits = [], [], []
            for _, elem in ET.iterparse(str(tripinfo), events=("end",)):
                if elem.tag == "tripinfo":
                    durations.append(float(elem.get("duration")))
                    timelosses.append(float(elem.get("timeLoss")))
                    waits.append(float(elem.get("waitingTime")))
                    elem.clear()
            if not durations:
                continue
            rows.append({
                "scenario": label, "lambda": lam, "seed": seed,
                "n_vehicles": len(durations),
                "mean_duration_s": float(np.mean(durations)),
                "mean_timeloss_s": float(np.mean(timelosses)),
                "mean_waiting_s": float(np.mean(waits)),
                "n_collisions": count_collisions(seed_dir / "stats.xml"),
            })
    return pd.DataFrame(rows)


def summarize(df_seed: pd.DataFrame, label: str) -> pd.DataFrame:
    lambda_rows = []
    for lam, grp in df_seed.groupby("lambda"):
        for metric in ("mean_timeloss_s", "mean_waiting_s", "n_collisions"):
            m, lo, hi = ci95(grp[metric])
            lambda_rows.append({"scenario": label, "lambda": lam, "metric": metric,
                                 "mean": m, "ci95_lo": lo, "ci95_hi": hi, "n_seeds": len(grp)})
    return pd.DataFrame(lambda_rows)


def main() -> None:
    fix_console_encoding()
    with open(ASSUMPTIONS, "r", encoding="utf-8") as f:
        assumptions = yaml.safe_load(f)
    with open(VTYPES_DIAGNOSTIC, "r", encoding="utf-8") as f:
        vcfg = yaml.safe_load(f)

    build_demand_mod = _load_module("build_demand", ROOT / "src" / "03_build_demand.py")
    run_experiments_mod = _load_module("run_experiments", ROOT / "src" / "04_run_experiments.py")

    run_experiments(run_experiments_mod, build_demand_mod, assumptions, vcfg)

    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    all_seed = []
    all_lambda = []
    for label in JOBS:
        df_seed = extract(label)
        if df_seed.empty:
            print(f"[warn] هیچ دادهٔ {label} استخراج نشد.")
            continue
        df_seed.to_csv(TABLES_DIR / f"{label}_seed_summary.csv", index=False)
        df_lambda = summarize(df_seed, label)
        df_lambda.to_csv(TABLES_DIR / f"{label}_lambda_summary.csv", index=False)
        all_seed.append(df_seed)
        all_lambda.append(df_lambda)

    if all_lambda:
        pd.concat(all_lambda, ignore_index=True).to_csv(
            TABLES_DIR / "diag_behavior_default_lambda_summary.csv", index=False)
        print(f"[ok] نوشته شد: {TABLES_DIR / 'diag_behavior_default_lambda_summary.csv'}")

    by_label = {df["scenario"].iat[0]: df for df in all_seed if not df.empty}
    if "diag_s0" in by_label and "diag_s1_fixed" in by_label:
        df0 = by_label["diag_s0"].set_index(["lambda", "seed"])
        df1 = by_label["diag_s1_fixed"].set_index(["lambda", "seed"])
        rows = []
        for lam in sorted(assumptions["experiment_design"]["demand_scale_levels"]["value"]):
            a = df1.loc[(lam,)]["mean_timeloss_s"].to_numpy(dtype=float)
            b = df0.loc[(lam,)]["mean_timeloss_s"].to_numpy(dtype=float)
            n = min(len(a), len(b))
            a, b = a[:n], b[:n]
            t_stat, p_val = stats.ttest_rel(a, b)
            rows.append({"lambda": lam, "mean_s1_fixed_diag": a.mean(), "mean_s0_diag": b.mean(),
                         "pct_diff": 100 * (a.mean() - b.mean()) / b.mean(), "p_value": p_val})
        result = pd.DataFrame(rows)
        result.to_csv(TABLES_DIR / "diag_behavior_default_comparison.csv", index=False)
        print(result.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
