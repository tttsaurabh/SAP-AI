"""phase2 citation table

Phase 2 non-security remediation: adds a new, additive `citations` join
table (`id`, `message_id` FK -> messages.id ON DELETE CASCADE, `chunk_id`
FK -> chunks.id ON DELETE SET NULL nullable, `rank`, `created_at`) so cited
chunks are durably joinable (e.g. "which chunks get cited most"), without
replacing the existing `messages.citations` JSON column, which stays the
fast denormalized read path for the chat UI.

Revision ID: 180c1b30601c
Revises: 9ff13957a9db
Create Date: 2026-07-12 02:54:42.117960

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '180c1b30601c'
down_revision: Union[str, Sequence[str], None] = '9ff13957a9db'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'citations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('message_id', sa.Integer(), nullable=False),
        sa.Column('chunk_id', sa.Integer(), nullable=True),
        sa.Column('rank', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['chunk_id'], ['chunks.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['message_id'], ['messages.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_citations_chunk_id'), 'citations', ['chunk_id'], unique=False)
    op.create_index(op.f('ix_citations_id'), 'citations', ['id'], unique=False)
    op.create_index(op.f('ix_citations_message_id'), 'citations', ['message_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_citations_message_id'), table_name='citations')
    op.drop_index(op.f('ix_citations_id'), table_name='citations')
    op.drop_index(op.f('ix_citations_chunk_id'), table_name='citations')
    op.drop_table('citations')
