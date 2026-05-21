-- ============================================================================
-- Migration: convert profiles.role (single enum) -> profiles.roles (array)
-- Adds USER + ADMIN to role_enum, backfills existing rows, drops old column.
--
-- WHY:
--  - Every authenticated user now has a base `USER` role.
--  - Extra roles are appended (e.g. group leaders are stored as
--    {USER, GROUP_LEADER}).
--  - SUPER_ADMIN is preserved exactly as before.
--  - ADMIN is a new privileged role that has full app access EXCEPT for
--    actions reserved to SUPER_ADMIN (one-of).
--
-- HOW TO APPLY:
--   psql "$DATABASE_URL" -f backend/migrations_manual/2026_05_08_roles_array.sql
--
-- This is idempotent up to the point where the old `role` column is dropped.
-- ============================================================================

BEGIN;

-- 1) Make sure the new role values exist on the enum.
--    Postgres requires ALTER TYPE ... ADD VALUE outside a transaction in some
--    versions; if you hit that, run these two statements separately.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_enum
                 WHERE enumlabel = 'USER'
                   AND enumtypid = 'role_enum'::regtype) THEN
    ALTER TYPE role_enum ADD VALUE 'USER';
  END IF;
END$$;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_enum
                 WHERE enumlabel = 'ADMIN'
                   AND enumtypid = 'role_enum'::regtype) THEN
    ALTER TYPE role_enum ADD VALUE 'ADMIN';
  END IF;
END$$;

-- 2) Add the new array column (nullable for now so we can backfill).
ALTER TABLE profiles
    ADD COLUMN IF NOT EXISTS roles role_enum[]
        NOT NULL DEFAULT ARRAY['USER']::role_enum[];

-- 3) Backfill from the legacy single `role` column, if it still exists.
--    MEMBER  -> {USER}
--    others  -> {USER, <role>}
DO $$
BEGIN
  IF EXISTS (
      SELECT 1 FROM information_schema.columns
      WHERE table_name = 'profiles' AND column_name = 'role'
  ) THEN
    UPDATE profiles
       SET roles = CASE
                     WHEN role::text = 'MEMBER' THEN ARRAY['USER']::role_enum[]
                     WHEN role::text = 'SUPER_ADMIN' THEN ARRAY['USER','SUPER_ADMIN']::role_enum[]
                     ELSE ARRAY['USER', role::text]::role_enum[]
                   END
     WHERE TRUE;
  END IF;
END$$;

-- 4) Drop the old single-role index and column.
DROP INDEX IF EXISTS ix_profile_role_completed;

ALTER TABLE profiles DROP COLUMN IF EXISTS role;

-- 5) New indexes for the array-based queries and completion gating.
CREATE INDEX IF NOT EXISTS ix_profile_roles ON profiles USING gin (roles);
CREATE INDEX IF NOT EXISTS ix_profile_completed ON profiles (profile_completed);

COMMIT;

-- ============================================================================
-- ROLLBACK (manual, only if no new ADMIN/USER-only data has been written):
--
-- BEGIN;
--   ALTER TABLE profiles ADD COLUMN role role_enum;
--   UPDATE profiles
--      SET role = COALESCE(
--                   (SELECT r FROM unnest(roles) r
--                    WHERE r::text IN ('SUPER_ADMIN','GROUP_LEADER','FINANCE')
--                    LIMIT 1),
--                   'MEMBER'::role_enum
--                 );
--   ALTER TABLE profiles ALTER COLUMN role SET NOT NULL;
--   DROP INDEX IF EXISTS ix_profile_roles;
--   DROP INDEX IF EXISTS ix_profile_completed;
--   ALTER TABLE profiles DROP COLUMN roles;
-- COMMIT;
-- ============================================================================
