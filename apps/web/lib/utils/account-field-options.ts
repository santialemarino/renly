import type { Account } from '@/lib/api/accounts';

/*
 * Pure decision layer behind the shared AccountField control: which options a stored value and a
 * currency should produce, and whether a now-invalid selection must be cleared. Extracted from the
 * component so the rules are unit-testable — the component itself renders a Radix popover, which the
 * jsdom test harness cannot mount (it resolves two React copies), and these are the parts worth
 * pinning: they decide whether a stored link renders at all.
 *
 * Labels stay in the component: each option carries its `kind` and the raw account, and the component
 * resolves the localized string. That keeps this module free of i18n and the copy in one place.
 */

// One row of the account picker. `none` is the always-present sentinel (the API stores null);
// `archived` marks a stored link the filtered list can't offer, so it can be labelled as such.
export type AccountOption =
  | { kind: 'none'; noMatchingCurrency: boolean }
  | { kind: 'account'; account: Account }
  | { kind: 'archived'; account: Account };

// Whether the currently-selected account must be dropped because the entry's currency moved away from
// it. Only ACTIVE accounts are cleared: an archived link is absent from the offerable list, and
// clearing it would silently drop the link of an entry the user is merely editing.
export function shouldClearAccountLink(
  selected: Account | undefined,
  currency: string | undefined,
): boolean {
  return !!selected?.isActive && !!currency && selected.currency !== currency;
}

/*
 * The picker's options, or `null` when the field should not render at all — nothing to offer and
 * nothing stored, so a user with no accounts (or only archived ones) never meets a dead control.
 *
 * A user who DOES have active accounts but none in this currency still gets the (disabled) field, so
 * the reason there is nothing to pick is stated rather than left as a silent absence.
 */
export function buildAccountFieldOptions(
  accounts: Account[],
  currency: string | undefined,
  selectedId: number | null | undefined,
): AccountOption[] | null {
  const matching = accounts.filter((a) => a.isActive && (!currency || a.currency === currency));
  const selected = accounts.find((a) => a.id === selectedId);
  /*
   * A stored link the filtered list can't offer (archived, or in another currency that
   * shouldClearAccountLink deliberately spares) still has to render: the combobox falls back to its
   * placeholder when no option matches the value, so the trigger would go BLANK while form state still
   * held the id — the field would read as cleared and a save would silently keep the old link.
   */
  const unofferable =
    selected && !matching.some((a) => a.id === selected.id)
      ? [
          {
            kind: selected.isActive ? ('account' as const) : ('archived' as const),
            account: selected,
          },
        ]
      : [];

  // No active account to offer (which also means `matching` is empty) and no stored link to show.
  if (unofferable.length === 0 && !accounts.some((a) => a.isActive)) return null;

  return [
    { kind: 'none', noMatchingCurrency: matching.length === 0 },
    ...matching.map((account) => ({ kind: 'account' as const, account })),
    ...unofferable,
  ];
}
