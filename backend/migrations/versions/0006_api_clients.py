"""Anonymous API clients and exclusive media ownership."""
from alembic import op
import sqlalchemy as sa

revision = '0006'
down_revision = '0005'
branch_labels = depends_on = None


def upgrade():
    op.create_table('api_clients',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('key_hash', sa.String(64), nullable=False, unique=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True)))
    with op.batch_alter_table('media_records') as batch:
        batch.alter_column('owner_id', existing_type=sa.Integer(), nullable=True)
        batch.add_column(sa.Column('api_client_id', sa.String(36)))
        batch.create_foreign_key('fk_media_api_client', 'api_clients', ['api_client_id'], ['id'], ondelete='RESTRICT')
        batch.create_index('ix_media_records_api_client_id', ['api_client_id'])
        batch.create_check_constraint('media_exactly_one_owner',
            '(owner_id IS NOT NULL AND api_client_id IS NULL) OR (owner_id IS NULL AND api_client_id IS NOT NULL)')


def downgrade():
    if op.get_bind().execute(sa.text('SELECT COUNT(*) FROM media_records WHERE api_client_id IS NOT NULL')).scalar():
        raise RuntimeError('Cannot downgrade while API-owned media exists; export or explicitly remove it first.')
    with op.batch_alter_table('media_records') as batch:
        batch.drop_constraint('media_exactly_one_owner', type_='check')
        batch.drop_index('ix_media_records_api_client_id')
        batch.drop_constraint('fk_media_api_client', type_='foreignkey')
        batch.drop_column('api_client_id')
        batch.alter_column('owner_id', existing_type=sa.Integer(), nullable=False)
    op.drop_table('api_clients')
