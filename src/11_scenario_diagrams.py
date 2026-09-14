#!/usr/bin/env python
"""
فاز ۴ — اسکچ شماتیک تکرارپذیر برای هر سناریو (S0 تا S5 + S2+S4)، برای شفاف‌سازی
مخاطب غیرمتخصص (درخواست صریح کاربر، ۱۴۰۵/۰۶/۲۴: «سناریوهای پیشنهادی باید با
شکل شماتیک و توضیح دقیق برای مخاطب شفاف‌سازی شود»).

**روش:** هر شکل مستقیماً از net.xml واقعیِ همان نسخهٔ کنترلی (طبق
config/scenarios.yml) تولید می‌شود — نه ترسیم دستی/آزاد (قاعدهٔ سخت ۲).
یال‌ها/گره‌های مشترک با S0 خاکستری‌اند؛ یال‌های افزوده‌شده (حلقه، بای‌پس،
دوربرگردان) قرمز پررنگ؛ یال‌های حذف/جایگزین‌شده (مثلاً یال عرشهٔ شکافته‌شدهٔ
S2) خاکستری نقطه‌چین؛ گره‌هایی که نوع کنترل‌شان عوض شده (zipper->traffic_light
یا zipper->priority) با نشانگر رنگی مطابق نوع جدید. این یعنی هر تغییر تصویری
در شکل، دقیقاً همان چیزی است که در شبکهٔ واقعی SUMO اتفاق افتاده — نه یک
دیاگرام مفهومیِ جدا از مدل.

اجرا: `python src/11_scenario_diagrams.py` (نیازمند این‌که همهٔ net.xml های
scenarios.yml از قبل ساخته شده باشند — رجوع به `make scenario-s1` تا `scenario-s2s4`)

خروجی: outputs/figures/scenario_diagrams/<table_prefix>.{svg,png}
"""
from __future__ import annotations

import pathlib
import sys
import xml.etree.ElementTree as ET

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCENARIOS_CFG = ROOT / "config" / "scenarios.yml"
OUT_DIR = ROOT / "outputs" / "figures" / "scenario_diagrams"

WEAVE_CENTER = (3200.0, 2750.0)
RADIUS = 320.0  # متر — کافی برای دیدن رمپ‌ها، حلقهٔ S3/S5، و دوربرگردان‌های S2 در D=350

NODE_TYPE_COLOR = {
    "traffic_light": "#1f77b4",   # آبی — چراغ راهنمایی
    "priority": "#2ca02c",        # سبز — priority (کانالیزاسیون S4 یا بازتایپ S5)
}
NODE_TYPE_LABEL_FA = {
    "traffic_light": "چراغ راهنمایی (بازطراحی‌شده با src/10_signal_design.py)",
    "priority": "priority (کانالیزاسیون / بازتایپ)",
}
NODE_TYPE_LABEL_EN = {
    "traffic_light": "traffic light (real design, src/10_signal_design.py)",
    "priority": "priority (channelization / retype)",
}

# گره‌های انشعابی که اتصال گردش چپشان در S2 حذف شده — از
# scenarios/S2_rcut/build_network.py::LEFT_TURN_CONNECTIONS (کپی شناسه‌ها،
# نه اتصال پویا، چون فقط شناسهٔ گره لازم است نه منطق ساخت شبکه).
S2_REMOVED_LEFT_TURN_NODES = {
    "6711509165", "6711509176", "6711509163", "6711509162", "6403676806",
}
REMOVED_MOVEMENT_NODES = {
    "s2": S2_REMOVED_LEFT_TURN_NODES,
    "s2_d150": S2_REMOVED_LEFT_TURN_NODES,
    "s2_d350": S2_REMOVED_LEFT_TURN_NODES,
    "s2s4": S2_REMOVED_LEFT_TURN_NODES,
}


def fix_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def load_net(net_path: pathlib.Path):
    tree = ET.parse(net_path)
    root = tree.getroot()
    nodes = {}
    for j in root.findall("junction"):
        if j.get("type") == "internal":
            continue
        x, y = j.get("x"), j.get("y")
        if x is None or y is None:
            continue
        nodes[j.get("id")] = (float(x), float(y), j.get("type"))
    edges = {}
    for e in root.findall("edge"):
        if e.get("function") == "internal":
            continue
        lanes = e.findall("lane")
        if not lanes:
            continue
        shape = lanes[0].get("shape")
        if not shape:
            continue
        pts = []
        for tok in shape.split():
            parts = tok.split(",")
            pts.append((float(parts[0]), float(parts[1])))  # z (اگر باشد) نادیده گرفته می‌شود
        edges[e.get("id")] = pts
    return nodes, edges


