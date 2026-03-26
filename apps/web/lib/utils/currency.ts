import { USD_VARIANTS } from '@/lib/constants/currency';

const USD_VARIANT_CODES = new Set<string>(USD_VARIANTS.map((v) => v.code));

// Returns true if the code is a USD variant (USD, USD_MEP, USD_BLUE).
export function isUsdVariant(code: string): boolean {
  return USD_VARIANT_CODES.has(code);
}

// Returns the base ISO currency for a code — strips variant suffix.
// "USD_MEP" -> "USD", "ARS" -> "ARS".
export function baseCurrency(code: string): string {
  if (USD_VARIANT_CODES.has(code)) return 'USD';
  return code;
}

// Currencies with exchange rate support (DolarApi provides USD/ARS rates).
// All USD variants are supported, plus ARS (identity conversion).
const SUPPORTED_CONVERSION_CURRENCIES = new Set(['USD', 'USD_MEP', 'USD_BLUE', 'ARS']);

export function isCurrencySupported(code: string): boolean {
  return SUPPORTED_CONVERSION_CURRENCIES.has(code);
}
