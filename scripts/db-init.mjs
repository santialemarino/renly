/**
 * Ensures Postgres (docker-compose) is up and applies the initial schema.
 * Run from repo root: pnpm db:init
 */
import { execSync } from 'child_process';
import fs from 'fs';
import path from 'path';

const ROOT = process.cwd();
const CONTAINER = 'renly-postgres';
const SCHEMA_PATH = path.join(ROOT, 'apps/api/database/01_create_tables.sql');

function run(cmd, opts = {}) {
  return execSync(cmd, { stdio: 'inherit', cwd: ROOT, ...opts });
}

function isPostgresReady() {
  try {
    execSync(`docker exec ${CONTAINER} psql -U renly -d renly -c "SELECT 1"`, {
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

  if (!fs.existsSync(SCHEMA_PATH)) {
    console.error(`Schema file not found: ${SCHEMA_PATH}`);
    process.exit(1);
  }

  console.log('Applying schema (01_create_tables.sql)...');
  const sql = fs.readFileSync(SCHEMA_PATH, 'utf8');
  execSync(`docker exec -i ${CONTAINER} psql -U renly -d renly`, {
    input: sql,
    stdio: ['pipe', 'inherit', 'inherit'],
    cwd: ROOT,
  });

  console.log(
    'Database initialized. Use DATABASE_URL=postgresql+asyncpg://renly:renly@localhost:5432/renly in apps/api/.env',
  );
}

main();
