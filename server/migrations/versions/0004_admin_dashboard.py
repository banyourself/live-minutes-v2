from alembic import op
import sqlalchemy as sa


revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('platform_settings',
    sa.Column('key', sa.String(length=80), nullable=False),
    sa.Column('value', sa.JSON(), nullable=True),
    sa.Column('updated_at', sa.Float(), nullable=False),
    sa.Column('updated_by', sa.String(length=32), nullable=True),
    sa.PrimaryKeyConstraint('key')
    )
    with op.batch_alter_table('user_sessions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('sudo_until', sa.Float(), nullable=True))



def downgrade():
    with op.batch_alter_table('user_sessions', schema=None) as batch_op:
        batch_op.drop_column('sudo_until')

    op.drop_table('platform_settings')
