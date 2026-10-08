import { expect, type Locator } from '@playwright/test';

/*
 * Waits until React has HYDRATED the element `target` resolves to — the moment its event handlers
 * exist, which visibility cannot tell you.
 *
 * A server-rendered page is visible, laid out and actionable to Playwright before React has hydrated
 * it, and React does not replay a pointer MOVE aimed at content it has not hydrated yet. Radix opens a
 * tooltip on `pointermove`, so a `hover()` that lands in that window is lost for good: the trigger
 * never changes state, no timer ever starts, and waiting longer on the tooltip cannot help.
 *
 * The condition read here is React's own: when it hydrates a server-rendered node it attaches that
 * node's current props to it (under a `__reactProps$<id>` key, the record its event system reads the
 * handlers from), and a node it has not reached carries none. So this waits on the exact thing a hover
 * needs, on the exact element, rather than on a page-wide signal or a timer.
 */
export async function waitForHydration(target: Locator, timeout = 20_000): Promise<void> {
  await expect
    .poll(
      () =>
        target.evaluate((element) =>
          Object.keys(element).some((key) => key.startsWith('__reactProps$')),
        ),
      { timeout, message: 'React never hydrated the element, so it has no event handlers' },
    )
    .toBe(true);
}
