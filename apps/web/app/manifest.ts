import type { MetadataRoute } from 'next';

import { siteConfig } from '@/config/site';
import { BRAND_SURFACE } from '@/lib/constants/brand';

// PWA web app manifest. Next serves it at /manifest.webmanifest and links it automatically.
// theme_color + background_color are the app's white surface (see the theme-color note in layout.tsx
// for why not brand blue). Icons cover the "any" purpose plus a full-bleed maskable for Android.
export default function manifest(): MetadataRoute.Manifest {
  return {
    id: '/',
    name: siteConfig.name,
    short_name: siteConfig.name,
    description: siteConfig.description,
    start_url: '/',
    display: 'standalone',
    categories: ['finance'],
    background_color: BRAND_SURFACE,
    theme_color: BRAND_SURFACE,
    icons: [
      { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
      { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
      {
        src: '/icons/icon-maskable-512.png',
        sizes: '512x512',
        type: 'image/png',
        purpose: 'maskable',
      },
    ],
  };
}
