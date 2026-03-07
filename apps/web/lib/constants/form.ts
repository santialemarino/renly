/** Email regex */
export const EMAIL_REGEX =
  /^(?!\.)(?!.*\.\.)([a-z0-9_'+\-.]*)[a-z0-9_+-]@([a-z0-9][a-z0-9-]*\.)+[a-z]{2,}$/i;

/** Password length limits */
export const PASSWORD_MIN_LENGTH = 8;
export const PASSWORD_MAX_LENGTH = 64;

/** Password strength check regexes */
export const PASSWORD_CONTAINS_UPPERCASE_REGEX = /[A-Z]/;
export const PASSWORD_CONTAINS_LOWERCASE_REGEX = /[a-z]/;
export const PASSWORD_CONTAINS_NUMBER_REGEX = /[0-9]/;
export const PASSWORD_CONTAINS_SPECIAL_CHARACTER_REGEX = /[!@#$%^&*]/;
