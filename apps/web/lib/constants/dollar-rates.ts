/*
 * Which USD/ARS rate a SHARED figure converts at, in the order the personal setting offers the same
 * three. Two things carry one: a pot, whose value, unit price and every movement priced against it
 * convert at the pot's rate, and a group, whose settling up — how much of one currency's debt a payment
 * in another clears, and the "at today's rate" balance — converts at the group's. One rate for everybody
 * rather than each reader's own, so every member sees the same figures; only converting them into a
 * reader's own display currency follows their personal preference.
 */
export const SHARED_DOLLAR_RATES = ['oficial', 'mep', 'blue'] as const;

export type SharedDollarRate = (typeof SHARED_DOLLAR_RATES)[number];

// Whether a string from a stored payload names one of the three, so it can be labelled.
export function isSharedDollarRate(value: string): value is SharedDollarRate {
  return (SHARED_DOLLAR_RATES as readonly string[]).includes(value);
}

// What a group settles at, and a pot starts on, when nobody has chosen. Mirrors the API's own defaults.
export const DEFAULT_SHARED_DOLLAR_RATE: SharedDollarRate = 'mep';
