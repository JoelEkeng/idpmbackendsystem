-- ============================================================================
-- Migration: performance indexes for the attendances table
--
-- WHY:
--   The attendance monitor pages filter by service_id (or profile_id) and
--   order by check_in_time DESC. Without a matching index Postgres does a full
--   table scan + in-memory sort on every request. At 5000 members with weekly
--   services this table grows fast and those pages get progressively slower.
--
-- WHAT THIS DOES:
--   Adds composite indexes that cover BOTH the WHERE filter and the ORDER BY:
--     * ix_attendance_service_checkin  (service_id, check_in_time DESC)
--     * ix_attendance_profile_checkin  (profile_id, check_in_time DESC)
--   Plus plain FK indexes on service_id / profile_id for joins and cascades.
--
-- HOW TO APPLY:
--   psql "$DATABASE_URL" -f backend/migrations_manual/2026_07_13_attendance_indexes.sql
--
-- NOTE: CREATE INDEX CONCURRENTLY cannot run inside a transaction block. Do NOT
--       wrap these statements in BEGIN/COMMIT. They are idempotent (IF NOT
--       EXISTS) and non-locking, so they are safe to run on a live database.
-- ============================================================================

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_attendances_service_id
    ON attendances (service_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_attendances_profile_id
    ON attendances (profile_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_attendance_service_checkin
    ON attendances (service_id, check_in_time DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_attendance_profile_checkin
    ON attendances (profile_id, check_in_time DESC);
