"""Builds the synthetic sample pages under samples/ and their ground truth.

Everything here is fiction: the names, numbers, cases and dates are invented. The pages imitate the layout of
undertrial registers and UTRC lists so that the reader can be exercised without any real prisoner data.

    python scripts/make_samples.py            # writes samples/*.png|jpg|pdf and samples/*.truth.json
"""
from __future__ import annotations

import io
import json
import math
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "samples"
OUT.mkdir(exist_ok=True)

CSS = """
@font-face { font-family: 'Dev'; src: local('Noto Sans Devanagari'); }
body { margin: 0; background: white; }
.page { width: 1480px; min-height: 1000px; padding: 48px 56px; box-sizing: border-box; font-family: 'DejaVu Serif', 'Noto Sans Devanagari', serif; color: #111; }
.page.mr { font-family: 'Noto Sans Devanagari', 'Hind', sans-serif; }
.page.mono { font-family: 'DejaVu Sans Mono', monospace; }
h1 { font-size: 26px; text-align: center; margin: 0 0 4px 0; letter-spacing: 0.5px; }
h2 { font-size: 20px; text-align: center; margin: 0 0 18px 0; font-weight: normal; }
.meta { display: flex; justify-content: space-between; font-size: 16px; margin-bottom: 10px; }
table { border-collapse: collapse; width: 100%; font-size: 17px; }
th, td { border: 1px solid #222; padding: 7px 8px; vertical-align: top; }
th { background: #eee; font-weight: bold; text-align: center; }
td.c { text-align: center; }
tr.struck td { text-decoration: line-through; color: #444; }
.hand { font-family: 'DejaVu Sans', sans-serif; font-style: italic; color: #1a237e; font-size: 15px; }
.foot { margin-top: 26px; font-size: 15px; display: flex; justify-content: space-between; }
.stamp { position: absolute; right: 80px; bottom: 40px; border: 3px solid #7b1fa2; color: #7b1fa2; padding: 6px 10px; font-size: 14px; transform: rotate(-8deg); opacity: 0.7; font-family: 'DejaVu Sans', sans-serif; }
"""


def table_html(headers: list[str], rows: list[list[str]], struck: set[int] = frozenset(), center_cols: set[int] = frozenset()) -> str:
    h = "".join(f"<th>{x}</th>" for x in headers)
    body = []
    for i, r in enumerate(rows, 1):
        cls = ' class="struck"' if i in struck else ""
        cells = "".join(f'<td{" class=c" if j in center_cols else ""}>{x}</td>' for j, x in enumerate(r))
        body.append(f"<tr{cls}>{cells}</tr>")
    return f"<table><thead><tr>{h}</tr></thead><tbody>{''.join(body)}</tbody></table>"


# ---------------------------------------------------------------- page 1: English, clean scan
P1_ROWS = [
    ["1", "UTP-2026/0417", "Ramesh Sitaram Pawar", "BNS 303(2)", "10/01/2025", "JMFC Pune, RCC 221/2025", "No", "No", ""],
    ["2", "UTP-2026/0533", "Sunil Dattatray More", "IPC 379, 34", "22/03/2024", "JMFC Pune, RCC 1180/2024", "Yes", "No", ""],
    ["3", "UTP-2026/0611", "Imran Yusuf Shaikh", "BNS 318(4), 316(2)", "01/03/2025", "CJM Pune, RCC 342/2025", "No", "No", ""],
    ["4", "UTP-2026/0698", "Vikas Ashok Jadhav", "NDPS 8(c) r/w 20(b)(ii)(B)", "15/11/2024", "Spl. Judge (NDPS) Pune, SC 55/2025", "No", "No", ""],
    ["5", "UTP-2026/0702", "Santosh Bhimrao Kamble", "IPC 420, 467, 468, 471", "05/06/2023", "Sessions Court Pune, SC 410/2023", "No", "Yes", "Another case at Khadki PS"],
    ["6", "UTP-2026/0745", "Ganesh Laxman Shinde", "BNS 137(2)", "20/08/2025", "Sessions Court Pune, SC 120/2025", "No", "No", ""],
    ["7", "UTP-2026/0788", "Rahul Popat Kale", "Arms Act 25(1-B)(a)", "02/02/2026", "JMFC Pune, RCC 77/2026", "No", "No", ""],
    ["8", "UTP-2026/0801", "Mahesh Tukaram Chavan", "IPC 326", "18/04/2024", "Sessions Court Pune, SC 300/2024", "Yes", "No", ""],
    ["9", "UTP-2026/0812", "Akash Dilip Sonawane", "BNS 115(2), 351(3)", "11/09/2025", "JMFC Pune, RCC 905/2025", "No", "No", ""],
    ["10", "UTP-2026/0830", "Nitin Baban Thorat", "MPA 65(e)", "29/07/2026", "JMFC Pune, RCC 1300/2026", "No", "No", ""],
]
P1_HEADERS = ["Sr.", "UTP No.", "Name of prisoner", "Sections", "Date of admission", "Court & Case No.", "Previous conviction", "Other cases pending", "Remarks"]


