'use client';

import { useState } from 'react';
import { ExternalLink, Smartphone } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

import {
  Button,
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
  Hint,
  Input,
  Label,
  Separator,
} from '@repo/ui/components';
import { saveShortcutCurrencies } from '@/app/(protected)/integrations/integrations-actions';
import { ComboboxChevron } from '@/components/combobox-chevron';
import { InlineLink } from '@/components/inline-link';
import { InfoHint } from '@/components/styled-hint';

// iCloud share link for the iOS Shortcut.
const ICLOUD_LINK: string | null =
  'https://www.icloud.com/shortcuts/8df8f795056349efaa407c0e29af30e7';

interface IntegrationsShortcutProps {
  initialCurrencies: string[] | null;
  defaultCurrencies: string | null;
}

export function IntegrationsShortcut({
  initialCurrencies,
  defaultCurrencies,
}: IntegrationsShortcutProps) {
  const t = useTranslations('integrations');

  const [currencyInput, setCurrencyInput] = useState(initialCurrencies?.join(', ') ?? '');
  const [saving, setSaving] = useState(false);
  const [instructionsOpen, setInstructionsOpen] = useState(false);

  async function handleSave() {
    setSaving(true);
    try {
      const parsed = currencyInput
        .split(',')
        .map((s) => s.trim().toUpperCase())
        .filter(Boolean);
      await saveShortcutCurrencies(parsed.length > 0 ? parsed : null);
      // Normalize the input after save.
      setCurrencyInput(parsed.join(', '));
      toast.success(t('shortcut.saveSuccess'));
    } catch {
      toast.error(t('shortcut.saveError'));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex flex-col w-full max-w-2xl gap-y-4">
      <div className="flex flex-col gap-y-1">
        <div className="flex items-center gap-x-2">
          <Smartphone className="size-4 text-muted-foreground" />
          <h3 className="text-paragraph-sm-semibold text-muted-foreground">
            {t('shortcut.title')}
          </h3>
        </div>
        <p className="text-paragraph-xs text-muted-foreground">{t('shortcut.description')}</p>
      </div>

      {/* iCloud download link */}
      {ICLOUD_LINK ? (
        <InlineLink href={ICLOUD_LINK} external icon={ExternalLink} className="self-start">
          {t('shortcut.downloadLink')}
        </InlineLink>
      ) : (
        <div className="flex items-center p-3 gap-x-3 border border-dashed rounded-lg">
          <Smartphone className="size-4 shrink-0 text-muted-foreground" />
          <p className="text-paragraph-xs text-muted-foreground">{t('shortcut.downloadPending')}</p>
        </div>
      )}

      <Separator />

      {/* Shortcut currencies configuration */}
      <div className="flex flex-col gap-y-2">
        <Label>{t('shortcut.currencies.label')}</Label>
        <Hint>{t('shortcut.currencies.hint')}</Hint>
        <div className="flex items-center gap-x-2">
          <Input
            value={currencyInput}
            onChange={(e) => setCurrencyInput(e.target.value.toUpperCase())}
            placeholder={defaultCurrencies || t('shortcut.currencies.placeholder')}
            surface
          />
          <Button variant="outline" size="sm" onClick={handleSave} disabled={saving}>
            {saving ? t('shortcut.currencies.saving') : t('shortcut.currencies.save')}
          </Button>
        </div>
        <InfoHint>
          {defaultCurrencies
            ? t('shortcut.currencies.formatWithDefaults', { defaults: defaultCurrencies })
            : t('shortcut.currencies.format')}
        </InfoHint>
      </div>

      <Separator />

      {/* Installation instructions */}
      <Collapsible open={instructionsOpen} onOpenChange={setInstructionsOpen}>
        <CollapsibleTrigger className="group/button flex items-center gap-x-2 transition-colors hover:text-foreground focus-visible:text-foreground focus-visible:outline-none text-paragraph-sm-medium text-muted-foreground">
          <ComboboxChevron
            open={instructionsOpen}
            className="group-focus-visible/button:text-foreground"
          />
          {t('shortcut.instructions.title')}
        </CollapsibleTrigger>
        <CollapsibleContent className="overflow-hidden data-[state=open]:animate-collapsible-down data-[state=closed]:animate-collapsible-up">
          <ol className="flex flex-col mt-3 pl-5 gap-y-2 list-decimal text-paragraph-xs text-muted-foreground">
            <li>{t('shortcut.instructions.step1')}</li>
            <li>{t('shortcut.instructions.step2')}</li>
            <li>{t('shortcut.instructions.step3')}</li>
            <li>{t('shortcut.instructions.step4')}</li>
          </ol>
        </CollapsibleContent>
      </Collapsible>
    </div>
  );
}
