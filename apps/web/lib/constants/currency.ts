// USD variant codes — each uses a different USD/ARS exchange rate.
// "USD" = oficial (default), "USD_MEP" = MEP/bolsa, "USD_BLUE" = blue/parallel.
export const USD_VARIANTS = [
  { code: 'USD', labelKey: 'oficial' },
  { code: 'USD_MEP', labelKey: 'mep' },
  { code: 'USD_BLUE', labelKey: 'blue' },
] as const;
