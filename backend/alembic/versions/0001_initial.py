"""Initialize the Relayvia schema baseline."""

from typing import Sequence, Union

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Phase 1 establishes the migration pipeline. Domain tables arrive with
    # their corresponding domain models in later phases.
    pass


def downgrade() -> None:
    pass

