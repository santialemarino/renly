// How long a toggle that saves on its own waits after the last click before it writes, so a burst of
// clicks on one control becomes one write carrying the final value. Short enough that a click followed
// by a navigation still saves (a pending write goes out at once when the control unmounts).
export const AUTOSAVE_COALESCE_MS = 300;
