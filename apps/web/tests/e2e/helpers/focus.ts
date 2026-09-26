import { expect, type Locator, type Page } from '@playwright/test';

/*
 * Browser-side measurements for the focus-system specs.
 *
 * The ring is measured from what the browser actually painted, never from a copied token: the ring
 * colour is read off the focused element's computed `box-shadow`, the surfaces off the computed
 * backgrounds and the `:root` custom properties, and every colour goes through a 1×1 canvas so the
 * browser itself resolves whatever syntax it is written in (oklch, color-mix, an alpha) and composites
 * it over the surface beneath. That last part is the point — a half-alpha ring is exactly the defect,
 * and only compositing it over its surface sees it.
 */

// WCAG 1.4.11: a focus indicator needs 3:1 against the colours adjacent to it.
export const RING_MIN_CONTRAST = 3;

// The surfaces a ring can sit on, read from `:root` so a token change moves the check with it.
export const RING_SURFACE_TOKENS = [
  '--background',
  '--card',
  '--popover',
  '--muted',
  '--secondary',
  '--accent',
  '--input',
  '--sidebar',
] as const;

export interface RingReport {
  ring: string;
  contrasts: { surface: string; ratio: number }[];
}

/*
 * The focused element's ring against its own backdrop (every ancestor's background composited over
 * white, since the ring is drawn OUTSIDE the element) and against each token surface. Throws, rather
 * than reporting a number, when there is no ring to measure or a colour will not parse — a silent
 * fallback there would measure black and pass.
 */
export async function measureRing(target: Locator): Promise<RingReport> {
  // The ring transitions in (`transition-[border-color,box-shadow]`); measured mid-way it is a
  // fraction of its alpha, so wait for the element's running transitions to settle first.
  await target.evaluate((element) =>
    Promise.all(element.getAnimations().map((animation) => animation.finished)),
  );
  return target.evaluate(
    (element, tokens) => {
      const SENTINEL = '#010203';
      const canvas = document.createElement('canvas');
      canvas.width = 1;
      canvas.height = 1;
      const context = canvas.getContext('2d', { willReadFrequently: true });
      if (!context) throw new Error('no 2d canvas');

      // Paints white, then each layer in order, and returns the pixel that results.
      const paint = (layers: string[]): [number, number, number] => {
        context.fillStyle = '#ffffff';
        context.fillRect(0, 0, 1, 1);
        layers.forEach((layer) => {
          context.fillStyle = SENTINEL;
          context.fillStyle = layer;
          if (context.fillStyle === SENTINEL) throw new Error(`unparseable colour: ${layer}`);
          context.fillRect(0, 0, 1, 1);
        });
        const [r = 0, g = 0, b = 0] = context.getImageData(0, 0, 1, 1).data;
        return [r, g, b];
      };
      const luminance = ([r, g, b]: [number, number, number]) => {
        const linear = (channel: number) => {
          const c = channel / 255;
          return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
        };
        return 0.2126 * linear(r) + 0.7152 * linear(g) + 0.0722 * linear(b);
      };
      const contrast = (a: [number, number, number], b: [number, number, number]) => {
        const [light, dark] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [
          number,
          number,
        ];
        return (light + 0.05) / (dark + 0.05);
      };

      // Splits a computed box-shadow list on its top-level commas (colours carry commas of their own).
      const shadows: string[] = [];
      let depth = 0;
      let current = '';
      for (const char of getComputedStyle(element).boxShadow) {
        if (char === '(') depth += 1;
        if (char === ')') depth -= 1;
        if (char === ',' && depth === 0) {
          shadows.push(current.trim());
          current = '';
        } else current += char;
      }
      shadows.push(current.trim());
      // A ring is a shadow with no offset and no blur, only a spread.
      const ring = shadows
        .map((shadow) => {
          const lengths = [...shadow.matchAll(/(-?[\d.]+)px/g)].map((match) => Number(match[1]));
          const colour = shadow
            .replace(/-?[\d.]+px/g, '')
            .replace(/\binset\b/, '')
            .trim();
          return { lengths, colour };
        })
        .find(
          ({ lengths }) =>
            lengths.length === 4 &&
            lengths[0] === 0 &&
            lengths[1] === 0 &&
            lengths[2] === 0 &&
            (lengths[3] ?? 0) > 0,
        );
      if (!ring)
        throw new Error(`no ring on the focused element: ${getComputedStyle(element).boxShadow}`);

      const backdrop: string[] = [];
      for (let node = element.parentElement; node; node = node.parentElement) {
        backdrop.unshift(getComputedStyle(node).backgroundColor);
      }
      const root = getComputedStyle(document.documentElement);
      const surfaces: [string, string[]][] = [
        ['backdrop', backdrop],
        ...tokens.map((token): [string, string[]] => [
          token,
          [root.getPropertyValue(token).trim()],
        ]),
      ];

      return {
        ring: ring.colour,
        contrasts: surfaces.map(([surface, layers]) => ({
          surface,
          ratio: Number(contrast(paint(layers), paint([...layers, ring.colour])).toFixed(2)),
        })),
      };
    },
    RING_SURFACE_TOKENS as readonly string[],
  );
}

// Asserts every measured contrast clears 3:1, naming the surfaces that do not.
export function expectRingContrast(report: RingReport) {
  const failing = report.contrasts.filter(({ ratio }) => ratio < RING_MIN_CONTRAST);
  expect(failing, `ring ${report.ring} below ${RING_MIN_CONTRAST}:1`).toEqual([]);
  // The token list really was measured, not skipped.
  expect(report.contrasts).toHaveLength(RING_SURFACE_TOKENS.length + 1);
}

// Presses Tab until `target` holds focus, so the focus is a KEYBOARD one (:focus-visible applies).
export async function tabTo(page: Page, target: Locator, maxStops = 60) {
  for (let stop = 0; stop < maxStops; stop += 1) {
    if (await target.evaluate((element) => element === document.activeElement)) return;
    await page.keyboard.press('Tab');
  }
  throw new Error(`not reached within ${maxStops} tab stops`);
}
