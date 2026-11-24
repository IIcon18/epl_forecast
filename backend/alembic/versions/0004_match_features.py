"""match_features

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-04 18:34:48.503620

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0004'
down_revision: Union[str, Sequence[str], None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('match_features',
    sa.Column('match_id', sa.Integer(), nullable=False),
    sa.Column('feature_version', sa.String(length=16), nullable=False),
    sa.Column('features', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('built_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['match_id'], ['matches.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('match_id')
    )


def downgrade() -> None:
    op.drop_table('match_features')
