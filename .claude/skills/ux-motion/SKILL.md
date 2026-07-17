---
name: ux-motion
description: UX/UI conventions for the Renly frontend — interaction states (focus-visible, hover, active, disabled), motion/animation (motion/react + the animation constants), layout-shift avoidance, reduced motion, and the app-vs-public surface split. Use when creating or restyling any component or page in apps/web or packages/ui.
---

# UX & motion conventions (Renly frontend)

Applies to every component/page in `apps/web` and `packages/ui`. Load alongside `web-components-pages` (where files go) and `web-structure`.

## Two surfaces — know which you're building

- **App** — the authenticated product + its auth flows: `app/(auth)/` (login, signup, forgot/reset/verify) and `app/(protected)/` (dashboard, investments, settings, …). Motion is **calm and functional**: feedback and orientation, never spectacle. It's a tool people use daily.
- **Public** — the marketing surface reachable without logging in: the `app/(public)/` route group (landing, privacy, terms, disclaimer). Motion is **expressive and vibrant** (on-load entrance, scroll-reveal, hover-float, ambient), built on the same base below.

The **Base conventions** apply to BOTH. **App motion** and **Public motion** layer on top — pick by surface.

## Base conventions (all surfaces)

### Interaction states — every interactive element gets all that apply

- **focus-visible — never leave the browser default.** Always `outline-none`, then replace with the Renly treatment:
  - **Surfaces** (buttons, inputs, focusable cards/controls): the ring, exactly like `packages/ui/src/components/button.tsx` — `outline-none focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:border-ring`. Variant-tinted rings use `focus-visible:ring-<color>/50` (destructive `ring-red-500/50`, blue `ring-blue-800/50`).
  - **Icon-only / inline triggers**: the focus-bump family via a focusable group — `group/<name>` on the focusable element + `group-focus-visible/<name>:animate-<x>` on the icon. Utilities (in `packages/ui/src/styles/index.css`): `animate-focus-bump` (scale 1.5, icon buttons), `animate-focus-bump-soft` (1.15, inline), `animate-focus-bump-subtle` (1.05, text links), `animate-pulse-scale` (0.95 press-in, toggle/segmented). Reference: the table sort headers.
  - Keyboard focus MUST be as visible as hover. Audit every element you add — no missing ring, no leftover native outline.
- **inline text links & actions** — text rendered as a link OR an inline action (auth links, footer/legal links, a wordmark-as-home link, an in-page action such as replaying a tour), not a full button: use the shared inline-link component, `InlineLink` (`apps/web/components/inline-link.tsx`) — never build a new one. Pass `href` for navigation or `onClick` for an action (it renders a `<Link>` or a `<button>` with identical styling), plus `color`/`size`/`className` and an optional leading `icon` (rotates on hover, like the nav items). It MUST: animate the underline on hover (`underline decoration-transparent underline-offset-2 … hover:decoration-<color>` + `transition-colors`) — put the hover on the underlined text itself (self-`hover:`), NOT a named-group `group-hover/…` variant on that same element (it compiles to a descendant selector that never matches the element hovering itself); give a focus-visible cue **distinct from hover** (`focus-visible:animate-focus-bump-subtle`); and drop the native outline (`outline-none`). Never a bare `<a>`/`<button>` with ad-hoc classes.
- **in-page anchor navigation** (a table of contents, a "jump to" list) — scroll **smoothly** to the target, never a hard jump. Render the links as plain `<a href="#id">` (NOT a Next `<Link>`, which intercepts the click and fights the scroll) and put the shared `useSmoothScrollToHash()` hook (`apps/web/lib/hooks/`) as a delegated `onClick` on the links' container: it calls `scrollIntoView({ behavior: 'smooth', block: 'start' })`, honors reduced motion (an explicit `'instant'` jump), updates the URL hash via `replaceState`, and moves focus to the target so keyboard/screen-reader users continue from the section, not the link. Give each scroll target a `scroll-mt-*` so it lands clear of the sticky header. Reuse the hook — never hand-roll `scrollIntoView` / a global `scroll-behavior: smooth` (the latter also animates Next's scroll-to-top on every route change) per page.
- **hover** — pair EVERY hover with a matching focus-visible (keyboard parity). `transition-colors` for color, `transition-all duration-200` for scale, `transition-[border-color,box-shadow]` for inputs. Don't signal interactivity with color alone (add scale/shape/underline). An icon inside an interactive element animates on the element's hover via `group-hover` — e.g. a small rotate, like the sidebar nav items — paired with the focus-bump (`group-focus-visible/<name>:animate-…`).
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

