'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { RotateCcw } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

import {
  Badge,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@repo/ui/components';
import { clearPotPermission, setPotPermission } from '@/app/(protected)/shared/pot-actions';
import { RowActionButton } from '@/components/row-action-button';
import { SectionHeader } from '@/components/section-header';
import type { Group, GroupMember } from '@/lib/api/groups';
import type { Pot } from '@/lib/api/pots';

interface PotPermissionsSectionProps {
  pot: Pot;
  group: Group;
}

/*
 * Per-member access to this pot. Rendered only for a group admin — and that is the whole of what being
 * an admin buys here: **administration never grants visibility.** An admin whose own row says
 * `canView: false` sees nothing of the pot, which is exactly why the API resolves this section's rules
 * without ever consulting `role`.
 *
 * A seat with no explicit row follows the pot's own default, which is why "reset" is a distinct action
 * from switching view off: "no opinion" and "denied" differ the moment the pot's default changes.
 */
export function PotPermissionsSection({ pot, group }: PotPermissionsSectionProps) {
  const t = useTranslations('shared');
  const router = useRouter();
  const [pendingSeat, setPendingSeat] = useState<number | null>(null);

  const seats = group.members.filter((m) => m.isActive);
  const byMember = new Map(pot.permissions.map((permission) => [permission.memberId, permission]));

  async function run(
    seatId: number,
    action: () => Promise<{ ok: boolean; conflictDetail?: string }>,
  ) {
    setPendingSeat(seatId);
    try {
      const result = await action();
      if (!result.ok) {
        toast.error(result.conflictDetail ?? t('pots.permissions.error'));
        return;
      }
      toast.success(t('pots.permissions.success'));
      router.refresh();
    } catch {
      toast.error(t('pots.permissions.error'));
    } finally {
      setPendingSeat(null);
    }
  }

  return (
    <div className="flex flex-col gap-y-4">
      <SectionHeader
        title={t('pots.permissions.title')}
        description={t('pots.permissions.description', {
          visibility: t(`pots.visibility.${pot.visibility}`),
        })}
      />

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{t('pots.permissions.table.member')}</TableHead>
            <TableHead className="w-32 text-center">{t('pots.permissions.table.view')}</TableHead>
            <TableHead className="w-32 text-center">{t('pots.permissions.table.write')}</TableHead>
            <TableHead className="w-28 text-center">{t('pots.permissions.table.source')}</TableHead>
            <TableHead className="w-20 text-center">
              {t('pots.permissions.table.actions')}
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {seats.map((seat) => (
            <PermissionRow
              key={seat.id}
              seat={seat}
              pot={pot}
              explicit={byMember.get(seat.id)}
              pending={pendingSeat === seat.id}
              onSet={(canView, canWrite) =>
                run(seat.id, () => setPotPermission(pot.id, seat.id, { canView, canWrite }))
              }
              onReset={() => run(seat.id, () => clearPotPermission(pot.id, seat.id))}
            />
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function PermissionRow({
  seat,
  pot,
  explicit,
  pending,
  onSet,
  onReset,
}: {
  seat: GroupMember;
  pot: Pot;
  explicit: { canView: boolean; canWrite: boolean } | undefined;
  pending: boolean;
  onSet: (canView: boolean, canWrite: boolean) => void;
  onReset: () => void;
}) {
  const t = useTranslations('shared');

  /*
   * The effective answer, resolved exactly as the database's own helper does: an explicit row if there
   * is one, otherwise the pot's visibility default. Write has NO such default — it is granted per
   * member and nowhere else, so a pot with no rows is readable by its group and writable by nobody.
   */
  const canView = explicit ? explicit.canView : pot.visibility === 'members';
  const canWrite = explicit?.canWrite ?? false;

  return (
    <TableRow>
      <TableCell className="text-paragraph-sm-medium">
        <span className="flex flex-wrap items-center gap-x-2">
          {seat.displayName}
          {seat.isSelf && <Badge variant="secondary">{t('pots.ownership.you')}</Badge>}
        </span>
      </TableCell>
      <TableCell className="text-center">
        <Switch
          blue
          checked={canView}
          disabled={pending}
          aria-label={t('pots.permissions.table.view')}
          // Turning view off also removes write, which the API and a table CHECK both enforce: writing
          // something you cannot see is not a state this product has a meaning for.
          onCheckedChange={(next) => onSet(next, next ? canWrite : false)}
        />
      </TableCell>
      <TableCell className="text-center">
        <Switch
          blue
          checked={canWrite}
          disabled={pending}
          aria-label={t('pots.permissions.table.write')}
          // And granting write implies view, resolved server-side rather than guessed here.
          onCheckedChange={(next) => onSet(next ? true : canView, next)}
        />
      </TableCell>
      <TableCell className="text-center text-paragraph-xs text-muted-foreground">
        {explicit ? t('pots.permissions.explicit') : t('pots.permissions.inherited')}
      </TableCell>
      <TableCell className="text-center">
        {/* Only an explicit row can be reset; a seat already following the default has nothing to drop. */}
        {explicit && (
          <RowActionButton
            icon={RotateCcw}
            tooltip={t('pots.permissions.reset')}
            ariaLabel="Reset to the pot default"
            variant="muted"
            disabled={pending}
            onClick={onReset}
          />
        )}
      </TableCell>
    </TableRow>
  );
}
