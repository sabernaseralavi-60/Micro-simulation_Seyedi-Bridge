#!/usr/bin/env python
"""
فاز ۱-۳ — ساخت تقاضای فرضی چندناوگانی با jtrrouter (نه ماتریس OD).

توجیه روش (برای گزارش): برای یک تقاطع منفرد، حجم ورودی هر پا + نسبت گردش‌ها
داده‌ای به‌مراتب کم‌نیازتر از ماتریس OD کامل است و با شواهد قابل‌دسترس (شمارش
ورودی، برداشت چشمی از تصاویر) سازگارتر است؛ رجوع به CLAUDE.md فاز ۱.

این اسکریپت به‌طور کامل برنامه‌نویسی‌شده است (طبق قاعدهٔ سخت ۱، هیچ XML دستی):
1. demand/flows.xml را از config/assumptions.yml (حجم ورودی هر پا) و
   config/vtypes.yml (ترکیب ناوگان) می‌سازد — با امکان مقیاس‌دهی تقاضا (λ)،
   تغییر سهم موتورسیکلت، تغییر ضریب tau، برای تحلیل حساسیت فاز ۳.
2. برای هر پای ورودی، اولین تقاطع واقعی (out-degree >= 2) در مسیر را پیدا
   می‌کند و بر اساس زاویهٔ هندسی، گزینه‌های خروجی را «مستقیم/راست/چپ» طبقه‌بندی
   کرده و نسبت گردش (با امکان بازتنظیم سهم چپ برای تحلیل حساسیت) را به آن‌ها
   اختصاص می‌دهد -> demand/turns.xml.
3. jtrrouter را با flows.xml + turns.xml اجرا می‌کند -> routes.rou.xml.

اجرا (تک‌اجرا، پیش‌فرض‌های مبنا): `make demand`
اجرا (پارامتری، برای رانر چند-seed/λ فاز ۳): رجوع به src/04_run_experiments.py
"""
from __future__ import annotations

import argparse
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


def build_turns(net, ratios: dict, blocked_edges: frozenset = frozenset()) -> str:
    """blocked_edges: شناسهٔ یال‌های خروجی که در شبکهٔ این سناریو دیگر واقعاً
    متصل نیستند (مثلاً S2 که اتصال گردش چپ را از plain-XML حذف کرده) — این
    گزینه‌ها باید کاملاً از فهرست کلاسه‌بندی‌شده حذف شوند، نه فقط وزن صفر
    بگیرند، وگرنه jtrrouter روی یک toEdge نامعتبر خطا می‌دهد."""
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
            if out.getID() in blocked_edges:
                continue
            out_bear = bearing(out.getShape()[0], out.getShape()[-1])
            cls = classify(out_bear - in_bear)
            classified.append((out, cls))
        if not classified:
            continue

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


def build_vtypes_block(vcfg: dict, tau_multiplier: float = 1.0) -> list[str]:
    lines = []
    for vid, params in vcfg["vtypes"].items():
        params = dict(params)
        if "tau" in params:
            params["tau"] = round(params["tau"] * tau_multiplier, 3)
        attrs = " ".join(f'{k}="{v}"' for k, v in params.items())
        lines.append(f'    <vType id="{vid}" {attrs}/>')
    return lines


def scaled_fleet_composition(vcfg: dict, motorcycle_share: float | None) -> dict:
    """در صورت override سهم موتورسیکلت (برای تحلیل حساسیت)، بقیهٔ سهم‌ها را
    متناسب کوچک/بزرگ می‌کند تا مجموع همچنان ۱ بماند."""
    fleet = {k: dict(v) for k, v in vcfg["fleet_composition"].items()}
    if motorcycle_share is None:
        return fleet
    old_moto = fleet["motorcycle"]["share"]
    old_rest = 1.0 - old_moto
    new_rest = 1.0 - motorcycle_share
    scale = (new_rest / old_rest) if old_rest > 1e-9 else 1.0
    for k, v in fleet.items():
        if k == "motorcycle":
            v["share"] = motorcycle_share
        else:
            v["share"] = v["share"] * scale
    return fleet


def build_flows_xml(assumptions: dict, vcfg: dict, lambda_scale: float = 1.0,
                     motorcycle_share: float | None = None,
                     tau_multiplier: float = 1.0) -> str:
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             "<!--",
             "  فاز ۱-۳ — تقاضای فرضی چندناوگانی (Walking Skeleton + ترکیب ناوگان ایران).",
             "  تولید خودکار توسط src/03_build_demand.py از روی assumptions.yml و vtypes.yml.",
             f"  lambda_scale={lambda_scale}, motorcycle_share={motorcycle_share}, tau_multiplier={tau_multiplier}",
             "  دستی ویرایش نکن — رجوع به config/assumptions.yml برای منبع هر عدد.",
             "-->",
             '<routes xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
             'xsi:noNamespaceSchemaLocation="http://sumo.dlr.de/xsd/routes_file.xsd">']
    lines.extend(build_vtypes_block(vcfg, tau_multiplier=tau_multiplier))

    demand_cfg = assumptions["demand_baseline_phase1"]
    fleet = scaled_fleet_composition(vcfg, motorcycle_share)
    flow_id = 0
    approach_name = {"410247492": "west", "412303657#0": "east",
                      "592154956#0": "north", "610531293#0": "south"}
    for edge_id in ENTRY_EDGES:
        base_volume = demand_cfg[ENTRY_ASSUMPTION_KEY[edge_id]]["value"]
        total_volume = base_volume * lambda_scale
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


