import { readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { beforeAll, describe, expect, it, vi } from 'vitest';

/*
 * Every protected page starts its reads as early as their inputs allow.
 *
 * A read that waits for another it does not need costs the whole of that other read on every visit — a
 * full round trip to the API, which on a deployment is the slowest part of a navigation. The ones that
 * crept in were plain sequential `await`s of independent reads (the income page made six reads one
 * after another) and lists started only after the table they sit beside.
 *
 * So each page is RUN, not read: its server function is called with every `@/lib/api` read replaced by
 * a recorder that holds the call open, and the reads are released round by round — every read started
 * so far answers, then the test looks at what the page started next. Every read must start in the
 * first round unless `LATER` names it with the dependency that holds it back (the settings a figure is
 * priced in, the record a page is about), and the number of rounds — the page's longest chain of reads
 * — must be the one stated. The population is derived from the route tree, and every read the page's
 * source calls must have been started (bar the conditional ones `NOT_CALLED` names), so a run that
 * stopped early cannot pass.
 *
 * The answers are a stand-in that is anything a page asks of it (any field, callable, iterable and
 * empty), so a page walks its full path with no fixtures; lists come back empty, which is what makes a
 * page take its first-run branches.
 */

const here = dirname(fileURLToPath(import.meta.url));
const WEB = join(here, '..', '..');
const PROTECTED = join(WEB, 'app', '(protected)');
const API = join(WEB, 'lib', 'api');

const SETTINGS = 'priced or dated by the user settings (currency, timezone), read first';
const RECORD = 'needs the record the page is about first (its group id)';
const SAMPLE = 'the first-run sample flag, read only when the list comes back empty';

/*
 * The reads each page may start after its first round, and why each cannot start sooner; every other
 * read must start in the first. `rounds` is the page's longest chain.
 */
const LATER: Record<string, { rounds: number; reads?: Record<string, string> }> = {
  account: { rounds: 0 },
  accounts: { rounds: 1 },
  'accounts/[id]': { rounds: 1 },
  admin: { rounds: 1 },
  'admin/feedback': { rounds: 1 },
  alerts: { rounds: 1 },
  collections: { rounds: 1 },
  'credit-cards': { rounds: 1 },
  dashboard: {
    rounds: 2,
    reads: {
      getDashboardOverview: SETTINGS,
      getDashboardEvolution: SETTINGS,
      getDashboardComposition: SETTINGS,
      getDashboardLiquidity: SETTINGS,
    },
  },
  data: { rounds: 0 },
  expenses: { rounds: 2, reads: { getExpenses: SETTINGS } },
  'finance-dashboard': {
    rounds: 2,
    reads: {
      getFinanceOverview: SETTINGS,
      getFinanceMonthly: SETTINGS,
      getExpenseBreakdown: SETTINGS,
      getIncomeBreakdown: SETTINGS,
    },
  },
  income: { rounds: 3, reads: { getIncome: SETTINGS, getOnboardingStatus: SAMPLE } },
  installments: { rounds: 2, reads: { getInstallments: SETTINGS } },
  integrations: { rounds: 1 },
  investments: { rounds: 2, reads: { getOnboardingStatus: SAMPLE } },
  'investor-dashboard': {
    rounds: 2,
    reads: {
      getPortfolioMetrics: SETTINGS,
      getPortfolioEvolution: SETTINGS,
      getAllocation: SETTINGS,
      getAllocationByCollection: SETTINGS,
      getInvestmentsSummary: SETTINGS,
    },
  },
  localization: { rounds: 1 },
  notifications: { rounds: 1 },
  'notifications/settings': { rounds: 1 },
  'payment-obligations': { rounds: 2, reads: { getPaymentObligations: SETTINGS } },
  'payments-calendar': { rounds: 2, reads: { getPaymentsCalendar: SETTINGS } },
  preferences: { rounds: 1 },
  shared: { rounds: 1 },
  'shared/[groupId]': {
    rounds: 2,
    reads: { getGroupBalances: `its glance figure is ${SETTINGS}` },
  },
  'shared/[groupId]/share': { rounds: 1 },
  'shared/pots/[id]': { rounds: 2, reads: { getGroup: RECORD } },
  'shared/pots/[id]/buy-out': { rounds: 2, reads: { getGroup: RECORD } },
  'shared/pots/[id]/contribute': { rounds: 1 },
  'shared/pots/[id]/take-out': { rounds: 2, reads: { getGroup: RECORD } },
  snapshots: { rounds: 2, reads: { getSnapshotGrid: SETTINGS } },
  subscriptions: { rounds: 2, reads: { getSubscriptions: SETTINGS } },
};

// Reads a page calls only on a branch this run does not take, and why.
const NOT_CALLED: Record<string, Record<string, string>> = {
  dashboard: { getOnboardingStatus: 'only while onboarding is not completed' },
  'investor-dashboard': { getInvestmentMetrics: 'only when filtered to one investment' },
  'shared/[groupId]/share': {
    getPot: 'only when filling an existing pot (`?pot=`)',
    getPotHoldings: 'only when filling an existing pot (`?pot=`)',
    getPotOwnershipEvents: 'only when filling an existing pot (`?pot=`)',
  },
};

// --- The stand-in answer, and the recorder every read becomes ---

// Anything a page asks of it: any field, callable, iterable (empty), a number or a string.
function anything(): unknown {
  const target = () => undefined;
  return new Proxy(target, {
    get(_, key) {
      if (key === 'then') return undefined;
      if (key === Symbol.iterator) return function* () {};
      if (key === Symbol.toPrimitive) return (hint: string) => (hint === 'number' ? 1 : '1');
      if (key === 'length') return 0;
      return anything();
    },
    apply: () => anything(),
  });
}

interface Call {
  name: string;
  release: () => void;
}

const calls: Call[] = [];

function recorder(name: string) {
  return () =>
    new Promise((resolve) => {
      calls.push({ name, release: () => resolve(anything()) });
    });
}

const NOT_FOUND = new Error('NEXT_NOT_FOUND');

// Every page.tsx under (protected), keyed by its folder.
function protectedPages(): { key: string; file: string }[] {
  const out: { key: string; file: string }[] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir)) {
      const full = join(dir, entry);
      if (statSync(full).isDirectory()) walk(full);
      else if (entry === 'page.tsx') out.push({ key: relative(PROTECTED, dir), file: full });
    }
  };
  walk(PROTECTED);
  return out.sort((a, b) => a.key.localeCompare(b.key));
}

