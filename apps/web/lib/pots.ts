import type { Pot } from '@/lib/api/pots';

/*
 * A pot's label. A null name is the group's default pot, which A4 deliberately leaves unnamed: the
 * container is not a thing to manage until there is a second one to tell apart. The caller passes the
 * translated fallback, so the rule lives here and the words stay in the locale files.
 *
 * In `lib/` rather than beside the Shared module because the dashboard names pots too — and because a
 * NULL name printed raw is exactly the defect the notification layer shipped ("None is due a new
 * valuation" on a lock screen). One function, so no surface can forget the fallback.
 *
 * Takes only the field it reads, so a caller holding a lighter shape than a full Pot — the dashboard's
 * undivided-pot rows carry an id, a name and a group — does not have to invent one.
 */
export function potLabel(pot: Pick<Pot, 'name'>, fallback: string): string {
  return pot.name?.trim() || fallback;
}
