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
 * — must be the one stated. Within a round the reads answer one at a time, inputs first, so a held-back
 * read must also start on the answer it names and not only once a whole round is in. Every page — and
 * the protected layout, which renders around all of them — runs twice: for an account that finished
 * onboarding and for one still in it, whose welcome reads must not hold the others back. The population
 * is derived from the route tree, and every read the page's source calls must have been started (bar
 * the conditional ones `NOT_CALLED` names), so a run that stopped early cannot pass.
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
  // The protected layout, which renders around every page.
  'layout.tsx': { rounds: 1 },
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

const WELCOME = 'the first-run checklist, read only while onboarding is not completed';

/*
 * Where an account still onboarding reads differently, the entries that replace `LATER`'s: a read that
 * only a newcomer makes must start with the others its inputs allow, not hold them back.
 */
const LATER_FOR_NEWCOMER: typeof LATER = {
  'layout.tsx': { rounds: 2, reads: { getOnboardingStatus: `${WELCOME}, so ${SETTINGS}` } },
  dashboard: {
    rounds: 2,
    reads: {
      getDashboardOverview: SETTINGS,
      getDashboardEvolution: SETTINGS,
      getDashboardComposition: SETTINGS,
      getDashboardLiquidity: SETTINGS,
      getOnboardingStatus: `${WELCOME}, so ${SETTINGS}`,
    },
  },
};

// The account states every page is run in: the stand-in settings say onboarding is done, or not.
const ACCOUNTS = [
  { name: 'onboarded', onboardingCompleted: true, later: LATER },
  { name: 'newcomer', onboardingCompleted: false, later: { ...LATER, ...LATER_FOR_NEWCOMER } },
] as const;

// Reads an onboarded account never makes, so its run does not start them.
const NOT_CALLED_ONCE_ONBOARDED: Record<string, Record<string, string>> = {
  'layout.tsx': { getOnboardingStatus: WELCOME },
  dashboard: { getOnboardingStatus: WELCOME },
};

// Reads a page calls only on a branch neither run takes, and why.
const NOT_CALLED: Record<string, Record<string, string>> = {
  'investor-dashboard': { getInvestmentMetrics: 'only when filtered to one investment' },
  'shared/pots/[id]': {
    getPotDollarRate: 'only when the pot is hidden from the reader, who may still own part of it',
  },
  'shared/[groupId]/share': {
    getPot: 'only when filling an existing pot (`?pot=`)',
    getPotHoldings: 'only when filling an existing pot (`?pot=`)',
    getPotOwnershipEvents: 'only when filling an existing pot (`?pot=`)',
  },
};

// --- The stand-in answer, and the recorder every read becomes ---

// The fields the stand-in answers with a fixed value, on every read and at any depth.
const fixed: Record<string, unknown> = { onboardingCompleted: true };

// Anything a page asks of it: any field, callable, iterable (empty), a number or a string.
function anything(): unknown {
  const target = () => undefined;
  return new Proxy(target, {
    get(_, key) {
      if (key === 'then') return undefined;
      if (key === Symbol.iterator) return function* () {};
      if (key === Symbol.toPrimitive) return (hint: string) => (hint === 'number' ? 1 : '1');
      if (key === 'length') return 0;
      if (typeof key === 'string' && key in fixed) return fixed[key];
      return anything();
    },
    apply: () => anything(),
  });
}

interface Call {
  name: string;
  release: () => void;
}

// The read whose answer a held-back read was waiting for, by the reason `LATER` gives for it.
function unlockersFor(reason: string): string[] {
  if (reason.includes(SETTINGS)) return ['getSettings', 'getPageSettings'];
  if (reason === RECORD) return ['getPot'];
  if (reason === SAMPLE) return ['getIncome', 'getInvestments'];
  throw new Error(`no unlocking read known for: ${reason}`);
}

// Released first within a round, so a read waiting on one of them alone starts before the others answer.
const RELEASED_FIRST = ['getSettings', 'getPageSettings', 'getPot', 'getIncome', 'getInvestments'];

const calls: Call[] = [];

function recorder(name: string) {
  return () =>
    new Promise((resolve) => {
      calls.push({ name, release: () => resolve(anything()) });
    });
}

