from alembic import op
import sqlalchemy as sa


revision = '0021'
down_revision = '0020'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('draft_revisions',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('meeting_id', sa.String(length=32), nullable=False),
    sa.Column('rev', sa.Integer(), nullable=False),
    sa.Column('draft', sa.JSON(), nullable=False),
    sa.Column('source', sa.String(length=20), nullable=False),
    sa.Column('user_id', sa.String(length=32), nullable=True),
    sa.Column('label', sa.String(length=200), nullable=False),
    sa.Column('created_at', sa.Float(), nullable=False),
    sa.ForeignKeyConstraint(['meeting_id'], ['meetings.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('draft_revisions', schema=None) as batch_op:
        batch_op.create_index('ix_draft_revisions_meeting_time', ['meeting_id', 'created_at'], unique=False)


def downgrade():
    with op.batch_alter_table('draft_revisions', schema=None) as batch_op:
        batch_op.drop_index('ix_draft_revisions_meeting_time')

    op.drop_table('draft_revisions')
