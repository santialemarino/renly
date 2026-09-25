// Places every money figure carries: the API's NUMERIC(18,2) columns and `domain.money.MONEY_PLACES`.
export const MONEY_DECIMALS = 2;

const DECIMAL_PATTERN = /^([+-]?)(\d*)(?:\.(\d*))?(?:e([+-]?\d+))?$/i;

/*
 * A decimal as an exact integer of units at a scale: `12.345` is { units: 12345n, scale: 3 }.
 *
 * A number is read through its shortest round-trip string (`String(1.005)` is "1.005"), which is the
 * decimal the value was written as, rather than through the binary fraction it is stored as
 * (1.00499999999999989…). That is the whole difference between this module and `toFixed`.
 */
function toScaled(value: string | number): { units: bigint; scale: number } | null {
  const match = DECIMAL_PATTERN.exec(String(value).trim());
  if (!match) return null;
  const [, sign, whole = '', fraction = '', exponent = '0'] = match;
  if (whole === '' && fraction === '') return null;
  const shift = Number(exponent);
  const digits = `${whole}${fraction}`;
  let scale = fraction.length - shift;
  let padded = digits;
  if (scale < 0) {
    padded = `${digits}${'0'.repeat(-scale)}`;
    scale = 0;
  }
  const units = BigInt(padded || '0');
  return { units: sign === '-' ? -units : units, scale };
}

// Drops `places` digits off the units, a tie going away from zero — Python's ROUND_HALF_UP.
function dropPlaces(units: bigint, places: number): bigint {
  const divisor = 10n ** BigInt(places);
  const magnitude = units < 0n ? -units : units;
  const up = (magnitude % divisor) * 2n >= divisor ? 1n : 0n;
  return (units < 0n ? -1n : 1n) * (magnitude / divisor + up);
}

// Renders an exact scaled decimal at `decimals` places, rounded half-up.
function roundScaled(units: bigint, scale: number, decimals: number): string {
  const rounded =
    scale > decimals
      ? dropPlaces(units, scale - decimals)
      : units * 10n ** BigInt(decimals - scale);
  const negative = rounded < 0n;
  const text = (negative ? -rounded : rounded).toString().padStart(decimals + 1, '0');
  const body = decimals === 0 ? text : `${text.slice(0, -decimals)}.${text.slice(-decimals)}`;
  return negative ? `-${body}` : body;
}

/*
 * The product of two decimals as a money string, rounded HALF-UP to two places — the same answer the
 * API's `domain.money.quantize` gives for the same inputs. `(1 * 1.005).toFixed(2)` is "1.00" because it
 * rounds the binary approximation; this multiplies the decimals exactly and rounds once.
 *
 * Returns null when either side is not a decimal.
 */
export function moneyProduct(a: string | number, b: string | number): string | null {
  const left = toScaled(a);
  const right = toScaled(b);
  if (!left || !right) return null;
  return roundScaled(left.units * right.units, left.scale + right.scale, MONEY_DECIMALS);
}
