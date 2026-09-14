#!/usr/bin/env python
"""
فاز ۴ — سناریوی S5 (ترکیبی/خلاقانه): دو ایدهٔ ابتکاری، هرکدام مبتنی بر
زیرساخت حلقهٔ گردشی S3 (رجوع به scenarios/S3_roundabout/build_network.py
برای توجیه کامل روش «افزودن حلقه بدون حذف توپولوژی قبلی»).

طبق `scenarios/S5_hybrid/README.md`، از سه ایدهٔ ثبت‌شده، دو ایدهٔ زیر
انتخاب و ساخته شدند (ایدهٔ سوم — بازکردن دهانهٔ مرکزی برای گردش‌های سبک —
با S3-full هم‌پوشانی مفهومی دارد و به نسخهٔ بعدی موکول شد):

  **metering** — میدان کوچک (دقیقاً حلقهٔ S3-constrained) + یک چراغ
  متردهندهٔ تک‌گرهی روی پای غالب (غرب — دریافت‌کنندهٔ ترافیک گردشی از عرشهٔ
  پرترددِ پل). توجیه مهندسی: میدان به‌تنهایی در تقاضای بالا ممکن است با
  ورود پیوستهٔ ترافیک از پای غالب دچار قفل‌شدگی شود؛ متردهنده نرخ ورود را
  کنترل می‌کند.

  **oneway_priority** — همان حلقه + یک اتصال مستقیم دوطرفهٔ شمال-جنوب
  (بای‌پس) با اولویت حتی بالاتر از خودِ حلقه، برای عبور مستقیم بلوار سیدی
  بدون نیاز به ورود به چرخهٔ گردشی. برخلاف وترِ شرق-غرب S3-full، این اتصال
  **نیازی به بازشدن دهانهٔ مرکزی پل ندارد** (بلوار سیدی همین حالا هم‌سطح و
  زیر پل عبور می‌کند) — پس مشروط به تأیید سازه‌ای نیست.

اجرا: `python scenarios/S5_hybrid/build_network.py`
"""
from __future__ import annotations

import importlib.util
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


