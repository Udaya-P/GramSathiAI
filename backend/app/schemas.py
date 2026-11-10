from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator, model_validator

Language = Literal["hi", "te", "kn", "en"]
Nonblank = Annotated[str, StringConstraints(min_length=1, max_length=20000)]
ShortText = Annotated[str, StringConstraints(min_length=1, max_length=200)]
Evidence = Annotated[list[Annotated[int, Field(strict=True, gt=0)]], Field(min_length=1, max_length=1000)]


class Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    @field_validator("*", mode="after")
    @classmethod
    def reject_blank(cls, value):
        # Validate without stripping: original multilingual text is preserved exactly.
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc)
        if isinstance(value, str) and not value.strip():
            raise ValueError("Must not be blank")
        return value


class Register(Schema):
    name: ShortText
    email: EmailStr
    password: Annotated[str, Field(min_length=12, max_length=128)]

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value):
        return value.lower()


class Login(Schema):
    email: EmailStr
    password: Annotated[str, Field(min_length=1, max_length=128)]


class UserOut(Schema):
    id: UUID
    name: str
    email: EmailStr
    created_at: datetime


class Token(Schema):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class MeetingCreate(Schema):
    title: Annotated[str, Field(min_length=1, max_length=300)]
    village_name: ShortText
    district: ShortText
    state: ShortText
    meeting_date: date
    primary_language: Language
    supported_languages: Annotated[list[Language], Field(min_length=1, max_length=4)]
    description: Nonblank | None = None

    @model_validator(mode="after")
    def valid_languages(self):
        if self.primary_language not in self.supported_languages:
            raise ValueError("Supported languages must include the primary language")
        if len(set(self.supported_languages)) != len(self.supported_languages):
            raise ValueError("Supported languages must be unique")
        return self


class MeetingOut(MeetingCreate):
    id: UUID
    owner_id: UUID
    created_at: datetime


class SegmentCreate(Schema):
    speaker_id: ShortText
    language: Literal["hi", "te", "kn", "en", "mixed"]
    text: Nonblank
    start_time: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    end_time: Annotated[float, Field(gt=0, allow_inf_nan=False)]

    @model_validator(mode="after")
    def valid_times(self):
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be greater than start_time")
        return self


class TranscriptCreate(Schema):
    segments: Annotated[list[SegmentCreate], Field(min_length=1, max_length=1000)]


class SegmentOut(SegmentCreate):
    id: int
    meeting_id: UUID
    transcription_job_id: UUID | None = None
    source_index: int | None = None
    detected_language: str | None = None
    provider_speaker_id: int | None = None


class EvidenceQuote(Schema):
    segment_id: Annotated[int, Field(strict=True, gt=0)]
    quote: Nonblank


Money = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2, allow_inf_nan=False)]
Classification = Literal["approved", "proposed", "rejected", "deferred", "unclear"]


class DecisionCreate(Schema):
    description: Nonblank
    status: Literal["proposed", "approved", "rejected"]
    classification: Classification | None = None
    estimated_amount: Money | None = None
    proposed_amount: Money | None = None
    approved_amount: Money | None = None
    currency: Literal["INR", "USD", "EUR"] | None = None
    evidence_segment_ids: Evidence
    evidence_quotes: list[EvidenceQuote] = Field(default_factory=list, max_length=1000)

    @model_validator(mode="before")
    @classmethod
    def map_status(cls, value):
        if isinstance(value, dict):
            value = dict(value)
            raw = value.get("status")
            if isinstance(raw, str):
                raw = raw.lower()
                value["status"] = "proposed" if raw in {"deferred", "unclear"} else raw
                value.setdefault("classification", raw)
            if isinstance(value.get("classification"), str):
                value["classification"] = value["classification"].lower()
        return value

    @model_validator(mode="after")
    def consistent_status(self):
        self.classification = self.classification or self.status
        expected = "proposed" if self.classification in {"deferred", "unclear"} else self.classification
        if self.status != expected:
            raise ValueError("classification must agree with the legacy status")
        return self


class ActionCreate(Schema):
    task: Nonblank
    assigned_to: ShortText | None = None
    deadline: date | None = None
    deadline_text: ShortText | None = None
    evidence_segment_ids: Evidence
    evidence_quotes: list[EvidenceQuote] = Field(default_factory=list, max_length=1000)


class IssueCreate(Schema):
    description: Nonblank
    evidence_segment_ids: Evidence
    evidence_quotes: list[EvidenceQuote] = Field(default_factory=list, max_length=1000)


class SummaryClaim(Schema):
    text: Nonblank
    evidence_segment_ids: Evidence
    evidence_quotes: list[EvidenceQuote] = Field(default_factory=list, max_length=1000)


class MinutesCreate(Schema):
    summary: Nonblank
    summary_evidence_segment_ids: list[Annotated[int, Field(strict=True, gt=0)]] = Field(default_factory=list, max_length=1000)
    summary_claims: list[SummaryClaim] = Field(default_factory=list, max_length=1000)
    expected_revision: Annotated[int, Field(ge=1)] | None = None
    decisions: Annotated[list[DecisionCreate], Field(max_length=1000)] = Field(default_factory=list)
    action_items: Annotated[list[ActionCreate], Field(max_length=1000)] = Field(default_factory=list)
    unresolved_issues: Annotated[list[IssueCreate], Field(max_length=1000)] = Field(default_factory=list)


class MinutesOut(MinutesCreate):
    id: int
    meeting_id: UUID
    status: Literal["draft", "verified"]
    verifier_name: str | None
    verified_at: datetime | None
    created_at: datetime
    review_flags: list[dict] = Field(default_factory=list)
    generation_source: str = "manual"
    generation_model: str | None = None
    review_state: Literal["pending", "rejected", "accepted"] = "pending"
    revision: int = 1


class Verification(Schema):
    """Prototype user confirmation, not legally authenticated government approval."""
    verifier_name: ShortText
    confirmed: Literal[True]
    acknowledge_warnings: bool = Field(default=False, strict=True)
    expected_revision: Annotated[int, Field(ge=1)] | None = None
    comment: Nonblank | None = None

    @field_validator("confirmed", mode="before")
    @classmethod
    def explicit_confirmation(cls, value):
        if value is not True:
            raise ValueError("Explicit confirmed: true is required")
        return value


class GenerateMinutes(Schema):
    provider: Literal["groq", "evon", "mock"] = "groq"
    fixture: MinutesCreate | None = None

    @model_validator(mode="after")
    def explicit_fixture(self):
        if (self.provider == "mock") != (self.fixture is not None):
            raise ValueError("Only mock mode accepts and requires a fixture")
        return self


class ReviewMinutes(Schema):
    decision: Literal["approve", "reject"]
    reviewer_name: ShortText
    expected_revision: Annotated[int, Field(ge=1)]
    confirmed: bool = Field(default=False, strict=True)
    acknowledge_warnings: bool = Field(default=False, strict=True)
    comment: Nonblank | None = None


class TranscriptionJobOut(Schema):
    id: UUID
    meeting_id: UUID
    filename: str
    language_codes: list[str]
    model: str
    output_format: str
    status: str
    provider_job_id: str | None
    provider_status: str | None
    progress: int
    attempts: int
    error_code: str | None
    warnings: list[dict]
    created_at: datetime
    updated_at: datetime


class ResumeTranscription(Schema):
    provider_job_id: UUID
