"""Deterministic checks on what the model read. The model proposes; this module decides whether a row may go on.

A row is ACCEPTED only when: the two reads agree; every charge resolves in the Rihai law table (or is a derivative
section that borrows another's punishment); the custody date parses and is plausible; the identifier does not look
like a person's name. Everything else is NEEDS_HUMAN with the reasons spelled out. The eligibility engine still runs
on such rows so the human sees what is at stake, but their results are marked as resting on an unverified reading.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from rihai.eligibility.s479 import _is_derivative
from rihai.eligibility import Charge
from rihai.law import UnknownSection, lookup

from .extract import RowRead

# An identifier that is only letters and spaces, two words or more, looks like a name. Register ids carry digits.
_NAME_LIKE = re.compile(r"^[A-Za-zऀ-ॿ.' ]+$")


@dataclass
class ChargeCheck:
    act: str
    section: str
    as_printed: str
    status: str            # known | umbrella | derivative | unknown | other_act
    key: str = ""
    title: str = ""
    max_years: Optional[float] = None
    life_or_death: bool = False
    note: str = ""

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class RowVerdict:
    row: RowRead
    accepted: bool
    reasons: list[str] = field(default_factory=list)
    charges: list[ChargeCheck] = field(default_factory=list)
    name_risk: bool = False

    @property
    def identifier(self) -> str:
        return self.row.identifier

    def to_dict(self) -> dict:
        d = self.row.to_dict()
        d.update({"accepted": self.accepted, "reasons": self.reasons, "name_risk": self.name_risk,
                  "charge_checks": [c.to_dict() for c in self.charges]})
        return d


def check_charge(c: dict) -> ChargeCheck:
    act, sec, printed = c.get("act", ""), c.get("section", ""), c.get("as_printed", "")
    if act in ("OTHER", "", None):
        return ChargeCheck(act, sec, printed, "other_act", note="act not recognised; a human must name the Act")
    if _is_derivative(Charge(act, sec)):
        return ChargeCheck(act, sec, printed, "derivative", key=f"{act}/{sec}",
                           note="takes the punishment of the principal offence")
    try:
        row = lookup(act, sec)
    except UnknownSection:
        return ChargeCheck(act, sec, printed, "unknown", note="not in the law table; nothing is guessed")
    except Exception as e:  # unknown act spelled oddly
        return ChargeCheck(act, sec, printed, "other_act", note=str(e))
    if row.umbrella:
        return ChargeCheck(act, sec, printed, "umbrella", key=row.key, title=row.title,
                           note=f"sub-section needed; variants: {', '.join(row.variants)}. {row.notes}".strip())
    return ChargeCheck(act, sec, printed, "known", key=row.key, title=row.title, max_years=row.max_years,
                       life_or_death=row.excluded_life_or_death)


def plausible_date(iso: str, as_of: Optional[date] = None) -> tuple[Optional[date], str]:
    as_of = as_of or date.today()
    if not iso:
        return None, "custody date missing"
    try:
        d = date.fromisoformat(iso)
    except ValueError:
        return None, f"custody date not a date: {iso!r}"
    if d > as_of:
        return None, f"custody date {iso} is in the future"
    if d.year < 1990:
        return None, f"custody date {iso} is implausibly old"
    return d, ""


def name_like(identifier: str) -> bool:
    s = identifier.strip()
    if not s or any(ch.isdigit() for ch in s):
        return False
    return bool(_NAME_LIKE.match(s)) and len(s.split()) >= 2


def verify_row(row: RowRead, as_of: Optional[date] = None, require_audit: bool = True) -> RowVerdict:
    reasons: list[str] = []
    checks = [check_charge(c) for c in row.charges]
    if not row.charges:
        reasons.append("no charge section read")
    for ck in checks:
        if ck.status == "unknown":
            reasons.append(f"{ck.act} {ck.section} ({ck.as_printed or 'as read'}): {ck.note}")
        elif ck.status == "other_act":
            reasons.append(f"{ck.as_printed or ck.section}: {ck.note}")
        elif ck.status == "umbrella":
            reasons.append(f"{ck.act} {ck.section}: {ck.note}")
    d, why = plausible_date(row.custody_start, as_of)
    if why:
        reasons.append(why)
    if not row.legible:
        reasons.append("the reader marked this row as not fully legible")
    if require_audit and row.agreement != "agreed":
        if row.agreement == "unaudited":
            reasons.append("no audit read")
        else:
            reasons.extend("second read disagrees: " + x for x in row.disputes)
    nr = name_like(row.identifier)
    if nr:
        reasons.append("identifier looks like a person's name; replace it with the register number")
    if not row.identifier:
        reasons.append("no identifier")
    return RowVerdict(row=row, accepted=not reasons, reasons=reasons, charges=checks, name_risk=nr)
