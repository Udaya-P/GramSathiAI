import streamlit as st

import api_client as api
import components as c
import ui

MAX_BYTES = 10 * 1024 * 1024
AUDIO_LANGS = {
    "English and Telugu": "en-IN,te-IN",
    "English and Kannada": "en-IN,kn-IN",
    "English and Hindi": "en-IN,hi-IN",
    "English, Telugu, Kannada and Hindi": "en-IN,te-IN,kn-IN,hi-IN",
}
CODE_NAMES = {"en-IN": "English", "te-IN": "Telugu", "kn-IN": "Kannada", "hi-IN": "Hindi"}
JOB_STATUS = {  # backend status -> (label, tone)
    "queued": ("Waiting in queue", "neutral"),
    "submitting": ("Sending to the speech service", "blue"),
    "needs_reconciliation": ("Needs attention", "amber"),
    "completed": ("Completed", "green"),
    "failed": ("Failed", "red"),
}


def render():
    c.page_header("Audio & Transcripts", "Add a meeting recording, then review what was said.", eyebrow="Meeting workflow")
    ctx = c.meeting_context()
    if not ctx:
        return
    meeting = ctx["meeting"]
    _upload(ctx, meeting)
    st.divider()
    _transcript(ctx, meeting)


def _upload(ctx, meeting):
    token = ctx["token"]
    with st.container(border=True):
        c.step_heading(1, "Meeting selected", done=True)
        st.caption(f"{meeting['title']} · {meeting['village_name']} · {ui.fmt_date(meeting['meeting_date'])}")
        st.write("")

        c.step_heading(2, "Add the recording")
        audio = st.file_uploader("Meeting recording", type=["m4a"], label_visibility="collapsed",
                                 help="M4A audio, up to 10 MB.")
        st.caption("Recording directly in the browser is not supported yet. Upload an M4A audio file (up to 10 MB).")
        choice = st.selectbox("Languages spoken in this recording", list(AUDIO_LANGS))
        st.write("")

        c.step_heading(3, "Check the file", done=audio is not None)
        if audio is None:
            st.caption("No file chosen yet.")
        else:
            size = audio.size
            st.markdown(f"**{audio.name}** · {ui.fmt_size(size)}")
            if size > MAX_BYTES:
                st.error("This file is larger than 10 MB. Choose a shorter recording.")
        ready = audio is not None and audio.size <= MAX_BYTES
        if st.button("Start transcription", type="primary", disabled=not ready, icon=":material/upload:"):
            bar = st.progress(10, text="Uploading the recording…")
            try:
                job = api.submit_transcription(token, meeting["id"], audio.name, audio.getvalue(), AUDIO_LANGS[choice])
                bar.progress(100, text="Upload complete.")
            except api.ApiError as exc:
                bar.empty()
                ui.handle_error(exc)
            else:
                ui.invalidate()
                label = JOB_STATUS.get(job["status"], (job["status"].replace("_", " ").title(), ""))[0]
                st.success(f"Recording received. Status: {label}.")
        st.write("")

        c.step_heading(4, "What happens next")
        st.markdown(
            "1. Your recording waits in a queue.\n"
            "2. A background service converts the speech to text, keeping each speaker's turn and language.\n"
            "3. When it is complete, the transcript appears below. Then you can write the minutes.")
        st.write("")

        c.step_heading(5, "Transcription status")
        _jobs(token, meeting["id"])


def _jobs(token, meeting_id):
    try:
        jobs = api.list_transcriptions(token, meeting_id)
    except api.ApiError as exc:
        ui.handle_error(exc)
        return
    top = st.columns([3, 1.4])
    if not jobs:
        top[0].caption("No recordings have been submitted for this meeting.")
    top[1].button("Refresh", icon=":material/refresh:", width="stretch")
    for j in jobs:
        label, tone = JOB_STATUS.get(j["status"], (j["status"].replace("_", " ").title(), "neutral"))
        with st.container(border=True):
            a, b = st.columns([3, 1.4], vertical_alignment="center")
            names = ", ".join(CODE_NAMES.get(code, code) for code in j["language_codes"])
            a.markdown(f"**Recording** · {names}  \n{ui.fmt_datetime(j['created_at'])}")
            b.markdown(c.chip(label, tone), unsafe_allow_html=True)
            if j["status"] not in ("completed", "failed"):
                st.progress(max(0, min(100, j["progress"])) / 100, text=f"{j['progress']}%")
            if j["error_code"]:
                st.error(f"This job could not finish (code: {j['error_code']}). Ask your administrator to check it.")
            for w in j["warnings"]:
                st.caption(f"Note: {w}")


def _transcript(ctx, meeting):
    segments = ctx["segments"]
    st.markdown("### Transcript")
    if not segments:
        c.empty_state("No transcript yet", "Upload a recording above, or add segments by hand below.")
    else:
        f1, f2 = st.columns([3, 2])
        query = f1.text_input("Search the transcript", placeholder="Search words…", label_visibility="collapsed")
        langs = sorted({s["language"] for s in segments})
        picked = f2.multiselect("Language", langs, default=[], format_func=ui.lang_label,
                                placeholder="All languages", label_visibility="collapsed")
        shown = [s for s in segments if (not query or query.lower() in s["text"].lower())
                 and (not picked or s["language"] in picked)]
        st.caption(f"Showing {len(shown)} of {len(segments)} segments · times are minutes:seconds")
        for s in shown:
            c.segment_card(s)
        if not shown:
            st.info("No segments match your search.")
        st.caption("Segment numbers (like #8) are used as evidence in the minutes. "
                   "Editing existing segments is not available yet.")

    with st.expander("Add a segment by hand"):
        last_end = segments[-1]["end_time"] if segments else 0.0
        with st.form("add_segment", clear_on_submit=True):
            a, b = st.columns(2)
            speaker = a.text_input("Speaker", value="Speaker 1")
            lang = b.selectbox("Language", list(ui.SEGMENT_LANGUAGES), format_func=ui.lang_label,
                               index=list(ui.SEGMENT_LANGUAGES).index(meeting["primary_language"]))
            text = st.text_area("What was said")
            d, e = st.columns(2)
            start = d.number_input("Starts at (seconds)", min_value=0.0, value=float(last_end), step=1.0)
            end = e.number_input("Ends at (seconds)", min_value=0.0, value=float(last_end) + 5.0, step=1.0)
            submitted = st.form_submit_button("Add segment")
        if submitted:
            if not text.strip() or not speaker.strip():
                st.error("Enter the speaker and what was said.")
            elif end <= start:
                st.error("The end time must be after the start time.")
            else:
                try:
                    api.add_transcript(ctx["token"], meeting["id"], [
                        {"speaker_id": speaker.strip(), "language": lang, "text": text,
                         "start_time": start, "end_time": end}])
                except api.ApiError as exc:
                    ui.handle_error(exc)
                else:
                    ui.invalidate()
                    ui.flash("Segment added.")
                    st.rerun()
