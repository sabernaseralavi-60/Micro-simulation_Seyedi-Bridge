#!/usr/bin/env python
"""
فاز ۴ — سناریوی S3 (میدان مدرن/نامتقارن): افزودن حلقهٔ گردشی زیر پل.

طبق Checkpoint کاربر (۱۴۰۵/۰۶/۲۳): **هر دو گزینه ساخته می‌شود** تا مقایسه‌ای
باشد:
  - **constrained** — حلقه فقط با استفاده از نقاط اتصال واقعیِ دو دهانهٔ باز
    موجود (بدون دهانهٔ مرکزی).
  - **full** — همان حلقه + یک وتر مستقیم شرق-غرب که فرضاً از دهانهٔ مرکزیِ
    بازشده عبور می‌کند (مشروط به تأیید سازه‌ای مهندس سازه — خارج از حیطهٔ این
    مطالعهٔ ترافیکی؛ رجوع به assumptions.yml -> bridge_geometry.span_structure).

**روش (کم‌ریسک‌ترین گزینهٔ ممکن با توجه به نبود یک گرهٔ تقاطعی واحد):**
به‌جای ادغام/حذف زنجیرهٔ ~۲۴گرهیِ رمپ/ادغام/انشعاب موجود (که S1 دقیقاً به
همین دلیل از آن پرهیز کرد)، یک حلقهٔ گردشی جدید با ۴ یال، **صرفاً میان چهار
گرهٔ ورودی/تلاقی واقعی موجود** (بدون حذف هیچ گره/یال قبلی) افزوده می‌شود:

    شمال (۵۰۹۱۶۳۲۸۲۶، تنها انشعاب واقعی ورودی شمال)
    غرب  (۶۷۱۱۵۰۹۱۶۳، نزدیک‌ترین گره به رمپ دهانهٔ باز غربی)
    جنوب (۶۷۱۱۵۰۹۱۷۶، تنها انشعاب واقعی ورودی جنوب)
    شرق  (۶۷۱۱۵۰۹۱۶۶، نزدیک‌ترین گره به رمپ دهانهٔ باز شرقی)

جهت گردش پادساعتگرد (طبق قرارداد رانندگی راست‌رو ایران). اتصال‌های حلقه
`pass="true"` می‌گیرند (حق‌تقدم بدون قیدوشرط برای ترافیک گردشی — دقیقاً
تعریف رفتاری یک میدان واقعی: ورودی‌ها منتظر می‌مانند، گردشی‌ها حق‌تقدم دارند).
این افزودنی، نه حذفی — همهٔ اتصالات قبلی دست‌نخورده می‌مانند و jtrrouter با
`--turn-defaults` طبیعتاً بخشی از تقاضا را از مسیر حلقه هم عبور می‌دهد.

اجرا: `python scenarios/S3_roundabout/build_network.py`
"""
from __future__ import annotations

import math
import pathlib
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[2]
SUMO_HOME = ROOT / ".venv" / "Lib" / "site-packages" / "sumo"
BASE_PLAIN_PREFIX = ROOT / "network" / "plain" / "seyedi"
SCEN_DIR = pathlib.Path(__file__).resolve().parent
TYPEMAP = ROOT / "config" / "typemap" / "urban_ir.typ.xml"

RING_NODES = {
    "N": "5091632826",
    "W": "6711509163",
    "S": "6711509176",
    "E": "6711509166",
}
# ترتیب پادساعتگرد (راست‌رو): شمال -> غرب -> جنوب -> شرق -> شمال
RING_ORDER = ["N", "W", "S", "E"]

# یال‌های موجودِ ورودی/خروجیِ هر گرهٔ تلاقی (بازرسی مستقیم plain/seyedi.edg.xml)
# — چون فایل اتصالات صریح است، اتصال تازه به/از حلقه باید دستی اضافه شود؛
# netconvert آن را خودکار حدس نمی‌زند.
TAP_IN = {
    "N": ["592154956#0-AddedOffRampEdge"],
    "W": ["627154371#0-AddedOffRampEdge"],
    "S": ["610531293#0-AddedOffRampEdge"],
    "E": ["627154378#0", "627633585"],
}
TAP_OUT = {
    "N": ["627154373", "627167743#0"],
    "W": ["627154371#8", "627633586"],
    "S": ["610531293#4", "713864643"],
    "E": ["627154378#1-AddedOnRampEdge"],
}
RING_SPEED = "6.94"  # 25 km/h — سرعت متعارف مانور داخل میدان کوچک


def fix_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def node_coord(nod_root, nid):
    for n in nod_root.findall("node"):
        if n.get("id") == nid:
            return float(n.get("x")), float(n.get("y"))
    raise KeyError(nid)


