from alembic import op
import sqlalchemy as sa


revision = '0013'
down_revision = '0012'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('library_templates',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('owner_scope', sa.String(length=20), nullable=False),
    sa.Column('owner_id', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('filename', sa.String(length=200), nullable=False),
    sa.Column('storage_key', sa.String(length=300), nullable=False),
    sa.Column('mode', sa.String(length=20), nullable=False),
    sa.Column('uses', sa.Integer(), nullable=False),
    sa.Column('created_by', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.Float(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('library_templates', schema=None) as batch_op:
        batch_op.create_index('ix_library_owner', ['owner_scope', 'owner_id'], unique=False)



def downgrade():
    with op.batch_alter_table('library_templates', schema=None) as batch_op:
        batch_op.drop_index('ix_library_owner')

    op.drop_table('library_templates')
