"""Shared UI helpers: session state, navigation, error handling and styling."""
from __future__ import annotations

import streamlit as st

from api_client import ApiError

LANGUAGES = {"hi": "Hindi (हिन्दी)", "te": "Telugu (తెలుగు)", "kn": "Kannada (ಕನ್ನಡ)", "en": "English"}
SEGMENT_LANGUAGES = {**LANGUAGES, "mixed": "Mixed"}

CSS = """
<style>
html, body, [class*="css"] { font-family: "Noto Sans", "Noto Sans Devanagari", "Noto Sans Telugu",
  "Noto Sans Kannada", system-ui, sans-serif; }
.gs-seg { border-left: 4px solid #2e7d32; padding: .4rem .8rem; margin: .35rem 0;
  background: rgba(46,125,50,.07); border-radius: 0 6px 6px 0; }
.gs-meta { font-size: .8rem; opacity: .75; }
.gs-text { font-size: 1.05rem; line-height: 1.6; }
</style>
"""


def init_state():
    for key, default in {"token": None, "user": None, "page": "dashboard", "meeting_id": None,
                         "flash": None}.items():
        st.session_state.setdefault(key, default)
    st.markdown(CSS, unsafe_allow_html=True)


def goto(page: str, meeting_id: str | None = None):
    st.session_state.page = page
    st.session_state.meeting_id = meeting_id
    st.rerun()


def logout(message: str | None = None):
    for key in ("token", "user", "meeting_id"):
        st.session_state[key] = None
    st.session_state.page = "dashboard"
    st.session_state.flash = message
    st.rerun()


def flash(message: str):
    """Show a success message after the next rerun."""
    st.session_state.flash = message


def show_flash():
    if st.session_state.get("flash"):
        st.toast(st.session_state.flash)
        st.session_state.flash = None


def handle_error(exc: ApiError):
    """Expired sessions log the user out; everything else is shown inline."""
    if exc.status == 401 and st.session_state.get("token"):
        logout("Your session has expired. Please log in again.")
    st.error(exc.message)


def fmt_time(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def lang_label(code: str) -> str:
    return SEGMENT_LANGUAGES.get(code, code)
