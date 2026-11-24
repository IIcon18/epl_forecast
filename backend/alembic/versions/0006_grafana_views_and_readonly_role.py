import os

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

PRODUCTION = "(SELECT id FROM model_versions WHERE status = 'production' ORDER BY id DESC LIMIT 1)"


def upgrade() -> None:
    op.execute(f"""
        CREATE VIEW v_match_forecast AS
        SELECT m.id AS match_id, m.season, m.match_date, m.status, m.stadium, m.attendance_status,
               m.home_team_id, th.name AS home_team, m.away_team_id, ta.name AS away_team,
               CASE WHEN m.attendance_status = 'ok' THEN m.attendance END AS attendance_trusted,
               m.attendance, p.predicted, p.baseline AS naive, p.kind AS prediction_kind
        FROM matches m
        JOIN teams th ON th.id = m.home_team_id
        JOIN teams ta ON ta.id = m.away_team_id
        LEFT JOIN predictions p ON p.match_id = m.id AND p.model_version_id = {PRODUCTION}
    """)
    op.execute(f"""
        CREATE VIEW v_model_quality AS
        SELECT m.season, count(*) AS matches,
               avg(abs(p.predicted - m.attendance)) AS mae_model,
               avg(abs(p.baseline - m.attendance)) AS mae_naive
        FROM matches m
        JOIN predictions p ON p.match_id = m.id
        WHERE p.model_version_id = {PRODUCTION} AND p.kind = 'backtest'
          AND m.attendance_status = 'ok' AND p.baseline IS NOT NULL
        GROUP BY m.season
    """)

    password = os.environ.get("GRAFANA_DB_PASSWORD", "grafana")
    conn = op.get_bind()
    conn.execute(sa.text("SELECT set_config('app.grafana_password', :pwd, false)"), {"pwd": password})
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'grafana_ro') THEN
                EXECUTE format('CREATE ROLE grafana_ro LOGIN PASSWORD %L', current_setting('app.grafana_password'));
            ELSE
                EXECUTE format('ALTER ROLE grafana_ro PASSWORD %L', current_setting('app.grafana_password'));
            END IF;
        END $$
    """)
    op.execute("GRANT CONNECT ON DATABASE %s TO grafana_ro" % conn.engine.url.database)
    op.execute("GRANT USAGE ON SCHEMA public TO grafana_ro")
    op.execute("GRANT SELECT ON ALL TABLES IN SCHEMA public TO grafana_ro")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO grafana_ro")


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_model_quality")
    op.execute("DROP VIEW IF EXISTS v_match_forecast")
