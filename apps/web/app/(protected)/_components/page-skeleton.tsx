import { cookies } from 'next/headers';
import { getTranslations } from 'next-intl/server';

import { buttonVariants, Skeleton } from '@repo/ui/components';
import { cn } from '@repo/ui/lib';
import { PageHeader } from '@/app/(protected)/_components/page-header';
import {
  TOOLBAR_ACTIONS,
  TOOLBAR_FILTERS,
  TOOLBAR_ITEM,
  TOOLBAR_ROW,
  TOOLBAR_SEARCH,
} from '@/components/entity-list-toolbar-layout';
import { FALLBACK_PRIMARY_CURRENCY } from '@/lib/constants/currency';
import { PERIOD_PRESETS } from '@/lib/constants/period-presets';
import { ACTIVE_CURRENCY_COOKIE, ORIGINAL_CURRENCY } from '@/lib/stores/currency-store';
import { formatPresetLabel } from '@/lib/utils/period-presets';

// How many placeholder rows a table body shows — enough to fill a laptop viewport, no more.
const TABLE_ROWS = 8;
// Stat tiles across the top of a dashboard, and field rows in a settings panel.
const DASHBOARD_TILES = 4;
const FORM_FIELDS = 4;

export type PageSkeletonBody = 'table' | 'dashboard' | 'form' | 'sections';

export type PeriodPickerPlacement = 'header' | 'toolbar';

/*
 * One control of a list toolbar, by the kind of control it is and the text it shows. The text is what
 * makes the placeholder the control's real width — and therefore the row wrap where the real row does,
 * in either language. In a `loading.tsx` the text is a full translation key; `PageSkeleton` resolves it.
 */
export type ToolbarControl<Text = string> =
  // A `FilterCombobox` trigger: icon, its "all" label, chevron.
  | { kind: 'filter'; label: Text }
  // `SegmentedPills`: one pill per option, in one bordered group.
  | { kind: 'segmented'; labels: Text[] }
  // The show-archived `Pill`.
  | { kind: 'pill'; label: Text }
  // An outline trailing action (an import link, a refresh button); `smallIcon` for a size-3.5 icon.
  | { kind: 'outline'; label: Text; smallIcon?: boolean }
  // The blue add button.
  | { kind: 'add'; label: Text };

/*
 * What a list page's `EntityListToolbar` holds, in order. Only the controls every visitor sees belong
 * here: the scope pill (a group member's) and the collections filter (someone who has a collection)
 * depend on data a loading state cannot read.
 */
export interface ToolbarShape<Text = string> {
  filters?: ToolbarControl<Text>[];
  actions?: ToolbarControl<Text>[];
}

interface PageSkeletonLayoutProps {
  // The muted "back to …" link a detail page opens with.
  backLink?: boolean;
  // The detail and wizard pages space their blocks `gap-y-6` rather than the list pages' `gap-y-4`.
  loose?: boolean;
  body: PageSkeletonBody;
}

interface PageSkeletonProps extends PageSkeletonLayoutProps {
  // The page's translation namespace, whose `title` and `subtitle` ARE its header. Omit it when the
  // page's title is DATA (an account's or a group's name), which a loading state cannot know.
  namespace?: string;
  // The page's title is static but its subtitle depends on data (a filter's name): paint the title
  // and a placeholder where the subtitle goes, rather than a default subtitle the page contradicts.
  subtitleIsData?: boolean;
  // The list toolbar under the header, with translation keys for its labels — or `'add-only'` for
  // the groups page's lone button.
  toolbar?: ToolbarShape | 'add-only';
  /*
   * Where the page renders `DashboardPeriodPicker`: `'header'` beside the header (stacked under it
   * below `sm`, the finance and main dashboards), or `'toolbar'` in a search + picker row under it (the
   * investor dashboard). Its labels come from `<namespace>.period` and the default presets, so the
   * placeholder is as wide as the picker.
   */
  periodPicker?: PeriodPickerPlacement;
  /*
   * The translation key of the warning a page shows when the display currency is "original" — which
   * is also what a visitor with no currency cookie gets. The page decides it from that cookie alone, so
   * the loading state can too, and reserves the warning's line(s) when it will show: under the header
   * (the investor dashboard), or under the header ROW on a page whose period picker sits beside its
   * header (the main and finance dashboards, which render it below that row). Its figure names the
   * user's primary currency, a setting this state cannot read; a three-letter stand-in takes the same
   * width, and it is never visible.
   */
  currencyFallback?: string;
}

