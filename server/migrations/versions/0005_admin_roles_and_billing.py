from alembic import op
import sqlalchemy as sa


revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None

STAFF = {"coast-community-college-district": ["cccd.edu"]}
SCHOOL_STAFF = {"coastline-college": ["coastline.edu"], "golden-west-college": ["gwc.cccd.edu"],
                "orange-coast-college": ["occ.cccd.edu"]}


def seed():
    bind = op.get_bind()
    districts = sa.table("districts", sa.column("id", sa.String), sa.column("slug", sa.String),
                         sa.column("staff_domains", sa.JSON))
    schools = sa.table("schools", sa.column("district_id", sa.String), sa.column("slug", sa.String),
                       sa.column("staff_domains", sa.JSON))
    for slug, domains in STAFF.items():
        district_id = bind.execute(sa.select(districts.c.id).where(districts.c.slug == slug)).scalar()
        if district_id is None:
            continue
        bind.execute(districts.update().where(districts.c.id == district_id).values(staff_domains=domains))
        for school_slug, school_domains in SCHOOL_STAFF.items():
            bind.execute(schools.update().where(schools.c.district_id == district_id, schools.c.slug == school_slug)
                         .values(staff_domains=school_domains))


def upgrade():
    op.create_table('plans',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('description', sa.String(length=500), nullable=False),
    sa.Column('price_cents', sa.Integer(), nullable=False),
    sa.Column('interval', sa.String(length=10), nullable=False),
    sa.Column('seat_limit', sa.Integer(), nullable=True),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.Float(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('admin_roles',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('user_id', sa.String(length=32), nullable=False),
    sa.Column('scope', sa.String(length=20), nullable=False),
    sa.Column('target_id', sa.String(length=32), nullable=False),
    sa.Column('staff_email', sa.String(length=320), nullable=False),
    sa.Column('granted_by', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.Float(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'scope', 'target_id')
    )
    with op.batch_alter_table('admin_roles', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_admin_roles_target_id'), ['target_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_admin_roles_user_id'), ['user_id'], unique=False)

    op.create_table('subscriptions',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('plan_id', sa.String(length=32), nullable=False),
    sa.Column('scope', sa.String(length=20), nullable=False),
    sa.Column('target_id', sa.String(length=32), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('seats', sa.Integer(), nullable=True),
    sa.Column('price_cents', sa.Integer(), nullable=False),
    sa.Column('interval', sa.String(length=10), nullable=False),
    sa.Column('started_at', sa.Float(), nullable=False),
    sa.Column('renews_at', sa.Float(), nullable=True),
    sa.Column('canceled_at', sa.Float(), nullable=True),
    sa.Column('notes', sa.String(length=500), nullable=False),
    sa.Column('created_by', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.Float(), nullable=False),
    sa.Column('updated_at', sa.Float(), nullable=False),
    sa.ForeignKeyConstraint(['plan_id'], ['plans.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('subscriptions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_subscriptions_plan_id'), ['plan_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_subscriptions_target_id'), ['target_id'], unique=False)

    with op.batch_alter_table('districts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('staff_domains', sa.JSON(), nullable=False, server_default='[]'))

    with op.batch_alter_table('schools', schema=None) as batch_op:
        batch_op.add_column(sa.Column('staff_domains', sa.JSON(), nullable=False, server_default='[]'))

    seed()



def downgrade():
    with op.batch_alter_table('schools', schema=None) as batch_op:
        batch_op.drop_column('staff_domains')

    with op.batch_alter_table('districts', schema=None) as batch_op:
        batch_op.drop_column('staff_domains')

    with op.batch_alter_table('subscriptions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_subscriptions_target_id'))
        batch_op.drop_index(batch_op.f('ix_subscriptions_plan_id'))

    op.drop_table('subscriptions')
    with op.batch_alter_table('admin_roles', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_admin_roles_user_id'))
        batch_op.drop_index(batch_op.f('ix_admin_roles_target_id'))

    op.drop_table('admin_roles')
    op.drop_table('plans')