def page1_html() -> str:
    return f"""<html><head><meta charset="utf-8"><style>{CSS}</style></head><body><div class="page mono">
<h1>YERAWADA CENTRAL PRISON, PUNE</h1>
<h2>List of undertrial prisoners for review under Section 479 BNSS &mdash; quarter ending 30/09/2026</h2>
<div class="meta"><span>Annexure A &nbsp;|&nbsp; Page 1 of 3</span><span>Prepared on: 03/10/2026</span></div>
{table_html(P1_HEADERS, P1_ROWS, center_cols={0, 6, 7})}
<div class="foot"><span>Verified by: Jailor (Records)</span><span>Superintendent, Yerawada Central Prison</span></div>
<div class="stamp">RECEIVED<br>DLSA PUNE 06 OCT 2026</div>
</div></body></html>"""


def p1_truth() -> dict:
    def ch(s):
        return s
    rows = [
        {"row_no": 1, "identifier": "UTP-2026/0417", "charges": [{"act": "BNS", "section": "303(2)", "as_printed": "BNS 303(2)"}], "custody_start": "2025-01-10", "custody_start_as_printed": "10/01/2025", "first_time_offender": "yes", "other_cases_pending": "no", "court": "JMFC Pune, RCC 221/2025", "legible": True, "notes": ""},
        {"row_no": 2, "identifier": "UTP-2026/0533", "charges": [{"act": "IPC", "section": "379", "as_printed": "IPC 379, 34"}, {"act": "IPC", "section": "34", "as_printed": "IPC 379, 34"}], "custody_start": "2024-03-22", "custody_start_as_printed": "22/03/2024", "first_time_offender": "no", "other_cases_pending": "no", "court": "JMFC Pune, RCC 1180/2024", "legible": True, "notes": ""},
        {"row_no": 3, "identifier": "UTP-2026/0611", "charges": [{"act": "BNS", "section": "318(4)", "as_printed": "BNS 318(4), 316(2)"}, {"act": "BNS", "section": "316(2)", "as_printed": "BNS 318(4), 316(2)"}], "custody_start": "2025-03-01", "custody_start_as_printed": "01/03/2025", "first_time_offender": "yes", "other_cases_pending": "no", "court": "CJM Pune, RCC 342/2025", "legible": True, "notes": ""},
        {"row_no": 4, "identifier": "UTP-2026/0698", "charges": [{"act": "NDPS", "section": "8(c)", "as_printed": "NDPS 8(c) r/w 20(b)(ii)(B)"}, {"act": "NDPS", "section": "20(b)(ii)(B)", "as_printed": "NDPS 8(c) r/w 20(b)(ii)(B)"}], "custody_start": "2024-11-15", "custody_start_as_printed": "15/11/2024", "first_time_offender": "yes", "other_cases_pending": "no", "court": "Spl. Judge (NDPS) Pune, SC 55/2025", "legible": True, "notes": ""},
        {"row_no": 5, "identifier": "UTP-2026/0702", "charges": [{"act": "IPC", "section": s, "as_printed": "IPC 420, 467, 468, 471"} for s in ("420", "467", "468", "471")], "custody_start": "2023-06-05", "custody_start_as_printed": "05/06/2023", "first_time_offender": "yes", "other_cases_pending": "yes", "court": "Sessions Court Pune, SC 410/2023", "legible": True, "notes": "Another case at Khadki PS"},
        {"row_no": 6, "identifier": "UTP-2026/0745", "charges": [{"act": "BNS", "section": "137(2)", "as_printed": "BNS 137(2)"}], "custody_start": "2025-08-20", "custody_start_as_printed": "20/08/2025", "first_time_offender": "yes", "other_cases_pending": "no", "court": "Sessions Court Pune, SC 120/2025", "legible": True, "notes": ""},
        {"row_no": 7, "identifier": "UTP-2026/0788", "charges": [{"act": "ARMS", "section": "25(1-B)(a)", "as_printed": "Arms Act 25(1-B)(a)"}], "custody_start": "2026-02-02", "custody_start_as_printed": "02/02/2026", "first_time_offender": "yes", "other_cases_pending": "no", "court": "JMFC Pune, RCC 77/2026", "legible": True, "notes": ""},
        {"row_no": 8, "identifier": "UTP-2026/0801", "charges": [{"act": "IPC", "section": "326", "as_printed": "IPC 326"}], "custody_start": "2024-04-18", "custody_start_as_printed": "18/04/2024", "first_time_offender": "no", "other_cases_pending": "no", "court": "Sessions Court Pune, SC 300/2024", "legible": True, "notes": ""},
        {"row_no": 9, "identifier": "UTP-2026/0812", "charges": [{"act": "BNS", "section": "115(2)", "as_printed": "BNS 115(2), 351(3)"}, {"act": "BNS", "section": "351(3)", "as_printed": "BNS 115(2), 351(3)"}], "custody_start": "2025-09-11", "custody_start_as_printed": "11/09/2025", "first_time_offender": "yes", "other_cases_pending": "no", "court": "JMFC Pune, RCC 905/2025", "legible": True, "notes": ""},
        {"row_no": 10, "identifier": "UTP-2026/0830", "charges": [{"act": "MPA", "section": "65(e)", "as_printed": "MPA 65(e)"}], "custody_start": "2026-07-29", "custody_start_as_printed": "29/07/2026", "first_time_offender": "yes", "other_cases_pending": "no", "court": "JMFC Pune, RCC 1300/2026", "legible": True, "notes": ""},
    ]
    return {"images": ["register_en_clean.png"], "page_read": {"page_kind": "utrc_list", "language": "en", "period_or_date": "quarter ending 30/09/2026", "rows": rows}}


