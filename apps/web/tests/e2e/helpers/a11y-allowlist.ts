/*
 * The ONE place an axe finding may be tolerated, and the rules an entry has to meet.
 *
 * The accessibility scans are zero-tolerance: any violation fails the spec that found it. An entry here
 * suppresses exactly one rule on exactly the elements one selector matches — never a rule everywhere
 * (`disableRules`), never an element for every rule (`exclude`) — and only until its `revisitBy` date.
 * Pure data and a pure validator, no Playwright import, because `tests/unit/a11y-allowlist.test.ts`
 * checks every entry:
 *
 *   * `revisitBy` has not passed — an exception is a dated debt, not a baseline, so on that day the
 *     unit suite goes red and the entry is either fixed or re-argued;
 *   * the selector still matches something — it must be built from `[data-testid="…"]` or
 *     `[data-slot="…"]` attributes, and each value must still be written somewhere in the web app or
 *     `packages/ui`. A selector nothing renders any more suppresses nothing today and whatever happens
 *     to take the name tomorrow;
 *   * the rule, the reason and the date are real values, not placeholders.
 *
 * It should stay as short as it can; each entry below is a debt with a date.
 */

export interface A11yAllowListEntry {
  // The axe rule id the exception is for, e.g. `color-contrast`.
  rule: string;
  // Which elements it covers. Only testid/slot attribute selectors, so the unit test can find them.
  selector: string;
  // Why the finding cannot be fixed yet, and what would fix it.
  reason: string;
  // ISO date (YYYY-MM-DD) after which the entry fails the unit suite.
  revisitBy: string;
}

export const A11Y_ALLOW_LIST: readonly A11yAllowListEntry[] = [
  {
    rule: 'scrollable-region-focusable',
    selector: '[data-slot="command-list"]',
    reason:
      'cmdk renders its listbox with a hardcoded tabIndex={-1}, after the props, so no caller can make it a Tab stop. Every combobox moves focus INTO the list when it opens and the arrow keys move the active option, which scrolls it, so a keyboard reaches every row. Fix by replacing cmdk or overriding the attribute on mount.',
    revisitBy: '2026-12-31',
  },
];

// The attribute forms an entry's selector may be built from, and how each is written in source.
const SELECTOR_ATTRIBUTE = /\[(data-testid|data-slot)="([^"]+)"\]/g;
const SOURCE_FORMS: Record<string, (value: string) => string[]> = {
  // `testId="x"` is how the components that declare their props take a testid (see e2e-testing).
  'data-testid': (value) => [`data-testid="${value}"`, `testId="${value}"`],
  'data-slot': (value) => [`data-slot="${value}"`],
};

/*
 * What is wrong with each entry, as messages; empty when every entry holds. `today` is YYYY-MM-DD and
 * `sources` the text of every file the selectors may point into.
 */
export function allowListProblems(
  entries: readonly A11yAllowListEntry[],
  today: string,
  sources: readonly string[],
): string[] {
  const problems: string[] = [];
  for (const entry of entries) {
    const where = `${entry.rule} on ${entry.selector}`;
    if (!/^[a-z0-9-]+$/.test(entry.rule))
      problems.push(`${where}: "${entry.rule}" is not a rule id`);
    if (entry.reason.trim().length < 20) problems.push(`${where}: the reason says nothing`);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(entry.revisitBy) || Number.isNaN(Date.parse(entry.revisitBy)))
      problems.push(`${where}: revisitBy "${entry.revisitBy}" is not a YYYY-MM-DD date`);
    else if (entry.revisitBy < today)
      problems.push(`${where}: revisitBy ${entry.revisitBy} has passed — fix it or re-argue it`);

    const attributes = [...entry.selector.matchAll(SELECTOR_ATTRIBUTE)];
    if (attributes.length === 0)
      problems.push(`${where}: the selector must name a [data-testid] or [data-slot] attribute`);
    for (const [, attribute = '', value = ''] of attributes) {
      const forms = SOURCE_FORMS[attribute]?.(value) ?? [];
      if (!sources.some((source) => forms.some((form) => source.includes(form))))
        problems.push(`${where}: nothing renders ${attribute}="${value}" any more`);
    }
  }
  return problems;
}
