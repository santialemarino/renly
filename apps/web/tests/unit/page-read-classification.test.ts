import { readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

/*
 * Every server read a protected page makes is a DECISION about what its failure costs.
 *
 * Every `lib/api` read shares one `if (!res.ok) throw`. Awaited bare, that throw takes the page to the
 * error boundary; wrapped in `.catch(() => <empty>)`, it costs only the control the read feeds. Both are
 * right for some reads and wrong for others — a list page's rows must fail loudly (an empty table would
 * claim there is nothing), while a picker's options must not take the page down with them. The failure
 * this file exists for is a read that got the loud treatment by DEFAULT: the next read somebody adds
 * with a bare await is primary without anyone having decided it.
 *
 * So the population is derived — every function a page imports from `@/lib/api/*`, at every call site —
 * and every call that is not followed by `.catch(` must appear in `PRIMARY` with the reason it may fail
 * the page. An unclassified bare read fails here, and so does a stale entry (a read listed as primary
 * that the page no longer makes bare), so the table cannot drift into describing a page that has moved
 * on. Reads that never throw by construction are in `NEVER_THROWS`, each checked against its source.
 */

const here = dirname(fileURLToPath(import.meta.url));
const WEB = join(here, '..', '..');
const PROTECTED = join(WEB, 'app', '(protected)');

// Reads that catch internally and therefore cannot reach a boundary, with the text that proves it.
const NEVER_THROWS: Record<string, { file: string; proof: RegExp }> = {
  // Both of its reads are caught inside it.
  getPageSettings: {
    file: 'lib/api/settings.ts',
    proof:
      /getSettings\(\)\.catch\(\(\) => null\),\s*getCreditCards\(\{ showArchived: true \}\)\.catch\(\(\) => \[\]\)/,
  },
  // Delegates to the auth-api fetch, which answers any failure with the invite-only default.
  getSignupContext: {
    file: 'lib/auth-api.ts',
    proof:
      /export async function getSignupContext[\s\S]*?try \{[\s\S]*?\} catch \{\s*return \{ mode: 'invite', invitedEmail: null \};/,
  },
};

const LIST = 'the page IS this list — an empty table would claim there is nothing';
const FIGURES = "the page's figures; the page's own try turns a failure into its inline load error";
const NOT_FOUND = 'the record the page is about: a 404 is notFound(), anything else must be loud';

// Every bare read a protected page makes, and why its failure may take the page.
const PRIMARY: Record<string, Record<string, string>> = {
  accounts: { getAccountsGrouped: LIST },
  'accounts/[id]': { getAccount: NOT_FOUND },
  collections: { getCollections: LIST },
  'credit-cards': { getCreditCards: LIST },
  dashboard: {
    getDashboardComposition: FIGURES,
    getDashboardEvolution: FIGURES,
    getDashboardLiquidity: FIGURES,
    getDashboardOverview: FIGURES,
  },
  expenses: { getExpenses: LIST },
  'finance-dashboard': {
    getExpenseBreakdown: FIGURES,
    getFinanceMonthly: FIGURES,
    getFinanceOverview: FIGURES,
    getIncomeBreakdown: FIGURES,
  },
  income: { getIncome: LIST },
  installments: { getInstallments: LIST },
  investments: { getInvestments: LIST },
  'investor-dashboard': {
    getAllocation: FIGURES,
    getAllocationByCollection: FIGURES,
    getInvestmentsSummary: FIGURES,
    getPortfolioEvolution: FIGURES,
    getPortfolioMetrics: FIGURES,
  },
  'payment-obligations': { getPaymentObligations: LIST },
  'payments-calendar': { getPaymentsCalendar: LIST },
  shared: { getGroups: LIST },
  'shared/[groupId]': {
    getGroup: NOT_FOUND,
    getPots: 'an empty pots section would say the group shares nothing',
    getSharedExpenses:
      'the flow half: "nothing shared yet" about a group that shared plenty is a lie',
    getSharedIncome:
      'the flow half: "nothing shared yet" about a group that shared plenty is a lie',
    getGroupBalances: 'where everyone stands — the question the page opens with',
    getGroupSettlements: 'what has cleared a balance: an empty list would misstate every position',
    getAccounts:
      "a settlement leg's edit dialog appends the stored account from this list; without it an attached (archived) leg reads as cleared while the form still holds its id",
  },
  'shared/[groupId]/share': {
    getGroup: NOT_FOUND,
    getPot: NOT_FOUND,
    getPotHoldings: NOT_FOUND,
    getPotOwnershipEvents: NOT_FOUND,
    getAccounts: 'the eligible set IS the page: an empty list would say there is nothing to share',
    getInvestments:
      'the eligible set IS the page: an empty list would say there is nothing to share',
  },
  'shared/pots/[id]': {
    getGroup: NOT_FOUND,
    getPot: NOT_FOUND,
    getPotHoldings: NOT_FOUND,
    getPotOwnershipEvents: NOT_FOUND,
    getPotSeries: NOT_FOUND,
  },
  'shared/pots/[id]/buy-out': { getGroup: NOT_FOUND, getPot: NOT_FOUND },
  'shared/pots/[id]/contribute': {
    getPot: NOT_FOUND,
    getContributableHoldings:
      'the step IS choosing from these: empty would claim nothing can be added',
  },
  'shared/pots/[id]/take-out': {
    getGroup: NOT_FOUND,
    getPot: NOT_FOUND,
    getPotHoldings: NOT_FOUND,
  },
  snapshots: { getSnapshotGrid: LIST },
  subscriptions: { getSubscriptions: LIST },
};

// Every directory under app/(protected) holding a page.tsx, relative to it.
function protectedPageDirs(): string[] {
  const out: string[] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir)) {
      const full = join(dir, entry);
      if (statSync(full).isDirectory()) walk(full);
      else if (entry === 'page.tsx') out.push(relative(PROTECTED, dir));
    }
  };
  walk(PROTECTED);
  return out.sort();
}

