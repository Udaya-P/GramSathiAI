"""PostgreSQL-backed Batch worker. Run explicitly; never started by FastAPI.

A session advisory lock allows just one worker tick across all processes. The
lock connection stays open across the durable checkpoints around remote I/O.
This is intentionally a small single-worker queue, not a general task system.
"""
import argparse
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, text
from pydantic import ValidationError

from app.config import get_settings
from app.database import SessionLocal, engine
from app.models import Meeting, TranscriptSegment, TranscriptionJob
from app.services.prisma import MODEL, OUTPUT_FORMAT, ProviderContractError, make_client, normalize_transcript

LOCK_ID = 478291804103  # Application-scoped advisory lock; not a secret.
ACTIVE = ("queued", "submitting", "submitted", "processing")
TERMINAL_FAILURE = {"FAILED", "START_FAILED", "CANCELLED"}


def _snapshot(factory, job_id):
    with factory() as db:
        job = db.get(TranscriptionJob, job_id)
        if job is None:
            return None
        # Copy only what the worker needs; no detached lazy loads.
        return {"id": job.id, "meeting_id": job.meeting_id, "status": job.status,
                "provider_job_id": job.provider_job_id, "language_codes": job.language_codes,
                "audio_data": job.audio_data if job.status == "queued" else None}


def _update(factory, job_id, **values):
    with factory.begin() as db:
        job = db.get(TranscriptionJob, job_id, with_for_update=True)
        if job is not None:
            for name, value in values.items():
                setattr(job, name, value)
            return True
        return False


def _validate_remote(remote, expected_name, codes):
    config = remote.config or {}
    # Especially important when an owner supplies a reconciliation job ID.
    if (config.get("model") != MODEL or config.get("format") != OUTPUT_FORMAT
            or config.get("with_diarization") is not True
            or set(str(config.get("language_code", "")).split(",")) != set(codes)):
        raise ProviderContractError("Provider job configuration does not match")
    files = remote.files()
    if len(files) != 1 or files[0].name != expected_name:
        raise ProviderContractError("Provider file does not match the queued upload")
    return files[0]


def _import(factory, snapshot, document):
    # Normalize the WHOLE response before writing; never leave a partial transcript.
    segments, warnings = normalize_transcript(document, snapshot["id"], snapshot["provider_job_id"])
    with factory.begin() as db:
        meeting = db.scalar(select(Meeting).where(Meeting.id == snapshot["meeting_id"]).with_for_update())
        if meeting is None:  # Meeting may be deleted while the provider is processing.
            return
        job = db.get(TranscriptionJob, snapshot["id"], with_for_update=True)
        if job is None or job.status == "completed":
            return
        # Atomic insert + completed flag, reinforced by a unique source-position key.
        db.add_all([TranscriptSegment(meeting_id=meeting.id, **segment) for segment in segments])
        job.status, job.progress, job.error_code = "completed", 100, None
        job.warnings = warnings
        job.result_json = document
        job.audio_data = None


