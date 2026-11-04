from html import escape

import streamlit as st

import api_client as api
import components as c
import ui


def render():
    token = st.session_state.token
    first = st.session_state.user["name"].split()[0]
    head, action = st.columns([2, 1.2], vertical_alignment="bottom")
    with head:
        c.page_header(f"Welcome, {first}", "Here is where your Gram Sabha meetings stand.", eyebrow="Dashboard")
    with action:
        if st.button("Create New Meeting", type="primary", width="stretch", icon=":material/add:"):
            ui.go("create")

    try:
        with st.spinner("Loading your meetings…"):
            meetings = api.list_meetings(token)
            statuses = ui.minutes_statuses(token, meetings)
    except api.ApiError as exc:
        ui.handle_error(exc)
        return

    counts = list(statuses.values())
    cols = st.columns(4)
    with cols[0]:
        c.stat_card("Total meetings", len(meetings), "All meetings you created")
    with cols[1]:
        c.stat_card("No minutes yet", counts.count("none"), "Waiting for minutes")
    with cols[2]:
        c.stat_card("Awaiting review", counts.count("draft"), "Draft minutes to check", tone="amber")
    with cols[3]:
        c.stat_card("Verified minutes", counts.count("verified"), "Confirmed by a person", tone="green")

    st.markdown("### Recent meetings")
    if not meetings:
        c.empty_state("No meetings yet", "Create your first meeting to start adding recordings and minutes.")
        return

    for m in sorted(meetings, key=lambda x: x["created_at"], reverse=True)[:5]:
        with st.container(border=True):
            info, status, btn = st.columns([4, 2, 1.3], vertical_alignment="center")
            info.markdown(f'<div class="gs-meeting-title">{escape(m["title"])}</div>'
                          f'<div class="gs-meeting-meta">{escape(m["village_name"])}, {escape(m["district"])} · '
                          f'{ui.fmt_date(m["meeting_date"])} · {escape(ui.LANGUAGES[m["primary_language"]])}</div>',
                          unsafe_allow_html=True)
            status.markdown(c.status_chip(statuses.get(m["id"], "unknown")), unsafe_allow_html=True)
            if btn.button("Open", key=f"open_{m['id']}", width="stretch"):
                ui.go("minutes", m["id"])
