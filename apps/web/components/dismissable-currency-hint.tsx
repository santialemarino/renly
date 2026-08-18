import { getTranslations } from 'next-intl/server';

import { ConceptHint } from '@/components/concept-hint';
import { HELP_ANCHORS } from '@/config/routes';

const STORAGE_KEY = 'currency-hint-dismissed';

interface DismissableCurrencyHintProps {
  show: boolean;
}

// Explains that currency conversions use today's exchange rate, and links to the help section that
// covers the whole conversion model. Dismissable permanently, like every other concept hint.
export async function DismissableCurrencyHint({ show }: DismissableCurrencyHintProps) {
  const t = await getTranslations('common.currencyHint');

  return (
    <ConceptHint storageKey={STORAGE_KEY} anchor={HELP_ANCHORS.currency} show={show}>
      {t('message')}
    </ConceptHint>
  );
}
