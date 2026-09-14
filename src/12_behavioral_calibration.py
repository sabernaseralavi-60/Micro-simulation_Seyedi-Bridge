#!/usr/bin/env python
"""
فاز ۶ (تأیید صریح کاربر، ۱۴۰۵/۰۶/۲۴) — آزمون استحکام رفتاری با Optuna.

**این کالیبراسیون-به-دادهٔ-میدانی نیست.** طبق §۵ CLAUDE.md، کالیبراسیون واقعی
(GEH<5 در مقابل شمارش گردش، خطای زمان سفر <۱۵٪) نیاز به داده‌ای دارد که هنوز
جمع‌آوری نشده. این اسکریپت یک **جست‌وجوی دوهدفه (Pareto، NSGA-II)** روی ۶
ضریب رفتاری است که مستقیماً پرسش بازِ فاز ۴ را جواب می‌دهد: آیا فروپاشی
برخورد در S1-fixed و S5-oneway_priority در λ=۱.۴ محصول یک نقطهٔ خاص و
دلبخواهی از فضای پارامتر تهاجمی (config/vtypes.yml) است، یا در سراسر بازهٔ
معقول مهندسی (۰.۷ تا ۱.۳ برابر مقادیر فعلی) پایدار می‌ماند؟

روش: هر ۶ ضریب (tau, minGap, sigma, impatience, jmIgnoreFoeProb, lcAssertive)
به‌طور یکسان روی مقدار *فعلی* همان پارامتر در تمام ردیف‌های vtypes.yml اعمال
می‌شود (آراستگی نسبی ناوگان حفظ می‌شود، فقط شدت کلی تهاجمی‌بودن جست‌وجو
می‌شود). هر ترایال = ۲ سناریو (S1-fixed, S5-oneway_priority) × ۲ seed = ۴
اجرای SUMO در λ=۱.۴؛ هدف: min(میانگین timeloss روی این ۴ اجرا),
min(میانگین برخورد روی همین ۴ اجرا). دامنه/تعداد ترایال در
config/assumptions.yml -> experiment_design.behavioral_calibration_search
ثبت شده (۴۰ ترایال × ۲ سناریو × ۲ seed = ۱۶۰ ران، ~۲.۳ ساعت — پس از سنجش
زمانی واقعی یک ترایال (۱۰۳ ثانیه/۲ ران با seed=۱) با کاربر تأیید شد).

اجرا: `make behavioral-calibration` (~۲.۳ ساعت — resume-پذیر، هر (ترایال,
سناریو, seed) که tripinfo.xml از قبل دارد رد می‌شود)
خروجی: scenarios/_diagnostics/behavioral_calibration/trial_*/...,
outputs/tables/behavioral_calibration_{trials,pareto}.csv,
outputs/figures/behavioral_calibration_pareto.{svg,png}
"""
from __future__ import annotations

import copy
import importlib.util
import pathlib
import sys
import time
import xml.etree.ElementTree as ET

import numpy as np
import optuna
import pandas as pd
import yaml

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSUMPTIONS = ROOT / "config" / "assumptions.yml"
VTYPES_CFG = ROOT / "config" / "vtypes.yml"
OUT_ROOT = ROOT / "scenarios" / "_diagnostics" / "behavioral_calibration"
TABLES_DIR = ROOT / "outputs" / "tables"
FIG_DIR = ROOT / "outputs" / "figures"

JOBS = {
    "s1_fixed": ROOT / "scenarios" / "S1_signal" / "network" / "seyedi_S1_fixed.net.xml",
    "s5_oneway_priority": ROOT / "scenarios" / "S5_hybrid" / "network" / "seyedi_S5_oneway.net.xml",
}

# مقادیر مبنا (ضرایب فعلی این مطالعه، معادل multiplier=1.0 برای همهٔ ۶ محور)
# از outputs/tables/*_lambda_summary.csv موجود، λ=1.4 — برای رسم مرجع روی نمودار،
# نه برای اجرای دوباره (این دو نقطه از قبل در فاز ۴ اجرا و گزارش شده‌اند).
BASELINE_REF_TABLES = {
    "s1_fixed": TABLES_DIR / "s1_fixed_lambda_summary.csv",
    "s5_oneway_priority": TABLES_DIR / "s5_oneway_lambda_summary.csv",
}

PARAM_FIELDS = ["tau", "minGap", "sigma", "impatience", "jmIgnoreFoeProb", "lcAssertive"]


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


# حداکثر مجاز طبق XSD واقعی SUMO برای هر پارامتر (نه یک برآورد) — بدون این
# سقف، ترایال ۸ (impatience_multiplier=1.165 روی taxi.impatience=0.9) واقعاً
# شکست خورد: jtrrouter با خطای schema «value '1.0486' must be <= maxInclusive
# facet value '1'» روی flows.xml رد شد. یافته و تکرارشده مستقیماً (نه حدس).
FIELD_MAX = {"sigma": 1.0, "impatience": 1.0}