# ---------------------------------------------------------------- page 2: Marathi, photographed
P2_HEADERS = ["अ.क्र.", "बंदी क्र.", "बंद्याचे नाव", "कलम", "प्रवेश दिनांक", "न्यायालय व केस क्र.", "पूर्वीची शिक्षा", "इतर खटले", "शेरा"]
P2_ROWS = [
    ["१", "ब.क्र. ४५१२", "सुरेश पांडुरंग वाघमारे", "भा.न्या.सं. ३०३(२)", "१२/०३/२०२५", "प्र.न्या.दं. पुणे, आर.सी.सी. ४०१/२०२५", "नाही", "नाही", ""],
    ["२", "ब.क्र. ४५२०", "प्रकाश नामदेव साळुंखे", "भा.दं.वि. ३८०, ४५७", "०५/०८/२०२३", "सत्र न्यायालय पुणे, एस.सी. ८८/२०२४", "होय", "नाही", ""],
    ["३", "ब.क्र. ४५३३", "अमोल रघुनाथ भोसले", "भा.न्या.सं. ३१८(४)", "२०/०९/२०२४", "मु.न्या.दं. पुणे, आर.सी.सी. ९९०/२०२४", "नाही", "नाही", ""],
    ["४", "ब.क्र. ४५४७", "सलीम अब्दुल पठाण", "एन.डी.पी.एस. २०(ब)(ii)(ब)", "०३/११/२०२३", "विशेष न्यायालय पुणे, एस.सी. १२/२०२४", "नाही", "होय", "खडकी पो.ठा. गुन्हा प्रलंबित"],
    ["५", "ब.क्र. ४५६०", "दीपक शंकर लोंढे", "भा.दं.वि. ३०७", "१८/०१/२०२३", "सत्र न्यायालय पुणे, एस.सी. ४०/२०२३", "नाही", "नाही", ""],
    ["६", "ब.क्र. ४५७८", "किरण बाळू कदम", "भा.न्या.सं. ११५(२), ३५१(३)", "२५/१२/२०२५", "प्र.न्या.दं. पुणे, आर.सी.सी. १५०/२०२६", "नाही", "नाही", ""],
    ["७", "ब.क्र. ४५९१", "योगेश मारुती डोंगरे", "भा.न्या.सं. ३०३", "०७/०६/२०२५", "प्र.न्या.दं. पुणे, आर.सी.सी. ७१२/२०२५", "नाही", "नाही", ""],
    ["८", "ब.क्र. ४६०३", "राजू विठ्ठल तांबे", "म.दा.का. ६५(ई)", "१४/०४/२०२६", "प्र.न्या.दं. पुणे, आर.सी.सी. ४३०/२०२६", "नाही", "नाही", ""],
]


