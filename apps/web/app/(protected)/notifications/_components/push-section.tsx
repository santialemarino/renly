'use client';

import { useEffect, useState } from 'react';
import { BellOff, BellRing } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

import { Button } from '@repo/ui/components';
import { subscribeToPush, unsubscribeFromPush } from '@/app/(protected)/notifications/actions';
import { SectionHeader } from '@/components/section-header';
import { InfoHint } from '@/components/styled-hint';
import type { NotificationPreferences } from '@/lib/api/notifications';
import {
  currentPushEndpoint,
  disablePush,
  enablePush,
  isPushSupported,
  PushPermissionDeniedError,
} from '@/lib/push';

interface PushSectionProps {
  initialPreferences: NotificationPreferences;
}

/*
 * Turning web push on or off FOR THIS BROWSER.
 *
 * Per browser, not per account, and the copy says so: the Push API mints a subscription against one
 * browser profile on one device, so a laptop and a phone are two separate decisions. Which is also why
 * this section reads the browser's own state on mount rather than trusting the account-level count —
 * "you have two browsers subscribed" says nothing about whether THIS one is among them.
 *
 * Three states are honestly distinct and all three are shown rather than collapsed into "off":
 * the browser cannot do push at all, the deployment has no key so nothing could ever be sent, and the
 * person has blocked notifications for this site (which no button can undo — only the browser's own
 * site settings can).
 */
export function PushSection({ initialPreferences }: PushSectionProps) {
  const t = useTranslations('notifications');

  const [preferences, setPreferences] = useState(initialPreferences);
  const [endpoint, setEndpoint] = useState<string | null>(null);
  const [supported, setSupported] = useState<boolean | null>(null);
  const [denied, setDenied] = useState(false);
  const [busy, setBusy] = useState(false);

  // Read on mount rather than during render: both answers come from browser APIs that do not exist on
  // the server, and `supported === null` is "not asked yet" rather than "no" — the distinction is what
  // stops the unsupported message flashing on every load.
  useEffect(() => {
    let active = true;
    setSupported(isPushSupported());
    if (!isPushSupported()) return;
    setDenied(Notification.permission === 'denied');
    void currentPushEndpoint().then((value) => {
      if (active) setEndpoint(value);
    });
    return () => {
      active = false;
    };
  }, []);

  async function handleEnable() {
    if (!preferences.pushPublicKey) return;
    setBusy(true);
    try {
      const subscription = await enablePush(preferences.pushPublicKey);
      const result = await subscribeToPush(
        subscription.endpoint,
        subscription.p256dh,
        subscription.auth,
        navigator.userAgent,
      );
      if (!result.ok) {
        toast.error(result.conflictDetail, { id: 'push' });
        return;
      }
      setPreferences(result.data);
      setEndpoint(subscription.endpoint);
      setDenied(false);
    } catch (error) {
      if (error instanceof PushPermissionDeniedError) {
        setDenied(true);
        return;
      }
      toast.error(t('push.error'), { id: 'push' });
    } finally {
      setBusy(false);
    }
  }

  async function handleDisable() {
    if (!endpoint) return;
    setBusy(true);
    try {
      // The browser's own subscription goes first. If the server call then fails the row is stale but
      // harmless — the endpoint is gone, so the push service answers 410 on the next send and the
      // sender deletes it. The other order would leave a browser still holding a live subscription for
      // an account that believes it turned it off.
      await disablePush();
      const result = await unsubscribeFromPush(endpoint);
      if (!result.ok) {
        toast.error(result.conflictDetail, { id: 'push' });
        return;
      }
      setPreferences(result.data);
      setEndpoint(null);
    } catch {
      toast.error(t('push.errorOff'), { id: 'push' });
    } finally {
      setBusy(false);
    }
  }

  /*
   * "On for this browser" needs BOTH halves to be true, and the account's count is the half that is
   * easy to forget. A browser can hold a live subscription this account does not own: a browser holds
   * exactly one, so a second account signing in here and turning push on takes it over — which is a
   * shared computer, the thing a shared-money app invites. Reading the browser alone would then leave
   * this page claiming push is on while every send goes to somebody else.
   *
   * Zero is the case this settles exactly: no rows means none of them is this browser's. With rows on
   * OTHER browsers the count cannot tell which, so the honest recovery stays the button — turning it on
   * re-claims this browser, and turning it off is idempotent either way.
   */
  const subscribedHere = endpoint !== null && preferences.pushSubscriptions > 0;
  const others = preferences.pushSubscriptions - (subscribedHere ? 1 : 0);

  return (
    <section className="flex flex-col items-start gap-y-4">
      <SectionHeader title={t('push.title')} description={t('push.description')} />

      {supported === false ? (
        <InfoHint>{t('push.unsupported')}</InfoHint>
      ) : !preferences.pushAvailable ? (
        <InfoHint>{t('push.unavailable')}</InfoHint>
      ) : (
        <>
          <div className="flex flex-col gap-y-1">
            <span className="text-paragraph-sm">
              {subscribedHere ? t('push.on') : t('push.off')}
            </span>
            {others > 0 && (
              <span className="text-paragraph-xs text-muted-foreground">
                {t('push.devicesOther', { count: others })}
              </span>
            )}
          </div>

          {subscribedHere ? (
            <Button variant="outline" onClick={handleDisable} disabled={busy}>
              <BellOff />
              {busy ? t('push.disabling') : t('push.disable')}
            </Button>
          ) : (
            <Button blue onClick={handleEnable} disabled={busy || supported === null}>
              <BellRing />
              {busy ? t('push.enabling') : t('push.enable')}
            </Button>
          )}

          {denied && <InfoHint>{t('push.denied')}</InfoHint>}
          <InfoHint>{t('push.privacy')}</InfoHint>
        </>
      )}
    </section>
  );
}
