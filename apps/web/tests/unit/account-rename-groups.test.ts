import { createTranslator } from 'next-intl';
import { describe, expect, it } from 'vitest';

import { offersGroupRename, renameGroupSeatsOnSave } from '@/app/(protected)/account/rename-groups';
import en from '../../translations/en.json';
import es from '../../translations/es.json';

/*
 * Renaming the account into the user's groups, from the account page: when the option shows, what a
 * save asks for, and the copy around it in both languages. The section itself renders a Radix checkbox,
 * which the jsdom suite cannot mount, so its behaviour in the browser is in
 * tests/e2e/account-name.auth.spec.ts.
 */

describe('when the groups option shows', () => {
  it('shows only for a different, non-empty name while some group still uses the current one', () => {
    expect(offersGroupRename('Santiago', 'Santi', 2)).toBe(true);
    expect(offersGroupRename('Santiago', 'Santi', 0)).toBe(false);
    expect(offersGroupRename('Santi', 'Santi', 2)).toBe(false);
    expect(offersGroupRename('', 'Santi', 2)).toBe(false);
  });

  it('trims as the API does, so spaces around the same name are no change', () => {
    expect(offersGroupRename('  Santi ', 'Santi', 2)).toBe(false);
    expect(offersGroupRename('   ', 'Santi', 2)).toBe(false);
  });

  it('treats another casing as a different name', () => {
    expect(offersGroupRename('santi', 'Santi', 1)).toBe(true);
  });
});

describe('what a save asks for', () => {
  it('asks for the groups only when the box is ticked and on screen', () => {
    expect(renameGroupSeatsOnSave(true, true)).toBe(true);
    expect(renameGroupSeatsOnSave(false, true)).toBe(false);
    expect(renameGroupSeatsOnSave(undefined, true)).toBe(false);
    // Ticked, then hidden by typing the name back: nothing to rename.
    expect(renameGroupSeatsOnSave(true, false)).toBe(false);
  });
});

describe('the copy', () => {
  const t = {
    en: createTranslator({ locale: 'en', messages: en, namespace: 'account.name' }),
    es: createTranslator({ locale: 'es', messages: es, namespace: 'account.name' }),
  };

  it('pluralises the checkbox label', () => {
    expect(t.en('groups.label', { count: 1 })).toBe('Also use this name in my group (1)');
    expect(t.en('groups.label', { count: 3 })).toBe('Also use this name in my groups (3)');
    expect(t.es('groups.label', { count: 1 })).toBe('Usar este nombre también en mi grupo (1)');
    expect(t.es('groups.label', { count: 3 })).toBe('Usar este nombre también en mis grupos (3)');
  });

  it('names the current name and the groups that would change', () => {
    expect(t.en('groups.helper', { name: 'Santi' })).toBe(
      "Only groups where you're still called Santi. Names a group chose for you stay as they are.",
    );
    expect(t.es('groups.helper', { name: 'Santi' })).toBe(
      'Solo en los grupos donde todavía te llamás Santi. Los nombres que un grupo eligió para vos se mantienen.',
    );
    expect(t.en('groups.which', { count: 1, groups: 'Trip' })).toBe('Group: Trip');
    expect(t.en('groups.which', { count: 2, groups: 'Flat and Trip' })).toBe(
      'Groups: Flat and Trip',
    );
    expect(t.es('groups.which', { count: 1, groups: 'Viaje' })).toBe('Grupo: Viaje');
    expect(t.es('groups.which', { count: 2, groups: 'Depto y Viaje' })).toBe(
      'Grupos: Depto y Viaje',
    );
  });

  it('says how many groups the save reached, none included', () => {
    expect(t.en('successWithGroups', { count: 1 })).toBe(
      'Your name has been updated, here and in 1 group.',
    );
    expect(t.en('successWithGroups', { count: 2 })).toBe(
      'Your name has been updated, here and in 2 groups.',
    );
    expect(t.en('successWithGroups', { count: 0 })).toBe(
      'Your name has been updated. None of your groups still used the old one, so they kept theirs.',
    );
    expect(t.es('successWithGroups', { count: 1 })).toBe(
      'Tu nombre se actualizó, acá y en 1 grupo.',
    );
    expect(t.es('successWithGroups', { count: 2 })).toBe(
      'Tu nombre se actualizó, acá y en 2 grupos.',
    );
    expect(t.es('successWithGroups', { count: 0 })).toBe(
      'Tu nombre se actualizó. Ninguno de tus grupos usaba todavía el anterior, así que mantuvieron el suyo.',
    );
  });
});
