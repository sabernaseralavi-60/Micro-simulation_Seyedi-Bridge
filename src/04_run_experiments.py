#!/usr/bin/env python
"""
فاز ۱ — اجرای سناریوی S0 (Walking Skeleton، تک-seed).

هشدار: این اجرا صرفاً برای آزمودن خط لولهٔ end-to-end است. طبق قاعدهٔ سخت ۵
CLAUDE.md، هیچ مقایسهٔ سناریویی نباید با یک اجرا گزارش شود — چند-seed در فاز ۳
اضافه می‌شود (src/04_run_experiments.py در آن فاز به یک runner موازیِ
چند-سناریو/چند-seed ارتقا می‌یابد).

اجرا: `make run`
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SUMO_HOME = ROOT / ".venv" / "Lib" / "site-packages" / "sumo"
SCENARIO_DIR = ROOT / "scenarios" / "S0_baseline"
OUT_DIR = SCENARIO_DIR / "out"


def fix_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def main() -> None:
    fix_console_encoding()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sumo = SUMO_HOME / "bin" / "sumo.exe"
    cmd = [
        str(sumo),
        "-c", str(SCENARIO_DIR / "run.sumocfg"),
        "--tripinfo-output", str(OUT_DIR / "tripinfo.xml"),
        "--summary-output", str(OUT_DIR / "summary.xml"),
        "--statistic-output", str(OUT_DIR / "stats.xml"),
        "--duration-log.statistics",
        "--device.ssm.probability", "1",
        "--device.ssm.measures", "TTC DRAC PET",
        "--device.ssm.file", str(OUT_DIR / "ssm.xml"),
        "--seed", "42",
        "--no-warnings", "true",
    ]
    print("[run]", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=str(SCENARIO_DIR))
    print(f"[ok] خروجی‌ها در {OUT_DIR}")


if __name__ == "__main__":
    main()
