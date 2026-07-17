import { notFound } from 'next/navigation';
import { getTranslations } from 'next-intl/server';

import { PageHeader } from '@/app/(protected)/_components/page-header';
import { AdminInvites } from '@/app/(protected)/admin/_components/admin-invites';
import { getInvites } from '@/lib/api/invites';
import { getSignupContext } from '@/lib/api/signup-context';
import { AdminForbiddenError } from '@/lib/api/types';
import { generatePageMetadata } from '@/lib/utils/page-metadata';

export async function generateMetadata() {
  return await generatePageMetadata('admin');
}

export default async function AdminPage() {
  const t = await getTranslations('admin');

  // Invites only matter in invite-only mode — in open mode anyone can sign up, so the page is gone
  // for everyone (real 404, matching the hidden sidebar item).
  const { mode } = await getSignupContext();
  if (mode !== 'invite') notFound();

  // The API gates invite reads on is_admin (403 for non-admins). A logged-in non-admin who reaches
  // this route gets a real 404 — hiding the page's existence — rather than a 403; logged-out users
  // were already redirected to /login by the route gate. Other errors surface normally.
  const invites = await getInvites().catch((error) => {
    if (error instanceof AdminForbiddenError) return null;
    throw error;
  });
  if (invites === null) notFound();

  return (
    <div className="flex flex-col flex-1 items-start p-8 gap-y-4">
      <PageHeader title={t('title')} subtitle={t('subtitle')} />
      <AdminInvites initialInvites={invites} />
    </div>
  );
}
