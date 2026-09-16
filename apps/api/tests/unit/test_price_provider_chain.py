from datetime import date
from decimal import Decimal

import pytest

from app.models.investment import InvestmentCategory
from app.services import asset_price_service, price_providers
from app.services.price_providers import PriceProviderInfo, PriceProviderUnavailable

# INFRA-9's fallback chain, driven with fake providers (no network, no DB).
#
# The property under test throughout is which provider ANSWERS and what the row is then labelled with,
# because those are the two things the old single-provider map could not get right: it had nowhere to
# put a second provider, and it read the stored `source` from the map rather than from whoever actually
# served the price — so every FCI price served by the ArgentinaDatos fallback was written down as
# "cafci", and `SOURCE_ARGENTIADATOS` was declared and never once used.

_ROW = [(date(2026, 9, 16), Decimal("100"), "USD")]


# A provider that answers with the given rows, recording that it was called.
def _answers(source: str, rows=None, *, supports_history: bool = True, configured: bool = True) -> tuple[PriceProviderInfo, list]:
    calls: list[str] = []

    async def fetch(ticker, start_date, end_date):
        calls.append(ticker)
        return _ROW if rows is None else rows

    return (
        PriceProviderInfo(source=source, fetch=fetch, supports_history=supports_history, is_configured=lambda: configured),
        calls,
    )


# A provider that cannot answer at all — the only outcome that advances the chain.
def _fails(source: str, *, supports_history: bool = True) -> tuple[PriceProviderInfo, list]:
    calls: list[str] = []

    async def fetch(ticker, start_date, end_date):
        calls.append(ticker)
        raise PriceProviderUnavailable(f"{source} is down")

    return PriceProviderInfo(source=source, fetch=fetch, supports_history=supports_history), calls


class TestTheChainStopsAtTheFirstProviderThatAnswers:
    @pytest.mark.asyncio
    async def test_the_primary_answering_means_no_fallback_is_called(self, monkeypatch):
        primary, primary_calls = _answers("primary")
        backup, backup_calls = _answers("backup")
        monkeypatch.setattr(asset_price_service, "_CATEGORY_PROVIDERS", {InvestmentCategory.stocks: (primary, backup)})

        rows, source = await asset_price_service._fetch_through_chain("AAPL", InvestmentCategory.stocks)

        assert (rows, source) == (_ROW, "primary")
        assert (primary_calls, backup_calls) == (["AAPL"], [])

    @pytest.mark.asyncio
    async def test_an_EMPTY_answer_still_stops_the_chain(self, monkeypatch):
        # The distinction the whole design rests on. An empty list is the provider saying "I am fine and
        # this ticker has no price for that range" — a weekend, a delisting — and asking the next
        # provider the identical question can only produce a second no. Before INFRA-9 every provider
        # returned [] for its own failures too, which is what made the two indistinguishable.
        primary, primary_calls = _answers("primary", rows=[])
        backup, backup_calls = _answers("backup")
        monkeypatch.setattr(asset_price_service, "_CATEGORY_PROVIDERS", {InvestmentCategory.stocks: (primary, backup)})

        rows, source = await asset_price_service._fetch_through_chain("AAPL", InvestmentCategory.stocks)

        assert (rows, source) == ([], "primary")
        assert backup_calls == [], "an empty answer is an answer — the fallback must not be reached"


