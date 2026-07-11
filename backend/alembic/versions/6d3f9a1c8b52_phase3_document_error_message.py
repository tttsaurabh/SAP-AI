"""phase3 document error_message

Phase 3 non-security remediation: adds a nullable `documents.error_message`
column so background-ingestion failures (see `process_document_ingestion`
in `backend/app/api/documents.py`, run via FastAPI `BackgroundTasks` after
the upload endpoint returns) are debuggable instead of the document
silently sitting at `status=failed` with no explanation. Purely additive --
no existing column is touched.

Revision ID: 6d3f9a1c8b52
Revises: 180c1b30601c
Create Date: 2026-07-12 05:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6d3f9a1c8b52'
down_revision: Union[str, Sequence[str], None] = '180c1b30601c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('documents', sa.Column('error_message', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('documents', 'error_message')