const NOT_FOUND = new Error('NEXT_NOT_FOUND');

// Every page.tsx under (protected), keyed by its folder, and the protected layout.
function protectedPages(): { key: string; file: string }[] {
  const out: { key: string; file: string }[] = [
    { key: 'layout.tsx', file: join(PROTECTED, 'layout.tsx') },
  ];
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

/*
 * Runs a page, releasing its reads round by round — and within a round one at a time, the inputs other
 * reads wait on first — so each later read is attributed to the answer that let it start. Returns the
 * reads each round started, and for every read the one whose answer came just before it started.
 */
async function readRounds(
  file: string,
): Promise<{ rounds: string[][]; unlockedBy: Map<string, string>; outcome: string }> {
  calls.length = 0;
  const page = (await import(/* @vite-ignore */ file)) as {
    default: (props: unknown) => Promise<unknown>;
  };
  const anyParam = new Proxy({}, { get: () => '1' });
  const run = page
    .default({
      params: Promise.resolve(anyParam),
      searchParams: Promise.resolve({}),
      children: null,
    })
    .then(
      () => 'rendered',
      (error: unknown) => {
        if (error === NOT_FOUND) return 'not found';
        throw error;
      },
    );
  const rounds: string[][] = [];
  const unlockedBy = new Map<string, string>();
  await flush();
  let round = calls.splice(0);
  while (round.length > 0) {
    rounds.push(round.map((call) => call.name));
    const ordered = [...round].sort(
      (a, b) => Number(!RELEASED_FIRST.includes(a.name)) - Number(!RELEASED_FIRST.includes(b.name)),
    );
    const next: Call[] = [];
    for (const call of ordered) {
      call.release();
      await flush();
      for (const started of calls.splice(0)) {
        if (!unlockedBy.has(started.name)) unlockedBy.set(started.name, call.name);
        next.push(started);
      }
    }
    round = next;
  }
  return { rounds, unlockedBy, outcome: await run };
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
  // A signed-in session with no refresh error, or the layout redirects before it reads anything.
  vi.doMock('@/lib/auth', () => ({
    getSession: async () => ({ user: { email: 'reader@example.com', isAdmin: false } }),
  }));
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
    expect(PAGES.map((page) => page.key).sort()).toEqual(Object.keys(LATER).sort());
    for (const [key, { rounds, reads }] of Object.entries({ ...LATER, ...LATER_FOR_NEWCOMER })) {
      expect(
        rounds <= 1 || Object.keys(reads ?? {}).length > 0,
        `${key}: rounds without a reason`,
      ).toBe(true);
    }
  });

  it.each(
    ACCOUNTS.flatMap((account) =>
      PAGES.map((page) => [page.key, account.name, page.file, account] as const),
    ),
  )(
    '%s (%s) starts each read as soon as its inputs exist',
    async (key, _name, file, account) => {
      fixed.onboardingCompleted = account.onboardingCompleted;
      const { rounds, unlockedBy, outcome } = await readRounds(file);
      const started = new Set(rounds.flat());
      const notCalled = {
        ...NOT_CALLED[key],
        ...(account.onboardingCompleted ? NOT_CALLED_ONCE_ONBOARDED[key] : {}),
      };
      const expected = readsCalledIn(readFileSync(file, 'utf8')).filter(
        (name) => !(name in notCalled),
      );
      expect(
        expected.filter((name) => !started.has(name)),
        `${key} (${outcome}) never started these reads, so the run proves nothing about them`,
      ).toEqual([]);
      expect(
        [...new Set(rounds.slice(1).flat())].sort(),
        `${key} started these after its first round: ${JSON.stringify(rounds)}`,
      ).toEqual(Object.keys(account.later[key]?.reads ?? {}).sort());
      expect(
        rounds.length,
        `${key} read in ${rounds.length} rounds: ${JSON.stringify(rounds)}`,
      ).toBe(account.later[key]?.rounds);
      // And each held-back read started on the answer it needs, not after others it does not.
      for (const [read, reason] of Object.entries(account.later[key]?.reads ?? {})) {
        expect(
          unlockersFor(reason),
          `${key}: ${read} started only once ${unlockedBy.get(read)} answered`,
        ).toContain(unlockedBy.get(read));
      }
    },
    30_000,
  );
});
