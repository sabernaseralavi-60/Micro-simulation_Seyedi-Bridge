#!/usr/bin/env python
"""
فاز ۱ — ساخت شبکهٔ SUMO از OSM و بازرسی چشمی جدایی تراز پل/زیرپل.

مراحل:
1. دانلود OSM برای bbox (اگر از قبل موجود نباشد) با osmGet.py.
2. اجرای netconvert طبق دستور CLAUDE.md §۴ فاز ۱.
3. رسم شبکه با تفکیک رنگ بر اساس ارتفاع (z) برای تأیید عدم چسبیدن تراز پل به زیرپل —
   خروجی الزامی طبق «تعریف تمام‌شده» (CLAUDE.md §۷).

اجرا: `make network` یا مستقیماً `python src/01_build_network.py`
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import sumolib
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
SUMO_HOME = ROOT / ".venv" / "Lib" / "site-packages" / "sumo"
OSM_FILE = ROOT / "data" / "raw" / "osm" / "seyedi_bbox.osm.xml"
NET_FILE = ROOT / "network" / "seyedi.net.xml"
PLAIN_PREFIX = ROOT / "network" / "plain" / "seyedi"
TYPEMAP = ROOT / "config" / "typemap" / "urban_ir.typ.xml"
ASSUMPTIONS = ROOT / "config" / "assumptions.yml"
FIG_DIR = ROOT / "outputs" / "figures"


def fix_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def ensure_osm() -> None:
    if OSM_FILE.exists():
        print(f"[skip] OSM از قبل موجود است: {OSM_FILE}")
        return
    with open(ASSUMPTIONS, "r", encoding="utf-8") as f:
        a = yaml.safe_load(f)
    sa = a["study_area"]
    lon0, lat0 = sa["center_lon"]["value"], sa["center_lat"]["value"]
    half = sa["bbox_half_extent"]["value"]
    from pyproj import Transformer

    to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32640", always_xy=True)
    to_wgs = Transformer.from_crs("EPSG:32640", "EPSG:4326", always_xy=True)
    e0, n0 = to_utm.transform(lon0, lat0)
    w, s = to_wgs.transform(e0 - half, n0 - half)
    e, n = to_wgs.transform(e0 + half, n0 + half)

    OSM_FILE.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, str(SUMO_HOME / "tools" / "osmGet.py"),
        "-b", f"{w},{s},{e},{n}", "-p", "seyedi", "-d", str(OSM_FILE.parent),
    ]
    print("[run]", " ".join(cmd))
    subprocess.run(cmd, check=True)
    # osmGet.py names the output <prefix>_bbox.osm.xml
    produced = OSM_FILE.parent / "seyedi_bbox.osm.xml"
    if not produced.exists():
        raise FileNotFoundError(f"osmGet.py did not produce {produced}")


def run_netconvert() -> None:
    PLAIN_PREFIX.parent.mkdir(parents=True, exist_ok=True)
    NET_FILE.parent.mkdir(parents=True, exist_ok=True)
    netconvert = SUMO_HOME / "bin" / "netconvert.exe"
    cmd = [
        str(netconvert),
        "--osm-files", str(OSM_FILE),
        "--output-file", str(NET_FILE),
        "--plain-output-prefix", str(PLAIN_PREFIX),
        "--type-files", str(TYPEMAP),
        "--osm.layer-elevation", "4",
        "--geometry.remove", "--ramps.guess",
        "--junctions.join", "--junctions.join-dist", "12",
        "--tls.discard-simple", "--no-turnarounds", "true",
        "--remove-edges.by-vclass", "pedestrian,bicycle,tram,rail",
        "--lefthand", "false",
        # تصمیم طراحی (ثبت در assumptions.yml -> network_scope.arterial_only):
        # مطالعه صرفاً یک تقاطع منفرد است؛ برای جلوگیری از پراکنده‌شدن تقاضای
        # jtrrouter در تار عنکبوتی خیابان‌های محلی/مسکونی اطراف، شبکه به معابر
        # شریانی محدود می‌شود. اگر در فاز ۲-۳ رفتار ورود/خروج محلی لازم شد، این
        # فیلتر با کنترل نسخه قابل بازگشت است.
        "--keep-edges.by-type",
        "highway.trunk,highway.trunk_link,highway.primary,highway.primary_link,"
        "highway.secondary,highway.secondary_link",
    ]
    print("[run]", " ".join(cmd))
    subprocess.run(cmd, check=True)


def plot_layer_check() -> None:
    """رسم شبکه با رنگ‌بندی بر اساس ارتفاع (z) برای تأیید چشمی جدایی تراز."""
    net = sumolib.net.readNet(str(NET_FILE))
    fig, ax = plt.subplots(figsize=(11, 11))
    for edge in net.getEdges():
        shape = edge.getShape3D() if hasattr(edge, "getShape3D") else edge.getShape()
        xs = [p[0] for p in shape]
        ys = [p[1] for p in shape]
        z_vals = [p[2] if len(p) > 2 else 0.0 for p in shape]
        z = max(z_vals) if z_vals else 0.0
        color = "#d62728" if z > 0.5 else "#1f77b4"
        lw = 2.2 if z > 0.5 else 0.8
        ax.plot(xs, ys, color=color, lw=lw, alpha=0.85, zorder=(2 if z > 0.5 else 1))

    ax.set_aspect("equal")
    ax.set_title(
        "بازرسی چشمی جدایی تراز — قرمز: عرشهٔ پل (z>0) / آبی: شبکهٔ هم‌سطح (z=0)\n"
        "تقاطع زیرپل سیدی، کرمان — فاز ۱ (Walking Skeleton)",
        fontsize=10,
    )
    ax.set_xlabel("x شبکه (متر، تصویر UTM)")
    ax.set_ylabel("y شبکه (متر، تصویر UTM)")
    from matplotlib.lines import Line2D
    handles = [
        Line2D([0], [0], color="#d62728", lw=2.2, label="عرشهٔ پل (بزرگراه امام‌رضا، z>0)"),
        Line2D([0], [0], color="#1f77b4", lw=0.8, label="شبکهٔ هم‌سطح (z=0)"),
    ]
    ax.legend(handles=handles, loc="upper right", fontsize=8)
    fig.tight_layout()

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    for path in (FIG_DIR / "network_layer_check.svg", FIG_DIR / "network_layer_check.png"):
        fig.savefig(path, dpi=200)
        print(f"[ok] نوشته شد: {path}")

    # --- نمای زوم‌شده حول خود تقاطع: نزدیک‌ترین نقطهٔ برخورد عرشهٔ پل با شبکهٔ هم‌سطح ---
    bridge_pts, ground_pts = [], []
    for edge in net.getEdges():
        shape = edge.getShape3D() if hasattr(edge, "getShape3D") else edge.getShape()
        pts2d = [(p[0], p[1]) for p in shape]
        if any((len(p) > 2 and p[2] > 0.5) for p in shape):
            bridge_pts.extend(pts2d)
        else:
            ground_pts.extend(pts2d)

    best = None
    if bridge_pts and ground_pts:
        # نمونه‌برداری تُنُک برای سرعت (شبکه چند صد یال دارد، کافی‌ست)
        bp = bridge_pts[::3] or bridge_pts
        gp = ground_pts[::5] or ground_pts
        for bx, by in bp:
            for gx, gy in gp:
                d2 = (bx - gx) ** 2 + (by - gy) ** 2
                if best is None or d2 < best[0]:
                    best = (d2, bx, by, gx, gy)

    if best is not None:
        _, bx, by, gx, gy = best
        cx, cy = (bx + gx) / 2, (by + gy) / 2
        half = 150
        ax.set_xlim(cx - half, cx + half)
        ax.set_ylim(cy - half, cy + half)
        ax.set_title(
            "بازرسی چشمی جدایی تراز (زوم‌شده حول تقاطع) — قرمز: عرشهٔ پل (z>0) / آبی: شبکهٔ هم‌سطح (z=0)\n"
            "تقاطع زیرپل سیدی، کرمان — فاز ۱ (Walking Skeleton)",
            fontsize=10,
        )
        for path in (FIG_DIR / "network_layer_check_zoom.svg", FIG_DIR / "network_layer_check_zoom.png"):
            fig.savefig(path, dpi=200)
            print(f"[ok] نوشته شد: {path}")


def main() -> None:
    fix_console_encoding()
    ensure_osm()
    run_netconvert()
    plot_layer_check()


if __name__ == "__main__":
    main()
