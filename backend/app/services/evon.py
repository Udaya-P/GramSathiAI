"""Reasoning provider dispatch and the reserved Evon adapter."""
from typing import Protocol

from fastapi import HTTPException
from sqlalchemy import select

from app import models, schemas
from app.config import get_settings
from app.services import meeting_service
from app.services.groq_reasoning import GroqReasoningAdapter

MISSING_CONTRACT = (
    "Live Evon generation is unavailable: official endpoint/base URL, authentication, "
    "model identifier, request/response and citation schemas, limits and job lifecycle are required."
)


class ReasoningProvider(Protocol):
    name: str

    def generate(self, segments: list[dict]) -> schemas.MinutesCreate:
        """Consume original persisted segment IDs/text/times; return an untrusted candidate."""
        ...


class EvonUnavailable(RuntimeError):
    pass


class EvonAdapter:
    name = "evon"

    def generate(self, segments: list[dict]) -> schemas.MinutesCreate:
        raise EvonUnavailable(MISSING_CONTRACT)


class MockEvonAdapter:
    """Deterministic fixture provider, clearly distinguished from real Evon."""
    name = "mock_fixture"

    def __init__(self, fixture: dict):
        self.fixture = fixture

    def generate(self, segments: list[dict]) -> schemas.MinutesCreate:
        return schemas.MinutesCreate.model_validate(self.fixture)


def get_evon_adapter():
    return EvonAdapter()


def generate_minutes(db, meeting_id, owner_id, adapter: ReasoningProvider, request=None):
    meeting = meeting_service.owned_meeting(db, meeting_id, owner_id, lock=True)
    minutes_query = select(models.MeetingMinutes).where(models.MeetingMinutes.meeting_id == meeting_id)
    existing = db.scalar(minutes_query)
    if existing and existing.status == "verified":
        raise HTTPException(409, "Verified minutes cannot be overwritten")
    segments = meeting_service.ordered_segments(db, meeting_id)
    if not segments:
        raise HTTPException(409, "A transcript is required before reasoning")
    provider = request.provider if request else "groq"
    if provider == "groq":
        settings = get_settings()
        key = settings.groq_api_key
        adapter = GroqReasoningAdapter(key.get_secret_value() if key else None, settings.groq_model)
    elif provider == "mock":
        adapter = MockEvonAdapter(request.fixture.model_dump())
    if adapter.name == "mock_fixture":
        settings = get_settings()
        if settings.app_environment not in {"development", "test"} or not settings.enable_mock_reasoning:
            raise HTTPException(403, "Mock reasoning is development/test only; enable APP_ENVIRONMENT and ENABLE_MOCK_REASONING explicitly")
    meeting_snapshot = schemas.MeetingOut.model_validate(meeting)
    draft_version = (existing.id, existing.revision) if existing else None
    transcript = [schemas.SegmentOut.model_validate(s).model_dump(mode="json") for s in segments]
    # End the snapshot transaction before waiting on the external provider.
    db.rollback()
    try:
        raw = adapter.generate(transcript)
        # Revalidate even provider-created Pydantic instances; do not trust an
        # adapter that used model_construct() or mutated a validated candidate.
        if isinstance(raw, schemas.MinutesCreate):
            raw = raw.model_dump()
        candidate = schemas.MinutesCreate.model_validate(raw)
    except EvonUnavailable:
        raise HTTPException(501, MISSING_CONTRACT) from None
    except ValueError:
        raise HTTPException(422, {"code": "unsupported_or_invalid_claims", "saved": False,
                                  "review_flags": [{"code": "INSUFFICIENT_EVIDENCE", "entity": "candidate",
                                                    "explanation": "Malformed structured output or empty evidence for a material claim.",
                                                    "evidence_segment_ids": [], "requires_human_review": True, "severity": "error"}]}) from None
    current_meeting = meeting_service.owned_meeting(db, meeting_id, owner_id, lock=True)
    current = db.scalar(minutes_query)
    current_version = (current.id, current.revision) if current else None
    current_transcript = [schemas.SegmentOut.model_validate(s).model_dump(mode="json")
                          for s in meeting_service.ordered_segments(db, meeting_id)]
    if (current_version != draft_version or current_transcript != transcript
            or schemas.MeetingOut.model_validate(current_meeting) != meeting_snapshot):
        raise HTTPException(409, "The meeting changed during generation. Reload it and try again.")
    candidate.expected_revision = draft_version[1] if draft_version else None
    return meeting_service.save_minutes(
        db, meeting_id, owner_id, candidate, source=adapter.name,
        source_model=adapter.model if isinstance(adapter, GroqReasoningAdapter) else None,
    )
