from alembic import op
import sqlalchemy as sa


revision = '0030'
down_revision = '0029'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('totp_secret_enc', sa.Text(), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('totp_pending_enc', sa.Text(), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('totp_enabled_at', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('totp_last_step', sa.BigInteger(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('recovery_codes', sa.JSON(), nullable=False, server_default='[]'))


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('recovery_codes')
        batch_op.drop_column('totp_last_step')
        batch_op.drop_column('totp_enabled_at')
        batch_op.drop_column('totp_pending_enc')
        batch_op.drop_column('totp_secret_enc')
