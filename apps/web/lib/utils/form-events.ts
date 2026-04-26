import type { KeyboardEvent } from 'react';

// Keys that produce a non-positive value or exponent in <input type="number">.
// Blocked on amount/value inputs that must be >= 0.
const BLOCKED_KEYS = new Set(['-', '+', 'e', 'E']);

// onKeyDown handler that blocks keystrokes which would introduce a negative
// number or scientific notation in a non-negative number input.
export function blockNegativeNumberKeys(e: KeyboardEvent<HTMLInputElement>) {
  if (BLOCKED_KEYS.has(e.key)) {
    e.preventDefault();
  }
}
