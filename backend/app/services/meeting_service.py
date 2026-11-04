"""All meeting mutations lock the parent row until the request commits.

This serializes draft replacement, verification, appends and deletion for one
meeting while allowing independent meetings to be processed concurrently.
"""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas


def owned_meeting(db: Session, meeting_id: UUID, owner_id: UUID, *, lock=False):
    query = select(models.Meeting).where(models.Meeting.id == meeting_id, models.Meeting.owner_id == owner_id)
    if lock:
        query = query.with_for_update()
    meeting = db.scalar(query)
    if meeting is None:
        raise HTTPException(404, "Meeting not found")
    return meeting


def create_meeting(db, owner_id, payload):
    meeting = models.Meeting(owner_id=owner_id, **payload.model_dump())
    db.add(meeting)
    db.flush()
    return meeting


def list_meetings(db, owner_id, offset, limit):
    return db.scalars(select(models.Meeting).where(models.Meeting.owner_id == owner_id)
                      .order_by(models.Meeting.created_at.desc(), models.Meeting.id).offset(offset).limit(limit)).all()


def delete_meeting(db, meeting_id, owner_id):
    db.delete(owned_meeting(db, meeting_id, owner_id, lock=True))
    db.flush()


def transcript(db, meeting_id, owner_id):
    owned_meeting(db, meeting_id, owner_id)
    return ordered_segments(db, meeting_id)


def ordered_segments(db, meeting_id):
    return db.scalars(select(models.TranscriptSegment).where(models.TranscriptSegment.meeting_id == meeting_id)
                      .order_by(models.TranscriptSegment.start_time, models.TranscriptSegment.end_time, models.TranscriptSegment.id)).all()


def append_transcript(db, meeting_id, owner_id, payload):
    owned_meeting(db, meeting_id, owner_id, lock=True)
    segments = [models.TranscriptSegment(meeting_id=meeting_id, **s.model_dump()) for s in payload.segments]
    db.add_all(segments)
    db.flush()
    return sorted(segments, key=lambda s: (s.start_time, s.end_time, s.id))


def current_minutes(db, meeting_id):
    minutes = db.scalar(select(models.MeetingMinutes).where(models.MeetingMinutes.meeting_id == meeting_id))
    if minutes is None:
        raise HTTPException(404, "Minutes not found")
    return minutes


def get_minutes(db, meeting_id, owner_id):
    owned_meeting(db, meeting_id, owner_id)
    return current_minutes(db, meeting_id)


def save_minutes(db: Session, meeting_id: UUID, owner_id: UUID, payload: schemas.MinutesCreate):
    owned_meeting(db, meeting_id, owner_id, lock=True)
    minutes = db.scalar(select(models.MeetingMinutes).where(models.MeetingMinutes.meeting_id == meeting_id))
    if minutes and minutes.status == "verified":
        raise HTTPException(409, "Verified minutes cannot be overwritten")
    ids = {i for entry in [*payload.decisions, *payload.action_items, *payload.unresolved_issues] for i in entry.evidence_segment_ids}
    valid = set(db.scalars(select(models.TranscriptSegment.id).where(
        models.TranscriptSegment.meeting_id == meeting_id, models.TranscriptSegment.id.in_(ids))).all()) if ids else set()
    if ids != valid:
        raise HTTPException(422, "Every evidence segment must exist and belong to this meeting")
    if minutes is None:
        minutes = models.MeetingMinutes(meeting_id=meeting_id, summary=payload.summary)
        db.add(minutes)
    minutes.review_flags = []
    minutes.summary = payload.summary
    minutes.decisions = [models.Decision(**d.model_dump()) for d in payload.decisions]
    minutes.action_items = [models.ActionItem(**a.model_dump()) for a in payload.action_items]
    minutes.unresolved_issues = [models.UnresolvedIssue(**i.model_dump()) for i in payload.unresolved_issues]
    db.flush()
    return minutes


def verify_minutes(db, meeting_id, owner_id, payload):
    owned_meeting(db, meeting_id, owner_id, lock=True)
    minutes = current_minutes(db, meeting_id)
    if minutes.status != "draft":
        raise HTTPException(409, "Only draft minutes can be verified")
    # Prototype owner confirmation; this does not establish legal/government identity.
    minutes.review_flags = []  # Explicit owner confirmation resolves outstanding review flags.
    minutes.status = "verified"
    minutes.verifier_name = payload.verifier_name
    minutes.verified_at = datetime.now(timezone.utc)
    db.flush()
    return minutes
