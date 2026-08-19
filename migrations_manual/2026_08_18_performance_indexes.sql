-- ============================================================================
-- Migration: performance indexes for high-traffic tables
--
-- WHY:
--   At 5000 active members the finance, group, and session tables grow quickly.
--   The application filters/sorts by status, created_at, profile_id, payment_type,
--   service date, session expiry, and group leader on almost every request.
--   Without matching indexes Postgres falls back to sequential scans and in-
--   memory sorts, which become progressively slower as data grows.
--
-- WHAT THIS DOES:
--   Adds covering / partial / FK indexes that match the WHERE / ORDER BY / JOIN
--   patterns used by the FastAPI routers. All statements are idempotent and
--   use CREATE INDEX CONCURRENTLY so they are safe to run on a live database.
--
-- HOW TO APPLY:
--   psql "$DATABASE_URL" -f backend/migrations_manual/2026_08_18_performance_indexes.sql
--
-- NOTE: CREATE INDEX CONCURRENTLY cannot run inside a transaction block. Do NOT
--       wrap these statements in BEGIN/COMMIT.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Finance transactions
-- ----------------------------------------------------------------------------
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_finance_transactions_status
    ON finance_transactions (status);

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_finance_transactions_payment_type
    ON finance_transactions (payment_type);

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_finance_transactions_profile_id
    ON finance_transactions (profile_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_finance_transactions_created_at_desc
    ON finance_transactions (created_at DESC);

-- Composite covering the ledger's most common filter + sort combination.
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_finance_transactions_status_created_at
    ON finance_transactions (status, created_at DESC);

-- Composite covering profile-scoped finance lookups.
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_finance_transactions_profile_status
    ON finance_transactions (profile_id, status);

-- ----------------------------------------------------------------------------
-- Profile finance stats (looked up on every profile overview / summary call)
-- ----------------------------------------------------------------------------
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_profile_finance_stats_profile_id
    ON profile_finance_stats (profile_id);

-- ----------------------------------------------------------------------------
-- Services (filtered by date for check-in and listing)
-- ----------------------------------------------------------------------------
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_services_date_desc
    ON services (date DESC);

-- ----------------------------------------------------------------------------
-- Sessions (expiry checks run on every auth verification)
-- ----------------------------------------------------------------------------
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_session_expires_at
    ON session (expiresAt);

-- ----------------------------------------------------------------------------
-- Groups (leader lookups, list ordering)
-- ----------------------------------------------------------------------------
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_groups_leader_id
    ON groups (leader_id);

-- ----------------------------------------------------------------------------
-- Group members (membership status checks, group/user lookups)
-- ----------------------------------------------------------------------------
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_group_members_status
    ON group_members (status);

-- Already created in initial migration, but kept here for completeness.
-- CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_group_members_group_id ON group_members (group_id);
-- CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_group_members_user_id ON group_members (user_id);
