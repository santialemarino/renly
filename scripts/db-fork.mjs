import { execSync, spawn } from 'child_process';
import fs from 'fs';
import path from 'path';

const ENV_PATH = path.join(process.cwd(), 'apps/api/.env');

const LOCAL_PORT = process.argv[2] || '5433';
const CONTAINER_NAME = `renly-db-local-${LOCAL_PORT}`;

const LOCAL_HOSTS = new Set(['localhost', '127.0.0.1', '::1', '']);

// Parse DATABASE_URL from a .env file.
// Handles both postgresql:// and postgresql+asyncpg:// (SQLAlchemy async format).
function parseEnv(filePath) {
  const content = fs.readFileSync(filePath, 'utf8');

  const match = content.match(/^DATABASE_URL\s*=\s*(.+)$/m);
  if (!match) throw new Error('DATABASE_URL not found in apps/api/.env');

  // Strip driver suffix (e.g. +asyncpg) so pg tools can parse it.
  const raw = match[1].trim().replace(/^postgresql\+\w+:\/\//, 'postgresql://');

  const url = new URL(raw);
  return {
    host: url.hostname,
    port: url.port || '5432',
    user: decodeURIComponent(url.username),
    password: decodeURIComponent(url.password),
    database: url.pathname.replace(/^\//, ''),
  };
}

async function run() {
  console.log(`Starting local DB fork: ${CONTAINER_NAME}...`);

  try {
    const creds = parseEnv(ENV_PATH);
    console.log(`Read credentials from apps/api/.env`);

    /* When the source is on the host machine, the throwaway pg_dump container
     * can't reach localhost — use host.docker.internal instead.
     * --add-host is required on Linux; Docker Desktop on Mac resolves it automatically.
     */
    const isLocalSource = LOCAL_HOSTS.has(creds.host);
    const dumpHost = isLocalSource ? 'host.docker.internal' : creds.host;

    // 1. Start Docker container
    console.log(`Ensuring Docker container "${CONTAINER_NAME}" is running...`);
    try {
      execSync(
        `docker run --name ${CONTAINER_NAME} \
          -e POSTGRES_PASSWORD=renly \
          -e POSTGRES_USER=renly \
          -e POSTGRES_DB=renly \
          -p ${LOCAL_PORT}:5432 \
          -d postgres:16-alpine`,
        { stdio: 'ignore' },
      );
      console.log(`   - Created new container on port ${LOCAL_PORT}`);
    } catch {
      try {
        const inspectOutput = execSync(`docker inspect -f '{{.State.Running}}' ${CONTAINER_NAME}`, {
          encoding: 'utf8',
          stdio: ['ignore', 'pipe', 'ignore'],
        }).trim();

        if (inspectOutput === 'true') {
          console.log(`   - Container already exists and is running.`);
        } else {
          execSync(`docker start ${CONTAINER_NAME}`, { stdio: 'inherit' });
          console.log(`   - Container already exists, started it.`);
        }
      } catch (inspectError) {
        throw inspectError;
      }
    }

    // Wait for PostgreSQL to be ready.
    console.log(`Waiting for PostgreSQL to be ready...`);
    let retries = 0;
    while (retries < 15) {
      try {
        execSync(`docker exec ${CONTAINER_NAME} pg_isready -U renly -d renly`, { stdio: 'ignore' });
        await new Promise((r) => setTimeout(r, 2000));
        break;
      } catch {
        await new Promise((r) => setTimeout(r, 2000));
        retries++;
      }
    }

    if (retries >= 15) {
      throw new Error('PostgreSQL did not become ready after 15 attempts; aborting setup.');
    }

    // 2. Sync data
    console.log(`Syncing data from ${creds.host}:${creds.port}...`);

    // Use a throwaway container to run pg_dump — no need to install it on the host.
    const pgDump = spawn('docker', [
      'run',
      '--rm',
      ...(isLocalSource ? ['--add-host=host.docker.internal:host-gateway'] : []),
      '-e',
      `PGPASSWORD=${creds.password}`,
      'postgres:16-alpine',
      'pg_dump',
      '-h',
      dumpHost,
      '-p',
      String(creds.port),
      '-U',
      creds.user,
      '-d',
      creds.database,
      '--no-owner', // Don't restore ownership (local user differs)
      '--no-acl', // Skip GRANT/REVOKE
      '--clean', // DROP before CREATE (idempotent re-runs)
      '--if-exists', // Avoid errors dropping non-existent objects
    ]);

    const psqlImport = spawn('docker', [
      'exec',
      '-i',
      CONTAINER_NAME,
      'psql',
      '-U',
      'renly',
      '-d',
      'renly',
    ]);

    // Pipe pg_dump stdout to psql stdin.
    pgDump.stdout.pipe(psqlImport.stdin);

    // Forward stderr for both processes.
    pgDump.stderr.pipe(process.stderr);
    psqlImport.stderr.pipe(process.stderr);

    // Forward psql stdout.
    psqlImport.stdout.pipe(process.stdout);

    // Wait for both processes to complete.
    await new Promise((resolve, reject) => {
      let dumpExited = false;
      let importExited = false;

      const checkComplete = () => {
        if (dumpExited && importExited) resolve();
      };

      pgDump.on('close', (code) => {
        dumpExited = true;
        if (code !== 0) {
          reject(new Error(`pg_dump exited with code ${code}`));
        } else {
          psqlImport.stdin.end();
          checkComplete();
        }
      });

      psqlImport.on('close', (code) => {
        importExited = true;
        if (code !== 0) {
          reject(new Error(`psql import exited with code ${code}`));
        } else {
          checkComplete();
        }
      });

      pgDump.on('error', reject);
      psqlImport.on('error', reject);
    });

    console.log(`\nSuccess! Local database is ready.`);
    console.log(`   - Host:     127.0.0.1`);
    console.log(`   - Port:     ${LOCAL_PORT}`);
    console.log(`   - User:     renly`);
    console.log(`   - Pass:     renly`);
    console.log(`\nDon't forget to update DATABASE_URL in apps/api/.env!`);
  } catch (err) {
    console.error(`Error during fork: ${err.message}`);
    process.exit(1);
  }
}

run();
