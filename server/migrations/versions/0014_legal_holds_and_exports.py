from alembic import op
import sqlalchemy as sa


revision = '0014'
down_revision = '0013'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('export_jobs',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('scope', sa.String(length=20), nullable=False),
    sa.Column('target_id', sa.String(length=32), nullable=False),
    sa.Column('requested_by', sa.String(length=32), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('storage_key', sa.String(length=300), nullable=False),
    sa.Column('size', sa.Integer(), nullable=False),
    sa.Column('counts', sa.JSON(), nullable=False),
    sa.Column('error', sa.Text(), nullable=False),
    sa.Column('created_at', sa.Float(), nullable=False),
    sa.Column('finished_at', sa.Float(), nullable=True),
    sa.Column('expires_at', sa.Float(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('export_jobs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_export_jobs_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_export_jobs_target_id'), ['target_id'], unique=False)

    op.create_table('legal_holds',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('district_id', sa.String(length=32), nullable=False),
    sa.Column('scope', sa.String(length=20), nullable=False),
    sa.Column('target_id', sa.String(length=32), nullable=False),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('created_by', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.Float(), nullable=False),
    sa.Column('released_at', sa.Float(), nullable=True),
    sa.Column('released_by', sa.String(length=32), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('legal_holds', schema=None) as batch_op:
        batch_op.create_index('ix_holds_target', ['scope', 'target_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_legal_holds_district_id'), ['district_id'], unique=False)



def downgrade():
    with op.batch_alter_table('legal_holds', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_legal_holds_district_id'))
        batch_op.drop_index('ix_holds_target')

    op.drop_table('legal_holds')
    with op.batch_alter_table('export_jobs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_export_jobs_target_id'))
        batch_op.drop_index(batch_op.f('ix_export_jobs_status'))

    op.drop_table('export_jobs')
