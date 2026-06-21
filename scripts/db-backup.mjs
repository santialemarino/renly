/**
 * Creates a compressed pg_dump backup of the Renly database (SHELL-4 / INFRA-4) under backups/.
 * Run from repo root: pnpm db:backup
 *
 * Source URL (first match wins):
 *   1. $BACKUP_DATABASE_URL
 *   2. DATABASE_ADMIN_URL in apps/api/.env — the table owner; bypasses RLS so the dump has ALL rows
 *   3. DATABASE_URL in apps/api/.env       — falls back, but a restricted RLS role dumps ZERO rows
 *
 * Uses a throwaway postgres:16-alpine container, so host pg_dump isn't required. The dump is
 * created with --no-owner --no-acl --clean --if-exists so it restores into any fresh database
 * (see scripts/db-restore.mjs and docs/technical/backups.md).
 */
import { spawn } from 'child_process';
import fs from 'fs';
import path from 'path';
import { createGzip } from 'zlib';

const ENV_PATH = path.join(process.cwd(), 'apps/api/.env');
const BACKUP_DIR = path.join(process.cwd(), 'backups');
const LOCAL_HOSTS = new Set(['localhost', '127.0.0.1', '::1', '']);
const PG_IMAGE = 'postgres:16-alpine';

// Reads a single KEY=value line from a .env file's contents.
function readEnvVar(content, key) {
  const match = content.match(new RegExp(`^${key}\\s*=\\s*(.+)$`, 'm'));
  return match ? match[1].trim() : null;
}

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

// Resolves the source URL, preferring the owner role so RLS doesn't filter rows out of the dump.
function resolveSourceUrl() {
  if (process.env.BACKUP_DATABASE_URL) {
    return { raw: process.env.BACKUP_DATABASE_URL, origin: '$BACKUP_DATABASE_URL' };
  }
  if (!fs.existsSync(ENV_PATH)) {
    throw new Error('No BACKUP_DATABASE_URL set and apps/api/.env not found.');
  }
  const content = fs.readFileSync(ENV_PATH, 'utf8');
  const admin = readEnvVar(content, 'DATABASE_ADMIN_URL');
  if (admin) return { raw: admin, origin: 'DATABASE_ADMIN_URL (apps/api/.env)' };
  const url = readEnvVar(content, 'DATABASE_URL');
  if (url) {
    console.warn(
      'WARNING: backing up via DATABASE_URL. If that is the restricted RLS role (renly_app), the\n' +
        'dump will contain ZERO user rows. Set DATABASE_ADMIN_URL (owner) or $BACKUP_DATABASE_URL.',
    );
    return { raw: url, origin: 'DATABASE_URL (apps/api/.env)' };
  }
  throw new Error(
    'No database URL found (BACKUP_DATABASE_URL / DATABASE_ADMIN_URL / DATABASE_URL).',
  );
}

// Builds a filesystem-safe YYYYMMDD-HHMMSS timestamp in local time.
function timestamp() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  return (
    `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-` +
    `${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`
  );
}

async function main() {
  const { raw, origin } = resolveSourceUrl();
  const creds = parseUrl(raw);
  const isLocal = LOCAL_HOSTS.has(creds.host);
  const dumpHost = isLocal ? 'host.docker.internal' : creds.host;

  fs.mkdirSync(BACKUP_DIR, { recursive: true });
  const outPath = path.join(BACKUP_DIR, `renly-${timestamp()}.sql.gz`);

  console.log(`Backing up "${creds.database}" @ ${creds.host}:${creds.port} (source: ${origin})`);
  console.log(`Output: ${path.relative(process.cwd(), outPath)}`);

  const pgDump = spawn('docker', [
    'run',
    '--rm',
    ...(isLocal ? ['--add-host=host.docker.internal:host-gateway'] : []),
    '-e',
    `PGPASSWORD=${creds.password}`,
    PG_IMAGE,
    'pg_dump',
    '-h',
    dumpHost,
    '-p',
    String(creds.port),
    '-U',
    creds.user,
    '-d',
    creds.database,
    '--no-owner',
    '--no-acl',
    '--clean',
    '--if-exists',
  ]);

  const gzip = createGzip();
  const out = fs.createWriteStream(outPath);
  pgDump.stdout.pipe(gzip).pipe(out);
  pgDump.stderr.pipe(process.stderr);

  try {
    // Resolve only once both the dump exited cleanly and the gzip file finished writing.
    await new Promise((resolve, reject) => {
      let dumpOk = false;
      let fileDone = false;
      const maybeResolve = () => {
        if (dumpOk && fileDone) resolve();
      };
      pgDump.on('error', reject);
      pgDump.on('close', (code) => {
        if (code !== 0) return reject(new Error(`pg_dump exited with code ${code}`));
        dumpOk = true;
        maybeResolve();
      });
      gzip.on('error', reject);
      out.on('error', reject);
      out.on('finish', () => {
        fileDone = true;
        maybeResolve();
      });
    });
  } catch (err) {
    // Don't leave a truncated dump behind.
    fs.rmSync(outPath, { force: true });
    throw err;
  }

  const { size } = fs.statSync(outPath);
  console.log(`\nBackup complete: ${(size / 1024).toFixed(1)} KiB.`);
}

main().catch((err) => {
  console.error(`Backup failed: ${err.message}`);
  process.exit(1);
});