def process_job(factory, client, job_id):
    """One bounded step (create OR status/start/import), never a wait loop.

    Call through run_once(), which serializes worker processes. Exposed separately
    so tests can inject a mocked SDK without keys or network access.
    """
    snapshot = _snapshot(factory, job_id)
    if snapshot is None or snapshot["status"] not in ACTIVE:
        return
    if snapshot["status"] == "submitting":
        if snapshot["provider_job_id"]:
            _update(factory, job_id, status="submitted", error_code=None)
        else:
            _update(factory, job_id, status="needs_reconciliation", error_code="submission_outcome_unknown")
        return
    if snapshot["status"] == "queued":
        # Persist BEFORE remote creation. Request IDs are trace IDs, not documented
        # idempotency keys. Never automatically repeat an uncertain create call.
        if not _update(factory, job_id, status="submitting", error_code=None):
            return  # Deleted before the upload was claimed.
        try:
            remote = client.create_job(
                (f"{job_id}.m4a", snapshot["audio_data"]),
                language_code=",".join(snapshot["language_codes"]), model=MODEL,
                format=OUTPUT_FORMAT, diarization=True, start=False, request_id=str(job_id),
            )
            _update(factory, job_id, provider_job_id=remote.id, provider_status=remote.status,
                    status="submitted", audio_data=None,
                    next_poll_at=datetime.now(timezone.utc) + timedelta(seconds=10))
        except Exception:
            # Do not log provider exception bodies, credentials, or audio.
            saved = _snapshot(factory, job_id)
            if saved and saved["provider_job_id"]:
                # A lost DB commit acknowledgement may still have saved the ID.
                _update(factory, job_id, status="submitted", error_code=None)
            else:
                _update(factory, job_id, status="needs_reconciliation", error_code="submission_outcome_unknown")
        return
    document = None
    try:
        remote = client.get_job(snapshot["provider_job_id"])
        audio_file = _validate_remote(remote, f"{job_id}.m4a", snapshot["language_codes"])
        _update(factory, job_id, provider_status=remote.status, progress=remote.percent,
                next_poll_at=datetime.now(timezone.utc) + timedelta(seconds=10), error_code=None)
        if remote.status == "CREATED":
            remote.start()  # ID was durably stored in an earlier step.
            _update(factory, job_id, provider_status=remote.status, status="processing")
        elif remote.status in TERMINAL_FAILURE:
            _update(factory, job_id, status="failed", error_code="provider_job_failed")
        elif remote.status in {"COMPLETED", "PARTIAL_FAILURE"}:
            if not audio_file.ok:
                _update(factory, job_id, status="failed", error_code="provider_file_failed")
                return
            document = audio_file.transcript
            _import(factory, snapshot, document)
        else:
            _update(factory, job_id, status="processing")
    except (ProviderContractError, ValidationError, KeyError, TypeError, ValueError):
        _update(factory, job_id, status="failed", error_code="provider_contract_invalid", result_json=document)
    except Exception:
        # Reads/start can be resumed by the persisted ID. A start whose response
        # was lost is checked with get_job before any further start attempt.
        with factory.begin() as db:
            job = db.get(TranscriptionJob, job_id, with_for_update=True)
            if job is not None:
                job.attempts += 1
                job.error_code = "provider_temporarily_unavailable"
                job.next_poll_at = datetime.now(timezone.utc) + timedelta(seconds=min(300, 30 * job.attempts))


def run_once(client, *, db_engine=engine, factory=SessionLocal):
    with db_engine.connect() as lock:
        acquired = lock.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": LOCK_ID})
        lock.commit()
        if not acquired:
            return False
        try:
            with factory() as db:
                job_id = db.scalar(select(TranscriptionJob.id).where(
                    TranscriptionJob.status.in_(ACTIVE), TranscriptionJob.next_poll_at <= func.now())
                    .order_by(TranscriptionJob.next_poll_at, TranscriptionJob.created_at, TranscriptionJob.id).limit(1))
            if job_id is None:
                return False
            process_job(factory, client, job_id)
            return True
        finally:
            lock.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": LOCK_ID})
            lock.commit()


def main():
    parser = argparse.ArgumentParser(description="Run the persistent Prisma Batch queue")
    parser.add_argument("--allow-live", action="store_true", help="Explicitly permit real, billable Gnani calls")
    parser.add_argument("--once", action="store_true", help="Process at most one due job and exit")
    args = parser.parse_args()
    if not args.allow_live:
        parser.error("Worker is disabled by default. Obtain approval before using --allow-live.")
    key = get_settings().gnani_api_key
    if key is None:
        parser.error("GNANI_API_KEY must be set in backend/.env or the environment")
    client = make_client(key.get_secret_value())
    try:
        while True:
            worked = run_once(client)
            if args.once:
                break
            if not worked:
                time.sleep(2)
    except KeyboardInterrupt:
        pass  # Committed provider IDs are picked up next time the worker starts.
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
