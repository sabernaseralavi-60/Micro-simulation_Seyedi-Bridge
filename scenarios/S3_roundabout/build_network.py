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
RING_LANES = "1"  # آزموده شد: ۲ خط برخورد را در چند اجرا افزایش داد (تراکم بیشتر
# در گرهٔ کوچک)، نه کاهش؛ به ۱ خط بازگردانده شد — رجوع به بحث گزارش (بخش ۷)
WEAVE_CENTER = (3200, 2750)
ARC_WAYPOINTS = 4  # تعداد نقاط میانی داخل هر یال حلقه، برای شکل کمانی (نه خط راست)


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


def arc_shape(p_from, p_to, center=WEAVE_CENTER, n_waypoints=ARC_WAYPOINTS):
    """نقاط میانی یک کمان پادساعتگرد از p_from به p_to حول center — با
    درون‌یابی خطی زاویه (همیشه رو به افزایش، برای تضمین جهت پادساعتگرد) و
    شعاع (چون ۴ گرهٔ واقعی هم‌فاصله از مرکز نیستند). نسخهٔ ۲ S3: جایگزین
    خط راست نسخهٔ اول — طول کمان بیشتر یعنی فضای بیشتر برای ادغام/شتاب‌گیری
    و شعاع انحراف واقعی‌تر (هستهٔ رفتاری یک میدان واقعی)."""
    cx, cy = center
    a0 = math.atan2(p_from[1] - cy, p_from[0] - cx)
    a1 = math.atan2(p_to[1] - cy, p_to[0] - cx)
    if a1 <= a0:
        a1 += 2 * math.pi
    r0 = math.hypot(p_from[0] - cx, p_from[1] - cy)
    r1 = math.hypot(p_to[0] - cx, p_to[1] - cy)
    pts = [p_from]
    for i in range(1, n_waypoints + 1):
        t = i / (n_waypoints + 1)
        a = a0 + t * (a1 - a0)
        r = r0 + t * (r1 - r0)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    pts.append(p_to)
    return pts


