"""Initial schema.

pgvector + full-text search on file_chunks (HNSW + GIN), RBAC tables,
audit trail, generated images and per-call LLM usage accounting.

Revision ID: 0001
Revises:
Create Date: 2026-10-22
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR

from app.config import get_settings

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    dim = get_settings().embedding_dimension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255)),
        sa.Column("full_name", sa.String(255)),
        sa.Column("department", sa.String(100)),
        sa.Column("role", sa.String(50)),
        sa.Column("designation", sa.String(100)),
        sa.Column("is_active", sa.Boolean, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.current_timestamp()),
        sa.Column("last_login", sa.DateTime),
        sa.Column("external_id", sa.String(255), unique=True),
        sa.Column("token_version", sa.Integer, nullable=False, server_default="0"),
    )

    op.create_table(
        "files",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("file_path", sa.String(500)),
        sa.Column("file_type", sa.String(20)),
        sa.Column("file_size_bytes", sa.Integer),
        sa.Column("department", sa.String(100)),
        sa.Column("owner_id", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("is_public", sa.Boolean, server_default=sa.false()),
        sa.Column("access_level", sa.String(50)),
        sa.Column("is_indexed", sa.Boolean, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.current_timestamp()),
        sa.Column("uploaded_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("version", sa.Integer, server_default="1"),
        sa.Column("index_status", sa.String(20), server_default="pending"),
        sa.Column("index_error", sa.Text),
        sa.Column("chunk_count", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_index("ix_files_department", "files", ["department"])
    op.create_index("ix_files_index_status", "files", ["index_status"])

    op.create_table(
        "file_chunks",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("file_id", sa.Integer, sa.ForeignKey("files.id", ondelete="CASCADE")),
        sa.Column("chunk_text", sa.Text, nullable=False),
        sa.Column("embedding", Vector(dim)),
        sa.Column("content_tsv", TSVECTOR),
        sa.Column("page_number", sa.Integer),
        sa.Column("section_title", sa.String(255)),
        sa.Column("chunk_index", sa.Integer),
        sa.Column("metadata", JSONB),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.current_timestamp()),
    )
    op.create_index("ix_file_chunks_file_id", "file_chunks", ["file_id"])
    # HNSW needs no training step, so it works from the first inserted row
    # (ivfflat built on an empty table has useless centroids).
    op.execute(
        "CREATE INDEX ix_file_chunks_embedding ON file_chunks USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute("CREATE INDEX ix_file_chunks_tsv ON file_chunks USING gin (content_tsv)")
    # content_tsv is maintained by the database so no code path can forget it
    op.execute(
        """
        CREATE OR REPLACE FUNCTION file_chunks_tsv_update() RETURNS trigger AS $$
        BEGIN
            NEW.content_tsv := to_tsvector('english', NEW.chunk_text);
            RETURN NEW;
        END
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_file_chunks_tsv
        BEFORE INSERT OR UPDATE OF chunk_text ON file_chunks
        FOR EACH ROW EXECUTE FUNCTION file_chunks_tsv_update()
        """
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("action", sa.String(100)),
        sa.Column("resource_type", sa.String(50)),
        sa.Column("resource_id", sa.Integer),
        sa.Column("details", JSONB),
        sa.Column("ip_address", sa.String(45)),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.current_timestamp()),
    )
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])

    op.create_table(
        "file_access_permissions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("file_id", sa.Integer, sa.ForeignKey("files.id", ondelete="CASCADE")),
        sa.Column("role", sa.String(50)),
        sa.Column("department", sa.String(100)),
        sa.Column("can_read", sa.Boolean, server_default=sa.false()),
        sa.Column("can_download", sa.Boolean, server_default=sa.false()),
        sa.Column("can_share", sa.Boolean, server_default=sa.false()),
        sa.Column("granted_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("granted_at", sa.DateTime, server_default=sa.func.current_timestamp()),
    )

    op.create_table(
        "access_requests",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("requester_id", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("file_id", sa.Integer, sa.ForeignKey("files.id", ondelete="CASCADE")),
        sa.Column("status", sa.String(50)),
        sa.Column("requested_at", sa.DateTime, server_default=sa.func.current_timestamp()),
        sa.Column("approver_id", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("approved_at", sa.DateTime),
        sa.Column("expires_at", sa.DateTime),
        sa.Column("is_recurring", sa.Boolean, server_default=sa.false()),
    )
    op.create_index("ix_access_requests_requester", "access_requests", ["requester_id"])

    op.create_table(
        "department_access_rules",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("department", sa.String(100)),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("rule_name", sa.String(255)),
        sa.Column("description", sa.Text),
        sa.Column("source_role", sa.String(50)),
        sa.Column("target_file_type", sa.String(100)),
        sa.Column("action", sa.String(50)),
        sa.Column("auto_approve_after_hours", sa.Integer),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.current_timestamp()),
        sa.Column("is_active", sa.Boolean, server_default=sa.true()),
    )

    op.create_table(
        "generated_images",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("department", sa.String(100)),
        sa.Column("prompt", sa.Text, nullable=False),
        sa.Column("provider", sa.String(50)),
        sa.Column("mime_type", sa.String(50)),
        sa.Column("file_path", sa.String(500)),
        sa.Column("file_size_bytes", sa.Integer),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.current_timestamp()),
    )
    op.create_index("ix_generated_images_user_id", "generated_images", ["user_id"])

    op.create_table(
        "llm_usage",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("tier", sa.String(10), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("prompt_tokens", sa.Integer, server_default="0"),
        sa.Column("completion_tokens", sa.Integer, server_default="0"),
        sa.Column("cost_usd", sa.Float, server_default="0"),
        sa.Column("latency_ms", sa.Integer, server_default="0"),
        sa.Column("success", sa.Boolean, server_default=sa.true()),
        sa.Column("error", sa.String(500)),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.current_timestamp()),
    )
    op.create_index("ix_llm_usage_created_at", "llm_usage", ["created_at"])
    op.create_index("ix_llm_usage_tier", "llm_usage", ["tier"])


def downgrade() -> None:
    op.drop_table("llm_usage")
    op.drop_table("generated_images")
    op.drop_table("department_access_rules")
    op.drop_table("access_requests")
    op.drop_table("file_access_permissions")
    op.drop_table("audit_logs")
    op.execute("DROP TRIGGER IF EXISTS trg_file_chunks_tsv ON file_chunks")
    op.execute("DROP FUNCTION IF EXISTS file_chunks_tsv_update()")
    op.drop_table("file_chunks")
    op.drop_table("files")
    op.drop_table("users")