// What each route's `loading.tsx` renders: resolves the copy, then draws the view below.
export async function PageSkeleton({
  namespace,
  subtitleIsData = false,
  toolbar,
  periodPicker,
  currencyFallback,
  ...layout
}: PageSkeletonProps) {
  const tAll = await getTranslations();
  const savedCurrency = (await cookies()).get(ACTIVE_CURRENCY_COOKIE)?.value;
  const showsCurrencyFallback =
    currencyFallback !== undefined &&
    (savedCurrency === undefined || savedCurrency === ORIGINAL_CURRENCY);
  const t = namespace ? await getTranslations(namespace) : null;

  const resolve = (control: ToolbarControl): ToolbarControl =>
    control.kind === 'segmented'
      ? { ...control, labels: control.labels.map((key) => tAll(key)) }
      : { ...control, label: tAll(control.label) };

  // The period picker's default labels (a user's own presets are data this state cannot read).
  const period =
    periodPicker && t
      ? {
          presets: PERIOD_PRESETS.map((preset) =>
            formatPresetLabel(preset.code, {
              ytd: t('period.ytd'),
              all: t('period.all'),
              monthSuffix: tAll('common.period.monthSuffix'),
              yearSuffix: tAll('common.period.yearSuffix'),
            }),
          ),
          custom: t('period.custom'),
          placement: periodPicker,
        }
      : undefined;

  return (
    <PageSkeletonView
      status={tAll('common.loading.status')}
      title={t?.('title')}
      subtitle={subtitleIsData ? undefined : t?.('subtitle')}
      toolbar={
        toolbar === 'add-only' || toolbar === undefined
          ? toolbar
          : { filters: toolbar.filters?.map(resolve), actions: toolbar.actions?.map(resolve) }
      }
      period={period}
      notice={
        showsCurrencyFallback
          ? tAll.rich(currencyFallback, {
              currency: FALLBACK_PRIMARY_CURRENCY,
              bold: (chunks) => <strong>{chunks}</strong>,
            })
          : undefined
      }
      {...layout}
    />
  );
}

interface PageSkeletonViewProps extends PageSkeletonLayoutProps {
  // The loading page's screen-reader status.
  status: string;
  // The page's real header. Omitted when the page's title is DATA (an account's or a group's name),
  // which a loading state cannot know — the header is then a placeholder of the same size.
  title?: string;
  subtitle?: string;
  // The list toolbar, its labels already translated.
  toolbar?: ToolbarShape | 'add-only';
  // A warning the page shows under its header, whose line(s) the placeholder reserves.
  notice?: React.ReactNode;
  // The period picker's labels, already translated, and where the page renders it.
  period?: { presets: string[]; custom: string; placement: PeriodPickerPlacement };
}

/*
 * The one loading state every protected route renders, through `PageSkeleton` in its `loading.tsx`.
 *
 * It paints the page's frame at the page's own sizes — the same `p-8` column, the real `PageHeader`
 * when the title is known, and placeholders laid out by the same classes, and sized by the same text,
 * as the controls that replace them — so the swap to the loaded page moves nothing. The header is the
 * one part rendered for real: it is the part a user reads to know the navigation worked.
 *
 * The placeholder block fades in after a short delay rather than appearing at once, so a page that
 * loads quickly swaps straight from its header to its content instead of flashing grey bars. The fade
 * is opacity only, which the reduced-motion rule allows; the Skeleton's own pulse is gated in the base.
 *
 * `aria-busy` marks the region that is still coming; the status line is what a screen reader
 * announces, since the placeholders themselves say nothing.
 */
