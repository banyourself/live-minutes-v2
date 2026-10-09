from alembic import op
import sqlalchemy as sa


revision = '0031'
down_revision = '0030'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('meetings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('zoom_recording_uuid', sa.String(length=200), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('zoom_text_source', sa.String(length=20), nullable=False, server_default=''))
        batch_op.create_index(batch_op.f('ix_meetings_zoom_recording_uuid'), ['zoom_recording_uuid'], unique=False)


def downgrade():
    with op.batch_alter_table('meetings', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_meetings_zoom_recording_uuid'))
        batch_op.drop_column('zoom_text_source')
        batch_op.drop_column('zoom_recording_uuid')
