import type { Page } from '@playwright/test';

/*
 * How far the text of each icon + text row sits from its icon's centre, measured off the rendered
 * page. A row is a flex container laid out as a row with `align-items: center` whose direct children
 * include an `<svg>` icon and a label (a text node, or an element holding text and no icon of its
 * own). `items-center` centres the label's LINE BOX on the icon, so the text looks centred only when
 * the font draws its letters in the middle of that box.
 *
 * The letters' middle is the optical one: halfway between the centre of a capital and the centre of a
 * lowercase letter, which is where mixed-case text reads as centred. It is found from the font itself
 * with canvas `measureText` in the label's own font — the font box's ascent puts the baseline inside
 * the measured line, and the ink ascent of 'H' and of 'x' gives the cap and x heights — so the check
 * holds whatever metrics the face declares and needs no number copied from the font file.
 *
 * Rows whose label wraps are left out: `items-center` centres the whole block there, so no single line
 * is meant to sit on the icon.
 */

export interface IconTextRow {
  // The row's text, for a readable failure.
  label: string;
  fontSize: number;
  // The label's optical middle minus the icon's centre, in px: positive is text drawn LOW.
  offset: number;
}

export async function measureIconTextRows(page: Page): Promise<IconTextRow[]> {
  return page.evaluate(() => {
    const context = document.createElement('canvas').getContext('2d');
    if (!context) throw new Error('no 2d canvas context');

    // The label: the first direct child other than the icon that holds text — a text node, or an
    // element holding text and no icon of its own — with the first text node inside it.
    const labelOf = (row: Element, icon: Element): { item: Node; text: Text } | null => {
      for (const child of row.childNodes) {
        if (child === icon) continue;
        if (child.nodeType === Node.TEXT_NODE && child.textContent?.trim())
          return { item: child, text: child as Text };
        if (child instanceof HTMLElement && child.textContent?.trim()) {
          if (child.querySelector('svg')) return null;
          const walker = document.createTreeWalker(child, NodeFilter.SHOW_TEXT, {
            acceptNode: (node) =>
              node.textContent?.trim() ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_SKIP,
          });
          const text = walker.nextNode() as Text | null;
          return text ? { item: child, text } : null;
        }
      }
      return null;
    };

    const rows: { label: string; fontSize: number; offset: number }[] = [];
    for (const row of document.body.querySelectorAll('*')) {
      const style = getComputedStyle(row);
      if (!style.display.endsWith('flex') || style.flexDirection !== 'row') continue;
      if (style.alignItems !== 'center') continue;
      const icon = [...row.children].find((child) => child instanceof SVGSVGElement);
      if (!icon) continue;
      const iconBox = icon.getBoundingClientRect();
      if (iconBox.height < 8 || iconBox.width === 0) continue;
      const label = labelOf(row, icon);
      if (!label || !label.text.parentElement) continue;
      const { item, text } = label;

      // One visible line: a visually hidden label (`sr-only`, a 1px clipped box) and a label that
      // wraps are not text drawn beside the icon.
      const range = document.createRange();
      range.selectNodeContents(item);
      const lines = [...range.getClientRects()].filter((rect) => rect.width > 1 && rect.height > 1);
      if (lines.length === 0) continue;
      if (new Set(lines.map((rect) => Math.round(rect.top))).size > 1) continue;
      if (item instanceof HTMLElement && item.getBoundingClientRect().height <= 1) continue;
      range.selectNodeContents(text);
      const first = [...range.getClientRects()].find((rect) => rect.width > 0);
      if (!first) continue;

      const font = getComputedStyle(text.parentElement);
      const fontSize = parseFloat(font.fontSize);
      context.font = `${font.fontStyle} ${font.fontWeight} ${font.fontSize} ${font.fontFamily}`;
      const box = context.measureText('Hx');
      const capHeight = context.measureText('H').actualBoundingBoxAscent;
      const xHeight = context.measureText('x').actualBoundingBoxAscent;
      const baseline = first.top + box.fontBoundingBoxAscent;
      const opticalMiddle = baseline - (capHeight + xHeight) / 4;
      const iconMiddle = iconBox.top + iconBox.height / 2;
      rows.push({
        label: (row.textContent ?? '').trim().replace(/\s+/g, ' ').slice(0, 48),
        fontSize,
        offset: Math.round((opticalMiddle - iconMiddle) * 100) / 100,
      });
    }
    return rows;
  });
}
