'use client';

import { useTranslations } from 'next-intl';
import { useWatch, type UseFormReturn } from 'react-hook-form';

import { Label } from '@repo/ui/components';
import { cn } from '@repo/ui/lib';
import {
  openingSharesTotal,
  type PotOpeningFormValues,
} from '@/app/(protected)/shared/pot-form-schema';
import { FormControl, FormField, FormItem, FormMessage } from '@/components/form';
import { LocaleAmountInput } from '@/components/locale-amount-input';
import { TruncatingTooltip } from '@/components/truncating-tooltip';
import type { GroupMember } from '@/lib/api/groups';
import { POT_PERCENTAGE_TOTAL } from '@/lib/constants/pots';
import { useFormatters } from '@/lib/i18n/formatters';

interface PotShareRowsProps {
  // Must be rendered inside this form's <Form> provider: FormItem and FormMessage read the context.
  form: UseFormReturn<PotOpeningFormValues>;
  // One row per seat, in roster order. A blank field means "owns none of it" rather than 0.
  seats: GroupMember[];
  /*
   * Whether to show the total's error. The callers trigger it differently and that is not incidental:
   * the dialog submits the form, so `formState.isSubmitted` is its signal; the guided flow's step has
   * no submit at all, so it is "you pressed Continue while the total was wrong".
   */
  showTotalError: boolean;
}

/*
 * Who owns what percentage of a pot, with the running total beside it.
 *
 * One implementation for the baseline dialog and the guided flow, because this block carries two
 * rules that must not be able to differ between them: the percentages ARE the agreement and are never
 * rescaled, and the total is shown live because someone a point out has to see it before submitting
 * rather than after.
 *
 * The total is the whole affordance, and it has to be: the schema's refine puts its message at
 * `shares`, which is react-hook-form's ARRAY entry, and an array's `message` is undefined — so a
 * FormMessage there renders nothing and an unbalanced submit looks like it silently did nothing.
 * Only the browser showed that. Hence a rule stated in words beside the figure instead.
 */
export function PotShareRows({ form, seats, showTotalError }: PotShareRowsProps) {
  const fmt = useFormatters();
  const t = useTranslations('shared');

  const watchedShares = useWatch({ control: form.control, name: 'shares' });
  const total = openingSharesTotal(watchedShares ?? []);
  const balanced = total === POT_PERCENTAGE_TOTAL;

  return (
    <div className="flex flex-col gap-y-2">
      {/*
       * The base Label, not FormLabel: this heads the whole shares block rather than one field, and
       * FormLabel outside a FormField has no field context to read.
       */}
      <Label required>{t('pots.opening.shares.label')}</Label>
      <p className="text-paragraph-xs text-muted-foreground">{t('pots.opening.shares.hint')}</p>

      {seats.map((seat, index) => (
        <ShareRow key={seat.id} seat={seat} index={index} form={form} />
      ))}

      <div className="flex items-center justify-between px-3 py-2 bg-muted/40 rounded-lg">
        <span className="text-paragraph-sm text-muted-foreground">
          {t('pots.opening.shares.total')}
        </span>
        <span
          className={cn(
            'text-paragraph-sm-medium tabular-nums',
            balanced ? 'text-emerald-600' : 'text-amber-600',
          )}
        >
          {`${fmt.sharePct(total)}% / ${POT_PERCENTAGE_TOTAL}%`}
        </span>
      </div>

      {showTotalError && !balanced && (
        <p className="text-paragraph-xs text-destructive">
          {t('pots.opening.totalError', { total: POT_PERCENTAGE_TOTAL })}
        </p>
      )}
    </div>
  );
}

interface ShareRowProps {
  seat: GroupMember;
  index: number;
  form: UseFormReturn<PotOpeningFormValues>;
}

/*
 * One owner's percentage. A blank field means "owns none of it" rather than 0 — the action drops those
 * rows, so an opening never writes an event granting nobody anything.
 */
function ShareRow({ seat, index, form }: ShareRowProps) {
  const t = useTranslations('shared');

  return (
    <FormField
      control={form.control}
      name={`shares.${index}.percentage`}
      render={({ field }) => (
        <FormItem>
          <div className="flex min-w-0 items-center gap-x-3">
            {/*
             * The name truncates on its own, with the whole name in a tooltip, and "(you)" stays whole
             * beside it: truncating the pair cut the tag first and gave no way to read either. The
             * input is shrink-0 and this row `min-w-0`, or a long name wraps and renders behind it.
             */}
            <span className="flex flex-1 min-w-0 items-baseline gap-x-1 text-paragraph-sm text-foreground">
              <TruncatingTooltip text={seat.displayName} className="min-w-0" />
              {seat.isSelf && (
                <span className="shrink-0 text-paragraph-xs text-muted-foreground">
                  {t('members.you')}
                </span>
              )}
            </span>
            <FormControl>
              <LocaleAmountInput
                {...field}
                containerClassName="w-28 shrink-0"
                placeholder={t('pots.opening.shares.placeholder')}
              />
            </FormControl>
            <span className="shrink-0 text-paragraph-sm text-muted-foreground">%</span>
          </div>
          <FormMessage />
        </FormItem>
      )}
    />
  );
}
