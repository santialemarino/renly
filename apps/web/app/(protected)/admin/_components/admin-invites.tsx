'use client';

import { useEffect, useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { Ban, Send } from 'lucide-react';
import { AnimatePresence, motion, useReducedMotion } from 'motion/react';
import { useLocale, useTranslations } from 'next-intl';
import { useForm } from 'react-hook-form';
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
import { inviteFormSchema, type InviteFormData } from '@/app/(protected)/admin/form-schema';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/form';
import type { Invite, InviteStatus } from '@/lib/api/invites';
import { ANIMATION_FAST } from '@/lib/constants/animations';
import { formatTimestampDate } from '@/lib/utils/format';

// Seconds before the same invite can be (re)sent again — matches the auth resend cooldown
// (CheckEmailNotice). Each send/resend starts it; a backstop on top of the server rate limit.
const RESEND_COOLDOWN_SECONDS = 30;

// Badge tone per status (all on the outline base so they read as quiet status chips, not actions).
const STATUS_CLASS: Record<InviteStatus, string> = {
  pending: 'border-blue-200 text-blue-800',
  accepted: 'bg-green-50 border-green-200 text-green-700',
  revoked: 'text-muted-foreground',
  expired: 'bg-amber-50 border-amber-200 text-amber-700',
};

interface AdminInvitesProps {
  initialInvites: Invite[];
}

export function AdminInvites({ initialInvites }: AdminInvitesProps) {
  const locale = useLocale();
  const t = useTranslations('admin');
  const tCommon = useTranslations('common');
  const reduceMotion = useReducedMotion();

  const form = useForm<InviteFormData>({
    defaultValues: { email: '' },
    mode: 'onSubmit',
    reValidateMode: 'onChange',
    resolver: zodResolver(inviteFormSchema(tCommon)),
  });

  const [invites, setInvites] = useState<Invite[]>(initialInvites);
  const [actingId, setActingId] = useState<number | null>(null);
  // Per-invite resend cooldown (invite id → seconds remaining).
  const [cooldowns, setCooldowns] = useState<Record<number, number>>({});

  // Transition honoring reduced motion (instant when the user prefers reduced motion).
  const transition = { duration: reduceMotion ? 0 : ANIMATION_FAST };

  // Tick every active cooldown down to zero, re-enabling its resend button.
  useEffect(() => {
    if (!Object.values(cooldowns).some((s) => s > 0)) return;
    const timer = setTimeout(() => {
      setCooldowns((prev) => {
        const next: Record<number, number> = {};
        Object.entries(prev).forEach(([id, seconds]) => {
          if (seconds > 1) next[Number(id)] = seconds - 1;
        });
        return next;
      });
    }, 1000);
    return () => clearTimeout(timer);
  }, [cooldowns]);

  // Starts the resend cooldown for an invite (after a send/resend went out).
  function startCooldown(id: number) {
    setCooldowns((prev) => ({ ...prev, [id]: RESEND_COOLDOWN_SECONDS }));
  }

  // Creates (or re-arms) an invite for the typed email. Email-specific failures (cooldown, an
  // address that already has an account) surface inline on the field; transient failures toast.
  const onSubmit = async ({ email }: InviteFormData) => {
    const value = email.trim();
    // Creating for an email that already has a row re-arms + re-sends it, so honor that row's cooldown.
    const existing = invites.find((i) => i.email.toLowerCase() === value.toLowerCase());
    const existingCooldown = existing ? (cooldowns[existing.id] ?? 0) : 0;
    if (existingCooldown > 0) {
      form.setError('email', { message: t('invite.cooldown', { seconds: existingCooldown }) });
      return;
    }
    try {
      const result = await createInvite(value);
      if (result.status === 'taken') {
        form.setError('email', { message: t('invite.taken') });
        return;
      }
      if (result.status === 'error') {
        toast.error(t('invite.error'));
        return;
      }
      // Re-arm replaces the existing row for that email; a fresh invite is prepended.
      setInvites((prev) => [result.invite, ...prev.filter((i) => i.id !== result.invite.id)]);
      startCooldown(result.invite.id);
      form.reset({ email: '' });
      toast.success(t('invite.success', { email: result.invite.email }));
    } catch {
      toast.error(t('invite.error'));
    }
  };

  async function handleResend(invite: Invite) {
    setActingId(invite.id);
    try {
      const updated = await resendInvite(invite.id);
      if (!updated) {
        toast.error(t('actions.resendError'));
        return;
      }
      setInvites((prev) => prev.map((i) => (i.id === updated.id ? updated : i)));
      startCooldown(updated.id);
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

  return (
    <div className="flex flex-col w-full max-w-3xl gap-y-6">
      <Form {...form}>
        {/* noValidate so the inline FormMessage is the only validation feedback (no native bubbles). */}
        <form noValidate onSubmit={form.handleSubmit(onSubmit)}>
          <FormField
            control={form.control}
            name="email"
            render={({ field }) => (
              <FormItem>
                <FormLabel>{t('invite.emailLabel')}</FormLabel>
                {/* Input + submit on one row, vertically centered against each other. */}
                <div className="flex items-center gap-x-2">
                  <FormControl>
                    <Input
                      {...field}
                      data-testid="admin-invite-email"
                      type="email"
                      autoComplete="off"
                      surface
                      containerClassName="flex-1"
                      placeholder={t('invite.emailPlaceholder')}
                    />
                  </FormControl>
                  <Button
                    blue
                    type="submit"
                    size="lg"
                    data-testid="admin-invite-submit"
                    disabled={form.formState.isSubmitting}
                  >
                    {form.formState.isSubmitting ? t('invite.sending') : t('invite.button')}
                  </Button>
                </div>
                <FormMessage />
              </FormItem>
            )}
          />
        </form>
      </Form>

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
            {invites.map((invite) => {
              const cooldown = cooldowns[invite.id] ?? 0;
              const showRevoke = invite.status !== 'accepted' && invite.status !== 'revoked';
              return (
                <TableRow key={invite.id}>
                  <TableCell className="text-paragraph-sm-medium">{invite.email}</TableCell>
                  <TableCell>
                    {/* Crossfade the badge when the status changes (revoke / resend-after-revoke). */}
                    <AnimatePresence mode="wait" initial={false}>
                      <motion.span
                        key={invite.status}
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        transition={transition}
                        className="inline-block"
                      >
                        <Badge variant="outline" className={STATUS_CLASS[invite.status]}>
                          {t(`status.${invite.status}`)}
                        </Badge>
                      </motion.span>
                    </AnimatePresence>
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {formatTimestampDate(invite.createdAt, locale)}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {invite.consumedAt
                      ? formatTimestampDate(invite.consumedAt, locale)
                      : t('table.never')}
                  </TableCell>
                  <TableCell>
                    {/* popLayout so the row's buttons grow/shrink smoothly as the Revoke action appears/disappears. */}
                    <div className="flex items-center justify-end gap-x-1">
                      <AnimatePresence mode="popLayout" initial={false}>
                        {invite.status !== 'accepted' && (
                          <motion.div
                            key="resend"
                            layout
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            exit={{ opacity: 0 }}
                            transition={transition}
                          >
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleResend(invite)}
                              disabled={actingId === invite.id || cooldown > 0}
                            >
                              <Send className="size-4" />
                              {cooldown > 0
                                ? t('actions.resendIn', { seconds: cooldown })
                                : t('actions.resend')}
                            </Button>
                          </motion.div>
                        )}
                        {showRevoke && (
                          <motion.div
                            key="revoke"
                            layout
                            initial={{ opacity: 0, scale: 0.8 }}
                            animate={{ opacity: 1, scale: 1 }}
                            exit={{ opacity: 0, scale: 0.8 }}
                            transition={transition}
                          >
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
                          </motion.div>
                        )}
                      </AnimatePresence>
                    </div>
                  </TableCell>
                </TableRow>
              );
            })}
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
