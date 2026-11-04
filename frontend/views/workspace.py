from datetime import date
from html import escape

import pandas as pd
import streamlit as st

import api_client as api
import ui

STATUS_ICON = {"proposed": "🟡 Proposed", "approved": "🟢 Approved", "rejected": "🔴 Rejected"}


def render(meeting_id: str):
    token = st.session_state.token
    try:
        with st.spinner("Loading meeting…"):
            meeting = api.get_meeting(token, meeting_id)
            segments = api.get_transcript(token, meeting_id)
            minutes = api.get_minutes(token, meeting_id)
    except api.ApiError as exc:
        ui.handle_error(exc)
        if st.button("← Back to meetings"):
            ui.goto("dashboard")
        return

    if st.button("← Back to meetings"):
        ui.goto("dashboard")
    st.header(meeting["title"])
    verified = bool(minutes and minutes["status"] == "verified")
    st.caption(f"📍 {meeting['village_name']}, {meeting['district']}  ·  📅 {meeting['meeting_date']}  ·  "
               + ("✅ Minutes verified" if verified else "📝 Minutes draft" if minutes else "No minutes yet"))

    by_id = {s["id"]: s for s in segments}
    t_overview, t_transcript, t_minutes, t_verify = st.tabs(["Overview", "Transcript", "Minutes", "Verification"])
    with t_overview:
        _overview(meeting, len(segments), minutes)
    with t_transcript:
        _transcript(meeting, segments)
    with t_minutes:
        _minutes(meeting, minutes, by_id, segments)
    with t_verify:
        _verification(meeting, minutes)


# --- overview ---------------------------------------------------------
def _overview(meeting, n_segments, minutes):
    c1, c2, c3 = st.columns(3)
    c1.metric("Transcript segments", n_segments)
    c2.metric("Primary language", ui.LANGUAGES[meeting["primary_language"]])
    c3.metric("Minutes", minutes["status"].title() if minutes else "None")
    st.write(f"**Location:** {meeting['village_name']}, {meeting['district']}, {meeting['state']}")
    st.write("**Languages:** " + ", ".join(ui.LANGUAGES[c] for c in meeting["supported_languages"]))
    if meeting.get("description"):
        st.write(meeting["description"])
    st.info("🎙️ Upload a meeting recording in the Transcript tab, or add segments manually.")

    with st.expander("Danger zone"):
        confirm = st.checkbox("I understand this permanently deletes the meeting, transcript and minutes.")
        if st.button("Delete meeting", disabled=not confirm):
            try:
                api.delete_meeting(st.session_state.token, meeting["id"])
            except api.ApiError as exc:
                ui.handle_error(exc)
                return
            ui.flash("Meeting deleted.")
            ui.goto("dashboard")


# --- transcript -------------------------------------------------------
AUDIO_LANGS = {
    "English + Telugu": "en-IN,te-IN",
    "English + Kannada": "en-IN,kn-IN",
    "English + Hindi": "en-IN,hi-IN",
    "English + Telugu + Kannada + Hindi": "en-IN,te-IN,kn-IN,hi-IN",
}


def _audio(meeting):
    with st.expander("🎙️ Upload meeting audio (M4A, max 10 MB)"):
        choice = st.selectbox("Languages in the recording", list(AUDIO_LANGS))
        audio = st.file_uploader("M4A recording", type=["m4a"])
        if st.button("Queue transcription", disabled=audio is None):
            data = audio.getvalue()
            if len(data) > 10 * 1024 * 1024:
                st.error("File is larger than 10 MB.")
            else:
                try:
                    with st.spinner("Uploading…"):
                        job = api.submit_transcription(st.session_state.token, meeting["id"], audio.name,
                                                       data, AUDIO_LANGS[choice])
                except api.ApiError as exc:
                    ui.handle_error(exc)
                else:
                    st.success(f"Queued (status: {job['status']}). Click Refresh to follow progress.")
        try:
            jobs = api.list_transcriptions(st.session_state.token, meeting["id"])
        except api.ApiError as exc:
            ui.handle_error(exc)
            return
        if jobs:
            c1, c2 = st.columns([4, 1])
            c1.markdown("**Transcription jobs**")
            c2.button("🔄 Refresh")
            for j in jobs:
                line = f"{j['created_at'][:19]} · {', '.join(j['language_codes'])} · **{j['status']}** · {j['progress']}%"
                if j["error_code"]:
                    line += f" · error: `{j['error_code']}`"
                st.markdown(line)
                for w in j["warnings"]:
                    st.caption(f"⚠️ {w}")
            st.caption("The worker process must be running on the backend for jobs to progress. "
                       "When a job is completed, refresh to see its segments below.")


