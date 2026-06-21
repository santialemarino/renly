---
name: ux-motion
description: UX/UI conventions for the Renly frontend — interaction states (focus-visible, hover, active, disabled), motion/animation (motion/react + the animation constants), layout-shift avoidance, rounding/tokens, reduced motion, and the app-vs-public surface split. Use when creating or restyling any component or page in apps/web or packages/ui.
---

# UX & motion conventions (Renly frontend)

Applies to every component/page in `apps/web` and `packages/ui`. Load alongside `web-components-pages` (where files go) and `web-structure`.

## Two surfaces — know which you're building

- **App** — the authenticated product + its auth flows: `app/(auth)/` (login, signup, forgot/reset/verify) and `app/(protected)/` (dashboard, investments, settings, …). Motion is **calm and functional**: feedback and orientation, never spectacle. It's a tool people use daily.
- **Public** — the marketing surface reachable without logging in: the `app/(public)/` route group (landing, privacy, terms, disclaimer). Motion is **expressive and vibrant** (scroll-reveal, hover-float, ambient), built on the same base below.

The **Base conventions** apply to BOTH. **App motion** and **Public motion** layer on top — pick by surface.

## Reuse first

Reuse `@repo/ui` (button, card, badge, input, textarea, checkbox, switch, select, popover, tooltip, dialog, sheet, toggle/toggle-group, separator, skeleton, pill, hint, table, command, calendar) and existing app components before building new — restyle through existing CVA variants, don't fork. A genuinely new shared component goes in `packages/ui/src/components` + its `index.ts` (see `web-components-pages`).

## Base conventions (all surfaces)

### Interaction states — every interactive element gets all that apply

- **focus-visible — never leave the browser default.** Always `outline-none`, then replace with the Renly treatment:
  - **Surfaces** (buttons, inputs, focusable cards/controls): the ring, exactly like `packages/ui/src/components/button.tsx` — `outline-none focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:border-ring`. Variant-tinted rings use `focus-visible:ring-<color>/50` (destructive `ring-red-500/50`, blue `ring-blue-800/50`).
  - **Icon-only / inline triggers**: the focus-bump family via a focusable group — `group/<name>` on the focusable element + `group-focus-visible/<name>:animate-<x>` on the icon. Utilities (in `packages/ui/src/styles/index.css`): `animate-focus-bump` (scale 1.5, icon buttons), `animate-focus-bump-soft` (1.15, inline), `animate-focus-bump-subtle` (1.05, text links), `animate-pulse-scale` (0.95 press-in, toggle/segmented). Reference: the table sort headers.
  - Keyboard focus MUST be as visible as hover. Audit every element you add — no missing ring, no leftover native outline.
- **hover** — pair EVERY hover with a matching focus-visible (keyboard parity). `transition-colors` for color, `transition-all duration-200` for scale, `transition-[border-color,box-shadow]` for inputs. Don't signal interactivity with color alone (add scale/shape/underline).
- **active / pressed** — give pressed feedback where it reads: `active:bg-<token>` (buttons already do this) or `active:scale-95` / `animate-pulse-scale` for toggles.
- **disabled** — `disabled:opacity-50 disabled:pointer-events-none` (button base); non-disabled buttons / `[role=button]` get `cursor-pointer` (base rule in `index.css`).

### Motion stack & timing

- Library: **`motion/react`** (`import { motion, AnimatePresence, LayoutGroup } from 'motion/react'`) — not framer-motion.
- Durations from `apps/web/lib/constants/animations.ts`: `ANIMATION_FAST` 0.15 / `ANIMATION_DEFAULT` 0.25 / `ANIMATION_SLOW` 0.5. **Never hardcode a duration** — add a shared constant if you need a new one.

### No layout shift (hard rule)

- Micro-interactions animate **transform + opacity only**.
- Reflowing siblings → `motion`'s `layout` prop + `AnimatePresence mode="popLayout"` (+ a negative margin to absorb the gap). Height reveal → `height: 0 ↔ 'auto'` + `overflow: hidden` + `initial={false}` (so it doesn't animate on mount).
- Toggling an icon between states → stack both in one grid cell (`col-start-1 row-start-1`) and crossfade with `scale-0/opacity-0` (password eye, sort icons) — never reflow.
- Reserve space for conditional content; use fixed icon sizes (`size-4`).

### Open / close — both directions

- Reuse the `@repo/ui` primitives' built-in open/close: dialog/popover/tooltip/sheet use `data-[state=open]:animate-in / data-[state=closed]:animate-out` + `fade` / `zoom-95` / directional `slide-in-from-*` (sheets are asymmetric: 500ms open / 300ms close). Collapsible → `animate-collapsible-down/up`. Don't reinvent these.
- Crossfade loading/empty/content via `AnimatePresence mode="wait"` + a ~500ms min-loading delay (credit-cards settlements pattern).
- Never conditionally unmount in a way that kills the exit — use `AnimatePresence` exits so **close looks as good as open**.

### Rounding & tokens

- **Never sharp / fully square.** `--radius` 0.625rem + the scale (`packages/ui/src/styles/theme.css`): buttons/inputs `rounded-lg`, cards `rounded-1.5xl` (or `rounded-xl` compact), badges `rounded-full` (square variant only when intentional).
- Use the oklch design tokens (`--ring`, `--destructive`, `--accent`, `--ghost`, `border-0..5`, …) — never raw hex. Variants via CVA (Button/Badge): extend variants, don't fork the component.

### Reduced motion (mandatory)

Honor `prefers-reduced-motion: reduce`. Non-essential motion (scroll reveals, floats, parallax, large scale/translate, ambient loops) collapses to instant / opacity-only. Use `@media (prefers-reduced-motion: reduce)` in CSS and `useReducedMotion()` (motion/react) for JS-driven motion. Functional feedback (focus ring, small hover) may stay.

## App motion (`(auth)` + `(protected)`)

Calm and functional: state feedback (focus/hover/active), the primitives' open/close, conditional-field reveals, loading crossfades. **No scroll-reveal, no ambient/decorative motion** — keep it quiet.

## Public motion (`(public)`)

Expressive but standards-based, on the same tokens/rounding/stack:

- **Scroll-reveal:** `whileInView` + `viewport={{ once: true, margin: '-10% 0px' }}` (reveal once, never replay on scroll-up). opacity + small `translateY` (~16–24px). Stagger groups (~0.06–0.1s). Content must be SSR'd and readable without JS — reveals are progressive enhancement, never a gate.
- **Hover micro-interactions:** card lift (`translateY(-6…-8px)`) + shadow, transform/opacity only, ~150–250ms; pair with focus-visible.
- **Ambient / float:** subtle hero accents only; always gated by reduced-motion.
- **Performance:** transform/opacity only (60fps); avoid animating width/height/blur; `will-change` sparingly.

## Verify (playwright-cli, per `e2e-testing`)

Keyboard focus-visible on every interactive element; hover; open AND close; (public) scroll reveals firing once; and the reduced-motion fallback (emulate reduce).
