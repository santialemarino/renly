/*
 * The animated body of an expanded row's panel (the history under an account or a card), inside a
 * cell that spans the whole table.
 *
 * `w-0 min-w-full` is what stops the panel from widening its table: at zero width it asks the table for
 * no room of its own, and `min-w-full` then stretches it to exactly the cell the other rows sized. Without
 * it, a long line in the panel (a subtitle, a nested table's columns) made the whole table wider than a
 * phone and the panel scrolled sideways with it; now a nested table scrolls inside its own container.
 * The cell itself also needs `whitespace-normal`, or the panel's text inherits the table's `nowrap`.
 */
export const EXPANDED_PANEL_CLASS = 'w-0 min-w-full overflow-hidden';