class TestTheChainAdvancesOnlyOnAFailure:
    @pytest.mark.asyncio
    async def test_a_failed_primary_hands_over_to_the_fallback(self, monkeypatch):
        primary, primary_calls = _fails("primary")
        backup, backup_calls = _answers("backup")
        monkeypatch.setattr(asset_price_service, "_CATEGORY_PROVIDERS", {InvestmentCategory.stocks: (primary, backup)})

        rows, source = await asset_price_service._fetch_through_chain("AAPL", InvestmentCategory.stocks)

        assert (rows, source) == (_ROW, "backup")
        assert (primary_calls, backup_calls) == (["AAPL"], ["AAPL"])

    @pytest.mark.asyncio
    async def test_the_row_is_labelled_with_who_SERVED_it_not_who_was_asked_first(self, monkeypatch):
        # The defect this fixes, stated as its own assertion rather than left implied by the one above:
        # the source travels with the result. Reading it from the map instead is how a price fetched
        # from ArgentinaDatos came to be stored claiming it came from CAFCI.
        primary, _ = _fails("cafci")
        backup, _ = _answers("argentinadatos")
        monkeypatch.setattr(asset_price_service, "_CATEGORY_PROVIDERS", {InvestmentCategory.fci: (primary, backup)})

        _rows, source = await asset_price_service._fetch_through_chain("4321", InvestmentCategory.fci)

        assert source == "argentinadatos"

    @pytest.mark.asyncio
    async def test_every_provider_failing_reports_nothing_rather_than_an_empty_price_list(self, monkeypatch):
        # None and [] mean different things to the caller: [] is "no price exists" and stores nothing
        # quietly, None is "we could not find out", which is the outcome that has to be loud.
        primary, _ = _fails("primary")
        backup, _ = _fails("backup")
        monkeypatch.setattr(asset_price_service, "_CATEGORY_PROVIDERS", {InvestmentCategory.stocks: (primary, backup)})

        assert await asset_price_service._fetch_through_chain("AAPL", InvestmentCategory.stocks) is None

    @pytest.mark.asyncio
    async def test_a_whole_chain_failing_is_logged_as_an_error_naming_the_ticker(self, monkeypatch, caplog):
        # The server-side signal is the entire user-visible consequence of this unit: prices silently
        # stop updating and the app keeps rendering the last stored value. A log line nobody emits is
        # the same as no fallback at all, so assert it rather than trusting it.
        primary, _ = _fails("primary")
        monkeypatch.setattr(asset_price_service, "_CATEGORY_PROVIDERS", {InvestmentCategory.stocks: (primary,)})

        with caplog.at_level("ERROR"):
            await asset_price_service._fetch_through_chain("AAPL", InvestmentCategory.stocks)

        errors = [record.getMessage() for record in caplog.records if record.levelname == "ERROR"]
        assert any("AAPL" in message for message in errors), errors


class TestAProviderThatCannotAnswerTheQuestionIsSkipped:
    @pytest.mark.asyncio
    async def test_an_unconfigured_provider_is_skipped_without_being_called(self, monkeypatch):
        # Finnhub needs a key. A deployment that never set one has no Finnhub in its chain — it is not a
        # failure, and logging it as one every refresh cycle is how a real error becomes background noise.
        primary, _ = _fails("primary")
        unconfigured, unconfigured_calls = _answers("needs-a-key", configured=False)
        monkeypatch.setattr(asset_price_service, "_CATEGORY_PROVIDERS", {InvestmentCategory.stocks: (primary, unconfigured)})

        assert await asset_price_service._fetch_through_chain("AAPL", InvestmentCategory.stocks) is None
        assert unconfigured_calls == []

    @pytest.mark.asyncio
    async def test_a_live_quote_provider_is_skipped_for_a_DATED_request(self, monkeypatch):
        # data912 and Finnhub answer only "what is it worth now". Asked what a holding cost in January,
        # a live quote is a WRONG answer rather than a missing one — worse than no answer, because it
        # would be stored. `supports_history` was declared on every provider and read by nothing until
        # the chain gave it a job.
        primary, _ = _fails("primary")
        live_only, live_calls = _answers("live-only", supports_history=False)
        monkeypatch.setattr(asset_price_service, "_CATEGORY_PROVIDERS", {InvestmentCategory.stocks: (primary, live_only)})

        result = await asset_price_service._fetch_through_chain("AAPL", InvestmentCategory.stocks, date(2026, 1, 5), date(2026, 1, 5))

        assert (result, live_calls) == (None, [])

    @pytest.mark.asyncio
    async def test_the_same_live_quote_provider_IS_used_when_no_date_is_asked_for(self, monkeypatch):
        # The other half, so the skip above is proven to be about the DATE rather than about that
        # provider being excluded outright.
        primary, _ = _fails("primary")
        live_only, live_calls = _answers("live-only", supports_history=False)
        monkeypatch.setattr(asset_price_service, "_CATEGORY_PROVIDERS", {InvestmentCategory.stocks: (primary, live_only)})

        _rows, source = await asset_price_service._fetch_through_chain("AAPL", InvestmentCategory.stocks)

        assert (source, live_calls) == ("live-only", ["AAPL"])


