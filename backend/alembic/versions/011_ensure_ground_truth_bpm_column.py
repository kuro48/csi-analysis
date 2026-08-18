"""Repair databases stamped at 010 without the ground-truth BPM column.

Revision ID: 011
Revises: 010
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("csi_data")}
    if "ground_truth_bpm" not in columns:
        op.add_column("csi_data", sa.Column("ground_truth_bpm", sa.Float(), nullable=True))


def downgrade() -> None:
    # Revision 010 owns this column. Downgrading only the repair revision must
    # leave the schema in the state declared by revision 010.
    pass
