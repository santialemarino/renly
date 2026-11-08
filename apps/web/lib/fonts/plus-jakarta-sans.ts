import localFont from 'next/font/local';

/*
 * The app's one typeface, self-hosted so the build never reaches the network. `next/font/google`
 * fetched it from Google Fonts at BUILD time, and a slow or failed fetch broke `next build` on CI.
 *
 * One variable file covers every weight the UI uses (400-700; the file spans 200-800), converted to
 * WOFF2 from the Google Fonts release (v2.071, the build Google serves). It is the whole font rather
 * than Google's latin subset, so text outside latin keeps the typeface instead of falling back. SIL
 * OFL 1.1 — the licence sits next to the file and travels with it.
 *
 * The root layout and the global error page both import THIS one definition, so the page and its
 * last-resort fallback can never render in two different faces. Both set its `variable` too, which the
 * `font-sans` theme token names, so a `font-sans` element renders this face rather than a family name
 * next/font never registers.
 *
 * The vertical metrics are overridden so text sits optically centred in its line box, which is what an
 * `items-center` row of icon + text aligns on. The file's own metrics (units per em 1000, typo ascent
 * 1038, descent 222, line gap 0, cap height 745, x-height 536) put the middle of the box
 * (1038 - 222) / 2 = 408 units above the baseline, while the optical middle of mixed-case text —
 * halfway between the centre of a capital (745 / 2) and the centre of a lowercase letter (536 / 2) —
 * sits at (372.5 + 268) / 2 ≈ 320. So labels drew up to ~0.09em low beside their icons (1.5px at 14px,
 * 1.9px at 24px). An ascent of 95% and a descent of 31% would put the box's middle exactly on 320 while
 * keeping the sum at 1.26em, so no line box changes height. 96% / 30% is used instead: the browser
 * rounds the ascent and the descent to whole pixels and floors the half-leading, which on average draws
 * the baseline about a quarter pixel high, and the extra point of ascent offsets it. Measured on every
 * icon + text row of the app: 96% keeps them all within 0.7px of their icon at 12-24px, where 95% left
 * the 12px hints 0.84px high and 98% the 16px rows 0.87px low.
 *
 * The one cost: a glyph taller than the 0.96em ascent — an accented capital (Á, É at 999 units),
 * Å (1044) — reaches above the content box, so a box that clips its overflow at a tight line height
 * can cut its top. Give such text the line height it needs rather than clipping it.
 */
export const plusJakartaSans = localFont({
  src: './plus-jakarta-sans-variable.woff2',
  weight: '400 700',
  style: 'normal',
  display: 'swap',
  variable: '--font-plus-jakarta-sans',
  declarations: [
    { prop: 'ascent-override', value: '96%' },
    { prop: 'descent-override', value: '30%' },
    { prop: 'line-gap-override', value: '0%' },
  ],
});
