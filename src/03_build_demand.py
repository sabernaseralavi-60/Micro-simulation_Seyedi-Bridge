#!/usr/bin/env python
"""
فاز ۱-۲ — ساخت تقاضای فرضی چندناوگانی با jtrrouter (نه ماتریس OD).

توجیه روش (برای گزارش): برای یک تقاطع منفرد، حجم ورودی هر پا + نسبت گردش‌ها
داده‌ای به‌مراتب کم‌نیازتر از ماتریس OD کامل است و با شواهد قابل‌دسترس (شمارش
ورودی، برداشت چشمی از تصاویر) سازگارتر است؛ رجوع به CLAUDE.md فاز ۱.

این اسکریپت به‌طور کامل برنامه‌نویسی‌شده است (طبق قاعدهٔ سخت ۱، هیچ XML دستی):
1. demand/flows.xml را از config/assumptions.yml (حجم ورودی هر پا) و
   config/vtypes.yml (ترکیب ناوگان: سواری/موتورسیکلت/تاکسی/وانت/اتوبوس/کامیونت
   + پارامترهای رفتاری) می‌سازد.
2. برای هر پای ورودی، اولین تقاطع واقعی (out-degree >= 2) در مسیر را پیدا
   می‌کند و بر اساس زاویهٔ هندسی، گزینه‌های خروجی را «مستقیم/راست/چپ» طبقه‌بندی
   کرده و نسبت گردش پیش‌فرض (config/assumptions.yml -> turn_ratio_baseline) را
   به آن‌ها اختصاص می‌دهد -> demand/turns.xml.
3. jtrrouter را با flows.xml + turns.xml (+ turn-defaults به‌عنوان fallback در
   سایر تقاطع‌های پایین‌دست) اجرا می‌کند -> demand/routes.rou.xml.

اجرا: `make demand`
"""
from __future__ import annotations

import math
import pathlib
import subprocess
import sys

import sumolib
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
SUMO_HOME = ROOT / ".venv" / "Lib" / "site-packages" / "sumo"
NET_FILE = ROOT / "network" / "seyedi.net.xml"
FLOWS_FILE = ROOT / "demand" / "flows.xml"
TURNS_FILE = ROOT / "demand" / "turns.xml"
ROUTES_FILE = ROOT / "demand" / "routes.rou.xml"
ASSUMPTIONS = ROOT / "config" / "assumptions.yml"
VTYPES_CFG = ROOT / "config" / "vtypes.yml"

ENTRY_EDGES = ["410247492", "412303657#0", "592154956#0", "610531293#0"]
ENTRY_ASSUMPTION_KEY = {
    "410247492": "entry_volume_west",
    "412303657#0": "entry_volume_east",
    "592154956#0": "entry_volume_north",
    "610531293#0": "entry_volume_south",
}


def fix_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def bearing(p_from, p_to) -> float:
    dx, dy = p_to[0] - p_from[0], p_to[1] - p_from[1]
    return math.degrees(math.atan2(dy, dx))


def classify(delta: float) -> str:
    """delta = زاویهٔ نسبی خروجی نسبت به امتداد ورود (۰=مستقیم، +=چپ، -=راست)."""
    d = ((delta + 180) % 360) - 180
    if d > 160 or d < -160:
        return "u_turn"
    if d > 25:
        return "left"
    if d < -25:
        return "right"
    return "through"


def first_branch_edge(entry_edge):
    """پیمایش رو به جلو از یال ورودی تا اولین تقاطع با >=۲ گزینهٔ خروجی."""
    edge = entry_edge
    seen = set()
    while edge.getID() not in seen:
        seen.add(edge.getID())
        to_node = edge.getToNode()
        outs = [e for e in to_node.getOutgoing() if e.getID() != edge.getID()]
        if len(outs) >= 2 or not outs:
            return edge, outs
        edge = outs[0]
    return edge, []


