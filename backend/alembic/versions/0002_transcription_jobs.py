"""Persistent Prisma Batch queue, segment provenance, and minutes review flags."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("transcription_jobs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("meeting_id", pg.UUID(as_uuid=True), sa.ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("audio_sha256", sa.String(64), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("audio_data", sa.LargeBinary()),
        sa.Column("language_codes", pg.JSONB(), nullable=False),
        sa.Column("model", sa.String(32), nullable=False, server_default="prisma-v3.0"),
        sa.Column("output_format", sa.String(16), nullable=False, server_default="codemix"),
        sa.Column("status", sa.String(24), nullable=False, server_default="queued"),
        sa.Column("provider_job_id", sa.String(64), unique=True),
        sa.Column("provider_status", sa.String(32)),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_poll_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("error_code", sa.String(64)),
        sa.Column("warnings", pg.JSONB(), nullable=False, server_default="[]"),
        sa.Column("result_json", pg.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("meeting_id", "audio_sha256", name="uq_transcription_audio"),
        sa.CheckConstraint("status IN ('queued','submitting','submitted','processing','completed','failed','needs_reconciliation')", name="ck_transcription_status"))
    op.create_index("ix_transcription_due", "transcription_jobs", ["status", "next_poll_at"])
    op.create_index("ix_transcription_meeting", "transcription_jobs", ["meeting_id"])
    op.add_column("transcript_segments", sa.Column("transcription_job_id", pg.UUID(as_uuid=True)))
    op.add_column("transcript_segments", sa.Column("source_index", sa.Integer()))
    op.add_column("transcript_segments", sa.Column("detected_language", sa.String(64)))
    op.add_column("transcript_segments", sa.Column("provider_speaker_id", sa.Integer()))
    op.create_foreign_key("fk_segment_transcription_job", "transcript_segments", "transcription_jobs", ["transcription_job_id"], ["id"], ondelete="CASCADE")
    op.create_unique_constraint("uq_segment_transcription_source", "transcript_segments", ["transcription_job_id", "source_index"])
    op.add_column("meeting_minutes", sa.Column("review_flags", pg.JSONB(), nullable=False, server_default="[]"))


def downgrade():
    op.drop_column("meeting_minutes", "review_flags")
    op.drop_constraint("uq_segment_transcription_source", "transcript_segments", type_="unique")
    op.drop_constraint("fk_segment_transcription_job", "transcript_segments", type_="foreignkey")
    for column in ("provider_speaker_id", "detected_language", "source_index", "transcription_job_id"):
        op.drop_column("transcript_segments", column)
    op.drop_table("transcription_jobs")
