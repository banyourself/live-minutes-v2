from alembic import op
import sqlalchemy as sa


revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('calendar_feeds',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('user_id', sa.String(length=32), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.Float(), nullable=False),
    sa.Column('last_used_at', sa.Float(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_hash'),
    sa.UniqueConstraint('user_id')
    )
    op.create_table('meeting_series',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('org_id', sa.String(length=32), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('template_id', sa.String(length=32), nullable=True),
    sa.Column('ai_connection_id', sa.String(length=32), nullable=True),
    sa.Column('run_mode', sa.String(length=10), nullable=False),
    sa.Column('notes', sa.Text(), nullable=False),
    sa.Column('frequency', sa.String(length=20), nullable=False),
    sa.Column('interval', sa.Integer(), nullable=False),
    sa.Column('weekdays', sa.JSON(), nullable=False),
    sa.Column('month_week', sa.Integer(), nullable=False),
    sa.Column('month_weekday', sa.Integer(), nullable=False),
    sa.Column('start_date', sa.String(length=10), nullable=False),
    sa.Column('until_date', sa.String(length=10), nullable=False),
    sa.Column('start_time', sa.String(length=5), nullable=False),
    sa.Column('timezone', sa.String(length=64), nullable=False),
    sa.Column('duration_min', sa.Integer(), nullable=False),
    sa.Column('zoom_url', sa.String(length=500), nullable=False),
    sa.Column('location', sa.String(length=200), nullable=False),
    sa.Column('skip_dates', sa.JSON(), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('created_by', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.Float(), nullable=False),
    sa.ForeignKeyConstraint(['ai_connection_id'], ['ai_connections.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['template_id'], ['templates.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('meeting_series', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_meeting_series_org_id'), ['org_id'], unique=False)

    with op.batch_alter_table('meetings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('scheduled_at', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('duration_min', sa.Integer(), nullable=False, server_default='60'))
        batch_op.add_column(sa.Column('timezone', sa.String(length=64), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('zoom_url', sa.String(length=500), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('location', sa.String(length=200), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('series_id', sa.String(length=32), nullable=True))
        batch_op.create_index(batch_op.f('ix_meetings_scheduled_at'), ['scheduled_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_meetings_series_id'), ['series_id'], unique=False)
        batch_op.create_unique_constraint('uq_meetings_series_slot', ['series_id', 'scheduled_at'])
        batch_op.create_foreign_key('fk_meetings_series_id', 'meeting_series', ['series_id'], ['id'], ondelete='SET NULL')



def downgrade():
    with op.batch_alter_table('meetings', schema=None) as batch_op:
        batch_op.drop_constraint('fk_meetings_series_id', type_='foreignkey')
        batch_op.drop_constraint('uq_meetings_series_slot', type_='unique')
        batch_op.drop_index(batch_op.f('ix_meetings_series_id'))
        batch_op.drop_index(batch_op.f('ix_meetings_scheduled_at'))
        batch_op.drop_column('series_id')
        batch_op.drop_column('location')
        batch_op.drop_column('zoom_url')
        batch_op.drop_column('timezone')
        batch_op.drop_column('duration_min')
        batch_op.drop_column('scheduled_at')

    with op.batch_alter_table('meeting_series', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_meeting_series_org_id'))

    op.drop_table('meeting_series')
    op.drop_table('calendar_feeds')
