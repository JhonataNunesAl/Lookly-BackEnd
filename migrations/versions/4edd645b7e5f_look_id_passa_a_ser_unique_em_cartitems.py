"""Look_id passa a ser unique em cartitems

Revision ID: 4edd645b7e5f
Revises: 6f3d2cd9f46a
Create Date: 2026-08-02 08:36:23.629983

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '4edd645b7e5f'
down_revision: Union[str, Sequence[str], None] = '6f3d2cd9f46a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
   
    op.add_column('cart', sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False))
    op.drop_column('cart', 'update_at')
    op.create_unique_constraint(None, 'cart_items', ['look_id'])
    
