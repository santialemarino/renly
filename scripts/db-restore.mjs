/**
 * Restores a db-backup dump (.sql.gz) into a target database (SHELL-4 / INFRA-4).
 * Run from repo root:
 *   RESTORE_DATABASE_URL=postgresql://user:pass@host:port/db node scripts/db-restore.mjs <file> --force
 *
 * DESTRUCTIVE: the dump uses --clean --if-exists, so matching objects in the target are dropped
 * and recreated. The target is taken ONLY from $RESTORE_DATABASE_URL (never DATABASE_URL, to avoid
 * clobbering your dev DB by accident), and --force is required to proceed. Restore as the table
 * owner. The renly_app role + its grants are NOT in the dump — re-provision them (the role section
 * of apps/api/database/01_create_tables.sql) when restoring into a brand-new database. See
 * docs/technical/backups.md for the full procedure.
 */
import { spawn } from 'child_process';
import fs from 'fs';
import { createGunzip } from 'zlib';

const LOCAL_HOSTS = new Set(['localhost', '127.0.0.1', '::1', '']);
const PG_IMAGE = 'postgres:16-alpine';

// Parses a Postgres URL, stripping any SQLAlchemy driver suffix (e.g. +asyncpg) so pg tools accept it.
function parseUrl(raw) {
  const normalized = raw.replace(/^postgresql\+\w+:\/\//, 'postgresql://');
  const url = new URL(normalized);
  return {
    host: url.hostname,
    port: url.port || '5432',
    user: decodeURIComponent(url.username),
    password: decodeURIComponent(url.password),
    database: url.pathname.replace(/^\//, ''),
  };
}

function fail(message) {
  console.error(message);
  process.exit(1);
}

const file = process.argv[2];
const force = process.argv.includes('--force');
const targetRaw = process.env.RESTORE_DATABASE_URL;

if (!file || file.startsWith('--')) {
  fail('Usage: RESTORE_DATABASE_URL=... node scripts/db-restore.mjs <backup-file.sql.gz> --force');
}
if (!fs.existsSync(file)) fail(`Backup file not found: ${file}`);
if (!targetRaw)
  fail('Set RESTORE_DATABASE_URL to the target database (not your dev DATABASE_URL).');
if (!force) fail('Refusing to restore without --force (this overwrites the target database).');

async function main() {
  const creds = parseUrl(targetRaw);
  const isLocal = LOCAL_HOSTS.has(creds.host);
  const targetHost = isLocal ? 'host.docker.internal' : creds.host;

  console.log(`Restoring ${file}`);
  console.log(`  into "${creds.database}" @ ${creds.host}:${creds.port} (user: ${creds.user})`);

  const psql = spawn('docker', [
    'run',
    '--rm',
    '-i',
    ...(isLocal ? ['--add-host=host.docker.internal:host-gateway'] : []),
    '-e',
    `PGPASSWORD=${creds.password}`,
    PG_IMAGE,
    'psql',
    '-h',
    targetHost,
    '-p',
    String(creds.port),
    '-U',
    creds.user,
    '-d',
    creds.database,
    '-v',
    'ON_ERROR_STOP=1',
  ]);

  const input = fs.createReadStream(file);
  const gunzip = createGunzip();
  input.pipe(gunzip).pipe(psql.stdin);
  psql.stdout.pipe(process.stdout);
  psql.stderr.pipe(process.stderr);

  await new Promise((resolve, reject) => {
    input.on('error', reject);
    gunzip.on('error', reject);
    psql.on('error', reject);
    psql.on('close', (code) => {
      if (code !== 0) return reject(new Error(`psql exited with code ${code}`));
      resolve();
    });
  });

  console.log('\nRestore complete.');
}

main().catch((err) => {
  console.error(`Restore failed: ${err.message}`);
  process.exit(1);
});
