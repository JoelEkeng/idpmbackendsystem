-- ============================================================================
-- Migration: reconcile role_enum with the application RoleEnum
--
-- ROLE MODEL:
--   Everyone is a USER first. On top of that they hold exactly one of the
--   functional roles: MEMBER, GROUP_LEADER, FINANCE, ADMIN or SUPER_ADMIN.
--   USER and ADMIN are distinct. MEMBER is a real role (a regular member),
--   NOT a synonym for USER.
--
-- WHY:
--  - The roles-array change was never fully applied to the DB, so the Postgres
--    `role_enum` still only has {MEMBER, GROUP_LEADER, FINANCE, SUPER_ADMIN}
--    while the app `RoleEnum` is {USER, MEMBER, GROUP_LEADER, FINANCE, ADMIN,
--    SUPER_ADMIN}. Reading a row raised:
--        invalid input value for enum role_enum: "USER"   (writing USER)
--    and, once USER existed app-side but not for older data:
--        LookupError: 'MEMBER' is not among the defined enum values.
--
-- WHAT THIS DOES:
--  1) Adds 'USER' and 'ADMIN' to role_enum (idempotent). MEMBER already exists.
--  2) Ensures every profile has the base 'USER' role, KEEPING its existing
--     functional role:
--        {MEMBER}      -> {USER, MEMBER}
--        {SUPER_ADMIN} -> {USER, SUPER_ADMIN}
--
-- HOW TO APPLY:
--   psql "$DATABASE_URL" -f backend/migrations_manual/2026_07_08_fix_member_role.sql
--
-- NOTE: ALTER TYPE ... ADD VALUE cannot run inside the same transaction that
-- later uses the new value, so the two steps are committed separately.
-- Idempotent: running it again is a no-op.
-- ============================================================================

-- 1) Make sure the new enum values exist (auto-committed, no explicit BEGIN).
ALTER TYPE role_enum ADD VALUE IF NOT EXISTS 'USER';
ALTER TYPE role_enum ADD VALUE IF NOT EXISTS 'ADMIN';

-- 2) Guarantee USER is present as the base role on every profile while keeping
--    each profile's existing functional role(s). De-duplicated.
BEGIN;

UPDATE profiles
   SET roles = sub.new_roles
  FROM (
        SELECT id,
               ARRAY(
                 SELECT DISTINCT val
                   FROM (
                          SELECT 'USER'::role_enum AS val
                          UNION ALL
                          SELECT r FROM unnest(roles) AS r
                        ) AS expanded
               ) AS new_roles
          FROM profiles
       ) AS sub
 WHERE profiles.id = sub.id;

COMMIT;
