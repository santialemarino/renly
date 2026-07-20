// Renly brand colors used by metadata / asset code (the web manifest, the theme-color meta, and the
// Open Graph image). These mirror Tailwind's blue-* scale — the same values baked into the static
// app/icon.svg and the generated app-icon PNGs (favicon.ico, apple-icon, icons/*). They live here as
// literals because none of those consumers run through Tailwind's class pipeline (a JSON manifest, a
// meta string, a static SVG file, a server-rendered image). If the brand blue ever changes, update
// this file AND regenerate the image assets so the two stay in sync.

export const BRAND_BLUE = '#1e40af'; // Tailwind blue-800 — the wordmark + primary brand color.
export const BRAND_BLUE_GRADIENT_FROM = '#1d4ed8'; // blue-700 — icon/OG tile gradient start.
export const BRAND_BLUE_GRADIENT_TO = '#1e3a8a'; // blue-900 — icon/OG tile gradient end.
export const BRAND_SURFACE = '#ffffff'; // App surface — manifest background + OG canvas.
