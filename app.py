"""Kaagaz - Streamlit front end.

    streamlit run app.py

Three modes in the sidebar: Muse Spark live (needs MODEL_API_KEY), recorded answers (replays kaagaz_cache/ without a
key), and offline sample answers (the samples' ground truth; not the model, clearly labelled).
"""
from __future__ import annotations

import io
import json
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from kaagaz import __version__
from kaagaz.images import load_pages
from kaagaz.model import FakeModel, MuseSpark, ReplayCache, load_api_key
from kaagaz.orders import replay_order
from kaagaz.pipeline import RunReport, reassess, run

ROOT = Path(__file__).resolve().parent
SAMPLES = ROOT / "samples"
CACHE_DIR = ROOT / "kaagaz_cache"

st.set_page_config(page_title="Kaagaz - register page to Section 479 list", page_icon="📄", layout="wide")

STATUS_COLOUR = {"ELIGIBLE": "green", "MUST_RELEASE_MAX_TERM": "green", "NOT_YET": "orange"}
STATUS_HELP = {
    "ELIGIBLE": "threshold under s.479(1) met: release on bond (first offence) or bail",
    "MUST_RELEASE_MAX_TERM": "full maximum term served: third proviso, no discretion",
    "NOT_YET": "threshold not yet reached; date shown",
    "EXCLUDED_LIFE_OR_DEATH": "an offence carries death or life; s.479 does not apply",
    "EXCLUDED_MULTIPLE_CASES": "s.479(2): other cases pending; flagged if the date has passed",
    "NEEDS_REVIEW": "the law table cannot settle it without a human",
    "UNKNOWN_SECTION": "a section the table does not know; nothing guessed",
    "NOT_ASSESSED": "the reading lacks a custody date or any charge",
}

# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.title("Kaagaz")
    st.caption(f"v{__version__} · the model reads, the code checks, a lawyer decides")
    mode = st.radio("Reader", ["Muse Spark (live)", "Recorded answers (no key needed)", "Offline sample answers (not the model)"],
                    help="Live calls Meta Model API and records every answer under kaagaz_cache/. Recorded replays those answers. "
                         "Offline uses the samples' ground truth so the interface can be tried without any model at all.")
    as_of = st.date_input("Assess as on", date.today())
    audit = st.checkbox("Second, independent read (audit)", True,
                        help="The page is read twice with different instructions; a row is accepted only when both reads agree.")
    model_name = st.text_input("Model", "muse-spark-1.3")
    key_present = bool(load_api_key())
    if mode.startswith("Muse"):
        st.write("API key:", "found" if key_present else "**missing** - put MODEL_API_KEY in .env or .streamlit/secrets.toml")
    st.write(f"Recorded answers on disk: {len(list(CACHE_DIR.glob('*.json'))) if CACHE_DIR.exists() else 0}")
    st.markdown("---")
    st.markdown("No names. The schema the model fills has no name field; the identifier is the register number. "
                "A row whose identifier looks like a name is held back.")


def make_model():
    if mode.startswith("Offline"):
        return FakeModel.from_samples(SAMPLES)
    cache = ReplayCache(CACHE_DIR)
    return MuseSpark(model=model_name, cache=cache, replay_only=mode.startswith("Recorded"))


def status_md(s: str) -> str:
    c = STATUS_COLOUR.get(s, "red")
    return f":{c}[{s}]"


# ------------------------------------------------------------------ tabs
tab_reg, tab_order, tab_how = st.tabs(["Register page", "Court order replay", "How it works"])

