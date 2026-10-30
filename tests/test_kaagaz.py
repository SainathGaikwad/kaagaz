from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from kaagaz import schema as S
from kaagaz.extract import RowRead, compare, norm_date, norm_section, read_page
from kaagaz.images import load_pages
from kaagaz.model import FakeModel, MuseSpark, ReplayCache, fingerprint
from kaagaz.orders import compare_decision, replay_order
from kaagaz.pipeline import reassess, run
from kaagaz.verify import check_charge, name_like, plausible_date, verify_row

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"
AS_OF = date(2026, 10, 31)


def _strict(schema: dict) -> None:
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert sorted(schema["required"]) == sorted(schema["properties"])
    for v in schema["properties"].values():
        if v.get("type") == "object":
            _strict(v)
        if v.get("type") == "array" and v["items"].get("type") == "object":
            _strict(v["items"])


def test_schemas_are_strict_and_nameless():
    def keys(sch: dict) -> set[str]:
        out = set()
        for k, v in sch.get("properties", {}).items():
            out.add(k)
            if v.get("type") == "object":
                out |= keys(v)
            if v.get("type") == "array" and v["items"].get("type") == "object":
                out |= keys(v["items"])
        return out

    for sch in (S.PAGE_READ, S.AUDIT_READ, S.ORDER_READ):
        _strict(sch)
        assert not {k for k in keys(sch) if "name" in k.lower()}   # no name field anywhere
    assert "identifier" in S.ROW["properties"]


def test_normalisation():
    assert norm_section("३०३(२)") == "303(2)"
    assert norm_section("303 (2)") == "303(2)"
    assert norm_section("Sec. 120B") == "120B"
    assert norm_date("१२/०३/२०२५") == "2025-03-12"
    assert norm_date("10/01/2025") == "2025-01-10"
    assert norm_date("2025-1-5") == "2025-01-05"
    assert norm_date("") == ""


def test_charge_checks():
    assert check_charge({"act": "BNS", "section": "303(2)", "as_printed": "BNS 303(2)"}).status == "known"
    assert check_charge({"act": "IPC", "section": "34", "as_printed": "IPC 34"}).status == "derivative"
    assert check_charge({"act": "BNS", "section": "999", "as_printed": "BNS 999"}).status == "unknown"
    assert check_charge({"act": "BNS", "section": "303", "as_printed": "BNS 303"}).status == "umbrella"
    assert check_charge({"act": "OTHER", "section": "12", "as_printed": "Some Act 12"}).status == "other_act"
    assert check_charge({"act": "IPC", "section": "326", "as_printed": "IPC 326"}).life_or_death is True


def test_dates_and_names():
    assert plausible_date("2025-01-10", AS_OF)[0] == date(2025, 1, 10)
    assert "future" in plausible_date("2027-01-01", AS_OF)[1]
    assert "missing" in plausible_date("", AS_OF)[1]
    assert name_like("Ramesh Sitaram Pawar")
    assert name_like("सुरेश पांडुरंग वाघमारे")
    assert not name_like("UTP-2026/0417")
    assert not name_like("ब.क्र. ४५१२")
    assert not name_like("row-3")


def _row(**kw) -> RowRead:
    base = dict(row_no=1, identifier="UTP-1", charges=[{"act": "BNS", "section": "303(2)", "as_printed": "BNS 303(2)"}],
                custody_start="2025-01-10", custody_start_as_printed="10/01/2025", first_time_offender="yes",
                other_cases_pending="no", court="", legible=True, notes="")
    base.update(kw)
    return RowRead(**base)


def test_agreement_and_verdicts():
    r = _row()
    compare(r, {"row_no": 1, "identifier": "UTP-1", "charges": [{"act": "BNS", "section": "303 (2)", "as_printed": "BNS 303(2)"}],
                "custody_start": "10/01/2025", "custody_start_as_printed": "10/01/2025"})
    assert r.agreement == "agreed"
    v = verify_row(r, AS_OF)
    assert v.accepted and v.reasons == []

    r2 = _row()
    compare(r2, {"row_no": 1, "identifier": "UTP-1", "charges": [{"act": "BNS", "section": "303(2)", "as_printed": ""}],
                 "custody_start": "2025-01-16", "custody_start_as_printed": "16/01/2025"})
    assert r2.agreement == "disputed" and "custody date" in r2.disputes[0]
    v2 = verify_row(r2, AS_OF)
    assert not v2.accepted and any("second read" in x for x in v2.reasons)

    r3 = _row(identifier="Ramesh Pawar", agreement="agreed")
    v3 = verify_row(r3, AS_OF)
    assert v3.name_risk and not v3.accepted

    r4 = _row(agreement="agreed", charges=[{"act": "BNS", "section": "999", "as_printed": "BNS 999"}])
    assert not verify_row(r4, AS_OF).accepted

    r5 = _row()  # unaudited
    assert not verify_row(r5, AS_OF, require_audit=True).accepted
    assert verify_row(r5, AS_OF, require_audit=False).accepted


