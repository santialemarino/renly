'use client';

import { useTranslations } from 'next-intl';
import { useWatch, type Control, type FieldValues } from 'react-hook-form';

import { Checkbox, Label } from '@repo/ui/components';
import { cn } from '@repo/ui/lib';
import {
  includedSplitCount,
  splitFiguresBalance,
  splitFiguresTotal,
  type SplitFormRow,
} from '@/app/(protected)/shared/split-form-schema';
import {
  splitFigureKind,
  splitMethodHasTotal,
  type SplitFigureKind,
} from '@/app/(protected)/shared/split-rules';
import { FormControl, FormField, FormItem } from '@/components/form';
import { LocaleAmountInput } from '@/components/locale-amount-input';
import type { GroupMember } from '@/lib/api/groups';
import {
  SPLIT_FIGURE_DECIMALS,
  SPLIT_PERCENTAGE_TOTAL,
  type SplitMethod,
} from '@/lib/constants/shared-expenses';
import { useFormatters } from '@/lib/i18n/formatters';

// Minimal form shape this control operates on — the three fields a split editor reads, and nothing
// about which flow the form belongs to. Every embedding schema declares all three.
export type SplitFormValues = {
  splits: SplitFormRow[];
  splitMethod: SplitMethod;
  amount: string;
};

interface EntrySplitRowsProps<T extends SplitFormValues & FieldValues> {
  // Must be rendered inside this form's <Form> provider: FormItem and FormMessage read the context.
  control: Control<T>;
  /*
   * One row per seat, in the order the form seeded them — which is the roster's order, so the rows
   * stay put as the method changes. Former seats appear only when the row being edited already named
   * them; a new one never offers one.
   */
  seats: GroupMember[];
  // The row's currency, for the amount fields' precision and the exact method's total.
  currency: string;
  /*
   * What this list of people IS, in the one place the two flows differ. An expense asks who was in on
   * it; income asks who gets a share of it. Every other string here — the per-method hints, the
   * running total, the figure placeholders, the errors — reads correctly for both and stays in the
   * shared namespace.
   */
  participantsLabel: string;
  /*
   * Whether to show the total's error. The dialog submits the form, so `formState.isSubmitted` is its
   * signal — the same split `PotShareRows` makes, and for the same reason: an error shown before the
   * user has finished typing the first figure is noise, not help.
   */
  showTotalError: boolean;
}

/*
 * Who a shared amount is divided between, and each participant's figure for the chosen split method.
 *
 * One control for both flows, because the division is one thing: a shared expense and a piece of
 * shared income take the same four methods, the same figures and the same running total. Only the
 * heading differs, and it arrives as a prop.
 *
 * The running total is the whole affordance, and it has to be. Both of the schema's split issues land
 * at `path: ['splits']`, which is react-hook-form's ARRAY entry, and an array's `message` is
 * undefined — so a `FormMessage` there renders nothing and an unbalanced submit looks like it
 * silently did nothing. `PotShareRows` learned this the same way, in the browser. Hence a rule stated
 * in words beside the figure, and a total that is visibly out before anyone presses save.
 *
 * `equal` shows no figures at all and no total: it divides by head count, so the only thing to say is
 * who is in. It deliberately does NOT preview a per-person amount — the API spreads the rounding
 * remainder one cent at a time from the largest part down, and a second copy of that would be a
 * second algorithm to disagree about the one figure a person checks. The exact shares are on the row
 * the moment it is saved.
 */
