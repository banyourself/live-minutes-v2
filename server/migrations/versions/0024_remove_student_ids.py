from alembic import op
import sqlalchemy as sa


revision = '0024'
down_revision = '0023'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_student_id'))
        batch_op.drop_column('student_id')
    op.execute("UPDATE meetings SET visibility = 'private' WHERE visibility <> 'private'")


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('student_id', sa.String(length=20), nullable=False, server_default=''))
        batch_op.create_index(batch_op.f('ix_users_student_id'), ['student_id'], unique=False)
