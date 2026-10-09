from alembic import op
import sqlalchemy as sa


revision = '0027'
down_revision = '0026'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('personal_tokens') as batch:
        batch.add_column(sa.Column('refresh_prev_hash', sa.String(64), nullable=True))
        batch.create_index('ix_personal_tokens_refresh_prev_hash', ['refresh_prev_hash'])


def downgrade():
    with op.batch_alter_table('personal_tokens') as batch:
        batch.drop_index('ix_personal_tokens_refresh_prev_hash')
        batch.drop_column('refresh_prev_hash')
