'use client';

import { useState, useTransition } from 'react';
import { useRouter } from 'next/navigation';
import { Users } from 'lucide-react';
import { motion } from 'motion/react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

import { Button, Card, CardContent, CardFooter, CardHeader, CardTitle } from '@repo/ui/components';
import { acceptGroupInvite } from '@/app/(auth)/join/join-actions';
import { InlineLink } from '@/components/inline-link';
import { StyledHint } from '@/components/styled-hint';
import { ROUTES, sharedGroupPath } from '@/config/routes';
import type { GroupInvitePreview } from '@/lib/api/groups';
import type { SignupMode } from '@/lib/auth-api';
import { ANIMATION_DEFAULT } from '@/lib/constants/animations';
import { useFormatters } from '@/lib/i18n/formatters';

const FADE_PROPS = {
  initial: { opacity: 0 },
  animate: { opacity: 1 },
  transition: { duration: ANIMATION_DEFAULT },
};

interface JoinCardProps {
  token: string | null;
  // Null for a token that is missing, unknown, already used or expired — one state for all of them, so
  // a holder cannot tell which and the remedy ("ask for a new link") is the same either way.
  preview: GroupInvitePreview | null;
  isLoggedIn: boolean;
  signupMode: SignupMode;
}

export function JoinCard({ token, preview, isLoggedIn, signupMode }: JoinCardProps) {
  const fmt = useFormatters();
  const t = useTranslations('join');
  const tCommon = useTranslations('common');
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [failure, setFailure] = useState<string | null>(null);

  // Carries the invite through login and back, so a logged-out recipient does not have to dig the
  // email out again. Signup deliberately does NOT carry it: email verification sits in the middle, so
  // no single redirect survives it, and promising one would be a lie.
  const loginHref = token
    ? `${ROUTES.auth.login}?next=${encodeURIComponent(`${ROUTES.auth.joinGroup}?token=${token}`)}`
    : ROUTES.auth.login;

  function handleAccept() {
    if (!token) return;
    startTransition(async () => {
      try {
        const result = await acceptGroupInvite(token);
        if (!result.ok) {
          setFailure(result.reason);
          return;
        }
        toast.success(t('success', { group: result.groupName }));
        router.push(sharedGroupPath(result.groupId));
      } catch {
        setFailure(t('error'));
      }
    });
  }

  return (
    <motion.div className="w-full max-w-auth-form" {...FADE_PROPS}>
      <Card>
        <CardHeader className="flex flex-col items-center gap-y-3">
          <span className="grid size-12 shrink-0 place-items-center bg-muted rounded-full text-muted-foreground">
            <Users className="size-6" />
          </span>
          <CardTitle className="text-heading-4 text-center text-blue-800">
            {preview ? t('title', { group: preview.groupName }) : t('invalidTitle')}
          </CardTitle>
        </CardHeader>

        <CardContent className="flex flex-col gap-y-4">
          {preview ? (
            <>
              {/* The group's kind is a LABEL, not part of the sentence. Interpolating it into prose
                  forced a determiner that cannot agree with every value: Spanish "en esta {kind}" is
                  correct for casa and pareja and wrong for viaje and grupo, and English "in this
                  {kind}" reads badly for a trip. As its own line it needs no grammar in any language. */}
              <p className="text-paragraph-xs text-center text-muted-foreground">
                {t('kindLabel')} · {tCommon(`groupKinds.${preview.groupKind}`)}
              </p>
              <p className="text-paragraph-sm text-center text-muted-foreground">
                {preview.invitedByName
                  ? t('description', {
                      inviter: preview.invitedByName,
                      seat: preview.memberDisplayName,
                    })
                  : t('descriptionNoInviter', { seat: preview.memberDisplayName })}
              </p>
              <p className="text-paragraph-xs text-center text-muted-foreground">
                {t('expires', { date: fmt.timestampDate(preview.expiresAt) })}
              </p>

              {failure && <StyledHint variant="error">{failure}</StyledHint>}

              {isLoggedIn ? (
                <Button blue size="lg" onClick={handleAccept} disabled={isPending}>
                  {isPending ? t('cta.loading') : t('cta.label')}
                </Button>
              ) : (
                <div className="flex flex-col gap-y-3">
                  <StyledHint variant="info">
                    {signupMode === 'invite' ? t('needAccountInviteOnly') : t('needAccount')}
                  </StyledHint>
                  <Button blue size="lg" asChild>
                    <a href={loginHref}>{t('cta.login')}</a>
                  </Button>
                </div>
              )}
            </>
          ) : (
            <p className="text-paragraph-sm text-center text-muted-foreground">
              {t('invalidDescription')}
            </p>
          )}
        </CardContent>

        <CardFooter className="justify-center gap-x-1 px-6 text-paragraph-sm text-muted-foreground">
          <InlineLink href={isLoggedIn ? ROUTES.home : ROUTES.landing}>
            {isLoggedIn ? t('goToDashboard') : t('goToHome')}
          </InlineLink>
        </CardFooter>
      </Card>
    </motion.div>
  );
}
