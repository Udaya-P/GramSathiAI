import streamlit as st

import api_client as api
import ui


def render():
    ui.show_flash()
    _, col, _ = st.columns([1, 1.5, 1])
    with col:
        st.markdown('<div class="gs-brand" style="margin-top:2rem"><div class="gs-brand-mark">G</div><div>'
                    '<div class="gs-brand-name">GramSathi AI</div>'
                    '<div class="gs-brand-sub">Gram Sabha meeting assistant</div></div></div>', unsafe_allow_html=True)
        st.markdown('<div class="gs-title">Meeting minutes, made clear</div>'
                    '<div class="gs-subtitle">Record Gram Sabha discussions in Hindi, Telugu, Kannada or English, '
                    'review what was said, and confirm the final minutes.</div>', unsafe_allow_html=True)

        login_tab, register_tab = st.tabs(["Log in", "Create account"])
        with login_tab:
            with st.form("login_form"):
                email = st.text_input("Email address", placeholder="name@example.com")
                password = st.text_input("Password", type="password")
                submitted = st.form_submit_button("Log in", type="primary", width="stretch")
            if submitted:
                if not email or not password:
                    st.error("Enter your email address and password.")
                else:
                    try:
                        with st.spinner("Logging in…"):
                            result = api.login(email.strip(), password)
                        st.session_state.token = result["access_token"]
                        st.session_state.user = None
                        st.rerun()
                    except api.ApiError as exc:
                        st.error(exc.message)

        with register_tab:
            with st.form("register_form"):
                name = st.text_input("Full name", placeholder="e.g. Lakshmi Devi")
                email = st.text_input("Email address", key="reg_email", placeholder="name@example.com")
                password = st.text_input("Password", type="password", key="reg_password",
                                         help="Use at least 12 characters.")
                submitted = st.form_submit_button("Create account", type="primary", width="stretch")
            if submitted:
                if not name.strip() or not email.strip():
                    st.error("Enter your name and email address.")
                elif len(password) < 12:
                    st.error("Your password needs at least 12 characters.")
                else:
                    try:
                        with st.spinner("Creating your account…"):
                            api.register(name.strip(), email.strip(), password)
                        st.success("Account created. Open the Log in tab to sign in.")
                    except api.ApiError as exc:
                        st.error(exc.message)