def run_jtrrouter(flows_path: pathlib.Path, turns_path: pathlib.Path,
                   routes_path: pathlib.Path, seed: int, net_file: pathlib.Path = NET_FILE) -> None:
    jtrrouter = SUMO_HOME / "bin" / "jtrrouter.exe"
    cmd = [
        str(jtrrouter),
        "-n", str(net_file),
        "-r", str(flows_path),
        "-t", str(turns_path),
        "-o", str(routes_path),
        "--turn-defaults", "15,70,15",
        "--accept-all-destinations",
        "--seed", str(seed),
        "--ignore-errors",
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def generate_demand(assumptions: dict, vcfg: dict, *, lambda_scale: float = 1.0,
                     seed: int = 42, left_turn_share: float | None = None,
                     motorcycle_share: float | None = None,
                     tau_multiplier: float = 1.0,
                     net_file: pathlib.Path = NET_FILE,
                     blocked_edges: frozenset = frozenset(),
                     flows_path: pathlib.Path = FLOWS_FILE,
                     turns_path: pathlib.Path = TURNS_FILE,
                     routes_path: pathlib.Path = ROUTES_FILE) -> None:
    """تابع اصلی قابل‌فراخوانی از رانر فاز ۳-۴ (چند-λ/چند-seed/چند-سناریو).

    نکتهٔ مهم: `net_file` باید همیشه دقیقاً همان شبکه‌ای باشد که SUMO با آن
    اجرا می‌شود — در غیر این صورت jtrrouter مسیرهایی می‌سازد که با توپولوژی
    واقعی شبیه‌سازی (مثلاً پس از حذف/افزودن اتصال در یک سناریو) سازگار
    نیستند. `blocked_edges` برای سناریوهایی مثل S2 است که اتصالی را از
    plain-XML حذف کرده‌اند — همان یال‌های خروجیِ حذف‌شده باید اینجا هم اعلام
    شوند تا build_turns() هرگز برایشان درصدی ننویسد."""
    ratios_cfg = assumptions["traffic_control"]["turn_ratio_baseline"]["value"]
    if left_turn_share is None:
        ratios = {"through": ratios_cfg["through"], "right": ratios_cfg["right"], "left": ratios_cfg["left"]}
    else:
        left_pct = left_turn_share * 100
        remaining = 100 - left_pct
        old_remaining = ratios_cfg["through"] + ratios_cfg["right"]
        scale = remaining / old_remaining if old_remaining > 1e-9 else 1.0
        ratios = {"through": ratios_cfg["through"] * scale,
                  "right": ratios_cfg["right"] * scale,
                  "left": left_pct}

    flows_xml = build_flows_xml(assumptions, vcfg, lambda_scale=lambda_scale,
                                 motorcycle_share=motorcycle_share, tau_multiplier=tau_multiplier)
    flows_path.write_text(flows_xml, encoding="utf-8")

    net = sumolib.net.readNet(str(net_file))
    turns_xml = build_turns(net, ratios, blocked_edges=blocked_edges)
    turns_path.write_text(turns_xml, encoding="utf-8")

    run_jtrrouter(flows_path, turns_path, routes_path, seed, net_file=net_file)


def parse_args():
    p = argparse.ArgumentParser(description="ساخت تقاضای jtrrouter (تک‌اجرا یا پارامتری)")
    p.add_argument("--lambda-scale", type=float, default=1.0)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--left-turn-share", type=float, default=None)
    p.add_argument("--motorcycle-share", type=float, default=None)
    p.add_argument("--tau-multiplier", type=float, default=1.0)
    p.add_argument("--out-routes", type=pathlib.Path, default=ROUTES_FILE)
    return p.parse_args()


def main() -> None:
    fix_console_encoding()
    args = parse_args()
    with open(ASSUMPTIONS, "r", encoding="utf-8") as f:
        a = yaml.safe_load(f)
    with open(VTYPES_CFG, "r", encoding="utf-8") as f:
        vcfg = yaml.safe_load(f)

    generate_demand(
        a, vcfg,
        lambda_scale=args.lambda_scale, seed=args.seed,
        left_turn_share=args.left_turn_share, motorcycle_share=args.motorcycle_share,
        tau_multiplier=args.tau_multiplier, routes_path=args.out_routes,
    )
    print(f"[ok] نوشته شد: {FLOWS_FILE}")
    print(f"[ok] نوشته شد: {TURNS_FILE}")
    print(f"[ok] نوشته شد: {args.out_routes}")


if __name__ == "__main__":
    main()
