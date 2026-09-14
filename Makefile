# مطالعهٔ ساماندهی ترافیکی تقاطع زیرپل سیدی، کرمان
# Makefile اصلی خط لولهٔ تکرارپذیر — طبق CLAUDE.md §3.1 هر شکل/جدول/عدد گزارش باید
# با `make all` از صفر بازتولید شود.
#
# فاز ۱-۳ کامل شد: network -> patch-geometry -> demand -> run -> analyze -> figures -> report
# (هر سه فرمت، هر دو زبان). فاز ۴ (سناریوسازی) در حال ساخت: S1 (چراغ‌دار) آماده
# است؛ `run`/`analyze`/`statistics` اکنون همهٔ سناریوهای status=built در
# config/scenarios.yml را پوشش می‌دهند (نه فقط S0). S2-S5 هنوز planned هستند.

PYTHON := .venv/Scripts/python.exe
SUMO_HOME_DIR := $(CURDIR)/.venv/Lib/site-packages/sumo
export SUMO_HOME := $(SUMO_HOME_DIR)
export PYTHONIOENCODING := utf-8
export QUARTO_PYTHON := $(CURDIR)/$(PYTHON)

.PHONY: all check-env sketch network patch-geometry demand webster-timing scenario-s1 scenario-s2 scenario-s3 scenario-s4 scenario-s5 scenario-s2s4 run analyze statistics behavior-diagnostic tune-s5-metering behavioral-calibration figures report publish clean

all: check-env sketch network patch-geometry demand webster-timing scenario-s1 scenario-s2 scenario-s3 scenario-s4 scenario-s5 scenario-s2s4 run analyze statistics figures report

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

## فاز ۴: محاسبهٔ سیکل بهینهٔ چراغ S1 با روش وبستر (@ λ=۱.۰) -> config/signal_timing_S1.yml
webster-timing:
	$(PYTHON) src/08_webster_timing.py

## فاز ۴: ساخت شبکهٔ S1 (چراغ‌دار) - نسخهٔ fixed + actuated
scenario-s1: webster-timing
	$(PYTHON) scenarios/S1_signal/build_network.py

## فاز ۴: ساخت شبکهٔ S2 (نسخهٔ ۱: حذف گردش چپ زیر پل)
scenario-s2:
	$(PYTHON) scenarios/S2_rcut/build_network.py

## فاز ۴: ساخت شبکهٔ S4 (کانالیزاسیون + گردش راست آزاد)
scenario-s4:
	$(PYTHON) scenarios/S4_channelization/build_network.py

## فاز ۴: ساخت شبکهٔ S3 (میدان نامتقارن — هر دو گزینهٔ constrained/full)
scenario-s3:
	$(PYTHON) scenarios/S3_roundabout/build_network.py

## فاز ۴: ساخت شبکهٔ S5 (ترکیبی — metering/oneway_priority/oneway_yield، مبتنی بر حلقهٔ S3)
scenario-s5: scenario-s3
	$(PYTHON) scenarios/S5_hybrid/build_network.py

## فاز ۴ (نشست ۵): ساخت شبکهٔ ترکیبی S2+S4 — دو تابع موجود S2/S4 را روی یک
## plain-XML مشترک فراخوانی می‌کند، نیازمند اسکریپت‌های S2/S4 (بدون وابستگی
## به شبکهٔ ساخته‌شدهٔ آن‌ها، چون از plain مبنا شروع می‌کند)
scenario-s2s4:
	$(PYTHON) scenarios/S2_S4_combined/build_network.py

## فاز ۳-۴: اجرای همهٔ سناریوهای built (S0 + S1×۲) در ۵ سطح λ × ۱۰ seed
run:
	$(PYTHON) src/04_run_experiments.py

## فاز ۳-۴: استخراج KPI چند-سناریو/چند-λ/چند-seed + میانگین±CI۹۵٪ به outputs/tables/*.{csv,parquet}
analyze:
	$(PYTHON) src/05_extract_kpis.py

## فاز ۴: مقایسهٔ زوجی سناریوها روی seedهای مشترک (آزمون معنی‌داری + اندازهٔ اثر)
statistics:
	$(PYTHON) src/06_statistics.py

## فاز ۴: آزمون تشخیصی — S0/S1 با پارامترهای رفتاری پیش‌فرض SUMO (نه تهاجمی) تا سهم رفتار از سهم چراغ جدا شود
behavior-diagnostic:
	$(PYTHON) src/09_behavior_diagnostic.py

## فاز ۴ (نشست ۴): جست‌وجوی سبک سیکل چراغ متردهندهٔ S5-metering — اختیاری،
## در «all» نیست (مثل behavior-diagnostic)، چون نتیجه‌اش (۲۰ ثانیه) از قبل
## در scenario-s5 کدنویسی شده؛ فقط برای بازتولید مستندسازی تصمیم طراحی
tune-s5-metering:
	$(PYTHON) scenarios/S5_hybrid/tune_metering_cycle.py

## فاز ۶ (تأیید صریح کاربر): آزمون استحکام رفتاری دوهدفه با Optuna — رجوع به
## سربرگ src/12_behavioral_calibration.py برای این‌که چرا این calibration-to-
## groundtruth نیست. طولانی (~۴۸۰ اجرای SUMO)؛ در «all» نیست، resume-پذیر.
behavioral-calibration:
	$(PYTHON) src/12_behavioral_calibration.py

## فاز ۳: نمودار KPI به تفکیک پا + نمودار حساسیت به λ
## فاز ۴ (نشست جاری): + اسکچ شماتیک هر سناریو (src/11_scenario_diagrams.py)
## — نیازمند اینکه net.xml همهٔ سناریوها از قبل ساخته شده باشد (بعد از
## scenario-s1..scenario-s2s4 در زنجیرهٔ all)
figures:
	$(PYTHON) src/07_figures.py
	$(PYTHON) src/11_scenario_diagrams.py

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