def fmt_shape(shape) -> str:
    return " ".join(f"{x:.2f},{y:.2f}" for x, y in shape)


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
        el.set("numLanes", RING_LANES)
        el.set("speed", RING_SPEED)
        # اولویت یال بالا (طبق رفتار واقعی میدان: ترافیک گردشی حق‌تقدم دارد،
        # ورودی‌ها منتظر می‌مانند) — pass="true" به‌تنهایی کافی نبود، چون فقط
        # روی همان اتصال اثر می‌گذارد نه رتبهٔ نسبی طرف مقابل در گره؛ این
        # priority عددی مستقیماً الگوریتم پیش‌فرض netconvert برای تعیین
        # M(اصلی)/m(فرعی) در گره‌های type=priority را هدایت می‌کند.
        el.set("priority", "50")
        el.set("shape", fmt_shape(arc_shape(coords[frm_key], coords[to_key])))
        ring_edge_ids.append((eid, frm, to, int(RING_LANES)))
        return el

    def add_chord_edge(eid, frm_key, to_key):
        """وتر مستقیم (نه کمانی حول مرکز — یک شکافِ زاویه‌ای بیش از نیمی از
        دایره بین W و E است؛ کمانی‌کردن آن عملاً معادل دوبارهٔ مسیر جنوبی
        حلقه می‌شد، نه یک میان‌بر مستقیم). خط راست بین دو گره، دقیقاً بازنماییِ
        مفهومیِ «مسیر سوم مستقیم از دهانهٔ مرکزی» است. عمداً ۱خطه (نه ۲خطه
        مثل حلقه) نگه داشته شد — بازرسی تجربی نشان داد ۲خطه‌کردن وتر، برخورد
        را در گره‌های W/E به‌شدت افزایش می‌داد (بار هم‌زمان بیشتر روی گرهٔ
        از قبل شلوغ)."""
        el = add_ring_edge(eid, frm_key, to_key)
        el.set("shape", fmt_shape([coords[frm_key], coords[to_key]]))
        el.set("numLanes", "1")
        ring_edge_ids[-1] = (eid, RING_NODES[frm_key], RING_NODES[to_key], 1)
        return el

    for i in range(len(RING_ORDER)):
        a, b = RING_ORDER[i], RING_ORDER[(i + 1) % len(RING_ORDER)]
        add_ring_edge(f"s3_ring_{a}_{b}", a, b)

    if variant == "full":
        # وتر شرق-غرب مستقیم، مشروط به بازشدن دهانهٔ مرکزی (رجوع به docstring)
        add_chord_edge("s3_chord_W_E", "W", "E")
        add_chord_edge("s3_chord_E_W", "E", "W")

    edg_tree.write(edg_path, encoding="UTF-8", xml_declaration=True)

    # اتصالات حلقه: هر یال حلقه pass="true" می‌گیرد (حق‌تقدم گردشی بدون قیدوشرط)
    # نکته (رفع باگ نسخهٔ ۲.۰): وقتی یال حلقه به RING_LANES=2 ارتقا یافت، اگر
    # فقط fromLane=0/toLane=0 وصل شود، خط دوم (index 1) هیچ اتصال خروجی‌ای
    # نمی‌گیرد — netconvert هشدار «Lane not connected» می‌دهد و خودروهایی که
    # روی آن خط قرار می‌گیرند، درست قبل از تقاطع مجبور به تغییر خط اضطراری
    # می‌شوند (دقیقاً همان teleportهای «خط اشتباه» که در بازرسی اولیه دیده
    # شد). راه‌حل: هر دو خط (۰ و ۱) صریحاً به‌صورت موازی وصل می‌شوند — سومو
    # صفت‌های دیگر (مثل pass) را روی یک <connection> بدون fromLane/toLane
    # صریح نمی‌پذیرد.
    con_tree = ET.parse(con_path)
    con_root = con_tree.getroot()
    for eid, frm, to, lanes in ring_edge_ids:
        for next_eid, _, next_to, next_lanes in [t for t in ring_edge_ids if t[1] == to]:
            for lane in range(min(lanes, next_lanes)):
                c = ET.SubElement(con_root, "connection")
                c.set("from", eid)
                c.set("to", next_eid)
                c.set("fromLane", str(lane))
                c.set("toLane", str(lane))
                c.set("pass", "true")

    # اتصال ورود: یال‌های ورودی موجود -> اولین یال حلقهٔ آغازشونده از همان گره
    # اتصال خروج: یال حلقهٔ رسیده به گره -> یال‌های خروجی موجود
    # (بدون این، netconvert چون فایل اتصالات صریح است، این مسیرهای تازه را
    # خودکار حدس نمی‌زند و jtrrouter با خطای «not connected» متوقف می‌شود.)
    #
    # نکتهٔ دوم (رفع باگ): اگر یال ورودی/خروجی از قبل اتصالات صریحِ
    # لِین‌دار داشته باشد (اکثر یال‌های این تقاطع دارند)، netconvert یک
    # اتصال تازهٔ بدون fromLane/toLane را بی‌صدا نادیده می‌گیرد (نه خطا، نه
    # هشدار) — دقیقاً همان چیزی که این‌جا رخ داد. راه‌حل: fromLane/toLane
    # صریح، با گرد کردن به کوچک‌ترین تعداد خط طرفین.
    def n_lanes_of(edge_id: str) -> int:
        el = edg_root.find(f"./edge[@id='{edge_id}']")
        return int(el.get("numLanes", "1")) if el is not None else 1

    def add_manual_connection(frm, to):
        n = min(n_lanes_of(frm), n_lanes_of(to))
        for lane in range(n):
            c = ET.SubElement(con_root, "connection")
            c.set("from", frm)
            c.set("to", to)
            c.set("fromLane", str(lane))
            c.set("toLane", str(lane))

    for key, node_id in RING_NODES.items():
        ring_starts_here = [eid for eid, frm, to, lanes in ring_edge_ids if frm == node_id]
        ring_ends_here = [eid for eid, frm, to, lanes in ring_edge_ids if to == node_id]
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
