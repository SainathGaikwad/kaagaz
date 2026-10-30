# Running Kaagaz on the laptop (PowerShell)

The Meta Model API is reachable only from the Windows side, so every real model call runs here. Nothing below prints the key.

## One-time setup

```powershell
cd C:\Users\TTPL-LNV-0319\Downloads\kaagaz
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
notepad .env           # one line: MODEL_API_KEY=...   (create the file if it does not exist)
```

## Check the key and the API

```powershell
python -m kaagaz.cli check
```

Expected: `key found (NN characters). API answered; ... models: ...` and `muse-spark-1.3 - present`. Paste that
output into the chat (it never contains the key).

## First real read

```powershell
python -m kaagaz.cli read samples\register_en_clean.png --as-of 2026-10-31 --out out\en.csv
python -m kaagaz.cli read samples\register_mr_photo.jpg  --as-of 2026-10-31 --out out\mr.csv
python -m kaagaz.cli read samples\register_worn.jpg      --as-of 2026-10-31 --out out\worn.csv
python -m kaagaz.cli order samples\court_order_sample.pdf --out out\order.json
```

Each command prints a table and a summary line. Paste the printed output into the chat. The model's full answers
are saved under `kaagaz_cache\` (JSON, no secrets) and under `out\` - those folders can be shared as they are.

## If something fails

* `401 invalid_api_key`: the key in `.env` is wrong or has spaces around it.
* `404 model_not_found`: run `python -m kaagaz.cli check` and set `KAAGAZ_MODEL=<an id from the list>` in `.env`.
* `400` mentioning `strict` or `response_format`: paste the whole error; the schema call shape will be adjusted.
* A long wait: a page costs two calls of roughly 20-60 seconds each; a PDF is one call per page.

## The interface

```powershell
streamlit run app.py
```

Sidebar: Reader = "Muse Spark (live)". Pick a sample page or upload one, press "Read the page(s)".
