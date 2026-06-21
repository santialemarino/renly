'use client';

import { useState } from 'react';
import { Ban, Send } from 'lucide-react';
import { useLocale, useTranslations } from 'next-intl';
import { toast } from 'sonner';

import {
  Badge,
  Button,
  Input,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@repo/ui/components';
import { createInvite, resendInvite, revokeInvite } from '@/app/(protected)/admin/admin-actions';
import type { Invite, InviteStatus } from '@/lib/api/invites';
import { getLocaleTag } from '@/lib/utils/locale';

// Badge tone per status (all on the outline base so they read as quiet status chips, not actions).
const STATUS_CLASS: Record<InviteStatus, string> = {
  pending: 'text-blue-800 border-blue-200',
  accepted: 'bg-green-50 text-green-700 border-green-200',
  revoked: 'text-muted-foreground',
  expired: 'bg-amber-50 text-amber-700 border-amber-200',
};

interface AdminInvitesProps {
  initialInvites: Invite[];
}

export function AdminInvites({ initialInvites }: AdminInvitesProps) {
  const locale = useLocale();
  const t = useTranslations('admin');

  const [invites, setInvites] = useState<Invite[]>(initialInvites);
  const [email, setEmail] = useState('');
  const [creating, setCreating] = useState(false);
  const [actingId, setActingId] = useState<number | null>(null);

  async function handleCreate() {
    const value = email.trim();
    if (!value || creating) return;
    setCreating(true);
    try {
      const result = await createInvite(value);
      if (result.status === 'taken') {
        toast.error(t('invite.taken'));
        return;
      }
      if (result.status === 'error') {
        toast.error(t('invite.error'));
        return;
      }
      // Re-arm replaces the existing row for that email; a fresh invite is prepended.
      setInvites((prev) => [result.invite, ...prev.filter((i) => i.id !== result.invite.id)]);
      setEmail('');
      toast.success(t('invite.success', { email: result.invite.email }));
    } catch {
      toast.error(t('invite.error'));
    } finally {
      setCreating(false);
    }
  }

  async function handleResend(invite: Invite) {
    setActingId(invite.id);
    try {
      const updated = await resendInvite(invite.id);
      if (!updated) {
        toast.error(t('actions.resendError'));
        return;
      }
      setInvites((prev) => prev.map((i) => (i.id === updated.id ? updated : i)));
      toast.success(t('actions.resendSuccess', { email: updated.email }));
    } catch {
      toast.error(t('actions.resendError'));
    } finally {
      setActingId(null);
    }
  }

  async function handleRevoke(invite: Invite) {
    setActingId(invite.id);
    try {
      const updated = await revokeInvite(invite.id);
      if (!updated) {
        toast.error(t('actions.revokeError'));
        return;
      }
      setInvites((prev) => prev.map((i) => (i.id === updated.id ? updated : i)));
      toast.success(t('actions.revokeSuccess', { email: updated.email }));
    } catch {
      toast.error(t('actions.revokeError'));
    } finally {
      setActingId(null);
    }
  }

  // Formats a timestamp as a short date string.
  function formatDate(iso: string): string {
    return new Date(iso).toLocaleDateString(getLocaleTag(locale), {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  }

  return (
    <div className="flex flex-col w-full max-w-3xl gap-y-6">
      <form
        className="flex items-end gap-x-2"
        onSubmit={(e) => {
          e.preventDefault();
          void handleCreate();
        }}
      >
        <div className="flex flex-col flex-1 gap-y-1.5">
          <label className="text-paragraph-sm-medium text-foreground" htmlFor="admin-invite-email">
            {t('invite.emailLabel')}
          </label>
          <Input
            id="admin-invite-email"
            data-testid="admin-invite-email"
            type="email"
            autoComplete="off"
            surface
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder={t('invite.emailPlaceholder')}
          />
        </div>
        <Button
          blue
          type="submit"
          data-testid="admin-invite-submit"
          disabled={creating || !email.trim()}
        >
          {creating ? t('invite.sending') : t('invite.button')}
        </Button>
      </form>

      {invites.length > 0 ? (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t('table.email')}</TableHead>
              <TableHead>{t('table.status')}</TableHead>
              <TableHead>{t('table.sent')}</TableHead>
              <TableHead>{t('table.accepted')}</TableHead>
              <TableHead className="text-right">{t('table.actions')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {invites.map((invite) => (
              <TableRow key={invite.id}>
                <TableCell className="text-paragraph-sm-medium">{invite.email}</TableCell>
                <TableCell>
                  <Badge variant="outline" className={STATUS_CLASS[invite.status]}>
                    {t(`status.${invite.status}`)}
                  </Badge>
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {formatDate(invite.createdAt)}
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {invite.consumedAt ? formatDate(invite.consumedAt) : t('table.never')}
                </TableCell>
                <TableCell>
                  <div className="flex items-center justify-end gap-x-1">
                    {invite.status !== 'accepted' && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleResend(invite)}
                        disabled={actingId === invite.id}
                      >
                        <Send className="size-4" />
                        {t('actions.resend')}
                      </Button>
                    )}
                    {invite.status !== 'accepted' && invite.status !== 'revoked' && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleRevoke(invite)}
                        disabled={actingId === invite.id}
                        className="text-muted-foreground hover:text-destructive"
                      >
                        <Ban className="size-4" />
                        {t('actions.revoke')}
                      </Button>
                    )}
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      ) : (
        <div className="flex items-center justify-center p-6 border border-dashed rounded-lg">
          <p className="text-paragraph-sm text-muted-foreground">{t('table.empty')}</p>
        </div>
      )}
    </div>
  );
}
