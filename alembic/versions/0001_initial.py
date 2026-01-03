from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'scan_runs',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('universe', sa.String(length=255), nullable=False),
        sa.Column('symbols_scanned', sa.JSON(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('errors_count', sa.Integer(), nullable=False, server_default='0'),
    )

    op.create_table(
        'alerts',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('symbol', sa.String(length=16), nullable=False),
        sa.Column('direction', sa.String(length=8), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('expected_window', sa.String(length=16), nullable=False),
        sa.Column('entry', sa.Float(), nullable=False),
        sa.Column('stop', sa.Float(), nullable=False),
        sa.Column('t1', sa.Float(), nullable=False),
        sa.Column('t2', sa.Float(), nullable=False),
        sa.Column('box_high', sa.Float(), nullable=False),
        sa.Column('box_low', sa.Float(), nullable=False),
        sa.Column('range_pct', sa.Float(), nullable=False),
        sa.Column('atr_ratio', sa.Float(), nullable=False),
        sa.Column('vol_ratio', sa.Float(), nullable=False),
        sa.Column('break_vol_mult', sa.Float(), nullable=False),
        sa.Column('extension_pct', sa.Float(), nullable=False),
        sa.Column('market_bias', sa.String(length=16), nullable=True),
        sa.Column('vwap_ok', sa.Boolean(), nullable=False, server_default=sa.sql.expression.false()),
        sa.Column('alert_text_short', sa.Text(), nullable=False),
        sa.Column('alert_text_medium', sa.Text(), nullable=False),
        sa.Column('alert_text_deep', sa.Text(), nullable=False),
        sa.Column('telegram_status_code', sa.Integer(), nullable=True),
        sa.Column('telegram_response', sa.Text(), nullable=True),
    )

    op.create_table(
        'option_candidates',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('alert_id', sa.Integer, sa.ForeignKey('alerts.id', ondelete='CASCADE')), 
        sa.Column('tier', sa.String(length=32), nullable=False),
        sa.Column('contract_symbol', sa.String(length=64), nullable=False),
        sa.Column('expiry', sa.String(length=16), nullable=False),
        sa.Column('strike', sa.Float(), nullable=False),
        sa.Column('call_put', sa.String(length=4), nullable=False),
        sa.Column('bid', sa.Float(), nullable=False),
        sa.Column('ask', sa.Float(), nullable=False),
        sa.Column('mid', sa.Float(), nullable=False),
        sa.Column('spread_pct', sa.Float(), nullable=False),
        sa.Column('volume', sa.Integer(), nullable=False),
        sa.Column('oi', sa.Integer(), nullable=False),
        sa.Column('delta', sa.Float(), nullable=True),
        sa.Column('gamma', sa.Float(), nullable=True),
        sa.Column('theta', sa.Float(), nullable=True),
        sa.Column('iv', sa.Float(), nullable=True),
        sa.Column('iv_percentile', sa.Float(), nullable=True),
        sa.Column('rationale', sa.Text(), nullable=False),
        sa.Column('exit_plan', sa.Text(), nullable=False),
    )

    op.create_table(
        'grades',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('alert_id', sa.Integer, sa.ForeignKey('alerts.id', ondelete='CASCADE')), 
        sa.Column('graded_at', sa.DateTime(), nullable=False),
        sa.Column('hit_t1', sa.Boolean(), nullable=True),
        sa.Column('hit_t2', sa.Boolean(), nullable=True),
        sa.Column('mfe_stock_pct', sa.Float(), nullable=True),
        sa.Column('mae_stock_pct', sa.Float(), nullable=True),
        sa.Column('time_to_t1_min', sa.Integer(), nullable=True),
        sa.Column('time_to_t2_min', sa.Integer(), nullable=True),
        sa.Column('max_option_gain_pct', sa.Float(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
    )


def downgrade():
    op.drop_table('grades')
    op.drop_table('option_candidates')
    op.drop_table('alerts')
    op.drop_table('scan_runs')