def within_radius(pts, center=WEAVE_CENTER, r=RADIUS) -> bool:
    cx, cy = center
    return any((x - cx) ** 2 + (y - cy) ** 2 <= r ** 2 for x, y in pts)


def real_signal_nodes(net_path: pathlib.Path) -> set[str]:
    """گره‌هایی که واقعاً >۱ فاز دارند (تعارض واقعی) — نه فقط بازتایپ‌شده به
    traffic_light اما همچنان تک‌فازهٔ «سبز دائم» (بدون تعارض واقعی، رجوع به
    src/10_signal_design.py و یافتهٔ فرعی S1). فقط این‌ها در نمودار شماتیک
    به‌عنوان «چراغ واقعی» نشانه‌گذاری می‌شوند تا نمودار با متن گزارش (که
    صراحتاً ۵ گرهٔ واقعی را ذکر می‌کند، نه ۱۰ گرهٔ بازتایپ‌شده) هم‌خوان بماند."""
    tree = ET.parse(net_path)
    root = tree.getroot()
    real = set()
    for tl in root.findall("tlLogic"):
        if len(tl.findall("phase")) > 1:
            real.add(tl.get("id"))
    return real


def draw_diagram(base, scen, scen_net_path: pathlib.Path, out_prefix: pathlib.Path,
                  title_fa: str, title_en: str, caption_fa: str, caption_en: str,
                  removed_movement_nodes: set[str] | None = None) -> None:
    bn_nodes, bn_edges = base
    sn_nodes, sn_edges = scen
    real_tl = real_signal_nodes(scen_net_path)

    # یال مشترک (همان id در پایه و سناریو) با شکل *سناریو* رسم می‌شود — چون
    # ممکن است طولش عوض شده باشد (مثلاً پارهٔ باقیماندهٔ یک یال شکافته‌شدهٔ S2).
    shared_edges = {eid: sn_edges[eid] for eid in sn_edges if eid in bn_edges}
    removed_edges = {eid: pts for eid, pts in bn_edges.items() if eid not in sn_edges}
    added_edges_raw = {eid: pts for eid, pts in sn_edges.items() if eid not in bn_edges}
    # یال‌هایی که فقط به‌دلیل شکافتن یک یال موجود (مثل دو یال بلند عرشه در S2)
    # شناسهٔ تازه گرفته‌اند (پیشوندشان با شناسهٔ یک یال پایه یکی است) یال
    # «واقعاً تازه» نیستند — همان جاده‌اند، فقط پاره شده؛ خاکستری می‌مانند تا
    # نمودار فقط اتصال‌های واقعاً جدید (مثل خودِ حلقهٔ دوربرگردان) را قرمز کند.
    base_ids = list(bn_edges)
    added_edges = {}
    split_continuations = {}
    for eid, pts in added_edges_raw.items():
        if any(eid != bid and eid.startswith(bid) for bid in base_ids):
            split_continuations[eid] = pts
        else:
            added_edges[eid] = pts
    changed_nodes = {}
    for nid, (x, y, typ) in sn_nodes.items():
        base_typ = bn_nodes.get(nid, (None, None, None))[2]
        if base_typ is None or typ == base_typ or typ not in NODE_TYPE_COLOR:
            continue
        if typ == "traffic_light" and nid not in real_tl:
            continue  # بازتایپ‌شده اما تک‌فازه/سبز دائم — تعارض واقعی ندارد، نشانه‌گذاری نمی‌شود
        changed_nodes[nid] = (x, y, typ)

    for lang, title, caption in (("fa", title_fa, caption_fa), ("en", title_en, caption_en)):
        fig, ax = plt.subplots(figsize=(8.5, 8.5))
        ax.set_aspect("equal")

        for eid, pts in shared_edges.items():
            if within_radius(pts):
                xs, ys = zip(*pts)
                ax.plot(xs, ys, color="#999999", lw=1.6, zorder=1)

        for eid, pts in split_continuations.items():
            if within_radius(pts):
                xs, ys = zip(*pts)
                ax.plot(xs, ys, color="#999999", lw=1.6, zorder=1)

        for eid, pts in removed_edges.items():
            if within_radius(pts):
                xs, ys = zip(*pts)
                ax.plot(xs, ys, color="#bbbbbb", lw=1.2, ls=":", zorder=1)

        for eid, pts in added_edges.items():
            if within_radius(pts):
                xs, ys = zip(*pts)
                ax.plot(xs, ys, color="#d62728", lw=2.8, zorder=3)

        label_map = NODE_TYPE_LABEL_FA if lang == "fa" else NODE_TYPE_LABEL_EN
        seen_types = set()
        for nid, (x, y, typ) in changed_nodes.items():
            if not within_radius([(x, y)]):
                continue
            color = NODE_TYPE_COLOR[typ]
            lbl = label_map[typ] if typ not in seen_types else None
            seen_types.add(typ)
            ax.scatter([x], [y], color=color, s=110, zorder=5, edgecolor="black",
                       linewidth=0.8, label=lbl)

        removed_mv_label_used = False
        for nid in (removed_movement_nodes or set()):
            if nid not in sn_nodes:
                continue
            x, y, _typ = sn_nodes[nid]
            if not within_radius([(x, y)]):
                continue
            lbl = None
            if not removed_mv_label_used:
                lbl = "اتصال گردش چپ حذف‌شده" if lang == "fa" else "removed left-turn connection"
                removed_mv_label_used = True
            ax.scatter([x], [y], marker="x", color="#8b0000", s=140, zorder=6,
                       linewidths=2.5, label=lbl)

        cx, cy = WEAVE_CENTER
        ax.set_xlim(cx - RADIUS, cx + RADIUS)
        ax.set_ylim(cy - RADIUS, cy + RADIUS)
        ax.set_title(title, fontsize=11)
        ax.set_xlabel("UTM X (m)")
        ax.set_ylabel("UTM Y (m)")

        legend_lines = [
            plt.Line2D([0], [0], color="#999999", lw=1.6,
                       label="شبکهٔ مشترک با S0" if lang == "fa" else "shared with S0"),
        ]
        if removed_edges:
            legend_lines.append(plt.Line2D([0], [0], color="#bbbbbb", lw=1.2, ls=":",
                                            label="یال حذف/جایگزین‌شده" if lang == "fa" else "removed/replaced edge"))
        if added_edges:
            legend_lines.append(plt.Line2D([0], [0], color="#d62728", lw=2.8,
                                            label="یال افزوده‌شدهٔ این سناریو" if lang == "fa" else "edge added by this scenario"))
        for typ in seen_types:
            legend_lines.append(plt.Line2D([0], [0], marker="o", color="w",
                                            markerfacecolor=NODE_TYPE_COLOR[typ], markersize=9,
                                            markeredgecolor="black", label=label_map[typ]))
        if removed_mv_label_used:
            legend_lines.append(plt.Line2D([0], [0], marker="x", color="#8b0000", markersize=10,
                                            linewidth=0, markeredgewidth=2.5,
                                            label="اتصال گردش چپ حذف‌شده" if lang == "fa" else "removed left-turn connection"))
        ax.legend(handles=legend_lines, loc="upper left", fontsize=7.5, framealpha=0.92)
        ax.grid(alpha=0.15, zorder=0)

        fig.text(0.5, -0.02, caption, ha="center", va="top", fontsize=8.5, wrap=True)

        out_path = out_prefix.with_name(f"{out_prefix.name}_{lang}")
        fig.savefig(out_path.with_suffix(".svg"), bbox_inches="tight", dpi=150)
        fig.savefig(out_path.with_suffix(".png"), bbox_inches="tight", dpi=150)
        plt.close(fig)
        print(f"[ok] نوشته شد: {out_path.with_suffix('.png')}")


