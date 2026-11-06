from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile

from app import schemas
from app.security import CurrentUser, Db
from app.services import meeting_service as service
from app.services import transcription_service, evon

router = APIRouter(prefix="/api/v1/meetings", tags=["Meetings"])


@router.post("", response_model=schemas.MeetingOut, status_code=201)
def create(payload: schemas.MeetingCreate, db: Db, user: CurrentUser):
    return service.create_meeting(db, user.id, payload)


@router.get("", response_model=list[schemas.MeetingOut])
def list_owned(db: Db, user: CurrentUser, offset: Annotated[int, Query(ge=0)] = 0,
               limit: Annotated[int, Query(ge=1, le=100)] = 50):
    return service.list_meetings(db, user.id, offset, limit)


@router.get("/{meeting_id}", response_model=schemas.MeetingOut)
def get(meeting_id: UUID, db: Db, user: CurrentUser):
    return service.owned_meeting(db, meeting_id, user.id)


@router.delete("/{meeting_id}", status_code=204)
def delete(meeting_id: UUID, db: Db, user: CurrentUser):
    service.delete_meeting(db, meeting_id, user.id)
    return Response(status_code=204)


@router.post("/{meeting_id}/transcript", response_model=list[schemas.SegmentOut], status_code=201)
def append_transcript(meeting_id: UUID, payload: schemas.TranscriptCreate, db: Db, user: CurrentUser):
    return service.append_transcript(db, meeting_id, user.id, payload)


@router.get("/{meeting_id}/transcript", response_model=list[schemas.SegmentOut])
def get_transcript(meeting_id: UUID, db: Db, user: CurrentUser):
    return service.transcript(db, meeting_id, user.id)


@router.post("/{meeting_id}/minutes", response_model=schemas.MinutesOut)
def save_minutes(meeting_id: UUID, payload: schemas.MinutesCreate, db: Db, user: CurrentUser):
    return service.save_minutes(db, meeting_id, user.id, payload)


@router.get("/{meeting_id}/minutes", response_model=schemas.MinutesOut)
def get_minutes(meeting_id: UUID, db: Db, user: CurrentUser):
    return service.get_minutes(db, meeting_id, user.id)


@router.post("/{meeting_id}/minutes/verify", response_model=schemas.MinutesOut,
             description="Prototype owner confirmation only; not legally authenticated government approval.")
def verify_minutes(meeting_id: UUID, payload: schemas.Verification, db: Db, user: CurrentUser):
    return service.verify_minutes(db, meeting_id, user.id, payload)


@router.post("/{meeting_id}/transcriptions", response_model=schemas.TranscriptionJobOut, status_code=202,
             description="Queue one M4A (maximum 10 MiB). No Gnani call is made by this request. Duplicate audio/options returns the same job with 200.")
def submit_transcription(meeting_id: UUID, db: Db, user: CurrentUser, response: Response,
                         audio: Annotated[UploadFile, File()],
                         language_code: Annotated[str, Form(description="Comma-separated: en-IN,te-IN / en-IN,kn-IN / en-IN,hi-IN / en-IN,te-IN,kn-IN,hi-IN")]):
    try:
        job, created = transcription_service.submit(db, meeting_id, user.id, audio, language_code)
    finally:
        audio.file.close()
    if not created:
        response.status_code = 200
    return job


@router.get("/{meeting_id}/transcriptions", response_model=list[schemas.TranscriptionJobOut])
def list_transcriptions(meeting_id: UUID, db: Db, user: CurrentUser):
    return transcription_service.list_jobs(db, meeting_id, user.id)


@router.get("/{meeting_id}/transcriptions/{job_id}", response_model=schemas.TranscriptionJobOut,
            description="Read durable local status; this endpoint never polls Gnani.")
def transcription_status(meeting_id: UUID, job_id: UUID, db: Db, user: CurrentUser):
    return transcription_service.get_job(db, meeting_id, user.id, job_id)


@router.post("/{meeting_id}/transcriptions/{job_id}/resume", response_model=schemas.TranscriptionJobOut,
             description="Reconcile an ambiguous create using its real provider job ID. The worker checks the opaque upload name and configuration before starting/importing.")
def resume_transcription(meeting_id: UUID, job_id: UUID, payload: schemas.ResumeTranscription, db: Db, user: CurrentUser):
    return transcription_service.resume(db, meeting_id, user.id, job_id, payload)


@router.post("/{meeting_id}/minutes/generate", response_model=schemas.MinutesOut,
             description="Default live Evon returns 501. Explicit mock mode requires development settings and a fixture with real persisted citations. All generated content remains a reviewed draft.")
def generate_minutes(meeting_id: UUID, db: Db, user: CurrentUser,
                     adapter: Annotated[evon.EvonAdapter, Depends(evon.get_evon_adapter)],
                     request: schemas.GenerateMinutes | None = None):
    return evon.generate_minutes(db, meeting_id, user.id, adapter, request)


@router.get("/{meeting_id}/decisions", response_model=list[schemas.DecisionCreate])
def get_decisions(meeting_id: UUID, db: Db, user: CurrentUser):
    return service.get_minutes(db, meeting_id, user.id).decisions


@router.get("/{meeting_id}/action-items", response_model=list[schemas.ActionCreate])
def get_action_items(meeting_id: UUID, db: Db, user: CurrentUser):
    return service.get_minutes(db, meeting_id, user.id).action_items


@router.get("/{meeting_id}/minutes/integrity")
def get_integrity(meeting_id: UUID, db: Db, user: CurrentUser):
    minutes = service.get_minutes(db, meeting_id, user.id)
    return {"revision": minutes.revision, "review_flags": minutes.review_flags}


@router.get("/{meeting_id}/minutes/evidence")
def get_evidence(meeting_id: UUID, db: Db, user: CurrentUser):
    return service.minutes_evidence(db, meeting_id, user.id)


@router.get("/{meeting_id}/minutes/history")
def get_history(meeting_id: UUID, db: Db, user: CurrentUser):
    minutes = service.get_minutes(db, meeting_id, user.id)
    return {"generated_original": minutes.generated_original, "history": minutes.history}


@router.post("/{meeting_id}/minutes/review", response_model=schemas.MinutesOut,
             description="Owner review: reject with a comment, or approve with explicit confirmation and warning acknowledgement. This is prototype confirmation, not government approval.")
def review_minutes(meeting_id: UUID, payload: schemas.ReviewMinutes, db: Db, user: CurrentUser):
    return service.review_minutes(db, meeting_id, user.id, payload)
