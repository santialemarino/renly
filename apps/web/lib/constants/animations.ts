// Motion animation durations (seconds) for framer-motion / motion/react transitions.
// Tailwind classes use the equivalent ms values: duration-150, duration-200, duration-300.

// Micro-interactions: icon toggles, chip appear/disappear, hover feedback.
export const ANIMATION_FAST = 0.15;

// Standard transitions: layout shifts, form errors, warnings, section transitions.
export const ANIMATION_DEFAULT = 0.25;

// Page-level entrances: full-page fade-ins, not-found page.
export const ANIMATION_SLOW = 0.5;

// Input debounce: delay before triggering search after keystrokes.
export const DEBOUNCE_MS = 300;

/*
 * How long to wait between closing one entry form and opening the other on a scope swap.
 *
 * Mirrors `duration-200` on the @repo/ui DialogContent. Both dialogs mounted at once would stack two
 * overlays and double the dim; letting the first finish its exit is what makes the swap read as one
 * form changing rather than two dialogs fighting. Shared by the expenses and income toolbars, which
 * is why it lives here rather than in either.
 */
export const DIALOG_EXIT_MS = 200;
