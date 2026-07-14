from datetime import UTC, date, datetime
from unittest.mock import AsyncMock

import pytest

from app.services import settings_service

BA = "America/Argentina/Buenos_Aires"


# Minimal stand-in for the user_settings row: the helpers only read `.settings`.
class _Row:
    def __init__(self, settings):
        self.settings = settings


# Patches the settings-row read so no session/DB is needed (session arg passed as None).
def _patch_row(monkeypatch, row):
    monkeypatch.setattr(settings_service.user_settings_repository, "get_by_user_id", AsyncMock(return_value=row))


# --- get_user_timezone ---


class TestGetUserTimezone:
    @pytest.mark.asyncio
    async def test_returns_stored_timezone(self, monkeypatch):
        _patch_row(monkeypatch, _Row({"timezone": BA}))
        assert await settings_service.get_user_timezone(None, 1) == BA

    @pytest.mark.asyncio
    async def test_no_row_returns_none(self, monkeypatch):
        _patch_row(monkeypatch, None)
        assert await settings_service.get_user_timezone(None, 1) is None

    @pytest.mark.asyncio
    async def test_missing_key_returns_none(self, monkeypatch):
        _patch_row(monkeypatch, _Row({}))
        assert await settings_service.get_user_timezone(None, 1) is None

    @pytest.mark.asyncio
    async def test_empty_string_returns_none(self, monkeypatch):
        _patch_row(monkeypatch, _Row({"timezone": ""}))
        assert await settings_service.get_user_timezone(None, 1) is None

    @pytest.mark.asyncio
    async def test_non_string_returns_none(self, monkeypatch):
        _patch_row(monkeypatch, _Row({"timezone": 123}))
        assert await settings_service.get_user_timezone(None, 1) is None


# --- get_user_today ---


class TestGetUserToday:
    @pytest.mark.asyncio
    async def test_buenos_aires_is_previous_day_at_02_utc(self, monkeypatch):
        # 2026-05-25 02:00 UTC = 2026-05-24 23:00 ART (UTC-3) -> user's today is still May 24.
        _patch_row(monkeypatch, _Row({"timezone": BA}))
        now = datetime(2026, 5, 25, 2, 0, tzinfo=UTC)
        assert await settings_service.get_user_today(None, 1, now_utc=now) == date(2026, 5, 24)

    @pytest.mark.asyncio
    async def test_auckland_is_next_day_at_13_utc(self, monkeypatch):
        # 2026-05-25 13:00 UTC = 2026-05-26 01:00 NZST (UTC+12 in May) -> today is May 26.
        _patch_row(monkeypatch, _Row({"timezone": "Pacific/Auckland"}))
        now = datetime(2026, 5, 25, 13, 0, tzinfo=UTC)
        assert await settings_service.get_user_today(None, 1, now_utc=now) == date(2026, 5, 26)

    @pytest.mark.asyncio
    async def test_no_settings_row_falls_back_to_utc_date(self, monkeypatch):
        _patch_row(monkeypatch, None)
        now = datetime(2026, 5, 25, 23, 30, tzinfo=UTC)
        assert await settings_service.get_user_today(None, 1, now_utc=now) == date(2026, 5, 25)
