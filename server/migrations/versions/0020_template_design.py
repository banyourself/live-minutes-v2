from alembic import op
import sqlalchemy as sa


revision = '0020'
down_revision = '0019'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('templates', schema=None) as batch_op:
        batch_op.add_column(sa.Column('design', sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table('templates', schema=None) as batch_op:
        batch_op.drop_column('design')
