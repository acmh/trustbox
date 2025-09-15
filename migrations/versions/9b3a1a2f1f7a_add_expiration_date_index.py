"""Add index on expiration_date

Revision ID: 9b3a1a2f1f7a
Revises: 4a4bed19ba9c
Create Date: 2025-09-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9b3a1a2f1f7a'
down_revision: Union[str, Sequence[str], None] = '4a4bed19ba9c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        'ix_encrypted_files_expiration_date',
        'encrypted_files',
        ['expiration_date'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_encrypted_files_expiration_date', table_name='encrypted_files')
