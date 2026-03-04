import { headers } from 'next/headers';
import { getRequestConfig } from 'next-intl/server';

import { DEFAULT_LOCALE, SUPPORTED_LOCALES } from '@/config/constants';

function getLocaleFromHeader(headersList: Headers): string | null {
  const acceptLanguage = headersList.get('accept-language');
  if (!acceptLanguage) return null;

  const languages = acceptLanguage
    .split(',')
    .map((lang) => lang.split(';')[0]?.trim().toLowerCase())
    .filter((lang): lang is string => Boolean(lang));

  for (const lang of languages) {
    if (SUPPORTED_LOCALES.includes(lang as (typeof SUPPORTED_LOCALES)[number])) {
      return lang;
    }
    const langPrefix = lang.split('-')[0];
    if (
      langPrefix &&
      SUPPORTED_LOCALES.includes(langPrefix as (typeof SUPPORTED_LOCALES)[number])
    ) {
      return langPrefix;
    }
  }

  return null;
}

export default getRequestConfig(async () => {
  const headersList = await headers();

  let locale = getLocaleFromHeader(headersList) || DEFAULT_LOCALE;

  if (!SUPPORTED_LOCALES.includes(locale as (typeof SUPPORTED_LOCALES)[number])) {
    locale = DEFAULT_LOCALE;
  }

  return {
    locale,
    messages: (await import(`../translations/${locale}.json`)).default,
  };
});
