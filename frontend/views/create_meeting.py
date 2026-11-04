from datetime import date

import streamlit as st

import api_client as api
import components as c
import ui


def render():
    c.page_header("Create New Meeting", "Enter the basic details. You can add the recording on the next screen.",
                  eyebrow="Meetings")
    with st.form("create_meeting"):
        st.markdown("### Meeting details")
        title = st.text_input("Meeting title", placeholder="e.g. Water supply and pipeline repair")
        description = st.text_area("Description (optional)", placeholder="What is this meeting about?", height=90)
        meeting_date = st.date_input("Meeting date", value=date.today())

        st.markdown("### Location")
        c1, c2, c3 = st.columns(3)
        village = c1.text_input("Village name", placeholder="e.g. Rampur")
        district = c2.text_input("District", placeholder="e.g. Bengaluru Rural")
        state = c3.text_input("State", placeholder="e.g. Karnataka")

        st.markdown("### Languages")
        l1, l2 = st.columns(2)
        primary = l1.selectbox("Main language of the meeting", list(ui.LANGUAGES), format_func=ui.LANGUAGES.get)
        supported = l2.multiselect("All languages spoken", list(ui.LANGUAGES), default=list(ui.LANGUAGES),
                                   format_func=ui.LANGUAGES.get, help="Include every language people may use.")
        submitted = st.form_submit_button("Create meeting", type="primary")

    if not submitted:
        return

    errors = []
    if not title.strip():
        errors.append("Enter a meeting title.")
    if not village.strip():
        errors.append("Enter the village name.")
    if not district.strip():
        errors.append("Enter the district.")
    if not state.strip():
        errors.append("Enter the state.")
    if not supported:
        errors.append("Choose at least one language.")
    elif primary not in supported:
        errors.append("The main language must also be in the list of languages spoken.")
    if errors:
        for e in errors:
            st.error(e)
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
    ui.invalidate()
    ui.flash("Meeting created. Add the recording next.")
    ui.go("audio", meeting["id"])
