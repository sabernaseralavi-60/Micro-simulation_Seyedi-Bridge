#!/usr/bin/env python
"""
فاز ۴ — طراحی واقعیِ فازبندی/زمان‌بندی چراغ راهنمایی (نه اکتفا به هیوریستیک
خودکار netconvert).

**مسئله‌ای که این اسکریپت رفع می‌کند:** تا پیش از این، هر گرهٔ چراغ‌دار S1
صرفاً با `--tls.cycle.time <C>` ساخته می‌شد و netconvert خودش سبز هر فاز را
به‌نسبت هیوریستیک داخلی خودش (تقریباً متناسب با تعداد اتصال/خط هر فاز) تقسیم
می‌کرد — بدون هیچ فاز همه‌قرمز (all-red clearance) صریح، و بدون هیچ ارتباط
دقیق و ردیابی‌پذیر با نسبت جریان بحرانی y_i وبستر. برای تقاطعی که کل روایت
این مطالعه حول برخورد می‌چرخد، نبود بازهٔ پاکسازی هنگام تعویض فاز یک خلأ
مهندسی واقعی بود، نه صرفاً یک ظرافت آماری.

**روش:**
۱. گروه‌بندی حرکات (کدام اتصال‌ها هم‌زمان می‌توانند سبز باشند) حدس زده
   نمی‌شود — از خروجی واقعیِ تحلیل تعارض (foe-analysis) خودِ netconvert
   خوانده می‌شود (فاز اول ساخت شبکه، با نوع static/کنترل‌نشده). این بخش «واقعی»
   است چون از تحلیل توپولوژی واقعی شبکه می‌آید، نه از این اسکریپت.
۲. طول بازهٔ همه‌قرمز هر گره از **هندسهٔ واقعی همان گره** محاسبه می‌شود: طولانی‌ترین
   لاین داخلی (internal lane) آن گره در net.xml — یعنی مسافت واقعی‌ای که یک
   خودرو باید طی کند تا تقاطع را کاملاً تخلیه کند — تقسیم بر سرعت طراحیِ
   تخلیه (assumptions.yml -> signal_design_S1.clearance_speed_mps).
۳. سبز هر فاز به‌نسبت وزن آن فاز (تعداد اتصال‌های سبز آن، پروکسی برای ظرفیت/
   تقاضای نسبی آن حرکت، در نبود شمارش واقعی حرکت‌به‌حرکت — محدودیت صریح
   ثبت‌شده در برنامهٔ کالیبراسیون) از سیکل وبستر توزیع می‌شود؛ حداقل سبز
   assumptions.yml -> signal_design_S1 (همان کفِ ۵ ثانیه که در
   src/08_webster_timing.py هم استفاده شده) رعایت می‌شود.
۴. خروجی نهایی به‌صورت `<tlLogic>` صریح در فایل plain .tll.xml همان سناریو
   نوشته می‌شود (نه ویرایش دستی net.xml کامپایل‌شده) و netconvert یک‌بار دیگر
   روی همان plain-XML اجرا می‌شود — یعنی قاعدهٔ سخت ۲ (ویرایش هندسه/کنترل فقط
   با اسکریپت روی plain-XML) کاملاً رعایت می‌شود. تأیید شد (آزمایش دستی):
   netconvert برنامهٔ تأمین‌شده در tllogic-files را عیناً می‌پذیرد و
   بازتولید نمی‌کند.

برای نسخهٔ actuated: فقط بازهٔ همه‌قرمز درج می‌شود (ایمنیِ عمومی، مستقل از
نوع کنترل)؛ فازهای سبز با minDur/maxDur اصلیِ netconvert دست‌نخورده می‌مانند
چون کل فلسفهٔ actuated واگذاری تطبیق پویا به SUMO است، نه زمان‌بندی ثابت.
"""
from __future__ import annotations

import pathlib
import sys
import xml.etree.ElementTree as ET

GREEN_CHARS = set("Gg")


def fix_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def _green_indices(state: str) -> list[int]:
    return [i for i, c in enumerate(state) if c in GREEN_CHARS]


def harvest_auto_program(net_path: pathlib.Path, node_ids: list[str]) -> tuple[dict, dict]:
    """از net.xml خام (auto) می‌خواند: برنامهٔ فازی هر گره + بلندترین طول
    لاین داخلی آن گره (مسافت واقعیِ تخلیهٔ تقاطع، برای بازهٔ همه‌قرمز)."""
    tree = ET.parse(net_path)
    root = tree.getroot()
    node_ids = set(node_ids)

    programs: dict[str, list[dict]] = {}
    for tl in root.findall("tlLogic"):
        tlid = tl.get("id")
        if tlid not in node_ids:
            continue
        phases = []
        for p in tl.findall("phase"):
            ph = {"state": p.get("state"), "duration": float(p.get("duration"))}
            if p.get("minDur") is not None:
                ph["minDur"] = p.get("minDur")
            if p.get("maxDur") is not None:
                ph["maxDur"] = p.get("maxDur")
            phases.append(ph)
        programs[tlid] = phases

    clearance_m = {nid: 0.0 for nid in node_ids}
    for e in root.findall("edge"):
        if e.get("function") != "internal":
            continue
        jid = e.get("id").split("_")[0].lstrip(":")
        if jid not in node_ids:
            continue
        for lane in e.findall("lane"):
            clearance_m[jid] = max(clearance_m[jid], float(lane.get("length", "0")))

    return programs, clearance_m


