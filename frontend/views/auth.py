import streamlit as st

import api_client as api
import ui


def render():
    ui.show_flash()
    _, col, _ = st.columns([1, 1.4, 1])
    with col:
        st.title("🌾 GramSathi AI")
        st.write("Multilingual Gram Sabha meeting assistant — turn village discussions in Hindi, Telugu, "
                 "Kannada and English into evidence-linked minutes.")
        login_tab, register_tab = st.tabs(["Log in", "Register"])

        with login_tab:
            with st.form("login_form"):
                email = st.text_input("Email")
                password = st.text_input("Password", type="password")
                submitted = st.form_submit_button("Log in", type="primary", width="stretch")
            if submitted:
                if not email or not password:
                    st.error("Enter your email and password.")
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
                name = st.text_input("Full name")
                email = st.text_input("Email", key="reg_email")
                password = st.text_input("Password (12–128 characters)", type="password", key="reg_password")
                submitted = st.form_submit_button("Create account", width="stretch")
            if submitted:
                if len(password) < 12:
                    st.error("Password must be at least 12 characters.")
                else:
                    try:
                        with st.spinner("Creating account…"):
                            api.register(name.strip(), email.strip(), password)
                        st.success("Account created. Switch to the Log in tab to sign in.")
                    except api.ApiError as exc:
                        st.error(exc.message)
