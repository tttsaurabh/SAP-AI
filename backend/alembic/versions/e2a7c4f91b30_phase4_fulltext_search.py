"""phase4 full-text search tsvector + GIN index

Phase 4 non-security remediation: replaces the `Chunk.text.ilike('%word%')`
full-table-scan "keyword search" leg of `RAGEngine.hybrid_search` with real
Postgres full-text search. Adds a generated `chunks.text_search` `tsvector`
column (`GENERATED ALWAYS AS (to_tsvector('english', text)) STORED`) plus a
GIN index over it.

**Postgres-specific migration.** `GENERATED ALWAYS AS ... STORED` generated
columns and `tsvector`/GIN indexes are a Postgres feature with no SQLite
equivalent (Alembic also can't autogenerate `GENERATED ALWAYS AS` columns,
per the plan for this phase -- this migration is hand-written). `upgrade()`
and `downgrade()` both check `op.get_bind().dialect.name` and no-op on any
non-Postgres dialect instead of raising, so the migration chain itself
doesn't break for non-Postgres callers -- but real full-text search
(`RAGEngine._db_keyword_search`) will not function against a non-Postgres
database after this migration lands, since the column it queries simply
won't exist there.

**Verification limitation**: unlike every prior phase (0-3), this migration
could NOT be round-trip-verified (`upgrade head` / `downgrade -1` /
re-`upgrade head`) against a scratch SQLite DB, because there is nothing to
verify on SQLite -- both directions are no-ops there by design. No live
Postgres instance was available in this sandbox either, so this migration's
actual SQL has been reviewed by hand but not executed against a real
database. Re-verify against a real Postgres instance before relying on this
in production.

Revision ID: e2a7c4f91b30
Revises: 6d3f9a1c8b52
Create Date: 2026-07-12 06:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e2a7c4f91b30'
down_revision: Union[str, Sequence[str], None] = '6d3f9a1c8b52'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    if bind.dialect.name != 'postgresql':
        # No SQLite/other-dialect equivalent for generated tsvector columns
        # + GIN indexes -- see module docstring. No-op rather than raise so
        # the migration chain doesn't break for non-Postgres callers.
        return

    op.execute(
        "ALTER TABLE chunks ADD COLUMN text_search tsvector "
        "GENERATED ALWAYS AS (to_tsvector('english', text)) STORED"
    )
    op.execute(
        "CREATE INDEX idx_chunks_text_search ON chunks USING GIN(text_search)"
    )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    if bind.dialect.name != 'postgresql':
        return

    op.execute("DROP INDEX IF EXISTS idx_chunks_text_search")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS text_search")
