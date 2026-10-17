"""Persistent local ML jobs. Revision 0004, parent 0003."""
from alembic import op
import sqlalchemy as sa

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('analysis_jobs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('media_id', sa.String(36), sa.ForeignKey('media_records.id', ondelete='CASCADE'), nullable=False),
        sa.Column('camera_profile', sa.String(20), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True)),
        sa.Column('finished_at', sa.DateTime(timezone=True)),
        sa.Column('error', sa.Text()),
        sa.Column('result', sa.JSON()),
        sa.UniqueConstraint('media_id', name='uq_analysis_media'),
        sa.CheckConstraint("status in ('queued','processing','done','failed')", name='analysis_status'),
        sa.CheckConstraint("camera_profile in ('forte_open','full_frame')", name='analysis_camera_profile'))
    op.create_index('ix_analysis_status_created', 'analysis_jobs', ['status', 'created_at'])


def downgrade():
    op.drop_table('analysis_jobs')
