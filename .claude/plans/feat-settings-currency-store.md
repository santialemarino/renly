# feat — Settings page + global currency Zustand store

## Objective

Implement the Settings page (currency configuration) and global currency Zustand store with a currency switch in the sidebar. Users can select up to 3 display currencies from a full ISO 4217 list, reorder them, and set a default. The sidebar shows those currencies + "Original" as a switch that drives a Zustand store read by the rest of the app.

## Approach

Settings display currencies are a UI preference, not financial data — the backend settings schema changes `display_currencies`/`default_currency` from the strict `Currency` enum to plain strings. The frontend uses `currency-codes` (npm) for the full ISO 4217 picker and Zustand for the active currency state. The protected layout initializes the store server-side by fetching settings and passing them to a client-side initializer component.

## Implementation Steps

1. Backend: loosen settings schema (`str` instead of `Currency` for display/default fields)
2. Backend: update settings service defaults/merge to use plain strings
3. Install frontend deps: `zustand`, `currency-codes`, `@radix-ui/react-popover`, `cmdk`
4. Add `NEXT_PUBLIC_FALLBACK_CURRENCIES=ARS,USD` to `.env` and `.env.example`
5. Add shadcn `popover.tsx` and `command.tsx` to `apps/web/components/ui/`
6. Create `apps/web/lib/stores/currency-store.ts` (Zustand)
7. Create `apps/web/lib/api/settings.ts` (GET/PUT settings API client)
8. Create `apps/web/app/(protected)/_components/currency-store-initializer.tsx`
9. Update `apps/web/app/(protected)/layout.tsx` to fetch settings + render initializer
10. Build settings page: `settings/page.tsx` + `settings/_components/settings-form.tsx`
11. Update sidebar: add currency switch group between nav items and logout
12. Add translation keys (en + es)

## Affected Files

- `apps/api/app/schemas/settings.py` — `str` instead of `Currency`
- `apps/api/app/services/settings_service.py` — update defaults/merge
- `apps/web/package.json` — add deps
- `apps/web/.env` + `.env.example` — `NEXT_PUBLIC_FALLBACK_CURRENCIES`
- `apps/web/components/ui/popover.tsx` — new
- `apps/web/components/ui/command.tsx` — new
- `apps/web/lib/stores/currency-store.ts` — new
- `apps/web/lib/api/settings.ts` — new
- `apps/web/app/(protected)/layout.tsx` — fetch settings + initializer
- `apps/web/app/(protected)/_components/currency-store-initializer.tsx` — new
- `apps/web/app/(protected)/_components/sidebar.tsx` — currency switch group
- `apps/web/app/(protected)/settings/page.tsx` — real implementation
- `apps/web/app/(protected)/settings/_components/settings-form.tsx` — new
- `apps/web/translations/en.json` + `es.json` — add keys

## Risks & Edge Cases

- If settings fetch fails in layout, fall back to env var currencies (`NEXT_PUBLIC_FALLBACK_CURRENCIES`)
- Max 3 currencies enforced in UI only; backend does no count validation
- `"original"` is always appended to the sidebar switch — never stored in settings
- Backend currently validates against `Currency` enum — must change or it rejects new currency codes

## Acceptance Criteria

- [ ] Settings page loads with current settings pre-populated
- [ ] User can search and pick up to 3 currencies from the full ISO 4217 list
- [ ] User can reorder selected currencies; order is reflected in the sidebar switch
- [ ] Save persists to backend with success/error toast
- [ ] Sidebar shows configured currencies + Original as a switch group, between two separators
- [ ] Selecting a currency updates the Zustand store
- [ ] Fallback to env var currencies if no settings saved
- [ ] `pnpm check:web` passes
