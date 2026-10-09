from alembic import op
import sqlalchemy as sa


revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('school_requests', schema=None) as batch_op:
        batch_op.add_column(sa.Column('kind', sa.String(length=20), nullable=False, server_default='school'))
        batch_op.add_column(sa.Column('school_id', sa.String(length=32), nullable=True))
        batch_op.create_foreign_key('fk_school_requests_school_id', 'schools', ['school_id'], ['id'], ondelete='SET NULL')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('account_type', sa.String(length=20), nullable=False, server_default=''))

    op.execute("UPDATE school_requests SET kind = 'district' WHERE district_id IS NULL")



def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('account_type')

    with op.batch_alter_table('school_requests', schema=None) as batch_op:
        batch_op.drop_constraint('fk_school_requests_school_id', type_='foreignkey')
        batch_op.drop_column('school_id')
        batch_op.drop_column('kind')

