// --- DB constraints ---

export const INVESTMENT_NAME_MAX = 255;
export const INVESTMENT_BROKER_MAX = 100;
export const COLLECTION_NAME_MAX = 255;
// Covers both groups.name and group_members.display_name — the same VARCHAR(255) on each.
export const GROUP_NAME_MAX = 255;

// --- API pagination ---

export const API_MAX_PAGE_SIZE = 100;

// --- DB constraints (expenses / income) ---

export const EXPENSE_NOTES_MAX = 500;
export const CREDIT_CARD_NAME_MAX = 100;

// --- API sentinel values ---

export const UNASSIGNED_LABEL = 'Unassigned';
export const CATEGORY_ALL = '__all__';
