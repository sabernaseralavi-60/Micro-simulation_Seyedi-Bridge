#!/usr/bin/env python
"""
فاز ۱ — یک نمودار خلاصه از KPI سناریوی S0 (تک-seed، Walking Skeleton).

می‌خواند: outputs/tables/s0_kpi_summary.csv (تولیدشده در src/05_extract_kpis.py)
می‌نویسد: outputs/figures/s0_timeloss_by_approach.{svg,png}

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
        "میانگین تلف‌شدگی زمان به تفکیک پا — سناریوی S0 (وضع موجود)\n"
        "تک-seed، تقاضای فرضی فاز ۱ — مدل کالیبره‌نشده، فقط برای مقایسهٔ نسبی",
        fontsize=10,
    )
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    for path in (FIG_DIR / "s0_timeloss_by_approach.svg", FIG_DIR / "s0_timeloss_by_approach.png"):
        fig.savefig(path, dpi=200)
        print(f"[ok] نوشته شد: {path}")


if __name__ == "__main__":
    main()