def build_variant(variant: str) -> pathlib.Path:
    assert variant in ("constrained", "full")
    plain_prefix = SCEN_DIR / "plain" / f"seyedi_s3_{variant}"
    plain_prefix.parent.mkdir(parents=True, exist_ok=True)
    for suffix in (".nod.xml", ".edg.xml", ".con.xml", ".tll.xml", ".typ.xml"):
        src = BASE_PLAIN_PREFIX.with_suffix(suffix)
        if src.exists():
            shutil.copy(src, plain_prefix.with_suffix(suffix))

    nod_path = plain_prefix.with_suffix(".nod.xml")
    edg_path = plain_prefix.with_suffix(".edg.xml")
    con_path = plain_prefix.with_suffix(".con.xml")

    nod_tree = ET.parse(nod_path)
    nod_root = nod_tree.getroot()
    coords = {k: node_coord(nod_root, v) for k, v in RING_NODES.items()}

    edg_tree = ET.parse(edg_path)
    edg_root = edg_tree.getroot()

    ring_edge_ids = []

    def add_ring_edge(eid, frm_key, to_key):
        frm, to = RING_NODES[frm_key], RING_NODES[to_key]
        el = ET.SubElement(edg_root, "edge")
        el.set("id", eid)
        el.set("from", frm)
        el.set("to", to)
        el.set("numLanes", "1")
        el.set("speed", RING_SPEED)
        # اولویت یال بالا (طبق رفتار واقعی میدان: ترافیک گردشی حق‌تقدم دارد،
        # ورودی‌ها منتظر می‌مانند) — pass="true" به‌تنهایی کافی نبود، چون فقط
        # روی همان اتصال اثر می‌گذارد نه رتبهٔ نسبی طرف مقابل در گره؛ این
        # priority عددی مستقیماً الگوریتم پیش‌فرض netconvert برای تعیین
        # M(اصلی)/m(فرعی) در گره‌های type=priority را هدایت می‌کند.
        el.set("priority", "50")
        ring_edge_ids.append((eid, frm, to))
        return el

    for i in range(len(RING_ORDER)):
        a, b = RING_ORDER[i], RING_ORDER[(i + 1) % len(RING_ORDER)]
        add_ring_edge(f"s3_ring_{a}_{b}", a, b)

    if variant == "full":
        # وتر شرق-غرب مستقیم، مشروط به بازشدن دهانهٔ مرکزی (رجوع به docstring)
        add_ring_edge("s3_chord_W_E", "W", "E")
        add_ring_edge("s3_chord_E_W", "E", "W")

    edg_tree.write(edg_path, encoding="UTF-8", xml_declaration=True)

    # اتصالات حلقه: هر یال حلقه pass="true" می‌گیرد (حق‌تقدم گردشی بدون قیدوشرط)
    con_tree = ET.parse(con_path)
    con_root = con_tree.getroot()
    for eid, frm, to in ring_edge_ids:
        for next_eid, _, next_to in [(e2, f2, t2) for e2, f2, t2 in ring_edge_ids if f2 == to]:
            c = ET.SubElement(con_root, "connection")
            c.set("from", eid)
            c.set("to", next_eid)
            c.set("fromLane", "0")
            c.set("toLane", "0")
            c.set("pass", "true")

    # اتصال ورود: یال‌های ورودی موجود -> اولین یال حلقهٔ آغازشونده از همان گره
    # اتصال خروج: یال حلقهٔ رسیده به گره -> یال‌های خروجی موجود
    # (بدون این، netconvert چون فایل اتصالات صریح است، این مسیرهای تازه را
    # خودکار حدس نمی‌زند و jtrrouter با خطای «not connected» متوقف می‌شود.)
    def add_manual_connection(frm, to):
        c = ET.SubElement(con_root, "connection")
        c.set("from", frm)
        c.set("to", to)
        c.set("fromLane", "0")
        c.set("toLane", "0")

    for key, node_id in RING_NODES.items():
        ring_starts_here = [eid for eid, frm, to in ring_edge_ids if frm == node_id]
        ring_ends_here = [eid for eid, frm, to in ring_edge_ids if to == node_id]
        for in_edge in TAP_IN[key]:
            for ring_eid in ring_starts_here:
                add_manual_connection(in_edge, ring_eid)
        for ring_eid in ring_ends_here:
            for out_edge in TAP_OUT[key]:
                add_manual_connection(ring_eid, out_edge)

    con_tree.write(con_path, encoding="UTF-8", xml_declaration=True)

    net_dir = SCEN_DIR / "network"
    net_dir.mkdir(parents=True, exist_ok=True)
    out_net = net_dir / f"seyedi_S3_{variant}.net.xml"
    netconvert = SUMO_HOME / "bin" / "netconvert.exe"
    cmd = [
        str(netconvert),
        "--node-files", str(nod_path),
        "--edge-files", str(edg_path),
        "--connection-files", str(con_path),
        "--tllogic-files", str(plain_prefix.with_suffix(".tll.xml")),
        "--type-files", str(TYPEMAP),
        "--output-file", str(out_net),
        "--no-turnarounds", "true",
    ]
    print("[run]", " ".join(cmd))
    subprocess.run(cmd, check=True)
    print(f"[ok] نوشته شد: {out_net}")
    return out_net


def main() -> None:
    fix_console_encoding()
    build_variant("constrained")
    build_variant("full")


if __name__ == "__main__":
    main()
