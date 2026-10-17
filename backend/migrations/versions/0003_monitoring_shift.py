"""Camera health history and event recordings.

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('alert_recordings',
        sa.Column('alert_id', sa.String(36), sa.ForeignKey('camera_alerts.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('media_id', sa.String(36), sa.ForeignKey('media_records.id', ondelete='RESTRICT'), nullable=False))
    op.create_index('ix_alert_recordings_media_id', 'alert_recordings', ['media_id'])
    op.create_table('camera_health_reports',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('camera_id', sa.String(36), sa.ForeignKey('cameras.id', ondelete='CASCADE'), nullable=False),
        sa.Column('external_id', sa.String(120), nullable=False),
        sa.Column('source', sa.String(80), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('checked_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('received_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('camera_id', 'external_id', name='uq_health_camera_external'),
        sa.CheckConstraint("status in ('observing','offline','occluded','frozen','poor_visibility')", name='health_report_status'))
    op.create_index('ix_health_camera_checked', 'camera_health_reports', ['camera_id', 'checked_at'])
    op.create_table('camera_health_intervals',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('camera_id', sa.String(36), sa.ForeignKey('cameras.id', ondelete='CASCADE'), nullable=False),
        sa.Column('kind', sa.String(20), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ended_at', sa.DateTime(timezone=True)),
        sa.CheckConstraint("kind in ('offline','occluded','frozen','poor_visibility','unknown')", name='health_interval_kind'),
        sa.CheckConstraint('ended_at IS NULL OR ended_at >= started_at', name='health_interval_order'))
    op.create_index('ix_health_interval_camera_start', 'camera_health_intervals', ['camera_id', 'started_at'])


def downgrade():
    op.drop_table('camera_health_intervals')
    op.drop_table('camera_health_reports')
    op.drop_table('alert_recordings')
