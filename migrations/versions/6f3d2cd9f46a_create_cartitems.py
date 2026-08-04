"""Create CartItems

Revision ID: 6f3d2cd9f46a
Revises: 5fdd0da7ea22
Create Date: 2026-07-30 11:50:27.239077

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '6f3d2cd9f46a'
down_revision: Union[str, Sequence[str], None] = '5fdd0da7ea22'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('cart_items',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('cart_id', sa.Uuid(), nullable=False),
    sa.Column('look_id', sa.UUID(), nullable=False),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['cart_id'], ['cart.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['look_id'], ['looks.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    # ### end Alembic commands ###
