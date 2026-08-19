-- ============================================================================
-- Migration: add LEADER_APPROVED to membership_status_enum
--
-- WHY:
--   The group membership approval workflow is being changed from a single
--   leader-approves-and-it's-final step into a two-stage flow:
--     PENDING -> LEADER_APPROVED (leader recommends) -> APPROVED (admin gives
--     final approval). REJECTED can still happen at either stage.
--   This requires a new enum value on the Postgres `membership_status_enum`
--   type backing `group_members.status`.
--
-- HOW TO APPLY:
--   psql "$DATABASE_URL" -f backend/migrations_manual/2026_08_17_leader_approved_membership_status.sql
--
-- NOTE: ALTER TYPE ... ADD VALUE cannot run inside a transaction block that
-- also uses the new value, so this file intentionally has no BEGIN/COMMIT.
-- Idempotent: running it again is a no-op.
-- ============================================================================

ALTER TYPE membership_status_enum ADD VALUE IF NOT EXISTS 'LEADER_APPROVED';