def scaled_vcfg(base_vcfg: dict, multipliers: dict[str, float]) -> dict:
    """کپی عمیق vcfg با ۶ ضریب یکسان روی همهٔ ردیف‌های vtypes اعمال‌شده،
    با سقف مطابق XSD واقعی SUMO برای پارامترهایی که محدودهٔ [0,1] دارند."""
    vcfg = copy.deepcopy(base_vcfg)
    for vt in vcfg["vtypes"].values():
        for field in PARAM_FIELDS:
            if field in vt:
                mult = multipliers[f"{field}_multiplier"]
                scaled = vt[field] * mult
                if field in FIELD_MAX:
                    scaled = min(scaled, FIELD_MAX[field])
                vt[field] = round(scaled, 4)
    return vcfg


def count_collisions(stats_path: pathlib.Path) -> int:
    if not stats_path.exists():
        return 0
    root = ET.parse(stats_path).getroot()
    safety = root.find("safety")
    return int(safety.get("collisions", 0)) if safety is not None else 0


def mean_timeloss(tripinfo_path: pathlib.Path) -> float:
    if not tripinfo_path.exists():
        return float("nan")
    vals = []
    for _, elem in ET.iterparse(str(tripinfo_path), events=("end",)):
        if elem.tag == "tripinfo":
            vals.append(float(elem.get("timeLoss")))
            elem.clear()
    return float(np.mean(vals)) if vals else float("nan")


def run_trial(trial: optuna.Trial, assumptions: dict, base_vcfg: dict,
              run_experiments_mod, build_demand_mod, n_seeds: int) -> tuple[float, float]:
    search_cfg = assumptions["experiment_design"]["behavioral_calibration_search"]["value"]
    multipliers = {}
    for p in search_cfg["parameters"]:
        multipliers[p["name"]] = trial.suggest_float(p["name"], p["low"], p["high"])

    vcfg = scaled_vcfg(base_vcfg, multipliers)
    lam = search_cfg["lambda"]
    trial_dir = OUT_ROOT / f"trial_{trial.number:04d}"

    timelosses, collisions = [], []
    for label, net_file in JOBS.items():
        for seed in range(1, n_seeds + 1):
            out_dir = trial_dir / label / f"seed_{seed}"
            run_experiments_mod.run_one(
                build_demand_mod, assumptions, vcfg,
                net_file=net_file, lambda_scale=lam, seed=seed, out_dir=out_dir,
            )
            tl = mean_timeloss(out_dir / "tripinfo.xml")
            if not np.isnan(tl):
                timelosses.append(tl)
            collisions.append(count_collisions(out_dir / "stats.xml"))

    # ثبت ضرایب این ترایال برای بازیابی/تحلیل بعدی (Optuna خودش هم ذخیره می‌کند
    # اما یک CSV مستقل ساده‌تر برای خواندن دستی/pandas است)
    trial.set_user_attr("multipliers", multipliers)
    return float(np.mean(timelosses)) if timelosses else float("nan"), float(np.mean(collisions))


def main() -> None:
    fix_console_encoding()
    with open(ASSUMPTIONS, "r", encoding="utf-8") as f:
        assumptions = yaml.safe_load(f)
    with open(VTYPES_CFG, "r", encoding="utf-8") as f:
        base_vcfg = yaml.safe_load(f)

    search_cfg = assumptions["experiment_design"]["behavioral_calibration_search"]["value"]
    n_trials = search_cfg["n_trials"]
    n_seeds = search_cfg["n_seeds_per_trial"]

    build_demand_mod = _load_module("build_demand", ROOT / "src" / "03_build_demand.py")
    run_experiments_mod = _load_module("run_experiments", ROOT / "src" / "04_run_experiments.py")

    storage_path = OUT_ROOT / "optuna_study.db"
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    study = optuna.create_study(
        study_name="seyedi_behavioral_calibration",
        directions=["minimize", "minimize"],
        # population_size=20 (نه پیش‌فرض ۵۰) تا با ۴۰ ترایال حداقل ۲ نسل واقعی
        # تحول NSGA-II طی شود؛ با population_size پیش‌فرض کل مطالعه فقط
        # نسل اول (نمونه‌گیری شبه‌تصادفی) اجرا می‌شد و انتخاب واقعی رخ نمی‌داد.
        sampler=optuna.samplers.NSGAIISampler(seed=42, population_size=20),
        storage=f"sqlite:///{storage_path}",
        load_if_exists=True,
    )

    n_done = len(study.trials)
    print(f"[info] {n_done}/{n_trials} ترایال از قبل موجود (resume از sqlite).")
    t0 = time.time()
    while len(study.trials) < n_trials:
        trial = study.ask()
        try:
            objectives = run_trial(trial, assumptions, base_vcfg,
                                    run_experiments_mod, build_demand_mod, n_seeds)
        except Exception as exc:  # noqa: BLE001 -- ثبت شکست ترایال، نه توقف کل جست‌وجو
            print(f"[warn] ترایال {trial.number} شکست خورد: {exc}")
            study.tell(trial, state=optuna.trial.TrialState.FAIL)
            continue
        study.tell(trial, objectives)
        elapsed = time.time() - t0
        print(f"[{len(study.trials)}/{n_trials}] timeloss={objectives[0]:.2f}s "
              f"collisions={objectives[1]:.1f} ({elapsed:.0f}s elapsed)")

    export_results(study)