export function PageSkeletonView({
  status,
  title,
  subtitle,
  backLink = false,
  toolbar,
  loose = false,
  period,
  notice,
  body,
}: PageSkeletonViewProps) {
  const header =
    title !== undefined && subtitle !== undefined ? (
      <PageHeader title={title} subtitle={subtitle} />
    ) : title !== undefined ? (
      <div className="flex flex-col gap-y-1">
        <h1 className="text-heading-2 text-foreground">{title}</h1>
        <Skeleton className="w-80 max-w-full h-6 rounded-md" />
        {notice !== undefined && period?.placement !== 'header' && (
          <NoticePlaceholder>{notice}</NoticePlaceholder>
        )}
      </div>
    ) : (
      <div className="flex flex-col gap-y-1">
        <Skeleton className="w-64 max-w-full h-10 rounded-lg" />
        <Skeleton className="w-80 max-w-full h-6 rounded-md" />
      </div>
    );

  return (
    <div
      className={cn('flex flex-col flex-1 p-8', loose ? 'gap-y-6' : 'gap-y-4')}
      data-testid="page-skeleton"
    >
      <p role="status" className="sr-only">
        {status}
      </p>
      {backLink && <Skeleton className="w-40 h-5 rounded-md" />}
      {period?.placement === 'header' ? (
        // The dashboards' header row, with the classes the pages give it.
        <div className="flex flex-col gap-y-4 sm:flex-row sm:items-start sm:justify-between">
          {header}
          <PeriodPickerSkeleton
            presets={period.presets}
            custom={period.custom}
            className="sm:max-w-md"
          />
        </div>
      ) : (
        header
      )}
      <div
        aria-busy="true"
        className="flex flex-col gap-y-4 animate-in fade-in fill-mode-backwards delay-150 duration-300"
      >
        {notice !== undefined && period?.placement === 'header' && (
          <NoticePlaceholder>{notice}</NoticePlaceholder>
        )}
        {period?.placement === 'toolbar' && (
          // The investor dashboard's row (`InvestorDashboardAnimatedToolbar`): the search grows, and the
          // picker takes its own row until `xl`.
          <div className="flex flex-wrap items-center gap-x-2 gap-y-2">
            <div className="min-w-0 flex-1">
              <Skeleton className="h-9 rounded-lg" />
            </div>
            <div className="basis-full xl:basis-auto">
              <PeriodPickerSkeleton presets={period.presets} custom={period.custom} />
            </div>
          </div>
        )}
        {toolbar === 'add-only' && <AddOnlyToolbarSkeleton />}
        {toolbar && toolbar !== 'add-only' && <ToolbarSkeleton {...toolbar} />}
        {body === 'table' && <TableSkeleton />}
        {body === 'dashboard' && <DashboardSkeleton />}
        {body === 'form' && <FormSkeleton />}
        {body === 'sections' && <SectionsSkeleton />}
      </div>
    </div>
  );
}

interface SizedPlaceholderProps {
  // The real control's box classes — its height, padding, gap, type and radius.
  className: string;
  // The real control's content: its label and an empty box where each icon sits.
  children: React.ReactNode;
}

/*
 * A placeholder exactly the size of a control: the control's own box, holding its own content
 * invisibly, under a Skeleton of the same shape. Taking the width from the content (rather than a
 * guessed `w-*`) is what makes two placeholders wrap onto two rows exactly when the two controls do.
 */
function SizedPlaceholder({ className, children }: SizedPlaceholderProps) {
  return (
    <div className={cn('relative', className)}>
      <span className="invisible flex items-center gap-[inherit] whitespace-nowrap">
        {children}
      </span>
      <Skeleton className="absolute inset-0 rounded-[inherit]" />
    </div>
  );
}

/*
 * A `WarningHint`'s line(s) under a header: its icon box and its text, invisible and free to wrap at
 * the column's width exactly as the real warning does, under a Skeleton.
 */
function NoticePlaceholder({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative flex items-center gap-x-2" data-testid="page-skeleton-notice">
      <span className="size-4 shrink-0" />
      <p className="invisible text-paragraph-xs whitespace-pre-line">{children}</p>
      <Skeleton className="absolute inset-0 rounded-md" />
    </div>
  );
}