- Reuse the `@repo/ui` primitives' built-in open/close: dialog/popover/tooltip/sheet use `data-[state=open]:animate-in / data-[state=closed]:animate-out` + `fade` / `zoom-95` / directional `slide-in-from-*` (sheets are asymmetric: 500ms open / 300ms close). Collapsible → `animate-collapsible-down/up`. Don't reinvent these. These primitives defer unmount via Radix `Presence`, so the closing animation genuinely plays.
- **`Select` is the exception — it animates open but NOT closed.** Its dropdown (`SelectContent`, the popup holding the options) fades/zooms in on open but is removed **instantly** on close, so the `data-[state=closed]:animate-out fade-out-0 zoom-out-95` classes shadcn ships on it never get a frame to run — every select in the app snaps shut. Verified: on close the content element is gone within a frame, whereas dialog/popover/tooltip/sheet keep their content mounted in `data-[state=closed]` for the animation and then unmount — that deferral is what lets THEM animate out, and Radix `Select` doesn't do it. This is a shared-primitive behavior, identical for every `Select` call site, **not** a per-call-site bug: don't add wrappers, `AnimatePresence`, or a forked select to "fix" one dropdown. If a closing animation is ever actually wanted, change the one shared `@repo/ui` `Select` (a deliberate, app-wide call — it's a third-party shadcn component, so treat it like any other shared-component change). The trigger's chevron rotating on open (`data-[state=open]:…rotate-180`) IS animated and unaffected. For any new dropdown/overlay, verify the close actually plays rather than assuming the `data-[state=closed]` classes imply it.
- Crossfade loading/empty/content via `AnimatePresence mode="wait"` + a ~500ms min-loading delay (credit-cards settlements pattern).
- Never conditionally unmount in a way that kills the exit — use `AnimatePresence` exits so **close looks as good as open**.
- **Dialogs — keep the content mounted through the exit.** Toggle only the dialog's `open`; pass its row/detail data as a **stable prop** rather than nulling it on close (nulling blanks the body, so the dialog visibly shrinks then vanishes instead of a clean fade + zoom-out). Reset any derived state _after_ the animation (a timeout), never mid-exit. The base `@repo/ui` `Dialog`'s close ✕ already carries the icon-button focus treatment — `outline-none` + a muted→foreground `transition-colors` hover/focus-visible + `animate-focus-bump` on the icon, **no rectangular `:focus` ring** — so use it, don't re-style the ✕ per dialog.
- A control's **open/closed state icon** (a select / combobox / disclosure chevron) rotates on open. Drive it off the open state (a prop, or `group-data-[state=open]`) and animate with **`transition-transform`** — in Tailwind v4 `rotate-*` sets the `rotate` property, so a `transform`-only transition does NOT animate it (the chevron snaps). Put the rotating chevron in one **shared component** so every dropdown's affordance (icon, size, rotation) is identical — don't re-implement it per call site.

### Reduced motion (mandatory)

Honor `prefers-reduced-motion: reduce`. Non-essential motion (scroll reveals, floats, parallax, large scale/translate, ambient loops) collapses to instant / opacity-only. Use `@media (prefers-reduced-motion: reduce)` in CSS and `useReducedMotion()` (motion/react) for JS-driven motion. Functional feedback (focus ring, small hover) may stay.

## App motion (`(auth)` + `(protected)`)

Calm and functional: state feedback (focus/hover/active), the primitives' open/close, conditional-field reveals, loading crossfades, and at most a quiet on-mount fade (the auth cards). **No scroll-reveal, no ambient/decorative motion** — keep it quiet.

- **State transitions between distinct steps** (e.g. an upload → review wizard, or any swap between mutually-exclusive panels) crossfade with `AnimatePresence mode="wait"` + opacity — don't snap from one state to the next.
- **A control's changing label/count animates, including its size.** When a button (or similar) label changes — e.g. a count updating — crossfade the text with a keyed `AnimatePresence`, and animate the control's **resize both ways** (grow and shrink) with the `layout` prop. Wrap a base component to make it animatable (`motion.create(Button)`); the bare CSS `transition-all` does not animate content-driven `width: auto` changes.

## Public motion (`(public)`)

Expressive but standards-based, on the same tokens/rounding/stack. The public surface deliberately animates **more** than the app — that contrast is intended, not a violation of the calm-app rule.

- **Animate on load AND on scroll.** The first view animates in on mount (hero fade + small rise); every section below reveals as it scrolls into view. (The app does neither — this is the public differentiation.)
- **Scroll-reveal:** `whileInView` + `viewport={{ once: true, margin: '-10% 0px' }}` (reveal once, never replay on scroll-up). opacity + small `translateY` (~16–24px). Stagger groups (~0.06–0.1s). Content must be SSR'd and readable without JS — reveals are progressive enhancement, never a gate.
- **Hover micro-interactions:** card lift (`translateY(-6…-8px)`) + shadow, transform/opacity only, ~150–250ms; pair with focus-visible.
- **Hover-lift without flicker (gotcha + fix):** when an element lifts on hover, the element that OWNS the hover must NOT move — otherwise the pointer falls outside the moved element at the boundary and it oscillates hover→un-hover→hover forever. Keep the hover/layout box stationary and lift an **inner** layer, or drive the lift from a stationary wrapper that owns the `:hover`/`whileHover`. Motion must be smooth in BOTH directions (same easing + duration in and out).
- **Ambient / float:** subtle hero accents only; always gated by reduced-motion.
- **Footer:** differentiate it from the page body — a subtle surface tint and/or a top border via the shared `Separator` (don't hand-roll `border-t`), optionally a soft shadow on the divider. Footer/legal links use the inline-link component above.
- **Sticky / translucent header — overscroll bleed:** a sticky, semi-transparent header shows a seam at the very top when the page overscroll-bounces. Back the overscroll area with the header's color (extend the header background upward, or paint a fixed top layer in the header color) so no line shows — without disabling overscroll/overflow.
- **Performance:** transform/opacity only (60fps); avoid animating width/height/blur; `will-change` sparingly.

## Verify (playwright-cli, per `e2e-testing`)

Keyboard focus-visible on every interactive element; hover; open AND close; (public) on-load entrance + scroll reveals firing once; hover-lift smooth both ways with no boundary flicker; and the reduced-motion fallback (emulate reduce).