export function EntrySplitRows<T extends SplitFormValues & FieldValues>({
  control: controlProp,
  seats,
  currency,
  participantsLabel,
  showTotalError,
}: EntrySplitRowsProps<T>) {
  const fmt = useFormatters();
  const t = useTranslations('shared');

  /*
   * Narrow the caller's form typing to the minimal shape, exactly as `AccountField` does and for the
   * same reason: react-hook-form's Control generic is invariant, so a direct assignment will not
   * compile even though T extends SplitFormValues. Safe because this control only ever reads and
   * writes the three fields that shape declares.
   */
  const control = controlProp as unknown as Control<SplitFormValues>;

  const watchedSplits = useWatch({ control, name: 'splits' });
  const watchedMethod = useWatch({ control, name: 'splitMethod' });
  const watchedAmount = useWatch({ control, name: 'amount' });

  const splits = watchedSplits ?? [];
  const hasTotal = splitMethodHasTotal(watchedMethod);
  const balanced = splitFiguresBalance(watchedMethod, splits, watchedAmount ?? '');
  const noParticipants = includedSplitCount(splits) === 0;
  // Null for `equal`, which asks for no figures — so there is nothing to render and nothing to say.
  const figureKind = splitFigureKind(watchedMethod);

  /*
   * What the total is measured against. A percentage split targets 100 whatever the amount is; an
   * exact one targets the amount itself, so an amount typed after the figures moves the target — and
   * the total has to say so rather than staying green against a figure that has changed.
   */
  const total = splitFiguresTotal(splits);
  const totalLabel =
    watchedMethod === 'percentage'
      ? `${fmt.sharePct(total)}% / ${SPLIT_PERCENTAGE_TOTAL}%`
      : `${fmt.amount(String(total), currency)} / ${fmt.amount(watchedAmount || '0', currency)}`;

  return (
    <div className="flex flex-col gap-y-2">
      {/*
       * The base Label, not FormLabel: this heads the whole participants block rather than one field,
       * and FormLabel outside a FormField has no field context to read.
       */}
      <Label required>{participantsLabel}</Label>
      <p className="text-paragraph-xs text-muted-foreground">{t(`split.hint.${watchedMethod}`)}</p>

      {seats.map((seat, index) => (
        <SplitRow
          key={seat.id}
          seat={seat}
          index={index}
          control={control}
          currency={currency}
          figureKind={figureKind}
        />
      ))}

      {hasTotal && (
        <div className="flex items-center justify-between px-3 py-2 bg-muted/40 rounded-lg">
          <span className="text-paragraph-sm text-muted-foreground">{t('split.total')}</span>
          <span
            className={cn(
              'text-paragraph-sm-medium tabular-nums',
              balanced ? 'text-emerald-600' : 'text-amber-600',
            )}
          >
            {totalLabel}
          </span>
        </div>
      )}

      {/*
       * The two array-level rules, in the only place they can be shown. Participants first because it
       * is the one that makes the other meaningless — an empty split has no total to be out by.
       */}
      {showTotalError && noParticipants && (
        <p className="text-paragraph-xs text-destructive">{t('split.errors.participants')}</p>
      )}
      {showTotalError && !noParticipants && !balanced && figureKind !== null && (
        <p className="text-paragraph-xs text-destructive">{t(`split.errors.${figureKind}`)}</p>
      )}
    </div>
  );
}

/*
 * One participant: whether they were in on it, and their figure.
 *
 * Unchecking leaves the figure in place rather than clearing it, so someone who unticks a person by
 * mistake gets their number back — the action drops every unchecked row before sending, and the
 * running total ignores them, so a stale figure can reach neither the API nor the sum.
 */
function SplitRow({
  seat,
  index,
  control,
  currency,
  figureKind,
}: {
  seat: GroupMember;
  index: number;
  control: Control<SplitFormValues>;
  currency: string;
  // Null when the method takes no figures, which is the one case that renders no input at all.
  figureKind: SplitFigureKind | null;
}) {
  const t = useTranslations('shared');

  const included = useWatch({ control, name: `splits.${index}.included` });

  return (
    <div className="flex min-w-0 items-center gap-x-3">
      <FormField
        control={control}
        name={`splits.${index}.included`}
        render={({ field }) => (
          <Checkbox
            blue
            checked={field.value}
            onCheckedChange={field.onChange}
            // A Radix checkbox renders a <button>, which is not labelable — so the name beside it
            // cannot be a <label> and has to reach assistive tech this way instead.
            aria-label={seat.displayName}
          />
        )}
      />

      {/*
       * truncate, and the field shrink-0: without both, a long display name wraps and renders behind
       * the input. `min-w-0` alone is not enough — a flex item's text forces its intrinsic width
       * until something clips it.
       */}
      <span
        className={cn(
          'flex-1 min-w-0 truncate text-paragraph-sm',
          included ? 'text-foreground' : 'text-muted-foreground',
        )}
      >
        {seat.displayName}
        {seat.isSelf && (
          <span className="text-paragraph-xs text-muted-foreground"> {t('members.you')}</span>
        )}
        {/* A former seat appears only on a row that already named them, and saying so is the point:
            the API refuses to re-record one, and the form says which person that is about. */}
        {!seat.isActive && (
          <span className="text-paragraph-xs text-muted-foreground">
            {' '}
            {t('split.formerMember')}
          </span>
        )}
      </span>

      {figureKind !== null && (
        <FormField
          control={control}
          name={`splits.${index}.figure`}
          render={({ field }) => (
            <FormItem className="shrink-0">
              <FormControl>
                <LocaleAmountInput
                  {...field}
                  containerClassName="w-32"
                  disabled={!included}
                  /*
                   * An exact figure is money and takes the expense's own precision. A percentage and
                   * a share are neither — both are bare figures the API stores at two places, which
                   * is what `SPLIT_FIGURE_DECIMALS` names.
                   */
                  currency={figureKind === 'exact' ? currency : undefined}
                  maxDecimals={figureKind === 'exact' ? undefined : SPLIT_FIGURE_DECIMALS}
                  placeholder={t(`split.figurePlaceholder.${figureKind}`)}
                />
              </FormControl>
            </FormItem>
          )}
        />
      )}

      {/* Rendered for every method that takes figures, so the rows keep their metrics when the user
          switches between percentage and the two without a unit. */}
      {figureKind !== null && (
        <span className="w-4 shrink-0 text-paragraph-sm text-muted-foreground">
          {figureKind === 'percentage' ? '%' : ''}
        </span>
      )}
    </div>
  );
}
