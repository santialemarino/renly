'use client';

import { useState } from 'react';
import dynamic from 'next/dynamic';
import { useRouter } from 'next/navigation';
import { Loader2, Plus } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { Button, useSidebar } from '@repo/ui/components';
import { cn } from '@repo/ui/lib';
import { PRIVATE_SCOPE } from '@/app/(protected)/_components/entry-scope-field';
import type { LinkedPlanMismatch } from '@/app/(protected)/_components/linked-plan-amount-mismatch-dialog';
import {
  getQuickAddContext,
  type QuickAddContext,
} from '@/app/(protected)/_components/quick-add-actions';
import type { EntryType } from '@/lib/constants/entries';
import {
  toTypeHandover,
  type EntryHandover,
  type ExpenseHandover,
  type IncomeHandover,
} from '@/lib/entry-handover';
import { useDeferredDialogSwap } from '@/lib/hooks/use-deferred-dialog-swap';
import { quickAddCurrency, soleEligibleAccountId } from '@/lib/quick-add';
import { todayInTimezone } from '@/lib/utils/dates';

/*
 * The five dialogs, loaded on demand — the ONE place in the app that does this, and for a measured
 * reason.
 *
 * The quick-add's trigger lives in the sidebar, which is part of the protected LAYOUT, so a static
 * import would put every entry form in the client graph of all twenty-odd protected routes. Measured
 * on the production build, per route, static → dynamic: `/dashboard` 1680 → 1560 KiB, `/notifications`
 * 1326 → 1206 KiB, `/snapshots` 1346 → 1254 KiB. Two of those three render no entry form at all.
 *
 * Deferring costs the user nothing, which is what makes it the right trade rather than a compromise:
 * `handleOpen` already awaits six reads before it opens anything, with the trigger in its loading
 * state, so the chunks arrive alongside a wait that was already happening. `ssr: false` because
 * nothing here renders until a click.
 */
const loadExpenseForm = () => import('@/app/(protected)/_components/expense-form-dialog');
const loadIncomeForm = () => import('@/app/(protected)/_components/income-form-dialog');
const loadSharedExpenseForm = () =>
  import('@/app/(protected)/_components/shared-expense-form-dialog');
const loadSharedIncomeForm = () =>
  import('@/app/(protected)/_components/shared-income-form-dialog');
const loadMismatchDialog = () =>
  import('@/app/(protected)/_components/linked-plan-amount-mismatch-dialog');

const ExpenseFormDialog = dynamic(() => loadExpenseForm().then((m) => m.ExpenseFormDialog), {
  ssr: false,
});
const IncomeFormDialog = dynamic(() => loadIncomeForm().then((m) => m.IncomeFormDialog), {
  ssr: false,
});
const SharedExpenseFormDialog = dynamic(
  () => loadSharedExpenseForm().then((m) => m.SharedExpenseFormDialog),
  { ssr: false },
);
const SharedIncomeFormDialog = dynamic(
  () => loadSharedIncomeForm().then((m) => m.SharedIncomeFormDialog),
  { ssr: false },
);
const LinkedPlanAmountMismatchDialog = dynamic(
  () => loadMismatchDialog().then((m) => m.LinkedPlanAmountMismatchDialog),
  { ssr: false },
);

/*
 * Every form's chunk, awaited together with the context read so the dialog is on screen the instant
 * the trigger's loading state ends.
 *
 * Without this the deferral would be visible rather than free: a `dynamic` component renders NOTHING
 * until its chunk lands, so `setOpen(true)` on a cold cache would stop the spinner and show no dialog
 * for as long as the fetch took. Preloading all five rather than just the one that opens first also
 * makes every later SWAP instant — a swap closes the outgoing form before the incoming one exists, so
 * a late chunk there would read as a dialog that shut for no reason.
 *
 * The module registry caches an `import()`, so `dynamic`'s own call resolves immediately afterwards.
 */
const preloadForms = () =>
  Promise.all([
    loadExpenseForm(),
    loadIncomeForm(),
    loadSharedExpenseForm(),
    loadSharedIncomeForm(),
    loadMismatchDialog(),
  ]);

// What a failed read leaves the pickers with — the same empty lists every page falls back to.
const EMPTY_CONTEXT: QuickAddContext = {
  accounts: [],
  creditCards: [],
  groups: [],
  obligations: [],
  subscriptions: [],
  installments: [],
};

/*
 * Which of the four entry forms the quick-add has open, and what it opens on.
 *
 * A discriminated union rather than two loose fields, because the two lists' handovers are bound to
 * their own category enum: keeping the type and the values together is what lets either be checked at
 * all. It also means the values travel WITH the swap, so nothing about the outgoing dialog changes
 * while it is animating out.
 */
