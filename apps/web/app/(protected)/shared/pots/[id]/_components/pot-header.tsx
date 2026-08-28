'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Eye, Pencil, Trash2 } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

import { Badge, Button } from '@repo/ui/components';
import { PageHeader } from '@/app/(protected)/_components/page-header';
import { PotFormDialog } from '@/app/(protected)/shared/_components/pot-form-dialog';
import { deletePot } from '@/app/(protected)/shared/pot-actions';
import { canDeletePot, potLabel } from '@/app/(protected)/shared/pot-rules';
import { ConfirmDialog } from '@/components/confirm-dialog';
import { sharedGroupPath } from '@/config/routes';
import type { Group } from '@/lib/api/groups';
import type { Pot, PotHoldings } from '@/lib/api/pots';
import { useFormatters } from '@/lib/i18n/formatters';

interface PotHeaderProps {
  pot: Pot;
  group: Group;
  holdings: PotHoldings;
}

/*
 * The pot's identity and its three headline figures. Renamed and deleted from here because both are
 * group administration rather than money movement — which is also why they are gated on `myRole` and
 * not on `canWrite`.
 *
 * A viewer with read-only access gets ONE line saying so, rather than a disabled control beside every
 * action further down. The reason is the same for all of them, so stating it once is what makes the
 * absences legible; repeating it per control would be five copies of one sentence.
 */
export function PotHeader({ pot, group, holdings }: PotHeaderProps) {
  const fmt = useFormatters();
  const t = useTranslations('shared');
  const router = useRouter();
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [pending, setPending] = useState(false);

  const isAdmin = group.myRole === 'admin';
  const label = potLabel(pot, t('pots.defaultLabel'));

  const stats = [
    {
      label: t('pots.card.value'),
      // A null NAV is "not valued", never zero: a pot holding nothing and a pot worth nothing are
      // different answers and only one of them can price a unit.
      value: pot.nav === null ? t('pots.unvalued') : fmt.amount(pot.nav, pot.baseCurrency),
    },
    { label: t('pots.card.myShare'), value: `${fmt.sharePct(Number(pot.myPercentage))}%` },
    { label: t('pots.card.members'), value: String(pot.shares.length) },
    { label: t('pots.card.created'), value: fmt.timestampDate(pot.createdAt) },
  ];

  async function onDelete() {
    setPending(true);
    try {
      const result = await deletePot(pot.id);
      if (!result.ok) {
        toast.error(result.conflictDetail);
        return;
      }
      toast.success(t('pots.delete.success'));
      // Back to the GROUP HUB, not the groups list: the page we are on no longer exists, and the hub is
      // where the group's remaining shared money is. The comment said hub and the code said list.
      router.push(sharedGroupPath(pot.groupId));
    } catch {
      toast.error(t('pots.delete.error'));
    } finally {
      setPending(false);
      setDeleteOpen(false);
    }
  }

  return (
    <div className="flex flex-col gap-y-4">
      <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-2">
        <PageHeader
          title={label}
          subtitle={t('pots.subtitle', { group: group.name })}
          trailing={
            <span className="flex flex-wrap items-center gap-x-2">
              <Badge variant="secondary">{pot.baseCurrency}</Badge>
              <Badge variant="secondary">{t(`pots.visibility.${pot.visibility}`)}</Badge>
            </span>
          }
        />
        {isAdmin && (
          <div className="flex flex-wrap items-center gap-x-2">
            <Button variant="outline" onClick={() => setEditOpen(true)}>
              <Pencil className="size-4" />
              {t('pots.edit')}
            </Button>
            {/*
             * Hidden rather than disabled while the pot still holds something — a Radix tooltip never
             * fires on a disabled trigger, so the explanation would never be readable. The holdings
             * section below is where the "move it out first" affordance lives.
             */}
            {canDeletePot(isAdmin, holdings) && (
              <Button variant="destructive" onClick={() => setDeleteOpen(true)}>
                <Trash2 className="size-4" />
                {t('pots.delete.cta')}
              </Button>
            )}
          </div>
        )}
      </div>

      {/* One line for every withheld write control on the page, because they all have this one reason. */}
      {!pot.canWrite && (
        <p className="flex items-center gap-x-2 text-paragraph-sm text-muted-foreground">
          <Eye className="size-4 shrink-0" />
          {t('pots.readOnlyNotice')}
        </p>
      )}

      <dl className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 p-4 gap-x-6 gap-y-4 bg-muted/30 border border-border rounded-1.5xl">
        {stats.map((stat) => (
          <div key={stat.label} className="flex flex-col gap-y-1">
            <dt className="text-paragraph-xs text-muted-foreground">{stat.label}</dt>
            <dd className="text-paragraph-medium tabular-nums text-foreground">{stat.value}</dd>
          </div>
        ))}
      </dl>

      <PotFormDialog
        open={editOpen}
        onOpenChange={setEditOpen}
        groupId={pot.groupId}
        pot={pot}
        onSuccess={() => router.refresh()}
      />
      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        entity={pot}
        title={t('pots.delete.title')}
        description={() => t('pots.delete.description', { name: label })}
        onConfirm={onDelete}
        loading={pending}
        loadingLabel={t('pots.delete.loading')}
        confirmLabel={t('pots.delete.confirm')}
        cancelLabel={t('form.cancel')}
      />
    </div>
  );
}
