import { redirect } from 'next/navigation';

import { LoginCard } from '@/app/(auth)/login/_components/login-card';
import { ROUTES } from '@/config/routes';
import { getSession } from '@/lib/auth';
import { generatePageMetadata } from '@/lib/utils/page-metadata';
import { safeNextPath } from '@/lib/utils/safe-next-path';

export async function generateMetadata() {
  return await generatePageMetadata('login');
}

/*
 * `?next=` exists for one flow: a group-invite link opened without a session sends the recipient here
 * and needs them back on the invite afterwards, token intact. It is run through safeNextPath, which
 * allowlists it against the app's own routes — so it cannot be turned into an off-site redirect — and
 * an already-logged-in visitor is sent there too rather than to the dashboard, which is what makes
 * clicking the link twice work.
 */
export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string }>;
}) {
  const [session, { next }] = await Promise.all([getSession(), searchParams]);
  const nextPath = safeNextPath(next);

  if (session?.user && !session.user.error) {
    redirect(nextPath ?? ROUTES.home);
  }

  return <LoginCard nextPath={nextPath} />;
}
