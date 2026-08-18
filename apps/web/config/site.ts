/*
 * The app-shell identity: the browser-tab title, the PWA manifest, the OG/Twitter card, and the
 * fallback meta description for any page without its own. Deliberately untranslated — a crawler
 * fetching the social card sends no locale, so this string has to stand on its own in one language.
 * A page with localized metadata overrides all of it via `generatePageMetadata`.
 */
export const siteConfig = {
  name: 'Renly',
  description: 'Personal finance — investments, cash, and debt in one net worth',
};

/*
 * The parts of the social card that describe the SITE rather than the page. Both the root layout and
 * `generatePageMetadata` spread these, because Next REPLACES a segment's `openGraph`/`twitter` object
 * instead of merging it into the layout's: a page returning only a title and description would ship
 * without `og:type` or `og:site_name`.
 */
export const OG_SITE_DEFAULTS = { type: 'website', siteName: siteConfig.name } as const;
export const TWITTER_SITE_DEFAULTS = { card: 'summary_large_image' } as const;
