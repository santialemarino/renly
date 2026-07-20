import type { MetadataRoute } from 'next';

import { siteConfig } from '@/config/site';
import { BRAND_BLUE, BRAND_SURFACE } from '@/lib/constants/brand';

// PWA web app manifest. Next serves it at /manifest.webmanifest and links it automatically.
// theme_color is the brand blue-800; background_color matches the app's white surface (used for
// the install splash). Icons cover the "any" purpose plus a full-bleed maskable for Android.
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
    theme_color: BRAND_BLUE,
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
