#!/usr/bin/env python
"""
فاز ۲ — وفاداری هندسی: اصلاحات مبتنی بر تصویر روی plain-XML + بازسازی شبکه.

طبق قاعدهٔ سخت ۲ (CLAUDE.md §3.2)، هیچ اصلاحی با netedit دستی اعمال نمی‌شود؛
این اسکریپت فایل‌های plain-XML خروجیِ src/01_build_network.py را برنامه‌نویسی‌شده
ویرایش می‌کند و سپس netconvert را با ورودی plain-XML (نه OSM خام) دوباره اجرا
می‌کند تا network/seyedi.net.xml نهایی بازسازی شود.

اصلاحات این فاز:
1. تعداد خط عرشهٔ پل: OSM آن را ۲ خط در هر جهت ثبت کرده، اما بازرسی تصویر
   2025_zoom.png (زوم نزدیک، خودروها به‌وضوح در ۳ ردیف روی هر جهت) با اطمینان
   بالا ۳ خط را نشان می‌دهد -> config/assumptions.yml: bridge_geometry.deck_lanes_per_direction.
2. نوع تقاطع نقاط ادغام (merge: ۲ ورودی/۱ خروجی) زیر پل از priority به zipper
   تغییر می‌کند — طبق توصیهٔ CLAUDE.md فاز ۲ برای رفتار «هر که زودتر رسید»ی
   میدانچهٔ ویوینگ بدون کانالیزاسیون (رجوع به traffic_control.left_turn_status_baseline
   که همین رفتار غیررسمی را در فاز ۰ تأیید کرد).

اجرا: `make patch-geometry` (پیش از `make network` در زنجیرهٔ all، رجوع به Makefile)
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]
SUMO_HOME = ROOT / ".venv" / "Lib" / "site-packages" / "sumo"
PLAIN_PREFIX = ROOT / "network" / "plain" / "seyedi"
NET_FILE = ROOT / "network" / "seyedi.net.xml"
TYPEMAP = ROOT / "config" / "typemap" / "urban_ir.typ.xml"

# --- اصلاح ۱: تعداد خط عرشهٔ پل (منبع: imagery، رجوع به assumptions.yml) ---
BRIDGE_DECK_EDGE_IDS = ["410247492", "627008192"]
BRIDGE_DECK_LANES = 3

# --- اصلاح ۲: تقاطع‌های ادغام زیر پل -> zipper ---
# شعاع جست‌وجو حول مرکز میدانچهٔ ویوینگ (مختصات محلی شبکه، نه جغرافیایی)
WEAVE_CENTER = (3200, 2750)
WEAVE_SEARCH_RADIUS = 120


def fix_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def patch_edge_lanes() -> int:
    edg_path = PLAIN_PREFIX.with_suffix(".edg.xml")
    text = edg_path.read_text(encoding="utf-8")
    n_patched = 0
    for eid in BRIDGE_DECK_EDGE_IDS:
        pattern = re.compile(rf'(<edge id="{re.escape(eid)}"[^>]*numLanes=")(\d+)(")')

        def _sub(m: re.Match) -> str:
            nonlocal n_patched
            n_patched += 1
            return f"{m.group(1)}{BRIDGE_DECK_LANES}{m.group(3)}"

        text, count = pattern.subn(_sub, text)
        if count == 0:
            raise RuntimeError(f"یال {eid} در {edg_path} برای پچ خط پیدا نشد.")
    edg_path.write_text(text, encoding="utf-8")
    return n_patched


def patch_merge_junctions_to_zipper() -> int:
    """گره‌هایی با دقیقاً ۲ یال ورودی و ۱ یال خروجی، درون شعاع میدانچهٔ ویوینگ، zipper می‌شوند."""
    nod_path = PLAIN_PREFIX.with_suffix(".nod.xml")
    edg_path = PLAIN_PREFIX.with_suffix(".edg.xml")

    edg_tree = ET.parse(edg_path)
    in_count: dict[str, int] = {}
    out_count: dict[str, int] = {}
    for edge in edg_tree.getroot().findall("edge"):
        out_count[edge.get("from")] = out_count.get(edge.get("from"), 0) + 1
        in_count[edge.get("to")] = in_count.get(edge.get("to"), 0) + 1

    nod_tree = ET.parse(nod_path)
    cx, cy = WEAVE_CENTER
    n_patched = 0
    for node in nod_tree.getroot().findall("node"):
        nid = node.get("id")
        x, y = float(node.get("x")), float(node.get("y"))
        if (x - cx) ** 2 + (y - cy) ** 2 > WEAVE_SEARCH_RADIUS ** 2:
            continue
        if in_count.get(nid, 0) == 2 and out_count.get(nid, 0) == 1:
            node.set("type", "zipper")
            n_patched += 1
    nod_tree.write(nod_path, encoding="UTF-8", xml_declaration=True)
    return n_patched


def rebuild_network_from_plain() -> None:
    netconvert = SUMO_HOME / "bin" / "netconvert.exe"
    cmd = [
        str(netconvert),
        "--node-files", str(PLAIN_PREFIX.with_suffix(".nod.xml")),
        "--edge-files", str(PLAIN_PREFIX.with_suffix(".edg.xml")),
        "--connection-files", str(PLAIN_PREFIX.with_suffix(".con.xml")),
        "--tllogic-files", str(PLAIN_PREFIX.with_suffix(".tll.xml")),
        "--type-files", str(TYPEMAP),
        "--output-file", str(NET_FILE),
        "--no-turnarounds", "true",
    ]
    print("[run]", " ".join(cmd))
    subprocess.run(cmd, check=True)


def main() -> None:
    fix_console_encoding()
    n_lanes = patch_edge_lanes()
    print(f"[ok] {n_lanes} یال عرشهٔ پل به {BRIDGE_DECK_LANES} خط اصلاح شد.")
    n_zip = patch_merge_junctions_to_zipper()
    print(f"[ok] {n_zip} تقاطع ادغام زیر پل به نوع zipper تغییر یافت.")
    rebuild_network_from_plain()
    print(f"[ok] شبکه از plain-XML اصلاح‌شده بازسازی شد: {NET_FILE}")


if __name__ == "__main__":
    main()