def build_turns(net, ratios: dict) -> str:
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<turns xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
             'xsi:noNamespaceSchemaLocation="http://sumo.dlr.de/xsd/turns_file.xsd">',
             '    <interval begin="0" end="3600">']
    for entry_id in ENTRY_EDGES:
        entry_edge = net.getEdge(entry_id)
        branch_edge, outs = first_branch_edge(entry_edge)
        if not outs:
            continue
        in_bear = bearing(branch_edge.getShape()[0], branch_edge.getShape()[-1])
        classified = []
        for out in outs:
            out_bear = bearing(out.getShape()[0], out.getShape()[-1])
            cls = classify(out_bear - in_bear)
            classified.append((out, cls))

        # اگر uturn هم در گزینه‌ها بود، عملاً حذفش می‌کنیم (نامعتبر برای ترافیک عادی)
        classified = [(o, c) for o, c in classified if c != "u_turn"] or classified
        weights = {o.getID(): ratios.get(c, ratios["through"]) for o, c in classified}
        total = sum(weights.values()) or 1.0
        lines.append(f'        <fromEdge id="{branch_edge.getID()}">')
        for out, cls in classified:
            pct = 100.0 * weights[out.getID()] / total
            lines.append(f'            <!-- {cls} -->')
            lines.append(f'            <toEdge id="{out.getID()}" probability="{pct:.1f}"/>')
        lines.append('        </fromEdge>')
    lines.append('    </interval>')
    lines.append('</turns>')
    return "\n".join(lines)


def build_vtypes_block(vcfg: dict) -> list[str]:
    lines = []
    for vid, params in vcfg["vtypes"].items():
        attrs = " ".join(f'{k}="{v}"' for k, v in params.items())
        lines.append(f'    <vType id="{vid}" {attrs}/>')
    return lines


def build_flows_xml(assumptions: dict, vcfg: dict) -> str:
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
              "<!--",
              "  فاز ۱-۲ — تقاضای فرضی چندناوگانی (Walking Skeleton + ترکیب ناوگان ایران).",
              "  تولید خودکار توسط src/03_build_demand.py از روی assumptions.yml و vtypes.yml.",
              "  دستی ویرایش نکن — رجوع به config/assumptions.yml برای منبع هر عدد.",
              "-->",
              '<routes xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
              'xsi:noNamespaceSchemaLocation="http://sumo.dlr.de/xsd/routes_file.xsd">']
    lines.extend(build_vtypes_block(vcfg))

    demand_cfg = assumptions["demand_baseline_phase1"]
    fleet = vcfg["fleet_composition"]
    flow_id = 0
    approach_name = {"410247492": "west", "412303657#0": "east",
                      "592154956#0": "north", "610531293#0": "south"}
    for edge_id in ENTRY_EDGES:
        total_volume = demand_cfg[ENTRY_ASSUMPTION_KEY[edge_id]]["value"]
        leg = approach_name[edge_id]
        for vt_id, vt_cfg in fleet.items():
            number = round(total_volume * vt_cfg["share"])
            if number <= 0:
                continue
            lines.append(
                f'    <flow id="from_{leg}_{vt_id}.{flow_id}" type="{vt_id}" '
                f'from="{edge_id}" begin="0" end="3600" number="{number}"/>'
            )
            flow_id += 1
    lines.append("</routes>")
    return "\n".join(lines)


def main() -> None:
    fix_console_encoding()
    with open(ASSUMPTIONS, "r", encoding="utf-8") as f:
        a = yaml.safe_load(f)
    with open(VTYPES_CFG, "r", encoding="utf-8") as f:
        vcfg = yaml.safe_load(f)
    ratios_cfg = a["traffic_control"]["turn_ratio_baseline"]["value"]
    ratios = {"through": ratios_cfg["through"], "right": ratios_cfg["right"], "left": ratios_cfg["left"]}

    flows_xml = build_flows_xml(a, vcfg)
    FLOWS_FILE.write_text(flows_xml, encoding="utf-8")
    print(f"[ok] نوشته شد: {FLOWS_FILE}")

    net = sumolib.net.readNet(str(NET_FILE))
    turns_xml = build_turns(net, ratios)
    TURNS_FILE.write_text(turns_xml, encoding="utf-8")
    print(f"[ok] نوشته شد: {TURNS_FILE}")

    jtrrouter = SUMO_HOME / "bin" / "jtrrouter.exe"
    cmd = [
        str(jtrrouter),
        "-n", str(NET_FILE),
        "-r", str(FLOWS_FILE),
        "-t", str(TURNS_FILE),
        "-o", str(ROUTES_FILE),
        "--turn-defaults", "15,70,15",  # fallback برای تقاطع‌های پایین‌دست بدون turns.xml
        "--accept-all-destinations",
        "--seed", "42",
        "--ignore-errors",
    ]
    print("[run]", " ".join(cmd))
    subprocess.run(cmd, check=True)
    print(f"[ok] نوشته شد: {ROUTES_FILE}")


if __name__ == "__main__":
    main()
