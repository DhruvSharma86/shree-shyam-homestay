"""receipts immutability triggers

Receipts issued at checkout have immutable PDF bytes and hashes; add
PostgreSQL BEFORE UPDATE/DELETE row triggers (same reject function as the
financial triggers) so issued records cannot be silently altered or
deleted. SQLite has no equivalent (service-layer only there; reindex of
receipt metadata cannot change issued bytes anyway, as they are stored).

Revision ID: c0d1e2f3a4b5
Revises: b9c0d1e2f3a4
"""


from alembic import op

revision = "c0d1e2f3a4b5"
down_revision = "b9c0d1e2f3a4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "CREATE OR REPLACE FUNCTION reject_financial_mutation() "
            "RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN "
            "RAISE EXCEPTION 'financial records are append-only; use a reversal entry'; "
            "RETURN NULL; END; $$"
        )
        op.execute("DROP TRIGGER IF EXISTS trg_receipts_immutable ON receipts")
        op.execute(
            "CREATE TRIGGER trg_receipts_immutable BEFORE UPDATE OR DELETE ON receipts "
            "FOR EACH ROW EXECUTE FUNCTION reject_financial_mutation()"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_receipts_immutable ON receipts")
