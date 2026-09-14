#!/usr/bin/env python
"""
فاز ۳-۴ — اجرای چند-λ × چند-seed برای همهٔ سناریوهای «built» در config/scenarios.yml.

طبق قاعدهٔ سخت ۵ CLAUDE.md: «هیچ مقایسهٔ سناریویی با یک اجرا گزارش نشود؛
حداقل ۱۰ seed برای هر سناریو؛ گزارش میانگین ± فاصلهٔ اطمینان ۹۵٪.» این اسکریپت
هر «نسخهٔ کنترلی» (control_variant) هر سناریوی status=built را در ۵ سطح تقاضا
(λ ∈ {۰.۶..۱.۴}) × ۱۰ seed مستقل اجرا می‌کند. تقاضا (routes.rou.xml) به ازای
هر (سناریو, λ, seed) دوباره با jtrrouter تولید می‌شود؛ چون توپولوژی یال/خط/
اتصالات میان سناریوها یکسان است (فقط نوع گره‌ها/منطق چراغ تغییر می‌کند)، تقاضای
تولیدشده با seed یکسان میان سناریوها قابل‌مقایسه (apples-to-apples) است.

خروجی خام هر اجرا در <out_dir از scenarios.yml>/lambda_*/seed_*/ (در .gitignore)
ذخیره می‌شود؛ src/05_extract_kpis.py این‌ها را به جدول خلاصه تبدیل می‌کند.

اجرا: `make run` (چند دقیقه طول می‌کشد)
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
ASSUMPTIONS = ROOT / "config" / "assumptions.yml"
VTYPES_CFG = ROOT / "config" / "vtypes.yml"
SCENARIOS_CFG = ROOT / "config" / "scenarios.yml"


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


def run_one(build_demand, assumptions, vcfg, *, net_file: pathlib.Path, lambda_scale: float,
            seed: int, out_dir: pathlib.Path, skip_if_done: bool = True,
            blocked_edges: frozenset = frozenset()) -> bool:
    """اجرای یک ترکیب (شبکه, λ, seed). اگر skip_if_done و tripinfo.xml از قبل
    موجود باشد، دوباره اجرا نمی‌کند (اجرای resume-پذیر برای پایپ‌لاین‌های
    بزرگ چندسناریویی) — بازمی‌گرداند: True اگر واقعاً اجرا شد، False اگر رد شد.

    نکتهٔ حیاتی: تقاضا همیشه روی *همان* net_file این اجرا تولید می‌شود (نه
    شبکهٔ مبنای S0) — وگرنه برای سناریوهایی که اتصالی حذف/اضافه کرده‌اند
    (مثل S2)، jtrrouter مسیرهایی می‌سازد که با توپولوژی واقعی سازگار نیست."""
    out_dir.mkdir(parents=True, exist_ok=True)
    if skip_if_done and (out_dir / "tripinfo.xml").exists():
        return False
    routes_path = out_dir / "routes.rou.xml"

    build_demand.generate_demand(
        assumptions, vcfg,
        lambda_scale=lambda_scale, seed=seed,
        net_file=net_file, blocked_edges=blocked_edges,
        routes_path=routes_path,
    )

    sumo = SUMO_HOME / "bin" / "sumo.exe"
    cmd = [
        str(sumo),
        "-n", str(net_file),
        "-r", str(routes_path),
        "-b", "0", "-e", "4500",
        "--tripinfo-output", str(out_dir / "tripinfo.xml"),
        "--summary-output", str(out_dir / "summary.xml"),
        "--statistic-output", str(out_dir / "stats.xml"),
        "--queue-output", str(out_dir / "queue.xml"),
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
        raise RuntimeError(f"sumo failed for net={net_file.name} lambda={lambda_scale} "
                            f"seed={seed}:\n{result.stderr[-2000:]}")
    return True


def main() -> None:
    fix_console_encoding()
    with open(ASSUMPTIONS, "r", encoding="utf-8") as f:
        assumptions = yaml.safe_load(f)
    with open(VTYPES_CFG, "r", encoding="utf-8") as f:
        vcfg = yaml.safe_load(f)
    with open(SCENARIOS_CFG, "r", encoding="utf-8") as f:
        scen_cfg = yaml.safe_load(f)["scenarios"]

    lambdas = assumptions["experiment_design"]["demand_scale_levels"]["value"]
    n_seeds = assumptions["experiment_design"]["n_seeds_per_condition"]["value"]
    build_demand = _load_demand_module()

    jobs = []  # (label, net_file, out_dir, blocked_edges)
    for scen_id, scen in scen_cfg.items():
        if scen.get("status") != "built":
            continue
        blocked = frozenset(scen.get("demand_blocked_edges", []))
        for variant_id, variant in scen["control_variants"].items():
            label = f"{scen_id}/{variant_id}"
            net_file = ROOT / variant["net_file"]
            out_dir = ROOT / variant["out_dir"]
            jobs.append((label, net_file, out_dir, blocked))

    total = len(jobs) * len(lambdas) * n_seeds
    done = 0
    t0 = time.time()
    for label, net_file, out_root, blocked in jobs:
        if not net_file.exists():
            raise FileNotFoundError(f"شبکهٔ {label} یافت نشد: {net_file} — ابتدا اسکریپت ساخت "
                                     f"شبکهٔ آن سناریو را اجرا کن.")
        for lam in lambdas:
            for seed in range(1, n_seeds + 1):
                out_dir = out_root / f"lambda_{lam}" / f"seed_{seed}"
                ran = run_one(build_demand, assumptions, vcfg, net_file=net_file,
                              lambda_scale=lam, seed=seed, out_dir=out_dir,
                              blocked_edges=blocked)
                done += 1
                tag = "done" if ran else "skip (exists)"
                print(f"[{done}/{total}] {label} lambda={lam} seed={seed} {tag} "
                      f"({time.time()-t0:.0f}s elapsed)")

    print(f"[ok] {total} اجرا در {len(jobs)} نسخهٔ سناریو کامل شد در {time.time()-t0:.0f} ثانیه.")


if __name__ == "__main__":
    main()
