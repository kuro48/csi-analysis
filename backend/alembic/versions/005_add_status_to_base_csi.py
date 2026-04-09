"""Add processing status fields to base_csi

Revision ID: 005
Revises: 004
Create Date: 2026-04-09 17:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '005'
down_revision: Union[str, None] = '004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('base_csi', sa.Column('status', sa.String(length=50), nullable=False, server_default='completed'))
    op.add_column('base_csi', sa.Column('error_message', sa.String(length=1000), nullable=True))
    op.create_index('ix_base_csi_status', 'base_csi', ['status'], unique=False)
    op.alter_column('base_csi', 'status', server_default=None)


def downgrade() -> None:
    op.drop_index('ix_base_csi_status', table_name='base_csi')
    op.drop_column('base_csi', 'error_message')
    op.drop_column('base_csi', 'status')
