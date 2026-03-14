import './globals.css';

import type { Metadata } from 'next';
import { Plus_Jakarta_Sans } from 'next/font/google';
import { NextIntlClientProvider } from 'next-intl';
import { getLocale, getMessages } from 'next-intl/server';

import { cn } from '@repo/ui/lib';
import { siteConfig } from '@/config/site';

export const metadata: Metadata = {
  title: siteConfig.name,
  description: siteConfig.description,
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
          <div className="flex flex-col min-h-safe-bottom md:min-h-screen overflow-x-hidden relative">
            <div className="grid min-h-safe-bottom md:min-h-screen w-full">{children}</div>
          </div>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
