import json

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
            st.session_state.minutes_edit_revision = minutes.get("revision") if minutes else None
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
        c.empty_state("No minutes yet", "Write the minutes yourself or generate an evidence-linked draft with Groq.")
        return

    if status == "verified":
        c.callout(f"Verified by {minutes['verifier_name']} on {ui.fmt_datetime(minutes['verified_at'])}.", "ok",
                  "These minutes are verified and can no longer be edited")

    c.minutes_document(minutes, ctx["by_id"], playback=ctx)
    c.voice_player(minutes)
    if status == "draft":
        st.divider()
        if st.button("Continue to Verification", type="primary", icon=":material/arrow_forward:"):
            ui.go("verification")


def _generate(ctx):
    try:
        with st.spinner("Drafting minutes with Groq…"):
            api.generate_minutes(ctx["token"], ctx["meeting"]["id"])
    except api.ApiError as exc:
        ui.handle_error(exc)
    else:
        ui.invalidate()
        ui.flash("Draft minutes created. Please review every item.")
        st.rerun()


# --- editing ---------------------------------------------------------------
def _text(value):
    return "" if pd.isna(value) else str(value)


def _format_ids(ids):
    return ", ".join(map(str, ids))


def _parse_ids(raw, valid, *, required=True):
    try:
        ids = [int(part) for part in _text(raw).replace(";", ",").split(",") if part.strip()]
    except ValueError:
        raise ValueError("Enter evidence segment numbers separated by commas.") from None
    if required and not ids:
        raise ValueError("Each row needs at least one evidence segment number.")
    if set(ids) - valid:
        raise ValueError("Evidence must refer to segments in this meeting.")
    return ids


def _json_list(raw, label):
    try:
        value = json.loads(_text(raw).strip() or "[]")
    except ValueError:
        raise ValueError(f"{label} must contain a valid JSON array.") from None
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError(f"{label} must be a JSON array of objects.")
    return value


def _edit_table(items, columns, config, key, *, dates=()):
    rows = [{**item, "evidence_segment_ids": _format_ids(item["evidence_segment_ids"]),
             "evidence_quotes": json.dumps(item.get("evidence_quotes", []), ensure_ascii=False)} for item in items]
    data = pd.DataFrame(rows, columns=columns, dtype=object)
    for field in dates:
        data[field] = pd.to_datetime(data[field])
    return st.data_editor(
        data, num_rows="dynamic", width="stretch", hide_index=True, key=key,
        column_config={**config, "evidence_segment_ids": st.column_config.TextColumn("Evidence segment IDs"),
                       "evidence_quotes": st.column_config.TextColumn("Evidence quotes (JSON)")},
    )


def _editor(ctx):
    token, meeting, minutes = ctx["token"], ctx["meeting"], ctx["minutes"]
    revision = minutes.get("revision") if minutes else None
    if revision != st.session_state.get("minutes_edit_revision"):
        st.warning("The draft changed while you were editing. Reopen it to load the latest revision.")
        if st.button("Return to minutes"):
            st.session_state.edit_minutes = False
            st.rerun()
        return
    draft = minutes or {}
    key = f"{meeting['id']}_{revision}"
    valid = set(ctx["by_id"])
    st.markdown("### Edit minutes")
    st.caption("Use transcript segment numbers for evidence. Separate multiple IDs with commas. Add rows with the + at the bottom of each table.")
    summary = st.text_area("Meeting summary", value=draft.get("summary", ""), height=120, key=f"summary_{key}")
    summary_ids = st.text_input("Summary evidence segment IDs", value=_format_ids(draft.get("summary_evidence_segment_ids", [])),
                                key=f"summary_ids_{key}")
    with st.expander("Summary claims and quotes"):
        summary_claims = st.text_area("Summary claims (JSON)", value=json.dumps(draft.get("summary_claims", []), ensure_ascii=False, indent=2),
                                      key=f"summary_claims_{key}")

    st.markdown("**Decisions**")
    decisions = [{**item, "status": item.get("classification") or item["status"]} for item in draft.get("decisions", [])]
    decision_rows = _edit_table(decisions,
        ["description", "status", "estimated_amount", "proposed_amount", "approved_amount", "currency", "evidence_segment_ids", "evidence_quotes"],
        {"description": st.column_config.TextColumn("Decision", width="medium"),
         "status": st.column_config.SelectboxColumn("Status", options=list(c.DECISION), required=True, default="proposed"),
         "estimated_amount": st.column_config.TextColumn("Estimated amount"),
         "proposed_amount": st.column_config.TextColumn("Proposed amount"),
         "approved_amount": st.column_config.TextColumn("Approved amount"),
         "currency": st.column_config.SelectboxColumn("Currency", options=["INR", "USD", "EUR"])}, f"decisions_{key}")
    st.markdown("**Action items**")
    action_rows = _edit_table(draft.get("action_items", []),
        ["task", "assigned_to", "deadline", "deadline_text", "evidence_segment_ids", "evidence_quotes"],
        {"task": st.column_config.TextColumn("Task", width="medium"),
         "assigned_to": st.column_config.TextColumn("Responsible person"),
         "deadline": st.column_config.DateColumn("Calendar deadline"),
         "deadline_text": st.column_config.TextColumn("Relative deadline")}, f"actions_{key}", dates=("deadline",))
    st.markdown("**Unresolved issues**")
    issue_rows = _edit_table(draft.get("unresolved_issues", []), ["description", "evidence_segment_ids", "evidence_quotes"],
                            {"description": st.column_config.TextColumn("Issue", width="medium")}, f"issues_{key}")

    save, cancel, _ = st.columns([1.4, 1, 2.6])
    if cancel.button("Cancel", width="stretch"):
        st.session_state.edit_minutes = False
        st.rerun()
    if save.button("Save minutes", type="primary", width="stretch", icon=":material/save:"):
        try:
            payload = _build_payload(summary, summary_ids, summary_claims, decision_rows, action_rows, issue_rows, valid, revision)
            api.save_minutes(token, meeting["id"], payload)
        except ValueError as exc:
            st.error(str(exc))
            return
        except api.ApiError as exc:
            ui.handle_error(exc)
            return
        ui.invalidate()
        st.session_state.edit_minutes = False
        ui.flash("Minutes saved as a draft.")
        st.rerun()


def _build_payload(summary, summary_ids, summary_claims, decisions, actions, issues, valid, revision):
    if not summary.strip():
        raise ValueError("Write a summary first.")
    payload = {"summary": summary, "summary_evidence_segment_ids": _parse_ids(summary_ids, valid, required=False),
               "summary_claims": _json_list(summary_claims, "Summary claims"), "expected_revision": revision}
    for key, table, title_field in (("decisions", decisions, "description"), ("action_items", actions, "task"),
                                    ("unresolved_issues", issues, "description")):
        payload[key] = []
        for _, row in table.iterrows():
            if not _text(row[title_field]).strip():
                raise ValueError("Every decision, action item, and issue needs a description.")
            item = {field: _text(value) or None for field, value in row.items()}
            item["evidence_segment_ids"] = _parse_ids(row["evidence_segment_ids"], valid)
            item["evidence_quotes"] = _json_list(row["evidence_quotes"], "Evidence quotes")
            if key == "action_items":
                item["deadline"] = None if pd.isna(row["deadline"]) else pd.Timestamp(row["deadline"]).date().isoformat()
            payload[key].append(item)
    return payload
