// --- DB constraints ---

export const INVESTMENT_NAME_MAX = 255;
export const INVESTMENT_BROKER_MAX = 100;
export const COLLECTION_NAME_MAX = 255;
// Covers both groups.name and group_members.display_name — the same VARCHAR(255) on each.
export const GROUP_NAME_MAX = 255;

// --- API pagination ---

// The page size the API serves when a caller does not ask (SEC-11's DEFAULT_PAGE_SIZE). Stated here so
// a page that needs the count before the response arrives — to size a skeleton, or to turn a page
// number into a row offset — reads the same number the server used rather than guessing one.
export const API_DEFAULT_PAGE_SIZE = 25;

export const API_MAX_PAGE_SIZE = 100;

// The largest page number the API will serve (SEC-11's MAX_PAGE). Mirrored here so a hand-edited URL
// is refused before a request is made rather than after: past this the page becomes an OFFSET outside
// Postgres' bigint range, which the API now answers with a 422 instead of a 500.
export const API_MAX_PAGE = 1_000_000;

// --- DB constraints (expenses / income) ---

// The cap on EVERY free-text `notes` field, not only an expense's: the API puts `max_length=500` on the
// notes of every request schema, and `notes-cap.test.ts` holds each web form to it.
export const EXPENSE_NOTES_MAX = 500;
export const CREDIT_CARD_NAME_MAX = 100;

// --- API query limits ---

// The API's `SEARCH_MAX_LENGTH` on every list `search` parameter: the longest column any search matches.
// Past it the API answers 422, which a list page reads as a load failure — so the box stops there.
export const SEARCH_MAX = 500;

// --- API sentinel values ---

export const UNASSIGNED_LABEL = 'Unassigned';
export const CATEGORY_ALL = '__all__';
