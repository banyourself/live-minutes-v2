from alembic import op
import sqlalchemy as sa


revision = '0028'
down_revision = '0027'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('zoom_connections', schema=None) as batch_op:
        batch_op.add_column(sa.Column('zoom_user_id', sa.String(length=64), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('zoom_account_id', sa.String(length=64), nullable=False, server_default=''))
        batch_op.create_index(batch_op.f('ix_zoom_connections_zoom_user_id'), ['zoom_user_id'], unique=False)

    op.create_table('zoom_pending',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('host_email', sa.String(length=320), nullable=False),
    sa.Column('zoom_user_id', sa.String(length=64), nullable=False),
    sa.Column('zoom_account_id', sa.String(length=64), nullable=False),
    sa.Column('token_enc', sa.Text(), nullable=False),
    sa.Column('created_at', sa.Float(), nullable=False),
    sa.Column('expires_at', sa.Float(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('zoom_pending', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_zoom_pending_zoom_user_id'), ['zoom_user_id'], unique=False)


def downgrade():
    with op.batch_alter_table('zoom_pending', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_zoom_pending_zoom_user_id'))
    op.drop_table('zoom_pending')
    with op.batch_alter_table('zoom_connections', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_zoom_connections_zoom_user_id'))
        batch_op.drop_column('zoom_account_id')
        batch_op.drop_column('zoom_user_id')
