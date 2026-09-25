import { execSync, spawn } from 'child_process';
import fs from 'fs';
import path from 'path';

const ENV_PATH = path.join(process.cwd(), 'apps/api/.env');
const ROLES_PATH = path.join(process.cwd(), 'apps/api/database/00_roles.sql');

const LOCAL_PORT = process.argv[2] || '5433';
const CONTAINER_NAME = `renly-db-local-${LOCAL_PORT}`;

const LOCAL_HOSTS = new Set(['localhost', '127.0.0.1', '::1', '']);

// Parse the SOURCE url from a .env file: DATABASE_ADMIN_URL, falling back to DATABASE_URL.
// Handles both postgresql:// and postgresql+asyncpg:// (SQLAlchemy async format).
//
// The admin url first, and that is the whole correctness of this script. It used to read
// DATABASE_URL, which names the RESTRICTED request role — a role with no user context and, now that
// the tables FORCE row-level security, no exemption from any policy. The fork came up EMPTY and the
// script printed "Success!", which is the failure mode its sibling db-backup.mjs already guards
// against. pg_dump does exit 1 under FORCE rather than writing nothing silently, but a script that
// reaches for the wrong role at all is one restore away from the quiet version.
function parseEnv(filePath) {
  const content = fs.readFileSync(filePath, 'utf8');

  const match =
    content.match(/^DATABASE_ADMIN_URL\s*=\s*(.+)$/m) ??
    content.match(/^DATABASE_URL\s*=\s*(.+)$/m);
  if (!match) throw new Error('Neither DATABASE_ADMIN_URL nor DATABASE_URL found in apps/api/.env');

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

    // 2. Provision the roles the app connects as. A fresh container has only the `renly` superuser,
    // and roles are CLUSTER-global, so pg_dump never carries them: without this the fork has no
    // renly_app or renly_admin to log in as, and every grant and ownership the dump names fails to
    // apply. The same file a new database is provisioned from, so the fork cannot drift from it.
    console.log(`Provisioning roles (00_roles.sql)...`);
    execSync(`docker exec -i ${CONTAINER_NAME} psql -q -v ON_ERROR_STOP=1 -U renly -d renly`, {
      input: fs.readFileSync(ROLES_PATH, 'utf8'),
      stdio: ['pipe', 'inherit', 'inherit'],
    });

    // 3. Sync data
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
      // Ownership and grants are kept, not stripped: they ARE the isolation model. renly_app's DML
      // grants and the policy helpers' owner (renly_policy_definer) come across exactly as the source
      // has them, onto the roles provisioned above. A source whose owner is not named `renly` logs one
      // error per OWNER TO line and leaves those objects owned by the fork's superuser, which still
      // works — a superuser owner reads everything, as on any local cluster.
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

    console.log(`\nSuccess! Local database is ready on 127.0.0.1:${LOCAL_PORT}, database renly.`);
    console.log(
      `\nPoint BOTH urls in apps/api/.env at it — leaving one on the source splits the app across`,
    );
    console.log(`two databases (requests on the fork, the scheduler and logins on the source):`);
    console.log(
      `  DATABASE_URL=postgresql+asyncpg://renly_app:renly_app@localhost:${LOCAL_PORT}/renly            (restricted, RLS-subject request role)`,
    );
    console.log(
      `  DATABASE_ADMIN_URL=postgresql+asyncpg://renly_admin:renly_admin@localhost:${LOCAL_PORT}/renly  (BYPASSRLS: scheduler, migrations, auth bootstrap)`,
    );
    console.log(`\nFor psql, the fork's superuser is renly / renly.`);
  } catch (err) {
    console.error(`Error during fork: ${err.message}`);
    process.exit(1);
  }
}

run();
