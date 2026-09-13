#!/usr/bin/env python
"""
فاز ۴ — سناریوی S1 (تقاطع چراغ‌دار): ساخت شبکه از روی plain-XML مبنا.

طبق تصمیم ثبت‌شده در config/assumptions.yml -> signal_design_S1: هر گرهٔ ادغام
واقعی (in-degree>=2) درون شعاع میدانچهٔ ویوینگ زیر پل (همان WEAVE_CENTER/RADIUS
فاز ۲) به‌طور مستقل نوع traffic_light می‌گیرد. plain-XML مبنا (network/plain/
seyedi.*، شامل اصلاحات فاز ۲: خط عرشه + zipper) کپی و روی نسخهٔ محلی این
سناریو ویرایش می‌شود — فایل‌های فاز ۲ دست‌نخورده می‌مانند (قاعدهٔ سخت ۲).

دو نسخهٔ شبکه ساخته می‌شود:
  seyedi_S1_fixed.net.xml    — --tls.default-type static, --tls.cycle.time <C>
                                (C از src/08_webster_timing.py، وبستر@λ=1.0)
  seyedi_S1_actuated.net.xml — --tls.default-type actuated (پیش‌فرض SUMO)

اجرا: `python scenarios/S1_signal/build_network.py` (نیازمند اجرای قبلی
`make webster-timing` برای وجود config/signal_timing_S1.yml)
"""
from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
SUMO_HOME = ROOT / ".venv" / "Lib" / "site-packages" / "sumo"
BASE_PLAIN_PREFIX = ROOT / "network" / "plain" / "seyedi"
SCEN_DIR = pathlib.Path(__file__).resolve().parent
PLAIN_PREFIX = SCEN_DIR / "plain" / "seyedi_s1"
NET_DIR = SCEN_DIR / "network"
TYPEMAP = ROOT / "config" / "typemap" / "urban_ir.typ.xml"
TIMING_FILE = ROOT / "config" / "signal_timing_S1.yml"

WEAVE_CENTER = (3200, 2750)  # همان مرکز میدانچهٔ ویوینگ فاز ۲ (src/02_patch_geometry.py)
WEAVE_SEARCH_RADIUS = 120


def fix_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def copy_base_plain() -> None:
    PLAIN_PREFIX.parent.mkdir(parents=True, exist_ok=True)
    for suffix in (".nod.xml", ".edg.xml", ".con.xml", ".tll.xml", ".typ.xml"):
        src = BASE_PLAIN_PREFIX.with_suffix(suffix)
        if src.exists():
            shutil.copy(src, PLAIN_PREFIX.with_suffix(suffix))


def retype_merge_nodes_to_signal() -> list[str]:
    """گره‌های ادغام واقعی (in-degree>=2) درون شعاع میدانچهٔ ویوینگ -> traffic_light مستقل."""
    edg_tree = ET.parse(PLAIN_PREFIX.with_suffix(".edg.xml"))
    in_count: dict[str, int] = {}
    for edge in edg_tree.getroot().findall("edge"):
        in_count[edge.get("to")] = in_count.get(edge.get("to"), 0) + 1

    nod_path = PLAIN_PREFIX.with_suffix(".nod.xml")
    nod_tree = ET.parse(nod_path)
    cx, cy = WEAVE_CENTER
    signalized: list[str] = []
    for node in nod_tree.getroot().findall("node"):
        nid = node.get("id")
        x, y = float(node.get("x")), float(node.get("y"))
        if (x - cx) ** 2 + (y - cy) ** 2 > WEAVE_SEARCH_RADIUS ** 2:
            continue
        if in_count.get(nid, 0) >= 2:
            node.set("type", "traffic_light")
            node.set("tl", nid)  # هر گره برنامهٔ TLS مستقل خودش را می‌گیرد (نه joined)
            signalized.append(nid)
    nod_tree.write(nod_path, encoding="UTF-8", xml_declaration=True)
    return signalized


def rebuild_network(tls_default_type: str, out_net: pathlib.Path, cycle_time: float | None) -> None:
    netconvert = SUMO_HOME / "bin" / "netconvert.exe"
    cmd = [
        str(netconvert),
        "--node-files", str(PLAIN_PREFIX.with_suffix(".nod.xml")),
        "--edge-files", str(PLAIN_PREFIX.with_suffix(".edg.xml")),
        "--connection-files", str(PLAIN_PREFIX.with_suffix(".con.xml")),
        "--tllogic-files", str(PLAIN_PREFIX.with_suffix(".tll.xml")),
        "--type-files", str(TYPEMAP),
        "--output-file", str(out_net),
        "--no-turnarounds", "true",
        "--tls.default-type", tls_default_type,
    ]
    if cycle_time is not None:
        cmd += ["--tls.cycle.time", str(int(round(cycle_time)))]
    print("[run]", " ".join(cmd))
    subprocess.run(cmd, check=True)


def main() -> None:
    fix_console_encoding()
    if not TIMING_FILE.exists():
        raise FileNotFoundError(f"{TIMING_FILE} یافت نشد — ابتدا `make webster-timing` را اجرا کن.")
    with open(TIMING_FILE, "r", encoding="utf-8") as f:
        timing = yaml.safe_load(f)
    cycle_s = timing["cycle_length_s"]["final_used_s"]

    copy_base_plain()
    signalized = retype_merge_nodes_to_signal()
    print(f"[ok] {len(signalized)} گرهٔ ادغام درون میدانچهٔ ویوینگ چراغ‌دار شد: {signalized}")

    NET_DIR.mkdir(parents=True, exist_ok=True)
    rebuild_network("static", NET_DIR / "seyedi_S1_fixed.net.xml", cycle_time=cycle_s)
    print(f"[ok] نوشته شد: {NET_DIR / 'seyedi_S1_fixed.net.xml'} (سیکل ثابت وبستر = {cycle_s}s)")
    rebuild_network("actuated", NET_DIR / "seyedi_S1_actuated.net.xml", cycle_time=None)
    print(f"[ok] نوشته شد: {NET_DIR / 'seyedi_S1_actuated.net.xml'} (actuated، پیش‌فرض SUMO)")


if __name__ == "__main__":
    main()