class TestTheStoredRowCarriesTheServingSource:
    @pytest.mark.asyncio
    async def test_a_refresh_labels_each_row_with_the_provider_that_answered(self, monkeypatch):
        # Driven through the refresh path rather than the chain alone, because that path used to read
        # the source from the map a SECOND time, after the fetch — so a fix applied only to the
        # single-ticker path would leave the scheduler still mislabelling every row it wrote.
        from app.models.investment import Investment

        primary, _ = _fails("cafci")
        backup, _ = _answers("argentinadatos")
        monkeypatch.setattr(asset_price_service, "_CATEGORY_PROVIDERS", {InvestmentCategory.fci: (primary, backup)})

        written: list = []

        async def fake_bulk_upsert(session, prices):
            written.extend(prices)
            return len(prices)

        monkeypatch.setattr(asset_price_service.asset_price_repository, "bulk_upsert", fake_bulk_upsert)

        class FakeSession:
            async def commit(self):
                return None

        investments = [Investment(id=1, user_id=1, name="f", category=InvestmentCategory.fci, base_currency="ARS", ticker="4321")]
        await asset_price_service._refresh_prices_for_investments(FakeSession(), investments)

        assert [price.source for price in written] == ["argentinadatos"]


class TestTheChainsAreWellFormed:
    def test_every_category_maps_to_a_TUPLE_of_providers(self):
        # A PriceProviderInfo is itself a NamedTuple, so a chain written `provider` instead of
        # `(provider,)` iterates its FIELDS — and fails with "'str' object has no attribute
        # 'is_configured'", which names neither the cause nor the fix. Two existing tests did exactly
        # this. Asserting the shape turns that into a sentence.
        for category, chain in asset_service_chains().items():
            assert isinstance(chain, tuple), f"{category} must map to a tuple of providers"
            assert chain, f"{category} maps to an empty chain"
            for provider in chain:
                assert isinstance(provider, PriceProviderInfo), f"{category} holds a {type(provider).__name__}"

    def test_no_chain_lists_the_same_provider_twice(self):
        # A repeated source is a chain that retries one outage instead of reaching an independent one.
        for category, chain in asset_service_chains().items():
            sources = [provider.source for provider in chain]
            assert len(sources) == len(set(sources)), f"{category} repeats a provider: {sources}"

    def test_every_source_a_chain_can_store_is_a_declared_constant(self):
        # The stored `source` is now whatever the serving provider calls itself, so a typo there writes
        # a source nothing else in the codebase knows. Compared against the module's own constants as a
        # set difference rather than per-provider, so a provider added later is covered by the same
        # assertion instead of needing its own.
        declared = {value for name, value in vars(price_providers).items() if name.startswith("SOURCE_") or name.endswith("_SOURCE")}
        used = {provider.source for chain in asset_service_chains().values() for provider in chain}
        assert used - declared == set(), f"chain sources with no SOURCE_* constant: {used - declared}"


# The live chain map, read through a function so the structural tests above cannot accidentally pick up
# a monkeypatched copy from an async test that ran earlier.
def asset_service_chains() -> dict:
    return asset_price_service._CATEGORY_PROVIDERS
