"""add_recipes_and_stock_flag

Revision ID: 651f9115049a
Revises: 9d07782f822f
Create Date: 2026-02-25 00:03:48.356961

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '651f9115049a'
down_revision = '9d07782f822f'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if 'product_recipes' not in inspector.get_table_names():
        op.create_table(
            'product_recipes',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('product_id', sa.Integer(), nullable=False),
            sa.Column('inventory_item_id', sa.Integer(), nullable=False),
            sa.Column('quantity_required', sa.Float(), nullable=False),
            sa.ForeignKeyConstraint(['inventory_item_id'], ['inventory_items.id']),
            sa.ForeignKeyConstraint(['product_id'], ['products.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('product_id', 'inventory_item_id', name='uq_product_inventory')
        )

    orders_columns = {col['name'] for col in inspector.get_columns('orders')}
    if 'stock_processed' not in orders_columns:
        with op.batch_alter_table('orders', schema=None) as batch_op:
            batch_op.add_column(sa.Column('stock_processed', sa.Boolean(), nullable=True))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if 'orders' in inspector.get_table_names():
        orders_columns = {col['name'] for col in inspector.get_columns('orders')}
        if 'stock_processed' in orders_columns:
            with op.batch_alter_table('orders', schema=None) as batch_op:
                batch_op.drop_column('stock_processed')

    if 'product_recipes' in inspector.get_table_names():
        op.drop_table('product_recipes')
