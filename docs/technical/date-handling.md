# Date handling

## Snapshots and dates

Each investment snapshot has an exact date (YYYY-MM-DD). The evolution chart normalizes snapshots to monthly points using forward-fill: if an investment has a snapshot on 2025-02-02, February 2025 shows that value. Months with no snapshot carry forward the previous month's value.

## Date range filtering

The dashboard supports two types of date range filtering:

### Preset date ranges

Preset buttons (1M, 3M, 6M, YTD, All) compute a date range automatically.

**Reference point:** Always `now()` (today's real date). If your latest snapshot is from two months ago and you select "1M", the evolution chart may still show data (it forward-fills monthly values from the last known snapshot), but the metric cards may show partial or zero results since TWR/IRR are computed only from snapshots that fall within the selected range.

**Start date snapping:** Presets snap the **start date of the range** to the 1st of the month. Snapshots always keep their real dates — only the range boundary moves. This prevents monthly snapshots from being accidentally excluded by day-level precision.

For example, with a snapshot on 2026-02-23 and today being 2026-03-23:

- **Preset 1M:** start_date = **Feb 1** (snapped) → snapshot on Feb 23 is **included** (23 >= 1)
- **Custom Feb 24 – Mar 23:** start_date = **Feb 24** (exact) → same snapshot is **excluded** (23 < 24)

The snapshot didn't move in either case. The difference is where the range starts.

| Preset | Start date formula          | Example (today = 2026-03-23) |
| ------ | --------------------------- | ---------------------------- |
| 1M     | 1st of (current month - 1)  | 2026-02-01                   |
| 3M     | 1st of (current month - 3)  | 2025-12-01                   |
| 6M     | 1st of (current month - 6)  | 2025-09-01                   |
| 1Y     | 1st of (current month - 12) | 2025-03-01                   |
| YTD    | January 1st of current year | 2026-01-01                   |
| All    | No filter applied           | —                            |

**End date:** Always today's date.

**1Y vs YTD:** These are different. 1Y starts 12 months back. YTD starts on January 1st of the current year. In March 2026: 1Y covers 12 months (Mar 2025–Mar 2026), YTD covers ~3 months (Jan–Mar).

### Custom date ranges

The custom date picker lets you choose exact start and end dates. Custom ranges do **not** snap to month boundaries — they use the exact dates you select.

**Example:** Custom range from 2026-02-24 to 2026-03-22:

- Snapshot on 2026-02-23 → **excluded** (Feb 23 < Feb 24)
- Snapshot on 2026-02-25 → **included** (Feb 25 is within range)
- Snapshot on 2026-03-22 → **included** (exactly on end date)
- Snapshot on 2026-03-23 → **excluded** (Mar 23 > Mar 22)

The filtering condition is: `snapshot.date >= start_date AND snapshot.date <= end_date`.

## What the date range affects

| Dashboard block    | Affected by date range? | Details                                                      |
| ------------------ | ----------------------- | ------------------------------------------------------------ |
| Metric cards       | Yes                     | TWR, IRR, and gain are computed only for the selected period |
| Evolution chart    | Yes                     | X axis shows only months within range                        |
| Distribution donut | No                      | Always shows current allocation                              |
| Investments table  | No                      | Always shows current values                                  |

## Configuring presets

Period presets are configurable via environment variables. See `.env.example` for details:

```
NEXT_PUBLIC_PERIOD_PRESET_1=1M
NEXT_PUBLIC_PERIOD_PRESET_2=3M
NEXT_PUBLIC_PERIOD_PRESET_3=6M
NEXT_PUBLIC_PERIOD_PRESET_4=YTD
```

Format: `NM` = N months, `NY` = N years, `YTD` = year to date. "All" is always appended as the last option. If no env vars are set, defaults to: 1M, 3M, 6M, YTD, All.