def page2_html() -> str:
    return f"""<html><head><meta charset="utf-8"><style>{CSS}</style></head><body><div class="page mr">
<h1>येरवडा मध्यवर्ती कारागृह, पुणे</h1>
<h2>भा.ना.सु.सं. कलम ४७९ अन्वये पुनर्विलोकनासाठी विचाराधीन बंद्यांची यादी &mdash; तिमाही समाप्त ३०/०९/२०२६</h2>
<div class="meta"><span>परिशिष्ट अ &nbsp;|&nbsp; पान २ पैकी १</span><span>दिनांक: ०३/१०/२०२६</span></div>
{table_html(P2_HEADERS, P2_ROWS, center_cols={0, 6, 7})}
<div class="foot"><span>तपासले: तुरुंगाधिकारी (अभिलेख)</span><span>अधीक्षक, येरवडा मध्यवर्ती कारागृह</span></div>
</div></body></html>"""


def p2_truth() -> dict:
    rows = [
        {"row_no": 1, "identifier": "ब.क्र. ४५१२", "charges": [{"act": "BNS", "section": "303(2)", "as_printed": "भा.न्या.सं. ३०३(२)"}], "custody_start": "2025-03-12", "custody_start_as_printed": "१२/०३/२०२५", "first_time_offender": "yes", "other_cases_pending": "no", "court": "प्र.न्या.दं. पुणे, आर.सी.सी. ४०१/२०२५", "legible": True, "notes": ""},
        {"row_no": 2, "identifier": "ब.क्र. ४५२०", "charges": [{"act": "IPC", "section": "380", "as_printed": "भा.दं.वि. ३८०, ४५७"}, {"act": "IPC", "section": "457", "as_printed": "भा.दं.वि. ३८०, ४५७"}], "custody_start": "2023-08-05", "custody_start_as_printed": "०५/०८/२०२३", "first_time_offender": "no", "other_cases_pending": "no", "court": "सत्र न्यायालय पुणे, एस.सी. ८८/२०२४", "legible": True, "notes": ""},
        {"row_no": 3, "identifier": "ब.क्र. ४५३३", "charges": [{"act": "BNS", "section": "318(4)", "as_printed": "भा.न्या.सं. ३१८(४)"}], "custody_start": "2024-09-20", "custody_start_as_printed": "२०/०९/२०२४", "first_time_offender": "yes", "other_cases_pending": "no", "court": "मु.न्या.दं. पुणे, आर.सी.सी. ९९०/२०२४", "legible": True, "notes": ""},
        {"row_no": 4, "identifier": "ब.क्र. ४५४७", "charges": [{"act": "NDPS", "section": "20(b)(ii)(b)", "as_printed": "एन.डी.पी.एस. २०(ब)(ii)(ब)"}], "custody_start": "2023-11-03", "custody_start_as_printed": "०३/११/२०२३", "first_time_offender": "yes", "other_cases_pending": "yes", "court": "विशेष न्यायालय पुणे, एस.सी. १२/२०२४", "legible": True, "notes": "खडकी पो.ठा. गुन्हा प्रलंबित"},
        {"row_no": 5, "identifier": "ब.क्र. ४५६०", "charges": [{"act": "IPC", "section": "307", "as_printed": "भा.दं.वि. ३०७"}], "custody_start": "2023-01-18", "custody_start_as_printed": "१८/०१/२०२३", "first_time_offender": "yes", "other_cases_pending": "no", "court": "सत्र न्यायालय पुणे, एस.सी. ४०/२०२३", "legible": True, "notes": ""},
        {"row_no": 6, "identifier": "ब.क्र. ४५७८", "charges": [{"act": "BNS", "section": "115(2)", "as_printed": "भा.न्या.सं. ११५(२), ३५१(३)"}, {"act": "BNS", "section": "351(3)", "as_printed": "भा.न्या.सं. ११५(२), ३५१(३)"}], "custody_start": "2025-12-25", "custody_start_as_printed": "२५/१२/२०२५", "first_time_offender": "yes", "other_cases_pending": "no", "court": "प्र.न्या.दं. पुणे, आर.सी.सी. १५०/२०२६", "legible": True, "notes": ""},
        {"row_no": 7, "identifier": "ब.क्र. ४५९१", "charges": [{"act": "BNS", "section": "303", "as_printed": "भा.न्या.सं. ३०३"}], "custody_start": "2025-06-07", "custody_start_as_printed": "०७/०६/२०२५", "first_time_offender": "yes", "other_cases_pending": "no", "court": "प्र.न्या.दं. पुणे, आर.सी.सी. ७१२/२०२५", "legible": True, "notes": ""},
        {"row_no": 8, "identifier": "ब.क्र. ४६०३", "charges": [{"act": "MPA", "section": "65(e)", "as_printed": "म.दा.का. ६५(ई)"}], "custody_start": "2026-04-14", "custody_start_as_printed": "१४/०४/२०२६", "first_time_offender": "yes", "other_cases_pending": "no", "court": "प्र.न्या.दं. पुणे, आर.सी.सी. ४३०/२०२६", "legible": True, "notes": ""},
    ]
    return {"images": ["register_mr_photo.jpg"], "page_read": {"page_kind": "utrc_list", "language": "mr", "period_or_date": "तिमाही समाप्त ३०/०९/२०२६", "rows": rows}}


