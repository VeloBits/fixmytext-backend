-- Sprint 5b — Multi-product database scaffolding.
--
-- The `velobits-dev-db` Postgres instance hosts ALL VeloBits product
-- databases (one per product). This script creates placeholder databases
-- for future products (Chat, Notes, ...). It runs ONLY on first init
-- (when the data volume is empty) — Postgres handles that gating.
--
-- Architectural principle (see docs/SPRINT-5.md decision row 20):
--   - Keycloak's identity database lives on a SEPARATE Postgres instance
--     (`keycloak-dev-db` container, NOT this one).
--   - This Postgres holds ONLY product data. Never identity data.
--   - Each product gets its own database here, isolated from siblings.
--   - Products reference Keycloak users via `user_id` (JWT `sub` claim) but
--     never via DB-level foreign keys across instances.
--
-- Note: the `fixmytext` database (the FixMyText product DB) is already
-- created by the POSTGRES_DB env var on the Postgres service. This file
-- only adds placeholders for additional products.

CREATE DATABASE chat_dev_db;
CREATE DATABASE notes_dev_db;
-- Add future product databases here:
-- CREATE DATABASE futureapp_dev_db;
