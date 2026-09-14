#!/usr/bin/env python
"""
فاز ۴ — سناریوی S4 (کانالیزاسیون + گردش راست آزاد): ساخت شبکه از روی plain-XML مبنا.

طبق CLAUDE.md، S4 یعنی جزیره‌سازی و گردش راست آزاد (بدون نیاز به توقف/تعارض)
در نقاط گردش زیر پل. بازرسی هندسی (با همان منطق تشخیص زاویه/بردار در
src/03_build_demand.py) نشان داد هر ۵ گرهٔ ادغام واقعی زیر پل (همان ۵ گرهٔ
شناسایی‌شده در فاز S1 که تعارض واقعی داشتند) دقیقاً یک الگوی «عبوری + راست‌گرد»
دارند (به‌علاوه یک گردش چپ اضافه در یک گره). این یعنی می‌توان کانالیزاسیون
گردش راست را در همهٔ این ۵ نقطه به‌صورت برنامه‌نویسی‌شده اعمال کرد، نه صرفاً
به‌صورت نمادین در دو دهانه.

پیاده‌سازی (کم‌ریسک‌ترین مکانیزم موجود SUMO برای این مفهوم):
- نوع گره از `zipper` (ادغام برابر/تعارض) به `priority` برمی‌گردد.
- اتصال (connection) مربوط به ورودیِ **عبوریِ اصلی** با `pass="true"` علامت‌گذاری
  می‌شود — طبق قرارداد متعارف مهندسی ترافیک، مسیر اصلی هرگز برای ادغام گردش
  راست کانالیزه متوقف نمی‌شود.
- ورودیِ **گردش راست کانالیزه‌شده** حق‌تقدم minor عادی می‌گیرد (باید گَپ پیدا
  کند، اما دیگر در مذاکرهٔ مبهم zipper با هر دو طرف معطل نمی‌ماند — یک قاعدهٔ
  حق‌تقدم شفاف و یک‌طرفه، به‌جای ابهام قبلی، هستهٔ فایدهٔ کانالیزاسیون است).
- در گرهٔ سه‌ورودی (6711509164)، ورودیِ **چپ‌گرد** دست‌نخورده می‌ماند (تعارض آن
  در حیطهٔ S2 است، نه S4).

«حذف پارک حاشیه‌ای در ۵۰ متر منتهی به تقاطع» در baseline اصلاً مدل نشده بود
(SUMO هیچ توقف حاشیه‌ای را به‌عنوان ظرفیت‌کاهنده لحاظ نکرده)، پس این بند اثر
شبکه‌ای ندارد و صرفاً یک یادداشت کیفی در گزارش است، نه تغییر مدل.

اجرا: `python scenarios/S4_channelization/build_network.py`
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
PLAIN_PREFIX = SCEN_DIR / "plain" / "seyedi_s4"
NET_DIR = SCEN_DIR / "network"
TYPEMAP = ROOT / "config" / "typemap" / "urban_ir.typ.xml"

# گره -> (یال عبوریِ اصلی، یال خروجی)
# طبق بازرسی هندسی زاویه (رجوع به مستندسازی این فایل) — همان ۵ گرهٔ تعارض واقعی فاز S1.
# یال عبوری pass="true" می‌گیرد (حق‌تقدم بدون قید‌وشرط، طبق قرارداد متعارف
# مهندسی ترافیک: مسیر اصلی/عبوری هرگز برای ادغام گردش راست متوقف نمی‌شود)؛
# یال گردش راستِ کانالیزه به‌صورت minor/yield عادی می‌ماند — یعنی به‌جای مذاکرهٔ
# مبهم zipper (که هر دو طرف را به‌طور مساوی معطل می‌کند)، اکنون یک قاعدهٔ
# حق‌تقدم شفاف و یک‌طرفه دارد؛ همین وضوح، هستهٔ اصلی فایدهٔ کانالیزاسیون است.
FREE_RIGHT_CONNECTIONS = {
    "4120846834": ("122236756#1", "122236756#2"),
    "4120854403": ("627167744#1", "627167744#2-AddedOnRampEdge"),
    "6053976954": ("643263246#1", "643263246#2"),
    "6053976957": ("1165329135#1", "1165329135#2"),
    "6711509164": ("627154372#1", "627154372#2"),
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


def retype_nodes_to_priority(plain_prefix: pathlib.Path = PLAIN_PREFIX) -> int:
    """`plain_prefix` پارامتر شد (نشست ۵) تا scenarios/S2_S4_combined بتواند
    همین منطق را روی plain-XML از قبل تغییریافتهٔ S2 اعمال کند، بدون کپی
    جداگانهٔ کد — گره‌های S4 (ادغام) و S2 (انشعاب) کاملاً مجزا هستند، پس
    این دو مرحله بدون تداخل روی هم قابل‌اعمال‌اند."""
    nod_path = plain_prefix.with_suffix(".nod.xml")
    tree = ET.parse(nod_path)
    n = 0
    for node in tree.getroot().findall("node"):
        if node.get("id") in FREE_RIGHT_CONNECTIONS and node.get("type") == "zipper":
            node.set("type", "priority")
            n += 1
    tree.write(nod_path, encoding="UTF-8", xml_declaration=True)
    return n


def mark_free_right_connections(plain_prefix: pathlib.Path = PLAIN_PREFIX) -> int:
    con_path = plain_prefix.with_suffix(".con.xml")
    tree = ET.parse(con_path)
    n = 0
    for node_id, (through_edge, out_edge) in FREE_RIGHT_CONNECTIONS.items():
        found = False
        for c in tree.getroot().findall("connection"):
            if c.get("from") == through_edge and c.get("to") == out_edge:
                c.set("pass", "true")
                n += 1
                found = True
        if not found:
            raise RuntimeError(f"اتصال {through_edge}->{out_edge} برای گرهٔ {node_id} در con.xml پیدا نشد.")
    tree.write(con_path, encoding="UTF-8", xml_declaration=True)
    return n


def rebuild_network() -> None:
    netconvert = SUMO_HOME / "bin" / "netconvert.exe"
    NET_DIR.mkdir(parents=True, exist_ok=True)
    out_net = NET_DIR / "seyedi_S4.net.xml"
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
    n_retyped = retype_nodes_to_priority()
    print(f"[ok] {n_retyped} گره از zipper به priority بازگردانده شد.")
    n_marked = mark_free_right_connections()
    print(f"[ok] {n_marked} اتصال گردش راست با pass=\"true\" کانالیزه شد.")
    rebuild_network()


if __name__ == "__main__":
    main()
