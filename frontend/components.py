"""Reusable UI building blocks shared by every page."""
from __future__ import annotations

from html import escape

import streamlit as st

import api_client as api
import ui
from recording_player import play_segment

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
    "deferred": ("Deferred", "Decision postponed", "amber"),
    "unclear": ("Unclear", "Outcome needs review", "neutral"),
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


def evidence(ids: list, by_id: dict, expanded: bool = False, quotes=(), *, playback=None, key=""):
    if not ids:
        return
    label = "Supporting transcript: " + ", ".join(f"#{i}" for i in ids)
    with st.expander(label, expanded=expanded):
        for i in dict.fromkeys(ids):
            s = by_id.get(i)
            if s:
                segment_card(s)
                if playback:
                    play_segment(playback, s, key=key, label=f"Play evidence #{i}")
            else:
                st.warning(f"Segment #{i} was not found in the transcript.")
        for quote in quotes:
            st.caption(f"Quote from segment #{quote['segment_id']}")
            st.text(quote["quote"])


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


def minutes_document(minutes: dict, by_id: dict, expand_evidence: bool = False, *, playback=None):
    """Show the structured draft and its review evidence."""
    source = minutes.get("generation_source")
    if source == "groq":
        st.caption(f"AI draft via Groq · {minutes.get('generation_model') or 'configured model'}")
    elif source == "mock_fixture":
        st.caption("Development fixture draft")

    st.markdown("### Meeting summary")
    with st.container(border=True):
        st.text(minutes["summary"])
        evidence(minutes.get("summary_evidence_segment_ids", []), by_id, expand_evidence,
                 playback=playback, key="summary")
        for index, claim in enumerate(minutes.get("summary_claims", [])):
            st.text(claim["text"])
            evidence(claim["evidence_segment_ids"], by_id, expand_evidence, claim.get("evidence_quotes", []),
                     playback=playback, key=f"claim-{index}")

    st.markdown("### Decisions")
    if not minutes["decisions"]:
        st.caption("No decisions were recorded.")
    for index, decision in enumerate(minutes["decisions"]):
        status = decision.get("classification") or decision["status"]
        label, hint, tone = DECISION[status]
        _item(status, chip(label, tone) + f' <span class="gs-item-meta">{escape(hint)}</span>', decision["description"])
        amounts = [f"{role} {decision.get('currency') or ''} {decision[field]}".replace("  ", " ")
                   for role, field in (("Estimate", "estimated_amount"), ("Proposed", "proposed_amount"),
                                       ("Approved", "approved_amount")) if decision.get(field) is not None]
        if amounts:
            st.caption(" · ".join(amounts))
        evidence(decision["evidence_segment_ids"], by_id, expand_evidence, decision.get("evidence_quotes", []),
                 playback=playback, key=f"decision-{index}")

    st.markdown("### Action items")
    if not minutes["action_items"]:
        st.caption("No action items were recorded.")
    for index, action in enumerate(minutes["action_items"]):
        deadline = " · ".join(filter(None, [ui.fmt_date(action.get("deadline")), action.get("deadline_text")]))
        assignee = action.get("assigned_to") or "Unassigned"
        _item("", chip("Action", "blue"), action["task"],
              f"Responsible: <b>{escape(assignee)}</b> &nbsp;·&nbsp; Deadline: <b>{escape(deadline or 'No deadline set')}</b>")
        evidence(action["evidence_segment_ids"], by_id, expand_evidence, action.get("evidence_quotes", []),
                 playback=playback, key=f"action-{index}")

    st.markdown("### Unresolved issues")
    if not minutes["unresolved_issues"]:
        st.caption("No unresolved issues.")
    for index, issue in enumerate(minutes["unresolved_issues"]):
        _item("", chip("Open", "neutral"), issue["description"])
        evidence(issue["evidence_segment_ids"], by_id, expand_evidence, issue.get("evidence_quotes", []),
                 playback=playback, key=f"issue-{index}")

    flags = minutes.get("review_flags", [])
    if flags:
        with st.expander(f"Integrity warnings ({len(flags)})", expanded=expand_evidence):
            for index, flag in enumerate(flags):
                ids = flag.get("evidence_segment_ids", [])
                location = flag.get("entity", "Draft")
                code = flag.get("code", "Review")
                acknowledged = " · Acknowledged" if flag.get("acknowledged") else ""
                references = " · " + ", ".join(f"#{i}" for i in ids) if ids else ""
                st.text(f"{code} · {location}{references}{acknowledged}")
                st.text(flag.get("explanation", "Review this item against its transcript evidence."))
                if playback:
                    for i in dict.fromkeys(ids):
                        if i in by_id:
                            play_segment(playback, by_id[i], key=f"warning-{index}", label=f"Play evidence #{i}")
