#!/usr/bin/env python
"""
فاز ۳ — اجرای چند-λ × چند-seed سناریوی S0 (Do-Nothing).

طبق قاعدهٔ سخت ۵ CLAUDE.md: «هیچ مقایسهٔ سناریویی با یک اجرا گزارش نشود؛
حداقل ۱۰ seed برای هر سناریو؛ گزارش میانگین ± فاصلهٔ اطمینان ۹۵٪.» این اسکریپت
دقیقاً همین را برای S0 در ۵ سطح تقاضا (λ ∈ {۰.۶..۱.۴}) اجرا می‌کند: به ازای هر
λ، ده seed مستقل (هم برای jtrrouter و هم sumo) اجرا می‌شود — نتیجه: ۵۰ اجرای
کامل. خروجی خام هر اجرا در scenarios/S0_baseline/out/lambda_*/seed_*/ (در
.gitignore) ذخیره می‌شود؛ src/05_extract_kpis.py این‌ها را به یک جدول خلاصه
تبدیل می‌کند.

اجرا: `make run` (ممکن است چند دقیقه طول بکشد؛ ۵۰ اجرای کوتاه SUMO)
"""
from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import sys
import time

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
SUMO_HOME = ROOT / ".venv" / "Lib" / "site-packages" / "sumo"
SCENARIO_DIR = ROOT / "scenarios" / "S0_baseline"
ASSUMPTIONS = ROOT / "config" / "assumptions.yml"
VTYPES_CFG = ROOT / "config" / "vtypes.yml"
DEMAND_DIR = ROOT / "demand"


def fix_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def _load_demand_module():
    """وارد کردن پویا از src/03_build_demand.py (نام فایل با رقم شروع می‌شود)."""
    spec = importlib.util.spec_from_file_location("build_demand", ROOT / "src" / "03_build_demand.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_one(build_demand, assumptions, vcfg, *, lambda_scale: float, seed: int,
            out_dir: pathlib.Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    routes_path = out_dir / "routes.rou.xml"

    build_demand.generate_demand(
        assumptions, vcfg,
        lambda_scale=lambda_scale, seed=seed,
        routes_path=routes_path,
    )

    sumo = SUMO_HOME / "bin" / "sumo.exe"
    cmd = [
        str(sumo),
        "-n", str(ROOT / "network" / "seyedi.net.xml"),
        "-r", str(routes_path),
        "-b", "0", "-e", "4500",
        "--tripinfo-output", str(out_dir / "tripinfo.xml"),
        "--summary-output", str(out_dir / "summary.xml"),
        "--statistic-output", str(out_dir / "stats.xml"),
        "--duration-log.statistics",
        "--device.ssm.probability", "1",
        "--device.ssm.measures", "TTC DRAC PET",
        "--device.ssm.file", str(out_dir / "ssm.xml"),
        "--lateral-resolution", "0.8",
        "--collision.action", "warn",
        "--seed", str(seed),
        "--no-warnings", "true",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"sumo failed for lambda={lambda_scale} seed={seed}:\n{result.stderr[-2000:]}")


def main() -> None:
    fix_console_encoding()
    with open(ASSUMPTIONS, "r", encoding="utf-8") as f:
        assumptions = yaml.safe_load(f)
    with open(VTYPES_CFG, "r", encoding="utf-8") as f:
        vcfg = yaml.safe_load(f)

    lambdas = assumptions["experiment_design"]["demand_scale_levels"]["value"]
    n_seeds = assumptions["experiment_design"]["n_seeds_per_condition"]["value"]
    build_demand = _load_demand_module()

    total = len(lambdas) * n_seeds
    done = 0
    t0 = time.time()
    for lam in lambdas:
        for seed in range(1, n_seeds + 1):
            out_dir = SCENARIO_DIR / "out" / f"lambda_{lam}" / f"seed_{seed}"
            run_one(build_demand, assumptions, vcfg, lambda_scale=lam, seed=seed, out_dir=out_dir)
            done += 1
            print(f"[{done}/{total}] lambda={lam} seed={seed} done ({time.time()-t0:.0f}s elapsed)")

    print(f"[ok] {total} اجرا کامل شد در {time.time()-t0:.0f} ثانیه.")


if __name__ == "__main__":
    main()