type QuickAddDraft =
  | { type: 'expense'; scope: string; prefill?: ExpenseHandover }
  | { type: 'income'; scope: string; prefill?: IncomeHandover };

interface QuickAddProps {
  // The entry currency to open on, before the supported-set check — see quickAddCurrency.
  primaryCurrency: string;
  preferredCurrencies?: string[];
  supportedCurrencies?: string[];
  // The user's stored timezone, so "today" is today where they are and not where the browser is.
  timeZone?: string;
}

/*
 * The global quick-add (X4): an expense or a piece of income, from anywhere, with everything pre-filled
 * that honestly can be.
 *
 * It owns three things and nothing else — the trigger, the two swaps, and the pre-fill. The forms are
 * the app's OWN four entry dialogs, unchanged. That is the whole design: a leaner form here would be a
 * second place an expense is created, and every rule the real one carries (the novel-currency confirm,
 * the auto-charge duplicate warning, the cycle-advance preview, a linked plan's funding account, the
 * split rows, the payer refusal) would be either absent or duplicated. "Quick" is delivered by reach
 * and pre-fill, not by dropping fields.
 *
 * It lives in the sidebar because the app has no top bar: every protected page owns its full vertical
 * space and renders its own PageHeader, so the sidebar is the persistent shell — the same reasoning the
 * notification bell records.
 */
