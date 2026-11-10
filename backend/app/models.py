from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Date, DateTime, Float, ForeignKey, Index, Integer, LargeBinary, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    meetings: Mapped[list["Meeting"]] = relationship(back_populates="owner", cascade="all, delete-orphan", passive_deletes=True)


class Meeting(Base):
    __tablename__ = "meetings"
    __table_args__ = (CheckConstraint("primary_language IN ('hi','te','kn','en')", name="ck_meeting_language"),)
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    village_name: Mapped[str] = mapped_column(String(200))
    district: Mapped[str] = mapped_column(String(200))
    state: Mapped[str] = mapped_column(String(200))
    meeting_date: Mapped[date] = mapped_column(Date)
    primary_language: Mapped[str] = mapped_column(String(5))
    supported_languages: Mapped[list[str]] = mapped_column(JSONB)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    owner: Mapped[User] = relationship(back_populates="meetings")
    segments: Mapped[list["TranscriptSegment"]] = relationship(cascade="all, delete-orphan", passive_deletes=True)
    minutes: Mapped["MeetingMinutes | None"] = relationship(cascade="all, delete-orphan", passive_deletes=True)


class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"
    __table_args__ = (
        CheckConstraint("start_time >= 0 AND end_time > start_time AND end_time < 'Infinity'::float8", name="ck_segment_times"),
        CheckConstraint("language IN ('hi','te','kn','en','mixed')", name="ck_segment_language"),
        Index("ix_segment_chronology", "meeting_id", "start_time", "end_time", "id"),
        UniqueConstraint("transcription_job_id", "source_index", name="uq_segment_transcription_source"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    meeting_id: Mapped[UUID] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"))
    speaker_id: Mapped[str] = mapped_column(String(200))
    language: Mapped[str] = mapped_column(String(5))
    text: Mapped[str] = mapped_column(Text)
    start_time: Mapped[float] = mapped_column(Float)
    end_time: Mapped[float] = mapped_column(Float)
    transcription_job_id: Mapped[UUID | None] = mapped_column(ForeignKey("transcription_jobs.id", ondelete="CASCADE"))
    source_index: Mapped[int | None] = mapped_column(Integer)
    detected_language: Mapped[str | None] = mapped_column(String(64))
    provider_speaker_id: Mapped[int | None] = mapped_column(Integer)


class MeetingMinutes(Base):
    __tablename__ = "meeting_minutes"
    __table_args__ = (
        UniqueConstraint("meeting_id", name="uq_minutes_meeting"),
        CheckConstraint("status IN ('draft','verified')", name="ck_minutes_status"),
        CheckConstraint("(status = 'draft' AND verifier_name IS NULL AND verified_at IS NULL) OR (status = 'verified' AND verifier_name IS NOT NULL AND verified_at IS NOT NULL)", name="ck_verification_metadata"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    meeting_id: Mapped[UUID] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"))
    summary: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default="draft", server_default="draft")
    verifier_name: Mapped[str | None] = mapped_column(String(200))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    review_flags: Mapped[list[dict]] = mapped_column(JSONB, default=list, server_default="[]")
    summary_evidence_segment_ids: Mapped[list[int]] = mapped_column(JSONB, default=list, server_default="[]")
    summary_claims: Mapped[list[dict]] = mapped_column(JSONB, default=list, server_default="[]")
    generation_model: Mapped[str | None] = mapped_column(String(200))
    generation_source: Mapped[str] = mapped_column(String(20), default="manual", server_default="manual")
    review_state: Mapped[str] = mapped_column(String(10), default="pending", server_default="pending")
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    generated_original: Mapped[dict | None] = mapped_column(JSONB)
    history: Mapped[list[dict]] = mapped_column(JSONB, default=list, server_default="[]", deferred=True)
    decisions: Mapped[list["Decision"]] = relationship(cascade="all, delete-orphan", passive_deletes=True, order_by="Decision.id")
    action_items: Mapped[list["ActionItem"]] = relationship(cascade="all, delete-orphan", passive_deletes=True, order_by="ActionItem.id")
    unresolved_issues: Mapped[list["UnresolvedIssue"]] = relationship(cascade="all, delete-orphan", passive_deletes=True, order_by="UnresolvedIssue.id")


class Decision(Base):
    __tablename__ = "decisions"
    __table_args__ = (CheckConstraint("status IN ('proposed','approved','rejected')", name="ck_decision_status"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    minutes_id: Mapped[int] = mapped_column(ForeignKey("meeting_minutes.id", ondelete="CASCADE"), index=True)
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10))
    classification: Mapped[str] = mapped_column(String(10), default="proposed", server_default="proposed")
    estimated_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    proposed_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    approved_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    evidence_segment_ids: Mapped[list[int]] = mapped_column(JSONB)
    evidence_quotes: Mapped[list[dict]] = mapped_column(JSONB, default=list, server_default="[]")


class ActionItem(Base):
    __tablename__ = "action_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    minutes_id: Mapped[int] = mapped_column(ForeignKey("meeting_minutes.id", ondelete="CASCADE"), index=True)
    task: Mapped[str] = mapped_column(Text)
    assigned_to: Mapped[str | None] = mapped_column(String(200))
    deadline: Mapped[date | None] = mapped_column(Date)
    deadline_text: Mapped[str | None] = mapped_column(String(200))
    evidence_segment_ids: Mapped[list[int]] = mapped_column(JSONB)
    evidence_quotes: Mapped[list[dict]] = mapped_column(JSONB, default=list, server_default="[]")


class UnresolvedIssue(Base):
    __tablename__ = "unresolved_issues"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    minutes_id: Mapped[int] = mapped_column(ForeignKey("meeting_minutes.id", ondelete="CASCADE"), index=True)
    description: Mapped[str] = mapped_column(Text)
    evidence_segment_ids: Mapped[list[int]] = mapped_column(JSONB)
    evidence_quotes: Mapped[list[dict]] = mapped_column(JSONB, default=list, server_default="[]")


class TranscriptionJob(Base):
    """Durable queue. Audio is cleared after the provider ID is committed.

    A create interrupted before that commit is NEVER blindly retried: its
    outcome may be unknown. An owner must reconcile it with the provider ID.
    """
    __tablename__ = "transcription_jobs"
    __table_args__ = (
        UniqueConstraint("meeting_id", "audio_sha256", name="uq_transcription_audio"),
        CheckConstraint("status IN ('queued','submitting','submitted','processing','completed','failed','needs_reconciliation')", name="ck_transcription_status"),
        Index("ix_transcription_due", "status", "next_poll_at"),
        Index("ix_transcription_meeting", "meeting_id"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    meeting_id: Mapped[UUID] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"))
    audio_sha256: Mapped[str] = mapped_column(String(64))
    filename: Mapped[str] = mapped_column(String(255))
    audio_data: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)
    language_codes: Mapped[list[str]] = mapped_column(JSONB)
    model: Mapped[str] = mapped_column(String(32), default="prisma-v3.0", server_default="prisma-v3.0")
    output_format: Mapped[str] = mapped_column(String(16), default="codemix", server_default="codemix")
    status: Mapped[str] = mapped_column(String(24), default="queued", server_default="queued")
    provider_job_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    provider_status: Mapped[str | None] = mapped_column(String(32))
    progress: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    next_poll_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    error_code: Mapped[str | None] = mapped_column(String(64))
    warnings: Mapped[list[dict]] = mapped_column(JSONB, default=list, server_default="[]")
    result_json: Mapped[dict | None] = mapped_column(JSONB, deferred=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
