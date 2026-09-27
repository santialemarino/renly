// One-year cookie max-age (seconds) — for preference cookies that should outlive sessions.
export const COOKIE_MAX_AGE_1_YEAR = 60 * 60 * 24 * 365;

/*
 * Sidebar progressive disclosure (UX-7): remembers a first-run newcomer's "Show more" choice.
 * Read server-side by the protected layout, written client-side by the sidebar. Lives here (a
 * neutral module) rather than in the sidebar so the server layout doesn't import a client module.
 */
export const SIDEBAR_EXPANDED_COOKIE = 'sidebar-expanded';

/*
 * The id of each layout's `<main>`, which the skip link jumps to. Lives here (a neutral module) rather
 * than beside the skip link so the server layouts rendering the `<main>` don't import a client module.
 */
export const MAIN_CONTENT_ID = 'main-content';
