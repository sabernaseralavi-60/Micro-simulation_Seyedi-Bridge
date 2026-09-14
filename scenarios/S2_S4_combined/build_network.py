#!/usr/bin/env python
"""
فاز ۴ — سناریوی ترکیبی S2+S4 (حذف گردش چپ + دوربرگردان فیزیکی، هم‌زمان با
کانالیزاسیون گردش راست).

طبق گام ۳ بخش ۱۲ گزارش: «بررسی سناریوی ترکیبی S2+S4 — هر دو کم‌ریسک و بدون
کنترل فعال‌اند؛ ممکن است اثر تجمعی بدهند.» این اسکریپت دقیقاً همان دو اصلاح
مستقل S2 و S4 را روی یک plain-XML مشترک اعمال می‌کند، نه یک پیاده‌سازی تازه:

  ۱. `S2_rcut.build_network.apply_s2_modifications` — حذف ۵ اتصال گردش چپ
     (گره‌های انشعاب) + شکافتن دو یال عرشه + افزودن دو دوربرگردان (D=250m،
     مقدار «default» رسمی S2).
  ۲. `S4_channelization.build_network.retype_nodes_to_priority` +
     `mark_free_right_connections` — بازگرداندن ۵ گرهٔ ادغام از zipper به
     priority + کانالیزهٔ گردش راست با pass="true".

**چرا ترکیب بدون تداخل ممکن است:** گره‌های S2 (انشعاب، ۹۰۹۰-نوع diverge:
۶۷۱۱۵۰۹۱۶۵/۷۶/۶۳/۶۲، ۶۴۰۳۶۷۶۸۰۶) کاملاً مجزا از گره‌های S4 (ادغام، ۴۱۲۰...
۶۷۱۱۵۰۹۱۶۴) هستند — دو مجموعهٔ گرهٔ فیزیکی متفاوت، بدون هم‌پوشانی. یال‌های
مرجع S4 (`FREE_RIGHT_CONNECTIONS`) هم هیچ‌کدام یال بلند عرشهٔ شکافته‌شدهٔ S2
نیستند، پس ترتیب اعمال (اول S2، بعد S4) اهمیتی ندارد و هیچ اتصال/یالی
دوبار دست‌کاری نمی‌شود.

اجرا: `python scenarios/S2_S4_combined/build_network.py`
"""
from __future__ import annotations

import importlib.util
import pathlib
import shutil
import subprocess
import sys

import sumolib
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
SUMO_HOME = ROOT / ".venv" / "Lib" / "site-packages" / "sumo"
BASE_PLAIN_PREFIX = ROOT / "network" / "plain" / "seyedi"
BASE_NET = ROOT / "network" / "seyedi.net.xml"
SCEN_DIR = pathlib.Path(__file__).resolve().parent
TYPEMAP = ROOT / "config" / "typemap" / "urban_ir.typ.xml"
ASSUMPTIONS = ROOT / "config" / "assumptions.yml"

S2_DISTANCE = 250.0  # همان مقدار «default» رسمی S2


def fix_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def _load_module(name: str, relpath: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relpath)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> None:
    fix_console_encoding()
    s2 = _load_module("s2build", "scenarios/S2_rcut/build_network.py")
    s4 = _load_module("s4build", "scenarios/S4_channelization/build_network.py")

    with open(ASSUMPTIONS, "r", encoding="utf-8") as f:
        assumptions = yaml.safe_load(f)
    left_pct = assumptions["traffic_control"]["turn_ratio_baseline"]["value"]["left"]
    net = sumolib.net.readNet(str(BASE_NET))

    plain_prefix = SCEN_DIR / "plain" / "seyedi_s2s4"
    plain_prefix.parent.mkdir(parents=True, exist_ok=True)
    for suffix in (".nod.xml", ".edg.xml", ".con.xml", ".tll.xml", ".typ.xml"):
        src = BASE_PLAIN_PREFIX.with_suffix(suffix)
        if src.exists():
            shutil.copy(src, plain_prefix.with_suffix(suffix))

    # ۱. اصلاح S2 (گردش چپ + دوربرگردان) روی plain-XML مشترک
    s2.apply_s2_modifications(net, S2_DISTANCE, plain_prefix)
    print("[ok] اصلاحات S2 (حذف گردش چپ + دوربرگردان D=250m) اعمال شد.")

    # ۲. اصلاح S4 (کانالیزاسیون) روی همان plain-XML، بعد از S2
    n_retyped = s4.retype_nodes_to_priority(plain_prefix)
    n_marked = s4.mark_free_right_connections(plain_prefix)
    print(f"[ok] {n_retyped} گره از zipper به priority بازگردانده شد "
          f"(کانالیزاسیون S4).")
    print(f"[ok] {n_marked} اتصال گردش راست با pass=\"true\" کانالیزه شد.")

    # ۳. بازسازی نهایی شبکه
    net_dir = SCEN_DIR / "network"
    net_dir.mkdir(parents=True, exist_ok=True)
    out_net = net_dir / "seyedi_S2_S4_combined.net.xml"
    netconvert = SUMO_HOME / "bin" / "netconvert.exe"
    cmd = [
        str(netconvert),
        "--node-files", str(plain_prefix.with_suffix(".nod.xml")),
        "--edge-files", str(plain_prefix.with_suffix(".edg.xml")),
        "--connection-files", str(plain_prefix.with_suffix(".con.xml")),
        "--tllogic-files", str(plain_prefix.with_suffix(".tll.xml")),
        "--type-files", str(TYPEMAP),
        "--output-file", str(out_net),
        "--no-turnarounds", "true",
    ]
    print("[run]", " ".join(cmd))
    subprocess.run(cmd, check=True)
    print(f"[ok] نوشته شد: {out_net}")


if __name__ == "__main__":
    main()
