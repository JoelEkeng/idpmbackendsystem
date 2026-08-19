# Manual SQL migrations

Your Alembic directory is `.gitignored`, so destructive schema migrations
that need code review live here as raw SQL files.

## Apply

```bash
psql "$DATABASE_URL" -f backend/migrations_manual/2026_05_08_roles_array.sql
```

## What's here

- **`2026_08_17_leader_approved_membership_status.sql`** — Adds
  `LEADER_APPROVED` to `membership_status_enum` for the new two-stage group
  approval workflow (`PENDING -> LEADER_APPROVED -> APPROVED`, or `REJECTED`
  at either stage).

- **`2026_05_08_roles_array.sql`** — Converts `profiles.role` (single enum)
  into `profiles.roles` (array of `role_enum`). Adds `USER` and `ADMIN` to
  `role_enum`. Backfills existing rows so:
  - `MEMBER` → `{USER}`
  - `GROUP_LEADER` → `{USER, GROUP_LEADER}`
  - `FINANCE` → `{USER, FINANCE}`
  - `SUPER_ADMIN` → `{USER, SUPER_ADMIN}`

  Drops the old `role` column at the end. A rollback block is included as a
  comment at the bottom of the file.

> ⚠️ Postgres requires `ALTER TYPE … ADD VALUE` to run **outside** a transaction
> in some versions. If the migration fails on those lines, extract those two
> `DO $$ … $$` blocks and run them as a separate `psql` command first, then
> re-run the rest of the file.

## After applying

1. Re-generate an Alembic baseline so future migrations stay in sync:
   ```bash
   alembic stamp head
   ```
2. Run the test suite (`pytest backend/tests`) to confirm the new permission
   model works against the updated schema.
