'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Check, Handshake, Trash2, Undo2, Wallet } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

import {
  Badge,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@repo/ui/components';
import { SettlementLegDialog } from '@/app/(protected)/shared/[groupId]/_components/settlement-leg-dialog';
import {
  confirmSettlement,
  deleteSettlement,
  unconfirmSettlement,
} from '@/app/(protected)/shared/settlement-actions';
import {
  canAttachOwnLeg,
  canUnconfirmSettlement,
  ownLegAccountId,
  ownLegAmount,
} from '@/app/(protected)/shared/settlement-rules';
import { ConfirmDialog } from '@/components/confirm-dialog';
import { EmptyState } from '@/components/empty-state';
import { RowActionButton } from '@/components/row-action-button';
import { SectionHeader } from '@/components/section-header';
import type { Account } from '@/lib/api/accounts';
import type { GroupSettlement } from '@/lib/api/group-settlements';
import type { Group } from '@/lib/api/groups';
import { useFormatters } from '@/lib/i18n/formatters';

interface GroupSettlementsSectionProps {
  group: Group;
  settlements: GroupSettlement[];
  accounts: Account[];
}

/*
 * Everything that has cleared a balance: payments between members, and the debts somebody gave up on.
 *
 * A settlement is ONE record both parties see, never two entries to reconcile — which is why the row
 * shows both names and why confirming is an act on the shared row rather than a private note. What
 * confirmation changes is not the arithmetic, which counted the payment from the moment it was
 * recorded, but who may undo it: while pending, either party may delete it (that IS reversing one);
 * once confirmed, nobody can until the payee takes their word back.
 *
 * `canConfirm` and `canDelete` come resolved from the API and are rendered as given. The two rules
 * the response does not carry — taking a confirmation back, and attaching your own cash leg — are
 * mirrored in `settlement-rules.ts`, in one place, and both are documented there.
 */
export function GroupSettlementsSection({
  group,
  settlements,
  accounts,
}: GroupSettlementsSectionProps) {
  const t = useTranslations('shared');
  const router = useRouter();
  const [pendingAction, setPendingAction] = useState(false);
  const [removing, setRemoving] = useState<GroupSettlement | null>(null);
  const [attaching, setAttaching] = useState<GroupSettlement | null>(null);

  const mySeatId = useMemo(
    () => group.members.find((member) => member.isSelf)?.id ?? null,
    [group.members],
  );

  const refresh = () => router.refresh();

  /*
   * One handler for the three one-click acts. Each returns its refusal as data rather than throwing,
   * so a settlement somebody else confirmed while this page sat open explains itself instead of
   * failing silently — the state on screen is a snapshot, and these are the acts most likely to race.
   */
  async function run(
    action: () => Promise<{ ok: boolean; conflictDetail?: string }>,
    successMessage: string,
    errorMessage: string,
  ) {
    setPendingAction(true);
    try {
      const result = await action();
      if (!result.ok) {
        toast.error(result.conflictDetail || errorMessage);
        return;
      }
      toast.success(successMessage);
      refresh();
    } catch {
      toast.error(errorMessage);
    } finally {
      setPendingAction(false);
    }
  }

  return (
    <div className="flex flex-col gap-y-4">
      <SectionHeader title={t('settlements.title')} description={t('settlements.description')} />

      {settlements.length === 0 ? (
        <EmptyState
          icon={Handshake}
          title={t('settlements.emptyTitle')}
          description={t('settlements.emptyDescription')}
        />
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-32">{t('settlements.table.date')}</TableHead>
              <TableHead>{t('settlements.table.between')}</TableHead>
              <TableHead className="w-40 text-right">{t('settlements.table.amount')}</TableHead>
              <TableHead className="w-32">{t('settlements.table.status')}</TableHead>
              <TableHead>{t('settlements.table.notes')}</TableHead>
              <TableHead className="w-32 text-center">{t('settlements.table.actions')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {settlements.map((settlement) => (
              <SettlementRow
                key={settlement.id}
                settlement={settlement}
                mySeatId={mySeatId}
                accounts={accounts}
                disabled={pendingAction}
                onConfirm={() =>
                  run(
                    () => confirmSettlement(group.id, settlement.id),
                    t('settlements.confirmSuccess'),
                    t('settlements.actionError'),
                  )
                }
                onUnconfirm={() =>
                  run(
                    () => unconfirmSettlement(group.id, settlement.id),
                    t('settlements.unconfirmSuccess'),
                    t('settlements.actionError'),
                  )
                }
                onAttach={() => setAttaching(settlement)}
                onRemove={() => setRemoving(settlement)}
              />
            ))}
          </TableBody>
        </Table>
      )}

      <ConfirmDialog
        open={removing !== null}
        onOpenChange={(open) => !open && setRemoving(null)}
        entity={removing}
        title={t('settlements.remove.title')}
        description={(entity) =>
          t(
            `settlements.remove.description.${entity.status === 'written_off' ? 'writeOff' : 'payment'}`,
          )
        }
        loading={pendingAction}
        loadingLabel={t('form.cta.loading')}
        confirmLabel={t('settlements.remove.confirm')}
        cancelLabel={t('form.cancel')}
        onConfirm={async () => {
          if (!removing) return;
          await run(
            () => deleteSettlement(group.id, removing.id),
            t('settlements.remove.success'),
            t('settlements.actionError'),
          );
          setRemoving(null);
        }}
      />

      <SettlementLegDialog
        open={attaching !== null}
        onOpenChange={(open) => !open && setAttaching(null)}
        groupId={group.id}
        settlement={attaching ?? undefined}
        mySeatId={mySeatId}
        accounts={accounts}
        onSuccess={refresh}
      />
    </div>
  );
}

/*
 * One recorded settlement.
 *
 * The amount cell states the bucket figure — what actually came off the balance — and adds the
 * caller's own cash leg beneath it only when that leg crossed currencies, which is the only time the
 * two differ. Within one currency they are the same number, and printing it twice would read as two
 * separate facts.
 */
function SettlementRow({
  settlement,
  mySeatId,
  accounts,
  disabled,
  onConfirm,
  onUnconfirm,
  onAttach,
  onRemove,
}: {
  settlement: GroupSettlement;
  mySeatId: number | null;
  accounts: Account[];
  disabled: boolean;
  onConfirm: () => void;
  onUnconfirm: () => void;
  onAttach: () => void;
  onRemove: () => void;
}) {
  const fmt = useFormatters();
  const t = useTranslations('shared');

  /*
   * The caller's OWN leg, through the rules rather than re-derived here. The inline version this
   * replaces read `toAmount` whenever the caller was on neither side — the payee's figure, shown to
   * somebody with no leg in the settlement at all. It was invisible only because the account lookup
   * below happened to come up empty for the same viewer, which is a second guard doing the first
   * one's job.
   */
  const legAccountId = ownLegAccountId(settlement, mySeatId);
  const legAccount = accounts.find((account) => account.id === legAccountId);
  const legAmount = ownLegAmount(settlement, mySeatId);

  return (
    <TableRow>
      <TableCell>{fmt.date(settlement.date)}</TableCell>
      <TableCell className="text-paragraph-sm">
        {t('settlements.table.pair', {
          from: settlement.fromDisplayName,
          to: settlement.toDisplayName,
        })}
      </TableCell>
      <TableCell className="text-right text-paragraph-sm tabular-nums">
        {/* Each figure names its own currency: a settlement list holds one row per bucket the group
            has a position in, and the two are never converted into each other. */}
        {`${fmt.amount(settlement.amount, settlement.currency)} ${settlement.currency}`}
        {legAccount && legAmount !== null && (
          <span className="block text-paragraph-xs text-muted-foreground">
            {t('settlements.table.leg', {
              amount: fmt.amount(legAmount, legAccount.currency),
              currency: legAccount.currency,
              account: legAccount.name,
            })}
          </span>
        )}
      </TableCell>
      <TableCell>
        <Badge variant={settlement.status === 'confirmed' ? 'default' : 'secondary'}>
          {t(`settlements.status.${settlement.status}`)}
        </Badge>
      </TableCell>
      <TableCell className="max-w-48 truncate text-muted-foreground">
        {settlement.notes ?? '—'}
      </TableCell>
      <TableCell className="text-center" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-center gap-x-1">
          {settlement.canConfirm && (
            <RowActionButton
              icon={Check}
              tooltip={t('settlements.actions.confirm')}
              ariaLabel="Confirm"
              disabled={disabled}
              onClick={onConfirm}
            />
          )}
          {canUnconfirmSettlement(settlement, mySeatId) && (
            <RowActionButton
              icon={Undo2}
              tooltip={t('settlements.actions.unconfirm')}
              ariaLabel="Un-confirm"
              variant="muted"
              disabled={disabled}
              onClick={onUnconfirm}
            />
          )}
          {canAttachOwnLeg(settlement, mySeatId) && (
            <RowActionButton
              icon={Wallet}
              tooltip={t('settlements.actions.attachAccount')}
              ariaLabel="Attach account"
              variant="muted"
              disabled={disabled}
              onClick={onAttach}
            />
          )}
          {settlement.canDelete && (
            <RowActionButton
              icon={Trash2}
              tooltip={t('settlements.actions.remove')}
              ariaLabel="Delete"
              variant="destructive"
              disabled={disabled}
              onClick={onRemove}
            />
          )}
        </div>
      </TableCell>
    </TableRow>
  );
}