# ---------------------------------------------------------------- page 3: worn English register, one illegible date, one struck row
P3_HEADERS = ["Sr.", "UTP No.", "Name", "Sections of law", "Date of admission", "Prev. conviction", "Other cases", "Remarks"]
P3_ROWS = [
    ["1", "UTP 7718", "Dnyaneshwar Kisan Bhise", "IPC 392, 34", "09/05/2022", "Yes", "No", ""],
    ["2", "UTP 7725", "Sachin Vilas Gore", "BNS 309(4)", "30/10/2024", "No", "No", ""],
    ["3", "UTP 7731", "Farooq Hasan Ansari", "IPC 457, 380", "17/06/2023", "No", "No", ""],
    ["4", "UTP 7740", "Pravin Arun Mane", "BNS 64", "12/12/2024", "No", "No", ""],
    ["5", "UTP 7752", "Balasaheb Rama Patil", "IPC 498A, 323", "02/07/2023", "No", "No", ""],
    ["6", "UTP 7760", "Shubham Ankush Lad", "BNS 303(2), 317(2)", "14/02/2025", "No", "Yes", "<span class=hand>Released 20/08/2026</span>"],
]


def page3_html() -> str:
    return f"""<html><head><meta charset="utf-8"><style>{CSS}</style></head><body><div class="page">
<h1>UNDERTRIAL PRISONERS &mdash; REGISTER EXTRACT</h1>
<h2>Barrack 4 &nbsp;&middot;&nbsp; Reviewed for Section 479 BNSS &nbsp;&middot;&nbsp; as on 30/09/2026</h2>
<div class="meta"><span>Register No. 14 / Folio 212</span><span>Extract date 02/10/2026</span></div>
{table_html(P3_HEADERS, P3_ROWS, struck={6}, center_cols={0, 5, 6})}
<div class="foot"><span>Entered by: Head Warder (Records)</span><span>Checked: Jailor Gr. I</span></div>
</div></body></html>"""


