'use client';

import { useEffect, useMemo, useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useTranslations } from 'next-intl';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';

import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Input,
  Label,
} from '@repo/ui/components';
import { createGroupInvite } from '@/app/(protected)/shared/group-actions';
import {
  buildGroupInviteFormSchema,
  type GroupInviteFormValues,
} from '@/app/(protected)/shared/group-form-schema';
import { CopyButton } from '@/components/copy-button';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/form';
import { StyledHint } from '@/components/styled-hint';
import type { GroupMember } from '@/lib/api/groups';
import { useFormatters } from '@/lib/i18n/formatters';

interface GroupInviteDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  groupId: number;
  member: GroupMember;
  onSuccess: () => void;
}

/*
 * Invites someone to one seat, or rotates an existing invite (a resend — which kills the previous
 * link). Two things shape this dialog and are worth stating:
 *
 *   * the email is OPTIONAL. Leaving it blank produces a link-only invite: nothing is sent and the
 *     admin shares the URL themselves, which is the shareable-link half of the feature.
 *   * the link is shown ONCE, here. Nothing stores the raw token — only its hash — so a lost link
 *     cannot be re-read, it is replaced by inviting again. Hence the copy affordance and the explicit
 *     warning rather than a quiet success toast.
 */
export function GroupInviteDialog({
  open,
  onOpenChange,
  groupId,
  member,
  onSuccess,
}: GroupInviteDialogProps) {
  const fmt = useFormatters();
  const t = useTranslations('shared');
  const tCommon = useTranslations('common');

  const schema = useMemo(
    () => buildGroupInviteFormSchema(tCommon('form.errors.invalidEmail')),
    [tCommon],
  );

  const form = useForm<GroupInviteFormValues>({
    resolver: zodResolver(schema),
    defaultValues: { email: '' },
  });
  const [issued, setIssued] = useState<{ url: string; email: string | null; expiresAt: string }>();

  /*
   * Reset on OPEN rather than on close: the link has to survive the close animation (nulling it
   * mid-exit blanks the dialog body), and clearing it on the next open is what stops a previously
   * issued link from reappearing for a different seat.
   */
  useEffect(() => {
    if (open) {
      form.reset({ email: '' });
      setIssued(undefined);
    }
  }, [open, form]);

  async function onSubmit(values: GroupInviteFormValues) {
    try {
      const result = await createGroupInvite(groupId, member.id, values);
      if (!result.ok) {
        toast.error(result.conflictDetail);
        return;
      }
      setIssued({ url: result.inviteUrl, email: result.email, expiresAt: result.expiresAt });
      // Refresh behind the dialog so the seat's status flips to "invited" while the link is still on
      // screen — the dialog stays open because the link cannot be recovered once it closes.
      onSuccess();
    } catch {
      toast.error(t('invite.error'));
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {member.hasPendingInvite ? t('invite.resendTitle') : t('invite.title')}
          </DialogTitle>
        </DialogHeader>
        <DialogDescription>
          {member.hasPendingInvite
            ? t('invite.resendDescription', { name: member.displayName })
            : t('invite.description', { name: member.displayName })}
        </DialogDescription>

        {issued ? (
          <div className="flex flex-col gap-y-3">
            <div className="flex flex-col gap-y-2">
              {/* The base Label, not FormLabel: this branch renders OUTSIDE the <Form> provider (the
                  form is gone once the link exists), and FormLabel reads useFormContext(), which is
                  null there. */}
              <Label>{t('invite.linkLabel')}</Label>
              <div className="flex items-center gap-x-2">
                <Input readOnly value={issued.url} className="min-w-0 flex-1" />
                <CopyButton value={issued.url} ariaLabel="Copy invite link" />
              </div>
            </div>
            <StyledHint variant="warning">
              {t('invite.shownOnce', { date: fmt.timestampDate(issued.expiresAt) })}
            </StyledHint>
            {issued.email && <StyledHint>{t('invite.sentTo', { email: issued.email })}</StyledHint>}
          </div>
        ) : (
          <Form {...form}>
            <form
              id="group-invite-form"
              className="flex flex-col min-w-0 gap-y-4"
              onSubmit={form.handleSubmit(onSubmit)}
              noValidate
            >
              <FormField
                control={form.control}
                name="email"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t('invite.email.label')}</FormLabel>
                    <FormControl>
                      <Input {...field} type="email" placeholder={t('invite.email.placeholder')} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <StyledHint>{t('invite.emailHint')}</StyledHint>
            </form>
          </Form>
        )}

        <DialogFooter>
          {issued ? (
            <Button blue onClick={() => onOpenChange(false)}>
              {t('invite.done')}
            </Button>
          ) : (
            <>
              <Button variant="outline" onClick={() => onOpenChange(false)}>
                {t('form.cancel')}
              </Button>
              <Button
                blue
                type="submit"
                form="group-invite-form"
                disabled={form.formState.isSubmitting}
              >
                {form.formState.isSubmitting ? t('invite.cta.loading') : t('invite.cta.label')}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
