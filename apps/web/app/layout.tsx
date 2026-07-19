import './globals.css';

import type { Metadata, Viewport } from 'next';
import { Plus_Jakarta_Sans } from 'next/font/google';
import { NextIntlClientProvider } from 'next-intl';
import { getLocale, getMessages } from 'next-intl/server';
import { Toaster } from 'sonner';

import { cn } from '@repo/ui/lib';
import { CookieConsent } from '@/components/cookie-consent';
import { siteConfig } from '@/config/site';

// Absolute base for resolving the favicon / Open Graph image URLs; falls back to localhost in dev.
const siteUrl = process.env.NEXT_PUBLIC_SITE_URL ?? 'http://localhost:3000';

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: siteConfig.name,
  description: siteConfig.description,
  applicationName: siteConfig.name,
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

// Brand-blue browser/PWA chrome tint (blue-800, the wordmark color).
export const viewport: Viewport = {
  themeColor: '#1e40af',
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
