// API boundary for group reads.
// Mutations are handled by server actions in groups-actions.ts.
// Core types and getGroups() are in lib/api/investments.ts (historical).

export { getGroups } from '@/lib/api/investments';
export type { InvestmentGroup, InvestmentGroupInfo } from '@/lib/api/investments';
