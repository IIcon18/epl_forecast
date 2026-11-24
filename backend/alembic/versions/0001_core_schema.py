"""core schema

Revision ID: 0001
Revises: 
Create Date: 2026-11-04 17:42:57.312531

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('ingest_runs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('source', sa.String(length=32), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('status', sa.String(length=16), server_default='running', nullable=False),
    sa.Column('rows_fetched', sa.Integer(), server_default='0', nullable=False),
    sa.Column('rows_inserted', sa.Integer(), server_default='0', nullable=False),
    sa.Column('rows_updated', sa.Integer(), server_default='0', nullable=False),
    sa.Column('rows_skipped', sa.Integer(), server_default='0', nullable=False),
    sa.Column('watermark', sa.DateTime(timezone=True), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('params', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_ingest_runs_source_started', 'ingest_runs', ['source', 'started_at'], unique=False)
    op.create_table('news_articles',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('source', sa.String(length=32), nullable=False),
    sa.Column('guid', sa.Text(), nullable=False),
    sa.Column('title', sa.Text(), nullable=False),
    sa.Column('summary', sa.Text(), nullable=True),
    sa.Column('url', sa.Text(), nullable=False),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('fetched_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('source', 'guid', name='uq_news_source_guid')
    )
    op.create_index('ix_news_published_at', 'news_articles', ['published_at'], unique=False)
    op.create_table('teams',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('football_data_id', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('football_data_id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('dq_checks',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('run_id', sa.Integer(), nullable=True),
    sa.Column('table_name', sa.String(length=64), nullable=False),
    sa.Column('check_name', sa.String(length=100), nullable=False),
    sa.Column('severity', sa.String(length=8), nullable=False),
    sa.Column('passed', sa.Boolean(), nullable=False),
    sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('checked_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['run_id'], ['ingest_runs.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_dq_checks_run_id'), 'dq_checks', ['run_id'], unique=False)
    op.create_table('matches',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('season', sa.SmallInteger(), nullable=False),
    sa.Column('match_date', sa.Date(), nullable=False),
    sa.Column('kickoff_utc', sa.DateTime(timezone=True), nullable=True),
    sa.Column('matchday', sa.SmallInteger(), nullable=True),
    sa.Column('home_team_id', sa.Integer(), nullable=False),
    sa.Column('away_team_id', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=16), server_default='FINISHED', nullable=False),
    sa.Column('home_goals', sa.SmallInteger(), nullable=True),
    sa.Column('away_goals', sa.SmallInteger(), nullable=True),
    sa.Column('attendance', sa.Integer(), nullable=True),
    sa.Column('stadium', sa.String(length=100), nullable=True),
    sa.Column('referee', sa.String(length=100), nullable=True),
    sa.Column('is_derby', sa.Boolean(), nullable=True),
    sa.Column('football_data_id', sa.Integer(), nullable=True),
    sa.Column('source', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('attendance IS NULL OR attendance >= 0', name='ck_matches_attendance_nonneg'),
    sa.CheckConstraint('home_team_id <> away_team_id', name='ck_matches_distinct_teams'),
    sa.ForeignKeyConstraint(['away_team_id'], ['teams.id'], ),
    sa.ForeignKeyConstraint(['home_team_id'], ['teams.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('football_data_id'),
    sa.UniqueConstraint('season', 'home_team_id', 'away_team_id', name='uq_matches_season_home_away')
    )
    op.create_index('ix_matches_home_team_date', 'matches', ['home_team_id', 'match_date'], unique=False)
    op.create_index('ix_matches_match_date', 'matches', ['match_date'], unique=False)
    op.create_table('news_article_teams',
    sa.Column('article_id', sa.Integer(), nullable=False),
    sa.Column('team_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['article_id'], ['news_articles.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('article_id', 'team_id')
    )
    op.create_index(op.f('ix_news_article_teams_team_id'), 'news_article_teams', ['team_id'], unique=False)
    op.create_table('team_aliases',
    sa.Column('alias', sa.String(length=100), nullable=False),
    sa.Column('team_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('alias')
    )
    op.create_index(op.f('ix_team_aliases_team_id'), 'team_aliases', ['team_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_team_aliases_team_id'), table_name='team_aliases')
    op.drop_table('team_aliases')
    op.drop_index(op.f('ix_news_article_teams_team_id'), table_name='news_article_teams')
    op.drop_table('news_article_teams')
    op.drop_index('ix_matches_match_date', table_name='matches')
    op.drop_index('ix_matches_home_team_date', table_name='matches')
    op.drop_table('matches')
    op.drop_index(op.f('ix_dq_checks_run_id'), table_name='dq_checks')
    op.drop_table('dq_checks')
    op.drop_table('teams')
    op.drop_index('ix_news_published_at', table_name='news_articles')
    op.drop_table('news_articles')
    op.drop_index('ix_ingest_runs_source_started', table_name='ingest_runs')
    op.drop_table('ingest_runs')
