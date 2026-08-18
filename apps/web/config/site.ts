/*
 * The app-shell identity: the browser-tab title, the PWA manifest, the OG/Twitter card, and the
 * fallback meta description for any page without its own. Deliberately untranslated — a crawler
 * fetching the social card sends no locale, so this string has to stand on its own in one language.
 * A page with localized metadata overrides all of it via `generatePageMetadata`.
 */
export const siteConfig = {
  name: 'Renly',
  description: 'Investments, cash, and debt in one net worth',
};

/*
 * The parts of the social card that describe the SITE rather than the page. Both the root layout and
 * `generatePageMetadata` spread these, because Next REPLACES a segment's `openGraph`/`twitter` object
 * instead of merging it into the layout's — so a page that declares one has to restate everything.
 *
 * `images` is the subtle half: the card image comes from the `app/opengraph-image.tsx` FILE
 * convention, which Next folds in only at the segment that owns the file. A page that declares
 * `openGraph` therefore drops the image unless it names it, and `twitter.images` is derived from
 * `openGraph.images`, so both vanish together. `card` is deliberately NOT set — Next picks
 * `summary_large_image` when an image resolves and `summary` when none does, so leaving it out means
 * the card type can never claim a large image the page does not actually have.
 */
/*
 * The share-card image, described in full. Naming `images` explicitly is what restores the tags the
 * file convention would have supplied, so the descriptor has to carry everything it did: without
 * `width`/`height` a scraper must fetch the image before it can lay the unfurl out, and without
 * `alt` the card has no accessible name. `app/opengraph-image.tsx` renders itself from these same
 * values, so the declared dimensions and the rendered ones cannot drift.
 */
export const SOCIAL_CARD_IMAGE = {
  url: '/opengraph-image',
  width: 1200,
  height: 630,
  type: 'image/png',
  alt: `${siteConfig.name} — ${siteConfig.description}`,
} as const;

export const OG_SITE_DEFAULTS = {
  type: 'website',
  siteName: siteConfig.name,
  images: SOCIAL_CARD_IMAGE,
} as const;
export const TWITTER_SITE_DEFAULTS = { images: SOCIAL_CARD_IMAGE } as const;
