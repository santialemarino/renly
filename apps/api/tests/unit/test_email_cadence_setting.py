# Where the email cadence is stored, and the two readers between the switch and the digest job.
#
# It lives in `user_settings.settings` rather than in `notification_preferences`, because it is one
# answer per PERSON where that table is keyed by (event, channel) — the same place the onboarding flags
# live, written by their own service rather than by `PUT /settings`. That choice puts three small things
# on the honest-failure path, and a mutation sweep found none of them covered: an unknown stored value,
# the write itself, and the targeted JSONB merge behind it.

import asyncio
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.dialects import postgresql

from app.domain import DEFAULT_EMAIL_CADENCE, EmailCadence
from app.repositories import user_settings_repository
from app.services import settings_service


class TestReadingTheCadence:
    @pytest.mark.parametrize(
        ("stored", "expected"),
        [
            ("daily", EmailCadence.daily),
            ("immediate", EmailCadence.immediate),
            # Everything below is a value the column can hold and the app cannot mean. JSONB validates
            # nothing, so a hand-edited row, an older client or a future value rolled back reaches this
            # reader — and the safe direction is always "as it happens", because the other one silently
            # delays somebody's email by up to a day.
            ("weekly", DEFAULT_EMAIL_CADENCE),
            ("", DEFAULT_EMAIL_CADENCE),
            (None, DEFAULT_EMAIL_CADENCE),
            (True, DEFAULT_EMAIL_CADENCE),
            (7, DEFAULT_EMAIL_CADENCE),
        ],
    )
    def test_an_unrecognised_value_reads_as_the_shipped_default(self, stored, expected):
        assert settings_service._cadence_or_default(stored) == expected

    def test_the_shipped_default_is_immediate(self):
        # Stated as its own assertion because it is a product decision, not an implementation detail: a
        # digest delays a message by up to a day, and nobody should have that applied without asking.
        assert DEFAULT_EMAIL_CADENCE == EmailCadence.immediate

    @pytest.mark.asyncio
    async def test_a_user_with_no_settings_row_gets_the_default(self, monkeypatch):
        monkeypatch.setattr(settings_service.user_settings_repository, "get_by_user_id", AsyncMock(return_value=None))
        assert await settings_service.get_email_cadence(AsyncMock(), 1) == DEFAULT_EMAIL_CADENCE

    @pytest.mark.asyncio
    async def test_the_batch_reader_answers_for_every_id_it_was_asked_about(self, monkeypatch):
        # The fan-out asks about every recipient at once and then indexes the result by id, so an id
        # omitted here is a KeyError inside dispatch — which dispatch swallows.
        monkeypatch.setattr(
            settings_service.user_settings_repository,
            "get_string_by_user_ids",
            AsyncMock(return_value={2: "daily"}),
        )
        answers = await settings_service.get_email_cadences_by_user_ids(AsyncMock(), [1, 2, 3])
        assert answers == {1: DEFAULT_EMAIL_CADENCE, 2: EmailCadence.daily, 3: DEFAULT_EMAIL_CADENCE}


class TestWritingTheCadence:
    @pytest.mark.asyncio
    async def test_the_service_writes_the_chosen_value_under_the_cadence_key(self, monkeypatch):
        set_key = AsyncMock()
        monkeypatch.setattr(settings_service.user_settings_repository, "set_key", set_key)
        await settings_service.set_email_cadence(AsyncMock(), 4, EmailCadence.daily)
        assert set_key.await_args.args[1:] == (4, settings_service.SETTINGS_KEY_EMAIL_CADENCE, "daily")

    @pytest.mark.asyncio
    async def test_it_writes_the_string_rather_than_the_enum_member(self, monkeypatch):
        # JSONB has no enum type, so the value that lands in the blob is whatever is handed to it — and
        # the readers above compare against the string. A member would serialise fine and read back as
        # something the parametrised table above would reject.
        set_key = AsyncMock()
        monkeypatch.setattr(settings_service.user_settings_repository, "set_key", set_key)
        await settings_service.set_email_cadence(AsyncMock(), 4, EmailCadence.immediate)
        written = set_key.await_args.args[3]
        assert isinstance(written, str) and settings_service._cadence_or_default(written) == EmailCadence.immediate


class TestTheTargetedJsonbMerge:
    # `set_key` is the statement `latch_flag` was generalised from, and the whole point of it is that it
    # writes ONE key rather than the blob — a read-modify-write would clobber a settings save from
    # another tab. That is a property of the SQL, so it is asserted against the compiled statement; a
    # mocked session would return whatever it was told to.

    # Returns the statement's SQL and the values bound into it. JSONB has no literal renderer, so the
    # patch travels as a bound parameter rather than inline — which is where the value actually is.
    def _compiled(self, write) -> tuple[str, list]:
        session = AsyncMock()
        asyncio.run(write(session))
        compiled = session.execute.await_args.args[0].compile(dialect=postgresql.dialect())
        return str(compiled), list(compiled.params.values())

    def test_it_merges_rather_than_replaces_the_blob(self):
        sql, _ = self._compiled(lambda s: user_settings_repository.set_key(s, 4, "notification_email_cadence", "daily"))
        assert "ON CONFLICT (user_id) DO UPDATE" in sql
        # The `||` is what makes it a merge: without it the update sets `settings` to the one-key patch
        # and every other preference the user holds is gone.
        assert "user_settings.settings ||" in sql

    def test_the_value_reaches_the_statement_verbatim(self):
        # The mutation this exists for: a `set_key` that writes `True` regardless of its argument still
        # satisfies `latch_flag`'s only caller, so every latch test passes while the cadence is stored
        # as a boolean nothing can read.
        for cadence in ("daily", "immediate"):
            _, params = self._compiled(lambda s, c=cadence: user_settings_repository.set_key(s, 4, "notification_email_cadence", c))
            assert {"notification_email_cadence": cadence} in params

    def test_latch_flag_still_writes_true(self):
        # The one-value case it was generalised from, kept honest in the same place.
        _, params = self._compiled(lambda s: user_settings_repository.latch_flag(s, 4, "tour_completed"))
        assert {"tour_completed": True} in params
