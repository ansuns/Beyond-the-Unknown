"""Merge discovery/progress and mechanism-catalog migration heads."""

revision = "0007_merge_progress_mech"
down_revision = ("0006_progress_discovery", "0006_mech_catalog_align")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
