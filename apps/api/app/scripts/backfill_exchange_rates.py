# One-off command: fills the exchange-rate history from the history providers (ArgentinaDatos for the
# three USD/ARS rates, Frankfurter for BRL/EUR/GBP), one row per day the source quotes. Run it once on a
# new or long-idle database; afterwards the scheduler keeps the recent window filled on its own.
#
#   uv run python -m app.scripts.backfill_exchange_rates --since 2011-01-01 [--until YYYY-MM-DD] [--dry-run]
#
# Safe to re-run: it inserts only the days with no stored rate, and replaces a stored rate only when it
# is provably a stale quote stamped with a later date (exchange_rate_service.is_misdated). It writes
# through the admin connection (DATABASE_ADMIN_URL), as the scheduler does.

import argparse
import asyncio
import sys
from datetime import date as date_type
from datetime import timedelta

from app.db import AdminSessionLocal, admin_engine
from app.models.exchange_rate import ExchangeRatePair
from app.services import exchange_rate_service
from app.services.exchange_rate_providers import ExchangeRateHistoryUnavailable

# The earliest day either history source quotes (ArgentinaDatos' oficial and blue series).
DEFAULT_SINCE = date_type(2011, 1, 1)


# Parses the command line.
def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill the daily exchange-rate history.")
    parser.add_argument("--since", type=date_type.fromisoformat, default=DEFAULT_SINCE, help="First day to fill (YYYY-MM-DD).")
    parser.add_argument(
        "--until",
        type=date_type.fromisoformat,
        default=None,
        help="Last day to fill (YYYY-MM-DD). Defaults to yesterday; today belongs to the scheduled fetch.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report what would be written without writing.")
    return parser.parse_args(argv)


# Formats one pair's stored coverage.
def _coverage_line(coverage: dict, pair: ExchangeRatePair) -> str:
    if pair not in coverage:
        return "0 rows"
    count, first, last = coverage[pair]
    return f"{count} rows, {first} to {last}"


# Runs the backfill and prints the rows per pair before and after. Returns the exit code.
async def _run(args: argparse.Namespace) -> int:
    until = args.until or date_type.today() - timedelta(days=1)
    if args.since > until:
        print(f"--since {args.since} is after --until {until}; nothing to do.", file=sys.stderr)
        return 2
    try:
        async with AdminSessionLocal() as session:
            before = await exchange_rate_service.get_coverage_by_pair(session)
            counts = await exchange_rate_service.backfill_history(session, args.since, until, dry_run=args.dry_run)
            after = await exchange_rate_service.get_coverage_by_pair(session)
    except ExchangeRateHistoryUnavailable as exc:
        print(f"A history source did not answer ({exc}); nothing was written. Re-run later.", file=sys.stderr)
        return 1
    finally:
        await admin_engine.dispose()

    mode = "DRY RUN — nothing written" if args.dry_run else "written"
    print(f"Exchange-rate backfill {args.since} to {until} ({mode}):")
    for pair in ExchangeRatePair:
        pair_counts = counts.get(pair, exchange_rate_service.PairBackfillCounts(0, 0))
        print(
            f"  {pair.value:<16} +{pair_counts.inserted} inserted, {pair_counts.repaired} repaired | "
            f"before: {_coverage_line(before, pair)} | after: {_coverage_line(after, pair)}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_run(_parse_args(sys.argv[1:]))))
