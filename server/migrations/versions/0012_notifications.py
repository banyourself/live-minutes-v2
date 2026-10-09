from alembic import op
import sqlalchemy as sa


revision = '0012'
down_revision = '0011'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('notification_prefs',
    sa.Column('user_id', sa.String(length=32), nullable=False),
    sa.Column('email', sa.JSON(), nullable=False),
    sa.Column('digest_weekday', sa.Integer(), nullable=False),
    sa.Column('last_digest_at', sa.Float(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id')
    )
    op.create_table('notifications',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('user_id', sa.String(length=32), nullable=False),
    sa.Column('org_id', sa.String(length=32), nullable=True),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('link', sa.String(length=300), nullable=False),
    sa.Column('created_at', sa.Float(), nullable=False),
    sa.Column('read_at', sa.Float(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.create_index('ix_notifications_user_time', ['user_id', 'created_at'], unique=False)

    with op.batch_alter_table('meetings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('reminded_at', sa.Float(), nullable=True))



def downgrade():
    with op.batch_alter_table('meetings', schema=None) as batch_op:
        batch_op.drop_column('reminded_at')

    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.drop_index('ix_notifications_user_time')

    op.drop_table('notifications')
    op.drop_table('notification_prefs')
