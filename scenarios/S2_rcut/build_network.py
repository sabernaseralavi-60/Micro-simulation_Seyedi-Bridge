#!/usr/bin/env python
"""
فاز ۴ — سناریوی S2 (نسخهٔ ۲: حذف گردش چپ + دوربرگردان فیزیکی میانهٔ عرشه).

این نسخه کامل RCUT/Median U-Turn را پیاده می‌کند:
1. (مشترک با v1) حذف ۵ اتصال گردش چپ واقعی زیر پل از plain-XML.
2. دو یال بلند عرشه (۴۱۰۲۴۷۴۹۲ شرق‌گرد و ۶۲۷۰۰۸۱۹۲ غرب‌گرد) هرکدام در دو نقطه
   (±D متر از مرکز میدانچهٔ ویوینگ، با درون‌یابی طول‌کمانی روی شکل واقعی یال،
   نه یک خط راست ساده) شکافته می‌شوند — هر یال به ۳ پاره تقسیم می‌شود.
3. در هر نقطهٔ شکاف، یک یال کوتاه دوربرگردان (U-turn) افزوده می‌شود که مسیر
   عبوری را به مسیر مخالف وصل می‌کند — دقیقاً بازنمایی یک دوربرگردان میانهٔ
   واقعی (Michigan Left): خودرو عبوری/راست‌گرد اصلی حذف‌شده‌اش را با
   «عبور از تقاطع → دوربرگردان → بازگشت → گردش راست» جایگزین می‌کند.
4. تقاضا (turns.xml) در هر نقطهٔ دوربرگردان یک قاعدهٔ صریح می‌گیرد: سهمی از
   ترافیک عبوری (برابر با turn_ratio_baseline.left، همان سهم گردش چپ حذف‌شده)
   دوربرگردان می‌زند؛ بقیه عبوری می‌مانند — طبق مکانیزم عمومی جدید
   `extra_turn_rules` در src/03_build_demand.py.

فاصلهٔ دوربرگردان از مرکز (D) متغیر حساسیت CLAUDE.md است؛ این اسکریپت سه
شبکهٔ مستقل برای D ∈ {۱۵۰, ۲۵۰, ۳۵۰} متر می‌سازد. سناریوی «built» رسمی در
config/scenarios.yml از D=۲۵۰ (مبنا) استفاده می‌کند؛ ۱۵۰/۳۵۰ برای تحلیل
حساسیت فاز بعد آماده نگه داشته می‌شوند.

اجرا: `python scenarios/S2_rcut/build_network.py`
"""
from __future__ import annotations

import math
import pathlib
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

import sumolib
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
SUMO_HOME = ROOT / ".venv" / "Lib" / "site-packages" / "sumo"
BASE_PLAIN_PREFIX = ROOT / "network" / "plain" / "seyedi"
BASE_NET = ROOT / "network" / "seyedi.net.xml"
SCEN_DIR = pathlib.Path(__file__).resolve().parent
TYPEMAP = ROOT / "config" / "typemap" / "urban_ir.typ.xml"
ASSUMPTIONS = ROOT / "config" / "assumptions.yml"

WEAVE_CENTER = (3200, 2750)

# گرهٔ انشعاب -> (یال ورودی, یال خروجیِ چپ‌گرد) — همان فهرست v1
LEFT_TURN_CONNECTIONS = {
    "6711509165": ("1165329134", "643263251"),
    "6711509176": ("610531293#0-AddedOffRampEdge", "713864643"),
    "6711509163": ("627154371#0-AddedOffRampEdge", "627633586"),
    "6711509162": ("627154372#0", "643263250"),
    "6403676806": ("627167743#0", "683662933"),
}

# دو یال بلند عرشه که دوربرگردان روی آن‌ها ساخته می‌شود
EB_EDGE = "410247492"   # شرق‌گرد (از غرب به شرق)
WB_EDGE = "627008192"   # غرب‌گرد (از نزدیک پل به غرب)


