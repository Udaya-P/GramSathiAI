"""Local reasoning contract only; NO guessed Evon HTTP endpoint or SDK call.

Missing official contract: base URL, authentication, request/response schemas,
model identifiers, evidence/citation format, limits and asynchronous lifecycle.
The mock is fixture-driven for tests; it never synthesizes fake AI content.
"""
from fastapi import HTTPException
from sqlalchemy import select

from app import models, schemas
from app.services import meeting_service

MISSING_CONTRACT = (
    "Evon is unavailable: official endpoint, authentication, request/response "
    "schema, model, citation format, limits and job lifecycle documentation are required."
)


class EvonUnavailable(RuntimeError):
    pass


class EvonAdapter:
    def generate(self, segments: list[dict]) -> schemas.MinutesCreate:
        raise EvonUnavailable(MISSING_CONTRACT)


class MockEvonAdapter(EvonAdapter):
    """Explicit test fixture, never the application's default generator."""
    def __init__(self, fixture: dict):
        self.fixture = fixture

    def generate(self, segments: list[dict]) -> schemas.MinutesCreate:
        return schemas.MinutesCreate.model_validate(self.fixture)


def get_evon_adapter():
    return EvonAdapter()


def generate_minutes(db, meeting_id, owner_id, adapter):
    meeting_service.owned_meeting(db, meeting_id, owner_id, lock=True)
    existing = db.scalar(select(models.MeetingMinutes).where(models.MeetingMinutes.meeting_id == meeting_id))
    if existing and existing.status == "verified":
        raise HTTPException(409, "Verified minutes cannot be overwritten")
    segments = meeting_service.ordered_segments(db, meeting_id)
    if not segments:
        raise HTTPException(409, "A transcript is required before reasoning")
    try:
        candidate = adapter.generate([schemas.SegmentOut.model_validate(s).model_dump(mode="json") for s in segments])
    except EvonUnavailable:
        raise HTTPException(501, MISSING_CONTRACT) from None
    except ValueError:
        raise HTTPException(422, {"code": "unsupported_or_invalid_claims", "saved": False}) from None
    # Validate even an injected adapter. Missing citations are unsupported claims;
    # never silently drop or save them. Other schema violations also fail closed.
    try:
        candidate = schemas.MinutesCreate.model_validate(candidate)
    except ValueError:
        raise HTTPException(422, {"code": "unsupported_or_invalid_claims", "saved": False}) from None
    valid = {s.id for s in segments}
    flags = []
    for collection in ("decisions", "action_items", "unresolved_issues"):
        for index, claim in enumerate(getattr(candidate, collection)):
            missing = sorted(set(claim.evidence_segment_ids) - valid)
            flags.append({"collection": collection, "index": index,
                          "code": "unsupported_evidence" if missing else "claim_support_unverified",
                          "invalid_segment_ids": missing})
    if any(flag["code"] == "unsupported_evidence" for flag in flags):
        raise HTTPException(422, {"code": "unsupported_claims", "review_flags": flags, "saved": False})
    # Valid IDs prove provenance, not that the claimed meaning is supported.
    # Every generated claim remains flagged for human assessment.
    minutes = meeting_service.save_minutes(db, meeting_id, owner_id, candidate)
    minutes.review_flags = flags
    db.flush()
    return minutes
