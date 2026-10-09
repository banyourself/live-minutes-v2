from alembic import op
import sqlalchemy as sa


revision = '0018'
down_revision = '0017'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('personal_tokens',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('user_id', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('can_write', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.Float(), nullable=False),
    sa.Column('expires_at', sa.Float(), nullable=False),
    sa.Column('last_used_at', sa.Float(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_hash')
    )
    with op.batch_alter_table('personal_tokens', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_personal_tokens_user_id'), ['user_id'], unique=False)



def downgrade():
    with op.batch_alter_table('personal_tokens', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_personal_tokens_user_id'))

    op.drop_table('personal_tokens')
