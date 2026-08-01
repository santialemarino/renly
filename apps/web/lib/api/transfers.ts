// Server-only types + mappers for transfers (Bucket 3 #1) — money moving between two of the user's
// own accounts. Client components fetch via server actions in `account-actions.ts` instead.

import 'server-only';

// --- Raw types (API JSON shape, snake_case) ---

interface TransferRaw {
  id: number;
  from_account_id: number;
  to_account_id: number;
  from_account_name: string;
  to_account_name: string;
  from_currency: string;
  to_currency: string;
  date: string;
  from_amount: string;
  to_amount: string;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

interface TransferListRaw {
  items: TransferRaw[];
  total: number;
}

// --- Frontend types (camelCase) ---

export interface Transfer {
  id: number;
  fromAccountId: number;
  toAccountId: number;
  fromAccountName: string;
  toAccountName: string;
  fromCurrency: string;
  toCurrency: string;
  date: string;
  fromAmount: string;
  toAmount: string;
  notes: string | null;
  createdAt: string;
  updatedAt: string;
}

// --- Mappers ---

export function mapTransfer(raw: TransferRaw): Transfer {
  return {
    id: raw.id,
    fromAccountId: raw.from_account_id,
    toAccountId: raw.to_account_id,
    fromAccountName: raw.from_account_name,
    toAccountName: raw.to_account_name,
    fromCurrency: raw.from_currency,
    toCurrency: raw.to_currency,
    date: raw.date,
    fromAmount: raw.from_amount,
    toAmount: raw.to_amount,
    notes: raw.notes,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
  };
}

export function mapTransferList(raw: TransferListRaw): Transfer[] {
  return raw.items.map(mapTransfer);
}
