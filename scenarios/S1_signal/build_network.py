#!/usr/bin/env python
"""
فاز ۴ — سناریوی S1 (تقاطع چراغ‌دار): ساخت شبکه از روی plain-XML مبنا.

طبق تصمیم ثبت‌شده در config/assumptions.yml -> signal_design_S1: هر گرهٔ ادغام
واقعی (in-degree>=2) درون شعاع میدانچهٔ ویوینگ زیر پل (همان WEAVE_CENTER/RADIUS
فاز ۲) به‌طور مستقل نوع traffic_light می‌گیرد. plain-XML مبنا (network/plain/
seyedi.*، شامل اصلاحات فاز ۲: خط عرشه + zipper) کپی و روی نسخهٔ محلی این
سناریو ویرایش می‌شود — فایل‌های فاز ۲ دست‌نخورده می‌مانند (قاعدهٔ سخت ۲).

**طراحی واقعی فازبندی (نه فقط فازبندی خام netconvert):** ساخت هر نسخه اکنون
دو‌پاسی است — یک پاس اول (auto) صرفاً برای خواندن گروه‌بندی واقعی تعارض
(netconvert) + هندسهٔ واقعی هر گره (طول لاین داخلی، برای همه‌قرمز)، و یک پاس
دوم که برنامهٔ TLS صریحاً طراحی‌شدهٔ src/10_signal_design.py (سبز وزن‌دار طبق
وبستر + همه‌قرمز واقعی) را از طریق plain .tll.xml به netconvert می‌دهد. رجوع
به docstring src/10_signal_design.py برای توجیه کامل روش.

دو نسخهٔ شبکه ساخته می‌شود:
  seyedi_S1_fixed.net.xml    — زمان‌ثابت، سبز از y_i وبستر (نه هیوریستیک خام)
  seyedi_S1_actuated.net.xml — سبزها actuated (minDur/maxDur اصلی SUMO)، فقط
                                همه‌قرمز واقعی اضافه شده

اجرا: `python scenarios/S1_signal/build_network.py` (نیازمند اجرای قبلی
`make webster-timing` برای وجود config/signal_timing_S1.yml)
"""
from __future__ import annotations

import importlib.util
import pathlib
import shutil
import subprocess
import sys
import tempfile
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
ASSUMPTIONS_FILE = ROOT / "config" / "assumptions.yml"

WEAVE_CENTER = (3200, 2750)  # همان مرکز میدانچهٔ ویوینگ فاز ۲ (src/02_patch_geometry.py)
WEAVE_SEARCH_RADIUS = 120


