# Seyedi Under-Bridge Intersection Traffic Reorganization Study — Kerman, Iran

> **Status: Phase 1 (Walking Skeleton) complete.** Results are **uncalibrated** and valid only for
> testing the reproducible pipeline end-to-end — not for scenario comparison or absolute-value
> prediction. See the report's Limitations section.

## Problem

The Seyedi under-bridge intersection (Seyedi Blvd × Imam Reza Highway, near Beheshti Bridge) in
Kerman functions as an uncontrolled, unchannelized weaving/roundabout-like junction. Through
movements on the bridge deck are not the bottleneck — the **turning movements under the bridge**
are.

## Reproduce

```bash
git clone https://github.com/sabernaseralavi-60/Micro-simulation_Seyedi-Bridge.git
cd Micro-simulation_Seyedi-Bridge
python -m venv .venv && .venv/Scripts/pip install -e .
source scripts/env.sh   # or: . scripts/env.ps1 on PowerShell
make all
```

## What's in this repo

- **Full methodology, phasing, and hard rules:** [`CLAUDE.md`](CLAUDE.md)
- **Phase-0 satellite imagery review:** [`docs/imagery_review.md`](docs/imagery_review.md)
- **All input assumptions** (value, source, sensitivity range): [`config/assumptions.yml`](config/assumptions.yml)
- **Reproducible pipeline:** [`src/`](src/) (network build → demand → simulation → KPIs → figures → report)
- **Bilingual (Persian/English) Quarto report:** [`report/`](report/)

## Model status: UNCALIBRATED

Network geometry currently comes from raw OpenStreetMap data; demand is hypothetical
(engineering judgment, not field counts). Scenario comparison, sensitivity analysis, and
calibration follow in later phases once accurate geometry and evidence-based demand are in place.
