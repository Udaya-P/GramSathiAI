"""Session state, navigation, error handling and small formatting helpers."""
from __future__ import annotations

import re
from datetime import datetime

import streamlit as st

import api_client as api
from api_client import ApiError

LANGUAGES = {"hi": "Hindi (हिन्दी)", "te": "Telugu (తెలుగు)", "kn": "Kannada (ಕನ್ನಡ)", "en": "English"}
SEGMENT_LANGUAGES = {**LANGUAGES, "mixed": "Mixed languages"}

# Filled in by app.py on every run; maps a page key to its st.Page.
PAGES: dict = {}


def init_state():
    for key, default in {"token": None, "user": None, "meeting_id": None, "flash": None,
                         "edit_minutes": False}.items():
        st.session_state.setdefault(key, default)


# --- navigation -----------------------------------------------------------
def go(page_key: str, meeting_id: str | None = None):
    if meeting_id:
        st.session_state.meeting_id = meeting_id
    st.switch_page(PAGES[page_key])


def logout(message: str | None = None):
    st.cache_data.clear()
    for key in ("token", "user", "meeting_id"):
        st.session_state[key] = None
    st.session_state.edit_minutes = False
    st.session_state.flash = message
    st.rerun()


def flash(message: str):
    """Show a toast after the next rerun."""
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


# --- cached status lookups (dashboard / meeting list) ----------------------
@st.cache_data(ttl=30, show_spinner=False)
def _minutes_status(token: str, meeting_id: str) -> str:
    minutes = api.get_minutes(token, meeting_id)
    return minutes["status"] if minutes else "none"


def minutes_statuses(token: str, meetings: list) -> dict:
    """meeting id -> 'none' | 'draft' | 'verified' | 'unknown'."""
    result = {}
    for m in meetings:
        try:
            result[m["id"]] = _minutes_status(token, m["id"])
        except ApiError as exc:
            if exc.status == 401:
                raise
            result[m["id"]] = "unknown"
    return result


def invalidate():
    """Call after anything that changes meetings, transcripts or minutes."""
    st.cache_data.clear()


# --- formatting -------------------------------------------------------------
def fmt_time(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def fmt_size(num_bytes: int) -> str:
    if num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.0f} KB"
    return f"{num_bytes / (1024 * 1024):.1f} MB"


def fmt_datetime(value: str | None) -> str:
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone().strftime("%d %b %Y, %I:%M %p")
    except ValueError:
        return value


def fmt_date(value: str | None) -> str:
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value).strftime("%d %b %Y")
    except ValueError:
        return value


def lang_label(code: str) -> str:
    return SEGMENT_LANGUAGES.get(code, code)


def speaker_label(raw: str) -> str:
    """Provider IDs look like 'gnani_<uuid>_speaker_2'; show 'Speaker 2'."""
    match = re.search(r"speaker[_ ]?(\d+)$", raw or "", re.IGNORECASE)
    return f"Speaker {match.group(1)}" if match else (raw or "Unknown speaker")


def initials(name: str) -> str:
    parts = [p for p in (name or "").split() if p]
    return ("".join(p[0] for p in parts[:2]) or "?").upper()
