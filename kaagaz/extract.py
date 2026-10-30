"""Two reads of the same page, then a deterministic comparison.

Read 1 (page read)  : the whole table, every column the schema names.
Read 2 (audit read) : the same page again, a different instruction, only the two columns that decide eligibility
                      (charge sections and custody date), row by row, with the row list from read 1 as the anchor.

A row is "agreed" when both reads give the same normalised set of sections and the same custody date. Anything else
is "disputed" and both readings are shown to the human. The point is not that the second read is better; it is that
two independent readings rarely make the same mistake, and when they differ nobody has to trust either.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from . import schema as S
from .model import Model, Reply, Usage

SYSTEM = """You are reading pages from Indian prison records: undertrial prisoner registers, Undertrial Review Committee (UTRC) lists and court orders, printed or handwritten, in English, Hindi or Marathi.

Rules you must follow:
1. Copy only what the page shows. Never infer, complete or guess a value. If a cell is not legible, leave the field empty (or "unknown") and set legible to false for that row.
2. Never output a person's name anywhere. The identifier is the register number for that row: the UTP number, bandi (prisoner) number, or case number. Prefer that over the plain serial/Sr. number - use the serial number only when the row has no UTP/bandi/case number. Give the identifier on its own (e.g. "UTP-2026/0417"), not combined with the serial number. If the only identifier on the page is a name, use the row position as "row-N".
3. Charges: give act and section normalised (acts: BNS, IPC, NDPS, ARMS, POCSO, MPA, MCOCA, UAPA, PMLA, IT, SCST, DPA, ITPA, ECA, PCA, MV, ELEC, WLPA, EXPL, GAMB, CGST, BNSS, CRPC; else OTHER), sub-sections in round brackets without spaces (303(2), 120B, 20(b)(ii)(B)), one charge per section even when the page writes "379, 34" under one act, and always keep the exact printed text in as_printed. "r/w" and "read with" join sections under the same act. If the act is not printed, use BNS for sections in a BNS-era register (2024 onwards) only when the page says BNS or Bharatiya Nyaya Sanhita somewhere; otherwise use OTHER.
4. Dates: convert to YYYY-MM-DD. Indian pages write day/month/year; Devanagari digits (०१२३४५६७८९) map to 0-9; "१२/०३/२०२५" is 2025-03-12. Keep the printed form in the as_printed field.
5. Previous conviction / first-time: if a column says no previous conviction (नाही, no, nil, first offender), first_time_offender is "yes"; if it records a conviction, "no"; otherwise "unknown". Other cases pending likewise.
6. Rows struck out or marked released are still returned, with a note saying so.
7. Abbreviations: I.P.C., भा.दं.वि., भा.द.वि., भादंवि = IPC; B.N.S., भा.न्या.सं., भान्यासं = BNS; भा.ना.सु.सं. = BNSS; Cr.P.C., फौ.प्र.सं. = CRPC; N.D.P.S., एन.डी.पी.एस. = NDPS; Arms Act, शस्त्र अधिनियम = ARMS; Bombay Prohibition Act, Maharashtra Prohibition Act, म.दा.का., महाराष्ट्र दारूबंदी कायदा = MPA; POCSO, पोक्सो = POCSO; SC/ST Act, अत्याचार प्रतिबंध = SCST; MCOCA, मोक्का = MCOCA."""

PAGE_READ_PROMPT = """Read this page and return EVERY row of its table, from the first to the last, in order. First count the data rows in the table (excluding the header), then return exactly that many entries - do not stop early, do not skip a row because it is faint or struck out, and do not summarise. A missed row means a prisoner is never reviewed. If a row is hard to read, still return it with legible set to false. If the page is not a register or list of prisoners, say so in page_kind and return no rows."""

AUDIT_PROMPT = PAGE_READ_PROMPT + """

