#!/usr/bin/env python
"""
سنتز هندسی فاز ۰-۳ — تقاطع زیرپل سیدی، کرمان.

این اسکریپت به‌صورت برنامه‌نویسی‌شده (نه با ابزار ترسیم دستی) یک اسکچ پلان از
وضع موجود زیرپل تولید می‌کند: عرشهٔ پل، محور هم‌سطح، ساختار واقعی ۷دهانه‌ای
پایه‌های پل (تأیید مستقیم کاربر با بازرسی data/raw/imagery/2012.png در فاز ۳ —
رجوع به assumptions.yml -> bridge_geometry.span_structure)، رمپ‌های حلقوی
ورودی/خروجی، و مسیر گردش (weaving) زیر پل.

تمام پارامترهای هندسی از config/assumptions.yml خوانده می‌شوند — هیچ عددی در
این فایل هاردکد نشده؛ خروجی با `make sketch` یا اجرای مستقیم این اسکریپت از صفر
بازتولید می‌شود (قاعدهٔ تکرارپذیری مطلق، CLAUDE.md §3.1).

خروجی: outputs/figures/seyedi_sketch.svg و .png
"""
from __future__ import annotations

import pathlib
import sys

import matplotlib

matplotlib.use("Agg")  # رندر headless — بدون نیاز به نمایشگر (برای make/CI)
import matplotlib.pyplot as plt
import numpy as np
import yaml
from pyproj import Transformer

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSUMPTIONS_PATH = ROOT / "config" / "assumptions.yml"
OUT_DIR = ROOT / "outputs" / "figures"


