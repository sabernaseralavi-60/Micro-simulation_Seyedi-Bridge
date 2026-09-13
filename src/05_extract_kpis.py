#!/usr/bin/env python
"""
فاز ۳ — استخراج KPI از خروجی خام چند-λ × چند-seed SUMO به خلاصهٔ parquet/csv.

طبق اصل «یک‌بار محاسبه، چندبار گزارش» (CLAUDE.md فاز ۵)، فایل‌های .qmd هرگز
XML خام نمی‌خوانند؛ فقط خروجی‌های این اسکریپت در outputs/tables را می‌خوانند.

سه سطح خروجی تولید می‌شود:
1. s0_multirun_tripinfo.parquet — همهٔ رکوردهای per-vehicle، همهٔ ۵۰ اجرا
   (فقط outputs/tables، gitignore‌شده — عملاً هم‌ارز خام، نه خلاصه).
2. s0_seed_summary.csv — یک ردیف به ازای هر (λ, seed): ۵۰ ردیف. کامیت می‌شود.
3. s0_lambda_summary.csv — یک ردیف به ازای هر λ: میانگین ± فاصلهٔ اطمینان ۹۵٪
   روی ۱۰ seed (طبق قاعدهٔ سخت ۵). کامیت می‌شود.

اجرا: `make analyze`
"""
from __future__ import annotations

import pathlib
import sys
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd
from scipy import stats

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT_ROOT = ROOT / "scenarios" / "S0_baseline" / "out"
TABLES_DIR = ROOT / "outputs" / "tables"


def fix_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def approach_of(veh_id: str) -> str:
    for leg in ("west", "east", "north", "south"):
        if veh_id.startswith(f"from_{leg}"):
            return leg
    return "other"


def parse_one_tripinfo(path: pathlib.Path, lam: float, seed: int) -> list[dict]:
    rows = []
    for _, elem in ET.iterparse(str(path), events=("end",)):
        if elem.tag == "tripinfo":
            rows.append({
                "lambda": lam,
                "seed": seed,
                "id": elem.get("id"),
                "approach": approach_of(elem.get("id", "")),
                "vType": elem.get("vType"),
                "duration": float(elem.get("duration")),
                "routeLength": float(elem.get("routeLength")),
                "waitingTime": float(elem.get("waitingTime")),
                "timeLoss": float(elem.get("timeLoss")),
                "departDelay": float(elem.get("departDelay")),
            })
            elem.clear()
    return rows


def count_collisions(stats_path: pathlib.Path) -> int:
    if not stats_path.exists():
        return 0
    root = ET.parse(stats_path).getroot()
    safety = root.find("safety")
    if safety is None:
        return 0
    return int(safety.get("collisions", 0))


def ci95(series: pd.Series) -> tuple[float, float, float]:
    """میانگین و بازهٔ اطمینان ۹۵٪ با توزیع t (نمونهٔ کوچک، n=۱۰ seed)."""
    n = len(series)
    m = series.mean()
    if n < 2:
        return m, m, m
    se = series.std(ddof=1) / np.sqrt(n)
    h = se * stats.t.ppf(0.975, n - 1)
    return m, m - h, m + h