def _transcript(meeting, segments):
    _audio(meeting)
    if not segments:
        st.info("No transcript yet. Add segments below.")
    for s in segments:
        st.markdown(
            f'<div class="gs-seg"><div class="gs-meta">#{s["id"]} · {ui.fmt_time(s["start_time"])}–'
            f'{ui.fmt_time(s["end_time"])} · {escape(s["speaker_id"])} · {escape(ui.lang_label(s["language"]))}'
            f'</div><div class="gs-text">{escape(s["text"])}</div></div>',
            unsafe_allow_html=True)

    with st.expander("➕ Add transcript segment (manual)"):
        last_end = segments[-1]["end_time"] if segments else 0.0
        with st.form("add_segment", clear_on_submit=True):
            c1, c2 = st.columns(2)
            speaker = c1.text_input("Speaker", value="speaker_1")
            lang = c2.selectbox("Language", list(ui.SEGMENT_LANGUAGES), format_func=ui.lang_label,
                                index=list(ui.SEGMENT_LANGUAGES).index(meeting["primary_language"]))
            text = st.text_area("Text")
            c3, c4 = st.columns(2)
            start = c3.number_input("Start (seconds)", min_value=0.0, value=float(last_end), step=1.0)
            end = c4.number_input("End (seconds)", min_value=0.0, value=float(last_end) + 5.0, step=1.0)
            submitted = st.form_submit_button("Add segment")
        if submitted:
            if not text.strip() or not speaker.strip():
                st.error("Speaker and text are required.")
            elif end <= start:
                st.error("End time must be greater than start time.")
            else:
                try:
                    api.add_transcript(st.session_state.token, meeting["id"], [
                        {"speaker_id": speaker.strip(), "language": lang, "text": text,
                         "start_time": start, "end_time": end}])
                except api.ApiError as exc:
                    ui.handle_error(exc)
                else:
                    ui.flash("Segment added.")
                    st.rerun()


# --- minutes ----------------------------------------------------------
def _evidence(ids, by_id):
    with st.expander(f"Evidence: segment {', '.join('#' + str(i) for i in ids)}"):
        for i in ids:
            s = by_id.get(i)
            if s:
                st.markdown(f"**#{i}** · {ui.fmt_time(s['start_time'])} · {s['speaker_id']} · "
                            f"{ui.lang_label(s['language'])}")
                st.text(s["text"])
            else:
                st.warning(f"Segment #{i} was not found in the transcript.")


def _minutes(meeting, minutes, by_id, segments):
    if minutes:
        if minutes.get("review_flags"):
            st.warning(f"⚠️ {len(minutes['review_flags'])} AI-generated item(s) need human review before verification.")
        st.subheader("Summary")
        st.write(minutes["summary"])

        st.subheader("Decisions")
        if not minutes["decisions"]:
            st.caption("No decisions recorded.")
        for status in ("approved", "proposed", "rejected"):
            for d in (d for d in minutes["decisions"] if d["status"] == status):
                with st.container(border=True):
                    st.markdown(f"**{STATUS_ICON[status]}** — {d['description']}")
                    _evidence(d["evidence_segment_ids"], by_id)

        st.subheader("Action items")
        if not minutes["action_items"]:
            st.caption("No action items recorded.")
        for a in minutes["action_items"]:
            with st.container(border=True):
                st.markdown(f"**{a['task']}**")
                st.caption(f"👤 {a['assigned_to']}  ·  ⏰ {a['deadline'] or 'No deadline'}")
                _evidence(a["evidence_segment_ids"], by_id)

        st.subheader("Unresolved issues")
        if not minutes["unresolved_issues"]:
            st.caption("No unresolved issues.")
        for u in minutes["unresolved_issues"]:
            with st.container(border=True):
                st.markdown(f"❓ {u['description']}")
                _evidence(u["evidence_segment_ids"], by_id)
    else:
        st.info("No minutes yet. Generate an AI draft or write draft minutes manually below.")
        if segments and st.button("✨ Generate draft minutes (AI)"):
            try:
                with st.spinner("Generating…"):
                    api.generate_minutes(st.session_state.token, meeting["id"])
            except api.ApiError as exc:
                if exc.status == 501:
                    st.warning("AI minutes generation is not available yet. Please write minutes manually below.")
                else:
                    ui.handle_error(exc)
            else:
                ui.flash("Draft minutes generated. Please review every item.")
                st.rerun()

    if minutes and minutes["status"] == "verified":
        st.success("Verified minutes can no longer be edited.")
        return
    if not segments:
        st.caption("Add transcript segments first — every decision and action must cite transcript evidence.")
        return
    _minutes_editor(meeting, minutes)


