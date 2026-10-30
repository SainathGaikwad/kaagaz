"""Pages in, a verified roster and Section 479 results out.

    pages (bytes)  -> read_page (two model reads)  -> verify_row (law table, dates, agreement)
                   -> Rihai assess (deterministic)  -> results + UTRC memos
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from rihai.agent.draft import Particulars, draft
from rihai.eligibility import Charge, Prisoner, assess

from .extract import PageRead, RowRead, read_page
from .model import Model, Usage
from .verify import RowVerdict, verify_row


@dataclass
class Result:
    page_name: str
    verdict: RowVerdict
    status: str
    controlling: str
    max_years: Optional[float]
    days_served: Optional[int]
    eligible_on: Optional[str]
    release_mode: Optional[str]
    reasons: list[str]
    flags: list[str]
    memo: str
    unverified_rows: list[str] = field(default_factory=list)

    @property
    def identifier(self) -> str:
        return self.verdict.identifier

    def to_dict(self) -> dict:
        return {
            "page": self.page_name, "identifier": self.identifier, "accepted": self.verdict.accepted,
            "reading_issues": "; ".join(self.verdict.reasons),
            "charges": "; ".join(f"{c['act']} {c['section']}" for c in self.verdict.row.charges),
            "custody_start": self.verdict.row.custody_start,
            "first_time": self.verdict.row.first_time_offender, "other_cases": self.verdict.row.other_cases_pending,
            "status": self.status, "controlling": self.controlling, "max_years": self.max_years,
            "days_served": self.days_served, "eligible_on": self.eligible_on or "", "release_mode": self.release_mode or "",
            "engine_reasons": " | ".join(self.reasons), "flags": ",".join(self.flags),
        }


@dataclass
class RunReport:
    pages: list[tuple[str, PageRead]]
    verdicts: list[tuple[str, RowVerdict]]
    results: list[Result]
    usage: Usage
    as_of: date

    @property
    def accepted(self) -> list[Result]:
        return [r for r in self.results if r.verdict.accepted]

    @property
    def needs_human(self) -> list[Result]:
        return [r for r in self.results if not r.verdict.accepted]

    def counts(self) -> dict:
        c: dict = {}
        for r in self.results:
            c[r.status] = c.get(r.status, 0) + 1
        return c

    def csv(self) -> str:
        buf = io.StringIO()
        rows = [r.to_dict() for r in self.results]
        if not rows:
            return ""
        w = csv.DictWriter(buf, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
        return buf.getvalue()

    def memos(self, only_eligible: bool = True) -> str:
        out = []
        for r in self.results:
            if only_eligible and r.status not in ("ELIGIBLE", "MUST_RELEASE_MAX_TERM"):
                continue
            head = "" if r.verdict.accepted else "[READING NOT VERIFIED - confirm against the register before use]\n"
            out.append(head + r.memo)
        return "\n\n".join(out)


def to_prisoner(row: RowRead) -> Prisoner:
    return Prisoner(
        charges=[Charge(c["act"], c["section"]) for c in row.charges if c.get("act") not in ("OTHER", "", None)],
        custody_start=date.fromisoformat(row.custody_start) if row.custody_start else date.today(),
        first_time_offender=row.first_time_offender == "yes",
        multiple_cases_pending=row.other_cases_pending == "yes",
        delay_attributable_days=0,
        identifier=row.identifier or f"row-{row.row_no}",
    )


def assess_verdict(page_name: str, v: RowVerdict, as_of: date) -> Result:
    row = v.row
    if not row.custody_start or not row.charges:
        return Result(page_name, v, "NOT_ASSESSED", "", None, None, None, None,
                      ["not assessed: " + "; ".join(v.reasons)], [], f"{row.identifier or 'row-' + str(row.row_no)}: not assessed ({'; '.join(v.reasons)})")
    try:
        p = to_prisoner(row)
        a = assess(p, as_of=as_of)
    except Exception as e:  # a date the engine cannot take, etc.
        return Result(page_name, v, "NOT_ASSESSED", "", None, None, None, None, [f"not assessed: {e}"], [], f"{row.identifier}: not assessed ({e})")
    memo = draft(a, Particulars())["memo"]
    return Result(
        page_name, v, a.status.value, a.controlling.key if a.controlling else "", a.max_term_years, a.days_served,
        a.eligible_on.isoformat() if a.eligible_on else None, a.release_mode, list(a.reasons), list(a.flags), memo,
        unverified_rows=list(a.unverified),
    )


def run(model: Model, pages: list[tuple[str, bytes]], as_of: Optional[date] = None, audit: bool = True,
        require_audit: bool = True) -> RunReport:
    as_of = as_of or date.today()
    usage = Usage()
    page_reads: list[tuple[str, PageRead]] = []
    verdicts: list[tuple[str, RowVerdict]] = []
    results: list[Result] = []
    for name, image in pages:
        pr = read_page(model, image, audit=audit)
        usage.add(pr.usage)
        page_reads.append((name, pr))
        for row in pr.rows:
            v = verify_row(row, as_of=as_of, require_audit=require_audit and audit)
            verdicts.append((name, v))
            results.append(assess_verdict(name, v, as_of))
    return RunReport(pages=page_reads, verdicts=verdicts, results=results, usage=usage, as_of=as_of)


def reassess(report: RunReport, edited: list[dict], as_of: Optional[date] = None) -> RunReport:
    """After a human corrected rows (identifier, charges text, custody date, flags), re-verify and re-assess without
    calling the model again. `edited` entries: {page, row_no, identifier, charges: 'BNS 303(2); IPC 34', custody_start,
    first_time, other_cases}."""
    from rihai.eligibility.s479 import _split_charge
    as_of = as_of or report.as_of
    by_key = {(name, v.row.row_no): (name, v) for name, v in report.verdicts}
    new_verdicts: list[tuple[str, RowVerdict]] = []
    new_results: list[Result] = []
    for e in edited:
        key = (e["page"], int(e["row_no"]))
        name, old = by_key[key]
        row = old.row
        charges = []
        for part in str(e.get("charges", "")).split(";"):
            part = part.strip()
            if not part:
                continue
            try:
                act, sec = _split_charge(part)
            except ValueError:
                act, sec = "OTHER", part
            charges.append({"act": act.upper(), "section": sec, "as_printed": part})
        row.identifier = str(e.get("identifier", row.identifier)).strip()
        row.charges = charges
        row.custody_start = str(e.get("custody_start", row.custody_start)).strip()
        row.first_time_offender = e.get("first_time", row.first_time_offender)
        row.other_cases_pending = e.get("other_cases", row.other_cases_pending)
        if e.get("confirmed"):
            # the human has looked at the page: the audit disagreement is resolved by that look
            row.agreement = "agreed"
            row.disputes = []
            row.legible = True
        v = verify_row(row, as_of=as_of, require_audit=True)
        new_verdicts.append((name, v))
        new_results.append(assess_verdict(name, v, as_of))
    return RunReport(pages=report.pages, verdicts=new_verdicts, results=new_results, usage=report.usage, as_of=as_of)