def main() -> None:
    fix_console_encoding()
    TABLES_DIR.mkdir(parents=True, exist_ok=True)

    all_rows = []
    seed_rows = []
    lambda_dirs = sorted(OUT_ROOT.glob("lambda_*"), key=lambda p: float(p.name.split("_")[1]))
    if not lambda_dirs:
        raise FileNotFoundError(f"هیچ خروجی‌ای در {OUT_ROOT} نیست — ابتدا `make run` را اجرا کن.")

    for lam_dir in lambda_dirs:
        lam = float(lam_dir.name.split("_")[1])
        for seed_dir in sorted(lam_dir.glob("seed_*"), key=lambda p: int(p.name.split("_")[1])):
            seed = int(seed_dir.name.split("_")[1])
            tripinfo = seed_dir / "tripinfo.xml"
            if not tripinfo.exists():
                continue
            rows = parse_one_tripinfo(tripinfo, lam, seed)
            all_rows.extend(rows)
            df_run = pd.DataFrame(rows)
            n_collisions = count_collisions(seed_dir / "stats.xml")
            seed_rows.append({
                "lambda": lam, "seed": seed,
                "n_vehicles": len(df_run),
                "mean_duration_s": df_run["duration"].mean(),
                "mean_timeloss_s": df_run["timeLoss"].mean(),
                "mean_waiting_s": df_run["waitingTime"].mean(),
                "p95_timeloss_s": df_run["timeLoss"].quantile(0.95),
                "n_collisions": n_collisions,
            })

    df_all = pd.DataFrame(all_rows)
    df_all.to_parquet(TABLES_DIR / "s0_multirun_tripinfo.parquet", index=False)

    df_seed = pd.DataFrame(seed_rows)
    df_seed.to_csv(TABLES_DIR / "s0_seed_summary.csv", index=False)
    df_seed.to_parquet(TABLES_DIR / "s0_seed_summary.parquet", index=False)

    lambda_rows = []
    for lam, grp in df_seed.groupby("lambda"):
        for metric in ("mean_duration_s", "mean_timeloss_s", "mean_waiting_s", "p95_timeloss_s", "n_collisions"):
            m, lo, hi = ci95(grp[metric])
            lambda_rows.append({"lambda": lam, "metric": metric, "mean": m, "ci95_lo": lo, "ci95_hi": hi,
                                 "n_seeds": len(grp)})
    df_lambda = pd.DataFrame(lambda_rows)
    df_lambda.to_csv(TABLES_DIR / "s0_lambda_summary.csv", index=False)
    df_lambda.to_parquet(TABLES_DIR / "s0_lambda_summary.parquet", index=False)

    # خلاصهٔ تفکیک‌شده به تفکیک پا + نوع وسیله، فقط برای λ=۱.۰ (مبنا) — برای مقایسه با فاز ۱-۲
    base = df_all[df_all["lambda"] == 1.0]
    by_approach = (
        base.groupby("approach")
        .agg(n_vehicles=("id", "count"), mean_duration_s=("duration", "mean"),
             mean_timeloss_s=("timeLoss", "mean"), mean_waiting_s=("waitingTime", "mean"),
             mean_route_length_m=("routeLength", "mean"))
        .reset_index()
    )
    total_row = pd.DataFrame([{
        "approach": "کل (all)", "n_vehicles": len(base),
        "mean_duration_s": base["duration"].mean(), "mean_timeloss_s": base["timeLoss"].mean(),
        "mean_waiting_s": base["waitingTime"].mean(), "mean_route_length_m": base["routeLength"].mean(),
    }])
    by_approach = pd.concat([by_approach, total_row], ignore_index=True)
    by_approach.to_csv(TABLES_DIR / "s0_kpi_summary.csv", index=False)
    by_approach.to_parquet(TABLES_DIR / "s0_kpi_summary.parquet", index=False)

    by_vtype = (
        base.groupby("vType")
        .agg(n_vehicles=("id", "count"), share=("id", lambda s: len(s) / len(base)),
             mean_duration_s=("duration", "mean"), mean_timeloss_s=("timeLoss", "mean"))
        .reset_index().sort_values("n_vehicles", ascending=False)
    )
    by_vtype.to_csv(TABLES_DIR / "s0_kpi_by_vtype.csv", index=False)
    by_vtype.to_parquet(TABLES_DIR / "s0_kpi_by_vtype.parquet", index=False)

    print(f"[ok] {len(df_all)} رکورد وسیله از {len(seed_rows)} اجرا پردازش شد.")
    print(df_lambda[df_lambda["metric"] == "mean_timeloss_s"].to_string(index=False))
    print(f"[ok] نوشته شد: {TABLES_DIR / 's0_lambda_summary.csv'}")


if __name__ == "__main__":
    main()
