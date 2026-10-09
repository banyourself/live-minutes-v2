from alembic import op
import sqlalchemy as sa


revision = '0022'
down_revision = '0021'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('oauth_clients',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('redirect_uris', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.Float(), nullable=False),
    sa.Column('last_used_at', sa.Float(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('oauth_codes',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('code_hash', sa.String(length=64), nullable=False),
    sa.Column('client_id', sa.String(length=64), nullable=False),
    sa.Column('user_id', sa.String(length=32), nullable=False),
    sa.Column('redirect_uri', sa.String(length=500), nullable=False),
    sa.Column('challenge', sa.String(length=128), nullable=False),
    sa.Column('can_write', sa.Boolean(), nullable=False),
    sa.Column('expires_at', sa.Float(), nullable=False),
    sa.Column('used_at', sa.Float(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code_hash')
    )
    with op.batch_alter_table('oauth_codes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_oauth_codes_user_id'), ['user_id'], unique=False)

    with op.batch_alter_table('personal_tokens', schema=None) as batch_op:
        batch_op.add_column(sa.Column('client_id', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('refresh_hash', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('refresh_expires_at', sa.Float(), nullable=True))
        batch_op.create_index(batch_op.f('ix_personal_tokens_client_id'), ['client_id'], unique=False)
        batch_op.create_unique_constraint('uq_personal_tokens_refresh_hash', ['refresh_hash'])


def downgrade():
    with op.batch_alter_table('personal_tokens', schema=None) as batch_op:
        batch_op.drop_constraint('uq_personal_tokens_refresh_hash', type_='unique')
        batch_op.drop_index(batch_op.f('ix_personal_tokens_client_id'))
        batch_op.drop_column('refresh_expires_at')
        batch_op.drop_column('refresh_hash')
        batch_op.drop_column('client_id')

    with op.batch_alter_table('oauth_codes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_oauth_codes_user_id'))

    op.drop_table('oauth_codes')
    op.drop_table('oauth_clients')