// The `@/lib/api` functions a page's source calls, by their own name.
function readsCalledIn(source: string): string[] {
  const names = new Set<string>();
  for (const match of source.matchAll(/import \{([^}]*)\} from '@\/lib\/api\/[^']+';/g)) {
    for (const raw of match[1]!.split(',')) {
      const binding = /^([a-z]\w*)(?:\s+as\s+(\w+))?$/.exec(raw.trim());
      if (binding && new RegExp(`\\b${binding[2] ?? binding[1]}\\(`).test(source)) {
        names.add(binding[1]!);
      }
    }
  }
  return [...names].sort();
}

const flush = async () => {
  for (let i = 0; i < 20; i += 1) await new Promise((resolve) => setImmediate(resolve));
};

// Runs a page, releasing its reads round by round: the reads each round started, in order.
async function readRounds(file: string): Promise<{ rounds: string[][]; outcome: string }> {
  calls.length = 0;
  const page = (await import(/* @vite-ignore */ file)) as {
    default: (props: unknown) => Promise<unknown>;
  };
  const anyParam = new Proxy({}, { get: () => '1' });
  const run = page
    .default({ params: Promise.resolve(anyParam), searchParams: Promise.resolve({}) })
    .then(
      () => 'rendered',
      (error: unknown) => {
        if (error === NOT_FOUND) return 'not found';
        throw error;
      },
    );
  const rounds: string[][] = [];
  for (;;) {
    await flush();
    const started = calls.splice(0);
    if (started.length === 0) break;
    rounds.push(started.map((call) => call.name));
    for (const call of started) call.release();
  }
  return { rounds, outcome: await run };
}

const PAGES = protectedPages();

beforeAll(async () => {
  vi.doMock('server-only', () => ({}));
  vi.doMock('next/headers', () => ({
    cookies: async () => ({ get: () => undefined }),
    headers: async () => new Headers(),
  }));
  vi.doMock('next/navigation', () => ({
    notFound: () => {
      throw NOT_FOUND;
    },
    redirect: () => {
      throw NOT_FOUND;
    },
  }));
  vi.doMock('next-intl/server', () => ({
    getTranslations: async () => anything(),
    getLocale: async () => 'en',
    getTimeZone: async () => 'UTC',
  }));
  vi.doMock('@/lib/i18n/formatters-server', () => ({ getFormatters: async () => anything() }));
  vi.doMock('@/lib/auth', () => ({ getSession: async () => anything() }));
  vi.doMock('@/lib/utils/page-metadata', () => ({ generatePageMetadata: async () => ({}) }));
  for (const file of readdirSync(API).filter((entry) => entry.endsWith('.ts'))) {
    const specifier = `@/lib/api/${file.replace(/\.ts$/, '')}`;
    vi.doMock(specifier, async (importOriginal) => {
      const original = await importOriginal<Record<string, unknown>>();
      return Object.fromEntries(
        Object.entries(original).map(([name, value]) => [
          name,
          typeof value === 'function' && /^[a-z]/.test(name) ? recorder(name) : value,
        ]),
      );
    });
  }
}, 60_000);

describe('protected page read rounds', () => {
  it('covers every protected page, and no page that is gone', () => {
    expect(PAGES.length).toBeGreaterThan(25);
    expect(PAGES.map((page) => page.key)).toEqual(Object.keys(LATER).sort());
    for (const [key, { rounds, reads }] of Object.entries(LATER)) {
      expect(
        rounds <= 1 || Object.keys(reads ?? {}).length > 0,
        `${key}: rounds without a reason`,
      ).toBe(true);
    }
  });

  it.each(PAGES.map((page) => [page.key, page.file]))(
    '%s starts each read as soon as its inputs exist',
    async (key, file) => {
      const { rounds, outcome } = await readRounds(file);
      const started = new Set(rounds.flat());
      const expected = readsCalledIn(readFileSync(file, 'utf8')).filter(
        (name) => !(name in (NOT_CALLED[key] ?? {})),
      );
      expect(
        expected.filter((name) => !started.has(name)),
        `${key} (${outcome}) never started these reads, so the run proves nothing about them`,
      ).toEqual([]);
      expect(
        [...new Set(rounds.slice(1).flat())].sort(),
        `${key} started these after its first round: ${JSON.stringify(rounds)}`,
      ).toEqual(Object.keys(LATER[key]?.reads ?? {}).sort());
      expect(
        rounds.length,
        `${key} read in ${rounds.length} rounds: ${JSON.stringify(rounds)}`,
      ).toBe(LATER[key]?.rounds);
    },
    30_000,
  );
});
