"""Reusable UI building blocks shared by every page."""
from __future__ import annotations

from html import escape

import streamlit as st

import api_client as api
import ui

STATUS = {  # minutes status -> (label, chip tone)
    "none": ("No minutes yet", "neutral"),
    "draft": ("Draft, needs review", "amber"),
    "verified": ("Verified", "green"),
    "unknown": ("Status unavailable", "neutral"),
}
DECISION = {  # decision status -> (label, hint, chip tone)
    "approved": ("Approved resolution", "Agreed by the meeting", "green"),
    "proposed": ("Suggestion", "Proposed, not yet agreed", "amber"),
    "rejected": ("Rejected proposal", "Discussed and turned down", "red"),
}


def chip(text: str, tone: str = "neutral") -> str:
    return f'<span class="gs-chip {tone}">{escape(text)}</span>'


def status_chip(status: str) -> str:
    label, tone = STATUS.get(status, STATUS["unknown"])
    return chip(label, tone)


def page_header(title: str, subtitle: str | None = None, eyebrow: str | None = None):
    html = ""
    if eyebrow:
        html += f'<div class="gs-eyebrow">{escape(eyebrow)}</div>'
    html += f'<div class="gs-title">{escape(title)}</div>'
    if subtitle:
        html += f'<div class="gs-subtitle">{escape(subtitle)}</div>'
    st.markdown(html, unsafe_allow_html=True)


def stat_card(label: str, value, hint: str = "", tone: str = ""):
    st.markdown(
        f'<div class="gs-stat tone-{tone}"><div class="gs-stat-label">{escape(label)}</div>'
        f'<div class="gs-stat-value">{escape(str(value))}</div>'
        f'<div class="gs-stat-hint">{escape(hint)}</div></div>', unsafe_allow_html=True)


def callout(text: str, tone: str = "info", title: str | None = None):
    head = f"<b>{escape(title)}</b>" if title else ""
    st.markdown(f'<div class="gs-callout {tone}">{head}{escape(text)}</div>', unsafe_allow_html=True)


def empty_state(title: str, text: str):
    st.markdown(f'<div class="gs-empty"><h4>{escape(title)}</h4><p>{escape(text)}</p></div>', unsafe_allow_html=True)


def step_heading(number: int, title: str, done: bool = False):
    st.markdown(f'<div class="gs-step"><div class="gs-step-num{" done" if done else ""}">'
                f'{"✓" if done else number}</div><div class="gs-step-title">{escape(title)}</div></div>',
                unsafe_allow_html=True)


def flow(labels_done: list):
    """Small progress trail, e.g. [('Recording', True), ('Transcript', False)]."""
    st.markdown('<div class="gs-flow">' + "".join(
        f'<span class="{"done" if d else ""}">{"✓ " if d else ""}{escape(l)}</span>' for l, d in labels_done) + "</div>",
        unsafe_allow_html=True)


def segment_card(s: dict):
    st.markdown(
        f'<div class="gs-seg"><div class="gs-seg-meta"><span class="gs-seg-id">#{s["id"]}</span>'
        f'<span>{ui.fmt_time(s["start_time"])} – {ui.fmt_time(s["end_time"])}</span>'
        f'<span>{escape(ui.speaker_label(s["speaker_id"]))}</span>{chip(ui.lang_label(s["language"]), "blue")}</div>'
        f'<div class="gs-seg-text">{escape(s["text"])}</div></div>', unsafe_allow_html=True)


def evidence(ids: list, by_id: dict, expanded: bool = False):
    label = "Supporting transcript: " + ", ".join(f"#{i}" for i in ids)
    with st.expander(label, expanded=expanded):
        for i in ids:
            s = by_id.get(i)
            if s:
                segment_card(s)
            else:
                st.warning(f"Segment #{i} was not found in the transcript.")


def voice_player(minutes: dict | None):
    """Voice playback card. The backend has no text-to-speech endpoint yet, so the controls are disabled."""
    with st.container(border=True):
        st.markdown("**Listen to the minutes**")
        c1, c2 = st.columns([2, 1])
        c1.selectbox("Language", list(ui.LANGUAGES), format_func=ui.LANGUAGES.get, disabled=True,
                     key="voice_language", help="Playback language")
        c2.button("Play", disabled=True, width="stretch", key="voice_play", icon=":material/play_arrow:")
        st.progress(0, text="0:00 / --:--")
        callout("Voice playback is not available yet. It will appear here once the backend connects the "
                "text-to-speech service.", "info")


