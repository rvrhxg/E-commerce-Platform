"""Optimistic cart snapshot for atomic checkout cleanup."""
from alembic import op
import sqlalchemy as sa
revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('carts', sa.Column('revision', sa.Integer(), nullable=False, server_default='0'))


def downgrade():
    op.drop_column('carts', 'revision')
