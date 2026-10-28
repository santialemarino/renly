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
 * Two edges, decided against that definition:
 *   * an editable region (`contenteditable`) IS one: the keyboard stops on it to type, and text inside
 *     it is content being edited, never a stop of its own;
 *   * a DISABLED button or field still counts. It is not a stop, but a focusable inside a `<button>` is
 *     invalid wherever the button is disabled or not, and once it is enabled the text would be the nested
 *     stop this rule exists to prevent. A cut label in it waits for the control to be enabled.
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
  '[contenteditable]:not([contenteditable="false"])',
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