CAPTIONS = {
    "s0": dict(
        title_fa="S0 — حفظ وضع موجود (Do-Nothing)",
        title_en="S0 — Do-Nothing (existing condition)",
        caption_fa="مبنای مقایسه: بدون چراغ، بدون کانالیزاسیون رسمی؛ گره‌های ادغام (نقاط خاکستری روی خطوط) با junction model از نوع zipper مدل شده‌اند.",
        caption_en="Comparison baseline: no signal, no formal channelization; merge nodes are modeled with SUMO's zipper junction type.",
    ),
    "s1_fixed": dict(
        title_fa="S1 — تقاطع چراغ‌دار (زمان‌ثابت)",
        title_en="S1 — Signalized intersection (fixed-time)",
        caption_fa="۵ گرهٔ ادغام واقعی زیر پل (نقاط آبی) به‌طور مستقل چراغ‌دار شده‌اند؛ فازبندی هرکدام با src/10_signal_design.py طراحی شده (سبز وزن‌دار وبستر + همه‌قرمز واقعی)، نه یک تقاطع کلاسیک واحد.",
        caption_en="The 5 real merge conflict nodes under the bridge (blue dots) are independently signalized; each phasing is designed with src/10_signal_design.py (Webster-weighted green + real all-red), not one classical single intersection.",
    ),
    "s1_actuated": dict(
        title_fa="S1 — تقاطع چراغ‌دار (actuated)",
        title_en="S1 — Signalized intersection (actuated)",
        caption_fa="همان ۵ گرهٔ S1-ثابت، اما با منطق gap-out پیش‌فرض SUMO (سبز بر اساس حضور واقعی وسیله) به‌جای سیکل ثابت.",
        caption_en="Same 5 nodes as S1-fixed, but with SUMO's default gap-out logic (green adapts to real vehicle presence) instead of a fixed cycle.",
    ),
    "s2": dict(
        title_fa="S2 — حذف گردش چپ + دوربرگردان فیزیکی (D=۲۵۰م)",
        title_en="S2 — Left-turn removal + physical U-turn (D=250m)",
        caption_fa="۵ اتصال گردش چپ واقعی حذف شده (نشانگر ×)؛ دو یال بلند عرشه در ±۲۵۰ متر از مرکز شکافته و دوربرگردان کوتاه افزوده شده (خطوط قرمز) — معادل RCUT/Median U-Turn.",
        caption_en="5 real left-turn connections removed (x markers); the two long deck edges are split at +-250m from center with a short U-turn added (red lines) — an RCUT / Median U-Turn.",
    ),
    "s3_constrained": dict(
        title_fa="S3 — میدان نامتقارن (محدود به دو دهانهٔ باز)",
        title_en="S3 — Asymmetric roundabout (constrained to open bays)",
        caption_fa="یک حلقهٔ گردشی پادساعتگرد تک‌خطهٔ ۴یالی (خطوط قرمز) میان چهار گرهٔ تلاقی واقعی افزوده شده — بدون حذف هیچ گره/یال قبلی.",
        caption_en="A single-lane, 4-edge counter-clockwise ring (red lines) added between four real junction nodes — no existing topology removed.",
    ),
    "s3_full": dict(
        title_fa="S3 — میدان نامتقارن (با دهانهٔ مرکزی باز)",
        title_en="S3 — Asymmetric roundabout (open center bay)",
        caption_fa="همان حلقهٔ constrained + یک وتر مستقیم غرب-شرق که فرضاً از دهانهٔ مرکزیِ بازشدهٔ پل عبور می‌کند (مشروط به تأیید سازه‌ای، خارج از حیطهٔ این مطالعه).",
        caption_en="Same ring as constrained plus a direct east-west chord standing in for the (structurally conditional) opened center bay — outside this study's scope.",
    ),
    "s4": dict(
        title_fa="S4 — کانالیزاسیون + گردش راست آزاد",
        title_en="S4 — Channelization + free right turn",
        caption_fa="همان ۵ گرهٔ تعارض واقعی S1، اما از zipper به priority بازگردانده شده (نقاط سبز)؛ اتصال عبوریِ اصلی هرکدام حق‌تقدم بدون‌قیدوشرط می‌گیرد، گردش راست کانالیزه‌شده حق‌تقدم minor شفاف دارد.",
        caption_en="The same 5 real S1 conflict nodes, reverted from zipper to priority (green dots); each node's main through connection gets unconditional priority, the channelized right turn gets a clear minor yield.",
    ),
    "s5_metering": dict(
        title_fa="S5 — میدان + چراغ متردهنده روی پای غالب",
        title_en="S5 — Roundabout + metering signal on the dominant leg",
        caption_fa="همان حلقهٔ S3-محدود (خطوط قرمز)؛ گرهٔ غرب (دریافت‌کنندهٔ ترافیک گردشی از عرشهٔ پرتردد) به چراغ راهنمایی با سیکل کوتاه ۲۰ثانیه بازتایپ شده (نقطهٔ آبی).",
        caption_en="The same S3-constrained ring (red lines); the west node (receiving heavy deck traffic) is retyped to a metering signal with a short 20s cycle (blue dot).",
    ),
    "s5_oneway": dict(
        title_fa="S5 — میدان + بای‌پس شمال-جنوب (حق‌تقدم بدون‌قیدوشرط)",
        title_en="S5 — Roundabout + N-S bypass (unconditional priority)",
        caption_fa="همان حلقهٔ S3-محدود + یک بای‌پس مستقیم دوطرفهٔ شمال-جنوب (خطوط قرمز) با اولویت بالاتر از خودِ حلقه — رد شد (رجوع به گزارش، بخش ۷).",
        caption_en="The same S3-constrained ring plus a direct two-way north-south bypass (red lines) with priority higher than the ring itself — rejected (see report Section 7).",
    ),
    "s5_oneway_yield": dict(
        title_fa="S5 — میدان + بای‌پس شمال-جنوب (حق‌تقدم عادی)",
        title_en="S5 — Roundabout + N-S bypass (yielding priority)",
        caption_fa="همان بای‌پس، اما با حق‌تقدم عادی/یالدهنده به‌جای بدون‌قیدوشرط — نیز رد شد.",
        caption_en="The same bypass, but with normal yielding priority instead of unconditional — also rejected.",
    ),
    "s5_oneway_signal": dict(
        title_fa="S5 — میدان + بای‌پس شمال-جنوب (چراغ راهنمایی واقعی)",
        title_en="S5 — Roundabout + N-S bypass (real traffic signal)",
        caption_fa="همان بای‌پس، با گرهٔ تعارض بازتایپ‌شده به چراغ راهنمایی واقعی (نقطهٔ آبی، طراحی‌شده با src/10_signal_design.py) — بدترین نتیجهٔ کل این مطالعه.",
        caption_en="The same bypass, with the conflict node retyped to a real traffic light (blue dot, designed with src/10_signal_design.py) — the worst outcome of this entire study.",
    ),
    "s2s4": dict(
        title_fa="S2+S4 ترکیبی — بهترین نتیجهٔ ایمنی این مطالعه",
        title_en="S2+S4 combined — this study's best safety result",
        caption_fa="اصلاح S2 (حذف گردش چپ با نشانگر ×، دوربرگردان با خطوط قرمز) و S4 (کانالیزاسیون، نقاط سبز) هم‌زمان روی یک شبکه — چون گره‌های فیزیکی‌شان کاملاً مجزا هستند.",
        caption_en="The S2 fix (left-turn removal, x markers; U-turn, red lines) and S4 fix (channelization, green dots) applied simultaneously on one network — their physical nodes are entirely separate.",
    ),
}


