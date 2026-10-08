/*
 * What counts as a CONTROL: an element a keyboard stops on in order to act — a link, a button, a form
 * field, or an element with a widget role. Text inside one must not become a second tab stop nested in
 * it (a focusable inside a control is announced badly and leaves an empty extra stop; axe's
 * `nested-interactive`).
 *
 * Deliberately not "anything focusable" (a bare `[tabindex]`): a scroll region that takes focus so the
 * keyboard can scroll it (a `Table` wider than its column) is a stop that may hold stops of its own,
 * and treating it as a control would take every cut text inside it out of the tab order.
 *
 * One definition for both sides: `TruncatingTooltip` decides with it whether its text may be a stop,
 * and the e2e text sweep (`tests/e2e/helpers/text-clipping.ts`) rules with it on what the component did.
 */
export const CONTROL_SELECTOR = [
  'a[href]',
  'button',
  'input:not([type="hidden"])',
  'select',
  'textarea',
  'summary',
  '[role="button"]',
  '[role="link"]',
  '[role="checkbox"]',
  '[role="radio"]',
  '[role="switch"]',
  '[role="tab"]',
  '[role="option"]',
  '[role="menuitem"]',
  '[role="menuitemcheckbox"]',
  '[role="menuitemradio"]',
  '[role="combobox"]',
  '[role="slider"]',
  '[role="spinbutton"]',
  '[role="textbox"]',
  '[role="searchbox"]',
  '[role="treeitem"]',
].join(', ');