export function QuickAdd({
  primaryCurrency,
  preferredCurrencies,
  supportedCurrencies,
  timeZone,
}: QuickAddProps) {
  const t = useTranslations('sidebar');
  const router = useRouter();
  const { setOpenMobile } = useSidebar();
  const [loading, setLoading] = useState(false);
  const [context, setContext] = useState<QuickAddContext>(EMPTY_CONTEXT);
  // Amount-mismatch follow-up, held here so the prompt survives the entry form's close animation.
  const [mismatch, setMismatch] = useState<LinkedPlanMismatch | null>(null);
  const {
    open,
    setOpen,
    target: draft,
    start,
    swapTo,
  } = useDeferredDialogSwap<QuickAddDraft>({ type: 'expense', scope: PRIVATE_SCOPE });

  const scopedGroup = context.groups.find((group) => String(group.id) === draft.scope);
  /*
   * Narrowed per form: `draft.prefill` is only the expense handover while the draft says 'expense',
   * and TypeScript can only see that through the discriminant.
   */
  const expensePrefill = draft.type === 'expense' ? draft.prefill : undefined;
  const incomePrefill = draft.type === 'income' ? draft.prefill : undefined;
  /*
   * The account to open a PRIVATE entry on, re-derived from whatever currency the draft carries — so a
   * swap out to the shared form and back opens on the same state the first door did.
   *
   * The shared forms get no such default. Their account is one leg of a PAYER's instrument, gated on
   * the funding shape and on whose seat it is, so pre-filling it would pre-answer "who fronted this" —
   * the shared form's central question, and not one a pre-fill should decide.
   */
  const prefillAccountId = soleEligibleAccountId(context.accounts, draft.prefill?.currency ?? '');

  /*
   * Reads the caller's pickers, THEN opens the form — deliberately in that order.
   *
   * Opening first and letting the lists arrive would be worse than a flicker. `AccountField` renders
   * nothing at all while it has no account to offer, and React Hook Form DELETES a field's value when
   * its control leaves the DOM — so the pre-selected account would be silently dropped the moment the
   * list landed and the field mounted. "The list is empty" and "the list has not arrived" are the same
   * value and opposite facts, and this is the one place that can tell them apart.
   *
   * Re-read on every opening rather than cached: a card, an account or a group can all have appeared on
   * another page since, and a stale list arriving mid-typing could only ever change a picker under
   * somebody's hands.
   */
  async function handleOpen() {
    setLoading(true);
    const [loaded] = await Promise.all([
      getQuickAddContext().catch(() => EMPTY_CONTEXT),
      // Never rejected on its own: a chunk that fails to load leaves `dynamic` to render its own
      // nothing, and taking the whole open down with it would be worse than the empty pickers a
      // failed read already degrades to.
      preloadForms().catch(() => undefined),
    ]);
    setLoading(false);
    setContext(loaded);
    // Closes the mobile sheet, which would otherwise sit behind the dialog with its own overlay. A
    // no-op on desktop, where the sidebar is never a sheet.
    setOpenMobile(false);
    start({
      type: 'expense',
      scope: PRIVATE_SCOPE,
      prefill: {
        date: todayInTimezone(timeZone),
        currency: quickAddCurrency(primaryCurrency, supportedCurrencies),
      },
    });
  }

  /*
   * Swaps between expense and income, keeping the scope. The category does not cross — see
   * toTypeHandover for why.
   *
   * The scope-swap handlers stay inline at their call sites: each one already knows its own type
   * statically, so `{ type: 'expense', scope, prefill: values }` type-checks against the union with no
   * cast, which a shared helper taking a runtime `EntryType` could not.
   */
  function swapEntryType(type: EntryType, values: EntryHandover<string>) {
    const prefill = toTypeHandover(values);
    swapTo(
      type === 'income'
        ? { type: 'income', scope: draft.scope, prefill }
        : { type: 'expense', scope: draft.scope, prefill },
    );
  }

  return (
    <>
      <Button
        blue
        size="lg"
        onClick={handleOpen}
        disabled={loading}
        aria-haspopup="dialog"
        data-testid="quick-add-trigger"
        className="w-full justify-center gap-2 [&_svg]:size-5 text-paragraph-medium"
      >
        {/* Both icons share one grid cell, so the swap crossfades instead of reflowing the label. */}
        <span className="grid shrink-0">
          <Plus
            className={cn(
              'col-start-1 row-start-1 transition-all duration-200',
              loading ? 'scale-0 opacity-0' : 'scale-100 opacity-100',
            )}
          />
          <Loader2
            className={cn(
              'col-start-1 row-start-1 animate-spin transition-all duration-200',
              loading ? 'scale-100 opacity-100' : 'scale-0 opacity-0',
            )}
          />
        </span>
        <span>{t('nav.quickAdd')}</span>
      </Button>

      <ExpenseFormDialog
        open={open && draft.type === 'expense' && draft.scope === PRIVATE_SCOPE}
        onOpenChange={setOpen}
        preferredCurrencies={preferredCurrencies}
        supportedCurrencies={supportedCurrencies}
        creditCards={context.creditCards}
        accounts={context.accounts}
        activeObligations={context.obligations}
        activeSubscriptions={context.subscriptions}
        activeInstallments={context.installments}
        scopeGroups={context.groups}
        onScopeChange={(scope, values) => swapTo({ type: 'expense', scope, prefill: values })}
        onEntryTypeChange={swapEntryType}
        prefill={expensePrefill}
        prefillAccountId={prefillAccountId}
        onSuccess={() => router.refresh()}
        onLinkedPlanSave={(values, plan) =>
          setMismatch({
            type: plan.type,
            planId: plan.id,
            planName: plan.name,
            enteredAmount: values.amount,
            currentAmount: plan.amount,
            currency: plan.currency,
          })
        }
      />

      <IncomeFormDialog
        open={open && draft.type === 'income' && draft.scope === PRIVATE_SCOPE}
        onOpenChange={setOpen}
        preferredCurrencies={preferredCurrencies}
        supportedCurrencies={supportedCurrencies}
        accounts={context.accounts}
        scopeGroups={context.groups}
        onScopeChange={(scope, values) => swapTo({ type: 'income', scope, prefill: values })}
        onEntryTypeChange={swapEntryType}
        prefill={incomePrefill}
        prefillAccountId={prefillAccountId}
        onSuccess={() => router.refresh()}
      />

      {/*
       * Each shared form is mounted only once its own scope AND type are what the draft names. The
       * dialog reads that group's shared accounts when it opens, so mounting one per group up front
       * would be a request each for a form the user has not asked for.
       */}
      {scopedGroup && draft.type === 'expense' && (
        <SharedExpenseFormDialog
          open={open}
          onOpenChange={setOpen}
          group={scopedGroup}
          prefill={expensePrefill}
          accounts={context.accounts}
          creditCards={context.creditCards}
          preferredCurrencies={preferredCurrencies}
          supportedCurrencies={supportedCurrencies}
          timeZone={timeZone}
          scopeGroups={context.groups}
          onScopeChange={(scope, values) => swapTo({ type: 'expense', scope, prefill: values })}
          onEntryTypeChange={swapEntryType}
          onSuccess={() => router.refresh()}
        />
      )}

      {scopedGroup && draft.type === 'income' && (
        <SharedIncomeFormDialog
          open={open}
          onOpenChange={setOpen}
          group={scopedGroup}
          prefill={incomePrefill}
          accounts={context.accounts}
          preferredCurrencies={preferredCurrencies}
          supportedCurrencies={supportedCurrencies}
          timeZone={timeZone}
          scopeGroups={context.groups}
          onScopeChange={(scope, values) => swapTo({ type: 'income', scope, prefill: values })}
          onEntryTypeChange={swapEntryType}
          onSuccess={() => router.refresh()}
        />
      )}

      <LinkedPlanAmountMismatchDialog
        mismatch={mismatch}
        onClose={() => setMismatch(null)}
        onConfirmed={() => {
          setMismatch(null);
          router.refresh();
        }}
      />
    </>
  );
}
