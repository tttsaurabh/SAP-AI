"""phase1 schema hardening

Phase 1 non-security schema hardening:

1. Missing FK indexes: chunks.document_id, conversations.user_id,
   messages.conversation_id, feedbacks.message_id.
2. New first-class `collections` table + `documents.collection_id` FK
   (nullable, `documents.collection_name` is kept as a denormalized display
   cache -- see CLAUDE.md), with a data-migration backfill step: distinct
   `collection_name` values are inserted into `collections`, then
   `documents.collection_id` is set to match.
3. `chunks.vector_id` column (single source of truth for the vector-store
   point/vector id, generated in app/api/documents.py's upload flow).
4. `role`/`status` columns converted from free-text String to native
   Postgres ENUM types (CHECK-constraint-backed VARCHAR on backends without
   native ENUM support, e.g. SQLite) -- purely a representation change, the
   underlying string values are unchanged:
     - users.role -> role_enum ('Super Admin', 'SAP Knowledge Manager',
       'SAP Consultant', 'End User', 'Guest')
     - documents.status -> document_status_enum ('processing', 'active',
       'failed')
     - messages.role -> message_role_enum ('user', 'assistant')

Revision ID: 9ff13957a9db
Revises: 4adb3cd37ee1
Create Date: 2026-07-12 02:43:24.319212

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9ff13957a9db'
down_revision: Union[str, Sequence[str], None] = '4adb3cd37ee1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Enum type definitions live here (not imported from app.core.roles) so this
# migration stays self-contained and immune to future edits of that module.
# Values must stay byte-for-byte identical to app/core/roles.py.
ROLE_VALUES = ("Super Admin", "SAP Knowledge Manager", "SAP Consultant", "End User", "Guest")
DOCUMENT_STATUS_VALUES = ("processing", "active", "failed")
MESSAGE_ROLE_VALUES = ("user", "assistant")


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()

    # ---------------------------------------------------------------- #
    # 1. New `collections` table
    # ---------------------------------------------------------------- #
    op.create_table(
        'collections',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('embedding_model', sa.String(), nullable=True),
        sa.Column('embedding_version', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_collections_id'), 'collections', ['id'], unique=False)
    op.create_index(op.f('ix_collections_name'), 'collections', ['name'], unique=True)

    # ---------------------------------------------------------------- #
    # 2. chunks.vector_id + missing FK indexes
    # ---------------------------------------------------------------- #
    op.add_column('chunks', sa.Column('vector_id', sa.String(), nullable=True))
    op.create_index(op.f('ix_chunks_document_id'), 'chunks', ['document_id'], unique=False)
    op.create_index(op.f('ix_conversations_user_id'), 'conversations', ['user_id'], unique=False)
    op.create_index(op.f('ix_feedbacks_message_id'), 'feedbacks', ['message_id'], unique=False)
    op.create_index(op.f('ix_messages_conversation_id'), 'messages', ['conversation_id'], unique=False)

    # ---------------------------------------------------------------- #
    # 3. documents.collection_id FK
    # ---------------------------------------------------------------- #
    op.add_column('documents', sa.Column('collection_id', sa.Integer(), nullable=True))
    with op.batch_alter_table('documents') as batch_op:
        batch_op.create_foreign_key(
            'fk_documents_collection_id_collections',
            'collections', ['collection_id'], ['id'], ondelete='SET NULL'
        )

    # ---------------------------------------------------------------- #
    # 4. Data migration: backfill collections from existing collection_name
    #    values, then point documents.collection_id at the matching row.
    # ---------------------------------------------------------------- #
    op.execute("""
        INSERT INTO collections (name, created_at)
        SELECT DISTINCT d.collection_name, CURRENT_TIMESTAMP
        FROM documents d
        WHERE d.collection_name IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM collections c WHERE c.name = d.collection_name
          )
    """)
    op.execute("""
        UPDATE documents
        SET collection_id = (
            SELECT c.id FROM collections c WHERE c.name = documents.collection_name
        )
        WHERE documents.collection_name IS NOT NULL
    """)

    # ---------------------------------------------------------------- #
    # 5. Enum-ify role/status columns. sa.Enum(...).create()/.drop() are
    #    dialect-aware: they emit CREATE TYPE/DROP TYPE on Postgres and are
    #    no-ops on backends (e.g. SQLite) that emulate enums via a CHECK
    #    constraint on a VARCHAR column instead. batch_alter_table is used
    #    so this also works on SQLite, which cannot ALTER COLUMN directly.
    # ---------------------------------------------------------------- #
    role_enum = sa.Enum(*ROLE_VALUES, name='role_enum')
    document_status_enum = sa.Enum(*DOCUMENT_STATUS_VALUES, name='document_status_enum')
    message_role_enum = sa.Enum(*MESSAGE_ROLE_VALUES, name='message_role_enum')

    role_enum.create(bind, checkfirst=True)
    document_status_enum.create(bind, checkfirst=True)
    message_role_enum.create(bind, checkfirst=True)

    with op.batch_alter_table('users') as batch_op:
        batch_op.alter_column(
            'role',
            existing_type=sa.String(),
            type_=role_enum,
            postgresql_using='role::role_enum',
            existing_nullable=True,
        )

    with op.batch_alter_table('documents') as batch_op:
        batch_op.alter_column(
            'status',
            existing_type=sa.String(),
            type_=document_status_enum,
            postgresql_using='status::document_status_enum',
            existing_nullable=True,
        )

    with op.batch_alter_table('messages') as batch_op:
        batch_op.alter_column(
            'role',
            existing_type=sa.String(),
            type_=message_role_enum,
            postgresql_using='role::message_role_enum',
            existing_nullable=False,
        )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()

    role_enum = sa.Enum(*ROLE_VALUES, name='role_enum')
    document_status_enum = sa.Enum(*DOCUMENT_STATUS_VALUES, name='document_status_enum')
    message_role_enum = sa.Enum(*MESSAGE_ROLE_VALUES, name='message_role_enum')

    with op.batch_alter_table('messages') as batch_op:
        batch_op.alter_column(
            'role',
            existing_type=message_role_enum,
            type_=sa.String(),
            existing_nullable=False,
        )

    with op.batch_alter_table('documents') as batch_op:
        batch_op.alter_column(
            'status',
            existing_type=document_status_enum,
            type_=sa.String(),
            existing_nullable=True,
        )

    with op.batch_alter_table('users') as batch_op:
        batch_op.alter_column(
            'role',
            existing_type=role_enum,
            type_=sa.String(),
            existing_nullable=True,
        )

    message_role_enum.drop(bind, checkfirst=True)
    document_status_enum.drop(bind, checkfirst=True)
    role_enum.drop(bind, checkfirst=True)

    with op.batch_alter_table('documents') as batch_op:
        batch_op.drop_constraint('fk_documents_collection_id_collections', type_='foreignkey')
        batch_op.drop_column('collection_id')

    op.drop_index(op.f('ix_messages_conversation_id'), table_name='messages')
    op.drop_index(op.f('ix_feedbacks_message_id'), table_name='feedbacks')
    op.drop_index(op.f('ix_conversations_user_id'), table_name='conversations')
    op.drop_index(op.f('ix_chunks_document_id'), table_name='chunks')
    op.drop_column('chunks', 'vector_id')

    op.drop_index(op.f('ix_collections_name'), table_name='collections')
    op.drop_index(op.f('ix_collections_id'), table_name='collections')
    op.drop_table('collections')
