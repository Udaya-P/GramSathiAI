"""GramSathi AI — Streamlit entry point.  Run: streamlit run frontend/app.py"""
import streamlit as st

import api_client as api
import ui
from views import auth, create_meeting, dashboard, workspace

st.set_page_config(page_title="GramSathi AI", page_icon="🌾", layout="wide")
ui.init_state()

if not st.session_state.token:
    auth.render()
    st.stop()

if not st.session_state.user:
    try:
        st.session_state.user = api.me(st.session_state.token)
    except api.ApiError as exc:
        ui.handle_error(exc)
        st.stop()

with st.sidebar:
    st.title("🌾 GramSathi AI")
    st.caption(f"Signed in as **{st.session_state.user['name']}**")
    if st.button("📋 My meetings", width="stretch"):
        ui.goto("dashboard")
    if st.button("➕ New meeting", width="stretch"):
        ui.goto("create")
    st.divider()
    if st.button("Log out", width="stretch"):
        ui.logout()

ui.show_flash()
page = st.session_state.page
if page == "create":
    create_meeting.render()
elif page == "meeting" and st.session_state.meeting_id:
    workspace.render(st.session_state.meeting_id)
else:
    dashboard.render()
