"""Persistent user carts."""
from alembic import op
import sqlalchemy as sa
revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('carts', sa.Column('id', sa.Integer(), primary_key=True), sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False, unique=True))
    op.create_table('cart_items', sa.Column('id', sa.Integer(), primary_key=True), sa.Column('cart_id', sa.Integer(), sa.ForeignKey('carts.id', ondelete='CASCADE'), nullable=False), sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id'), nullable=False), sa.Column('quantity', sa.Integer(), nullable=False), sa.UniqueConstraint('cart_id', 'product_id'), sa.CheckConstraint('quantity >= 1 AND quantity <= 99', name='ck_cart_quantity'))
    op.create_index('ix_cart_items_cart_id', 'cart_items', ['cart_id'])


def downgrade():
    op.drop_table('cart_items')
    op.drop_table('carts')
