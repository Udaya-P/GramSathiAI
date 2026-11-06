from datetime import date

import pandas as pd
import streamlit as st

import api_client as api
import components as c
import ui


def render():
    c.page_header("Meeting Minutes", "Read, edit and prepare the minutes for verification.", eyebrow="Meeting workflow")
    ctx = c.meeting_context()
    if not ctx:
        return
    minutes, status = ctx["minutes"], ctx["status"]

    if st.session_state.edit_minutes and status != "verified":
        _editor(ctx)
        return

    bar = st.columns([2, 1.3, 1.3], vertical_alignment="center")
    bar[0].markdown(c.status_chip(status), unsafe_allow_html=True)
    if status != "verified":
        if bar[1].button("Edit minutes" if minutes else "Write minutes", width="stretch", icon=":material/edit:",
                         disabled=not ctx["segments"]):
            st.session_state.edit_minutes = True
            st.rerun()
        if not minutes and bar[2].button("Draft with AI", width="stretch", icon=":material/auto_awesome:",
                                         disabled=not ctx["segments"]):
            _generate(ctx)
    if not ctx["segments"]:
        c.callout("Minutes need a transcript, because every decision must point to what was said. "
                  "Add a recording or transcript first.", "info", "Transcript needed")
        if st.button("Go to Audio & Transcripts", icon=":material/graphic_eq:"):
            ui.go("audio")
        return

    if not minutes:
        c.empty_state("No minutes yet", "Write the minutes yourself, or draft them with AI when that is available.")
        return

    if minutes.get("review_flags"):
        c.callout(f"{len(minutes['review_flags'])} item(s) were drafted by AI. Check each one against the "
                  "transcript before verifying.", "warn", "Review needed")
    if status == "verified":
        c.callout(f"Verified by {minutes['verifier_name']} on {ui.fmt_datetime(minutes['verified_at'])}.", "ok",
                  "These minutes are verified and can no longer be edited")

    c.minutes_document(minutes, ctx["by_id"])
    c.voice_player(minutes)
    if status == "draft":
        st.divider()
        if st.button("Continue to Verification", type="primary", icon=":material/arrow_forward:"):
            ui.go("verification")


def _generate(ctx):
    try:
        with st.spinner("Drafting minutes…"):
            api.generate_minutes(ctx["token"], ctx["meeting"]["id"])
    except api.ApiError as exc:
        if exc.status == 501:
            st.warning("Drafting with AI is not available yet. Please write the minutes yourself.")
        else:
            ui.handle_error(exc)
    else:
        ui.invalidate()
        ui.flash("Draft minutes created. Please review every item.")
        st.rerun()


# --- editing ---------------------------------------------------------------
def _parse_ids(raw, valid):
    try:
        ids = [int(p) for p in str(raw or "").replace(";", ",").split(",") if p.strip()]
    except ValueError:
        return None, "Evidence must be segment numbers separated by commas, such as 4, 6."
    if not ids:
        return None, "Each row needs at least one evidence segment number."
    bad = [i for i in ids if i not in valid]
    if bad:
        return None, f"These segment numbers are not in the transcript: {', '.join(map(str, bad))}."
    return ids, None


def _rows(items, cols, date_cols=()):
    """Editor table with explicit dtypes, so empty tables are still editable as text/date columns."""
    df = pd.DataFrame(items, columns=cols) if items else pd.DataFrame({k: pd.Series([], dtype="object") for k in cols})
    for k in cols:
        df[k] = pd.to_datetime(df[k]) if k in date_cols else df[k].astype("object")
    return df