def fix_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def _load_s3_module():
    spec = importlib.util.spec_from_file_location(
        "s3build", ROOT / "scenarios" / "S3_roundabout" / "build_network.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build_ring_plain(s3, plain_prefix: pathlib.Path) -> tuple[ET.ElementTree, ET.ElementTree, ET.ElementTree, dict]:
    """دقیقاً همان مراحل build_variant("constrained") در S3، اما بدون بازسازی
    شبکه در پایان — تا این اسکریپت بتواند پیش از netconvert، تغییرات
    اضافهٔ خودش (متردهنده یا بای‌پس) را هم اعمال کند."""
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
    coords = {k: s3.node_coord(nod_root, v) for k, v in s3.RING_NODES.items()}

    edg_tree = ET.parse(edg_path)
    edg_root = edg_tree.getroot()
    ring_edge_ids = []

    def add_ring_edge(eid, frm_key, to_key):
        frm, to = s3.RING_NODES[frm_key], s3.RING_NODES[to_key]
        el = ET.SubElement(edg_root, "edge")
        el.set("id", eid)
        el.set("from", frm)
        el.set("to", to)
        el.set("numLanes", s3.RING_LANES)
        el.set("speed", s3.RING_SPEED)
        el.set("priority", "50")
        el.set("shape", s3.fmt_shape(s3.arc_shape(coords[frm_key], coords[to_key])))
        ring_edge_ids.append((eid, frm, to))
        return el

    for i in range(len(s3.RING_ORDER)):
        a, b = s3.RING_ORDER[i], s3.RING_ORDER[(i + 1) % len(s3.RING_ORDER)]
        add_ring_edge(f"s3_ring_{a}_{b}", a, b)
    edg_tree.write(edg_path, encoding="UTF-8", xml_declaration=True)

    # (رجوع به یادداشت رفع باگ مشابه در S3_roundabout/build_network.py: هر دو
    # خط یال ۲خطهٔ حلقه باید صریحاً وصل شوند، وگرنه خط دوم بی‌اتصال می‌ماند)
    con_tree = ET.parse(con_path)
    con_root = con_tree.getroot()
    n_ring_lanes = int(s3.RING_LANES)
    for eid, frm, to in ring_edge_ids:
        for next_eid, _, next_to in [(e2, f2, t2) for e2, f2, t2 in ring_edge_ids if f2 == to]:
            for lane in range(n_ring_lanes):
                c = ET.SubElement(con_root, "connection")
                c.set("from", eid)
                c.set("to", next_eid)
                c.set("fromLane", str(lane))
                c.set("toLane", str(lane))
                c.set("pass", "true")

    def n_lanes_of(edge_id: str) -> int:
        el = edg_root.find(f"./edge[@id='{edge_id}']")
        return int(el.get("numLanes", "1")) if el is not None else 1

    def add_manual_connection(frm, to):
        # رفع همان باگ S3: بدون fromLane/toLane صریح، netconvert اتصال تازه
        # را برای یال‌هایی که از قبل اتصال صریح دارند بی‌صدا نادیده می‌گیرد.
        n = min(n_lanes_of(frm), n_lanes_of(to))
        for lane in range(n):
            c = ET.SubElement(con_root, "connection")
            c.set("from", frm)
            c.set("to", to)
            c.set("fromLane", str(lane))
            c.set("toLane", str(lane))

    for key, node_id in s3.RING_NODES.items():
        ring_starts_here = [eid for eid, frm, to in ring_edge_ids if frm == node_id]
        ring_ends_here = [eid for eid, frm, to in ring_edge_ids if to == node_id]
        for in_edge in s3.TAP_IN[key]:
            for ring_eid in ring_starts_here:
                add_manual_connection(in_edge, ring_eid)
        for ring_eid in ring_ends_here:
            for out_edge in s3.TAP_OUT[key]:
                add_manual_connection(ring_eid, out_edge)
    con_tree.write(con_path, encoding="UTF-8", xml_declaration=True)

    return nod_tree, edg_tree, con_tree, coords


def build_metering(s3, cycle_time: int | None = 20, out_name: str = "seyedi_S5_metering.net.xml",
                    plain_name: str = "seyedi_s5_metering") -> pathlib.Path:
    """میدان S3-constrained + چراغ متردهندهٔ تک‌گرهی روی پای غالب (غرب).

    `cycle_time` قابل‌پارامتر شد (نشست ۴) تا `tune_metering_cycle.py` بتواند
    چند سیکل کاندید را بسازد و با اجرای تجربی کوتاه بهترین را انتخاب کند —
    به‌جای یک عدد ثابت دلخواه؛ رجوع به README همین فولدر برای نتیجهٔ آزمایش
    و سیکل نهایی انتخاب‌شده."""
    plain_prefix = SCEN_DIR / "plain" / plain_name
    nod_tree, edg_tree, con_tree, coords = build_ring_plain(s3, plain_prefix)

    # گرهٔ غرب را چراغ متردهنده می‌کنیم — همان تکنیک S1: بازتایپ گره به
    # traffic_light و واگذاری فازبندی پیش‌فرض به netconvert؛ طول سیکل با
    # --tls.cycle.time کوتاه (متردهنده‌های واقعی معمولاً سیکل کوتاه دارند
    # تا صف پشت آن‌ها طولانی نشود) به‌جای سیکل وبستر S1 تنظیم می‌شود.
    nod_path = plain_prefix.with_suffix(".nod.xml")
    nod_root = nod_tree.getroot()
    metered_node_id = s3.RING_NODES["W"]
    for n in nod_root.findall("node"):
        if n.get("id") == metered_node_id:
            n.set("type", "traffic_light")
            n.set("tl", metered_node_id)
    nod_tree.write(nod_path, encoding="UTF-8", xml_declaration=True)

    net_dir = SCEN_DIR / "network"
    net_dir.mkdir(parents=True, exist_ok=True)
    out_net = net_dir / out_name
    netconvert = SUMO_HOME / "bin" / "netconvert.exe"
    cmd = [
        str(netconvert),
        "--node-files", str(nod_path),
        "--edge-files", str(plain_prefix.with_suffix(".edg.xml")),
        "--connection-files", str(plain_prefix.with_suffix(".con.xml")),
        "--tllogic-files", str(plain_prefix.with_suffix(".tll.xml")),
        "--type-files", str(TYPEMAP),
        "--output-file", str(out_net),
        "--no-turnarounds", "true",
        "--tls.default-type", "static",
    ]
    # نکتهٔ حیاتی (رفع باگ نشست ۴): netconvert سیکل هدف را وقتی با حداقل
    # سبز/زرد هر فاز سازگار نباشد **بی‌صدا نادیده می‌گیرد** — فقط یک هشدار
    # چاپ می‌کند («cannot be adapted») و به سیکل پیش‌فرض خودش برمی‌گردد؛
    # cycle_time=None یعنی «از همین رفتار پیش‌فرض استفاده کن» (بدون فلگ)،
    # نه یک مقدار نامعتبر. هر فراخوانی باید تلLogic تولیدشده را بازرسی کند
    # تا سیکل واقعاً اعمال‌شده تأیید شود (رجوع به tune_metering_cycle.py).
    if cycle_time is not None:
        cmd += ["--tls.cycle.time", str(cycle_time)]
    print("[run]", " ".join(cmd))
    subprocess.run(cmd, check=True)
    print(f"[ok] نوشته شد: {out_net}")
    return out_net


def _build_bypass_variant(s3, *, plain_name: str, out_name: str, bypass_priority: int,
                           unconditional: bool, bypass_junction_radius: float = 10.0) -> pathlib.Path:
    """هستهٔ مشترک ساخت بای‌پس شمال-جنوب، با اولویت و نوع حق‌تقدم قابل‌پارامتر —
    تا `build_oneway_priority` (حق‌تقدم بدون قیدوشرط) و `build_oneway_yield`
    (حق‌تقدم عادی/میانه، بدون pass، رجوع به بخش ۱۲ گزارش) یک پیاده‌سازی را
    به‌اشتراک بگذارند، نه دو کپی مجزا."""
    plain_prefix = SCEN_DIR / "plain" / plain_name
    nod_tree, edg_tree, con_tree, coords = build_ring_plain(s3, plain_prefix)

    edg_path = plain_prefix.with_suffix(".edg.xml")
    con_path = plain_prefix.with_suffix(".con.xml")
    edg_root = edg_tree.getroot()
    con_root = con_tree.getroot()

    s_id = s3.RING_NODES["S"]

    nod_path = plain_prefix.with_suffix(".nod.xml")
    nod_root = nod_tree.getroot()
    for n in nod_root.findall("node"):
        if n.get("id") == s_id:
            n.set("radius", str(bypass_junction_radius))
    nod_tree.write(nod_path, encoding="UTF-8", xml_declaration=True)

    def add_bypass(eid, frm_key, to_key):
        el = ET.SubElement(edg_root, "edge")
        el.set("id", eid)
        el.set("from", s3.RING_NODES[frm_key])
        el.set("to", s3.RING_NODES[to_key])
        el.set("numLanes", "1")
        el.set("speed", s3.RING_SPEED)
        el.set("priority", str(bypass_priority))
        el.set("shape", s3.fmt_shape([coords[frm_key], coords[to_key]]))
        return eid

    bypass_ns = add_bypass("s5_bypass_N_S", "N", "S")
    bypass_sn = add_bypass("s5_bypass_S_N", "S", "N")
    edg_tree.write(edg_path, encoding="UTF-8", xml_declaration=True)

    for eid, in_edges, out_edges in [
        (bypass_ns, s3.TAP_IN["N"], s3.TAP_OUT["S"]),
        (bypass_sn, s3.TAP_IN["S"], s3.TAP_OUT["N"]),
    ]:
        for in_edge in in_edges:
            c = ET.SubElement(con_root, "connection")
            c.set("from", in_edge)
            c.set("to", eid)
            c.set("fromLane", "0")
            c.set("toLane", "0")
            if unconditional:
                c.set("pass", "true")
        for out_edge in out_edges:
            c = ET.SubElement(con_root, "connection")
            c.set("from", eid)
            c.set("to", out_edge)
            c.set("fromLane", "0")
            c.set("toLane", "0")
    con_tree.write(con_path, encoding="UTF-8", xml_declaration=True)

    net_dir = SCEN_DIR / "network"
    net_dir.mkdir(parents=True, exist_ok=True)
    out_net = net_dir / out_name
    netconvert = SUMO_HOME / "bin" / "netconvert.exe"
    cmd = [
        str(netconvert),
        "--node-files", str(plain_prefix.with_suffix(".nod.xml")),
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


def build_oneway_priority(s3, bypass_junction_radius: float = 10.0) -> pathlib.Path:
    """میدان S3-constrained + بای‌پس مستقیم شمال-جنوب با اولویت بالاتر از حلقه
    (priority=80، `pass="true"` — حق‌تقدم بدون قیدوشرط).

    **رفع باگ هندسی (نشست ۴):** ساخت اولیه در ساخت شبکه هشدار زیر را از
    netconvert می‌گرفت: «Intersecting left turns at junction 6711509176 from
    lane s5_bypass_N_S_0 and lane 610531293#0-AddedOffRampEdge_1 (increase
    junction radius to avoid this)». علت: در نبود یک `radius` صریح روی گرهٔ
    S، netconvert شعاع تقاطع را کوچک محاسبه می‌کند و مسیرهای پیچشیِ داخلیِ دو
    حرکت گردش-به-چپِ متفاوت (بای‌پس تازه‌افزوده و لِینِ دومِ رمپِ موجود) در
    فضای کوچک همدیگر را قطع می‌کنند. راه‌حل مستقیماً از پیشنهاد خودِ
    netconvert گرفته شده: تنظیم `radius` صریح روی گرهٔ S (۱۰ متر، با
    حاشیهٔ اطمینان روی حداقل تجربی ۸ متر).

    **نتیجهٔ صادقانهٔ این رفع (نشست ۴):** هشدار کاملاً حذف شد، اما بهبود
    قابل‌اتکایی در نتیجهٔ شبیه‌سازی‌شده نداد و یک ریسک دنبالهٔ جدی (۱ از ۱۰
    seed با فروپاشی کامل) آشکار کرد — رجوع به بخش ۷ گزارش (مکانیزم ۵).
    این نشان داد ریشهٔ اصلی مشکل رفتاری است (حق‌تقدم بدون قیدوشرط از یک
    حرکت پرسرعت روی یک گرهٔ شلوغ)، نه صرفاً هندسی؛ `build_oneway_yield`
    زیر دقیقاً همین فرضیه را آزمون می‌کند."""
    return _build_bypass_variant(
        s3, plain_name="seyedi_s5_oneway", out_name="seyedi_S5_oneway.net.xml",
        bypass_priority=80, unconditional=True, bypass_junction_radius=bypass_junction_radius)


def build_oneway_yield(s3, bypass_junction_radius: float = 10.0) -> pathlib.Path:
    """آزمون «کنترل فعال» فصل ۱۲ گزارش (نشست ۵): همان بای‌پس، اما به‌جای
    حق‌تقدم بدون قیدوشرط (priority=80 + pass="true")، حق‌تقدم آن به زیر
    حلقه (priority=30 < ۵۰ حلقه) کاهش می‌یابد و `pass="true"` حذف می‌شود —
    یعنی بای‌پس دیگر «همیشه برنده» نیست، باید مثل هر تقاطع priority عادی
    این شبکه (S0/S4) برای ورود جای خالی پیدا کند و حق‌تقدم واقعی بدهد.

    فرضیهٔ آزمون (مستقیماً از یافتهٔ نشست ۴): چون رفع صرفاً هندسی
    (`build_oneway_priority`) کمکی نکرد، ریشهٔ اصلی «حق‌تقدم بدون قیدوشرط
    روی یک تقاطع شلوغ + رفتار تهاجمی» است، نه هندسهٔ لِین داخلی؛ اگر این
    فرضیه درست باشد، حذف حق‌تقدم بدون قیدوشرط باید برخورد/ریسک دنباله را
    کاهش دهد — به‌قیمت افزایش تأخیر بای‌پس (چون دیگر تضمینی برای عبور آزاد
    ندارد). اگر باز هم بهبود ندهد، شاهد قوی‌تری برای نتیجه‌گیری «این محل
    بدون جداسازی ترازی کامل قابل‌حل نیست» به‌دست می‌آید."""
    return _build_bypass_variant(
        s3, plain_name="seyedi_s5_oneway_yield", out_name="seyedi_S5_oneway_yield.net.xml",
        bypass_priority=30, unconditional=False, bypass_junction_radius=bypass_junction_radius)


def main() -> None:
    fix_console_encoding()
    s3 = _load_s3_module()
    # سیکل ۲۰ ثانیه با جست‌وجوی تجربی `tune_metering_cycle.py` بازآزمایی شد:
    # ۶ کاندید (۲۰/۳۰/۴۰/۵۰/۶۰ ثانیه + پیش‌فرض netconvert=۹۰ ثانیه) با ۳ seed
    # سبک در λ=۱.۰/۱.۴ اجرا شدند؛ در λ=۱.۴ (نقطهٔ تمایزدهنده)، ۲۰ ثانیه
    # بهترین رتبهٔ نرمال‌شده را روی هر سهٔ معیار گرفت (رجوع به
    # scenarios/S5_hybrid/tune_metering_cycle_result.csv و README برای جدول
    # کامل و بحث دربارهٔ واریانس بالای این جست‌وجوی سبک). نتیجه: انتخاب
    # اولیهٔ ۲۰ ثانیه تأیید تجربی گرفت، نه یک عدد صرفاً دلخواه.
    build_metering(s3, cycle_time=20)
    # radius=10 روی گرهٔ جنوب، رفع مستند تداخل هندسی بای‌پس (رجوع به
    # docstring build_oneway_priority بالا).
    build_oneway_priority(s3)
    # آزمون کنترل فعال (نشست ۵، بخش ۱۲ گزارش): بای‌پس با حق‌تقدم عادی
    # به‌جای بدون‌قیدوشرط — رجوع به docstring build_oneway_yield بالا.
    build_oneway_yield(s3)


if __name__ == "__main__":
    main()
