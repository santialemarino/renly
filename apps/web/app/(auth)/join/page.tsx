import { JoinCard } from '@/app/(auth)/join/_components/join-card';
import { getInvitePreview } from '@/lib/api/groups';
import { getSignupContext } from '@/lib/api/signup-context';
import { getSession } from '@/lib/auth';
import { generatePageMetadata } from '@/lib/utils/page-metadata';

export async function generateMetadata() {
  return await generatePageMetadata('join');
}

/*
 * Landing page for a group-invite link. Public on purpose — most recipients open it with no session,
 * and a protected route would bounce them to /login and lose the token from the URL. It deliberately
 * does NOT redirect a logged-in visitor either: accepting the invite is what they came here to do.
 *
 * The preview is read server-side with no auth: the token IS the credential, and it discloses only the
 * group's name and kind, the seat's label, and who sent it. A dead token renders the same "invalid or
 * expired" state as an unknown one, so nothing here can be probed.
 */
export default async function JoinGroupPage({
  searchParams,
}: {
  searchParams: Promise<{ token?: string }>;
}) {
  const { token } = await searchParams;
  const session = await getSession();
  const isLoggedIn = !!session?.user && !(session.user as { error?: string }).error;

  // Fetched together — the invite preview does not depend on the signup mode. The mode decides whether
  // a visitor with no account can be honestly offered a way to create one.
  const [preview, { mode }] = await Promise.all([
    token ? getInvitePreview(token) : Promise.resolve(null),
    getSignupContext(),
  ]);

  return (
    <JoinCard token={token ?? null} preview={preview} isLoggedIn={isLoggedIn} signupMode={mode} />
  );
}
