/*
 * Every ✕ in the app — a control that closes, dismisses, clears or removes something — is one of four
 * KINDS, and each kind looks and behaves one way wherever it appears. The classes live here, once, so a
 * new ✕ picks a kind rather than restyling one; `apps/web/tests/unit/close-controls.test.ts` refuses a
 * lucide X rendered any other way. The ux-motion skill explains why the kinds differ.
 *
 * Every kind shares the icon-button focus language: `outline-none`, a SOLID blue ring for keyboard focus
 * (the same `ring-ring` every button draws) and the focus-bump on the icon, both through the shared
 * `group/close`. What differs is size, colour and hover — and, for a field's ✕, whose ring it is:
 *
 *   surface  closes a whole surface: a dialog, a sheet, a dismissable card. A 24px box in the corner,
 *            16px icon, muted → foreground with the ghost button's muted wash on hover. Ring + bump.
 *   inline   dismisses a one-line hint from inside it. A 24px box (pulled into the line so the hint
 *            keeps its height), 14px icon in the hint's own intent colour at half strength, full on
 *            hover or focus, and it grows on hover. Ring + bump.
 *   field    clears a field it sits in or over (a search box, a combobox). Looks like `inline` in the
 *            field's muted colour. Its ring is the FIELD's — the field draws it while the ✕ has focus,
 *            as it does for the password toggle — so focus never shows two nested rings. Bump only.
 *   chip     removes one selection from inside its 20px pill. A 16px circle, 12px icon, muted → danger
 *            and growing on hover (it removes something). A 2px ring, which stays inside the gap
 *            between chips where a 3px one would cover the next pill. Ring + bump.
 *
 * `data-close-kind` names the kind on the element, for the field's ring and for the e2e focus spec.
 */
export type CloseControlKind = 'surface' | 'inline' | 'field' | 'chip';

export const CLOSE_CONTROL: Record<CloseControlKind, { button: string; icon: string }> = {
  surface: {
    button:
      'group/close inline-flex size-6 shrink-0 items-center justify-center rounded-md text-muted-foreground cursor-pointer outline-none transition-colors duration-200 hover:bg-muted hover:text-foreground focus-visible:text-foreground focus-visible:ring-3 focus-visible:ring-ring disabled:pointer-events-none',
    icon: 'size-4 group-focus-visible/close:animate-focus-bump',
  },
  inline: {
    button:
      'group/close inline-flex size-6 -my-1 shrink-0 items-center justify-center rounded-md opacity-50 cursor-pointer outline-none transition-[opacity,transform] duration-150 hover:opacity-100 hover:scale-110 focus-visible:opacity-100 focus-visible:ring-3 focus-visible:ring-ring',
    icon: 'size-3.5 group-focus-visible/close:animate-focus-bump',
  },
  field: {
    button:
      'group/close inline-flex size-6 shrink-0 items-center justify-center rounded-md text-muted-foreground opacity-50 cursor-pointer outline-none transition-[opacity,transform] duration-150 hover:opacity-100 hover:scale-110 focus-visible:opacity-100',
    icon: 'size-3.5 group-focus-visible/close:animate-focus-bump',
  },
  chip: {
    button:
      'group/close inline-flex size-4 shrink-0 items-center justify-center rounded-full text-muted-foreground cursor-pointer outline-none transition-[color,transform] duration-150 hover:scale-110 hover:text-danger focus-visible:text-foreground focus-visible:ring-2 focus-visible:ring-ring',
    icon: 'size-3 group-focus-visible/close:animate-focus-bump',
  },
};

// The ring a field draws while the ✕ inside or over it has keyboard focus (the `field` kind's ring).
export const FIELD_CLEAR_RING =
  'has-[[data-close-kind=field]:focus-visible]:border-ring has-[[data-close-kind=field]:focus-visible]:ring-3 has-[[data-close-kind=field]:focus-visible]:ring-ring';
