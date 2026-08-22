'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { LogOut, Mail, Pencil, Plus, RotateCcw, UserMinus, UserPlus, Users, X } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

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
import { GroupInviteDialog } from '@/app/(protected)/shared/[groupId]/_components/group-invite-dialog';
import { GroupMemberFormDialog } from '@/app/(protected)/shared/[groupId]/_components/group-member-form-dialog';
import {
  canEditMember,
  canInviteMember,
  canReactivateMember,
  canRemoveMember,
  canRevokeInvite,
  memberStatus,
} from '@/app/(protected)/shared/[groupId]/member-permissions';
import {
  reactivateGroupMember,
  removeGroupMember,
  revokeGroupInvite,
} from '@/app/(protected)/shared/group-actions';
import { ConfirmDialog } from '@/components/confirm-dialog';
import { EmptyState } from '@/components/empty-state';
import { RowActionButton } from '@/components/row-action-button';
import { SectionHeader } from '@/components/section-header';
import type { Group, GroupMember } from '@/lib/api/groups';

interface GroupMembersSectionProps {
  group: Group;
}

/*
 * The roster: every seat in the group, active and former, placeholders included. It is the group's
 * source of truth for "who is in this" — a pending invite shows as a state ON the seat rather than in a
 * separate list, because an invite is not a person, it is one seat's outstanding link.
 *
 * Which controls render is decided by role, never what is READ: every member sees the identical roster.
 */
export function GroupMembersSection({ group }: GroupMembersSectionProps) {
  const t = useTranslations('shared');
  const router = useRouter();
  const [addOpen, setAddOpen] = useState(false);

  const isAdmin = group.myRole === 'admin';
  const active = group.members.filter((m) => m.isActive);
  const former = group.members.filter((m) => !m.isActive);

  const refresh = () => router.refresh();

  return (
    <div className="flex flex-col gap-y-4">
      <div className="flex flex-wrap items-end justify-between gap-x-3 gap-y-2">
        <SectionHeader title={t('members.title')} description={t('members.description')} />
        {isAdmin && (
          <Button blue onClick={() => setAddOpen(true)}>
            <Plus className="size-4" />
            {t('members.add')}
          </Button>
        )}
      </div>

      {active.length === 0 ? (
        <EmptyState
          icon={Users}
          title={t('members.emptyTitle')}
          description={t('members.emptyDescription')}
        />
      ) : (
        <RosterTable group={group} members={active} isAdmin={isAdmin} onSuccess={refresh} />
      )}

      {/* Former members are kept out of the main roster but never hidden: their seats still carry the
          group's history, and an admin can bring one back. Rendered only when there are any — the same
          table component, so the two can never drift apart. */}
      {former.length > 0 && (
        <div className="flex flex-col gap-y-2">
          <SectionHeader
            title={t('members.formerTitle')}
            description={t('members.formerDescription')}
          />
          <RosterTable group={group} members={former} isAdmin={isAdmin} onSuccess={refresh} />
        </div>
      )}

      <GroupMemberFormDialog
        open={addOpen}
        onOpenChange={setAddOpen}
        groupId={group.id}
        onSuccess={refresh}
      />
    </div>
  );
}

// One table for both rosters — active and former seats differ only in which rows they hold and which
// actions those rows offer, so the columns are defined once.
function RosterTable({
  group,
  members,
  isAdmin,
  onSuccess,
}: {
  group: Group;
  members: GroupMember[];
  isAdmin: boolean;
  onSuccess: () => void;
}) {
  const t = useTranslations('shared');

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>{t('members.table.name')}</TableHead>
          <TableHead className="w-28">{t('members.table.role')}</TableHead>
          <TableHead className="w-40">{t('members.table.status')}</TableHead>
          <TableHead className="w-32 text-center">{t('members.table.actions')}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {members.map((member) => (
          <MemberRow
            key={member.id}
            group={group}
            member={member}
            isAdmin={isAdmin}
            onSuccess={onSuccess}
          />
        ))}
      </TableBody>
    </Table>
  );
}

