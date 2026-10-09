from alembic import op
import sqlalchemy as sa


revision = '0019'
down_revision = '0018'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('assistant_actions',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('user_id', sa.String(length=32), nullable=False),
    sa.Column('org_id', sa.String(length=32), nullable=False),
    sa.Column('kind', sa.String(length=40), nullable=False),
    sa.Column('params', sa.JSON(), nullable=False),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('lines', sa.JSON(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('result', sa.Text(), nullable=False),
    sa.Column('link', sa.String(length=300), nullable=False),
    sa.Column('created_at', sa.Float(), nullable=False),
    sa.Column('decided_at', sa.Float(), nullable=True),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('assistant_actions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_assistant_actions_org_id'), ['org_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_assistant_actions_user_id'), ['user_id'], unique=False)


def downgrade():
    with op.batch_alter_table('assistant_actions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_assistant_actions_user_id'))
        batch_op.drop_index(batch_op.f('ix_assistant_actions_org_id'))

    op.drop_table('assistant_actions')
