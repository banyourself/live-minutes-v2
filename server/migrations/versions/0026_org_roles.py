from alembic import op
import sqlalchemy as sa


revision = '0026'
down_revision = '0025'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    positions = sa.table('positions', sa.column('id', sa.String), sa.column('name', sa.String),
                         sa.column('access', sa.String), sa.column('permissions', sa.JSON))
    for pid, name, access, perms in conn.execute(sa.select(positions.c.id, positions.c.name, positions.c.access,
                                                           positions.c.permissions)).all():
        perms = list(perms or [])
        new_access = access
        if "edit_permissions" in perms and "delete_organization" not in perms:
            perms.append("delete_organization")
        if (name or "").strip().lower() == "president" and access == "secretary":
            new_access = "owner"
        conn.execute(positions.update().where(positions.c.id == pid).values(permissions=perms, access=new_access))


def downgrade():
    conn = op.get_bind()
    positions = sa.table('positions', sa.column('id', sa.String), sa.column('permissions', sa.JSON))
    for pid, perms in conn.execute(sa.select(positions.c.id, positions.c.permissions)).all():
        conn.execute(positions.update().where(positions.c.id == pid)
                     .values(permissions=[p for p in (perms or []) if p != "delete_organization"]))