with tab_reg:
    st.markdown("Upload a photographed or scanned page of an undertrial register or UTRC list (JPG, PNG or PDF), or pick a sample.")
    c1, c2 = st.columns([2, 1])
    with c1:
        up = st.file_uploader("Page(s)", type=["jpg", "jpeg", "png", "webp", "pdf"], accept_multiple_files=True, key="reg_up")
    with c2:
        sample = st.selectbox("or a sample page", ["(none)", "register_en_clean.png", "register_mr_photo.jpg", "register_worn.jpg"], key="reg_sample")
    pages: list[tuple[str, bytes]] = []
    if up:
        for f in up:
            data = f.read()
            for i, b in enumerate(load_pages(data, f.name), 1):
                pages.append((f"{f.name}#p{i}" if f.name.lower().endswith(".pdf") else f.name, b))
    elif sample != "(none)":
        pages.append((sample, load_pages(SAMPLES / sample)[0]))
    if pages:
        cols = st.columns(min(3, len(pages)))
        for i, (name, b) in enumerate(pages[:3]):
            cols[i].image(b, caption=name, width="stretch")
        if len(pages) > 3:
            st.caption(f"... and {len(pages) - 3} more page(s)")
    go = st.button("Read the page(s)", type="primary", disabled=not pages)
    if go:
        model = make_model()
        with st.spinner("Reading with " + ("Muse Spark" if mode.startswith("Muse") else "recorded answers" if mode.startswith("Recorded") else "sample answers") + " ..."):
            try:
                st.session_state["report"] = run(model, pages, as_of=as_of, audit=audit)
                st.session_state["report_mode"] = mode
            except Exception as e:
                st.error(f"{type(e).__name__}: {e}")
    rep: RunReport | None = st.session_state.get("report")
    if rep is not None:
        if st.session_state.get("report_mode", "").startswith("Offline"):
            st.warning("Offline sample answers: this is the samples' ground truth, not a model reading.")
        u = rep.usage
        m = st.columns(6)
        m[0].metric("Rows read", len(rep.results))
        m[1].metric("Accepted", len(rep.accepted))
        m[2].metric("Need a human", len(rep.needs_human))
        m[3].metric("Model calls", u.calls, help=f"{u.cached} answered from recorded answers")
        m[4].metric("Tokens in / out", f"{u.input_tokens} / {u.output_tokens}")
        m[5].metric("Seconds", f"{u.seconds:.1f}")
        for name, pr in rep.pages:
            st.caption(f"{name}: {pr.page_kind}, language {pr.language or '-'}, heading date {pr.period_or_date or '-'}, {len(pr.rows)} rows"
                       + (" (from recorded answers)" if pr.from_cache else ""))
        st.markdown("**Summary:** " + " · ".join(f"{k} {v}" for k, v in sorted(rep.counts().items())))

        rows = []
        for r in rep.results:
            v = r.verdict
            rows.append({
                "page": r.page_name, "row": v.row.row_no, "identifier": r.identifier,
                "reading": "accepted" if v.accepted else "CHECK",
                "charges": "; ".join(f"{c['act']} {c['section']}" for c in v.row.charges),
                "custody_start": v.row.custody_start, "first_time": v.row.first_time_offender, "other_cases": v.row.other_cases_pending,
                "status": r.status, "eligible_on": r.eligible_on or "", "controlling": r.controlling,
                "why": "; ".join(v.reasons) if not v.accepted else (r.reasons[0] if r.reasons else ""),
            })
        df = pd.DataFrame(rows)

        def _style(row):
            colour = {"ELIGIBLE": "#e5f4e4", "MUST_RELEASE_MAX_TERM": "#e5f4e4", "NOT_YET": "#f9eeda"}.get(row["status"], "#fbebeb")
            styles = [""] * len(row)
            styles[list(row.index).index("status")] = f"background-color: {colour}"
            if row["reading"] == "CHECK":
                styles[list(row.index).index("reading")] = "background-color: #f9ece7; font-weight: bold"
            return styles

        st.dataframe(df.style.apply(_style, axis=1), width="stretch", hide_index=True)

        disputed = [(n, v) for n, v in rep.verdicts if v.row.agreement == "disputed" or not v.accepted]
        if disputed:
            with st.expander(f"Rows held back ({len(disputed)}): what the two reads said"):
                for n, v in disputed:
                    r = v.row
                    st.markdown(f"**{n} row {r.row_no} · {r.identifier or '(no identifier)'}**")
                    for reason in v.reasons:
                        st.write("• " + reason)
                    if r.audit_charges is not None:
                        st.caption(f"read 1: {', '.join(c['act'] + ' ' + c['section'] for c in r.charges) or '-'} · {r.custody_start or '-'} "
                                   f"({r.custody_start_as_printed or 'as printed: -'})  |  read 2: {', '.join(c['act'] + ' ' + c['section'] for c in r.audit_charges) or '-'} · {r.audit_custody_start or '-'}")

        st.markdown("#### Correct and confirm")
        st.caption("Edit any cell against the page, tick confirmed for rows you have looked at, then re-assess. No model call is made.")
        edit_df = df[["page", "row", "identifier", "charges", "custody_start", "first_time", "other_cases"]].copy()
        edit_df["confirmed"] = False
        edited = st.data_editor(edit_df, width="stretch", hide_index=True, key="editor",
                                column_config={"first_time": st.column_config.SelectboxColumn(options=["yes", "no", "unknown"]),
                                               "other_cases": st.column_config.SelectboxColumn(options=["yes", "no", "unknown"]),
                                               "confirmed": st.column_config.CheckboxColumn()})
        if st.button("Re-assess with these corrections"):
            edits = [{"page": e["page"], "row_no": int(e["row"]), "identifier": e["identifier"], "charges": e["charges"],
                      "custody_start": e["custody_start"], "first_time": e["first_time"], "other_cases": e["other_cases"],
                      "confirmed": bool(e["confirmed"])} for e in edited.to_dict("records")]
            st.session_state["report"] = reassess(rep, edits, as_of=as_of)
            st.rerun()

        d1, d2, d3 = st.columns(3)
        d1.download_button("Download results (.csv)", rep.csv(), file_name="kaagaz_results.csv")
        d2.download_button("Download UTRC memos (.txt)", rep.memos(), file_name="kaagaz_memos.txt")
        d3.download_button("Download the raw reads (.json)", json.dumps(
            [{"page": n, "page_kind": pr.page_kind, "rows": [r.to_dict() for r in pr.rows]} for n, pr in rep.pages],
            ensure_ascii=False, indent=1), file_name="kaagaz_reads.json")
        with st.expander("UTRC memos for the eligible rows"):
            st.code(rep.memos() or "(none)", language=None)