def fix_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def cumulative_lengths(shape: list[tuple[float, float]]) -> list[float]:
    d = [0.0]
    for i in range(1, len(shape)):
        x0, y0 = shape[i - 1][:2]
        x1, y1 = shape[i][:2]
        d.append(d[-1] + math.hypot(x1 - x0, y1 - y0))
    return d


def closest_position_on_polyline(shape, query) -> float:
    """موقعیت طول‌کمانی نزدیک‌ترین نقطهٔ روی چندخط به query (برای یافتن مرکز)."""
    best = None
    d = 0.0
    for i in range(len(shape) - 1):
        x0, y0 = shape[i][:2]
        x1, y1 = shape[i + 1][:2]
        qx, qy = query
        dx, dy = x1 - x0, y1 - y0
        seglen = math.hypot(dx, dy)
        seglen2 = dx * dx + dy * dy
        t = 0.0 if seglen2 == 0 else max(0.0, min(1.0, ((qx - x0) * dx + (qy - y0) * dy) / seglen2))
        px, py = x0 + t * dx, y0 + t * dy
        dist = math.hypot(qx - px, qy - py)
        pos = d + t * seglen
        if best is None or dist < best[0]:
            best = (dist, pos)
        d += seglen
    return best[1]


def split_shape(shape: list[tuple[float, float]], pos: float):
    """شکافتن چندخط در موقعیت طول‌کمانی pos. برمی‌گرداند: (نقطهٔ شکاف, پارهٔ قبل, پارهٔ بعد)."""
    d = 0.0
    for i in range(len(shape) - 1):
        x0, y0 = shape[i][:2]
        x1, y1 = shape[i + 1][:2]
        seg = math.hypot(x1 - x0, y1 - y0)
        if d + seg >= pos or i == len(shape) - 2:
            t = 0.0 if seg == 0 else max(0.0, min(1.0, (pos - d) / seg))
            px, py = x0 + t * (x1 - x0), y0 + t * (y1 - y0)
            before = shape[: i + 1] + [(px, py)]
            after = [(px, py)] + shape[i + 1:]
            return (px, py), before, after
        d += seg
    return shape[-1], shape, [shape[-1]]


def fmt_shape(shape, z: str | None = None) -> str:
    """z: اگر داده شود، به هر نقطه افزوده می‌شود — لازم برای این دو یال
    چون هر دو کاملاً روی عرشهٔ پل (z=4.00 ثابت، بازرسی‌شده در seyedi.nod.xml)
    قرار دارند؛ بدون z صریح، netconvert آن را ۰ فرض می‌کند و در محل اتصال به
    گره‌های واقعی (که z=4.00 دارند) یک شیب کاذب می‌سازد."""
    if z is None:
        return " ".join(f"{x:.2f},{y:.2f}" for x, y in shape)
    return " ".join(f"{x:.2f},{y:.2f},{z}" for x, y in shape)


