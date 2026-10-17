"""Legacy users baseline, matching the original template schema."""
from alembic import op
import sqlalchemy as sa

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('users',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('email', sa.String(120)), sa.Column('nickname', sa.String(50)),
        sa.Column('password_hash', sa.String(255)), sa.Column('full_name', sa.String(100)),
        sa.Column('user_type', sa.String(20)), sa.Column('is_active', sa.Boolean()),
        sa.Column('is_verified', sa.Boolean()), sa.Column('created_at', sa.DateTime()),
        sa.Column('last_login', sa.DateTime()), sa.Column('reset_token', sa.String(100), unique=True),
        sa.Column('reset_token_expires', sa.DateTime()), sa.Column('verification_token', sa.String(100), unique=True))
    op.create_index('ix_users_email', 'users', ['email'], unique=True)
    op.create_index('ix_users_nickname', 'users', ['nickname'], unique=True)


def downgrade():
    op.drop_table('users')
