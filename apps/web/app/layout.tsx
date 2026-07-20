import './globals.css';

import type { Metadata, Viewport } from 'next';
import { Plus_Jakarta_Sans } from 'next/font/google';
import { NextIntlClientProvider } from 'next-intl';
import { getLocale, getMessages } from 'next-intl/server';
import { Toaster } from 'sonner';

import { cn } from '@repo/ui/lib';
import { CookieConsent } from '@/components/cookie-consent';
import { siteConfig } from '@/config/site';
import { BRAND_SURFACE } from '@/lib/constants/brand';

// Absolute base for resolving the favicon / Open Graph image URLs. Reuses NEXTAUTH_URL, the app's
// canonical web origin (see docs/technical/env-vars.md) — a runtime env, so it carries the real
// domain on every (dynamic) page render without a build arg. `||` (not `??`) so an empty value also
// falls back — new URL('') would throw here in the root layout and take down every page.
const siteUrl = process.env.NEXTAUTH_URL || 'http://localhost:3000';

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: siteConfig.name,
  description: siteConfig.description,
  applicationName: siteConfig.name,
  appleWebApp: { capable: true, title: siteConfig.name, statusBarStyle: 'default' },
  openGraph: {
    type: 'website',
    siteName: siteConfig.name,
    title: siteConfig.name,
    description: siteConfig.description,
  },
  twitter: {
    card: 'summary_large_image',
    title: siteConfig.name,
    description: siteConfig.description,
  },
};

// Browser/PWA chrome tint = the app's white surface, not the brand blue: iOS Safari ignores a custom
// theme-color (it tints from the page background) and an iOS home-screen app's status bar has no
// custom-color option — so white is what most users actually see. Keeps the chrome consistent
// instead of a blue bar that only Android would render.
export const viewport: Viewport = {
  themeColor: BRAND_SURFACE,
};

const plusJakartaSans = Plus_Jakarta_Sans({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
});

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const locale = await getLocale();
  const messages = await getMessages();

  return (
    <html className={plusJakartaSans.className} lang={locale}>
      <body
        className={cn(
          'min-h-safe-bottom md:min-h-screen w-full bg-muted/30 antialiased overflow-x-hidden',
        )}
      >
        <NextIntlClientProvider messages={messages}>
          {children}
          <CookieConsent />
          <Toaster richColors />
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
