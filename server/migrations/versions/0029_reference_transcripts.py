from alembic import op
import sqlalchemy as sa


revision = '0029'
down_revision = '0028'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('reference_transcripts',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('meeting_id', sa.String(length=32), nullable=False),
    sa.Column('label', sa.String(length=60), nullable=False),
    sa.Column('filename', sa.String(length=200), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('created_by', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.Float(), nullable=False),
    sa.ForeignKeyConstraint(['meeting_id'], ['meetings.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('reference_transcripts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_reference_transcripts_meeting_id'), ['meeting_id'], unique=False)


def downgrade():
    with op.batch_alter_table('reference_transcripts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_reference_transcripts_meeting_id'))
    op.drop_table('reference_transcripts')
