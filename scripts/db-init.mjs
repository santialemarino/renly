/**
 * Ensures Postgres (docker-compose) is up, provisions the roles and applies the initial schema.
 * Run from repo root: pnpm db:init
 */
import { execSync } from 'child_process';
import fs from 'fs';
import path from 'path';

const ROOT = process.cwd();
const CONTAINER = 'renly-postgres';
const ROLES_PATH = path.join(ROOT, 'apps/api/database/00_roles.sql');
const SCHEMA_PATH = path.join(ROOT, 'apps/api/database/01_create_tables.sql');

function run(cmd, opts = {}) {
  return execSync(cmd, { stdio: 'inherit', cwd: ROOT, ...opts });
}

/*
 * Over TCP rather than the container's Unix socket, because on a FRESH volume the image first runs a
 * temporary server that listens on the socket only, creates the database, and then shuts down to
 * restart for real. A socket check answers during that window, and the roles file then dies with
 * "the database system is shutting down". Only the final server listens on TCP.
 */
function isPostgresReady() {
  try {
    execSync(`docker exec ${CONTAINER} psql -h 127.0.0.1 -U renly -d renly -c "SELECT 1"`, {
      stdio: 'pipe',
      cwd: ROOT,
    });
    return true;
  } catch {
    return false;
  }
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function waitForPostgres(maxAttempts = 15) {
  for (let i = 0; i < maxAttempts; i++) {
    if (isPostgresReady()) return;
    if (i === 0) process.stdout.write('Waiting for Postgres');
    process.stdout.write('.');
    await sleep(i < 3 ? 500 : 1000);
  }
  console.error('\nPostgres did not become ready in time.');
  process.exit(1);
}

async function main() {
  // Start postgres if not running.
  console.log('Starting Postgres (docker compose up -d postgres)...');
  run('docker compose up -d postgres');

  // Wait until we can run a query.
  await waitForPostgres();
  console.log(' Postgres is ready.');

  for (const file of [ROLES_PATH, SCHEMA_PATH]) {
    if (!fs.existsSync(file)) {
      console.error(`Schema file not found: ${file}`);
      process.exit(1);
    }
  }

  // Roles first: they are cluster-global and need a superuser (compose's `renly` is one), and the
  // schema grants to them. The roles file is idempotent, so re-running db:init never fails on it.
  console.log('Provisioning roles (00_roles.sql)...');
  execSync(`docker exec -i ${CONTAINER} psql -v ON_ERROR_STOP=1 -U renly -d renly`, {
    input: fs.readFileSync(ROLES_PATH, 'utf8'),
    stdio: ['pipe', 'inherit', 'inherit'],
    cwd: ROOT,
  });

  console.log('Applying schema (01_create_tables.sql)...');
  execSync(`docker exec -i ${CONTAINER} psql -v ON_ERROR_STOP=1 -U renly -d renly`, {
    input: fs.readFileSync(SCHEMA_PATH, 'utf8'),
    stdio: ['pipe', 'inherit', 'inherit'],
    cwd: ROOT,
  });

  // Mark the freshly-built schema as current for Alembic so future migrations apply cleanly.
  console.log('Stamping Alembic head (alembic_version)...');
  try {
    execSync('uv run alembic stamp head', {
      stdio: 'inherit',
      cwd: path.join(ROOT, 'apps/api'),
    });
  } catch {
    console.warn(
      'Could not stamp Alembic head (is uv installed?). Run `uv run alembic stamp head` from apps/api, or `pnpm db:migrate`.',
    );
  }

  console.log(
    'Database initialized (roles provisioned by 00_roles.sql; the schema FORCEs RLS). In apps/api/.env set:\n' +
      '  DATABASE_URL=postgresql+asyncpg://renly_app:renly_app@localhost:5432/renly            (restricted, RLS-subject request role)\n' +
      '  DATABASE_ADMIN_URL=postgresql+asyncpg://renly_admin:renly_admin@localhost:5432/renly  (BYPASSRLS: scheduler, migrations, auth bootstrap)\n' +
      '\nThe OWNER role (renly) is in neither line and must not be: locally it is a superuser, which\n' +
      'bypasses every policy, and in production (NOSUPERUSER, tables FORCEd) it reads nothing.',
  );
}

main();
