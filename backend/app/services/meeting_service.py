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
from app.services import integrity


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


def _check_revision(minutes, expected_revision):
    if expected_revision is not None and minutes.revision != expected_revision:
        raise HTTPException(409, "Draft changed; reload it before reviewing or replacing it")


def minutes_evidence(db, meeting_id, owner_id):
    minutes = get_minutes(db, meeting_id, owner_id)
    payload = schemas.MinutesCreate.model_validate(schemas.MinutesOut.model_validate(minutes).model_dump(
        include=set(schemas.MinutesCreate.model_fields)))
    ids = integrity.evidence_ids(payload)
    return {"revision": minutes.revision,
            "segments": [schemas.SegmentOut.model_validate(s).model_dump(mode="json")
                         for s in ordered_segments(db, meeting_id) if s.id in ids],
            "claims": [{"entity": entity, "evidence_segment_ids": claim.evidence_segment_ids,
                        "evidence_quotes": [q.model_dump() for q in claim.evidence_quotes]}
                       for entity, claim in integrity.claims(payload)]}


def _history_entry(db, minutes, owner_id, event, **metadata):
    document = schemas.MinutesOut.model_validate(minutes).model_dump(mode="json")
    payload = schemas.MinutesCreate.model_validate({k: v for k, v in document.items() if k in schemas.MinutesCreate.model_fields})
    ids = integrity.evidence_ids(payload)
    entry = {"event": event, "actor_user_id": str(owner_id), "at": datetime.now(timezone.utc).isoformat(),
             "revision": minutes.revision, "document": document,
             "evidence": [schemas.SegmentOut.model_validate(s).model_dump(mode="json")
                          for s in ordered_segments(db, minutes.meeting_id) if s.id in ids], **metadata}
    minutes.history = [*(minutes.history or []), entry]
    return entry


def save_minutes(db: Session, meeting_id: UUID, owner_id: UUID, payload: schemas.MinutesCreate, *, source="manual"):
    owned_meeting(db, meeting_id, owner_id, lock=True)
    minutes = db.scalar(select(models.MeetingMinutes).where(models.MeetingMinutes.meeting_id == meeting_id))
    if minutes and minutes.status == "verified":
        raise HTTPException(409, "Verified minutes cannot be overwritten")
    if minutes:
        _check_revision(minutes, payload.expected_revision)
    elif payload.expected_revision is not None:
        raise HTTPException(409, "No existing draft matches expected_revision")
    flags = integrity.check_minutes(payload, ordered_segments(db, meeting_id), generated=source != "manual")
    if any(flag["severity"] == "error" for flag in flags):
        raise HTTPException(422, {"code": "unsupported_claims", "review_flags": flags, "saved": False})
    if minutes is None:
        minutes = models.MeetingMinutes(meeting_id=meeting_id, summary=payload.summary, revision=1)
        db.add(minutes)
    else:
        # Preserve a legacy draft on its first Phase 3 edit as well.
        if not minutes.history:
            _history_entry(db, minutes, owner_id, "prior_draft")
        minutes.revision += 1
    minutes.summary = payload.summary
    minutes.summary_evidence_segment_ids = payload.summary_evidence_segment_ids or sorted(
        {i for claim in payload.summary_claims for i in claim.evidence_segment_ids})
    minutes.summary_claims = [c.model_dump(mode="json") for c in payload.summary_claims]
    minutes.review_flags = flags
    minutes.review_state = "pending"
    if source != "manual" or minutes.generated_original is None:
        minutes.generation_source = source
    minutes.decisions = [models.Decision(**d.model_dump()) for d in payload.decisions]
    minutes.action_items = [models.ActionItem(**a.model_dump()) for a in payload.action_items]
    minutes.unresolved_issues = [models.UnresolvedIssue(**i.model_dump()) for i in payload.unresolved_issues]
    db.flush()
    entry = _history_entry(db, minutes, owner_id, "generated" if source != "manual" else "manual_edit")
    if source != "manual" and minutes.generated_original is None:
        minutes.generated_original = entry
    db.flush()
    return minutes


def verify_minutes(db, meeting_id, owner_id, payload):
    owned_meeting(db, meeting_id, owner_id, lock=True)
    minutes = current_minutes(db, meeting_id)
    _check_revision(minutes, payload.expected_revision)
    if minutes.status != "draft" or minutes.review_state == "rejected":
        raise HTTPException(409, "Only a pending draft can be verified; revise a rejected draft first")
    if minutes.generated_original is not None and minutes.review_flags and not payload.acknowledge_warnings:
        raise HTTPException(409, "Review the integrity warnings and explicitly set acknowledge_warnings=true")
    if not minutes.history:
        _history_entry(db, minutes, owner_id, "prior_draft")
    # Prototype owner confirmation; this does not establish legal/government identity.
    minutes.review_flags = [{**flag, "acknowledged": True} for flag in minutes.review_flags]
    minutes.status, minutes.review_state = "verified", "accepted"
    minutes.verifier_name = payload.verifier_name
    minutes.verified_at = datetime.now(timezone.utc)
    minutes.revision += 1
    _history_entry(db, minutes, owner_id, "approved", reviewer_name=payload.verifier_name, comment=payload.comment)
    db.flush()
    return minutes


def review_minutes(db, meeting_id, owner_id, payload):
    if payload.decision == "approve":
        if payload.confirmed is not True:
            raise HTTPException(422, "Approval requires explicit confirmed=true")
        return verify_minutes(db, meeting_id, owner_id, schemas.Verification(
            verifier_name=payload.reviewer_name, confirmed=True,
            acknowledge_warnings=payload.acknowledge_warnings, expected_revision=payload.expected_revision, comment=payload.comment))
    owned_meeting(db, meeting_id, owner_id, lock=True)
    minutes = current_minutes(db, meeting_id)
    _check_revision(minutes, payload.expected_revision)
    if minutes.status != "draft" or minutes.review_state != "pending":
        raise HTTPException(409, "Only a pending draft can be rejected")
    if not payload.comment:
        raise HTTPException(422, "Rejecting a draft requires a review comment")
    if not minutes.history:
        _history_entry(db, minutes, owner_id, "prior_draft")
    minutes.review_state = "rejected"
    minutes.revision += 1
    _history_entry(db, minutes, owner_id, "rejected", reviewer_name=payload.reviewer_name, comment=payload.comment)
    db.flush()
    return minutes
