'use client';

import { useRef, useState, useTransition } from 'react';
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
import {
  autosaveErrorMessage,
  AutosaveRefusal,
  useAutosaveToggles,
} from '@/lib/hooks/use-autosave-toggles';

interface Access {
  canView: boolean;
  canWrite: boolean;
}

const sameAccess = (a: Access, b: Access) => a.canView === b.canView && a.canWrite === b.canWrite;

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
 *
 * The two switches save on their own, through `useAutosaveToggles` keyed by seat: they flip at once and
 * stay live, a burst on one seat writes once, and a failed write puts that seat back. A save that lands
 * is recorded here as the seat's explicit row rather than re-read with `router.refresh()`, because a
 * refresh is a navigation and would cancel the next seat's write if it started first. Reset is not a
 * toggle: it waits for its answer and refreshes, as before.
 */
export function PotPermissionsSection({ pot, group }: PotPermissionsSectionProps) {
  const t = useTranslations('shared');
  const router = useRouter();
  const [pendingSeat, setPendingSeat] = useState<number | null>(null);
  const [isRefreshing, startRefresh] = useTransition();
  // Whether a save since the last refresh changed the viewer's OWN access, which the rest of the page
  // (the header, the holdings' actions) is drawn from.
  const ownAccessChanged = useRef(false);
  // Explicit rows written since the server last rendered this pot, keyed by seat id. Dropped whenever
  // the server's own permissions arrive, which then include them.
  const [saved, setSaved] = useState<{ from: Pot['permissions']; rows: Map<number, Access> }>(
    () => ({ from: pot.permissions, rows: new Map() }),
  );
  if (saved.from !== pot.permissions) setSaved({ from: pot.permissions, rows: new Map() });

  const seats = group.members.filter((m) => m.isActive);
  const byMember = new Map<number, Access>(
    pot.permissions.map((permission) => [permission.memberId, permission]),
  );
  saved.rows.forEach((access, seatId) => byMember.set(seatId, access));

  // The effective answer for one seat, resolved exactly as the database's own helper does: an explicit
  // row if there is one, otherwise the pot's visibility default. Write has NO such default — it is
  // granted per member and nowhere else, so a pot with no rows is readable by its group and writable
  // by nobody.
  const effective = (seatId: number): Access => {
    const explicit = byMember.get(seatId);
    return explicit
      ? { canView: explicit.canView, canWrite: explicit.canWrite }
      : { canView: pot.visibility === 'members', canWrite: false };
  };

  const access = useAutosaveToggles<Access>({
    confirmed: (seat) => effective(Number(seat)),
    equals: sameAccess,
    write: async (seat, next) => {
      const result = await setPotPermission(pot.id, Number(seat), next);
      if (!result.ok) throw new AutosaveRefusal(result.conflictDetail);
      setSaved((current) => ({
        from: current.from,
        rows: new Map(current.rows).set(Number(seat), next),
      }));
      if (seats.find((member) => member.id === Number(seat))?.isSelf) {
        ownAccessChanged.current = true;
      }
      toast.success(t('pots.permissions.success'));
    },
    onError: (_, error) => toast.error(autosaveErrorMessage(error, t('pots.permissions.error'))),
    // Only once nothing is left to write, and only when it changes what the page shows, since a
    // refresh started before a write cancels that write. The switches wait for it like any navigation.
    onSettled: () => {
      if (!ownAccessChanged.current) return;
      ownAccessChanged.current = false;
      startRefresh(() => router.refresh());
    },
  });

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

      <Table label={t('pots.permissions.title')}>
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
              explicit={byMember.has(seat.id)}
              access={access.value(String(seat.id))}
              saving={access.isPending(String(seat.id))}
              resetting={pendingSeat === seat.id || isRefreshing}
              onSet={(canView, canWrite) => access.set(String(seat.id), { canView, canWrite })}
              onReset={() => run(seat.id, () => clearPotPermission(pot.id, seat.id))}
            />
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

interface PermissionRowProps {
  seat: GroupMember;
  // Whether the seat has its own row rather than following the pot's default.
  explicit: boolean;
  // What the switches show: the seat's effective access, or the one just asked for.
  access: Access;
  // A switch's write is still settling, so there is nothing to reset to yet.
  saving: boolean;
  // A reset, or the refresh after the viewer's own access changed, is on its way.
  resetting: boolean;
  onSet: (canView: boolean, canWrite: boolean) => void;
  onReset: () => void;
}

function PermissionRow({
  seat,
  explicit,
  access,
  saving,
  resetting,
  onSet,
  onReset,
}: PermissionRowProps) {
  const t = useTranslations('shared');

  const { canView, canWrite } = access;

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
          disabled={resetting}
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
          disabled={resetting}
          aria-label={t('pots.permissions.table.write')}
          // And granting write implies view, resolved server-side rather than guessed here.
          onCheckedChange={(next) => onSet(next ? true : canView, next)}
        />
      </TableCell>
      <TableCell className="text-center text-paragraph-xs text-muted-foreground">
        {explicit || saving ? t('pots.permissions.explicit') : t('pots.permissions.inherited')}
      </TableCell>
      <TableCell className="text-center">
        {/* Only an explicit row can be reset; a seat already following the default has nothing to drop. */}
        {explicit && (
          <RowActionButton
            icon={RotateCcw}
            tooltip={t('pots.permissions.reset')}
            variant="muted"
            disabled={resetting || saving}
            onClick={onReset}
          />
        )}
      </TableCell>
    </TableRow>
  );
}
