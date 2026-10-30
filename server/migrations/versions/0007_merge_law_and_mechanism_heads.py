"""Merge the law-action and mechanism-catalog migration heads."""

revision = "0007_merge_law_and_mechanism_heads"
down_revision = ("0005_authoritative_law_actions", "0006_mech_catalog_align")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
