"""Add ground-truth BPM to CSI data.

Revision ID: 010
Revises: 009
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("csi_data", sa.Column("ground_truth_bpm", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("csi_data", "ground_truth_bpm")
