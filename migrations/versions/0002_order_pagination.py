"""Indexes for descending owner and management order pages."""
from alembic import op

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade():
    op.create_index('ix_orders_user_id_id', 'orders', ['user_id', 'id'])


def downgrade():
    op.drop_index('ix_orders_user_id_id', table_name='orders')