# --- meeting context shared by the meeting pages ---------------------------
def meeting_label(m: dict) -> str:
    return f"{m['title']}  ·  {m['village_name']}  ·  {ui.fmt_date(m['meeting_date'])}"


def meeting_context():
    """Meeting picker plus the data every meeting page needs. Returns None when it cannot continue."""
    token = st.session_state.token
    try:
        meetings = api.list_meetings(token)
    except api.ApiError as exc:
        ui.handle_error(exc)
        return None
    if not meetings:
        empty_state("No meetings yet", "Create a meeting first, then come back to add a recording and minutes.")
        if st.button("Create New Meeting", type="primary", icon=":material/add:"):
            ui.go("create")
        return None

    ids = [m["id"] for m in meetings]
    active = st.session_state.meeting_id if st.session_state.meeting_id in ids else ids[0]
    by_meeting = {m["id"]: m for m in meetings}
    chosen = st.selectbox("Meeting", ids, index=ids.index(active), format_func=lambda i: meeting_label(by_meeting[i]))
    if chosen != st.session_state.meeting_id:
        st.session_state.meeting_id = chosen
        st.session_state.edit_minutes = False

    try:
        with st.spinner("Loading meeting…"):
            meeting = api.get_meeting(token, chosen)
            segments = api.get_transcript(token, chosen)
            minutes = api.get_minutes(token, chosen)
    except api.ApiError as exc:
        ui.handle_error(exc)
        return None

    status = minutes["status"] if minutes else "none"
    flow([("Meeting created", True), ("Transcript added", bool(segments)),
          ("Minutes drafted", bool(minutes)), ("Minutes verified", status == "verified")])
    return {"token": token, "meeting": meeting, "segments": segments, "minutes": minutes,
            "by_id": {s["id"]: s for s in segments}, "status": status}


# --- minutes document (read-only) -------------------------------------------
def _item(tone: str, chip_html: str, title: str, meta: str = ""):
    st.markdown(f'<div class="gs-item {tone}">{chip_html}<div class="gs-item-title">{escape(title)}</div>'
                + (f'<div class="gs-item-meta">{meta}</div>' if meta else "") + "</div>", unsafe_allow_html=True)


def minutes_document(minutes: dict, by_id: dict, expand_evidence: bool = False):
    """Summary, decisions (suggestion vs approved vs rejected), actions and open issues."""
    st.markdown("### Meeting summary")
    with st.container(border=True):
        st.write(minutes["summary"])

    st.markdown("### Decisions")
    if not minutes["decisions"]:
        st.caption("No decisions were recorded.")
    for status in ("approved", "proposed", "rejected"):
        group = [d for d in minutes["decisions"] if d["status"] == status]
        if not group:
            continue
        label, hint, tone = DECISION[status]
        st.markdown(f"**{label}s** · {len(group)}" if status != "proposed" else f"**Suggestions** · {len(group)}")
        for d in group:
            _item(status, chip(label, tone) + f' <span class="gs-item-meta">{escape(hint)}</span>', d["description"])
            evidence(d["evidence_segment_ids"], by_id, expand_evidence)

    st.markdown("### Action items")
    if not minutes["action_items"]:
        st.caption("No action items were recorded.")
    for a in minutes["action_items"]:
        deadline = ui.fmt_date(a["deadline"]) if a["deadline"] else "No deadline set"
        _item("", chip("Action", "blue"), a["task"],
              f"Responsible: <b>{escape(a['assigned_to'])}</b> &nbsp;·&nbsp; Deadline: <b>{escape(deadline)}</b>")
        evidence(a["evidence_segment_ids"], by_id, expand_evidence)

    st.markdown("### Unresolved issues")
    if not minutes["unresolved_issues"]:
        st.caption("No unresolved issues.")
    for u in minutes["unresolved_issues"]:
        _item("", chip("Open", "neutral"), u["description"])
        evidence(u["evidence_segment_ids"], by_id, expand_evidence)
