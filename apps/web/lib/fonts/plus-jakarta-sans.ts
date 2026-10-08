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
 * last-resort fallback can never render in two different faces.
 */
export const plusJakartaSans = localFont({
  src: './plus-jakarta-sans-variable.woff2',
  weight: '400 700',
  style: 'normal',
  display: 'swap',
});
