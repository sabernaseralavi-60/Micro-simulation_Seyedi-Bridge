#!/usr/bin/env python
"""
فاز ۴ — محاسبهٔ طول سیکل بهینهٔ چراغ (روش وبستر) برای سناریوی S1.

طبق config/assumptions.yml -> signal_design_S1: زیر پل به‌جای یک تقاطع واحد،
زنجیره‌ای از گره‌های ادغام مستقل است (رجوع به یادداشت آن بخش برای توجیه کامل
تصمیم). این اسکریپت طول سیکل مشترک (C0) و نسبت سبز دو گروه حرکتی رقابتی را
یک‌بار، برای تقاضای طراحی λ=۱.۰، با فرمول وبستر محاسبه می‌کند:

    y_i = q_i / (s × lanes_i)          نسبت جریان بحرانی هر فاز
    Y = Σ y_i
    C0 = (1.5·L + 5) / (1 - Y)         سیکل بهینهٔ وبستر (L = مجموع تلف‌شده)
    g_i = (y_i / Y) × (C0 − L)         سبز مؤثر هر فاز

دو گروه حرکتی رقابتی زیر پل:
  فاز A — عبوری/راست‌گرد بلوار سیدی (هم‌سطح، شمال↔جنوب)
  فاز B — گردش‌های ورودی از عرشهٔ پل به زیرپل (رمپ‌های حلقوی شرق/غرب)

خروجی: config/signal_timing_S1.yml (تکرارپذیر، فقط از assumptions.yml خوانده
می‌شود) — توسط scenarios/S1_signal/build_network.py مصرف می‌شود.

اجرا: `make webster-timing` یا مستقیماً `python src/08_webster_timing.py`
"""
from __future__ import annotations

import pathlib
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSUMPTIONS = ROOT / "config" / "assumptions.yml"
OUT_FILE = ROOT / "config" / "signal_timing_S1.yml"


def fix_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def webster(assumptions: dict) -> dict:
    sd = assumptions["signal_design_S1"]
    demand = assumptions["demand_baseline_phase1"]
    turns = assumptions["traffic_control"]["turn_ratio_baseline"]["value"]
    underpass_lanes = assumptions["bridge_geometry"]["underpass_lanes_per_direction"]["value"]

    s = sd["saturation_flow_per_lane"]["value"]
    L_per_phase = sd["lost_time_per_phase"]["value"]
    ramp_lanes = sd["turning_movement_lanes"]["value"]
    lam = sd["design_demand_lambda"]["value"]
    bounds = sd["cycle_length_bounds"]["value"]

    n_phases = 2
    L = L_per_phase * n_phases

    # فاز A: عبوری همسطح شمال-جنوب (بلوار سیدی زیر پل)
    q_a = (demand["entry_volume_north"]["value"] + demand["entry_volume_south"]["value"]) * lam
    cap_a = s * underpass_lanes
    y_a = q_a / cap_a

    # فاز B: حرکات گردشی از عرشهٔ پل (شرق+غرب) که وارد زیرپل می‌شوند (سهم چپ+راست
    # از ترکیب گردش پایه؛ عبوری مستقیم روی خود عرشه می‌ماند و وارد این تعارض نمی‌شود)
    turning_share = (turns["left"] + turns["right"]) / 100.0
    q_b = (demand["entry_volume_west"]["value"] + demand["entry_volume_east"]["value"]) * lam * turning_share
    cap_b = s * ramp_lanes
    y_b = q_b / cap_b

    Y = y_a + y_b
    saturated = Y >= 0.95
    if Y < 0.95:
        c0 = (1.5 * L + 5) / (1 - Y)
    else:
        c0 = bounds["max"]  # نمی‌توان بهینه محاسبه کرد؛ به سقف مهندسی برمی‌گردیم

    c0_clamped = min(max(c0, bounds["min"]), bounds["max"])
    clamped = abs(c0_clamped - c0) > 1e-6

    g_total = c0_clamped - L
    g_a = max(g_total * (y_a / Y), 5.0) if Y > 0 else g_total / 2
    g_b = max(g_total - g_a, 5.0)

    return {
        "method": "webster",
        "design_lambda": lam,
        "inputs": {
            "saturation_flow_per_lane": s,
            "lost_time_per_phase": L_per_phase,
            "underpass_lanes": underpass_lanes,
            "ramp_lanes": ramp_lanes,
            "q_phase_A_veh_per_hour": round(q_a, 1),
            "q_phase_B_veh_per_hour": round(q_b, 1),
        },
        "critical_flow_ratios": {"y_A": round(y_a, 4), "y_B": round(y_b, 4), "Y": round(Y, 4)},
        "saturated_at_design_demand": saturated,
        "cycle_length_s": {
            "webster_optimum_raw": round(c0, 1),
            "clamped_to_engineering_bounds": clamped,
            "final_used_s": round(c0_clamped, 1),
        },
        "green_split_s": {"phase_A_ns_through": round(g_a, 1), "phase_B_bridge_turns": round(g_b, 1)},
        "total_lost_time_s": L,
    }


def main() -> None:
    fix_console_encoding()
    with open(ASSUMPTIONS, "r", encoding="utf-8") as f:
        assumptions = yaml.safe_load(f)

    result = webster(assumptions)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        yaml.dump(result, f, allow_unicode=True, sort_keys=False)

    print(f"[ok] Y (نسبت جریان بحرانی کل) = {result['critical_flow_ratios']['Y']}")
    if result["saturated_at_design_demand"]:
        print("[warn] Y >= 0.95 در تقاضای طراحی — زیرپل حتی با چراغ در وضع نزدیک/فراتر از "
              "اشباع است؛ سیکل به سقف مهندسی (max) محدود شد.")
    print(f"[ok] طول سیکل نهایی = {result['cycle_length_s']['final_used_s']} ثانیه "
          f"(خام وبستر: {result['cycle_length_s']['webster_optimum_raw']})")
    print(f"[ok] سبز فاز A/B = {result['green_split_s']['phase_A_ns_through']} / "
          f"{result['green_split_s']['phase_B_bridge_turns']} ثانیه")
    print(f"[ok] نوشته شد: {OUT_FILE}")


if __name__ == "__main__":
    main()
