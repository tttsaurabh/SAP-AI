"""phase8 parent-child chunk hierarchy

Phase 8b non-security remediation: adds the schema needed for parent-child
("small-to-big") chunking -- small child chunks are embedded/indexed for
precise retrieval matching, while their larger parent chunk (unindexed,
SQL-only) supplies full context to the LLM at generation time. See the
Phase 8 CLAUDE.md Work Log entry.

Purely additive:
- `chunks.parent_id`: nullable self-FK -> chunks.id, ON DELETE CASCADE
  (deleting a parent cascades to its children), indexed.
- `chunks.is_parent`: boolean, server_default false, indexed -- lets
  RAGEngine._db_keyword_search filter parents out of the FTS leg without a
  join.
- `documents.parent_chunk_size`: nullable integer, mirrors the existing
  `chunk_size`/`chunk_overlap` bookkeeping columns from Phase 5, but for the
  parent-level token target. Child-level size/overlap continue to reuse the
  existing `chunk_size`/`chunk_overlap` columns.

Existing chunk rows are untouched: they get `is_parent=false` (the column
default) and `parent_id=NULL`, which is exactly the "flat legacy chunk"
shape RAGEngine's small-to-big expansion falls back to (use the chunk's own
text when it has no parent) -- no data backfill needed for old rows to keep
working.

Revision ID: 3f8a2c6d9e14
Revises: 7c1e4f2a9d3b
Create Date: 2026-07-12 08:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3f8a2c6d9e14'
down_revision: Union[str, Sequence[str], None] = '7c1e4f2a9d3b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('documents', sa.Column('parent_chunk_size', sa.Integer(), nullable=True))

    op.add_column('chunks', sa.Column('parent_id', sa.Integer(), nullable=True))
    op.add_column('chunks', sa.Column('is_parent', sa.Boolean(), server_default=sa.text('false'), nullable=True))

    # batch_alter_table so the FK/index also work on SQLite (can't ALTER
    # ADD CONSTRAINT directly), matching the pattern used in the Phase 1
    # enum migration for the same cross-dialect reason.
    with op.batch_alter_table('chunks') as batch_op:
        batch_op.create_index('ix_chunks_parent_id', ['parent_id'])
        batch_op.create_index('ix_chunks_is_parent', ['is_parent'])
        batch_op.create_foreign_key(
            'fk_chunks_parent_id_chunks',
            'chunks',
            local_cols=['parent_id'],
            remote_cols=['id'],
            ondelete='CASCADE',
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('chunks') as batch_op:
        batch_op.drop_constraint('fk_chunks_parent_id_chunks', type_='foreignkey')
        batch_op.drop_index('ix_chunks_is_parent')
        batch_op.drop_index('ix_chunks_parent_id')

    op.drop_column('chunks', 'is_parent')
    op.drop_column('chunks', 'parent_id')
    op.drop_column('documents', 'parent_chunk_size')
