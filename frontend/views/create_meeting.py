from datetime import date

import streamlit as st

import api_client as api
import ui


def render():
    st.header("Create a meeting")
    with st.form("create_meeting"):
        title = st.text_input("Meeting title")
        c1, c2, c3 = st.columns(3)
        village = c1.text_input("Village")
        district = c2.text_input("District")
        state = c3.text_input("State")
        c4, c5 = st.columns(2)
        meeting_date = c4.date_input("Meeting date", value=date.today())
        primary = c5.selectbox("Primary language", list(ui.LANGUAGES), format_func=ui.LANGUAGES.get)
        supported = st.multiselect("Languages spoken in the meeting", list(ui.LANGUAGES),
                                   default=list(ui.LANGUAGES), format_func=ui.LANGUAGES.get)
        description = st.text_area("Description (optional)")
        submitted = st.form_submit_button("Create meeting", type="primary")

    if not submitted:
        return

    if not all(v.strip() for v in (title, village, district, state)):
        st.error("Title, village, district and state are required.")
        return
    if not supported:
        st.error("Select at least one language.")
        return
    if primary not in supported:
        st.error("The primary language must be included in the languages spoken.")
        return

    payload = {"title": title.strip(), "village_name": village.strip(), "district": district.strip(),
               "state": state.strip(), "meeting_date": meeting_date.isoformat(),
               "primary_language": primary, "supported_languages": supported}
    if description.strip():
        payload["description"] = description.strip()
    try:
        with st.spinner("Creating meeting…"):
            meeting = api.create_meeting(st.session_state.token, payload)
    except api.ApiError as exc:
        ui.handle_error(exc)
        return
    ui.flash("Meeting created.")
    ui.goto("meeting", meeting["id"])