with tab_order:
    st.markdown("Upload a published bail order (PDF or image) or use the sample. The order is read, the engine runs on its facts as of the order date, and the two conclusions are compared.")
    o1, o2 = st.columns([2, 1])
    with o1:
        oup = st.file_uploader("Order", type=["pdf", "jpg", "jpeg", "png"], key="order_up")
    with o2:
        osample = st.checkbox("use the sample order", value=oup is None, key="order_sample")
    obytes: list[bytes] = []
    oname = ""
    if oup is not None:
        obytes = load_pages(oup.read(), oup.name)
        oname = oup.name
    elif osample:
        obytes = load_pages(SAMPLES / "court_order_sample.pdf")
        oname = "court_order_sample.pdf"
    if obytes:
        st.image(obytes[0], caption=f"{oname} (page 1 of {len(obytes)})", width=520)
    if st.button("Read the order and replay it", type="primary", disabled=not obytes):
        model = make_model()
        with st.spinner("Reading ..."):
            try:
                st.session_state["order"] = replay_order(model, obytes)
            except Exception as e:
                st.error(f"{type(e).__name__}: {e}")
    orep = st.session_state.get("order")
    if orep is not None:
        verdict_colour = {"agree": "green", "court_liberal": "orange", "court_strict": "red", "engine_abstains": "gray"}[orep.verdict]
        st.markdown(f"### :{verdict_colour}[{orep.verdict}]  ·  {orep.verdict_note}")
        a, b = st.columns(2)
        with a:
            st.markdown("**What the order says (as read)**")
            st.write(f"Court: {orep.court or '-'}")
            st.write(f"Case: {orep.case_reference or '-'} · order date {orep.order_date or '-'}")
            st.write("Charges: " + (", ".join(f"{c['act']} {c['section']}" for c in orep.charges) or "-"))
            for ck in orep.checks:
                st.caption(f"{ck.act} {ck.section}: {ck.status} {('- ' + ck.note) if ck.note else ''}")
            st.write(f"Custody from {orep.custody_start or '-'} · first-time {orep.first_time_offender} · other cases {orep.other_cases_pending} · s.479 discussed: {orep.section_479_invoked}")
            st.write(f"Decision: **{orep.decision}**")
            if orep.decision_quote:
                st.caption("“" + orep.decision_quote + "”")
            if orep.period_served_quote:
                st.caption("“" + orep.period_served_quote + "”")
        with b:
            st.markdown("**What the engine says on those facts**")
            st.markdown(status_md(orep.engine_status) + (f" · eligible from {orep.engine_eligible_on}" if orep.engine_eligible_on else ""))
            for r in orep.engine_reasons:
                st.write("• " + r)
        st.caption(f"model calls {orep.usage.calls} (+{orep.usage.cached} cached) · tokens {orep.usage.input_tokens} in / {orep.usage.output_tokens} out")
        st.download_button("Download this replay (.json)", json.dumps(orep.to_dict(), ensure_ascii=False, indent=1), file_name="kaagaz_order_replay.json")

with tab_how:
    st.markdown("""
#### What happens to a page

1. **Read 1.** Muse Spark reads the whole table into a strict JSON schema: identifier, charge sections (act, section, text as printed), custody date (converted and as printed), previous conviction, other cases, legibility, notes. The schema has no field for a name.
2. **Read 2.** The same page is read again with a different instruction, one row at a time, only the two columns that decide eligibility. A row is *agreed* when both reads give the same sections and the same date; otherwise it is *disputed* and both readings are shown.
3. **Checks.** Every section is looked up in the Rihai law table (800 rows, each with its India Code source). Unknown sections, bare sections without their sub-section, implausible dates, illegible rows, name-like identifiers and disputed rows are held back for a human.
4. **Assessment.** Accepted rows go to the Section 479 engine: controlling section, one-third or one-half, eligible date, exclusions, the maximum-term cap. Held-back rows are assessed too, but marked.
5. **Correction.** A person corrects any cell against the page, ticks *confirmed*, and the row is re-checked and re-assessed without another model call.
6. **Output.** A results sheet, a UTRC memo for every eligible row, and the raw reads, for audit.

**Court order replay** does the same for a published bail order: the order's facts are read, the engine runs as of the order date, and the court's decision is compared with the engine's. Every replay is a test of the law table.

Every live model call is recorded under `kaagaz_cache/` (request text, image hashes, the answer, token counts; never the key), so any run can be replayed and audited.
""")
