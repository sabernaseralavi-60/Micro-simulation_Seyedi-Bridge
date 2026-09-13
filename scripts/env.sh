#!/usr/bin/env bash
# فعال‌سازی محیط پروژه (venv + SUMO_HOME) برای bash/git-bash
# استفاده: در ریشهٔ پروژه اجرا کن:  source scripts/env.sh
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/.venv/Scripts/activate"
export SUMO_HOME="$ROOT/.venv/Lib/site-packages/sumo"
export PATH="$SUMO_HOME/bin:$PATH"
echo "SUMO_HOME = $SUMO_HOME"
"$SUMO_HOME/bin/sumo.exe" --version | head -1