def main() -> None:
    fix_console_encoding()
    with open(SCENARIOS_CFG, "r", encoding="utf-8") as f:
        scen_cfg = yaml.safe_load(f)["scenarios"]

    base_scen = scen_cfg["S0_baseline"]
    base_net_file = ROOT / base_scen["control_variants"]["default"]["net_file"]
    if not base_net_file.exists():
        raise FileNotFoundError(f"شبکهٔ مبنای S0 یافت نشد: {base_net_file} — ابتدا `make network` را اجرا کن.")
    base = load_net(base_net_file)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    jobs = []
    for scen_id, scen in scen_cfg.items():
        if scen.get("status") != "built":
            continue
        for variant_id, variant in scen["control_variants"].items():
            table_prefix = variant["table_prefix"]
            jobs.append((table_prefix, ROOT / variant["net_file"]))

    for table_prefix, net_file in jobs:
        if table_prefix not in CAPTIONS:
            print(f"[skip] {table_prefix}: کپشن تعریف نشده، رد شد")
            continue
        if not net_file.exists():
            print(f"[warn] {table_prefix}: شبکه یافت نشد ({net_file}) — رد شد")
            continue
        scen_net = load_net(net_file) if table_prefix != "s0" else base
        c = CAPTIONS[table_prefix]
        draw_diagram(base, scen_net, net_file, OUT_DIR / table_prefix,
                     c["title_fa"], c["title_en"], c["caption_fa"], c["caption_en"],
                     removed_movement_nodes=REMOVED_MOVEMENT_NODES.get(table_prefix))

    print(f"[ok] {len(jobs)} نمودار شماتیک در {OUT_DIR} تولید شد.")


if __name__ == "__main__":
    main()
