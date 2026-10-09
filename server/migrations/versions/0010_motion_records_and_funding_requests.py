from alembic import op
import sqlalchemy as sa


revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('motion_records',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('org_id', sa.String(length=32), nullable=False),
    sa.Column('meeting_id', sa.String(length=32), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('t', sa.Float(), nullable=True),
    sa.Column('under', sa.String(length=300), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('mover', sa.String(length=200), nullable=False),
    sa.Column('seconder', sa.String(length=200), nullable=False),
    sa.Column('method', sa.String(length=20), nullable=False),
    sa.Column('result', sa.String(length=20), nullable=False),
    sa.Column('votes', sa.JSON(), nullable=False),
    sa.Column('updated_by', sa.String(length=32), nullable=False),
    sa.Column('updated_at', sa.Float(), nullable=False),
    sa.ForeignKeyConstraint(['meeting_id'], ['meetings.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('motion_records', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_motion_records_meeting_id'), ['meeting_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_motion_records_org_id'), ['org_id'], unique=False)

    op.create_table('funding_requests',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('org_id', sa.String(length=32), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('requester', sa.String(length=200), nullable=False),
    sa.Column('amount_cents', sa.Integer(), nullable=False),
    sa.Column('approved_cents', sa.Integer(), nullable=True),
    sa.Column('purpose', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('motion_id', sa.String(length=32), nullable=True),
    sa.Column('notes', sa.Text(), nullable=False),
    sa.Column('created_by', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.Float(), nullable=False),
    sa.Column('updated_at', sa.Float(), nullable=False),
    sa.Column('decided_at', sa.Float(), nullable=True),
    sa.ForeignKeyConstraint(['motion_id'], ['motion_records.id'], name='fk_funding_motion', ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('funding_requests', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_funding_requests_org_id'), ['org_id'], unique=False)



def downgrade():
    with op.batch_alter_table('funding_requests', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_funding_requests_org_id'))

    op.drop_table('funding_requests')
    with op.batch_alter_table('motion_records', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_motion_records_org_id'))
        batch_op.drop_index(batch_op.f('ix_motion_records_meeting_id'))

    op.drop_table('motion_records')
