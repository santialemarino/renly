// Feedback categories, in display order ("other" last). Single source of truth for the form select,
// the schema, the admin list badges, and the API type.
export const FEEDBACK_CATEGORIES = ['bug', 'idea', 'question', 'other'] as const;

export type FeedbackCategory = (typeof FEEDBACK_CATEGORIES)[number];

// Max feedback message length; mirrors the API schema cap.
export const MAX_FEEDBACK_LENGTH = 2000;
