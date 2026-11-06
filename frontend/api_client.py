"""All communication with the FastAPI backend lives here."""
from __future__ import annotations

import os

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
TIMEOUT = 30


class ApiError(Exception):
    """A failed backend call, with a message that is safe to show to the user."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.message = message
        self.status = status


def _detail_message(response: requests.Response) -> str:
    try:
        detail = response.json().get("detail")
    except (ValueError, AttributeError):
        return ""
    if isinstance(detail, str):
        return detail
    if isinstance(detail, list):  # FastAPI/Pydantic 422 list
        parts = []
        for err in detail:
            loc = ".".join(str(p) for p in err.get("loc", []) if p not in ("body",))
            parts.append(f"{loc}: {err.get('msg', 'invalid')}" if loc else err.get("msg", "invalid"))
        return "; ".join(parts)
    return ""


def request(method: str, path: str, token: str | None = None, **kwargs):
    headers = kwargs.pop("headers", {})
    timeout = kwargs.pop("timeout", TIMEOUT)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        response = requests.request(method, f"{BASE_URL}{path}", headers=headers, timeout=timeout, **kwargs)
    except requests.exceptions.Timeout:
        raise ApiError("The server took too long to respond. Please try again.") from None
    except requests.exceptions.ConnectionError:
        raise ApiError(f"Cannot reach the backend at {BASE_URL}. Is it running?") from None
    except requests.exceptions.RequestException as exc:
        raise ApiError(f"Request failed: {exc}") from None

    if response.ok:
        return response.json() if response.content else None

    detail = _detail_message(response)
    status = response.status_code
    if status == 401:
        msg = detail or "Your session has expired. Please log in again."
    elif status == 403:
        msg = detail or "You do not have permission to do that."
    elif status == 404:
        msg = detail or "Not found."
    elif status == 409:
        msg = detail or "That conflicts with existing data."
    elif status == 422:
        msg = f"Please check the form: {detail}" if detail else "Some fields are invalid."
    else:
        msg = detail or f"Server error ({status}). Please try again."
    raise ApiError(msg, status)


# --- auth -------------------------------------------------------------
def register(name, email, password):
    return request("POST", "/api/v1/auth/register", json={"name": name, "email": email, "password": password})


def login(email, password):
    return request("POST", "/api/v1/auth/login", json={"email": email, "password": password})


def me(token):
    return request("GET", "/api/v1/auth/me", token)


# --- meetings ---------------------------------------------------------
def list_meetings(token):
    return request("GET", "/api/v1/meetings", token, params={"limit": 100})


def create_meeting(token, payload):
    return request("POST", "/api/v1/meetings", token, json=payload)


def get_meeting(token, meeting_id):
    return request("GET", f"/api/v1/meetings/{meeting_id}", token)


def delete_meeting(token, meeting_id):
    return request("DELETE", f"/api/v1/meetings/{meeting_id}", token)


# --- transcript -------------------------------------------------------
def get_transcript(token, meeting_id):
    return request("GET", f"/api/v1/meetings/{meeting_id}/transcript", token)


def add_transcript(token, meeting_id, segments):
    return request("POST", f"/api/v1/meetings/{meeting_id}/transcript", token, json={"segments": segments})


# --- minutes ----------------------------------------------------------
def get_minutes(token, meeting_id):
    """Returns None when no minutes have been saved yet (backend answers 404)."""
    try:
        return request("GET", f"/api/v1/meetings/{meeting_id}/minutes", token)
    except ApiError as exc:
        if exc.status == 404:
            return None
        raise


def save_minutes(token, meeting_id, payload):
    return request("POST", f"/api/v1/meetings/{meeting_id}/minutes", token, json=payload)


def verify_minutes(token, meeting_id, verifier_name):
    return request("POST", f"/api/v1/meetings/{meeting_id}/minutes/verify", token,
                   json={"verifier_name": verifier_name, "confirmed": True})


# --- transcription jobs (Prisma) and AI minutes ----------------------------
def submit_transcription(token, meeting_id, filename, audio_bytes, language_code):
    """Queue an M4A upload (max 10 MiB). A duplicate upload returns the existing job."""
    return request("POST", f"/api/v1/meetings/{meeting_id}/transcriptions", token,
                   files={"audio": (filename, audio_bytes, "audio/mp4")},
                   data={"language_code": language_code}, timeout=120)


def list_transcriptions(token, meeting_id):
    return request("GET", f"/api/v1/meetings/{meeting_id}/transcriptions", token)


def generate_minutes(token, meeting_id):
    return request("POST", f"/api/v1/meetings/{meeting_id}/minutes/generate", token)