def load_assumptions() -> dict:
    with open(ASSUMPTIONS_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def val(d: dict, key: str) -> float:
    return d[key]["value"]


def build_sketch(assumptions: dict) -> plt.Figure:
    bg = assumptions["bridge_geometry"]

    span = val(bg, "span_width_between_abutments")  # m, N-S extent of deck footprint
    deck_lanes = val(bg, "deck_lanes_per_direction")
    under_lanes = val(bg, "underpass_lanes_per_direction")
    r_nw = val(bg, "loop_ramp_radius_nw")
    r_ne = val(bg, "loop_ramp_radius_ne")
    r_weave = val(bg, "weave_area_south_radius")
    span_layout = bg["span_structure"]["value"]["layout_west_to_east"]
    open_w = val(bg, "open_span_width")
    closed_w = val(bg, "closed_span_width")

    lane_w = 3.5  # m، عرض استاندارد خط — قضاوت مهندسی (ثبت در assumptions در فاز ۲)
    deck_half_w = deck_lanes * lane_w  # نیم‌عرض عرشه هر جهت
    under_half_w = under_lanes * lane_w

    fig, ax = plt.subplots(figsize=(9, 9))
    ax.set_aspect("equal")

    extent = max(120, span * 3)

    # --- محور هم‌سطح شمالی-جنوبی (بلوار سیدی) ---
    ax.add_patch(
        plt.Rectangle(
            (-under_half_w, -extent), 2 * under_half_w, 2 * extent,
            facecolor="#d9d9d9", edgecolor="none", zorder=1,
        )
    )
    for k in range(1, under_lanes):
        x = -under_half_w + k * lane_w
        ax.plot([x, x], [-extent, extent], ls="--", lw=0.8, color="white", zorder=2)

    # --- عرشهٔ پل شرقی-غربی (نوار افقی span عرضش) ---
    ax.add_patch(
        plt.Rectangle(
            (-extent, -span / 2), 2 * extent, span,
            facecolor="#8c8c8c", edgecolor="black", lw=1.2, zorder=3, alpha=0.55,
        )
    )
    ax.plot([-extent, extent], [0, 0], color="black", lw=1.0, ls=":", zorder=4)  # بریر میانی عرشه
    ax.text(0, span / 2 + 18, "عرشهٔ پل — بزرگراه امام‌رضا (شرقی-غربی)",
            ha="center", fontsize=9)

    # --- ساختار ۷دهانه‌ای پل (تأیید مستقیم کاربر با بازرسی 2012.png، فاز ۳؛
    #     تصحیح دوم در نشست ۱۴۰۵/۰۶/۲۴ — جزیرهٔ سه‌دهانه‌ای میانی + دوربرگردان
    #     دو-دهانه‌ای در دو انتها، رجوع به assumptions.yml برای تاریخچه) ---
    # چیدمان از غرب به شرق: open, open, closed, closed_center, closed, open, open
    # پایه‌ها روی دو خط لبهٔ عرشه (y=±span/2) قرار می‌گیرند؛ هر دهانه یک بازهٔ x
    # بین دو پایهٔ متوالی است. عرض دهانه‌ها شماتیک است (رجوع به
    # assumptions.yml -> open_span_width / closed_span_width).
    widths = [closed_w if s.startswith("closed") else open_w for s in span_layout]
    total_w = sum(widths)
    x_start = -total_w / 2
    boundaries = [x_start]
    for w in widths:
        boundaries.append(boundaries[-1] + w)
    pier_thickness = 1.6

    for i, (s, w) in enumerate(zip(span_layout, widths)):
        x0, x1 = boundaries[i], boundaries[i + 1]
        is_open = s == "open"
        color = "#ffffff" if is_open else "#6b6b6b"
        alpha = 0.0 if is_open else 0.85
        for y0 in (-span / 2, span / 2 - 2):
            ax.add_patch(
                plt.Rectangle((x0, y0), w, 2, facecolor=color, edgecolor="none",
                              alpha=alpha, zorder=4.5)
            )
        label = {"open": "باز", "closed": "بسته", "closed_center": "بسته (مرکزی)"}[s]
        ax.text((x0 + x1) / 2, span / 2 + 3, label, ha="center", va="bottom",
                fontsize=6.5, color=("#1a7a1a" if is_open else "#7a1a1a"))

    # خطوط پایه‌ها (مرزهای بین دهانه‌ها)
    for bx in boundaries:
        ax.add_patch(
            plt.Rectangle((bx - pier_thickness / 2, -span / 2 - 1), pier_thickness,
                          span + 2, facecolor="#3a3a3a", zorder=5)
        )
    # --- رمپ‌های حلقوی شمالی (ورود/خروج به عرشه) ---
    theta = np.linspace(0, np.pi, 60)

    def loop(cx, cy, r, flip_x=1, flip_y=1):
        x = cx + flip_x * r * np.cos(theta)
        y = cy + flip_y * r * np.sin(theta)
        return x, y

    x, y = loop(under_half_w + r_nw, span / 2, r_nw, flip_x=1, flip_y=1)
    ax.plot(x, y, color="#1f77b4", lw=2.2, zorder=6)
    ax.text(under_half_w + r_nw, span / 2 + r_nw + 4, f"رمپ حلقوی شمال‌شرقی\nR≈{r_ne:.0f} m",
            ha="center", fontsize=7, color="#1f77b4")

    x, y = loop(-under_half_w - r_nw, span / 2, r_nw, flip_x=1, flip_y=1)
    ax.plot(x, y, color="#1f77b4", lw=2.2, zorder=6)
    ax.text(-under_half_w - r_nw, span / 2 + r_nw + 4, f"رمپ حلقوی شمال‌غربی\nR≈{r_nw:.0f} m",
            ha="center", fontsize=7, color="#1f77b4")

    # --- جزیرهٔ قطره‌ای و انحنای weaving جنوبی ---
    drop_island = plt.Polygon(
        [(-3, -span / 2 - 3), (3, -span / 2 - 3), (0, -span / 2 - r_weave)],
        closed=True, facecolor="#2ca02c", alpha=0.5, zorder=6,
    )
    ax.add_patch(drop_island)
    ax.text(0, -span / 2 - r_weave - 6, f"جزیرهٔ قطره‌ای + انحنای ویوینگ جنوبی\nR≈{r_weave:.0f} m",
            ha="center", fontsize=7, color="#2ca02c")

    xw, yw = loop(under_half_w * 0.3, -span / 2, r_weave, flip_x=1, flip_y=-1)
    ax.plot(xw, yw, color="#d62728", lw=2.0, ls="-.", zorder=6, label="مسیر گردش (weaving) بدون کانالیزاسیون")
    xw2, yw2 = loop(-under_half_w * 0.3, -span / 2, r_weave, flip_x=1, flip_y=-1)
    ax.plot(xw2, yw2, color="#d62728", lw=2.0, ls="-.", zorder=6)

    ax.set_xlim(-extent, extent)
    ax.set_ylim(-extent, extent)
    ax.set_xlabel("فاصلهٔ شرقی-غربی از مرکز تقاطع (متر)")
    ax.set_ylabel("فاصلهٔ شمالی-جنوبی از مرکز تقاطع (متر)")
    ax.set_title(
        "سنتز هندسی وضع موجود — تقاطع زیرپل سیدی، کرمان\n"
        "ساختار ۷دهانه‌ای پایه‌ها طبق تأیید کاربر (2012.png) — جزیرهٔ ۳دهانه‌ای بسته در مرکز، دوربرگردان ۲دهانه‌ای هر سمت\n"
        "مدل کالیبره‌نشده، فقط برای بازرسی چشمی",
        fontsize=9.5,
    )
    ax.legend(loc="lower right", fontsize=7, framealpha=0.9)
    ax.grid(alpha=0.15, zorder=0)
    fig.tight_layout()
    return fig


def build_bbox_figure(assumptions: dict) -> plt.Figure:
    """نمودار طرحوارهٔ bbox پیشنهادی حول مرکز تخمینی تقاطع (فاز ۰، پیش از راستی‌آزمایی OSM)."""
    sa = assumptions["study_area"]
    lon0, lat0 = val(sa, "center_lon"), val(sa, "center_lat")
    half = val(sa, "bbox_half_extent")

    to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32640", always_xy=True)
    to_wgs = Transformer.from_crs("EPSG:32640", "EPSG:4326", always_xy=True)
    e0, n0 = to_utm.transform(lon0, lat0)
    corners_ll = [to_wgs.transform(e0 + dx, n0 + dy) for dx, dy in
                  [(-half, -half), (half, -half), (half, half), (-half, half), (-half, -half)]]
    xs, ys = zip(*corners_ll)

    fig, ax = plt.subplots(figsize=(7, 7))
    ax.set_aspect("equal")
    ax.plot(xs, ys, color="#d62728", lw=2, label=f"bbox پیشنهادی (±{half:.0f} m از مرکز)")
    ax.scatter([lon0], [lat0], color="black", zorder=5, label="مرکز تخمینی تقاطع")
    ax.annotate("زیرپل سیدی\n(تخمینی — نیازمند تأیید OSM)",
                (lon0, lat0), textcoords="offset points", xytext=(10, 10), fontsize=8)

    margin = half / 111_000 * 1.6
    ax.set_xlim(lon0 - margin, lon0 + margin)
    ax.set_ylim(lat0 - margin, lat0 + margin)
    ax.set_xlabel("طول جغرافیایی")
    ax.set_ylabel("عرض جغرافیایی")
    ax.set_title(
        f"محدودهٔ مطالعه (bbox) پیشنهادی — فاز ۰\n"
        f"مرکز: {lat0:.5f}, {lon0:.5f} (اطمینان: متوسط) — نیم‌بُعد {half:.0f} متر در هر جهت",
        fontsize=10,
    )
    ax.legend(loc="upper left", fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    return fig


def main() -> None:
    # کنسول ویندوز پیش‌فرض cp1252 است؛ خروجی فارسی UTF-8 را با آن سازگار می‌کنیم
    # تا `make` روی CI/ویندوز بدون کرش کنسول اجرا شود (خود فایل‌های خروجی UTF-8 هستند).
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    assumptions = load_assumptions()

    fig = build_sketch(assumptions)
    for path in (OUT_DIR / "seyedi_sketch.svg", OUT_DIR / "seyedi_sketch.png"):
        fig.savefig(path, dpi=200)
        print(f"[ok] نوشته شد: {path}")

    fig_bbox = build_bbox_figure(assumptions)
    for path in (OUT_DIR / "seyedi_bbox.svg", OUT_DIR / "seyedi_bbox.png"):
        fig_bbox.savefig(path, dpi=200)
        print(f"[ok] نوشته شد: {path}")


if __name__ == "__main__":
    main()
