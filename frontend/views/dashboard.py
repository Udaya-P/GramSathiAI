import streamlit as st

import api_client as api
import ui


def render():
    head, action = st.columns([4, 1])
    head.header("My Gram Sabha meetings")
    if action.button("➕ New meeting", type="primary", width="stretch"):
        ui.goto("create")

    try:
        with st.spinner("Loading meetings…"):
            meetings = api.list_meetings(st.session_state.token)
    except api.ApiError as exc:
        ui.handle_error(exc)
        return

    if not meetings:
        st.info("You have no meetings yet. Create your first meeting to get started.")
        return

    search = st.text_input("Search by title, village or district", placeholder="Search…")
    if search:
        q = search.lower()
        meetings = [m for m in meetings
                    if q in " ".join([m["title"], m["village_name"], m["district"]]).lower()]
        if not meetings:
            st.warning("No meetings match your search.")
            return

    cols = st.columns(3)
    for i, m in enumerate(meetings):
        with cols[i % 3].container(border=True):
            st.subheader(m["title"])
            st.caption(f"📍 {m['village_name']}, {m['district']}, {m['state']}")
            st.write(f"📅 {m['meeting_date']}  ·  🗣️ {ui.LANGUAGES[m['primary_language']]}")
            if st.button("Open meeting", key=f"open_{m['id']}", width="stretch"):
                ui.goto("meeting", m["id"])
