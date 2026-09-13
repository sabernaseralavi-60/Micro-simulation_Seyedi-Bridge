#!/usr/bin/env python
"""
فاز ۱-۳ — نمودارهای خلاصهٔ KPI سناریوی S0.

می‌خواند: outputs/tables/s0_kpi_summary.csv و s0_lambda_summary.csv
(تولیدشده در src/05_extract_kpis.py)
می‌نویسد: outputs/figures/s0_timeloss_by_approach.{svg,png} و
outputs/figures/s0_sensitivity_lambda.{svg,png}

اجرا: `make figures` (بخشی از `make analyze`/`make all`)
"""
from __future__ import annotations

import pathlib
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
TABLE = ROOT / "outputs" / "tables" / "s0_kpi_summary.csv"
LAMBDA_TABLE = ROOT / "outputs" / "tables" / "s0_lambda_summary.csv"
FIG_DIR = ROOT / "outputs" / "figures"

# پالت کیفی ثابت (ترتیب معنادار: چهار پا + کل) — طبق راهنمای dataviz، هرگز چرخشی نیست
APPROACH_ORDER = ["west", "east", "north", "south", "کل (all)"]
APPROACH_LABELS_FA = {
    "west": "غرب (عرشهٔ پل)", "east": "شرق (عرشهٔ پل)",
    "north": "شمال (جادهٔ سیدی)", "south": "جنوب (بلوار سلیمانی)",
    "کل (all)": "کل تقاطع",
}
COLORS = {
    "west": "#4C78A8", "east": "#72B7B2", "north": "#E45756",
    "south": "#F58518", "کل (all)": "#54585A",
}


def fix_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def main() -> None:
    fix_console_encoding()
    df = pd.read_csv(TABLE).set_index("approach").loc[APPROACH_ORDER].reset_index()

    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    labels = [APPROACH_LABELS_FA[a] for a in df["approach"]]
    colors = [COLORS[a] for a in df["approach"]]
    bars = ax.bar(labels, df["mean_timeloss_s"], color=colors, width=0.6)

    for bar, val in zip(bars, df["mean_timeloss_s"]):
        ax.annotate(f"{val:.1f}", (bar.get_x() + bar.get_width() / 2, bar.get_height()),
                    xytext=(0, 4), textcoords="offset points", ha="center", fontsize=9)

    ax.set_ylabel("میانگین تلف‌شدگی زمان (ثانیه/وسیله)")
    ax.set_title(
        "میانگین تلف‌شدگی زمان به تفکیک پا — سناریوی S0 (وضع موجود)، λ=۱.۰\n"
        "میانگین روی ۱۰ seed — مدل کالیبره‌نشده، فقط برای مقایسهٔ نسبی",
        fontsize=10,
    )
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    for path in (FIG_DIR / "s0_timeloss_by_approach.svg", FIG_DIR / "s0_timeloss_by_approach.png"):
        fig.savefig(path, dpi=200)
        print(f"[ok] نوشته شد: {path}")


def plot_lambda_sensitivity() -> None:
    df = pd.read_csv(LAMBDA_TABLE)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))

    for ax, metric, ylabel, color in [
        (axes[0], "mean_timeloss_s", "میانگین تلف‌شدگی زمان (ثانیه/وسیله)", "#4C78A8"),
        (axes[1], "n_collisions", "میانگین تعداد برخورد ثبت‌شده (در هر اجرا)", "#E45756"),
    ]:
        sub = df[df["metric"] == metric].sort_values("lambda")
        yerr_lo = sub["mean"] - sub["ci95_lo"]
        yerr_hi = sub["ci95_hi"] - sub["mean"]
        ax.errorbar(sub["lambda"], sub["mean"], yerr=[yerr_lo, yerr_hi],
                    fmt="o-", color=color, capsize=4, lw=2, markersize=6)
        ax.set_xlabel("ضریب مقیاس تقاضا λ")
        ax.set_ylabel(ylabel)
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(alpha=0.25)
        ax.set_xticks(sorted(df["lambda"].unique()))

    fig.suptitle(
        "حساسیت سناریوی S0 به سطح تقاضا (λ) — میانگین ± فاصلهٔ اطمینان ۹۵٪ روی ۱۰ seed\n"
        "مدل کالیبره‌نشده؛ تعداد برخورد فقط علامت کیفی تراکم تعارض است، نه نرخ واقعی",
        fontsize=10,
    )
    fig.tight_layout()

    for path in (FIG_DIR / "s0_sensitivity_lambda.svg", FIG_DIR / "s0_sensitivity_lambda.png"):
        fig.savefig(path, dpi=200)
        print(f"[ok] نوشته شد: {path}")


if __name__ == "__main__":
    main()
    plot_lambda_sensitivity()
