from datetime import UTC, date, datetime

import pytest

from app.services import auto_snapshot_service

# Unit coverage for the month-end auto-snapshot startup catch-up (P08 perf): the window + dedup
# decision and the pure most_recent_month_end helper. generate_auto_snapshots + the existence probe
# are faked so no DB is touched; now_utc is injected.


class TestRunStartupCatchup:
    def _wire(self, monkeypatch, *, has_autos: bool):
        ran = {"generated": False}

        async def fake_generate(session):
            ran["generated"] = True
            return 0

        async def fake_has(session, since):
            return has_autos

        monkeypatch.setattr(auto_snapshot_service, "generate_auto_snapshots", fake_generate)
        monkeypatch.setattr(auto_snapshot_service, "_has_auto_snapshots_since", fake_has)
        return ran

    # Inside the window with no auto snapshots since the month-end → the catch-up runs.
    @pytest.mark.asyncio
    async def test_runs_inside_window_when_no_autos(self, monkeypatch):
        ran = self._wire(monkeypatch, has_autos=False)
        result = await auto_snapshot_service.run_startup_catchup(
            None, catchup_days=3, snapshots_hour_utc=23, now_utc=datetime(2026, 7, 1, 10, 0, tzinfo=UTC)
        )
        assert result is True and ran["generated"] is True

    # Inside the window but autos already exist → no run.
    @pytest.mark.asyncio
    async def test_skips_when_autos_exist(self, monkeypatch):
        ran = self._wire(monkeypatch, has_autos=True)
        result = await auto_snapshot_service.run_startup_catchup(
            None, catchup_days=3, snapshots_hour_utc=23, now_utc=datetime(2026, 7, 1, 10, 0, tzinfo=UTC)
        )
        assert result is False and ran["generated"] is False

    # Before the month-end fire time (month-end day, before snapshots_hour_utc) → no run.
    @pytest.mark.asyncio
    async def test_skips_before_fire_time(self, monkeypatch):
        ran = self._wire(monkeypatch, has_autos=False)
        result = await auto_snapshot_service.run_startup_catchup(
            None, catchup_days=3, snapshots_hour_utc=23, now_utc=datetime(2026, 6, 30, 10, 0, tzinfo=UTC)
        )
        assert result is False and ran["generated"] is False

    # Past the catch-up window (more than catchup_days after the month-end fire) → no run.
    @pytest.mark.asyncio
    async def test_skips_past_catchup_window(self, monkeypatch):
        ran = self._wire(monkeypatch, has_autos=False)
        result = await auto_snapshot_service.run_startup_catchup(
            None, catchup_days=3, snapshots_hour_utc=23, now_utc=datetime(2026, 7, 5, 10, 0, tzinfo=UTC)
        )
        assert result is False and ran["generated"] is False


class TestMostRecentMonthEnd:
    @pytest.mark.parametrize(
        ("today", "expected"),
        [
            (date(2026, 7, 15), date(2026, 6, 30)),  # mid-month → previous month's last day
            (date(2026, 7, 31), date(2026, 7, 31)),  # on the last day → today
            (date(2026, 1, 1), date(2025, 12, 31)),  # Jan 1 → Dec 31 of the prior year
            (date(2024, 2, 29), date(2024, 2, 29)),  # leap-Feb last day → today
            (date(2024, 2, 15), date(2024, 1, 31)),  # mid leap-Feb → January's last day
        ],
    )
    def test_most_recent_month_end(self, today, expected):
        assert auto_snapshot_service.most_recent_month_end(today) == expected
