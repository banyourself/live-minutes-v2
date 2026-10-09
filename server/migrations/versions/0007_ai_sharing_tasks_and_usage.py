from alembic import op
import sqlalchemy as sa


revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('ai_prices',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('provider', sa.String(length=40), nullable=False),
    sa.Column('model', sa.String(length=200), nullable=False),
    sa.Column('input_per_mtok_cents', sa.Float(), nullable=False),
    sa.Column('output_per_mtok_cents', sa.Float(), nullable=False),
    sa.Column('updated_at', sa.Float(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('provider', 'model')
    )
    op.create_table('ai_usage',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('org_id', sa.String(length=32), nullable=True),
    sa.Column('user_id', sa.String(length=32), nullable=True),
    sa.Column('connection_id', sa.String(length=32), nullable=True),
    sa.Column('owner_scope', sa.String(length=20), nullable=False),
    sa.Column('task', sa.String(length=20), nullable=False),
    sa.Column('provider', sa.String(length=40), nullable=False),
    sa.Column('model', sa.String(length=200), nullable=False),
    sa.Column('input_tokens', sa.Integer(), nullable=False),
    sa.Column('output_tokens', sa.Integer(), nullable=False),
    sa.Column('cost_cents', sa.Float(), nullable=False),
    sa.Column('priced', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.Float(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('ai_usage', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ai_usage_created_at'), ['created_at'], unique=False)
        batch_op.create_index('ix_ai_usage_org_time', ['org_id', 'created_at'], unique=False)

    op.create_table('ai_shares',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('connection_id', sa.String(length=32), nullable=False),
    sa.Column('target_scope', sa.String(length=20), nullable=False),
    sa.Column('target_id', sa.String(length=32), nullable=False),
    sa.Column('created_by', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.Float(), nullable=False),
    sa.ForeignKeyConstraint(['connection_id'], ['ai_connections.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('connection_id', 'target_scope', 'target_id')
    )
    with op.batch_alter_table('ai_shares', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ai_shares_connection_id'), ['connection_id'], unique=False)

    op.create_table('ai_task_settings',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('scope', sa.String(length=20), nullable=False),
    sa.Column('scope_id', sa.String(length=32), nullable=False),
    sa.Column('task', sa.String(length=20), nullable=False),
    sa.Column('connection_id', sa.String(length=32), nullable=True),
    sa.Column('prompt', sa.Text(), nullable=True),
    sa.Column('updated_by', sa.String(length=32), nullable=False),
    sa.Column('updated_at', sa.Float(), nullable=False),
    sa.ForeignKeyConstraint(['connection_id'], ['ai_connections.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('scope', 'scope_id', 'task')
    )
    with op.batch_alter_table('ai_connections', schema=None) as batch_op:
        batch_op.add_column(sa.Column('owner_scope', sa.String(length=20), nullable=False, server_default='org'))
        batch_op.add_column(sa.Column('owner_id', sa.String(length=32), nullable=False, server_default=''))
        batch_op.alter_column('org_id',
               existing_type=sa.VARCHAR(length=32),
               nullable=True)
        batch_op.create_index(batch_op.f('ix_ai_connections_owner_id'), ['owner_id'], unique=False)

    op.execute("UPDATE ai_connections SET owner_scope = 'org', owner_id = org_id WHERE owner_id = '' AND org_id IS NOT NULL")

    with op.batch_alter_table('districts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('settings', sa.JSON(), nullable=False, server_default='{}'))

    with op.batch_alter_table('schools', schema=None) as batch_op:
        batch_op.add_column(sa.Column('settings', sa.JSON(), nullable=False, server_default='{}'))



def downgrade():
    with op.batch_alter_table('schools', schema=None) as batch_op:
        batch_op.drop_column('settings')

    with op.batch_alter_table('districts', schema=None) as batch_op:
        batch_op.drop_column('settings')

    with op.batch_alter_table('ai_connections', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ai_connections_owner_id'))
        batch_op.alter_column('org_id',
               existing_type=sa.VARCHAR(length=32),
               nullable=False)
        batch_op.drop_column('owner_id')
        batch_op.drop_column('owner_scope')

    op.drop_table('ai_task_settings')
    with op.batch_alter_table('ai_shares', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ai_shares_connection_id'))

    op.drop_table('ai_shares')
    with op.batch_alter_table('ai_usage', schema=None) as batch_op:
        batch_op.drop_index('ix_ai_usage_org_time')
        batch_op.drop_index(batch_op.f('ix_ai_usage_created_at'))

    op.drop_table('ai_usage')
    op.drop_table('ai_prices')
