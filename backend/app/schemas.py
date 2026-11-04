from datetime import date, datetime, timezone
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


class DecisionCreate(Schema):
    description: Nonblank
    status: Literal["proposed", "approved", "rejected"]
    evidence_segment_ids: Evidence


class ActionCreate(Schema):
    task: Nonblank
    assigned_to: ShortText
    deadline: date | None = None
    evidence_segment_ids: Evidence


class IssueCreate(Schema):
    description: Nonblank
    evidence_segment_ids: Evidence


class MinutesCreate(Schema):
    summary: Nonblank
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


class Verification(Schema):
    """Prototype user confirmation, not legally authenticated government approval."""
    verifier_name: ShortText
    confirmed: Literal[True]

    @field_validator("confirmed", mode="before")
    @classmethod
    def explicit_confirmation(cls, value):
        if value is not True:
            raise ValueError("Explicit confirmed: true is required")
        return value


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
