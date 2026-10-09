from alembic import op
import sqlalchemy as sa


revision = '0032'
down_revision = '0031'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'free_ai_runs',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('org_id', sa.String(length=32), nullable=True),
        sa.Column('user_id', sa.String(length=32), nullable=True),
        sa.Column('task', sa.String(length=20), nullable=False),
        sa.Column('ref', sa.String(length=32), nullable=False),
        sa.Column('connection_id', sa.String(length=32), nullable=False),
        sa.Column('model', sa.String(length=200), nullable=False),
        sa.Column('system', sa.Text(), nullable=False),
        sa.Column('material', sa.Text(), nullable=False),
        sa.Column('max_tokens', sa.Integer(), nullable=False),
        sa.Column('prompt_chars', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('phase', sa.String(length=20), nullable=False),
        sa.Column('output_tokens', sa.Integer(), nullable=False),
        sa.Column('result', sa.Text(), nullable=False),
        sa.Column('error', sa.Text(), nullable=False),
        sa.Column('created_at', sa.Float(), nullable=False),
        sa.Column('started_at', sa.Float(), nullable=True),
        sa.Column('first_token_at', sa.Float(), nullable=True),
        sa.Column('updated_at', sa.Float(), nullable=True),
        sa.Column('finished_at', sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('free_ai_runs', schema=None) as batch_op:
        batch_op.create_index('ix_free_ai_runs_status_created', ['status', 'created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_free_ai_runs_org_id'), ['org_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_free_ai_runs_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_free_ai_runs_ref'), ['ref'], unique=False)


def downgrade():
    with op.batch_alter_table('free_ai_runs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_free_ai_runs_ref'))
        batch_op.drop_index(batch_op.f('ix_free_ai_runs_user_id'))
        batch_op.drop_index(batch_op.f('ix_free_ai_runs_org_id'))
        batch_op.drop_index('ix_free_ai_runs_status_created')
    op.drop_table('free_ai_runs')