def build_for_distance(net, D: float, out_dir: pathlib.Path, left_pct: float) -> pathlib.Path:
    plain_prefix = out_dir / "plain" / "seyedi_s2"
    plain_prefix.parent.mkdir(parents=True, exist_ok=True)
    for suffix in (".nod.xml", ".edg.xml", ".con.xml", ".tll.xml", ".typ.xml"):
        src = BASE_PLAIN_PREFIX.with_suffix(suffix)
        if src.exists():
            shutil.copy(src, plain_prefix.with_suffix(suffix))

    # --- گام ۱: حذف اتصال‌های گردش چپ (مشترک با v1) ---
    con_path = plain_prefix.with_suffix(".con.xml")
    con_tree = ET.parse(con_path)
    con_root = con_tree.getroot()
    for node_id, (in_edge, left_edge) in LEFT_TURN_CONNECTIONS.items():
        to_remove = [c for c in con_root.findall("connection")
                     if c.get("from") == in_edge and c.get("to") == left_edge]
        if not to_remove:
            raise RuntimeError(f"اتصال چپ‌گرد {in_edge}->{left_edge} برای گرهٔ {node_id} پیدا نشد.")
        for c in to_remove:
            con_root.remove(c)

    # --- گام ۲: محاسبهٔ نقاط شکاف روی هر دو یال عرشه ---
    eb = net.getEdge(EB_EDGE)
    wb = net.getEdge(WB_EDGE)
    eb_shape = list(eb.getShape())
    wb_shape = list(wb.getShape())
    eb_center_pos = closest_position_on_polyline(eb_shape, WEAVE_CENTER)
    wb_center_pos = closest_position_on_polyline(wb_shape, WEAVE_CENTER)

    # روی EB (غرب->شرق): موقعیت با x افزایش می‌یابد -> غرب=موقعیت کوچک‌تر
    eb_west_pos = eb_center_pos - D
    eb_east_pos = eb_center_pos + D
    # روی WB (نزدیک‌پل->غرب): موقعیت با فاصله از پل (به‌سمت غرب) افزایش می‌یابد
    # -> شرق=موقعیت کوچک‌تر (نزدیک‌تر به ابتدا)، غرب=موقعیت بزرگ‌تر
    wb_east_pos = wb_center_pos - D
    wb_west_pos = wb_center_pos + D

    for pos, name in [(eb_west_pos, "EB west"), (eb_east_pos, "EB east")]:
        if not (0 < pos < eb.getLength()):
            raise ValueError(f"نقطهٔ شکاف {name} در D={D} خارج از طول یال {EB_EDGE} است ({pos:.1f}m).")
    for pos, name in [(wb_east_pos, "WB east"), (wb_west_pos, "WB west")]:
        if not (0 < pos < wb.getLength()):
            raise ValueError(f"نقطهٔ شکاف {name} در D={D} خارج از طول یال {WB_EDGE} است ({pos:.1f}m).")

    _, eb_first, eb_rest = split_shape(eb_shape, eb_west_pos)
    _, eb_mid, eb_last = split_shape(eb_rest, eb_east_pos - eb_west_pos)
    _, wb_first, wb_rest = split_shape(wb_shape, wb_east_pos)
    _, wb_mid, wb_last = split_shape(wb_rest, wb_west_pos - wb_east_pos)

    node_west_eb = "s2_west_split_eb"
    node_east_eb = "s2_east_split_eb"
    node_east_wb = "s2_east_split_wb"
    node_west_wb = "s2_west_split_wb"

    # --- گام ۳: افزودن گره‌های جدید ---
    nod_path = plain_prefix.with_suffix(".nod.xml")
    nod_tree = ET.parse(nod_path)
    nod_root = nod_tree.getroot()
    # نکتهٔ حیاتی (طبق هشدار CLAUDE.md دربارهٔ جدایی تراز): هر ۴ گرهٔ ابتدایی/
    # انتهاییِ این دو یال روی عرشهٔ پل با z=4.00 ثبت شده‌اند (بازرسی مستقیم
    # network/plain/seyedi.nod.xml) — گره‌های جدید شکاف نیز باید همان ارتفاع
    # را بگیرند، وگرنه netconvert بین آن‌ها و انتهای واقعی یال شیب کاذب
    # می‌سازد (دقیقاً همین خطا یک‌بار رخ داد و در بازبینی این اسکریپت اصلاح شد).
    BRIDGE_Z = "4.00"
    for nid, pt in [(node_west_eb, eb_first[-1]), (node_east_eb, eb_mid[-1]),
                     (node_east_wb, wb_first[-1]), (node_west_wb, wb_mid[-1])]:
        el = ET.SubElement(nod_root, "node")
        el.set("id", nid)
        el.set("x", f"{pt[0]:.2f}")
        el.set("y", f"{pt[1]:.2f}")
        el.set("z", BRIDGE_Z)
        el.set("type", "priority")
    nod_tree.write(nod_path, encoding="UTF-8", xml_declaration=True)

    # --- گام ۴: جایگزینی دو یال بلند با ۳+۳ پاره + ۲ یال دوربرگردان ---
    edg_path = plain_prefix.with_suffix(".edg.xml")
    edg_tree = ET.parse(edg_path)
    edg_root = edg_tree.getroot()

    eb_el = next(e for e in edg_root.findall("edge") if e.get("id") == EB_EDGE)
    wb_el = next(e for e in edg_root.findall("edge") if e.get("id") == WB_EDGE)
    eb_attrs = dict(eb_el.attrib)
    wb_attrs = dict(wb_el.attrib)
    eb_from, eb_to = eb_attrs["from"], eb_attrs["to"]
    wb_from, wb_to = wb_attrs["from"], wb_attrs["to"]
    edg_root.remove(eb_el)
    edg_root.remove(wb_el)

    def add_edge(eid, frm, to, shape_pts, base_attrs):
        el = ET.SubElement(edg_root, "edge")
        el.set("id", eid)
        el.set("from", frm)
        el.set("to", to)
        el.set("numLanes", base_attrs["numLanes"])
        if "speed" in base_attrs:
            el.set("speed", base_attrs["speed"])
        if "priority" in base_attrs:
            el.set("priority", base_attrs["priority"])
        el.set("shape", fmt_shape(shape_pts, z=BRIDGE_Z))
        return el

    add_edge(EB_EDGE, eb_from, node_west_eb, eb_first, eb_attrs)
    add_edge(f"{EB_EDGE}_mid", node_west_eb, node_east_eb, eb_mid, eb_attrs)
    add_edge(f"{EB_EDGE}_east", node_east_eb, eb_to, eb_last, eb_attrs)

    add_edge(WB_EDGE, wb_from, node_east_wb, wb_first, wb_attrs)
    add_edge(f"{WB_EDGE}_mid", node_east_wb, node_west_wb, wb_mid, wb_attrs)
    add_edge(f"{WB_EDGE}_west", node_west_wb, wb_to, wb_last, wb_attrs)

    # یال‌های دوربرگردان (کوتاه، ۱ خط، سرعت پایین‌تر برای مانور U-turn، روی همان تراز عرشه)
    UTURN_SPEED = "8.33"  # 30 km/h
    add_edge("s2_uturn_west", node_west_wb, node_west_eb, [wb_mid[-1], eb_first[-1]], {"numLanes": "1", "speed": UTURN_SPEED})
    add_edge("s2_uturn_east", node_east_eb, node_east_wb, [eb_mid[-1], wb_first[-1]], {"numLanes": "1", "speed": UTURN_SPEED})
    edg_tree.write(edg_path, encoding="UTF-8", xml_declaration=True)

    # --- گام ۵: به‌روزرسانی اتصالات موجود که به انتهای یال‌های اصلی اشاره می‌کردند ---
    for c in con_root.findall("connection"):
        if c.get("from") == EB_EDGE:
            c.set("from", f"{EB_EDGE}_east")
        if c.get("from") == WB_EDGE:
            c.set("from", f"{WB_EDGE}_west")
    con_tree.write(con_path, encoding="UTF-8", xml_declaration=True)

    # --- گام ۶: بازسازی شبکه ---
    net_dir = out_dir / "network"
    net_dir.mkdir(parents=True, exist_ok=True)
    out_net = net_dir / f"seyedi_S2_D{int(D)}.net.xml"
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
    print(f"[ok] نوشته شد: {out_net} (D={D}m)")
    return out_net


def main() -> None:
    fix_console_encoding()
    net = sumolib.net.readNet(str(BASE_NET))
    with open(ASSUMPTIONS, "r", encoding="utf-8") as f:
        assumptions = yaml.safe_load(f)
    left_pct = assumptions["traffic_control"]["turn_ratio_baseline"]["value"]["left"]

    for D in (150, 250, 350):
        build_for_distance(net, D, SCEN_DIR, left_pct)


if __name__ == "__main__":
    main()
