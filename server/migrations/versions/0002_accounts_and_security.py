from alembic import op
import sqlalchemy as sa


revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('outbox',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('to_addr', sa.String(length=320), nullable=False),
    sa.Column('subject', sa.String(length=300), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('created_at', sa.Float(), nullable=False),
    sa.Column('next_try_at', sa.Float(), nullable=False),
    sa.Column('sent_at', sa.Float(), nullable=True),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('error', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('outbox', schema=None) as batch_op:
        batch_op.create_index('ix_outbox_pending', ['sent_at', 'next_try_at'], unique=False)

    op.create_table('rate_events',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('key', sa.String(length=400), nullable=False),
    sa.Column('created_at', sa.Float(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('rate_events', schema=None) as batch_op:
        batch_op.create_index('ix_rate_key_time', ['key', 'created_at'], unique=False)

    op.create_table('email_tokens',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('user_id', sa.String(length=32), nullable=False),
    sa.Column('purpose', sa.String(length=20), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.Float(), nullable=False),
    sa.Column('expires_at', sa.Float(), nullable=False),
    sa.Column('used_at', sa.Float(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_hash')
    )
    with op.batch_alter_table('email_tokens', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_email_tokens_user_id'), ['user_id'], unique=False)

    op.create_table('identities',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('user_id', sa.String(length=32), nullable=False),
    sa.Column('provider', sa.String(length=40), nullable=False),
    sa.Column('subject', sa.String(length=300), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('created_at', sa.Float(), nullable=False),
    sa.Column('last_used_at', sa.Float(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('provider', 'subject')
    )
    with op.batch_alter_table('identities', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_identities_user_id'), ['user_id'], unique=False)

    with op.batch_alter_table('capture_tokens', schema=None) as batch_op:
        batch_op.add_column(sa.Column('expires_at', sa.Float(), nullable=True))

    with op.batch_alter_table('invites', schema=None) as batch_op:
        batch_op.add_column(sa.Column('expires_at', sa.Float(), nullable=True))

    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('run_after', sa.Float(), nullable=False, server_default='0'))

    with op.batch_alter_table('meetings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('draft_rev', sa.Integer(), nullable=False, server_default='0'))

    with op.batch_alter_table('user_sessions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('last_seen_at', sa.Float(), nullable=True))

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('email_verified_at', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('verified_via', sa.String(length=20), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('password_changed_at', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('disabled', sa.Boolean(), nullable=False, server_default=sa.false()))

    op.execute("UPDATE users SET email_verified_at = created_at, verified_via = 'legacy' WHERE email_verified_at IS NULL")
    op.execute("UPDATE invites SET expires_at = created_at + 604800 WHERE expires_at IS NULL AND accepted_at IS NULL")



def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('disabled')
        batch_op.drop_column('password_changed_at')
        batch_op.drop_column('verified_via')
        batch_op.drop_column('email_verified_at')

    with op.batch_alter_table('user_sessions', schema=None) as batch_op:
        batch_op.drop_column('last_seen_at')

    with op.batch_alter_table('meetings', schema=None) as batch_op:
        batch_op.drop_column('draft_rev')

    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.drop_column('run_after')

    with op.batch_alter_table('invites', schema=None) as batch_op:
        batch_op.drop_column('expires_at')

    with op.batch_alter_table('capture_tokens', schema=None) as batch_op:
        batch_op.drop_column('expires_at')

    with op.batch_alter_table('identities', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_identities_user_id'))

    op.drop_table('identities')
    with op.batch_alter_table('email_tokens', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_email_tokens_user_id'))

    op.drop_table('email_tokens')
    with op.batch_alter_table('rate_events', schema=None) as batch_op:
        batch_op.drop_index('ix_rate_key_time')

    op.drop_table('rate_events')
    with op.batch_alter_table('outbox', schema=None) as batch_op:
        batch_op.drop_index('ix_outbox_pending')

    op.drop_table('outbox')