def p3_truth() -> dict:
    rows = [
        {"row_no": 1, "identifier": "UTP 7718", "charges": [{"act": "IPC", "section": "392", "as_printed": "IPC 392, 34"}, {"act": "IPC", "section": "34", "as_printed": "IPC 392, 34"}], "custody_start": "2022-05-09", "custody_start_as_printed": "09/05/2022", "first_time_offender": "no", "other_cases_pending": "no", "court": "", "legible": True, "notes": ""},
        {"row_no": 2, "identifier": "UTP 7725", "charges": [{"act": "BNS", "section": "309(4)", "as_printed": "BNS 309(4)"}], "custody_start": "2024-10-30", "custody_start_as_printed": "30/10/2024", "first_time_offender": "yes", "other_cases_pending": "no", "court": "", "legible": True, "notes": ""},
        {"row_no": 3, "identifier": "UTP 7731", "charges": [{"act": "IPC", "section": "457", "as_printed": "IPC 457, 380"}, {"act": "IPC", "section": "380", "as_printed": "IPC 457, 380"}], "custody_start": "", "custody_start_as_printed": "", "first_time_offender": "yes", "other_cases_pending": "no", "court": "", "legible": False, "notes": "date of admission smudged"},
        {"row_no": 4, "identifier": "UTP 7740", "charges": [{"act": "BNS", "section": "64", "as_printed": "BNS 64"}], "custody_start": "2024-12-12", "custody_start_as_printed": "12/12/2024", "first_time_offender": "yes", "other_cases_pending": "no", "court": "", "legible": True, "notes": ""},
        {"row_no": 5, "identifier": "UTP 7752", "charges": [{"act": "IPC", "section": "498A", "as_printed": "IPC 498A, 323"}, {"act": "IPC", "section": "323", "as_printed": "IPC 498A, 323"}], "custody_start": "2023-07-02", "custody_start_as_printed": "02/07/2023", "first_time_offender": "yes", "other_cases_pending": "no", "court": "", "legible": True, "notes": ""},
        {"row_no": 6, "identifier": "UTP 7760", "charges": [{"act": "BNS", "section": "303(2)", "as_printed": "BNS 303(2), 317(2)"}, {"act": "BNS", "section": "317(2)", "as_printed": "BNS 303(2), 317(2)"}], "custody_start": "2025-02-14", "custody_start_as_printed": "14/02/2025", "first_time_offender": "yes", "other_cases_pending": "yes", "court": "", "legible": True, "notes": "row struck out; remark: Released 20/08/2026"},
    ]
    return {"images": ["register_worn.jpg"], "page_read": {"page_kind": "undertrial_register", "language": "en", "period_or_date": "as on 30/09/2026", "rows": rows}}


# ---------------------------------------------------------------- court order (PDF, fiction)
def order_html() -> str:
    return f"""<html><head><meta charset="utf-8"><style>
body {{ font-family: 'DejaVu Serif', serif; font-size: 15px; line-height: 1.55; color: #111; margin: 0; }}
.p {{ padding: 60px 70px; }}
h1 {{ text-align: center; font-size: 17px; margin: 0; }}
h2 {{ text-align: center; font-size: 15px; font-weight: normal; margin: 2px 0 18px 0; }}
.center {{ text-align: center; }}
p {{ text-align: justify; margin: 10px 0; }}
.sig {{ margin-top: 36px; text-align: right; }}
</style></head><body><div class="p">
<h1>IN THE COURT OF THE ADDITIONAL SESSIONS JUDGE, PUNE</h1>
<h2>(Presided over by Shri A. B. Deshmukh, Additional Sessions Judge)</h2>
<p class="center"><b>Criminal Bail Application No. 1234 of 2026</b><br>(in Sessions Case No. 318 of 2024, arising out of C.R. No. 210 of 2024 of Yerawada Police Station)</p>
<p class="center">Applicant (undertrial prisoner, UTP No. 2024/1187) &nbsp;&nbsp; versus &nbsp;&nbsp; The State of Maharashtra</p>
<p class="center">Shri P. R. Joshi, Legal Aid Defence Counsel, for the applicant.<br>Smt. S. K. Nair, Additional Public Prosecutor, for the State.</p>
<p class="center"><b>ORDER</b> &nbsp;(dated 20th October 2026)</p>
<p>1. This is an application under Section 479 of the Bharatiya Nagarik Suraksha Sanhita, 2023 for release of the applicant, who is facing trial for offences punishable under Sections 379 and 411 read with Section 34 of the Indian Penal Code. The applicant was arrested on 14th March 2024 and has been in judicial custody since that date.</p>
<p>2. It is not disputed by the learned Additional Public Prosecutor that the applicant has no previous conviction and that no other case is pending against him. The maximum punishment prescribed for the offence under Section 379 of the Indian Penal Code is imprisonment of either description for a term which may extend to three years, and the same is the position under Section 411.</p>
<p>3. The report of the Superintendent, Yerawada Central Prison, dated 1st October 2026 shows that the applicant has undergone detention for a period of two years, six months and seventeen days as on that date, which exceeds one-third, and indeed one-half, of the maximum period of imprisonment specified for the offences.</p>
<p>4. In view of the first proviso to sub-section (1) of Section 479 of the Sanhita, and the directions of the Hon'ble Supreme Court in <i>In Re: Inhuman Conditions in 1382 Prisons</i>, the applicant, being a first-time offender who has undergone detention for more than one-third of the maximum period of imprisonment, is entitled to be released on bond.</p>
<p class="center"><b>ORDER</b></p>
<p>(i) The application is allowed. The applicant shall be released on his executing a personal bond of Rs. 15,000/- (Rupees fifteen thousand only), without sureties, to the satisfaction of the learned trial court.</p>
<p>(ii) The applicant shall attend the trial court on every date of hearing and shall not leave the jurisdiction of the Pune Police Commissionerate without the permission of the trial court.</p>
<p>(iii) The application stands disposed of accordingly.</p>
<div class="sig">Pune<br>20th October 2026<br><br>(A. B. Deshmukh)<br>Additional Sessions Judge, Pune</div>
</div></body></html>"""