// An empty box the size of an icon, standing where the control draws one.
function IconBox({ small = false }: { small?: boolean }) {
  return <span className={cn('shrink-0', small ? 'size-3.5' : 'size-4')} />;
}

/*
 * One preset pill's box: `toggleVariants({ size: 'sm' })` plus the group's `px-2` and `flex-1`. Restated
 * rather than imported because `toggle.tsx` is a client module, whose exports a server component can
 * only render, not call; the layout e2e (`loading-layout.auth.spec.ts`) fails if this stops matching.
 */
const PRESET_BOX =
  'inline-flex flex-1 shrink-0 h-8 min-w-8 items-center justify-center px-2 gap-2 rounded-md text-paragraph-sm-medium';

// The box classes of an outline or a blue `Button` at the default size — the toolbar's pills and actions.
const BUTTON_BOX = cn(buttonVariants({ variant: 'outline' }), 'border-transparent shadow-none');

// One toolbar control's placeholder, by kind — each mirroring that control's own box.
function ControlPlaceholder({ control }: { control: ToolbarControl }) {
  switch (control.kind) {
    case 'filter':
      // `FilterCombobox`: its root takes the item classes, its trigger `h-9 w-full px-3 gap-x-2`.
      return (
        <div className={TOOLBAR_ITEM}>
          <SizedPlaceholder
            className={cn(
              buttonVariants({ variant: 'outline' }),
              'h-9 w-full justify-between px-3 gap-x-2 border-transparent shadow-none text-paragraph-sm font-normal',
            )}
          >
            <span className="flex items-center gap-x-2">
              <IconBox />
              {control.label}
            </span>
            <IconBox />
          </SizedPlaceholder>
        </div>
      );
    case 'segmented':
      // `SegmentedPills`: a `p-0.5` bordered group of `h-8 px-2.5` pills, never narrower than all of them.
      return (
        <SizedPlaceholder className="flex min-w-fit items-center p-0.5 border border-transparent rounded-md">
          {control.labels.map((label) => (
            <span
              key={label}
              className={cn(
                buttonVariants({ variant: 'outline' }),
                'h-8 px-2.5 border-0 text-paragraph-sm',
              )}
            >
              {label}
            </span>
          ))}
        </SizedPlaceholder>
      );
    case 'pill':
      return (
        <SizedPlaceholder className={cn(BUTTON_BOX, TOOLBAR_ITEM, 'rounded-md')}>
          <IconBox />
          {control.label}
        </SizedPlaceholder>
      );
    case 'outline':
      return (
        <SizedPlaceholder className={cn(BUTTON_BOX, TOOLBAR_ITEM)}>
          <IconBox small={control.smallIcon} />
          {control.label}
        </SizedPlaceholder>
      );
    case 'add':
      return (
        <SizedPlaceholder className={cn(BUTTON_BOX, TOOLBAR_ITEM)}>
          <IconBox />
          {control.label}
        </SizedPlaceholder>
      );
  }
}

/*
 * The list toolbar, built from `EntityListToolbar`'s own layout classes so it wraps at the same
 * widths: the search item, the filters group (its own row until `lg`) and the actions group (its own
 * row until `md`), each control placeholder sized by that control's own box and text.
 */
function ToolbarSkeleton({ filters = [], actions = [] }: ToolbarShape) {
  return (
    <div className={TOOLBAR_ROW} data-testid="page-skeleton-toolbar">
      <div className={TOOLBAR_SEARCH}>
        <Skeleton className="h-9 rounded-lg" />
      </div>
      {filters.length > 0 && (
        <div className={TOOLBAR_FILTERS}>
          {filters.map((control, i) => (
            <ControlPlaceholder key={i} control={control} />
          ))}
        </div>
      )}
      {actions.length > 0 && (
        <div className={TOOLBAR_ACTIONS}>
          {actions.map((control, i) => (
            <ControlPlaceholder key={i} control={control} />
          ))}
        </div>
      )}
    </div>
  );
}

