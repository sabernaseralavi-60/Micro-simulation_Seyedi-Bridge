#!/usr/bin/env python
"""
فاز ۴ — سناریوی S2 (نسخهٔ ۱: حذف تعارض گردش چپ زیر پل).

بازرسی هندسی نقاط انشعاب (diverge: ۱ ورودی/≥۲ خروجی) درون شعاع میدانچهٔ
ویوینگ (همان WEAVE_CENTER فاز ۲/S1) با همان منطق تشخیص زاویه/بردار
src/03_build_demand.py نشان داد ۹ گرهٔ انشعاب واقعی وجود دارد که هرکدام
دقیقاً بین «عبوری» و یکی از «چپ‌گرد» یا «راست‌گرد» تصمیم می‌گیرند. این اسکریپت
اتصال (connection) مربوط به هر ۵ گزینهٔ **چپ‌گرد** شناسایی‌شده را از plain-XML
حذف می‌کند — یعنی گردش چپ زیر پل از نظر توپولوژیک دیگر ممکن نیست، نه صرفاً
در سطح تقاضا (نسبت صفر در turns.xml).

**محدودیت صریح این نسخه (v1):** ساخت فیزیکی خودِ دوربرگردان‌های میانهٔ عرشه
(median U-turn، با حساسیت فاصلهٔ ۱۵۰/۲۵۰/۳۵۰ متر طبق CLAUDE.md) هنوز
پیاده‌سازی نشده — نیازمند شکافتن (split) دو یال بلند عرشه با درون‌یابی
طول‌کمانی، کاری با ریسک/پیچیدگی به‌مراتب بالاتر که به‌عمد به نسخهٔ بعدی
موکول شد (رجوع به README این سناریو). آنچه این نسخه می‌سنجد، **اثر اصلی و
مستقیم‌تر**: در نبود گزینهٔ گردش چپ، تقاضای مربوطه صرفاً از میان عبوری/راست‌گرد
باقی‌مانده توزیع مجدد می‌شود (جابه‌جایی مقصد واقعی وسیله، نه یک مسیر U-turn
واقعی با مسافت اضافه) — این دقیقاً همان ساده‌سازی صریحی است که پروژه ترجیح
می‌دهد به‌جای پنهان کردنش، آشکارا اعلام کند.

اجرا: `python scenarios/S2_rcut/build_network.py`
"""
from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[2]
SUMO_HOME = ROOT / ".venv" / "Lib" / "site-packages" / "sumo"
BASE_PLAIN_PREFIX = ROOT / "network" / "plain" / "seyedi"
SCEN_DIR = pathlib.Path(__file__).resolve().parent
PLAIN_PREFIX = SCEN_DIR / "plain" / "seyedi_s2"
NET_DIR = SCEN_DIR / "network"
TYPEMAP = ROOT / "config" / "typemap" / "urban_ir.typ.xml"

# گرهٔ انشعاب -> (یال ورودی, یال خروجیِ چپ‌گرد) — طبق بازرسی هندسی زاویه
LEFT_TURN_CONNECTIONS = {
    "6711509165": ("1165329134", "643263251"),
    "6711509176": ("610531293#0-AddedOffRampEdge", "713864643"),
    "6711509163": ("627154371#0-AddedOffRampEdge", "627633586"),
    "6711509162": ("627154372#0", "643263250"),
    "6403676806": ("627167743#0", "683662933"),
}


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


def remove_left_turn_connections() -> int:
    con_path = PLAIN_PREFIX.with_suffix(".con.xml")
    tree = ET.parse(con_path)
    root = tree.getroot()
    n = 0
    for node_id, (in_edge, left_edge) in LEFT_TURN_CONNECTIONS.items():
        to_remove = [c for c in root.findall("connection")
                     if c.get("from") == in_edge and c.get("to") == left_edge]
        if not to_remove:
            raise RuntimeError(f"اتصال چپ‌گرد {in_edge}->{left_edge} برای گرهٔ {node_id} پیدا نشد.")
        for c in to_remove:
            root.remove(c)
            n += 1
    tree.write(con_path, encoding="UTF-8", xml_declaration=True)
    return n


def rebuild_network() -> None:
    netconvert = SUMO_HOME / "bin" / "netconvert.exe"
    NET_DIR.mkdir(parents=True, exist_ok=True)
    out_net = NET_DIR / "seyedi_S2.net.xml"
    cmd = [
        str(netconvert),
        "--node-files", str(PLAIN_PREFIX.with_suffix(".nod.xml")),
        "--edge-files", str(PLAIN_PREFIX.with_suffix(".edg.xml")),
        "--connection-files", str(PLAIN_PREFIX.with_suffix(".con.xml")),
        "--tllogic-files", str(PLAIN_PREFIX.with_suffix(".tll.xml")),
        "--type-files", str(TYPEMAP),
        "--output-file", str(out_net),
        "--no-turnarounds", "true",
    ]
    print("[run]", " ".join(cmd))
    subprocess.run(cmd, check=True)
    print(f"[ok] نوشته شد: {out_net}")


def main() -> None:
    fix_console_encoding()
    copy_base_plain()
    n = remove_left_turn_connections()
    print(f"[ok] {n} اتصال گردش چپ زیر پل حذف شد (رجوع به LEFT_TURN_CONNECTIONS).")
    rebuild_network()


if __name__ == "__main__":
    main()
