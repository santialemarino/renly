import { PageSkeleton } from '@/app/(protected)/_components/page-skeleton';
import { AccountSections } from '@/app/(protected)/account/_components/account-sections';
import { getSession } from '@/lib/auth';

export default async function AccountLoading() {
  // The layout has already read the session for this request, so this costs nothing.
  const session = await getSession();

  return (
    <PageSkeleton
      namespace="account"
      body="page"
      content={<AccountSections email={session?.user?.email ?? ''} />}
    />
  );
}