This is a second, independent verification pass over the same page. Read it again carefully from the image and return every row, so the two readings can be compared."""


_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


def norm_section(s: str) -> str:
    s = (s or "").translate(_DEVANAGARI_DIGITS)
    s = s.strip().upper().replace(" ", "").replace("[", "(").replace("]", ")").replace("SEC.", "").replace("S.", "")
    s = re.sub(r"^SECTION", "", s)
    return s


def norm_act(a: str) -> str:
    return (a or "").strip().upper()


def charge_key(c: dict) -> str:
    return f"{norm_act(c.get('act'))}/{norm_section(c.get('section'))}"


_ISO = re.compile(r"\d{4}-\d{2}-\d{2}")


def best_date(*candidates: str) -> str:
    """Return the first candidate that yields a clean ISO date. The model sometimes fills custody_start, sometimes
    only custody_start_as_printed; take the date from whichever field has it, so a read is not wasted."""
    for c in candidates:
        d = norm_date(c or "")
        if _ISO.fullmatch(d):
            return d
    return ""


def norm_date(d: str) -> str:
    d = (d or "").translate(_DEVANAGARI_DIGITS).strip()
    # A model sometimes wraps the date in extra text (e.g. 's:"2026-10-20",as_printed:"20th October 2026"').
    # Search, don't just full-match, so the ISO date is recovered wherever it sits.
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", d)
    if m:
        y, mo, dd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= mo <= 12 and 1 <= dd <= 31:
            return f"{y:04d}-{mo:02d}-{dd:02d}"
    m = re.search(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})", d)
    if m:
        dd, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= mo <= 12 and 1 <= dd <= 31:
            return f"{y:04d}-{mo:02d}-{dd:02d}"
    return d


@dataclass
class RowRead:
    row_no: int
    identifier: str
    charges: list[dict]
    custody_start: str
    custody_start_as_printed: str = ""
    first_time_offender: str = "unknown"
    other_cases_pending: str = "unknown"
    court: str = ""
    legible: bool = True
    notes: str = ""
    # audit
    audit_charges: Optional[list[dict]] = None
    audit_custody_start: Optional[str] = None
    agreement: str = "unaudited"          # agreed | disputed | unaudited
    disputes: list[str] = field(default_factory=list)

    @property
    def charge_keys(self) -> list[str]:
        return sorted({charge_key(c) for c in self.charges})

    def to_dict(self) -> dict:
        return {
            "row_no": self.row_no, "identifier": self.identifier, "charges": self.charges,
            "custody_start": self.custody_start, "custody_start_as_printed": self.custody_start_as_printed,
            "first_time_offender": self.first_time_offender, "other_cases_pending": self.other_cases_pending,
            "court": self.court, "legible": self.legible, "notes": self.notes,
            "audit_charges": self.audit_charges, "audit_custody_start": self.audit_custody_start,
            "agreement": self.agreement, "disputes": self.disputes,
        }


@dataclass
class PageRead:
    page_kind: str
    language: str
    period_or_date: str
    rows: list[RowRead]
    usage: Usage = field(default_factory=Usage)
    raw_page: dict = field(default_factory=dict)
    raw_audit: Optional[dict] = None
    from_cache: bool = False


def _rows_from(data: dict) -> list[RowRead]:
    out = []
    for i, r in enumerate(data.get("rows", []), 1):
        out.append(RowRead(
            row_no=i,   # position in the returned list; the model's own row_no field is unreliable (it sometimes repeats)
            identifier=str(r.get("identifier", "")).strip(),
            charges=[{"act": norm_act(c.get("act")), "section": norm_section(c.get("section")), "as_printed": c.get("as_printed", "")}
                     for c in r.get("charges", [])],
            custody_start=best_date(r.get("custody_start", ""), r.get("custody_start_as_printed", "")),
            custody_start_as_printed=r.get("custody_start_as_printed", ""),
            first_time_offender=r.get("first_time_offender", "unknown"),
            other_cases_pending=r.get("other_cases_pending", "unknown"),
            court=r.get("court", ""),
            legible=bool(r.get("legible", True)),
            notes=r.get("notes", ""),
        ))
    return out


def _audit_view(a) -> tuple[list, str, str]:
    """Read charges + the two date fields from an audit entry, whether it is a raw dict or a parsed RowRead."""
    if isinstance(a, RowRead):
        return a.charges, a.custody_start, a.custody_start_as_printed
    return a.get("charges", []), a.get("custody_start", ""), a.get("custody_start_as_printed", "")


def compare(row: RowRead, audit) -> None:
    """Fill the audit fields of `row` from the second read and decide agreement."""
    charges_raw, cust, cust_printed = _audit_view(audit)
    a_charges = [{"act": norm_act(c.get("act")), "section": norm_section(c.get("section")), "as_printed": c.get("as_printed", "")}
                 for c in charges_raw]
    a_date = best_date(cust, cust_printed)
    row.audit_charges = a_charges
    row.audit_custody_start = a_date
    disputes = []
    k1 = row.charge_keys
    k2 = sorted({charge_key(c) for c in a_charges})
    if k1 != k2:
        disputes.append(f"sections: read 1 {', '.join(k1) or 'none'} / read 2 {', '.join(k2) or 'none'}")
    if row.custody_start != a_date:
        disputes.append(f"custody date: read 1 {row.custody_start or 'empty'} / read 2 {a_date or 'empty'}")
    row.disputes = disputes
    row.agreement = "disputed" if disputes else "agreed"


def _mark_only_one(row: RowRead) -> RowRead:
    """A row only one of the two reads returned: hold it and say so, never drop it. (legible is left as read - this is
    about corroboration, not legibility.)"""
    row.agreement = "disputed"
    note = "only one of the two reads returned this row - confirm it against the page"
    row.notes = (row.notes + "; " + note) if row.notes else note
    row.disputes = [note]
    return row


def read_page(model: Model, image: bytes, audit: bool = True) -> PageRead:
    r1: Reply = model.extract(system=SYSTEM, user_text=PAGE_READ_PROMPT, images=[image], schema=S.PAGE_READ, schema_name="page_read")
    data = r1.data
    page = PageRead(page_kind=data.get("page_kind", "other"), language=data.get("language", ""),
                    period_or_date=data.get("period_or_date", ""), rows=_rows_from(data), raw_page=data, from_cache=r1.from_cache)
    page.usage.add(r1.usage)
    if audit and page.rows:
        # The second read is a full, independent re-read with the same (reliable) instruction. Two opinions, compared
        # by identifier. A reasoning model occasionally returns a short/empty second pass; retry that read once if so,
        # rather than wrongly holding every row.
        r2: Reply = model.extract(system=SYSTEM, user_text=AUDIT_PROMPT, images=[image], schema=S.PAGE_READ, schema_name="page_read_audit")
        audit = _rows_from(r2.data)
        if len(audit) * 2 < len(page.rows) and not r2.from_cache:
            r2b: Reply = model.extract(system=SYSTEM, user_text=AUDIT_PROMPT + "\n\n(Return every row; the previous attempt was incomplete.)",
                                       images=[image], schema=S.PAGE_READ, schema_name="page_read_audit2")
            page.usage.add(r2b.usage)
            if len(_rows_from(r2b.data)) > len(audit):
                r2, audit = r2b, _rows_from(r2b.data)
        page.raw_audit = r2.data
        page.usage.add(r2.usage)
        a_by_ident = {r.identifier.strip(): r for r in audit if r.identifier}
        a_by_no = {r.row_no: r for r in audit}
        matched = set()
        for row in page.rows:
            a = a_by_ident.get(row.identifier.strip()) if row.identifier else None
            if a is None:
                a = a_by_no.get(row.row_no)
            if a is None:
                _mark_only_one(row)
            else:
                matched.add(id(a))
                compare(row, a)
        # Union: a row only the second read saw is surfaced and held, never silently dropped.
        r1_ids = {r.identifier.strip() for r in page.rows if r.identifier}
        r1_nos = {r.row_no for r in page.rows}
        for a in audit:
            if id(a) in matched:
                continue
            if (a.identifier.strip() and a.identifier.strip() in r1_ids) or (a.row_no in r1_nos):
                continue
            page.rows.append(_mark_only_one(a))
        page.rows.sort(key=lambda r: r.row_no)
    return page
