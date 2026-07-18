// One-year cookie max-age (seconds) — for preference cookies that should outlive sessions.
export const COOKIE_MAX_AGE_1_YEAR = 60 * 60 * 24 * 365;

/*
 * Sidebar progressive disclosure (UX-7): remembers a first-run newcomer's "Show more" choice.
 * Read server-side by the protected layout, written client-side by the sidebar. Lives here (a
 * neutral module) rather than in the sidebar so the server layout doesn't import a client module.
 */
export const SIDEBAR_EXPANDED_COOKIE = 'sidebar-expanded';
