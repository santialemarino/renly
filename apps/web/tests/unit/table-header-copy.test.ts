import { describe, expect, it } from 'vitest';

import en from '../../translations/en.json';
import es from '../../translations/es.json';

/*
 * Two column headers that said something other than what their column holds.
 */

const LOCALES = { en, es } as const;

// Every string under `node` whose key is `actions`: the row-actions column header, wherever it lives.
function actionsHeaders(node: unknown, path = ''): [string, string][] {
  if (typeof node !== 'object' || node === null) return [];
  return Object.entries(node).flatMap(([key, value]) => {
    const here = path ? `${path}.${key}` : key;
    if (key === 'actions' && typeof value === 'string') return [[here, value] as [string, string]];
    return actionsHeaders(value, here);
  });
}

describe('table header copy', () => {
  /*
   * The payment obligations column shows the free-text label typed into the form's "Label" field, not
   * an expense category (the obligation's category is a separate field the table does not show), so it
   * is headed with the form field's own word.
   */
  it.each(Object.entries(LOCALES))(
    'heads the obligations label column with the form field’s name (%s)',
    (_locale, messages) => {
      expect(messages.paymentObligations.table.label).toBe(
        messages.paymentObligations.form.category.label,
      );
    },
  );

  /*
   * In Spanish "Acciones" is both "actions" and the Stocks category, so an actions column headed
   * "Acciones" beside a category column read as a column of stocks. No row-actions header may reuse
   * a category's name.
   */
  it.each(Object.entries(LOCALES))(
    'never heads a row-actions column with a category name (%s)',
    (_locale, messages) => {
      const categories = new Set(Object.values(messages.common.categories));
      const headers = actionsHeaders(messages);
      expect(headers.length).toBeGreaterThan(10);
      const colliding = headers.filter(([, value]) => categories.has(value));
      expect(colliding).toEqual([]);
    },
  );
});
