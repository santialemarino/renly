import { createTranslator } from 'next-intl';
import { describe, expect, it } from 'vitest';

import { resetPasswordFormSchema } from '@/app/(auth)/reset-password/form-schema';
import { signupFormSchema } from '@/app/(auth)/signup/form-schema';
import { changePasswordSchema } from '@/app/(protected)/account/form-schemas';
import { USER_NAME_MAX } from '@/lib/constants/api-constants';
import { PASSWORD_MAX_BYTES, PASSWORD_MAX_LENGTH } from '@/lib/constants/form';
import { newPasswordSchema, withinPasswordByteLimit } from '@/lib/new-password';
import en from '../../translations/en.json';
import es from '../../translations/es.json';

/*
 * The web's half of the API's 72-byte password ceiling.
 *
 * The API counts UTF-8 BYTES because bcrypt does; zod's `.max()` counts characters. A password that
 * passes one and fails the other reaches the API and comes back as a 422 the form can only render as a
 * generic "something went wrong" — the defect this pins, reproduced with the passphrase below.
 */

// 50 characters, 74 bytes: every `ñ` is two bytes and every 🔐 four. Under the 64-character cap,
// over the 72-byte one, and it satisfies every other rule — so the byte check is the only thing that
// can refuse it.
const ACCENTED_PASSPHRASE = 'Contraseña segura 🔐🔐🔐🔐🔐🔐🔐🔐🔐🔐🔐 Año 2026!';

// A password that satisfies every rule, for the forms' other fields to sit beside.
const VALID_PASSWORD = 'Valid-Passw0rd!';

const tEn = createTranslator({ locale: 'en', messages: en, namespace: 'common' });
const tEs = createTranslator({ locale: 'es', messages: es, namespace: 'common' });
const BYTES_KEY = 'form.errors.passwordTooManyBytes';

// The schemas are typed against next-intl's hook, which this standalone translator is at runtime but
// not in type — the same `as never` bridge the api-error tests use.
const t = tEn as never;

function messagesFor(result: { success: boolean; error?: { issues: { message: string }[] } }) {
  return result.success ? [] : (result.error?.issues.map((issue) => issue.message) ?? []);
}

describe('withinPasswordByteLimit', () => {
  it('counts bytes, not characters', () => {
    expect(ACCENTED_PASSPHRASE).toHaveLength(50);
    expect(new TextEncoder().encode(ACCENTED_PASSPHRASE)).toHaveLength(74);
    expect(withinPasswordByteLimit(ACCENTED_PASSPHRASE)).toBe(false);
  });

  it('accepts exactly the ceiling and refuses one byte past it', () => {
    expect(withinPasswordByteLimit('a'.repeat(PASSWORD_MAX_BYTES))).toBe(true);
    expect(withinPasswordByteLimit('a'.repeat(PASSWORD_MAX_BYTES + 1))).toBe(false);
    // 36 two-byte letters are 72 bytes; a 37th is 74.
    expect(withinPasswordByteLimit('ñ'.repeat(36))).toBe(true);
    expect(withinPasswordByteLimit('ñ'.repeat(37))).toBe(false);
  });

  it('agrees with the API ceiling', () => {
    expect(PASSWORD_MAX_BYTES).toBe(72);
  });
});

describe('newPasswordSchema', () => {
  it('refuses the accented passphrase with the byte message and nothing else', () => {
    expect(messagesFor(newPasswordSchema(t).safeParse(ACCENTED_PASSPHRASE))).toEqual([
      tEn(BYTES_KEY),
    ]);
  });

  it('keeps the character cap', () => {
    const long = `Aa1!${'a'.repeat(PASSWORD_MAX_LENGTH - 3)}`;
    expect(withinPasswordByteLimit(long)).toBe(true);
    expect(newPasswordSchema(t).safeParse(long).success).toBe(false);
  });

  it('accepts an accented password that fits in 72 bytes', () => {
    expect(newPasswordSchema(t).safeParse('Contraseña-Año-2026!').success).toBe(true);
  });

  // A missing message renders as its own key path, which is a non-empty string — so assert the key
  // is absent from the output rather than that the output is truthy.
  it('has a real message in both locales', () => {
    expect(tEn(BYTES_KEY)).not.toContain(BYTES_KEY);
    expect(tEs(BYTES_KEY)).not.toContain(BYTES_KEY);
    expect(tEs(BYTES_KEY)).not.toBe(tEn(BYTES_KEY));
  });
});

// Every form that SETS a password carries the byte rule, on the field the API caps.
describe('the forms that set a password', () => {
  it('signup refuses the accented passphrase', () => {
    const result = signupFormSchema(t).safeParse({
      name: 'Ana',
      email: 'ana@example.com',
      password: ACCENTED_PASSPHRASE,
      confirmPassword: ACCENTED_PASSPHRASE,
    });
    expect(messagesFor(result)).toEqual([tEn(BYTES_KEY)]);
  });

  it('reset refuses the accented passphrase', () => {
    const result = resetPasswordFormSchema(t).safeParse({
      password: ACCENTED_PASSPHRASE,
      confirmPassword: ACCENTED_PASSPHRASE,
    });
    expect(messagesFor(result)).toEqual([tEn(BYTES_KEY)]);
  });

  it('change-password refuses the accented passphrase', () => {
    const result = changePasswordSchema(t).safeParse({
      currentPassword: VALID_PASSWORD,
      newPassword: ACCENTED_PASSPHRASE,
      confirmPassword: ACCENTED_PASSPHRASE,
    });
    expect(messagesFor(result)).toEqual([tEn(BYTES_KEY)]);
  });
});

// The signup name is capped at the column it lands in, so an over-long one is a field error rather
// than the generic server error the API's 422 used to become.
describe('signup name', () => {
  const body = (name: string) => ({
    name,
    email: 'ana@example.com',
    password: VALID_PASSWORD,
    confirmPassword: VALID_PASSWORD,
  });

  it('accepts a name at the cap and refuses one character past it', () => {
    expect(signupFormSchema(t).safeParse(body('a'.repeat(USER_NAME_MAX))).success).toBe(true);
    expect(messagesFor(signupFormSchema(t).safeParse(body('a'.repeat(USER_NAME_MAX + 1))))).toEqual(
      [tEn('form.errors.tooLong', { max: USER_NAME_MAX })],
    );
  });
});