def export_results(study: optuna.Study) -> None:
    rows = []
    for t in study.trials:
        if t.state != optuna.trial.TrialState.COMPLETE:
            continue
        row = {"trial": t.number, "mean_timeloss_s": t.values[0], "mean_collisions": t.values[1]}
        row.update(t.user_attrs.get("multipliers", {}))
        rows.append(row)
    df = pd.DataFrame(rows)
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(TABLES_DIR / "behavioral_calibration_trials.csv", index=False)
    print(f"[ok] نوشته شد: {TABLES_DIR / 'behavioral_calibration_trials.csv'} ({len(df)} ترایال)")

    pareto_trials = study.best_trials
    pareto_rows = []
    for t in pareto_trials:
        row = {"trial": t.number, "mean_timeloss_s": t.values[0], "mean_collisions": t.values[1]}
        row.update(t.user_attrs.get("multipliers", {}))
        pareto_rows.append(row)
    df_pareto = pd.DataFrame(pareto_rows).sort_values("mean_timeloss_s")
    df_pareto.to_csv(TABLES_DIR / "behavioral_calibration_pareto.csv", index=False)
    print(f"[ok] نوشته شد: {TABLES_DIR / 'behavioral_calibration_pareto.csv'} "
          f"({len(df_pareto)} نقطهٔ Pareto)")

    correlation_table(df)
    plot_pareto(df, df_pareto)


def correlation_table(df: pd.DataFrame) -> None:
    """همبستگی خام هرکدام از ۶ ضریب با دو هدف — برای پاسخ به پرسش اصلی این
    جست‌وجو: کدام محور (اگر هیچ‌کدام نه) واقعاً فروپاشی برخورد را می‌راند؟
    خروجی مبنای عدد گزارش می‌شود (اصل «یک‌بار محاسبه، چندبار گزارش»)."""
    mult_cols = [c for c in df.columns if c.endswith("_multiplier")]
    corr = df[["mean_timeloss_s", "mean_collisions"] + mult_cols].corr()
    out = corr.loc[mult_cols, ["mean_timeloss_s", "mean_collisions"]].reset_index()
    out.columns = ["parameter_multiplier", "corr_with_mean_timeloss", "corr_with_mean_collisions"]
    out = out.sort_values("corr_with_mean_collisions", key=lambda s: s.abs(), ascending=False)
    out.to_csv(TABLES_DIR / "behavioral_calibration_correlations.csv", index=False)
    print(f"[ok] نوشته شد: {TABLES_DIR / 'behavioral_calibration_correlations.csv'}")
    print(out.round(3).to_string(index=False))


def plot_pareto(df_all: pd.DataFrame, df_pareto: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(9, 7))
    ax.scatter(df_all["mean_timeloss_s"], df_all["mean_collisions"],
               s=18, alpha=0.35, color="steelblue", label="ترایال‌های Optuna (همه)")
    ax.scatter(df_pareto["mean_timeloss_s"], df_pareto["mean_collisions"],
               s=45, color="#d62728", zorder=3, label="جبههٔ Pareto")
    ax.plot(df_pareto.sort_values("mean_timeloss_s")["mean_timeloss_s"],
            df_pareto.sort_values("mean_timeloss_s")["mean_collisions"],
            color="#d62728", lw=1, alpha=0.6, zorder=2)

    for label, path in BASELINE_REF_TABLES.items():
        if not path.exists():
            continue
        ref = pd.read_csv(path)
        row_tl = ref[(ref["lambda"] == 1.4) & (ref["metric"] == "mean_timeloss_s")]
        row_col = ref[(ref["lambda"] == 1.4) & (ref["metric"] == "n_collisions")]
        if not row_tl.empty and not row_col.empty:
            ax.scatter([row_tl["mean"].iat[0]], [row_col["mean"].iat[0]],
                       marker="*", s=220, color="black", zorder=4,
                       label=f"مبنای فعلی پروژه ({label}, λ=۱.۴)")

    ax.set_xlabel("میانگین timeloss (ثانیه)")
    ax.set_ylabel("میانگین تعداد برخورد در هر اجرا")
    ax.set_title(
        "آزمون استحکام رفتاری (Optuna NSGA-II) — S1-fixed + S5-oneway_priority @ λ=۱.۴\n"
        "آیا فروپاشی برخورد در سراسر فضای پارامتر تهاجمی پایدار می‌ماند؟",
        fontsize=10)
    ax.legend(fontsize=8, loc="upper right")
    fig.tight_layout()
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    for path in (FIG_DIR / "behavioral_calibration_pareto.svg",
                 FIG_DIR / "behavioral_calibration_pareto.png"):
        fig.savefig(path, dpi=200)
        print(f"[ok] نوشته شد: {path}")


if __name__ == "__main__":
    main()
