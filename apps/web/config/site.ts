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
