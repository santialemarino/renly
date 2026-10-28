import { describe, expect, it } from 'vitest';

import { CONTROL_SELECTOR } from '@/lib/constants/controls';

/*
 * What `CONTROL_SELECTOR` takes for a control, at its edges. `TruncatingTooltip` and the e2e text sweep
 * both rule with it on whether a cut text may be a tab stop of its own: never inside a control, always
 * inside anything else that merely takes focus (a scroll region).
 */

function el(html: string): Element {
  const host = document.createElement('div');
  host.innerHTML = html;
  const first = host.firstElementChild;
  if (!first) throw new Error(`no element in ${html}`);
  return first;
}

describe('CONTROL_SELECTOR', () => {
  it.each([
    ['a link', '<a href="/x">x</a>'],
    ['a button', '<button>x</button>'],
    ['a disabled button', '<button disabled>x</button>'],
    ['an editable region', '<div contenteditable="true">x</div>'],
    ['a bare contenteditable', '<div contenteditable>x</div>'],
    ['an option', '<div role="option">x</div>'],
  ])('takes %s for a control', (_name, html) => {
    expect(el(html).matches(CONTROL_SELECTOR)).toBe(true);
  });

  it.each([
    ['a focusable scroll region', '<div role="region" tabindex="0" aria-label="t">x</div>'],
    ['a bare tab stop', '<div tabindex="0">x</div>'],
    ['a region that is not editable', '<div contenteditable="false">x</div>'],
    ['a link with no href', '<a>x</a>'],
    ['a hidden input', '<input type="hidden">'],
  ])('does not take %s for one', (_name, html) => {
    expect(el(html).matches(CONTROL_SELECTOR)).toBe(false);
  });
});
