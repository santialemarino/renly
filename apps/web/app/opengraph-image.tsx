import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { ImageResponse } from 'next/og';

import { siteConfig, SOCIAL_CARD_IMAGE } from '@/config/site';
import {
  BRAND_BLUE,
  BRAND_BLUE_GRADIENT_FROM,
  BRAND_BLUE_GRADIENT_TO,
  BRAND_SURFACE,
} from '@/lib/constants/brand';

// Social share card (og:image + twitter fallback) rendered on demand by next/og. Mirrors the app
// brand: the gradient R monogram over the blue-800 wordmark and the product tagline, on white.
export const runtime = 'nodejs';
export const alt = SOCIAL_CARD_IMAGE.alt;
export const size = { width: SOCIAL_CARD_IMAGE.width, height: SOCIAL_CARD_IMAGE.height };
export const contentType = SOCIAL_CARD_IMAGE.type;

// Read a bundled font. The static `new URL(..., import.meta.url)` lets the bundler trace and emit
// the .ttf next to the compiled route, so it resolves in both dev and a standalone production build.
function loadFont(url: URL): Promise<Buffer> {
  return readFile(fileURLToPath(url));
}

export default async function OpengraphImage() {
  const [regular, semibold] = await Promise.all([
    loadFont(new URL('./_og-fonts/PlusJakartaSans-Regular.ttf', import.meta.url)),
    loadFont(new URL('./_og-fonts/PlusJakartaSans-SemiBold.ttf', import.meta.url)),
  ]);

  return new ImageResponse(
    <div
      style={{
        width: '100%',
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: BRAND_SURFACE,
        backgroundImage: `linear-gradient(160deg, ${BRAND_SURFACE} 55%, #eef2ff 100%)`,
        fontFamily: 'Jakarta',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: 208,
          height: 208,
          borderRadius: 48,
          backgroundImage: `linear-gradient(135deg, ${BRAND_BLUE_GRADIENT_FROM} 0%, ${BRAND_BLUE_GRADIENT_TO} 100%)`,
          boxShadow: '0 24px 60px -18px rgba(30, 64, 175, 0.55)', // brand blue at 55%.
        }}
      >
        <div style={{ display: 'flex', fontSize: 150, fontWeight: 600, color: '#ffffff' }}>R</div>
      </div>
      <div
        style={{
          display: 'flex',
          marginTop: 48,
          fontSize: 92,
          fontWeight: 600,
          letterSpacing: -1,
          color: BRAND_BLUE,
        }}
      >
        {siteConfig.name}
      </div>
      <div
        style={{
          display: 'flex',
          marginTop: 18,
          maxWidth: 840,
          textAlign: 'center',
          fontSize: 34,
          fontWeight: 400,
          color: '#48505e',
        }}
      >
        {siteConfig.description}
      </div>
    </div>,
    {
      ...size,
      fonts: [
        { name: 'Jakarta', data: regular, weight: 400, style: 'normal' },
        { name: 'Jakarta', data: semibold, weight: 600, style: 'normal' },
      ],
    },
  );
}
