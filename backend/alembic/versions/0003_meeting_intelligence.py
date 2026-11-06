"""Claim grounding and draft review history; no transcript or job changes."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    for name in ("summary_evidence_segment_ids", "summary_claims", "history"):
        op.add_column("meeting_minutes", sa.Column(name, pg.JSONB(), nullable=False, server_default="[]"))
    op.add_column("meeting_minutes", sa.Column("generation_source", sa.String(20), nullable=False, server_default="manual"))
    op.add_column("meeting_minutes", sa.Column("review_state", sa.String(10), nullable=False, server_default="pending"))
    op.add_column("meeting_minutes", sa.Column("revision", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("meeting_minutes", sa.Column("generated_original", pg.JSONB()))
    # Backfill only review metadata; existing verified documents stay verified.
    op.execute("UPDATE meeting_minutes SET review_state = 'accepted' WHERE status = 'verified'")
    op.add_column("decisions", sa.Column("classification", sa.String(10), nullable=False, server_default="proposed"))
    op.execute("UPDATE decisions SET classification = status")
    for name in ("estimated_amount", "proposed_amount", "approved_amount"):
        op.add_column("decisions", sa.Column(name, sa.Numeric(14, 2)))
    op.add_column("decisions", sa.Column("currency", sa.String(3)))
    op.add_column("action_items", sa.Column("deadline_text", sa.String(200)))
    op.alter_column("action_items", "assigned_to", existing_type=sa.String(200), nullable=True)
    for table in ("decisions", "action_items", "unresolved_issues"):
        op.add_column(table, sa.Column("evidence_quotes", pg.JSONB(), nullable=False, server_default="[]"))


def downgrade():
    # Do not silently replace unknown assignees with invented text on downgrade.
    op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM action_items WHERE assigned_to IS NULL) THEN RAISE EXCEPTION 'Cannot downgrade with unknown assignees'; END IF; END $$")
    for table in ("decisions", "action_items", "unresolved_issues"):
        op.drop_column(table, "evidence_quotes")
    op.alter_column("action_items", "assigned_to", existing_type=sa.String(200), nullable=False)
    op.drop_column("action_items", "deadline_text")
    for name in ("currency", "approved_amount", "proposed_amount", "estimated_amount", "classification"):
        op.drop_column("decisions", name)
    for name in ("generated_original", "revision", "review_state", "generation_source", "history", "summary_claims", "summary_evidence_segment_ids"):
        op.drop_column("meeting_minutes", name)
