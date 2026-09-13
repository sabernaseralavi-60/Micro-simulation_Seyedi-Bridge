# مطالعهٔ ساماندهی ترافیکی تقاطع زیرپل سیدی، کرمان
# Makefile اصلی خط لولهٔ تکرارپذیر — طبق CLAUDE.md §3.1 هر شکل/جدول/عدد گزارش باید
# با `make all` از صفر بازتولید شود.
#
# فاز ۱-۳ کامل شد: network -> patch-geometry -> demand -> run -> analyze -> figures -> report
# (هر سه فرمت، هر دو زبان). `run` اکنون سناریوی S0 را در ۵ سطح تقاضا (λ) × ۱۰ seed
# (طبق قاعدهٔ سخت ۵) اجرا می‌کند — حدود ۱۰ دقیقه. سناریوهای S1-S5 در فاز ۴ اضافه می‌شوند.

PYTHON := .venv/Scripts/python.exe
SUMO_HOME_DIR := $(CURDIR)/.venv/Lib/site-packages/sumo
export SUMO_HOME := $(SUMO_HOME_DIR)
export PYTHONIOENCODING := utf-8
export QUARTO_PYTHON := $(CURDIR)/$(PYTHON)

.PHONY: all check-env sketch network patch-geometry demand run analyze figures report publish clean

all: check-env sketch network patch-geometry demand run analyze figures report

## بررسی نصب‌بودن ابزارهای لازم (فاز ۰، گام ۱)
check-env:
	@echo "--- sumo ---"
	@"$(SUMO_HOME_DIR)/bin/sumo.exe" --version | head -1
	@echo "--- python + sumolib/traci ---"
	@$(PYTHON) -c "import sumolib, traci; print('ok')"
	@echo "--- quarto ---"
	@quarto --version
	@echo "--- gh ---"
	@gh auth status
	@echo "--- git ---"
	@git --version

## سنتز هندسی فاز ۰: اسکچ پلان زیرپل + نقشهٔ bbox پیشنهادی
sketch:
	$(PYTHON) src/00_geometry_sketch.py

## فاز ۱: ساخت شبکه از OSM (osmGet + netconvert) + بازرسی جدایی تراز
network:
	$(PYTHON) src/01_build_network.py

## فاز ۲: اصلاحات هندسی مبتنی بر تصویر روی plain-XML (خط عرشه، junction model) + بازسازی شبکه
patch-geometry:
	$(PYTHON) src/02_patch_geometry.py

## فاز ۱-۲: تقاضای jtrrouter چندناوگانی، تک‌اجرا (λ=۱, seed=۴۲) — برای بازرسی چشمی/netedit
demand:
	$(PYTHON) src/03_build_demand.py

## فاز ۳: اجرای سناریوی S0 در ۵ سطح λ × ۱۰ seed (۵۰ اجرا، ~۱۰ دقیقه)
run:
	$(PYTHON) src/04_run_experiments.py

## فاز ۳: استخراج KPI چند-λ/چند-seed + میانگین±CI۹۵٪ به outputs/tables/*.{csv,parquet}
analyze:
	$(PYTHON) src/05_extract_kpis.py

## فاز ۳: نمودار KPI به تفکیک پا + نمودار حساسیت به λ
figures:
	$(PYTHON) src/07_figures.py

## رندر گزارش دوزبانه در هر سه فرمت (html/pdf/docx)
report:
	cd report && quarto render report-fa.qmd --profile fa --to html
	cd report && quarto render report-fa.qmd --profile fa --to pdf
	cd report && quarto render report-fa.qmd --profile fa --to docx
	cd report && quarto render report-en.qmd --profile en --to html
	cd report && quarto render report-en.qmd --profile en --to pdf
	cd report && quarto render report-en.qmd --profile en --to docx

publish:
	@echo "TODO فاز ۵: quarto publish gh-pages (پس از Checkpoint ۲)"

clean:
	rm -rf outputs/figures/* outputs/tables/* outputs/logs/* report/_output
