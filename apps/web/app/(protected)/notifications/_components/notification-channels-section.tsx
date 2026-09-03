'use client';

import { useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

import { Switch } from '@repo/ui/components';
import { saveNotificationPreference } from '@/app/(protected)/notifications/actions';
import { SectionHeader } from '@/components/section-header';
import { InfoHint } from '@/components/styled-hint';
import type { NotificationPreferences } from '@/lib/api/notifications';
import {
  NOTIFICATION_CHANNELS,
  NOTIFICATION_EVENTS,
  type NotificationChannel,
  type NotificationEvent,
} from '@/lib/constants/notifications';

interface NotificationChannelsSectionProps {
  initialPreferences: NotificationPreferences;
}

/*
 * The events x channels grid: every event on every row, every channel a column, every cell a switch.
 *
 * The grid is BUILT from the two enums rather than from the response's row order, so a cell exists for
 * every combination the app knows about even if the API ever answers a partial set — and the response
 * is looked up into a map, which is also what makes a missing pair fall back to "off" rather than to
 * an undefined that renders as an uncontrolled switch.
 *
 * A save writes ONE cell and gets the WHOLE grid back, which the state is then replaced with — each
 * answer is the complete truth rather than a patch. That alone is not enough for two switches flipped
 * in quick succession, though: two saves in flight can ANSWER out of order, and the older answer would
 * then erase the newer one's cell. So only the latest save's answer is applied.
 */
export function NotificationChannelsSection({
  initialPreferences,
}: NotificationChannelsSectionProps) {
  const t = useTranslations('notifications');

  const [preferences, setPreferences] = useState(initialPreferences);
  const [saving, setSaving] = useState<string | null>(null);
  // Which save is the newest. A ref rather than state because nothing renders from it and a re-render
  // between taking a ticket and comparing it would defeat the point.
  const latestSave = useRef(0);

  // Typed as plain strings on purpose: inferred, the key would be the literal union of every
  // event.channel pair, and looking one up with a composed string would then be a type error rather
  // than a lookup.
  const byCell = new Map<string, boolean>(
    preferences.preferences.map((p) => [`${p.event}.${p.channel}`, p.enabled]),
  );

  async function handleToggle(
    event: NotificationEvent,
    channel: NotificationChannel,
    enabled: boolean,
  ) {
    const cell = `${event}.${channel}`;
    const ticket = (latestSave.current += 1);
    setSaving(cell);
    try {
      const result = await saveNotificationPreference(event, channel, enabled);
      if (!result.ok) {
        toast.error(result.conflictDetail, { id: 'notification-preference' });
        return;
      }
      // A superseded answer is dropped rather than applied: the save that overtook it will bring back
      // a grid that already includes this cell's change, so nothing is lost by ignoring this one.
      if (ticket === latestSave.current) setPreferences(result.data);
    } catch {
      toast.error(t('channels.error'), { id: 'notification-preference' });
    } finally {
      // Only the newest save owns the disabled state, or an older one finishing would re-enable the
      // switch the newer save is still writing.
      if (ticket === latestSave.current) setSaving(null);
    }
  }

  return (
    <section className="flex flex-col gap-y-4">
      <SectionHeader title={t('channels.title')} description={t('channels.description')} />

      <div className="overflow-x-auto">
        <table className="w-full min-w-md">
          <thead>
            <tr className="border-b border-border">
              <th
                scope="col"
                className="py-2 pr-4 text-left text-paragraph-xs-medium text-muted-foreground"
              >
                {t('channels.event')}
              </th>
              {NOTIFICATION_CHANNELS.map((channel) => (
                <th
                  key={channel}
                  scope="col"
                  className="w-20 py-2 text-center text-paragraph-xs-medium text-muted-foreground"
                >
                  {t(`channels.${channel}`)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {NOTIFICATION_EVENTS.map((event) => (
              <tr key={event} className="border-b border-border/60 last:border-b-0">
                <th scope="row" className="py-3 pr-4 text-left text-paragraph-sm font-normal">
                  {t(`events.${event}.label`)}
                </th>
                {NOTIFICATION_CHANNELS.map((channel) => {
                  const cell = `${event}.${channel}`;
                  const enabled = byCell.get(cell) ?? false;
                  return (
                    <td key={channel} className="py-3 text-center">
                      <Switch
                        blue
                        surface
                        checked={enabled}
                        disabled={saving === cell}
                        onCheckedChange={(next) => handleToggle(event, channel, next)}
                        aria-label={`${t(`events.${event}.label`)} — ${t(`channels.${channel}`)}`}
                      />
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Said once, under the grid, rather than on each of the ten push switches. */}
      {!preferences.pushAvailable && <InfoHint>{t('channels.pushUnavailableHint')}</InfoHint>}
    </section>
  );
}