def order_truth() -> dict:
    return {"images": ["court_order_sample.pdf"], "order_read": {
        "court": "Court of the Additional Sessions Judge, Pune", "case_reference": "Criminal Bail Application No. 1234 of 2026",
        "order_date": "2026-10-20",
        "charges": [{"act": "IPC", "section": "379", "as_printed": "Sections 379 and 411 read with Section 34 of the Indian Penal Code"},
                    {"act": "IPC", "section": "411", "as_printed": "Sections 379 and 411 read with Section 34 of the Indian Penal Code"},
                    {"act": "IPC", "section": "34", "as_printed": "Sections 379 and 411 read with Section 34 of the Indian Penal Code"}],
        "custody_start": "2024-03-14", "first_time_offender": "yes", "other_cases_pending": "no", "section_479_invoked": True,
        "decision": "released_on_bond",
        "decision_quote": "The application is allowed. The applicant shall be released on his executing a personal bond of Rs. 15,000/- (Rupees fifteen thousand only), without sureties, to the satisfaction of the learned trial court.",
        "period_served_quote": "the applicant has undergone detention for a period of two years, six months and seventeen days as on that date",
    }}


# ---------------------------------------------------------------- degradation
def photograph(img: Image.Image, seed: int, angle: float = 2.2, blur: float = 0.9, noise: int = 14, quality: int = 62,
               shadow: float = 0.35) -> bytes:
    rnd = random.Random(seed)
    im = img.convert("RGB")
    # paper tint and uneven lighting
    w, h = im.size
    grad = Image.new("L", (w, h))
    gd = ImageDraw.Draw(grad)
    for x in range(0, w, 4):
        v = int(255 * (1 - shadow * (x / w) ** 1.5))
        gd.rectangle([x, 0, x + 4, h], fill=v)
    tint = Image.new("RGB", (w, h), (246, 240, 226))
    im = Image.composite(im, tint, Image.new("L", (w, h), 230))
    im = Image.composite(im, Image.new("RGB", (w, h), (40, 36, 30)), grad.point(lambda p: 255 - int((255 - p) * 0.9)))
    # rotation and a slight perspective skew
    im = im.rotate(angle, resample=Image.BICUBIC, expand=True, fillcolor=(90, 86, 80))
    w, h = im.size
    dx = int(w * 0.02)
    coeffs = _perspective_coeffs([(0, 0), (w, 0), (w, h), (0, h)], [(dx, 0), (w - dx // 2, dx // 3), (w, h), (0, h - dx // 2)])
    im = im.transform((w, h), Image.PERSPECTIVE, coeffs, Image.BICUBIC, fillcolor=(90, 86, 80))
    im = im.filter(ImageFilter.GaussianBlur(blur))
    # sensor noise
    px = im.load()
    for _ in range(int(w * h * 0.02)):
        x, y = rnd.randrange(w), rnd.randrange(h)
        r, g, b = px[x, y]
        d = rnd.randint(-noise, noise)
        px[x, y] = (max(0, min(255, r + d)), max(0, min(255, g + d)), max(0, min(255, b + d)))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def _perspective_coeffs(src, dst):
    import numpy as np
    matrix = []
    for (x, y), (u, v) in zip(dst, src):
        matrix.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        matrix.append([0, 0, 0, x, y, 1, -v * x, -v * y])
    A = np.array(matrix, dtype=float)
    B = np.array([c for p in src for c in p], dtype=float)
    res = np.linalg.solve(A, B)
    return res.tolist()


def wear(img: Image.Image, seed: int, smudge_box: tuple[int, int, int, int]) -> bytes:
    rnd = random.Random(seed)
    im = img.convert("RGB")
    w, h = im.size
    # fade (gentle: the page must stay readable; only the one smudged cell should defeat the reader)
    im = ImageEnhance.Contrast(im).enhance(0.84)
    im = ImageEnhance.Brightness(im).enhance(1.03)
    # yellowed paper + a few light stains, kept away from the table text
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for _ in range(4):
        cx, cy = rnd.randrange(w), rnd.randrange(h)
        rx, ry = rnd.randrange(50, 150), rnd.randrange(30, 110)
        od.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=(150, 110, 40, rnd.randrange(12, 26)))
    overlay = overlay.filter(ImageFilter.GaussianBlur(20))
    im = Image.alpha_composite(im.convert("RGBA"), overlay).convert("RGB")
    # one cell genuinely illegible: the date of row 3, blurred hard and darkened (this is the NOT_ASSESSED case)
    x0, y0, x1, y1 = smudge_box
    region = im.crop((x0, y0, x1, y1)).filter(ImageFilter.GaussianBlur(8))
    region = ImageEnhance.Brightness(region).enhance(0.78)
    im.paste(region, (x0, y0))
    sm = Image.new("RGBA", (x1 - x0, y1 - y0), (60, 50, 40, 85))
    im.paste(Image.alpha_composite(im.crop((x0, y0, x1, y1)).convert("RGBA"), sm).convert("RGB"), (x0, y0))
    im = im.rotate(-0.6, resample=Image.BICUBIC, expand=True, fillcolor=(236, 230, 214))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=80)
    return buf.getvalue()


def render(html: str, pdf: bool = False) -> bytes:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1480, "height": 1000}, device_scale_factor=1)
        page.set_content(html, wait_until="load")
        page.wait_for_timeout(300)
        if pdf:
            data = page.pdf(format="A4", print_background=True, margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
        else:
            data = page.screenshot(full_page=True, type="png")
        browser.close()
    return data


def find_cell_box(html: str, row: int, col: int) -> tuple[int, int, int, int]:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1480, "height": 1000}, device_scale_factor=1)
        page.set_content(html, wait_until="load")
        box = page.locator(f"tbody tr:nth-child({row}) td:nth-child({col})").bounding_box()
        browser.close()
    return (int(box["x"]) + 2, int(box["y"]) + 2, int(box["x"] + box["width"]) - 2, int(box["y"] + box["height"]) - 2)


