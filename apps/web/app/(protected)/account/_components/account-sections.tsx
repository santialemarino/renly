import { Separator } from '@repo/ui/components';
import { AccountDangerZone } from '@/app/(protected)/account/_components/account-danger-zone';
import { AccountLegalSection } from '@/app/(protected)/account/_components/account-legal-section';
import { ChangeEmailSection } from '@/app/(protected)/account/_components/change-email-section';
import { ChangePasswordSection } from '@/app/(protected)/account/_components/change-password-section';

interface AccountSectionsProps {
  email: string;
}

// The account page's sections under its header — rendered by the page, and as its placeholder by
// its loading state.
export function AccountSections({ email }: AccountSectionsProps) {
  return (
    <div className="flex flex-col w-full max-w-2xl gap-y-8">
      <ChangeEmailSection currentEmail={email} />
      <Separator />
      <ChangePasswordSection />
      <Separator />
      <AccountLegalSection />
      <Separator />
      <AccountDangerZone email={email} />
    </div>
  );
}
