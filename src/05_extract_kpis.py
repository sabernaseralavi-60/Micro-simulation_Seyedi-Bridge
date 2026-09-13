#!/usr/bin/env python
"""
فاز ۱ — استخراج KPI از خروجی خام SUMO (tripinfo.xml) به خلاصهٔ parquet/csv.

طبق اصل «یک‌بار محاسبه، چندبار گزارش» (CLAUDE.md فاز ۵)، فایل‌های .qmd هرگز
XML خام نمی‌خوانند؛ فقط خروجی‌های این اسکریپت در outputs/tables را می‌خوانند.

اجرا: `make analyze`
"""
from __future__ import annotations

import pathlib
import sys
import xml.etree.ElementTree as ET

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
TRIPINFO = ROOT / "scenarios" / "S0_baseline" / "out" / "tripinfo.xml"
TABLES_DIR = ROOT / "outputs" / "tables"


def fix_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def parse_tripinfo(path: pathlib.Path) -> pd.DataFrame:
    rows = []
    for _, elem in ET.iterparse(str(path), events=("end",)):
        if elem.tag == "tripinfo":
            leg = "west" if elem.get("id", "").startswith("from_west") else \
                  "east" if elem.get("id", "").startswith("from_east") else \
                  "north" if elem.get("id", "").startswith("from_north") else \
                  "south" if elem.get("id", "").startswith("from_south") else "other"
            rows.append({
                "id": elem.get("id"),
                "approach": leg,
                "vType": elem.get("vType"),
                "depart": float(elem.get("depart")),
                "duration": float(elem.get("duration")),
                "routeLength": float(elem.get("routeLength")),
                "waitingTime": float(elem.get("waitingTime")),
                "timeLoss": float(elem.get("timeLoss")),
                "departDelay": float(elem.get("departDelay")),
            })
            elem.clear()
    return pd.DataFrame(rows)


def main() -> None:
    fix_console_encoding()
    if not TRIPINFO.exists():
        raise FileNotFoundError(f"{TRIPINFO} پیدا نشد — ابتدا `make run` را اجرا کن.")

    df = parse_tripinfo(TRIPINFO)
    TABLES_DIR.mkdir(parents=True, exist_ok=True)

    df.to_parquet(TABLES_DIR / "s0_tripinfo.parquet", index=False)
    df.to_csv(TABLES_DIR / "s0_tripinfo.csv", index=False)

    summary = (
        df.groupby("approach")
        .agg(
            n_vehicles=("id", "count"),
            mean_duration_s=("duration", "mean"),
            mean_timeloss_s=("timeLoss", "mean"),
            mean_waiting_s=("waitingTime", "mean"),
            mean_route_length_m=("routeLength", "mean"),
        )
        .reset_index()
    )
    total_row = pd.DataFrame([{
        "approach": "کل (all)",
        "n_vehicles": len(df),
        "mean_duration_s": df["duration"].mean(),
        "mean_timeloss_s": df["timeLoss"].mean(),
        "mean_waiting_s": df["waitingTime"].mean(),
        "mean_route_length_m": df["routeLength"].mean(),
    }])
    summary = pd.concat([summary, total_row], ignore_index=True)
    summary.to_csv(TABLES_DIR / "s0_kpi_summary.csv", index=False)
    summary.to_parquet(TABLES_DIR / "s0_kpi_summary.parquet", index=False)

    by_vtype = (
        df.groupby("vType")
        .agg(
            n_vehicles=("id", "count"),
            share=("id", lambda s: len(s) / len(df)),
            mean_duration_s=("duration", "mean"),
            mean_timeloss_s=("timeLoss", "mean"),
        )
        .reset_index()
        .sort_values("n_vehicles", ascending=False)
    )
    by_vtype.to_csv(TABLES_DIR / "s0_kpi_by_vtype.csv", index=False)
    by_vtype.to_parquet(TABLES_DIR / "s0_kpi_by_vtype.parquet", index=False)

    print(f"[ok] {len(df)} tripinfo پردازش شد.")
    print(summary.to_string(index=False))
    print(f"[ok] نوشته شد: {TABLES_DIR / 's0_kpi_summary.csv'}")


if __name__ == "__main__":
    main()