def test_best_date_fallback_from_as_printed():
    from kaagaz.extract import best_date, _rows_from
    assert best_date("", "09/05/2022") == "2022-05-09"      # model put the date only in the printed field
    assert best_date("2022-05-09", "nonsense") == "2022-05-09"
    assert best_date("unknown", "") == ""
    rows = _rows_from({"rows": [{"row_no": 1, "identifier": "UTP-1",
                                 "charges": [{"act": "BNS", "section": "303(2)", "as_printed": "BNS 303(2)"}],
                                 "custody_start": "", "custody_start_as_printed": "10/01/2025",
                                 "first_time_offender": "yes", "other_cases_pending": "no", "court": "", "legible": True, "notes": ""}]})
    assert rows[0].custody_start == "2025-01-10"


def test_fake_model_reads_samples_and_pipeline_assesses():
    model = FakeModel.from_samples(SAMPLES)
    pages = [("en", load_pages(SAMPLES / "register_en_clean.png")[0]),
             ("mr", load_pages(SAMPLES / "register_mr_photo.jpg")[0]),
             ("worn", load_pages(SAMPLES / "register_worn.jpg")[0])]
    rep = run(model, pages, as_of=AS_OF)
    assert len(rep.results) == 24
    assert rep.usage.calls == 6            # two reads per page
    by_id = {r.identifier: r for r in rep.results}
    assert by_id["UTP-2026/0417"].status == "ELIGIBLE" and by_id["UTP-2026/0417"].eligible_on == "2026-01-10"
    assert by_id["UTP-2026/0417"].verdict.accepted
    assert by_id["ब.क्र. ४५१२"].status == "ELIGIBLE" and by_id["ब.क्र. ४५१२"].eligible_on == "2026-03-12"
    assert by_id["UTP-2026/0698"].status == "NEEDS_REVIEW" and not by_id["UTP-2026/0698"].verdict.accepted
    assert by_id["UTP 7731"].status == "NOT_ASSESSED"          # smudged date: nothing guessed
    assert by_id["UTP 7752"].status == "MUST_RELEASE_MAX_TERM"
    assert by_id["UTP 7760"].status == "EXCLUDED_MULTIPLE_CASES"
    assert "UTP-2026/0417" in rep.memos()
    csv = rep.csv()
    assert "Ramesh" not in csv and "Pawar" not in csv       # no name reaches the output
    assert "Ramesh" not in rep.memos()


def test_audit_disagreement_blocks_a_row():
    noise = {1: {"custody_start": "2025-01-16", "custody_start_as_printed": "16/01/2025"}}
    model = FakeModel.from_samples(SAMPLES, audit_noise=noise)
    rep = run(model, [("en", load_pages(SAMPLES / "register_en_clean.png")[0])], as_of=AS_OF)
    r1 = rep.results[0]
    assert r1.identifier == "UTP-2026/0417" and not r1.verdict.accepted
    assert any("custody date: read 1 2025-01-10 / read 2 2025-01-16" in x for x in r1.verdict.reasons)
    # the human looks at the page and confirms the first reading
    rep2 = reassess(rep, [{"page": "en", "row_no": 1, "identifier": "UTP-2026/0417", "charges": "BNS 303(2)",
                           "custody_start": "2025-01-10", "first_time": "yes", "other_cases": "no", "confirmed": True}])
    assert rep2.results[0].verdict.accepted and rep2.results[0].status == "ELIGIBLE"


def test_order_replay():
    model = FakeModel.from_samples(SAMPLES)
    pages = load_pages(SAMPLES / "court_order_sample.pdf")
    rep = replay_order(model, pages)
    assert rep.decision == "released_on_bond" and rep.engine_status == "ELIGIBLE"
    assert rep.verdict == "agree"
    assert compare_decision("NOT_YET", "released_on_bail")[0] == "court_liberal"
    assert compare_decision("ELIGIBLE", "refused")[0] == "court_strict"
    assert compare_decision("UNKNOWN_SECTION", "refused")[0] == "engine_abstains"


def test_replay_cache_roundtrip(tmp_path):
    cache = ReplayCache(tmp_path)
    key = fingerprint(model="m", system="s", user_text="u", images=[b"abc"], schema={"a": 1}, schema_name="n")
    assert cache.get(key) is None
    cache.put(key, {"response": {"rows": []}})
    assert cache.get(key)["response"] == {"rows": []}
    m = MuseSpark(model="m", cache=cache, replay_only=True)
    out = m.extract(system="s", user_text="u", images=[b"abc"], schema={"a": 1}, schema_name="n")
    assert out.from_cache and out.data == {"rows": []}
    with pytest.raises(RuntimeError):
        m.extract(system="s", user_text="other", images=[b"abc"], schema={"a": 1}, schema_name="n")


def test_unknown_image_is_honest():
    model = FakeModel()
    pr = read_page(model, b"\xff\xd8not-a-real-image", audit=True)
    assert pr.page_kind == "other" and pr.rows == []
