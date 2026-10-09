from alembic import op
import sqlalchemy as sa


revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('meeting_translations',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('meeting_id', sa.String(length=32), nullable=False),
    sa.Column('org_id', sa.String(length=32), nullable=False),
    sa.Column('language', sa.String(length=20), nullable=False),
    sa.Column('draft', sa.JSON(), nullable=False),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('source_rev', sa.Integer(), nullable=False),
    sa.Column('ai_label', sa.String(length=200), nullable=False),
    sa.Column('created_by', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.Float(), nullable=False),
    sa.ForeignKeyConstraint(['meeting_id'], ['meetings.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('meeting_id', 'language')
    )
    with op.batch_alter_table('meeting_translations', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_meeting_translations_meeting_id'), ['meeting_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_meeting_translations_org_id'), ['org_id'], unique=False)

    with op.batch_alter_table('meetings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('plain_summary', sa.Text(), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('plain_summary_at', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('plain_summary_rev', sa.Integer(), nullable=False, server_default='0'))



def downgrade():
    with op.batch_alter_table('meetings', schema=None) as batch_op:
        batch_op.drop_column('plain_summary_rev')
        batch_op.drop_column('plain_summary_at')
        batch_op.drop_column('plain_summary')

    with op.batch_alter_table('meeting_translations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_meeting_translations_org_id'))
        batch_op.drop_index(batch_op.f('ix_meeting_translations_meeting_id'))

    op.drop_table('meeting_translations')