def design_fixed_program(phases: list[dict], clearance_m: float, cycle_s: float,
                          yellow_s: float, clearance_speed_mps: float,
                          min_green_s: float, all_red_bounds: tuple[float, float]
                          ) -> tuple[list[tuple[str, float]], float] | None:
    """بازطراحی کامل زمان‌ثابت: سبز واقعاً وزن‌دار (نه هیوریستیک netconvert) +
    زرد + همه‌قرمز صریح. گره‌های بدون تعارض واقعی (<۲ فاز سبز) نادیده گرفته
    می‌شوند (None) — از قبل بدون تعارض بودند، نیازی به چراغ ندارند."""
    green_phases = [p for p in phases if _green_indices(p["state"])]
    if len(green_phases) < 2:
        return None

    n = len(green_phases)
    all_red_s = clearance_m / clearance_speed_mps
    all_red_s = min(max(all_red_s, all_red_bounds[0]), all_red_bounds[1])
    lost_total = n * (yellow_s + all_red_s)
    green_total = max(cycle_s - lost_total, n * min_green_s)

    weights = [len(_green_indices(p["state"])) for p in green_phases]
    wsum = sum(weights) or n

    out: list[tuple[str, float]] = []
    for p, w in zip(green_phases, weights):
        state = p["state"]
        g = max(min_green_s, round(green_total * w / wsum, 1))
        yellow_state = "".join("y" if c in GREEN_CHARS else "r" for c in state)
        red_state = "r" * len(state)
        out.append((state, g))
        out.append((yellow_state, yellow_s))
        out.append((red_state, round(all_red_s, 1)))
    return out, all_red_s


def design_actuated_program(phases: list[dict], clearance_m: float, yellow_s: float,
                             clearance_speed_mps: float, all_red_bounds: tuple[float, float]
                             ) -> tuple[list[dict], float] | None:
    """actuated: سبزها (با minDur/maxDur اصلی) دست‌نخورده می‌مانند؛ فقط یک فاز
    همه‌قرمز صریح بعد از هر زرد اضافه می‌شود — رفع همان خلأ ایمنی، بدون دخالت
    در منطق تطبیق پویای SUMO."""
    green_phases = [p for p in phases if _green_indices(p["state"])]
    if len(green_phases) < 2:
        return None

    all_red_s = clearance_m / clearance_speed_mps
    all_red_s = min(max(all_red_s, all_red_bounds[0]), all_red_bounds[1])

    # بازسازی صریح: سبز(minDur/maxDur اصلی) -> زرد(duration اصلی) -> همه‌قرمز(جدید)
    out: list[dict] = []
    for p in phases:
        if _green_indices(p["state"]):
            out.append(dict(p))
        else:
            out.append(dict(p))
            red_state = "r" * len(p["state"])
            out.append({"state": red_state, "duration": round(all_red_s, 1)})
    return out, all_red_s


def write_tll_override(tll_path: pathlib.Path, node_programs: dict[str, list]) -> None:
    """برنامه‌های تازه‌طراحی‌شده را به <tlLogics> فایل plain .tll.xml همان
    سناریو (کپی محلی، نه فایل پایهٔ مشترک) اضافه می‌کند. netconvert در اجرای
    بعدی این برنامه‌ها را عیناً می‌پذیرد (آزموده‌شده)."""
    tree = ET.parse(tll_path)
    root = tree.getroot()
    for nid, entry in node_programs.items():
        phases, tls_type = entry
        tl = ET.SubElement(root, "tlLogic")
        tl.set("id", nid)
        tl.set("type", tls_type)
        tl.set("programID", "0")
        tl.set("offset", "0")
        for ph in phases:
            if isinstance(ph, tuple):
                state, dur = ph
                attrs = {"duration": str(dur), "state": state}
            else:
                attrs = {"duration": str(ph["duration"]), "state": ph["state"]}
                if "minDur" in ph:
                    attrs["minDur"] = str(ph["minDur"])
                if "maxDur" in ph:
                    attrs["maxDur"] = str(ph["maxDur"])
            el = ET.SubElement(tl, "phase")
            for k, v in attrs.items():
                el.set(k, v)
    tree.write(tll_path, encoding="UTF-8", xml_declaration=True)
