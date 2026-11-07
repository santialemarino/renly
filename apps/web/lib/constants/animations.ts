// Motion animation durations (seconds) for framer-motion / motion/react transitions.
// Tailwind classes use the equivalent ms values: duration-150, duration-200, duration-300.

// Micro-interactions: icon toggles, chip appear/disappear, hover feedback.
export const ANIMATION_FAST = 0.15;

// Standard transitions: layout shifts, form errors, warnings, section transitions.
export const ANIMATION_DEFAULT = 0.25;

// Page-level entrances: full-page fade-ins, not-found page.
export const ANIMATION_SLOW = 0.5;

/*
 * How long (ms) a navigation may run before it shows that it is still going: the progress bar across the
 * top of the main column and, when it changes page, the dimmed old page. A navigation that lands sooner
 * shows neither — only the sidebar item it activated on the click — so a fast page swaps in with no
 * flash of a loading state. Read by `NavigationPendingProvider`.
 */
export const NAVIGATION_PENDING_DELAY_MS = 150;

// One sweep (ms) of the navigation progress bar's segment across the main column.
export const NAVIGATION_PROGRESS_SWEEP_MS = 1000;

// Minimum time (ms) a loading line stays up before the content replaces it, so a fast load crossfades
// once instead of flashing loading → content. Shared by the expandable rows' history panels.
export const LOADING_DISPLAY_FLOOR_MS = 500;

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
