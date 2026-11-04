"""Initial PostgreSQL schema. Frozen DDL independent of application models."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("users",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_table("meetings",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("village_name", sa.String(200), nullable=False),
        sa.Column("district", sa.String(200), nullable=False),
        sa.Column("state", sa.String(200), nullable=False),
        sa.Column("meeting_date", sa.Date(), nullable=False),
        sa.Column("primary_language", sa.String(5), nullable=False),
        sa.Column("supported_languages", pg.JSONB(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("primary_language IN ('hi','te','kn','en')", name="ck_meeting_language"))
    op.create_index("ix_meetings_owner_id", "meetings", ["owner_id"])
    op.create_table("transcript_segments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("meeting_id", pg.UUID(as_uuid=True), sa.ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("speaker_id", sa.String(200), nullable=False),
        sa.Column("language", sa.String(5), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("start_time", sa.Float(), nullable=False),
        sa.Column("end_time", sa.Float(), nullable=False),
        sa.CheckConstraint("start_time >= 0 AND end_time > start_time AND end_time < 'Infinity'::float8", name="ck_segment_times"),
        sa.CheckConstraint("language IN ('hi','te','kn','en','mixed')", name="ck_segment_language"))
    op.create_index("ix_segment_chronology", "transcript_segments", ["meeting_id", "start_time", "end_time", "id"])
    op.create_table("meeting_minutes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("meeting_id", pg.UUID(as_uuid=True), sa.ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="draft"),
        sa.Column("verifier_name", sa.String(200)),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("meeting_id", name="uq_minutes_meeting"),
        sa.CheckConstraint("status IN ('draft','verified')", name="ck_minutes_status"),
        sa.CheckConstraint("(status = 'draft' AND verifier_name IS NULL AND verified_at IS NULL) OR (status = 'verified' AND verifier_name IS NOT NULL AND verified_at IS NOT NULL)", name="ck_verification_metadata"))
    op.create_table("decisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("minutes_id", sa.Integer(), sa.ForeignKey("meeting_minutes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("evidence_segment_ids", pg.JSONB(), nullable=False),
        sa.CheckConstraint("status IN ('proposed','approved','rejected')", name="ck_decision_status"))
    op.create_table("action_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("minutes_id", sa.Integer(), sa.ForeignKey("meeting_minutes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task", sa.Text(), nullable=False),
        sa.Column("assigned_to", sa.String(200), nullable=False),
        sa.Column("deadline", sa.Date()),
        sa.Column("evidence_segment_ids", pg.JSONB(), nullable=False))
    op.create_table("unresolved_issues",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("minutes_id", sa.Integer(), sa.ForeignKey("meeting_minutes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("evidence_segment_ids", pg.JSONB(), nullable=False))
    for table in ("decisions", "action_items", "unresolved_issues"):
        op.create_index(f"ix_{table}_minutes_id", table, ["minutes_id"])


def downgrade():
    for table in ("unresolved_issues", "action_items", "decisions", "meeting_minutes", "transcript_segments", "meetings", "users"):
        op.drop_table(table)
