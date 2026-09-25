import { useTranslations } from 'next-intl';
import { z } from 'zod';

import {
  PASSWORD_CONTAINS_LOWERCASE_REGEX,
  PASSWORD_CONTAINS_NUMBER_REGEX,
  PASSWORD_CONTAINS_SPECIAL_CHARACTER_REGEX,
  PASSWORD_CONTAINS_UPPERCASE_REGEX,
  PASSWORD_MAX_BYTES,
  PASSWORD_MAX_LENGTH,
  PASSWORD_MIN_LENGTH,
} from '@/lib/constants/form';

/*
 * Whether a password fits the API's ceiling, counted the way the API counts it: in UTF-8 bytes.
 *
 * zod's `.max()` counts characters, so on its own it passes a 50-character passphrase with a few
 * accents and emoji that is 74 bytes long — which the API then refuses with a 422 the form can only
 * show as a generic server error. This is an es-locale app, so an accented passphrase is the ordinary
 * case rather than an exotic one.
 */
export function withinPasswordByteLimit(value: string): boolean {
  return new TextEncoder().encode(value).length <= PASSWORD_MAX_BYTES;
}

/*
 * The rule for a password being SET — signup, reset, and change-password all build their field from
 * this, so the three cannot drift apart. Signing in is deliberately not a caller: it checks a password
 * that already exists rather than choosing a new one.
 *
 * Takes the `common` translator, where the `form.errors.*` messages live.
 */
export function newPasswordSchema(t: ReturnType<typeof useTranslations>) {
  return z
    .string()
    .min(PASSWORD_MIN_LENGTH, {
      message: t('form.errors.passwordMinLength', { length: PASSWORD_MIN_LENGTH }),
    })
    .max(PASSWORD_MAX_LENGTH, {
      message: t('form.errors.passwordMaxLength', { length: PASSWORD_MAX_LENGTH }),
    })
    .refine(withinPasswordByteLimit, { message: t('form.errors.passwordTooManyBytes') })
    .regex(PASSWORD_CONTAINS_UPPERCASE_REGEX, { message: t('form.errors.passwordRequirements') })
    .regex(PASSWORD_CONTAINS_LOWERCASE_REGEX, { message: t('form.errors.passwordRequirements') })
    .regex(PASSWORD_CONTAINS_NUMBER_REGEX, { message: t('form.errors.passwordRequirements') })
    .regex(PASSWORD_CONTAINS_SPECIAL_CHARACTER_REGEX, {
      message: t('form.errors.passwordRequirements'),
    });
}
