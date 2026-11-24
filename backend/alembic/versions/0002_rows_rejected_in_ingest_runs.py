"""rows_rejected in ingest_runs

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-04 17:56:07.817424

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0002'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('ingest_runs', sa.Column('rows_rejected', sa.Integer(), server_default='0', nullable=False))


def downgrade() -> None:
    op.drop_column('ingest_runs', 'rows_rejected')