def _editor(ctx):
    token, meeting, minutes = ctx["token"], ctx["meeting"], ctx["minutes"]
    valid = set(ctx["by_id"])
    st.markdown("### Edit minutes")
    c.callout("Evidence is the transcript segment number (like 8 or 10) shown on the Audio & Transcripts page. "
              "Use commas for several, such as 8, 10. Add a row with the + at the bottom of each table.",
              "info", "How to fill this in")
    summary = st.text_area("Meeting summary", value=minutes["summary"] if minutes else "", height=120,
                           placeholder="A short summary of what was discussed.")

    dec = [{"description": d["description"], "status": d["status"],
            "evidence": ", ".join(map(str, d["evidence_segment_ids"]))} for d in (minutes or {}).get("decisions", [])]
    act = [{"task": a["task"], "assigned_to": a["assigned_to"],
            "deadline": date.fromisoformat(a["deadline"]) if a["deadline"] else None,
            "evidence": ", ".join(map(str, a["evidence_segment_ids"]))} for a in (minutes or {}).get("action_items", [])]
    iss = [{"description": u["description"], "evidence": ", ".join(map(str, u["evidence_segment_ids"]))}
           for u in (minutes or {}).get("unresolved_issues", [])]

    st.markdown("**Decisions**")
    st.caption("A Suggestion was only proposed. Choose Approved resolution only if the meeting agreed.")
    dec_df = st.data_editor(_rows(dec, ["description", "status", "evidence"]), num_rows="dynamic", width="stretch",
                            key="m_dec", column_config={
                                "description": st.column_config.TextColumn("Decision", width="medium"),
                                "status": st.column_config.SelectboxColumn(
                                    "Status", options=["proposed", "approved", "rejected"], required=True,
                                    help="proposed = suggestion, approved = agreed, rejected = turned down"),
                                "evidence": st.column_config.TextColumn("Evidence segments")})
    st.markdown("**Action items**")
    act_df = st.data_editor(_rows(act, ["task", "assigned_to", "deadline", "evidence"], date_cols=("deadline",)),
                            num_rows="dynamic", width="stretch", key="m_act", column_config={
                                "task": st.column_config.TextColumn("Task", width="medium"),
                                "assigned_to": st.column_config.TextColumn("Responsible person"),
                                "deadline": st.column_config.DateColumn("Deadline"),
                                "evidence": st.column_config.TextColumn("Evidence segments")})
    st.markdown("**Unresolved issues**")
    iss_df = st.data_editor(_rows(iss, ["description", "evidence"]), num_rows="dynamic", width="stretch",
                            key="m_iss", column_config={
                                "description": st.column_config.TextColumn("Issue", width="medium"),
                                "evidence": st.column_config.TextColumn("Evidence segments")})

    save, cancel, _ = st.columns([1.4, 1, 2.6])
    if cancel.button("Cancel", width="stretch"):
        st.session_state.edit_minutes = False
        st.rerun()
    if save.button("Save minutes", type="primary", width="stretch", icon=":material/save:"):
        payload, error = _build_payload(summary, dec_df, act_df, iss_df, valid)
        if error:
            st.error(error)
            return
        try:
            api.save_minutes(token, meeting["id"], payload)
        except api.ApiError as exc:
            ui.handle_error(exc)
            return
        ui.invalidate()
        st.session_state.edit_minutes = False
        ui.flash("Minutes saved as a draft.")
        st.rerun()


def _build_payload(summary, dec_df, act_df, iss_df, valid):
    if not summary.strip():
        return None, "Write a summary first."
    payload = {"summary": summary, "decisions": [], "action_items": [], "unresolved_issues": []}
    for _, r in dec_df.iterrows():
        if not str(r["description"] or "").strip():
            return None, "Each decision needs a description."
        ids, err = _parse_ids(r["evidence"], valid)
        if err:
            return None, f"Decision: {err}"
        payload["decisions"].append({"description": r["description"], "status": r["status"],
                                     "evidence_segment_ids": ids})
    for _, r in act_df.iterrows():
        if not str(r["task"] or "").strip() or not str(r["assigned_to"] or "").strip():
            return None, "Each action item needs a task and a responsible person."
        ids, err = _parse_ids(r["evidence"], valid)
        if err:
            return None, f"Action item: {err}"
        deadline = r["deadline"]
        payload["action_items"].append({
            "task": r["task"], "assigned_to": r["assigned_to"],
            "deadline": None if pd.isna(deadline) else pd.Timestamp(deadline).date().isoformat(),
            "evidence_segment_ids": ids})
    for _, r in iss_df.iterrows():
        if not str(r["description"] or "").strip():
            return None, "Each unresolved issue needs a description."
        ids, err = _parse_ids(r["evidence"], valid)
        if err:
            return None, f"Issue: {err}"
        payload["unresolved_issues"].append({"description": r["description"], "evidence_segment_ids": ids})
    return payload, None
