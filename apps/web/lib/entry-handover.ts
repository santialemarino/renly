import type { ExpenseCategory, IncomeCategory } from '@/lib/constants/categories';

/*
 * What one entry form hands another when the user swaps which record they are writing, so nothing
 * typed is lost across the swap.
 *
 * There are two swaps and they carry different things. The SCOPE swap (private ↔ a group's shared
 * form) keeps the category, because both of its sides are the same list. The TYPE swap
 * (expense ↔ income) drops it, because the two lists' categories do not overlap. One function each,
 * both here, so there is a single place that says what survives which swap.
 *
 * Pure and under lib/ rather than beside the two controls that perform the swaps, for the reason every
 * rule in this app lives here: those controls render Radix primitives, which cannot be mounted in the
 * web unit suite at all — so a rule inside one is a rule nothing can test.
 */

/*
 * Deliberately only the fields the records genuinely share. A shared expense has no obligation,
 * subscription or installment link; a private one has no participants or split; a shared income row
 * has a destination and a source asset that no private entry has; and their funding is the same
 * question with opposite answers — a private entry cannot touch joint money at all, which is the whole
 * reason the scope control exists. Carrying any of those across would mean seeding a field the
 * receiving form never asked about.
 *
 * Generic over the category so each list keeps its own enum: an expense category is not an income
 * category, and a handover that typed them as plain strings would let one reach the other's picker,
 * which renders a blank field and submits a value the API refuses with a 422.
 */
export interface EntryHandover<TCategory extends string = string> {
  date?: string;
  amount?: string;
  currency?: string;
  category?: TCategory;
  notes?: string;
}

// The two lists' handovers, bound to their own category enum. Named here rather than beside each form
// so there is one place that says what crosses a swap and one place that says it per list.
export type ExpenseHandover = EntryHandover<ExpenseCategory>;
export type IncomeHandover = EntryHandover<IncomeCategory>;

// Narrows either form's values to what crosses a SCOPE swap. One function so the two directions cannot
// come to disagree about which fields survive it.
export function toHandover<TCategory extends string>(
  values: EntryHandover<TCategory>,
): EntryHandover<TCategory> {
  return {
    date: values.date,
    amount: values.amount,
    currency: values.currency,
    category: values.category,
    notes: values.notes,
  };
}

/*
 * Narrows either form's values to what crosses a TYPE swap: the date, the amount, the currency and the
 * notes — and deliberately NOT the category.
 *
 * An expense category is not an income category and the two enums do not overlap, so carrying one
 * across would put a value in the receiving form's picker that it cannot render (a blank field) and
 * that the API refuses with a 422. `EntryHandover<never>` is what states that in the type: it is
 * assignable to either list's handover precisely because it can never carry a category at all.
 */
export function toTypeHandover(values: EntryHandover<string>): EntryHandover<never> {
  return {
    date: values.date,
    amount: values.amount,
    currency: values.currency,
    notes: values.notes,
  };
}