function MemberRow({
  group,
  member,
  isAdmin,
  onSuccess,
}: {
  group: Group;
  member: GroupMember;
  isAdmin: boolean;
  onSuccess: () => void;
}) {
  const t = useTranslations('shared');
  const [editOpen, setEditOpen] = useState(false);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [removeOpen, setRemoveOpen] = useState(false);
  const [pending, setPending] = useState(false);

  // Every one of these lives in member-permissions.ts, tested there: they are order-dependent rules
  // whose wrong answer is a plausible-looking label or a control that should not be here.
  const status = memberStatus(member);

  async function run(action: () => Promise<{ ok: boolean; conflictDetail?: string }>, ok: string) {
    setPending(true);
    try {
      const result = await action();
      if (!result.ok) {
        toast.error(result.conflictDetail ?? t('members.actionError'));
        return;
      }
      toast.success(ok);
      onSuccess();
    } catch {
      toast.error(t('members.actionError'));
    } finally {
      setPending(false);
    }
  }

  return (
    <>
      <TableRow>
        <TableCell className="text-paragraph-sm-medium">
          <span className="flex flex-wrap items-center gap-x-2">
            {member.displayName}
            {member.isSelf && (
              <span className="text-paragraph-xs text-muted-foreground">{t('members.you')}</span>
            )}
          </span>
        </TableCell>
        <TableCell>
          <Badge variant={member.role === 'admin' ? 'default' : 'secondary'}>
            {t(`roles.${member.role}`)}
          </Badge>
        </TableCell>
        <TableCell className="text-paragraph-sm text-muted-foreground">
          {t(`members.status.${status}`)}
        </TableCell>
        <TableCell className="text-center">
          <div className="flex items-center justify-center gap-x-1">
            {canInviteMember(member, isAdmin) && (
              <RowActionButton
                icon={member.hasPendingInvite ? Mail : UserPlus}
                tooltip={member.hasPendingInvite ? t('invite.resend') : t('invite.title')}
                ariaLabel="Invite"
                disabled={pending}
                onClick={() => setInviteOpen(true)}
              />
            )}
            {canRevokeInvite(member, isAdmin) && (
              <RowActionButton
                icon={X}
                tooltip={t('invite.revoke')}
                ariaLabel="Revoke invite"
                variant="muted"
                disabled={pending}
                onClick={() =>
                  run(() => revokeGroupInvite(group.id, member.id), t('invite.revokeSuccess'))
                }
              />
            )}
            {canEditMember(member, isAdmin) && (
              <RowActionButton
                icon={Pencil}
                tooltip={t('members.form.titleEdit')}
                ariaLabel="Edit"
                disabled={pending}
                onClick={() => setEditOpen(true)}
              />
            )}
            {canReactivateMember(member, isAdmin) && (
              <RowActionButton
                icon={RotateCcw}
                tooltip={t('members.reactivate')}
                ariaLabel="Reactivate"
                variant="muted"
                disabled={pending}
                onClick={() =>
                  run(
                    () => reactivateGroupMember(group.id, member.id),
                    t('members.reactivateSuccess'),
                  )
                }
              />
            )}
            {canRemoveMember(member, isAdmin) && (
              <RowActionButton
                icon={member.isSelf ? LogOut : UserMinus}
                tooltip={member.isSelf ? t('members.leave') : t('members.remove')}
                ariaLabel={member.isSelf ? 'Leave group' : 'Remove member'}
                variant="destructive"
                disabled={pending}
                onClick={() => setRemoveOpen(true)}
              />
            )}
          </div>
        </TableCell>
      </TableRow>

      <GroupMemberFormDialog
        open={editOpen}
        onOpenChange={setEditOpen}
        groupId={group.id}
        member={member}
        onSuccess={onSuccess}
      />
      <GroupInviteDialog
        open={inviteOpen}
        onOpenChange={setInviteOpen}
        groupId={group.id}
        member={member}
        onSuccess={onSuccess}
      />
      <ConfirmDialog
        open={removeOpen}
        onOpenChange={setRemoveOpen}
        entity={member}
        title={member.isSelf ? t('members.leaveTitle') : t('members.removeTitle')}
        description={(m) =>
          m.isSelf
            ? t('members.leaveDescription', { group: group.name })
            : t('members.removeDescription', { name: m.displayName })
        }
        onConfirm={async () => {
          await run(
            () => removeGroupMember(group.id, member.id),
            member.isSelf ? t('members.leaveSuccess') : t('members.removeSuccess'),
          );
          setRemoveOpen(false);
        }}
        loading={pending}
        loadingLabel={t('members.removing')}
        confirmLabel={member.isSelf ? t('members.leaveConfirm') : t('members.removeConfirm')}
        cancelLabel={t('form.cancel')}
      />
    </>
  );
}
