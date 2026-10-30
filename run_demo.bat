@echo off
REM Runs all four Kaagaz reads and leaves results in out\ for review.
cd /d C:\Users\TTPL-LNV-0319\Downloads\kaagaz
call .venv\Scripts\activate.bat
echo Running English register...
python -m kaagaz.cli read samples\register_en_clean.png --as-of 2026-10-31 --out out\en.csv
echo Running Marathi register...
python -m kaagaz.cli read samples\register_mr_photo.jpg --as-of 2026-10-31 --out out\mr.csv
echo Running worn register...
python -m kaagaz.cli read samples\register_worn.jpg --as-of 2026-10-31 --out out\worn.csv
echo Running court order...
python -m kaagaz.cli order samples\court_order_sample.pdf --out out\order.json
echo.
echo Done. Results are in the out\ folder.
