from alembic import op
import sqlalchemy as sa


revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('positions',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('org_id', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('rank', sa.Integer(), nullable=False),
    sa.Column('access', sa.String(length=20), nullable=False),
    sa.Column('permissions', sa.JSON(), nullable=False),
    sa.Column('account_types', sa.JSON(), nullable=False),
    sa.Column('max_holders', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.Float(), nullable=False),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('org_id', 'name')
    )
    with op.batch_alter_table('positions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_positions_org_id'), ['org_id'], unique=False)

    op.create_table('position_terms',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('org_id', sa.String(length=32), nullable=False),
    sa.Column('position_id', sa.String(length=32), nullable=False),
    sa.Column('user_id', sa.String(length=32), nullable=False),
    sa.Column('starts_at', sa.Float(), nullable=False),
    sa.Column('ends_at', sa.Float(), nullable=True),
    sa.Column('remove_at_end', sa.Boolean(), nullable=False),
    sa.Column('assigned_by', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.Float(), nullable=False),
    sa.Column('ended_at', sa.Float(), nullable=True),
    sa.Column('ended_by', sa.String(length=32), nullable=False),
    sa.Column('end_reason', sa.String(length=40), nullable=False),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['position_id'], ['positions.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('position_terms', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_position_terms_ended_at'), ['ended_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_position_terms_ends_at'), ['ends_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_position_terms_org_id'), ['org_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_position_terms_position_id'), ['position_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_position_terms_user_id'), ['user_id'], unique=False)
        batch_op.create_index('ix_terms_org_user', ['org_id', 'user_id'], unique=False)

    with op.batch_alter_table('meetings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('review_status', sa.String(length=20), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('review_note', sa.Text(), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('review_requested_at', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('reviewed_by', sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column('reviewed_at', sa.Float(), nullable=True))



def downgrade():
    with op.batch_alter_table('meetings', schema=None) as batch_op:
        batch_op.drop_column('reviewed_at')
        batch_op.drop_column('reviewed_by')
        batch_op.drop_column('review_requested_at')
        batch_op.drop_column('review_note')
        batch_op.drop_column('review_status')

    with op.batch_alter_table('position_terms', schema=None) as batch_op:
        batch_op.drop_index('ix_terms_org_user')
        batch_op.drop_index(batch_op.f('ix_position_terms_user_id'))
        batch_op.drop_index(batch_op.f('ix_position_terms_position_id'))
        batch_op.drop_index(batch_op.f('ix_position_terms_org_id'))
        batch_op.drop_index(batch_op.f('ix_position_terms_ends_at'))
        batch_op.drop_index(batch_op.f('ix_position_terms_ended_at'))

    op.drop_table('position_terms')
    with op.batch_alter_table('positions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_positions_org_id'))

    op.drop_table('positions')
