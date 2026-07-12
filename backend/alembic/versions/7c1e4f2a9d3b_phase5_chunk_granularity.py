"""phase5 chunk granularity tracking

Phase 5 non-security remediation: adds nullable `documents.chunk_size` and
`documents.chunk_overlap` (token counts) so the chunking parameters actually
used for a given document are recorded and retrieval-time granularity is
explainable after the fact. Different ingestion entry points historically
used different, unrecorded values (interactive upload / seed_spec.py used
the chunker's defaults of 450/80 tokens; ingest_public_pdfs.py -- which
built the shipped public/ knowledge base -- overrode to 1200/200). Purely
additive, no existing column is touched.

Revision ID: 7c1e4f2a9d3b
Revises: e2a7c4f91b30
Create Date: 2026-07-12 06:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7c1e4f2a9d3b'
down_revision: Union[str, Sequence[str], None] = 'e2a7c4f91b30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('documents', sa.Column('chunk_size', sa.Integer(), nullable=True))
    op.add_column('documents', sa.Column('chunk_overlap', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('documents', 'chunk_overlap')
    op.drop_column('documents', 'chunk_size')
