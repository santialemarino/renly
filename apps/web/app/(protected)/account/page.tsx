import { getTranslations } from 'next-intl/server';

import { Separator } from '@repo/ui/components';
import { PageHeader } from '@/app/(protected)/_components/page-header';
import { AccountDangerZone } from '@/app/(protected)/account/_components/account-danger-zone';
import { AccountLegalSection } from '@/app/(protected)/account/_components/account-legal-section';
import { ChangeEmailSection } from '@/app/(protected)/account/_components/change-email-section';
import { ChangeNameSection } from '@/app/(protected)/account/_components/change-name-section';
import { ChangePasswordSection } from '@/app/(protected)/account/_components/change-password-section';
import { getCurrentUser, getGroupsUsingAccountName } from '@/lib/api/me';
import { getSession } from '@/lib/auth';
import { generatePageMetadata } from '@/lib/utils/page-metadata';

export async function generateMetadata() {
  return await generatePageMetadata('account');
}

export default async function AccountPage() {
  const t = await getTranslations('account');
  // The name is read fresh from the API: the session holds the one from sign-in. The groups that would
  // follow a rename come with it; without them the rename is offered for the account alone.
  const [session, user, groupsUsingName] = await Promise.all([
    getSession(),
    getCurrentUser().catch(() => null),
    getGroupsUsingAccountName().catch(() => []),
  ]);
  const email = session?.user?.email ?? '';

  return (
    <div className="flex flex-col flex-1 items-start p-8 gap-y-4">
      <PageHeader title={t('title')} subtitle={t('subtitle')} />
      <div className="flex flex-col w-full max-w-2xl gap-y-8">
        {user && (
          <>
            <ChangeNameSection currentName={user.name} groupsUsingName={groupsUsingName} />
            <Separator />
          </>
        )}
        <ChangeEmailSection currentEmail={email} />
        <Separator />
        <ChangePasswordSection />
        <Separator />
        <AccountLegalSection />
        <Separator />
        <AccountDangerZone email={email} />
      </div>
    </div>
  );
}
