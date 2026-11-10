"""Authenticated queue operations. None of these functions contact Gnani."""
import hashlib
from datetime import datetime, timezone
from pathlib import PurePath

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import TranscriptionJob
from app.services import recording_storage
from app.services.meeting_service import owned_meeting
from app.services.prisma import LANGUAGES, MAX_AUDIO_BYTES


def submit(db, meeting_id, owner_id, upload, language_code):
    owned_meeting(db, meeting_id, owner_id, lock=True)
    codes = [part.strip() for part in language_code.split(",")]
    if not 1 <= len(codes) <= 4 or len(set(codes)) != len(codes) or any(code not in LANGUAGES for code in codes):
        raise HTTPException(422, "Use 1–4 unique comma-separated codes: en-IN,te-IN,kn-IN,hi-IN")
    name = PurePath((upload.filename or "").replace("\\", "/")).name
    if not name.lower().endswith(".m4a") or len(name) > 255:
        raise HTTPException(415, "Upload an M4A recording (.m4a)")
    audio = upload.file.read(MAX_AUDIO_BYTES + 1)
    if len(audio) > MAX_AUDIO_BYTES:
        raise HTTPException(413, "Audio exceeds the SDK limit of 10 MiB (10,485,760 bytes)")
    # M4A is an ISO Base Media container; this is a format sanity check, not decoding.
    if len(audio) < 12 or audio[4:8] != b"ftyp":
        raise HTTPException(415, "Empty or invalid M4A container")
    digest = hashlib.sha256(audio).hexdigest()
    previous = db.scalar(select(TranscriptionJob).where(
        TranscriptionJob.meeting_id == meeting_id, TranscriptionJob.audio_sha256 == digest))
    if previous:
        if set(previous.language_codes) != set(codes):
            raise HTTPException(409, "This recording is already submitted with different language options")
        recording_storage.retain(previous, audio)
        return previous, False
    job = TranscriptionJob(meeting_id=meeting_id, filename=name, audio_sha256=digest,
                           audio_data=audio, language_codes=codes)
    db.add(job)
    db.flush()
    recording_storage.retain(job, audio)
    return job, True


def list_jobs(db, meeting_id, owner_id):
    owned_meeting(db, meeting_id, owner_id)
    return db.scalars(select(TranscriptionJob).where(TranscriptionJob.meeting_id == meeting_id)
                      .order_by(TranscriptionJob.created_at, TranscriptionJob.id)).all()


def get_job(db, meeting_id, owner_id, job_id):
    owned_meeting(db, meeting_id, owner_id)
    job = db.scalar(select(TranscriptionJob).where(
        TranscriptionJob.meeting_id == meeting_id, TranscriptionJob.id == job_id))
    if job is None:
        raise HTTPException(404, "Transcription job not found")
    return job


def resume(db, meeting_id, owner_id, job_id, payload):
    owned_meeting(db, meeting_id, owner_id, lock=True)
    job = get_job(db, meeting_id, owner_id, job_id)
    if job.status != "needs_reconciliation" or job.provider_job_id:
        raise HTTPException(409, "Only a job with an unknown submission outcome can be reconciled")
    job.provider_job_id = str(payload.provider_job_id)
    job.status = "submitted"
    job.error_code = None
    job.next_poll_at = datetime.now(timezone.utc)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Provider job is already attached") from None
    # Worker validates model/config and the opaque upload name before starting/importing.
    return job
