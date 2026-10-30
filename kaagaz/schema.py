"""JSON schemas handed to the model (strict mode: every key required, no extra keys) and the act list it may use.

There is deliberately no field for a person's name anywhere in these schemas. A register page carries names; the
roster that leaves this tool carries identifiers only.
"""
from __future__ import annotations

# Acts the model may normalise to. Anything else becomes OTHER and is refused downstream.
ACTS = ["BNS", "IPC", "NDPS", "ARMS", "POCSO", "MPA", "MCOCA", "UAPA", "PMLA", "IT", "SCST", "DPA", "ITPA",
        "ECA", "PCA", "MV", "ELEC", "WLPA", "EXPL", "GAMB", "CGST", "BNSS", "CRPC", "OTHER"]

YES_NO_UNKNOWN = ["yes", "no", "unknown"]


def _obj(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "additionalProperties": False, "properties": props,
            "required": required if required is not None else list(props)}


CHARGE = _obj({
    "act": {"type": "string", "enum": ACTS,
            "description": "The Act, normalised. BNS = Bharatiya Nyaya Sanhita 2023; IPC = Indian Penal Code 1860."},
    "section": {"type": "string",
                "description": "Section number as printed, sub-section in round brackets, no spaces: 303(2), 120B, 20(b)(ii)(B)."},
    "as_printed": {"type": "string", "description": "The charge text exactly as it appears on the page, including the Act."},
})

ROW = _obj({
    "row_no": {"type": "integer", "description": "1-based position of the row in the table on this page."},
    "identifier": {"type": "string",
                   "description": "The register serial number, UTP number, bandi number or case number as printed. NEVER a person's name."},
    "charges": {"type": "array", "items": CHARGE},
    "custody_start": {"type": "string",
                      "description": "Date the person entered custody (admission / remand date) as YYYY-MM-DD; empty string if not printed or not legible."},
    "custody_start_as_printed": {"type": "string", "description": "That date exactly as printed, in its own script and format."},
    "first_time_offender": {"type": "string", "enum": YES_NO_UNKNOWN,
                            "description": "yes if the page says no previous conviction; no if it records a previous conviction; unknown otherwise."},
    "other_cases_pending": {"type": "string", "enum": YES_NO_UNKNOWN,
                            "description": "yes if the page records other pending cases for this person; no if it says none; unknown otherwise."},
    "court": {"type": "string", "description": "Court or case reference as printed, or empty."},
    "legible": {"type": "boolean", "description": "false if any field of this row could not be read with confidence."},
    "notes": {"type": "string", "description": "Anything unusual: struck-out row, overwritten cell, remark column."},
})

PAGE_READ = _obj({
    "page_kind": {"type": "string", "enum": ["undertrial_register", "utrc_list", "court_order", "other"]},
    "language": {"type": "string", "description": "Main language(s) of the page, e.g. 'mr', 'hi', 'en' or 'mr+en'."},
    "period_or_date": {"type": "string", "description": "Quarter, date or heading date printed on the page, as printed, or empty."},
    "rows": {"type": "array", "items": ROW},
})

# The audit read is deliberately narrower: only the two columns that decide eligibility.
AUDIT_ROW = _obj({
    "row_no": {"type": "integer"},
    "identifier": {"type": "string"},
    "charges": {"type": "array", "items": CHARGE},
    "custody_start": {"type": "string", "description": "YYYY-MM-DD or empty."},
    "custody_start_as_printed": {"type": "string"},
})

AUDIT_READ = _obj({"rows": {"type": "array", "items": AUDIT_ROW}})

ORDER_READ = _obj({
    "court": {"type": "string"},
    "case_reference": {"type": "string", "description": "Bail application / criminal case number as printed."},
    "order_date": {"type": "string", "description": "YYYY-MM-DD or empty."},
    "charges": {"type": "array", "items": CHARGE},
    "custody_start": {"type": "string", "description": "Date of arrest or first remand as stated in the order, YYYY-MM-DD or empty."},
    "first_time_offender": {"type": "string", "enum": YES_NO_UNKNOWN},
    "other_cases_pending": {"type": "string", "enum": YES_NO_UNKNOWN},
    "section_479_invoked": {"type": "boolean", "description": "true if the order discusses Section 479 BNSS or Section 436A CrPC."},
    "decision": {"type": "string", "enum": ["released_on_bond", "released_on_bail", "refused", "other"]},
    "decision_quote": {"type": "string", "description": "The operative sentence of the order, verbatim."},
    "period_served_quote": {"type": "string", "description": "The sentence stating how long the applicant has been in custody, verbatim, or empty."},
})
