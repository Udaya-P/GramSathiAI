import streamlit as st

import api_client as api
import components as c
import ui


def render():
    c.page_header("Verification", "Check the minutes against the transcript, then confirm them.", eyebrow="Meeting workflow")
    ctx = c.meeting_context()
    if not ctx:
        return
    minutes = ctx["minutes"]

    c.callout("Verification here is a person confirming the minutes inside this prototype application. "
              "It is not official government approval and has no legal standing.", "warn", "Please note")

    if not minutes:
        c.empty_state("Nothing to verify yet", "Save draft minutes first, then return here to confirm them.")
        if st.button("Go to Meeting Minutes", icon=":material/description:"):
            ui.go("minutes")
        return

    if ctx["status"] == "verified":
        c.callout(f"Verified by {minutes['verifier_name']} on {ui.fmt_datetime(minutes['verified_at'])}. "
                  "These minutes can no longer be edited.", "ok", "Minutes verified")

    st.markdown("#### What you are confirming")
    st.caption("Each decision and action below is linked to the words in the transcript that support it.")
    c.minutes_document(minutes, ctx["by_id"], expand_evidence=True)
    c.voice_player(minutes)

    if ctx["status"] == "verified":
        return
    st.divider()
    st.markdown("### Confirm the minutes")
    with st.form("verify"):
        name = st.text_input("Your full name", placeholder="The person confirming these minutes")
        confirmed = st.checkbox("I have read these minutes and checked them against the transcript. "
                                "I confirm they are accurate.")
        submitted = st.form_submit_button("Verify minutes", type="primary")
    if not submitted:
        return
    if not name.strip() or not confirmed:
        st.error("Enter your name and tick the confirmation box.")
        return
    try:
        with st.spinner("Verifying…"):
            result = api.verify_minutes(ctx["token"], ctx["meeting"]["id"], name.strip())
    except api.ApiError as exc:
        ui.handle_error(exc)
        return
    if result and result.get("status") == "verified":
        ui.invalidate()
        ui.flash("Minutes verified.")
        st.rerun()
    else:
        st.error("The server did not confirm the verification. The minutes are still a draft.")
