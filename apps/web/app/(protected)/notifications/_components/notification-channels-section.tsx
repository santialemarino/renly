'use client';

import { useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

import { Label, Switch } from '@repo/ui/components';
import {
  saveNotificationEmailCadence,
  saveNotificationPreference,
} from '@/app/(protected)/notifications/actions';
import type { SharedDataResult } from '@/app/(protected)/shared/mutation-result';
import { SectionHeader } from '@/components/section-header';
import { InfoHint } from '@/components/styled-hint';
import type { NotificationPreferences } from '@/lib/api/notifications';
import {
  NOTIFICATION_CHANNELS,
  NOTIFICATION_EVENTS,
  type NotificationChannel,
  type NotificationEvent,
} from '@/lib/constants/notifications';

// The cadence switch's key in the same in-flight-save slot the grid's cells use. A literal rather than
// an `event.channel` pair because it is neither: it is one answer for the whole email column.
const CADENCE_CELL = 'email.cadence';

// Ties the switch to its own label, which is the only thing that makes the label clickable and the
// control announced by name — the grid's cells carry an aria-label instead because they have no
// visible label of their own.
const DIGEST_SWITCH_ID = 'notification-email-digest';

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
 *
 * The email CADENCE switch under the grid shares that ticket, which is the point of it living here
 * rather than in a section of its own: it writes to a different endpoint but gets the same grid back,
 * so a cadence save and a cell save racing each other is exactly the out-of-order case above.
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
    await save(`${event}.${channel}`, () => saveNotificationPreference(event, channel, enabled));
  }

  async function handleCadenceToggle(daily: boolean) {
    await save(CADENCE_CELL, () => saveNotificationEmailCadence(daily ? 'daily' : 'immediate'));
  }

  /*
   * One write, whatever switch made it. Extracted because the cadence control writes to a different
   * endpoint and returns the same grid, so it needs the identical staleness rule — and two copies of
   * that rule is two places the "drop a superseded answer" branch can be got wrong.
   */
  async function save(
    cell: string,
    write: () => Promise<SharedDataResult<NotificationPreferences>>,
  ) {
    const ticket = (latestSave.current += 1);
    setSaving(cell);
    try {
      const result = await write();
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
              <tr
                key={event}
                data-testid={`notification-event-${event}`}
                className="border-b border-border/60 last:border-b-0"
              >
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

      {/* The one control that is about WHEN rather than WHETHER, so it sits under the grid rather than
          inside it — a per-person answer beneath a per-event one. A Switch because there are two
          values; when a third (weekly) exists it becomes a segmented control and this comment is the
          reminder that the API already stores a string rather than a boolean. */}
      <div className="flex w-full items-start justify-between gap-x-6">
        <div className="flex flex-col gap-y-1">
          <Label htmlFor={DIGEST_SWITCH_ID} className="text-paragraph-sm-medium">
            {t('channels.digestLabel')}
          </Label>
          <span className="text-paragraph-xs text-muted-foreground">
            {t('channels.digestDescription')}
          </span>
        </div>
        <Switch
          blue
          surface
          id={DIGEST_SWITCH_ID}
          data-testid="notification-digest-switch"
          checked={preferences.emailCadence === 'daily'}
          disabled={saving === CADENCE_CELL}
          onCheckedChange={handleCadenceToggle}
        />
      </div>

      {/* Said once, under the grid, rather than on every push switch in the column. */}
      {!preferences.pushAvailable && <InfoHint>{t('channels.pushUnavailableHint')}</InfoHint>}
    </section>
  );
}
