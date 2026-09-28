import { expect, request as playwrightRequest } from '@playwright/test';

import { API_BASE, apiToken } from './api';
import { testMarker } from './factories';

/*
 * The group the text sweep needs to reach the shared pages: one group, one name-only seat, one
 * shared expense split between the two seats, and one empty pot — seeded through the API and deleted
 * again (deleting the group cascades to all of it). The text sweep asks whether copy fits, and a group
 * hub, its share wizard and a pot page render all their own copy for a group this small.
 *
 * The names are long on purpose: a Spanish seat name and a marker-long group and pot name, so the
 * places that show them (the hub header, the member list, the pot header) have something to cut, and
 * the expense carries a note longer than its column, so the hub's truncated notes cell is on screen.
 *
 * A killed run never reaches `cleanup`, so the seed first deletes every group whose name starts with
 * the marker prefix — a leftover from any earlier run.
 */

export const GROUP_MARKER_PREFIX = 'e2e-text-';

export interface GroupSeed {
  groupId: number;
  potId: number;
  cleanup: () => Promise<void>;
}

export async function seedGroup(): Promise<GroupSeed> {
  const token = await apiToken();
  const request = await playwrightRequest.newContext();
  const headers = { Authorization: `Bearer ${token}` };

  const listed = await request.get(`${API_BASE}/groups`, { headers });
  expect(listed.ok(), `GET /groups: ${listed.status()}`).toBe(true);
  for (const group of (await listed.json()) as { id: number; name: string }[]) {
    if (!group.name.startsWith(GROUP_MARKER_PREFIX)) continue;
    const deleted = await request.delete(`${API_BASE}/groups/${group.id}`, { headers });
    expect(deleted.ok(), `DELETE /groups/${group.id}: ${deleted.status()}`).toBe(true);
  }

  const marker = testMarker('text');
  const created = await request.post(`${API_BASE}/groups`, {
    headers,
    data: { name: `${marker} Casa de la familia`, kind: 'household' },
  });
  expect(created.ok(), `POST /groups: ${created.status()} ${await created.text()}`).toBe(true);
  const groupId: number = (await created.json()).id;

  async function cleanup() {
    const deleted = await request.delete(`${API_BASE}/groups/${groupId}`, { headers });
    if (!deleted.ok())
      console.warn(`e2e cleanup could not delete group ${groupId}: ${deleted.status()}`);
    await request.dispose();
  }

  try {
    const seat = await request.post(`${API_BASE}/groups/${groupId}/members`, {
      headers,
      data: { display_name: 'María Fernanda de los Santos Echeverría' },
    });
    expect(seat.ok(), `POST members: ${seat.status()} ${await seat.text()}`).toBe(true);
    const members = (await seat.json()).members as { id: number; is_self: boolean }[];
    const self = members.find((member) => member.is_self);
    expect(self, 'the harness account holds a seat in its own group').toBeDefined();

    const settings = await (await request.get(`${API_BASE}/settings`, { headers })).json();
    const currency: string = settings.primary_currency ?? 'ARS';
    const expense = await request.post(`${API_BASE}/groups/${groupId}/expenses`, {
      headers,
      data: {
        date: new Date().toISOString().slice(0, 10),
        amount: '84250.00',
        currency,
        notes: `${marker} Supermercado del mes y artículos de limpieza para la casa`,
        split_method: 'equal',
        splits: members.map((member) => ({ member_id: member.id })),
        payer_member_id: self!.id,
      },
    });
    expect(expense.ok(), `POST expenses: ${expense.status()} ${await expense.text()}`).toBe(true);
    const pot = await request.post(`${API_BASE}/pots`, {
      headers,
      data: {
        group_id: groupId,
        name: `${marker} Ahorros compartidos`,
        base_currency: currency,
      },
    });
    expect(pot.ok(), `POST /pots: ${pot.status()} ${await pot.text()}`).toBe(true);
    return { groupId, potId: (await pot.json()).id, cleanup };
  } catch (error) {
    await cleanup();
    throw error;
  }
}