def _parse_ids(raw, valid):
    try:
        ids = [int(p) for p in str(raw or "").replace(";", ",").split(",") if p.strip()]
    except ValueError:
        return None, "Evidence must be comma-separated segment numbers, e.g. 4, 6."
    if not ids:
        return None, "Every row needs at least one evidence segment."
    bad = [i for i in ids if i not in valid]
    if bad:
        return None, f"Unknown segment(s): {', '.join(map(str, bad))}."
    return ids, None


def _rows(items, cols, date_cols=()):
    """Editor table with explicit dtypes, so empty tables are still editable as text/date columns."""
    df = pd.DataFrame(items, columns=cols) if items else pd.DataFrame({c: pd.Series([], dtype="object") for c in cols})
    for c in cols:
        df[c] = pd.to_datetime(df[c]) if c in date_cols else df[c].astype("object")
    return df


def _minutes_editor(meeting, minutes):
    token = st.session_state.token
    valid = {s["id"] for s in api.get_transcript(token, meeting["id"])}
    with st.expander("✏️ Edit draft minutes (manual)", expanded=not minutes):
        st.caption("Evidence = transcript segment numbers (the #id shown in the Transcript tab), comma-separated.")
        summary = st.text_area("Summary", value=minutes["summary"] if minutes else "", key="m_summary")

        dec = [{"description": d["description"], "status": d["status"],
                "evidence": ", ".join(map(str, d["evidence_segment_ids"]))} for d in (minutes or {}).get("decisions", [])]
        act = [{"task": a["task"], "assigned_to": a["assigned_to"],
                "deadline": date.fromisoformat(a["deadline"]) if a["deadline"] else None,
                "evidence": ", ".join(map(str, a["evidence_segment_ids"]))} for a in (minutes or {}).get("action_items", [])]
        iss = [{"description": u["description"], "evidence": ", ".join(map(str, u["evidence_segment_ids"]))}
               for u in (minutes or {}).get("unresolved_issues", [])]

        st.markdown("**Decisions**")
        dec_df = st.data_editor(_rows(dec, ["description", "status", "evidence"]), num_rows="dynamic",
                                width="stretch", key="m_dec", column_config={
                                    "status": st.column_config.SelectboxColumn(
                                        options=["proposed", "approved", "rejected"], required=True)})
        st.markdown("**Action items**")
        act_df = st.data_editor(_rows(act, ["task", "assigned_to", "deadline", "evidence"], date_cols=("deadline",)), num_rows="dynamic",
                                width="stretch", key="m_act", column_config={
                                    "deadline": st.column_config.DateColumn()})
        st.markdown("**Unresolved issues**")
        iss_df = st.data_editor(_rows(iss, ["description", "evidence"]), num_rows="dynamic",
                                width="stretch", key="m_iss")

        if st.button("Save draft minutes", type="primary"):
            payload, error = _build_payload(summary, dec_df, act_df, iss_df, valid)
            if error:
                st.error(error)
                return
            try:
                api.save_minutes(token, meeting["id"], payload)
            except api.ApiError as exc:
                ui.handle_error(exc)
                return
            ui.flash("Draft minutes saved.")
            st.rerun()


def _build_payload(summary, dec_df, act_df, iss_df, valid):
    if not summary.strip():
        return None, "Summary is required."
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
            return None, "Each action item needs a task and an assignee."
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


# --- verification -----------------------------------------------------
def _verification(meeting, minutes):
    st.warning("**Prototype confirmation only.** Verifying here records that you reviewed and confirm these "
               "minutes within this application. It is **not** official or legally authenticated "
               "government approval.")
    if not minutes:
        st.info("Save draft minutes before verifying.")
        return
    if minutes["status"] == "verified":
        st.success(f"✅ Verified by **{minutes['verifier_name']}** on {minutes['verified_at']}")
        return
    st.write("Review the Minutes tab carefully. Once verified, minutes cannot be edited.")
    with st.form("verify"):
        name = st.text_input("Your full name")
        confirmed = st.checkbox("I have reviewed these minutes and confirm they are accurate.")
        submitted = st.form_submit_button("Verify minutes", type="primary")
    if submitted:
        if not name.strip() or not confirmed:
            st.error("Enter your name and tick the confirmation box.")
            return
        try:
            result = api.verify_minutes(st.session_state.token, meeting["id"], name.strip())
        except api.ApiError as exc:
            ui.handle_error(exc)
            return
        if result and result.get("status") == "verified":
            ui.flash("Minutes verified.")
            st.rerun()
