'use client';

import { Fragment, useCallback, useEffect, useState, useTransition } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  Archive,
  ArchiveRestore,
  ArrowDown,
  ArrowUp,
  ChevronRight,
  ChevronsUpDown,
  Pencil,
  Plus,
  Trash2,
} from 'lucide-react';
import { AnimatePresence, motion } from 'motion/react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

import {
  Button,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@repo/ui/components';
import { cn } from '@repo/ui/lib';
import { CreditCardArchiveDialog } from '@/app/(protected)/credit-cards/_components/credit-card-archive-dialog';
import { CreditCardDeleteDialog } from '@/app/(protected)/credit-cards/_components/credit-card-delete-dialog';
import { CreditCardFormDialog } from '@/app/(protected)/credit-cards/_components/credit-card-form-dialog';
import { SettlementDeleteDialog } from '@/app/(protected)/credit-cards/_components/settlement-delete-dialog';
import { SettlementFormDialog } from '@/app/(protected)/credit-cards/_components/settlement-form-dialog';
import {
  fetchSettlements,
  unarchiveCreditCard,
  type SettlementResult,
} from '@/app/(protected)/credit-cards/credit-card-actions';
import { ROUTES } from '@/config/routes';
import type { CreditCard, CreditCardSortField, SortOrder } from '@/lib/api/credit-cards';
import { formatAmount } from '@/lib/utils/currency';

// Minimum time (ms) from fetch start before showing the result.
// Prevents layout flash when the fetch resolves instantly.
const SETTLEMENTS_DISPLAY_DELAY_MS = 500;

function SortIcon({
  column,
  sortBy,
  sortOrder,
}: {
  column: CreditCardSortField;
  sortBy: CreditCardSortField | null;
  sortOrder: SortOrder;
}) {
  const active = sortBy === column;
  const isAsc = active && sortOrder === 'asc';
  const isDesc = active && sortOrder === 'desc';
  return (
    <span className="grid shrink-0 group-focus-visible/sort:animate-focus-bump">
      <ChevronsUpDown
        className={cn(
          'col-start-1 row-start-1 size-3.5 text-blue-400 transition-all duration-200',
          active ? 'scale-0 opacity-0' : 'scale-100 opacity-100',
        )}
      />
      <ArrowUp
        className={cn(
          'col-start-1 row-start-1 size-3.5 text-blue-800 transition-all duration-200',
          isAsc ? 'scale-100 opacity-100' : 'scale-0 opacity-0',
        )}
      />
      <ArrowDown
        className={cn(
          'col-start-1 row-start-1 size-3.5 text-blue-800 transition-all duration-200',
          isDesc ? 'scale-100 opacity-100' : 'scale-0 opacity-0',
        )}
      />
    </span>
  );
}

function SettlementsSection({
  cardId,
  cardCurrency,
  expanded,
}: {
  cardId: number;
  cardCurrency: string;
  expanded: boolean;
}) {
  const t = useTranslations('creditCards');
  const router = useRouter();
  const [settlements, setSettlements] = useState<SettlementResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [deleteSettlementState, setDeleteSettlementState] = useState<SettlementResult | null>(null);

  const loadSettlements = useCallback(async () => {
    setLoading(true);
    const start = Date.now();
    try {
      const data = await fetchSettlements(cardId);
      const elapsed = Date.now() - start;
      if (elapsed < SETTLEMENTS_DISPLAY_DELAY_MS) {
        await new Promise((r) => setTimeout(r, SETTLEMENTS_DISPLAY_DELAY_MS - elapsed));
      }
      setSettlements(data);
    } catch {
      setSettlements([]);
    } finally {
      setLoading(false);
    }
  }, [cardId]);

  // Fetch on first expand. Re-expand shows cached data instantly.
  const [fetched, setFetched] = useState(false);
  useEffect(() => {
    if (expanded && !fetched) {
      setFetched(true);
      loadSettlements();
    }
  }, [expanded, fetched, loadSettlements]);

  return (
    <AnimatePresence>
      {expanded && (
        <TableRow>
          <TableCell colSpan={7} className="p-0">
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.2, ease: 'easeInOut' }}
              className="overflow-hidden"
            >
              <div className="px-8 py-4 bg-muted/30">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-paragraph-sm-medium">{t('settlements.title')}</span>
                  <Button variant="outline" size="sm" onClick={() => setAddOpen(true)}>
                    <Plus className="size-3.5" />
                    {t('settlements.add')}
                  </Button>
                </div>

                <AnimatePresence mode="wait">
                  {loading ? (
                    <motion.p
                      key="loading"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      transition={{ duration: 0.15 }}
                      className="text-paragraph-sm text-muted-foreground"
                    >
                      {t('settlements.loading')}
                    </motion.p>
                  ) : settlements.length === 0 ? (
                    <motion.p
                      key="empty"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      transition={{ duration: 0.15 }}
                      className="text-paragraph-sm text-muted-foreground"
                    >
                      {t('settlements.empty')}
                    </motion.p>
                  ) : (
                    <motion.div
                      key="table"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      transition={{ duration: 0.15 }}
                    >
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>{t('settlements.table.date')}</TableHead>
                            <TableHead>{t('settlements.table.amount')}</TableHead>
                            <TableHead>{t('settlements.table.currency')}</TableHead>
                            <TableHead>{t('settlements.table.notes')}</TableHead>
                            <TableHead className="w-12 text-center">{t('table.actions')}</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {settlements.map((s) => (
                            <TableRow key={s.id}>
                              <TableCell>{s.date}</TableCell>
                              <TableCell className="text-paragraph-sm tabular-nums">
                                {formatAmount(s.amount)}
                              </TableCell>
                              <TableCell>{s.currency}</TableCell>
                              <TableCell className="max-w-48 truncate text-muted-foreground">
                                {s.notes ?? '—'}
                              </TableCell>
                              <TableCell>
                                <Tooltip>
                                  <TooltipTrigger asChild>
                                    <Button
                                      variant="ghost"
                                      size="icon"
                                      className="size-7 text-muted-foreground hover:text-destructive"
                                      onClick={() => setDeleteSettlementState(s)}
                                      aria-label="Delete settlement"
                                    >
                                      <Trash2 className="size-3.5" />
                                    </Button>
                                  </TooltipTrigger>
                                  <TooltipContent>{t('settlements.deleteTooltip')}</TooltipContent>
                                </Tooltip>
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </motion.div>
                  )}
                </AnimatePresence>

                <SettlementFormDialog
                  open={addOpen}
                  onOpenChange={setAddOpen}
                  cardId={cardId}
                  cardCurrency={cardCurrency}
                  onSuccess={() => {
                    loadSettlements();
                    router.refresh();
                  }}
                />

                <SettlementDeleteDialog
                  open={!!deleteSettlementState}
                  onOpenChange={(open) => {
                    if (!open) setDeleteSettlementState(null);
                  }}
                  cardId={cardId}
                  settlement={deleteSettlementState}
                  onSuccess={() => {
                    loadSettlements();
                    router.refresh();
                  }}
                />
              </div>
            </motion.div>
          </TableCell>
        </TableRow>
      )}
    </AnimatePresence>
  );
}

export function CreditCardsTable({
  cards,
  preferredCurrencies,
}: {
  cards: CreditCard[];
  preferredCurrencies?: string[];
}) {
  const t = useTranslations('creditCards');
  const router = useRouter();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [editCard, setEditCard] = useState<CreditCard | null>(null);
  const [archiveCard, setArchiveCard] = useState<CreditCard | null>(null);
  const [deleteCardState, setDeleteCardState] = useState<CreditCard | null>(null);
  const [unarchiving, setUnarchiving] = useState<number | null>(null);

  async function handleUnarchive(card: CreditCard) {
    setUnarchiving(card.id);
    try {
      await unarchiveCreditCard(card.id);
      toast.success(t('actions.unarchiveSuccess'));
      router.refresh();
    } catch {
      toast.error(t('actions.unarchiveError'));
    } finally {
      setUnarchiving(null);
    }
  }

  const sortBy = (searchParams.get('sort_by') as CreditCardSortField | null) ?? null;
  const sortOrder = (searchParams.get('sort_order') as SortOrder | null) ?? 'asc';

  function navigate(overrides: Record<string, string | null>) {
    const params = new URLSearchParams(searchParams.toString());
    Object.entries(overrides).forEach(([key, val]) => {
      if (val === null) params.delete(key);
      else params.set(key, val);
    });
    startTransition(() => router.push(`${ROUTES.creditCards}?${params.toString()}`));
  }

  function handleSortChange(column: CreditCardSortField) {
    if (sortBy === column) {
      if (sortOrder === 'asc') {
        navigate({ sort_by: column, sort_order: 'desc' });
      } else {
        navigate({ sort_by: null, sort_order: null });
      }
    } else {
      navigate({ sort_by: column, sort_order: 'asc' });
    }
  }

  return (
    <div className="flex flex-col gap-y-4">
      <div className={isPending ? 'opacity-60 pointer-events-none transition-opacity' : ''}>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-6" />
              <TableHead>
                <button
                  type="button"
                  onClick={() => handleSortChange('name')}
                  className="group/sort flex items-center gap-x-1 hover:text-foreground transition-colors focus-visible:outline-none"
                >
                  {t('table.name')}
                  <SortIcon column="name" sortBy={sortBy} sortOrder={sortOrder} />
                </button>
              </TableHead>
              <TableHead>
                <button
                  type="button"
                  onClick={() => handleSortChange('closing_day')}
                  className="group/sort flex items-center gap-x-1 hover:text-foreground transition-colors focus-visible:outline-none"
                >
                  {t('table.closingDay')}
                  <SortIcon column="closing_day" sortBy={sortBy} sortOrder={sortOrder} />
                </button>
              </TableHead>
              <TableHead>
                <button
                  type="button"
                  onClick={() => handleSortChange('due_day')}
                  className="group/sort flex items-center gap-x-1 hover:text-foreground transition-colors focus-visible:outline-none"
                >
                  {t('table.dueDay')}
                  <SortIcon column="due_day" sortBy={sortBy} sortOrder={sortOrder} />
                </button>
              </TableHead>
              <TableHead>
                <button
                  type="button"
                  onClick={() => handleSortChange('currency')}
                  className="group/sort flex items-center gap-x-1 hover:text-foreground transition-colors focus-visible:outline-none"
                >
                  {t('table.currency')}
                  <SortIcon column="currency" sortBy={sortBy} sortOrder={sortOrder} />
                </button>
              </TableHead>
              <TableHead>{t('table.balance')}</TableHead>
              <TableHead className="w-20 text-center">{t('table.actions')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {cards.length === 0 ? (
              <TableRow>
                <TableCell
                  colSpan={7}
                  className="py-10 rounded-sm text-center text-muted-foreground"
                >
                  {t('table.empty')}
                </TableCell>
              </TableRow>
            ) : (
              cards.map((card) => {
                const isExpanded = expandedId === card.id;
                return (
                  <Fragment key={card.id}>
                    <TableRow
                      className="cursor-pointer"
                      onClick={() => setExpandedId(isExpanded ? null : card.id)}
                    >
                      <TableCell>
                        <ChevronRight
                          className={cn(
                            'size-4 transition-transform duration-200',
                            isExpanded && 'rotate-90',
                          )}
                        />
                      </TableCell>
                      <TableCell className="text-paragraph-sm-medium">{card.name}</TableCell>
                      <TableCell>{card.closingDay}</TableCell>
                      <TableCell>{card.dueDay}</TableCell>
                      <TableCell>{card.currency}</TableCell>
                      <TableCell className="text-paragraph-sm tabular-nums">
                        {formatAmount(card.balance)}
                      </TableCell>
                      <TableCell className="text-center" onClick={(e) => e.stopPropagation()}>
                        {!card.isActive ? (
                          <div className="flex items-center justify-center">
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Button
                                  variant="ghost"
                                  size="icon"
                                  className="size-8"
                                  onClick={() => handleUnarchive(card)}
                                  disabled={unarchiving === card.id}
                                  aria-label="Unarchive"
                                >
                                  <ArchiveRestore className="size-4" />
                                </Button>
                              </TooltipTrigger>
                              <TooltipContent>{t('actions.unarchive')}</TooltipContent>
                            </Tooltip>
                          </div>
                        ) : (
                          <div className="flex items-center justify-center gap-x-1">
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Button
                                  variant="ghost"
                                  size="icon"
                                  className="size-8"
                                  onClick={() => setEditCard(card)}
                                  aria-label="Edit"
                                >
                                  <Pencil className="size-4" />
                                </Button>
                              </TooltipTrigger>
                              <TooltipContent>{t('actions.edit')}</TooltipContent>
                            </Tooltip>
                            {card.hasExpenses ? (
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <Button
                                    variant="ghost"
                                    size="icon"
                                    className="size-8 text-muted-foreground hover:text-foreground"
                                    onClick={() => setArchiveCard(card)}
                                    aria-label="Archive"
                                  >
                                    <Archive className="size-4" />
                                  </Button>
                                </TooltipTrigger>
                                <TooltipContent>{t('actions.archive')}</TooltipContent>
                              </Tooltip>
                            ) : (
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <Button
                                    variant="ghost"
                                    size="icon"
                                    className="size-8 text-muted-foreground hover:text-destructive"
                                    onClick={() => setDeleteCardState(card)}
                                    aria-label="Delete"
                                  >
                                    <Trash2 className="size-4" />
                                  </Button>
                                </TooltipTrigger>
                                <TooltipContent>{t('actions.delete')}</TooltipContent>
                              </Tooltip>
                            )}
                          </div>
                        )}
                      </TableCell>
                    </TableRow>
                    <SettlementsSection
                      key={`settlements-${card.id}`}
                      cardId={card.id}
                      cardCurrency={card.currency}
                      expanded={isExpanded}
                    />
                  </Fragment>
                );
              })
            )}
          </TableBody>
        </Table>
      </div>

      <CreditCardFormDialog
        open={!!editCard}
        onOpenChange={(open) => {
          if (!open) setEditCard(null);
        }}
        card={editCard ?? undefined}
        preferredCurrencies={preferredCurrencies}
        onSuccess={() => router.refresh()}
      />

      <CreditCardArchiveDialog
        open={!!archiveCard}
        onOpenChange={(open) => {
          if (!open) setArchiveCard(null);
        }}
        card={archiveCard}
        onSuccess={() => router.refresh()}
      />

      <CreditCardDeleteDialog
        open={!!deleteCardState}
        onOpenChange={(open) => {
          if (!open) setDeleteCardState(null);
        }}
        card={deleteCardState}
        onSuccess={() => router.refresh()}
      />
    </div>
  );
}
