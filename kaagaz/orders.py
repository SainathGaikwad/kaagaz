"""Court order replay: read a published bail order, run the engine on the facts as of the order date, and compare.

    agree          the engine and the court reached the same conclusion
    court_liberal  the court released although the engine says the threshold was not (yet) met or s.479 did not apply
    court_strict   the court refused although the engine says the threshold was met   <- the finding that matters
    engine_abstains the engine could not assess (unknown section, needs review, no custody date)

Every order replayed is one more row of evidence about where the law table or the rule encoding is wrong.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from rihai.eligibility import Charge, Prisoner, assess

from . import schema as S
from .extract import SYSTEM, norm_act, norm_date, norm_section
from .model import Model, Usage
from .verify import ChargeCheck, check_charge

ORDER_PROMPT = """Read this court order. Extract the court, the case reference, the date of the order, every charge section the applicant faces (act + section + the text as printed), the date the applicant was taken into custody (arrest or first remand) if the order states it, whether the order treats the applicant as a first-time offender (no previous conviction), whether other cases are said to be pending, whether Section 479 BNSS or Section 436A CrPC is discussed, and the decision: released on bond, released on bail, refused, or other. Quote the operative sentence of the decision verbatim, and the sentence stating the period already spent in custody, verbatim. Do not output any person's name."""


@dataclass
class OrderReplay:
    court: str
    case_reference: str
    order_date: str
    charges: list[dict]
    custody_start: str
    first_time_offender: str
    other_cases_pending: str
    section_479_invoked: bool
    decision: str
    decision_quote: str
    period_served_quote: str
    checks: list[ChargeCheck] = field(default_factory=list)
    engine_status: str = ""
    engine_eligible_on: Optional[str] = None
    engine_reasons: list[str] = field(default_factory=list)
    verdict: str = ""
    verdict_note: str = ""
    usage: Usage = field(default_factory=Usage)
    from_cache: bool = False

    def to_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k not in ("checks", "usage")}
        d["checks"] = [c.to_dict() for c in self.checks]
        return d


def compare_decision(engine_status: str, decision: str) -> tuple[str, str]:
    engine_yes = engine_status in ("ELIGIBLE", "MUST_RELEASE_MAX_TERM")
    engine_no = engine_status in ("NOT_YET", "EXCLUDED_LIFE_OR_DEATH", "EXCLUDED_MULTIPLE_CASES")
    court_yes = decision in ("released_on_bond", "released_on_bail")
    court_no = decision == "refused"
    if engine_status in ("NEEDS_REVIEW", "UNKNOWN_SECTION", "NOT_ASSESSED") or decision == "other":
        return "engine_abstains", "the engine could not assess this order, or the decision is not a release/refusal"
    if engine_yes and court_yes:
        return "agree", "both say release"
    if engine_no and court_no:
        return "agree", "both say not yet / not under this section"
    if engine_no and court_yes:
        return "court_liberal", "the court released where the engine's reading of the section does not reach release"
    if engine_yes and court_no:
        return "court_strict", "the court refused where the engine says the threshold was met: check the facts and the table"
    return "engine_abstains", "no comparable outcome"


def replay_order(model: Model, pages: list[bytes]) -> OrderReplay:
    reply = model.extract(system=SYSTEM, user_text=ORDER_PROMPT, images=pages, schema=S.ORDER_READ, schema_name="order_read")
    d = reply.data
    charges = [{"act": norm_act(c.get("act")), "section": norm_section(c.get("section")), "as_printed": c.get("as_printed", "")}
               for c in d.get("charges", [])]
    rep = OrderReplay(
        court=d.get("court", ""), case_reference=d.get("case_reference", ""), order_date=norm_date(d.get("order_date", "")),
        charges=charges, custody_start=norm_date(d.get("custody_start", "")),
        first_time_offender=d.get("first_time_offender", "unknown"), other_cases_pending=d.get("other_cases_pending", "unknown"),
        section_479_invoked=bool(d.get("section_479_invoked", False)), decision=d.get("decision", "other"),
        decision_quote=d.get("decision_quote", ""), period_served_quote=d.get("period_served_quote", ""),
        usage=reply.usage, from_cache=reply.from_cache,
    )
    rep.checks = [check_charge(c) for c in charges]
    def _d(s):
        try:
            return date.fromisoformat(s) if s else None
        except ValueError:
            return None
    cs = _d(rep.custody_start)                 # parse each date on its own: a malformed order_date must not
    as_of = _d(rep.order_date) or date.today()  # null out a custody date that read fine
    if cs is None or not charges:
        rep.engine_status = "NOT_ASSESSED"
        rep.engine_reasons = ["custody date or charges missing from the order as read"]
    else:
        p = Prisoner(charges=[Charge(c["act"], c["section"]) for c in charges if c["act"] not in ("OTHER", "")],
                     custody_start=cs, first_time_offender=rep.first_time_offender == "yes",
                     multiple_cases_pending=rep.other_cases_pending == "yes", identifier=rep.case_reference or "order")
        a = assess(p, as_of=as_of)
        rep.engine_status = a.status.value
        rep.engine_eligible_on = a.eligible_on.isoformat() if a.eligible_on else None
        rep.engine_reasons = list(a.reasons)
    rep.verdict, rep.verdict_note = compare_decision(rep.engine_status, rep.decision)
    return rep
