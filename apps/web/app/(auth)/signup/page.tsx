import { redirect } from 'next/navigation';

import { InviteOnlyNotice } from '@/app/(auth)/signup/_components/invite-only-notice';
import { SignupCard } from '@/app/(auth)/signup/_components/signup-card';
import { ROUTES } from '@/config/routes';
import { getSignupContext } from '@/lib/api/signup-context';
import { getSession } from '@/lib/auth';
import { generatePageMetadata } from '@/lib/utils/page-metadata';

export async function generateMetadata() {
  return await generatePageMetadata('signup');
}

export default async function SignupPage({
  searchParams,
}: {
  searchParams: Promise<{ invite?: string }>;
}) {
  const session = await getSession();
  if (session?.user && !session.user.error) {
    redirect(ROUTES.home);
  }

  const { invite } = await searchParams;
  const { mode, invitedEmail } = await getSignupContext(invite);

  // Invite-only mode without a valid invite link shows an invite-only notice — never an open
  // registration form. This is what keeps the M2 anti-enumeration property: with no form, an
  // uninvited visitor can't even submit an email to probe. The form appears only via a valid invite
  // link (email locked to the invited address), or unconditionally in open mode.
  if (mode === 'invite' && !invitedEmail) {
    return <InviteOnlyNotice />;
  }

  return (
    <SignupCard lockedEmail={invitedEmail} inviteToken={invitedEmail ? (invite ?? null) : null} />
  );
}
