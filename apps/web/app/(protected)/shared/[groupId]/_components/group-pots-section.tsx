'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { ArrowRight, Coins, HandCoins, Plus } from 'lucide-react';
import { useTranslations } from 'next-intl';

import {
  Badge,
  Button,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@repo/ui/components';
import { PotFormDialog } from '@/app/(protected)/shared/_components/pot-form-dialog';
import { potLabel } from '@/app/(protected)/shared/pot-rules';
import { DismissableHint } from '@/components/dismissable-hint';
import { EmptyState } from '@/components/empty-state';
import { SectionHeader } from '@/components/section-header';
import { sharedPotPath, sharedSharePath } from '@/config/routes';
import type { Group } from '@/lib/api/groups';
import type { Pot } from '@/lib/api/pots';
import { useFormatters } from '@/lib/i18n/formatters';

interface GroupPotsSectionProps {
  group: Group;
  pots: Pot[];
  preferredCurrencies?: string[];
}

/*
 * The group's shared money, on its hub.
 *
 * The shape follows A4 — the pot container stays invisible until there is more than one. With a single
 * pot the section renders THAT POT's headline directly, so there is no list of one and nothing to
 * manage; a second pot turns it into a list, and only then does a pot need a name of its own.
 *
 * Every member sees the identical section. Only the create control is gated, on group admin, which is
 * the API's rule too — and administration grants no additional visibility anywhere.
 *
 * The guided flow is offered only while the group has NOTHING shared, which is the case it is for:
 * starting from a private holding. Once shared money exists, the flows live on ITS page, where the
 * ownership history is known — from here they could only guess whether adding to it is safe, and
 * putting a holding into an already-divided pot hands its value to every owner pro-rata.
 */
export function GroupPotsSection({ group, pots, preferredCurrencies }: GroupPotsSectionProps) {
  const t = useTranslations('shared');
  const router = useRouter();
  const [createOpen, setCreateOpen] = useState(false);

  const isAdmin = group.myRole === 'admin';
  const single = pots.length === 1 ? pots[0] : undefined;

  return (
    <div className="flex flex-col gap-y-4">
      <div className="flex flex-wrap items-end justify-between gap-x-3 gap-y-2">
        <SectionHeader title={t('pots.title')} description={t('pots.description')} />
        {isAdmin &&
          (pots.length === 0 ? (
            <Button blue asChild>
              <Link href={sharedSharePath(group.id)}>
                <HandCoins className="size-4" />
                {t('pots.share.cta')}
              </Link>
            </Button>
          ) : (
            <Button blue onClick={() => setCreateOpen(true)}>
              <Plus className="size-4" />
              {t('pots.add')}
            </Button>
          ))}
      </div>

      {/*
       * Teaches the one idea the rest of the surface assumes — that a share is a proportion of the
       * whole, not a pile of money — and only once there is a pot for it to be about. No help deep
       * link: co-ownership has no help section yet, so ConceptHint would point at nothing.
       */}
      <DismissableHint storageKey="pot-ownership-hint-dismissed" show={pots.length > 0}>
        {t('pots.hint')}
      </DismissableHint>

      {pots.length === 0 ? (
        <EmptyState
          icon={Coins}
          title={t('pots.emptyTitle')}
          description={isAdmin ? t('pots.emptyDescription') : t('pots.emptyDescriptionMember')}
        />
      ) : single ? (
        <SinglePotCard pot={single} />
      ) : (
        <PotsTable pots={pots} />
      )}

      <PotFormDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        groupId={group.id}
        preferredCurrencies={preferredCurrencies}
        onSuccess={() => router.refresh()}
      />
    </div>
  );
}

/*
 * The group's only pot, rendered as itself rather than as a row in a list of one. The three figures are
 * what the hub is for: what it is worth, what share is yours, and whether you can change anything.
 */
function SinglePotCard({ pot }: { pot: Pot }) {
  const fmt = useFormatters();
  const t = useTranslations('shared');

  const stats = [
    {
      label: t('pots.card.value'),
      // Null NAV is "we have not valued this", never 0 — a pot with no holdings and one worth nothing
      // are different answers, and only one of them can price units.
      value: pot.nav === null ? t('pots.unvalued') : fmt.amount(pot.nav, pot.baseCurrency),
    },
    { label: t('pots.card.myShare'), value: `${fmt.sharePct(Number(pot.myPercentage))}%` },
    { label: t('pots.card.members'), value: String(pot.shares.length) },
  ];

  return (
    <div className="flex flex-col p-4 gap-y-4 bg-muted/30 border border-border rounded-1.5xl">
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
        <span className="flex flex-wrap items-center gap-x-2">
          <span className="text-paragraph-medium text-foreground">
            {potLabel(pot, t('pots.defaultLabel'))}
          </span>
          <Badge variant="secondary">{pot.baseCurrency}</Badge>
          {/*
           * The glance version of the pot page's freshness line. It belongs HERE as well as there,
           * because an indicator you only see once you have gone looking cannot prompt anyone to go
           * looking — the hub is where a household notices a pot has fallen behind.
           */}
          {pot.isStale && <Badge variant="outline">{t('pots.freshness.badge')}</Badge>}
          {!pot.canWrite && <Badge variant="secondary">{t('pots.readOnly')}</Badge>}
        </span>
        <Button variant="outline" asChild>
          <Link href={sharedPotPath(pot.id)}>
            {t('pots.card.open')}
            <ArrowRight className="size-4" />
          </Link>
        </Button>
      </div>

      <dl className="grid grid-cols-1 sm:grid-cols-3 gap-x-6 gap-y-4">
        {stats.map((stat) => (
          <div key={stat.label} className="flex flex-col gap-y-1">
            <dt className="text-paragraph-xs text-muted-foreground">{stat.label}</dt>
            <dd className="text-paragraph-medium tabular-nums text-foreground">{stat.value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

// Two or more pots: a list, where the name finally carries meaning because there is something to tell
// apart. The default pot still shows its fallback label rather than a blank cell.
function PotsTable({ pots }: { pots: Pot[] }) {
  const fmt = useFormatters();
  const t = useTranslations('shared');

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>{t('pots.table.name')}</TableHead>
          <TableHead className="w-40 text-right">{t('pots.table.value')}</TableHead>
          <TableHead className="w-32 text-right">{t('pots.table.myShare')}</TableHead>
          <TableHead className="w-28 text-center">{t('pots.table.actions')}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {pots.map((pot) => (
          <TableRow key={pot.id}>
            <TableCell className="text-paragraph-sm-medium">
              <span className="flex flex-wrap items-center gap-x-2">
                {potLabel(pot, t('pots.defaultLabel'))}
                <Badge variant="secondary">{pot.baseCurrency}</Badge>
                {pot.isStale && <Badge variant="outline">{t('pots.freshness.badge')}</Badge>}
                {!pot.canWrite && <Badge variant="secondary">{t('pots.readOnly')}</Badge>}
              </span>
            </TableCell>
            <TableCell className="text-right text-paragraph-sm tabular-nums">
              {pot.nav === null ? t('pots.unvalued') : fmt.amount(pot.nav, pot.baseCurrency)}
            </TableCell>
            <TableCell className="text-right text-paragraph-sm tabular-nums">
              {`${fmt.sharePct(Number(pot.myPercentage))}%`}
            </TableCell>
            <TableCell className="text-center">
              <Button variant="outline" size="sm" asChild>
                <Link href={sharedPotPath(pot.id)}>{t('pots.card.open')}</Link>
              </Button>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
