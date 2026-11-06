from html import escape

import streamlit as st

import api_client as api
import components as c
import ui

FILTERS = {"All": None, "No minutes yet": "none", "Awaiting review": "draft", "Verified": "verified"}


def render():
    token = st.session_state.token
    head, action = st.columns([2, 1.2], vertical_alignment="bottom")
    with head:
        c.page_header("All Meetings", "Open a meeting to add a recording, review minutes or verify.", eyebrow="Meetings")
    with action:
        if st.button("Create New Meeting", type="primary", width="stretch", icon=":material/add:"):
            ui.go("create")

    try:
        with st.spinner("Loading meetings…"):
            meetings = api.list_meetings(token)
            statuses = ui.minutes_statuses(token, meetings)
    except api.ApiError as exc:
        ui.handle_error(exc)
        return
    if not meetings:
        c.empty_state("No meetings yet", "Create your first meeting to get started.")
        return

    search = st.text_input("Search", placeholder="Search by title, village or district", label_visibility="collapsed")
    choice = st.segmented_control("Status", list(FILTERS), default="All", label_visibility="collapsed") or "All"

    shown = sorted(meetings, key=lambda m: m["created_at"], reverse=True)
    if search:
        q = search.lower()
        shown = [m for m in shown if q in " ".join([m["title"], m["village_name"], m["district"]]).lower()]
    if FILTERS[choice]:
        shown = [m for m in shown if statuses.get(m["id"]) == FILTERS[choice]]
    if not shown:
        c.empty_state("No meetings match", "Try a different search or status filter.")
        return

    for m in shown:
        with st.container(border=True):
            st.markdown(
                f'<div class="gs-meeting-title">{escape(m["title"])}</div>'
                f'<div class="gs-meeting-meta">{escape(m["village_name"])}, {escape(m["district"])}, {escape(m["state"])}'
                f' · {ui.fmt_date(m["meeting_date"])} · {escape(ui.LANGUAGES[m["primary_language"]])}</div>'
                + c.status_chip(statuses.get(m["id"], "unknown")), unsafe_allow_html=True)
            b1, b2, b3, _ = st.columns([1.6, 1.2, 1, 2])
            if b1.button("Transcript", key=f"a_{m['id']}", width="stretch"):
                ui.go("audio", m["id"])
            if b2.button("Minutes", key=f"m_{m['id']}", width="stretch"):
                ui.go("minutes", m["id"])
            with b3.popover("More", width="stretch"):
                st.caption("Deleting removes the meeting, its transcript and minutes for good.")
                confirm = st.checkbox("I understand", key=f"c_{m['id']}")
                if st.button("Delete meeting", key=f"d_{m['id']}", disabled=not confirm, type="primary"):
                    try:
                        api.delete_meeting(token, m["id"])
                    except api.ApiError as exc:
                        ui.handle_error(exc)
                    else:
                        ui.invalidate()
                        if st.session_state.meeting_id == m["id"]:
                            st.session_state.meeting_id = None
                        ui.flash("Meeting deleted.")
                        st.rerun()
