from alembic import op
import sqlalchemy as sa


revision = '0015'
down_revision = '0014'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('backup_targets',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('scope', sa.String(length=20), nullable=False),
    sa.Column('target_id', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('config', sa.JSON(), nullable=False),
    sa.Column('secret', sa.Text(), nullable=False),
    sa.Column('data_kinds', sa.JSON(), nullable=False),
    sa.Column('schedule', sa.String(length=20), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('created_by', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.Float(), nullable=False),
    sa.Column('last_run_at', sa.Float(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('backup_targets', schema=None) as batch_op:
        batch_op.create_index('ix_backup_scope', ['scope', 'target_id'], unique=False)

    op.create_table('backup_runs',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('backup_id', sa.String(length=32), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('trigger', sa.String(length=20), nullable=False),
    sa.Column('object_key', sa.String(length=500), nullable=False),
    sa.Column('size', sa.Integer(), nullable=False),
    sa.Column('error', sa.Text(), nullable=False),
    sa.Column('requested_by', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.Float(), nullable=False),
    sa.Column('finished_at', sa.Float(), nullable=True),
    sa.ForeignKeyConstraint(['backup_id'], ['backup_targets.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('backup_runs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_backup_runs_backup_id'), ['backup_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_backup_runs_status'), ['status'], unique=False)



def downgrade():
    with op.batch_alter_table('backup_runs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_backup_runs_status'))
        batch_op.drop_index(batch_op.f('ix_backup_runs_backup_id'))

    op.drop_table('backup_runs')
    with op.batch_alter_table('backup_targets', schema=None) as batch_op:
        batch_op.drop_index('ix_backup_scope')

    op.drop_table('backup_targets')
