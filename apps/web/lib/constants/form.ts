/** Email regex */
export const EMAIL_REGEX =
  /^(?!\.)(?!.*\.\.)([a-z0-9_'+\-.]*)[a-z0-9_+-]@([a-z0-9][a-z0-9-]*\.)+[a-z]{2,}$/i;

/** Password length limits */
export const PASSWORD_MIN_LENGTH = 12;
export const PASSWORD_MAX_LENGTH = 64;

/*
 * The API's ceiling on a password, in UTF-8 BYTES rather than characters: bcrypt hashes at most 72
 * bytes, and the API refuses anything longer (`MAX_PASSWORD_BYTES` in `apps/api/app/domain/password.py`).
 * An accented letter is two bytes and an emoji four, so a password well under `PASSWORD_MAX_LENGTH`
 * characters can still be over it.
 */
export const PASSWORD_MAX_BYTES = 72;

/** Password strength check regexes */
export const PASSWORD_CONTAINS_UPPERCASE_REGEX = /[A-Z]/;
export const PASSWORD_CONTAINS_LOWERCASE_REGEX = /[a-z]/;
export const PASSWORD_CONTAINS_NUMBER_REGEX = /[0-9]/;
export const PASSWORD_CONTAINS_SPECIAL_CHARACTER_REGEX = /[!@#$%^&*]/;
