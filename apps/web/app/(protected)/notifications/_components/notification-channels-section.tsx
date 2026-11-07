'use client';

import { useState } from 'react';
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
import {
  autosaveErrorMessage,
  AutosaveRefusal,
  useAutosaveToggles,
} from '@/lib/hooks/use-autosave-toggles';

// The cadence switch's key beside the grid's `event.channel` cells. A literal rather than a pair
// because it is neither: it is one answer for the whole email column.
const CADENCE_CELL = 'email.cadence';

// Ties the switch to its own label, which is the only thing that makes the label clickable and the
// control announced by name — the grid's cells carry an aria-label instead because they have no
// visible label of their own.
const DIGEST_SWITCH_ID = 'notification-email-digest';

interface NotificationChannelsSectionProps {
  initialPreferences: NotificationPreferences;
}

// One cell's state in the server's answer: off when the answer leaves the pair out.
function cellEnabled(preferences: NotificationPreferences, cell: string): boolean {
  return preferences.preferences.some((p) => `${p.event}.${p.channel}` === cell && p.enabled);
}

/*
 * The events x channels grid: every event on every row, every channel a column, every cell a switch.
 *
 * The grid is BUILT from the two enums rather than from the response's row order, so a cell exists for
 * every combination the app knows about even if the API ever answers a partial set — and a missing pair
 * reads as "off" rather than as an undefined that renders an uncontrolled switch.
 *
 * Every switch here saves on its own, through `useAutosaveToggles`: it flips the instant it is clicked
 * and stays live, a burst of clicks writes once, and a failed write puts that switch back and toasts.
 * A save writes ONE cell and gets the whole grid back, but only that cell is taken from the answer: two
 * cells' writes can answer in either order, and taking the whole grid from an older answer would put
 * the other cell back where it was.
 *
 * The email CADENCE switch under the grid saves the same way through its own endpoint; it is a
 * per-person answer where the cells are per (event, channel), and it lives here because it shares the
 * grid's confirmed state.
 */
export function NotificationChannelsSection({
  initialPreferences,
}: NotificationChannelsSectionProps) {
  const t = useTranslations('notifications');

  const [preferences, setPreferences] = useState(initialPreferences);
  const toggles = useAutosaveToggles<boolean>({
    confirmed: (cell) =>
      cell === CADENCE_CELL ? preferences.emailCadence === 'daily' : cellEnabled(preferences, cell),
    write: (cell, enabled) =>
      cell === CADENCE_CELL
        ? save(cell, () => saveNotificationEmailCadence(enabled ? 'daily' : 'immediate'))
        : save(cell, () => {
            const [event, channel] = cell.split('.') as [NotificationEvent, NotificationChannel];
            return saveNotificationPreference(event, channel, enabled);
          }),
    onError: (_, error) =>
      toast.error(autosaveErrorMessage(error, t('channels.error')), {
        id: 'notification-preference',
      }),
  });

  /*
   * One write, whatever switch made it, and only its own part of the answer is kept: the cell's state,
   * or the cadence. A refusal is thrown so the hook rolls the switch back.
   */
  async function save(
    cell: string,
    write: () => Promise<SharedDataResult<NotificationPreferences>>,
  ) {
    const result = await write();
    if (!result.ok) throw new AutosaveRefusal(result.conflictDetail);
    const answer = result.data;
    setPreferences((current) =>
      cell === CADENCE_CELL
        ? { ...current, emailCadence: answer.emailCadence }
        : {
            ...current,
            preferences: [
              ...current.preferences.filter((p) => `${p.event}.${p.channel}` !== cell),
              ...answer.preferences.filter((p) => `${p.event}.${p.channel}` === cell),
            ],
          },
    );
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
                  return (
                    <td key={channel} className="py-3 text-center">
                      <Switch
                        blue
                        surface
                        checked={toggles.value(cell)}
                        onCheckedChange={(next) => toggles.set(cell, next)}
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
          checked={toggles.value(CADENCE_CELL)}
          onCheckedChange={(next) => toggles.set(CADENCE_CELL, next)}
        />
      </div>

      {/* Said once, under the grid, rather than on every push switch in the column. */}
      {!preferences.pushAvailable && <InfoHint>{t('channels.pushUnavailableHint')}</InfoHint>}
    </section>
  );
}