// The value-level functions a page imports from `@/lib/api/*` (types and constants excluded).
function apiReads(source: string): string[] {
  const names = new Set<string>();
  for (const match of source.matchAll(/import \{([^}]*)\} from '@\/lib\/api\/[^']+';/g)) {
    for (const raw of match[1]!.split(',')) {
      const name = raw.trim();
      if (/^get[A-Z]\w*$/.test(name)) names.add(name);
    }
  }
  return [...names];
}

// The reads a page makes BARE — at least one call site not followed by `.catch(`.
function bareReads(source: string): string[] {
  const bare = new Set<string>();
  for (const name of apiReads(source)) {
    for (const match of source.matchAll(new RegExp(`\\b${name}\\(`, 'g'))) {
      let i = match.index! + match[0].length;
      for (let depth = 1; depth > 0; i += 1) {
        if (source[i] === '(') depth += 1;
        else if (source[i] === ')') depth -= 1;
      }
      if (!source.startsWith('.catch(', i)) bare.add(name);
    }
  }
  return [...bare].sort();
}

const PAGE_DIRS = protectedPageDirs();

describe('protected page read classification', () => {
  it('derives reads from real pages, caught and bare alike', () => {
    // A scan that found nothing would pass every assertion below.
    const expenses = readFileSync(join(PROTECTED, 'expenses', 'page.tsx'), 'utf8');
    expect(apiReads(expenses)).toEqual(expect.arrayContaining(['getExpenses', 'getAccounts']));
    expect(bareReads(expenses)).toContain('getExpenses');
    expect(bareReads(expenses)).not.toContain('getAccounts');
  });

  it.each(PAGE_DIRS)('%s makes no unclassified bare read', (dir) => {
    const bare = bareReads(readFileSync(join(PROTECTED, dir, 'page.tsx'), 'utf8'));
    const classified = PRIMARY[dir] ?? {};
    const unclassified = bare.filter((name) => !(name in classified) && !(name in NEVER_THROWS));
    expect(unclassified, `bare reads in ${dir} need .catch or a PRIMARY entry`).toEqual([]);

    const stale = Object.keys(classified).filter((name) => !bare.includes(name));
    expect(stale, `PRIMARY lists reads ${dir} no longer makes bare`).toEqual([]);
  });

  it('names only pages that exist', () => {
    expect(Object.keys(PRIMARY).filter((dir) => !PAGE_DIRS.includes(dir))).toEqual([]);
  });

  it.each(Object.entries(NEVER_THROWS))('%s catches every failure itself', (_, { file, proof }) => {
    expect(readFileSync(join(WEB, file), 'utf8')).toMatch(proof);
  });
});
