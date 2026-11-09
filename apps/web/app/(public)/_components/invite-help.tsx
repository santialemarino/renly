import { getTranslations } from 'next-intl/server';

import {
  Button,
  Popover,
  PopoverContent,
  PopoverDescription,
  PopoverHeader,
  PopoverTitle,
  PopoverTrigger,
} from '@repo/ui/components';

interface InviteHelpProps {
  size: 'sm' | 'lg';
}

/*
 * "Have an invite?" for the landing page while signup is invite-only. There is nothing to sign up
 * through on the site itself in that mode — an account starts from the link in an invite email — so
 * rather than sending a visitor to a signup page that can only refuse them, this says where the way in
 * actually is.
 */
export async function InviteHelp({ size }: InviteHelpProps) {
  const t = await getTranslations('landing.invite');

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="outline" size={size} data-testid="landing-invite-help">
          {t('trigger')}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="center" className="w-80 p-4" data-testid="landing-invite-help-panel">
        <PopoverHeader className="gap-y-1">
          <PopoverTitle className="text-paragraph-sm-semibold">{t('title')}</PopoverTitle>
          <PopoverDescription className="text-paragraph-sm">{t('body')}</PopoverDescription>
        </PopoverHeader>
      </PopoverContent>
    </Popover>
  );
}
