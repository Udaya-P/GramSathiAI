"""Deliver private audio to one Streamlit session and seek with subsecond precision."""
from base64 import b64encode

import streamlit as st

import api_client as api
import ui


_PLAYER = st.components.v2.component(
    "original_recording_player",
    html="""
        <audio controls preload="metadata" aria-label="Original meeting recording"></audio>
        <div><label hidden><input type="checkbox"> Continue past the segment end</label></div>
        <div role="status"></div>
    """,
    css="audio { width: 100%; }",
    js="""
export default function ({data, parentElement}) {
    const audio = parentElement.querySelector("audio");
    const continuePlayback = parentElement.querySelector("input");
    const status = parentElement.querySelector('[role="status"]');
    const listeners = new AbortController();
    const on = (event, handler) => audio.addEventListener(event, handler, {signal: listeners.signal});
    const bytes = Uint8Array.from(atob(data.audio), char => char.charCodeAt(0));
    const source = URL.createObjectURL(new Blob([bytes], {type: "audio/mp4"}));
    continuePlayback.checked = false;
    continuePlayback.parentElement.hidden = data.end === null;
    status.textContent = "";

    on("loadedmetadata", () => {
        if (data.start >= audio.duration) {
            status.textContent = "This timestamp is outside the recording. You can still play the original.";
            continuePlayback.checked = true;
            return;
        }
        audio.currentTime = data.start;
        audio.play().catch(() => {
            if (!listeners.signal.aborted && !audio.error) {
                status.textContent = "Press Play in the audio player to start.";
            }
        });
    });
    const limited = () => data.end !== null && !continuePlayback.checked;
    on("play", () => {
        if (limited() && audio.currentTime >= data.end) audio.currentTime = data.start;
    });
    on("playing", () => { status.textContent = ""; });
    on("timeupdate", () => {
        if (!audio.paused && limited() && audio.currentTime >= data.end) {
            audio.pause();
            audio.currentTime = data.end;
        }
    });
    on("error", () => { status.textContent = "This browser could not play the recording."; });
    audio.src = source;

    return () => {
        listeners.abort();
        audio.pause();
        audio.removeAttribute("src");
        audio.load();
        URL.revokeObjectURL(source);
    };
}
""",
)


def play_recording(token, meeting_id, job_id, *, key, label, start=0, end=None):
    if not job_id:
        st.caption("No original recording is linked to this segment.")
        return
    key = f"recording-{meeting_id}-{key}"
    if not st.button(label, key=key, icon=":material/play_arrow:"):
        return
    try:
        with st.spinner("Loading original recording…"):
            audio = api.get_recording(token, meeting_id, job_id)
    except api.ApiError as exc:
        if exc.status == 404:
            st.info("The original recording is unavailable. If you have it, upload the identical M4A "
                    "with the same languages to this meeting to restore playback.")
        else:
            ui.handle_error(exc)
        return
    # Passing bytes to st.audio would register a separate, unauthenticated media URL.
    _PLAYER(key=f"{key}-player", data={"audio": b64encode(audio).decode("ascii"), "start": start, "end": end})


def play_segment(ctx, segment, *, key, label):
    play_recording(ctx["token"], ctx["meeting"]["id"], segment.get("transcription_job_id"),
                   key=f"{key}-{segment['id']}", label=label,
                   start=segment["start_time"], end=segment["end_time"])
