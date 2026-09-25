-- Renly — role provisioning
-- Run as a SUPERUSER, connected to the target database, BEFORE 01_create_tables.sql:
--
--   psql -U <superuser> -d <database> -f apps/api/database/00_roles.sql
--
-- Everything here is something the table owner cannot do for itself. Roles are CLUSTER-global and
-- CREATE ROLE needs CREATEROLE; membership in a role can only be granted by a superuser or a holder
-- of ADMIN on it; and a default privilege FOR ROLE renly_admin can only be declared by renly_admin or
-- a superuser. The owner is NOSUPERUSER in production (that is what makes FORCE mean anything), so
-- none of this can live in 01_create_tables.sql, which the owner applies — there a CREATE ROLE is
-- denied and a GRANT of the owner's own membership degrades to a NOTICE, silently. Kept in its own
-- file so it can be run, and re-run, on its own: every statement is idempotent.
--
-- "The owner" below is the DATABASE owner, read from the catalogue rather than assumed to be
-- whoever runs this file — here that is a superuser, which is exactly what the owner must not be.
-- Create the database `OWNER <owner>` first; 01_create_tables.sql is then applied as that role, so
-- the database owner and the table owner are the same role.
--
-- The four roles:
--   * the OWNER (`renly` locally) owns every table, NOSUPERUSER / NOBYPASSRLS. Nothing connects as
--     it at runtime. Created by whoever provisions the database, not here;
--   * renly_admin — BYPASSRLS, a member of the owner. DATABASE_ADMIN_URL, migrations, backups, forks;
--   * renly_app — NOBYPASSRLS, DML grants only. DATABASE_URL, every request connection;
--   * renly_policy_definer — NOLOGIN, BYPASSRLS, SELECT on exactly the tables the SECURITY DEFINER
--     policy helpers read. It owns those helpers and nothing else (see 01_create_tables.sql).
--
-- The passwords are local-dev defaults; production provisions both login roles with real secrets.

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'renly_admin') THEN
    CREATE ROLE renly_admin LOGIN PASSWORD 'renly_admin' NOSUPERUSER NOCREATEDB NOCREATEROLE BYPASSRLS;
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'renly_app') THEN
    CREATE ROLE renly_app LOGIN PASSWORD 'renly_app' NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
  END IF;
END $$;

-- NOLOGIN: nothing ever connects as it. It exists so the three policy helpers run as a role that
-- bypasses RLS WITHOUT being the table owner — under FORCE the owner is subject to the policies,
-- and a helper running as the owner re-enters the very policy that called it (group_members'
-- policy calls app_is_group_member, which reads group_members) until the stack runs out.
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'renly_policy_definer') THEN
    CREATE ROLE renly_policy_definer NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE BYPASSRLS;
  END IF;
END $$;

-- renly_admin is a member of the owner: migrations ALTER and DROP owner-owned objects, which only a
-- member of the owner may do. BYPASSRLS is a role ATTRIBUTE and is NOT inherited through membership,
-- which is why renly_admin carries it directly — and why `SET ROLE <owner>` inside an admin session
-- gives the bypass up rather than keeping it.
--
-- The owner is a member of renly_policy_definer: handing a function to a role requires being able to
-- SET ROLE to it, and 01_create_tables.sql (run as the owner) hands the helpers over. renly_admin
-- reaches it through its membership of the owner, which is what lets a migration re-own or replace a
-- helper. Membership carries no BYPASSRLS either, for the same reason as above.
DO $$
DECLARE
  db_owner TEXT := (SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = current_database());
BEGIN
  EXECUTE format('GRANT %I TO renly_admin', db_owner);
  EXECUTE format('GRANT renly_policy_definer TO %I', db_owner);
END $$;

-- Objects a migration creates are owned, at first, by the role that ran it — renly_admin — and the
-- default privileges 01_create_tables.sql declares cover only objects the OWNER creates. Without this,
-- a table added by a migration reaches renly_app with no grants at all: `migrations/env.py` reassigns
-- its ownership to the owner afterwards, but REASSIGN OWNED moves ownership and adds no privilege.
-- Same grant set as the owner's default privileges.
ALTER DEFAULT PRIVILEGES FOR ROLE renly_admin IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO renly_app;
ALTER DEFAULT PRIVILEGES FOR ROLE renly_admin IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO renly_app;
