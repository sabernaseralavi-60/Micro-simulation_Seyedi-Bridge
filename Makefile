# مطالعهٔ ساماندهی ترافیکی تقاطع زیرپل سیدی، کرمان
# Makefile اصلی خط لولهٔ تکرارپذیر — طبق CLAUDE.md §3.1 هر شکل/جدول/عدد گزارش باید
# با `make all` از صفر بازتولید شود.
#
# این نسخه مربوط به فاز ۰ است؛ اهداف network/demand/run/analyze/report در فازهای
# بعدی (طبق CLAUDE.md §۴) اضافه می‌شوند.

PYTHON := .venv/Scripts/python.exe

.PHONY: all check-env sketch network demand run analyze report publish clean

all: check-env sketch

## بررسی نصب‌بودن ابزارهای لازم (فاز ۰، گام ۱)
check-env:
	@echo "--- sumo ---"
	@SUMO_HOME=.venv/Lib/site-packages/sumo .venv/Lib/site-packages/sumo/bin/sumo.exe --version | head -1
	@echo "--- python + sumolib/traci ---"
	@SUMO_HOME=.venv/Lib/site-packages/sumo $(PYTHON) -c "import sumolib, traci; print('ok')"
	@echo "--- quarto ---"
	@quarto --version
	@echo "--- gh ---"
	@gh auth status
	@echo "--- git ---"
	@git --version

## سنتز هندسی فاز ۰: اسکچ پلان زیرپل + نقشهٔ bbox پیشنهادی
sketch:
	$(PYTHON) src/00_geometry_sketch.py

## اهداف فازهای بعدی (placeholder — پیاده‌سازی در فاز ۱ به بعد)
network:
	@echo "TODO فاز ۱: netconvert از data/raw/osm/seyedi.osm"

demand:
	@echo "TODO فاز ۱: jtrrouter از demand/flows.xml + demand/turns.xml"

run:
	@echo "TODO فاز ۱: اجرای sumo برای هر سناریو/seed"

analyze:
	@echo "TODO فاز ۱: استخراج KPI و آمار چند-seed"

report:
	@echo "TODO فاز ۱: quarto render --profile fa && quarto render --profile en"

publish:
	@echo "TODO فاز ۵: quarto publish gh-pages (پس از Checkpoint ۲)"

clean:
	rm -rf outputs/figures/* outputs/tables/* outputs/logs/*
