"""Scoped access, refresh rotation, throttling and administrator MFA."""
from alembic import op
import sqlalchemy as sa
revision = '0005'
down_revision = '0004'
branch_labels = depends_on = None


def upgrade():
    op.create_table('branches', sa.Column('id', sa.String(36), primary_key=True), sa.Column('name', sa.String(120), nullable=False))
    op.create_table('camera_scopes',
        sa.Column('camera_id', sa.String(36), sa.ForeignKey('cameras.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('branch_id', sa.String(36), sa.ForeignKey('branches.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('is_demo', sa.Boolean(), nullable=False))
    op.create_table('branch_access',
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('branch_id', sa.String(36), sa.ForeignKey('branches.id', ondelete='CASCADE'), primary_key=True))
    op.create_table('camera_access',
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('camera_id', sa.String(36), sa.ForeignKey('cameras.id', ondelete='CASCADE'), primary_key=True))
    op.create_table('session_security',
        sa.Column('session_id', sa.String(36), sa.ForeignKey('auth_sessions.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('refresh_jti', sa.String(36), nullable=False),
        sa.Column('mfa_verified', sa.Boolean(), nullable=False))
    op.create_table('login_buckets', sa.Column('key', sa.String(64), primary_key=True),
        sa.Column('window', sa.BigInteger(), nullable=False), sa.Column('count', sa.Integer(), nullable=False))
    op.create_table('user_mfa',
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('secret', sa.Text(), nullable=False), sa.Column('last_step', sa.BigInteger(), nullable=False))
    # Existing sessions predate rotation/MFA; require a fresh login after upgrade.
    op.execute(sa.text('UPDATE auth_sessions SET revoked_at = CURRENT_TIMESTAMP WHERE revoked_at IS NULL'))


def downgrade():
    for name in ('user_mfa', 'login_buckets', 'session_security', 'camera_access', 'branch_access', 'camera_scopes', 'branches'):
        op.drop_table(name)