def main() -> None:
    # page 1: clean scan
    png = render(page1_html())
    (OUT / "register_en_clean.png").write_bytes(png)
    (OUT / "register_en_clean.truth.json").write_text(json.dumps(p1_truth(), ensure_ascii=False, indent=1), encoding="utf-8")
    # page 2: photographed
    png2 = render(page2_html())
    (OUT / "register_mr_photo.jpg").write_bytes(photograph(Image.open(io.BytesIO(png2)), seed=7))
    (OUT / "register_mr_photo.truth.json").write_text(json.dumps(p2_truth(), ensure_ascii=False, indent=1), encoding="utf-8")
    # page 3: worn, with the date of row 3 smudged
    h3 = page3_html()
    png3 = render(h3)
    box = find_cell_box(h3, 3, 5)
    (OUT / "register_worn.jpg").write_bytes(wear(Image.open(io.BytesIO(png3)), seed=11, smudge_box=box))
    (OUT / "register_worn.truth.json").write_text(json.dumps(p3_truth(), ensure_ascii=False, indent=1), encoding="utf-8")
    # court order: PDF plus its first page as JPEG (the hash the fake model answers to)
    pdf = render(order_html(), pdf=True)
    (OUT / "court_order_sample.pdf").write_bytes(pdf)
    sys.path.insert(0, str(ROOT))
    from kaagaz.images import load_pages
    pages = load_pages(pdf, "court_order_sample.pdf")
    (OUT / "court_order_sample.pdf.p1.jpg").write_bytes(pages[0])
    (OUT / "court_order_sample.truth.json").write_text(json.dumps(order_truth(), ensure_ascii=False, indent=1), encoding="utf-8")
    print("wrote", sorted(p.name for p in OUT.iterdir()))


if __name__ == "__main__":
    main()