def fix_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def _load_signal_design_module():
    spec = importlib.util.spec_from_file_location(
        "signal_design", ROOT / "src" / "10_signal_design.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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


def rebuild_network(tls_default_type: str | None, out_net: pathlib.Path,
                     cycle_time: float | None, tll_path: pathlib.Path) -> None:
    netconvert = SUMO_HOME / "bin" / "netconvert.exe"
    cmd = [
        str(netconvert),
        "--node-files", str(PLAIN_PREFIX.with_suffix(".nod.xml")),
        "--edge-files", str(PLAIN_PREFIX.with_suffix(".edg.xml")),
        "--connection-files", str(PLAIN_PREFIX.with_suffix(".con.xml")),
        "--tllogic-files", str(tll_path),
        "--type-files", str(TYPEMAP),
        "--output-file", str(out_net),
        "--no-turnarounds", "true",
    ]
    if tls_default_type is not None:
        cmd += ["--tls.default-type", tls_default_type]
    if cycle_time is not None:
        cmd += ["--tls.cycle.time", str(int(round(cycle_time)))]
    print("[run]", " ".join(cmd))
    subprocess.run(cmd, check=True)


def main() -> None:
    fix_console_encoding()
    sd = _load_signal_design_module()

    if not TIMING_FILE.exists():
        raise FileNotFoundError(f"{TIMING_FILE} یافت نشد — ابتدا `make webster-timing` را اجرا کن.")
    with open(TIMING_FILE, "r", encoding="utf-8") as f:
        timing = yaml.safe_load(f)
    cycle_s = timing["cycle_length_s"]["final_used_s"]

    with open(ASSUMPTIONS_FILE, "r", encoding="utf-8") as f:
        a = yaml.safe_load(f)["signal_design_S1"]
    yellow_s = a["yellow_time_s"]["value"]
    clearance_speed = a["clearance_speed_mps"]["value"]
    all_red_bounds = (a["all_red_bounds_s"]["value"]["min"], a["all_red_bounds_s"]["value"]["max"])
    min_green_s = 5.0  # همان کف استفاده‌شده در src/08_webster_timing.py::compute_cycle

    copy_base_plain()
    signalized = retype_merge_nodes_to_signal()
    print(f"[ok] {len(signalized)} گرهٔ ادغام درون میدانچهٔ ویوینگ چراغ‌دار شد: {signalized}")

    NET_DIR.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="s1_auto_") as tmp:
        tmp_dir = pathlib.Path(tmp)
        auto_fixed = tmp_dir / "auto_fixed.net.xml"
        auto_actuated = tmp_dir / "auto_actuated.net.xml"
        base_tll = PLAIN_PREFIX.with_suffix(".tll.xml")

        # پاس اول: صرفاً برای خواندن گروه‌بندی واقعی تعارض + هندسهٔ واقعی
        rebuild_network("static", auto_fixed, cycle_time=cycle_s, tll_path=base_tll)
        rebuild_network("actuated", auto_actuated, cycle_time=None, tll_path=base_tll)

        programs_fixed, clearance_m = sd.harvest_auto_program(auto_fixed, signalized)
        programs_actuated, _ = sd.harvest_auto_program(auto_actuated, signalized)

        node_programs_fixed: dict[str, tuple] = {}
        node_programs_actuated: dict[str, tuple] = {}
        n_real = 0
        for nid in signalized:
            res_f = sd.design_fixed_program(
                programs_fixed[nid], clearance_m[nid], cycle_s, yellow_s,
                clearance_speed, min_green_s, all_red_bounds)
            res_a = sd.design_actuated_program(
                programs_actuated[nid], clearance_m[nid], yellow_s,
                clearance_speed, all_red_bounds)
            if res_f is None:
                continue  # گرهٔ بدون تعارض واقعی (فاز تک‌سبز) — نیازی به طراحی ندارد
            n_real += 1
            phases_f, all_red_f = res_f
            phases_a, all_red_a = res_a
            node_programs_fixed[nid] = (phases_f, "static")
            node_programs_actuated[nid] = (phases_a, "actuated")
            print(f"    گرهٔ واقعی {nid}: همه‌قرمز={all_red_f}s "
                  f"(از طول لاین داخلی {clearance_m[nid]:.1f}m / {clearance_speed}m/s)")

        print(f"[ok] {n_real} گرهٔ تعارض واقعی با روش src/10_signal_design.py بازطراحی شدند "
              f"(از {len(signalized)} گرهٔ چراغ‌دار)")

        # پاس دوم: نسخهٔ نهایی، با برنامهٔ صریح طراحی‌شده در plain .tll.xml
        fixed_tll = PLAIN_PREFIX.parent / "seyedi_s1_fixed.tll.xml"
        actuated_tll = PLAIN_PREFIX.parent / "seyedi_s1_actuated.tll.xml"
        shutil.copy(base_tll, fixed_tll)
        shutil.copy(base_tll, actuated_tll)
        sd.write_tll_override(fixed_tll, node_programs_fixed)
        sd.write_tll_override(actuated_tll, node_programs_actuated)

        # tls.default-type فقط روی گره‌های بدون برنامهٔ صریح در tllogic-files اثر
        # می‌گذارد (همان گره‌های بی‌تعارض تک‌فازه) — برنامهٔ صریح ۵ گرهٔ واقعی
        # دست‌نخورده اعمال می‌شود (آزموده‌شده، رجوع به docstring بالا)
        rebuild_network("static", NET_DIR / "seyedi_S1_fixed.net.xml", cycle_time=None, tll_path=fixed_tll)
        print(f"[ok] نوشته شد: {NET_DIR / 'seyedi_S1_fixed.net.xml'} "
              f"(سیکل هدف وبستر={cycle_s}s، سبز وزن‌دار + همه‌قرمز واقعی)")
        rebuild_network("actuated", NET_DIR / "seyedi_S1_actuated.net.xml", cycle_time=None, tll_path=actuated_tll)
        print(f"[ok] نوشته شد: {NET_DIR / 'seyedi_S1_actuated.net.xml'} "
              f"(actuated اصلی SUMO + همه‌قرمز واقعی)")


if __name__ == "__main__":
    main()
