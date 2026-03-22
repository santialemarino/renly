// Currencies with exchange rate support (DolarApi provides USD/ARS rates).
// Other currencies will show values in their original currency until more rate sources are added.
const SUPPORTED_CONVERSION_CURRENCIES = ['USD', 'ARS'] as const;

export function isCurrencySupported(code: string): boolean {
  return (SUPPORTED_CONVERSION_CURRENCIES as readonly string[]).includes(code);
}
