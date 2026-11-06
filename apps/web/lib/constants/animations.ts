// Motion animation durations (seconds) for framer-motion / motion/react transitions.
// Tailwind classes use the equivalent ms values: duration-150, duration-200, duration-300.

// Micro-interactions: icon toggles, chip appear/disappear, hover feedback.
export const ANIMATION_FAST = 0.15;

// Standard transitions: layout shifts, form errors, warnings, section transitions.
export const ANIMATION_DEFAULT = 0.25;

// Page-level entrances: full-page fade-ins, not-found page.
export const ANIMATION_SLOW = 0.5;

/*
 * How long (ms) a route's loading state stays invisible before it fades in. A navigation whose page is
 * ready within it shows no placeholder at all — the page just fades in, whole — and one that takes
 * longer shows the skeleton rather than a screen that looks frozen. It must outlast React's reveal
 * throttle: once a loading state has mounted, React keeps it for ~300 ms however soon the content
 * is ready (measured: a 50 ms and a 150 ms answer both swapped at 283–301 ms), so any delay under
 * that would show every quick load's placeholder for a moment. 350 ms is that throttle plus a
 * frame or two to commit. Read by `PageEntrance`.
 */
export const PAGE_SKELETON_DELAY_MS = 350;

/*
 * How long (ms) a route's loading state stays up once it has started to show, so a load that lands
 * just past the delay does not flash the placeholder for a frame or two. 400 ms covers the fade-in
 * (`ANIMATION_DEFAULT`) plus a beat to read it as a state, and stays under the panels'
 * `LOADING_DISPLAY_FLOOR_MS` because the page has already waited out the delay. A load that never
 * showed the loading state is not held at all. Read by `PageEntrance`.
 */
export const PAGE_SKELETON_MIN_VISIBLE_MS = 400;

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
