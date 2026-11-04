"""GramSathi AI — Streamlit entry point.  Run from the repo root: streamlit run frontend/app.py"""
from html import escape

import streamlit as st

import api_client as api
import styles
import ui
from views import audio, auth, create_meeting, dashboard, meetings, minutes, verification

st.set_page_config(page_title="GramSathi AI", page_icon=":material/groups:", layout="wide")
styles.inject()
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

NAV = [  # key, label, icon, url, render function
    ("dashboard", "Dashboard", ":material/space_dashboard:", "dashboard", dashboard.render),
    ("meetings", "All Meetings", ":material/folder_open:", "meetings", meetings.render),
    ("create", "Create New Meeting", ":material/add_circle:", "create", create_meeting.render),
    ("audio", "Audio & Transcripts", ":material/graphic_eq:", "audio", audio.render),
    ("minutes", "Meeting Minutes", ":material/description:", "minutes", minutes.render),
    ("verification", "Verification", ":material/verified:", "verification", verification.render),
]
ui.PAGES.clear()
for key, label, icon, url, func in NAV:
    ui.PAGES[key] = st.Page(func, title=label, icon=icon, url_path=url, default=(key == "dashboard"))
page = st.navigation(list(ui.PAGES.values()), position="hidden")

user = st.session_state.user
with st.sidebar:
    st.markdown('<div class="gs-brand"><div class="gs-brand-mark">G</div><div>'
                '<div class="gs-brand-name">GramSathi AI</div>'
                '<div class="gs-brand-sub">Gram Sabha meeting assistant</div></div></div>', unsafe_allow_html=True)
    for key, label, icon, _, _ in NAV:
        st.page_link(ui.PAGES[key], label=label, icon=icon)
    st.markdown(f'<div class="gs-profile"><div class="gs-avatar">{escape(ui.initials(user["name"]))}</div><div>'
                f'<div class="gs-profile-name">{escape(user["name"])}</div>'
                f'<div class="gs-profile-mail">{escape(user["email"])}</div></div></div>', unsafe_allow_html=True)
    if st.button("Log out", width="stretch", icon=":material/logout:"):
        ui.logout()

ui.show_flash()
page.run()
