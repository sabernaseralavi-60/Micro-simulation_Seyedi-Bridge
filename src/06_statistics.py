#!/usr/bin/env python
"""
فاز ۴ — مقایسهٔ آماری زوجی سناریوها روی seedهای مشترک (CLAUDE.md فاز ۴: «مقایسهٔ
زوجی سناریوها روی seedهای مشترک، آزمون معنی‌داری، و اندازهٔ اثر — نه صرفاً
درصد تفاوت میانگین‌ها»).

چون هر seed یکسان در همهٔ سناریوها همان تقاضای پایه (jtrrouter با همان seed،
روی توپولوژی یال/خط یکسان) را تولید می‌کند، seedها میان سناریوها جفت‌شونده‌اند؛
از آزمون t زوجی (paired t-test) و Cohen's d_z (اندازهٔ اثر نمونهٔ زوجی) استفاده
می‌شود، نه آزمون مستقل.

مرجع مقایسه: سناریوی is_reference=true در config/scenarios.yml (فعلاً S0).
هر نسخهٔ کنترلی غیرمرجع (مثلاً s1_fixed، s1_actuated) به‌ازای هر λ و هر متریک
با مرجع مقایسه می‌شود.

ورودی: outputs/tables/all_scenarios_seed_summary.csv (از src/05_extract_kpis.py)
خروجی: outputs/tables/scenario_comparison.csv

اجرا: `make statistics`
"""
from __future__ import annotations

import pathlib
import sys

import numpy as np
import pandas as pd
import yaml
from scipy import stats

ROOT = pathlib.Path(__file__).resolve().parents[1]
TABLES_DIR = ROOT / "outputs" / "tables"
SCENARIOS_CFG = ROOT / "config" / "scenarios.yml"

METRICS = ["mean_timeloss_s", "mean_waiting_s", "p95_timeloss_s", "n_collisions", "max_queue_length_m"]


def fix_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def paired_cohens_dz(a: np.ndarray, b: np.ndarray) -> float:
    """Cohen's d_z برای نمونهٔ زوجی: میانگین تفاوت / انحراف‌معیار تفاوت."""
    diff = a - b
    sd = diff.std(ddof=1)
    if sd < 1e-9:
        return 0.0
    return diff.mean() / sd


def find_reference_prefix(scen_cfg: dict) -> str:
    for scen_id, scen in scen_cfg.items():
        if scen.get("is_reference"):
            variants = scen["control_variants"]
            first = next(iter(variants.values()))
            return first["table_prefix"]
    raise ValueError("هیچ سناریویی با is_reference: true در scenarios.yml نیست.")


def compare(df: pd.DataFrame, ref_prefix: str) -> pd.DataFrame:
    rows = []
    scenarios = [s for s in df["scenario"].unique() if s != ref_prefix]
    for scen in scenarios:
        for lam in sorted(df["lambda"].unique()):
            df_ref = df[(df["scenario"] == ref_prefix) & (df["lambda"] == lam)].set_index("seed")
            df_scn = df[(df["scenario"] == scen) & (df["lambda"] == lam)].set_index("seed")
            shared_seeds = sorted(set(df_ref.index) & set(df_scn.index))
            if len(shared_seeds) < 2:
                continue
            for metric in METRICS:
                a = df_scn.loc[shared_seeds, metric].to_numpy(dtype=float)
                b = df_ref.loc[shared_seeds, metric].to_numpy(dtype=float)
                valid = ~(np.isnan(a) | np.isnan(b))
                a, b = a[valid], b[valid]
                if len(a) < 2:
                    continue
                t_stat, p_val = stats.ttest_rel(a, b)
                dz = paired_cohens_dz(a, b)
                rows.append({
                    "scenario": scen, "reference": ref_prefix, "lambda": lam, "metric": metric,
                    "mean_scenario": a.mean(), "mean_reference": b.mean(),
                    "mean_diff": a.mean() - b.mean(),
                    "pct_diff": 100.0 * (a.mean() - b.mean()) / b.mean() if b.mean() != 0 else np.nan,
                    "paired_t": t_stat, "p_value": p_val, "cohens_dz": dz,
                    "n_seeds": len(a), "significant_p05": bool(p_val < 0.05),
                })
    return pd.DataFrame(rows)


def main() -> None:
    fix_console_encoding()
    seed_summary_path = TABLES_DIR / "all_scenarios_seed_summary.csv"
    if not seed_summary_path.exists():
        raise FileNotFoundError(f"{seed_summary_path} یافت نشد — ابتدا `make analyze` را اجرا کن.")
    df = pd.read_csv(seed_summary_path)

    with open(SCENARIOS_CFG, "r", encoding="utf-8") as f:
        scen_cfg = yaml.safe_load(f)["scenarios"]
    ref_prefix = find_reference_prefix(scen_cfg)

    result = compare(df, ref_prefix)
    if result.empty:
        print("[warn] هیچ مقایسه‌ای ممکن نبود — احتمالاً فقط سناریوی مرجع اجرا شده است.")
        return

    result.to_csv(TABLES_DIR / "scenario_comparison.csv", index=False)
    result.to_parquet(TABLES_DIR / "scenario_comparison.parquet", index=False)

    print(f"[ok] نوشته شد: {TABLES_DIR / 'scenario_comparison.csv'} ({len(result)} ردیف مقایسه)")
    key = result[result["metric"] == "mean_timeloss_s"][
        ["scenario", "lambda", "mean_scenario", "mean_reference", "pct_diff", "p_value", "cohens_dz",
         "significant_p05"]
    ]
    print(key.to_string(index=False))


if __name__ == "__main__":
    main()
