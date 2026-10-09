import time
import uuid

from alembic import op
import sqlalchemy as sa


revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None

SEED = ("Coast Community College District", "coast-community-college-district", [
    ("Coastline College", "coastline-college", ["student.cccd.edu", "coastline.edu"]),
    ("Golden West College", "golden-west-college", ["student.cccd.edu", "gwc.cccd.edu"]),
    ("Orange Coast College", "orange-coast-college", ["student.cccd.edu", "occ.cccd.edu"]),
])


def seed():
    bind = op.get_bind()
    districts = sa.table("districts", sa.column("id", sa.String), sa.column("name", sa.String),
                         sa.column("slug", sa.String), sa.column("allowed_domains", sa.JSON),
                         sa.column("created_at", sa.Float))
    schools = sa.table("schools", sa.column("id", sa.String), sa.column("district_id", sa.String),
                       sa.column("name", sa.String), sa.column("slug", sa.String),
                       sa.column("email_domains", sa.JSON), sa.column("active", sa.Boolean),
                       sa.column("created_at", sa.Float))
    name, slug, rows = SEED
    district_id = bind.execute(sa.select(districts.c.id).where(districts.c.slug == slug)).scalar()
    if district_id is None:
        district_id = uuid.uuid4().hex
        bind.execute(districts.insert().values(id=district_id, name=name, slug=slug, allowed_domains=[],
                                               created_at=time.time()))
    for school_name, school_slug, domains in rows:
        found = bind.execute(sa.select(schools.c.id).where(schools.c.district_id == district_id,
                                                           schools.c.slug == school_slug)).scalar()
        if found is None:
            bind.execute(schools.insert().values(id=uuid.uuid4().hex, district_id=district_id, name=school_name,
                                                 slug=school_slug, email_domains=domains, active=True,
                                                 created_at=time.time()))


def upgrade():
    op.create_table('school_emails',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('user_id', sa.String(length=32), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('domain', sa.String(length=255), nullable=False),
    sa.Column('verified_at', sa.Float(), nullable=True),
    sa.Column('code_hash', sa.String(length=64), nullable=False),
    sa.Column('code_expires_at', sa.Float(), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.Float(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email')
    )
    with op.batch_alter_table('school_emails', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_school_emails_domain'), ['domain'], unique=False)
        batch_op.create_index(batch_op.f('ix_school_emails_user_id'), ['user_id'], unique=False)

    op.create_table('school_requests',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('user_id', sa.String(length=32), nullable=False),
    sa.Column('district_id', sa.String(length=32), nullable=True),
    sa.Column('district_name', sa.String(length=200), nullable=False),
    sa.Column('school_name', sa.String(length=200), nullable=False),
    sa.Column('org_name', sa.String(length=200), nullable=False),
    sa.Column('school_email', sa.String(length=320), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('note', sa.String(length=500), nullable=False),
    sa.Column('org_id', sa.String(length=32), nullable=True),
    sa.Column('created_at', sa.Float(), nullable=False),
    sa.Column('decided_by', sa.String(length=32), nullable=True),
    sa.Column('decided_at', sa.Float(), nullable=True),
    sa.ForeignKeyConstraint(['district_id'], ['districts.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('school_requests', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_school_requests_user_id'), ['user_id'], unique=False)

    op.create_table('schools',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('district_id', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('slug', sa.String(length=120), nullable=False),
    sa.Column('email_domains', sa.JSON(), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.Float(), nullable=False),
    sa.ForeignKeyConstraint(['district_id'], ['districts.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('district_id', 'slug')
    )
    with op.batch_alter_table('schools', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_schools_district_id'), ['district_id'], unique=False)

    op.create_table('join_requests',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('org_id', sa.String(length=32), nullable=False),
    sa.Column('user_id', sa.String(length=32), nullable=False),
    sa.Column('school_email', sa.String(length=320), nullable=False),
    sa.Column('message', sa.String(length=500), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('created_at', sa.Float(), nullable=False),
    sa.Column('decided_by', sa.String(length=32), nullable=True),
    sa.Column('decided_at', sa.Float(), nullable=True),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('org_id', 'user_id')
    )
    with op.batch_alter_table('join_requests', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_join_requests_org_id'), ['org_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_join_requests_user_id'), ['user_id'], unique=False)

    with op.batch_alter_table('organizations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('school_id', sa.String(length=32), nullable=True))
        batch_op.create_index(batch_op.f('ix_organizations_school_id'), ['school_id'], unique=False)
        batch_op.create_foreign_key('fk_organizations_school_id', 'schools', ['school_id'], ['id'], ondelete='SET NULL')

    seed()



def downgrade():
    with op.batch_alter_table('organizations', schema=None) as batch_op:
        batch_op.drop_constraint('fk_organizations_school_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_organizations_school_id'))
        batch_op.drop_column('school_id')

    with op.batch_alter_table('join_requests', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_join_requests_user_id'))
        batch_op.drop_index(batch_op.f('ix_join_requests_org_id'))

    op.drop_table('join_requests')
    with op.batch_alter_table('schools', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_schools_district_id'))

    op.drop_table('schools')
    with op.batch_alter_table('school_requests', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_school_requests_user_id'))

    op.drop_table('school_requests')
    with op.batch_alter_table('school_emails', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_school_emails_user_id'))
        batch_op.drop_index(batch_op.f('ix_school_emails_domain'))

    op.drop_table('school_emails')