// The groups page's toolbar: one add button at the end of its row.
function AddOnlyToolbarSkeleton() {
  return (
    <div className="flex justify-end" data-testid="page-skeleton-toolbar">
      <Skeleton className="w-32 h-8 rounded-lg" />
    </div>
  );
}

/*
 * The dashboards' period picker, in the picker's own wrapping row: the preset group (a bordered
 * `PillToggleGroup` of `h-8 px-2` items that never shrink) and the `h-9 px-3` custom-range button,
 * each in a `flex-1` item like the real ones, each sized by its real labels.
 */
interface PeriodPickerSkeletonProps {
  presets: string[];
  custom: string;
  // What the page passes as the picker's own `className`.
  className?: string;
}

function PeriodPickerSkeleton({ presets, custom, className }: PeriodPickerSkeletonProps) {
  return (
    <div
      className={cn('flex flex-wrap items-center gap-x-2 gap-y-2', className)}
      data-testid="page-skeleton-period"
    >
      <div className="flex-1">
        <SizedPlaceholder className="flex w-full border border-transparent rounded-full overflow-hidden">
          {presets.map((label) => (
            <span key={label} className={PRESET_BOX}>
              {label}
            </span>
          ))}
        </SizedPlaceholder>
      </div>
      <div className="flex-1">
        <SizedPlaceholder className={cn(BUTTON_BOX, 'h-9 w-full gap-x-1.5 px-3 text-paragraph-sm')}>
          <IconBox />
          {custom}
        </SizedPlaceholder>
      </div>
    </div>
  );
}

// A header row and body rows at the table primitive's heights (`h-10` head, 49px rows).
function TableSkeleton() {
  return (
    <div className="flex flex-col w-full">
      <div className="flex h-10 items-center px-2 gap-x-6 border-b border-border-3">
        <Skeleton className="w-24 h-4 rounded-md" />
        <Skeleton className="w-32 h-4 rounded-md" />
        <Skeleton className="hidden sm:block w-28 h-4 rounded-md" />
        <Skeleton className="hidden md:block w-24 h-4 rounded-md" />
      </div>
      {Array.from({ length: TABLE_ROWS }, (_, i) => (
        <div key={i} className="flex h-[49px] items-center px-2 gap-x-6 border-b border-border-3">
          <Skeleton className="w-24 h-4 rounded-md" />
          <Skeleton className="w-32 h-4 rounded-md" />
          <Skeleton className="hidden sm:block w-28 h-4 rounded-md" />
          <Skeleton className="hidden md:block w-24 h-4 rounded-md" />
        </div>
      ))}
    </div>
  );
}

// Stat tiles, then the wide chart and the two panels under it.
function DashboardSkeleton() {
  return (
    <div className="flex flex-col gap-y-4" data-testid="page-skeleton-dashboard">
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        {Array.from({ length: DASHBOARD_TILES }, (_, i) => (
          <Skeleton key={i} className="h-28 rounded-1.5xl" />
        ))}
      </div>
      <Skeleton className="h-80 rounded-1.5xl" />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Skeleton className="h-72 rounded-1.5xl" />
        <Skeleton className="h-72 rounded-1.5xl" />
      </div>
    </div>
  );
}

// A settings panel: label + field pairs in a bounded column.
function FormSkeleton() {
  return (
    <div className="flex flex-col w-full max-w-2xl gap-y-6">
      {Array.from({ length: FORM_FIELDS }, (_, i) => (
        <div key={i} className="flex flex-col gap-y-2">
          <Skeleton className="w-32 h-4 rounded-md" />
          <Skeleton className="h-9 rounded-lg" />
        </div>
      ))}
    </div>
  );
}

// A detail page's stacked sections: a summary panel, then section blocks.
function SectionsSkeleton() {
  return (
    <div className="flex flex-col gap-y-6">
      <Skeleton className="h-32 rounded-1.5xl" />
      <Skeleton className="h-64 rounded-1.5xl" />
      <Skeleton className="h-64 rounded-1.5xl" />
    </div>
  );
}
