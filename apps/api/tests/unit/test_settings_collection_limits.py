import pytest
from pydantic import ValidationError

from app.schemas.settings import COLLECTION_WARNING_PCT_RANGE, MAX_COLLECTIONS_RANGE, SettingsUpdate
from app.services import settings_service

# The two collection-limit settings are ranged on the way IN and on the way OUT. Unranged, `PUT
# /settings` stored a 4,000-digit `max_collections` and a `collection_warning_pct` of -5, and the reader
# handed both straight back to a page that multiplies one by the other.


class TestTheWriteRefusesAnOutOfRangeValue:
    @pytest.mark.parametrize(
        ("field", "bounds"),
        [("max_collections", MAX_COLLECTIONS_RANGE), ("collection_warning_pct", COLLECTION_WARNING_PCT_RANGE)],
    )
    def test_both_ends_are_accepted_and_one_past_either_is_refused(self, field, bounds):
        low, high = bounds
        assert getattr(SettingsUpdate(**{field: low}), field) == low
        assert getattr(SettingsUpdate(**{field: high}), field) == high
        for value in (low - 1, high + 1):
            with pytest.raises(ValidationError):
                SettingsUpdate(**{field: value})

    def test_the_two_reported_values_are_refused(self):
        with pytest.raises(ValidationError):
            SettingsUpdate(max_collections=10**4000)
        with pytest.raises(ValidationError):
            SettingsUpdate(collection_warning_pct=-5)

    def test_clearing_a_setting_is_still_allowed(self):
        assert SettingsUpdate(max_collections=None, collection_warning_pct=None).max_collections is None

    def test_the_ranges_match_the_form(self):
        # The Alerts form offers 1..1000 and 1..100 — the premise of both ranges, stated so a change to
        # one side is a decision rather than drift. The web asserts the same numbers from its side.
        assert MAX_COLLECTIONS_RANGE == (1, 1000)
        assert COLLECTION_WARNING_PCT_RANGE == (1, 100)


class TestTheReadDropsAValueStoredBeforeTheRange:
    @pytest.mark.parametrize(
        ("stored", "expected"),
        [({"max_collections": 20}, 20), ({"max_collections": 10**4000}, None), ({"max_collections": 0}, None)],
    )
    def test_max_collections(self, stored, expected):
        assert settings_service._settings_to_response(stored)["max_collections"] == expected

    @pytest.mark.parametrize(
        ("stored", "expected"),
        [({"collection_warning_pct": 80}, 80), ({"collection_warning_pct": -5}, None), ({"collection_warning_pct": 101}, None)],
    )
    def test_collection_warning_pct(self, stored, expected):
        assert settings_service._settings_to_response(stored)["collection_warning_pct"] == expected
