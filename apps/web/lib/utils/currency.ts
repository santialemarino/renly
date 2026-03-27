// All currencies with exchange rate support.
const SUPPORTED_CONVERSION_CURRENCIES = new Set(['USD', 'ARS', 'BRL', 'EUR', 'GBP']);

export function isCurrencySupported(code: string): boolean {
  return SUPPORTED_CONVERSION_CURRENCIES.has(code);
}
