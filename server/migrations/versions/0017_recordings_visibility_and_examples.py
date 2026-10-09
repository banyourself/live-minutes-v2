from alembic import op
import sqlalchemy as sa


revision = '0017'
down_revision = '0016'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('meetings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('visibility', sa.String(length=10), nullable=False, server_default='private'))
        batch_op.add_column(sa.Column('recording_key', sa.String(length=300), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('recording_type', sa.String(length=60), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('recording_name', sa.String(length=200), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('recording_size', sa.BigInteger(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('recording_link', sa.String(length=500), nullable=False, server_default=''))

    with op.batch_alter_table('templates', schema=None) as batch_op:
        batch_op.add_column(sa.Column('purpose', sa.String(length=20), nullable=False, server_default='template'))
        batch_op.add_column(sa.Column('example_text', sa.Text(), nullable=False, server_default=''))



def downgrade():
    with op.batch_alter_table('templates', schema=None) as batch_op:
        batch_op.drop_column('example_text')
        batch_op.drop_column('purpose')

    with op.batch_alter_table('meetings', schema=None) as batch_op:
        batch_op.drop_column('recording_link')
        batch_op.drop_column('recording_size')
        batch_op.drop_column('recording_name')
        batch_op.drop_column('recording_type')
        batch_op.drop_column('recording_key')
        batch_op.drop_column('visibility')

