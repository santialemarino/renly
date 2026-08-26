# The scope boundary as the rest of the app sees it: which lookups may reach a co-owned row, what
# scope a child row inherits, and what is refused for crossing.
#
# Every test here exists because a mutation sweep found the rule UNPROVEN — each one was verified to
# redden against the specific break it describes. They live apart from test_pot_service.py because
# none of them is about pots as an entity: they are about investments, accounts and entries behaving
# correctly now that "mine" is no longer the same question as "not someone else's".

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.domain import NotFoundError, PrivateEntryFromSharedAccountError
from app.models.account import Account, AccountType
from app.models.investment import Currency, Investment, InvestmentCategory
from app.models.transaction import TransactionType
from app.models.user import User
from app.services import account_service, investment_service

USER = User(id=1, name="Santi", email="u@test", password_hash="x", session_epoch=0)


def _investment(*, user_id: int | None = 1, pot_id: int | None = None) -> Investment:
    return Investment(id=3, user_id=user_id, pot_id=pot_id, name="F", category=InvestmentCategory.fci, base_currency="USD")


def _account(*, user_id: int | None = 1, pot_id: int | None = None) -> Account:
    return Account(id=7, user_id=user_id, pot_id=pot_id, name="A", type=AccountType.bank, currency="USD", opening_date=date(2026, 1, 1))


class TestReachingACoOwnedRow:
    @pytest.mark.asyncio
    async def test_a_co_owned_investment_is_reachable_by_id(self, monkeypatch):
        # The owner-filtered lookup can never match a row whose user_id is NULL, so using it here
        # left a holding moved into a pot impossible to snapshot — and a pot that cannot be
        # snapshotted can never be valued, which makes the whole feature inert.
        monkeypatch.setattr(
            investment_service.investment_repository, "get_by_id_any_scope", AsyncMock(return_value=_investment(user_id=None, pot_id=5))
        )
        inv = await investment_service.get_investment(AsyncMock(), 3, USER)
        assert (inv.user_id, inv.pot_id) == (None, 5)

    @pytest.mark.asyncio
    async def test_another_users_private_investment_is_still_404(self, monkeypatch):
        # The half that must NOT have been widened. Any-scope reaching means the service now has to
        # state the private-branch owner check itself, instead of inheriting it from the query.
        monkeypatch.setattr(investment_service.investment_repository, "get_by_id_any_scope", AsyncMock(return_value=_investment(user_id=999)))
        with pytest.raises(NotFoundError):
            await investment_service.get_investment(AsyncMock(), 3, USER)

    @pytest.mark.asyncio
    async def test_a_co_owned_account_is_reachable_by_id(self, monkeypatch):
        monkeypatch.setattr(account_service.account_repository, "get_by_id_any_scope", AsyncMock(return_value=_account(user_id=None, pot_id=5)))
        acct = await account_service.get_account_in_scope(AsyncMock(), 7, USER)
        assert (acct.user_id, acct.pot_id) == (None, 5)

    @pytest.mark.asyncio
    async def test_another_users_private_account_is_still_404(self, monkeypatch):
        monkeypatch.setattr(account_service.account_repository, "get_by_id_any_scope", AsyncMock(return_value=_account(user_id=999)))
        with pytest.raises(NotFoundError):
            await account_service.get_account_in_scope(AsyncMock(), 7, USER)


class TestChildRowsInheritTheirParentsScope:
    # A snapshot or transaction takes its scope from the INVESTMENT, never from whoever is typing.
    # Taking the caller's would both violate the single-owner CHECK (a co-owned parent's child would
    # carry a user_id AND no pot) and hide the row from every other member, since the child's policy
    # reads the child's own scope rather than joining to the parent.

    @pytest.mark.asyncio
    async def test_a_snapshot_of_a_co_owned_investment_belongs_to_the_pot(self, monkeypatch):
        monkeypatch.setattr(investment_service, "get_investment", AsyncMock(return_value=_investment(user_id=None, pot_id=5)))
        monkeypatch.setattr(investment_service.snapshot_repository, "get_by_investment_and_date", AsyncMock(return_value=None))
        created = AsyncMock(side_effect=lambda _s, row: row)
        monkeypatch.setattr(investment_service.snapshot_repository, "create", created)
        await investment_service.upsert_snapshot(AsyncMock(), 3, USER, snapshot_date=date(2026, 6, 1), value=Decimal("100"), currency=Currency.USD)
        written = created.await_args.args[1]
        assert (written.user_id, written.pot_id) == (None, 5)

    @pytest.mark.asyncio
    async def test_a_snapshot_of_a_private_investment_still_belongs_to_its_owner(self, monkeypatch):
        # The positive control: without it, "inherits the parent" would pass even if the service
        # hardcoded None.
        monkeypatch.setattr(investment_service, "get_investment", AsyncMock(return_value=_investment(user_id=1)))
        monkeypatch.setattr(investment_service.snapshot_repository, "get_by_investment_and_date", AsyncMock(return_value=None))
        created = AsyncMock(side_effect=lambda _s, row: row)
        monkeypatch.setattr(investment_service.snapshot_repository, "create", created)
        await investment_service.upsert_snapshot(AsyncMock(), 3, USER, snapshot_date=date(2026, 6, 1), value=Decimal("100"), currency=Currency.USD)
        written = created.await_args.args[1]
        assert (written.user_id, written.pot_id) == (1, None)

    @pytest.mark.asyncio
    async def test_a_transaction_of_a_co_owned_investment_belongs_to_the_pot(self, monkeypatch):
        monkeypatch.setattr(investment_service, "get_investment", AsyncMock(return_value=_investment(user_id=None, pot_id=5)))
        created = AsyncMock(side_effect=lambda _s, row: row)
        monkeypatch.setattr(investment_service.transaction_repository, "create", created)
        await investment_service.create_transaction(
            AsyncMock(), 3, USER, transaction_date=date(2026, 6, 1), amount=Decimal("50"), currency=Currency.USD, tx_type=TransactionType.buy
        )
        written = created.await_args.args[1]
        assert (written.user_id, written.pot_id) == (None, 5)

    @pytest.mark.asyncio
    async def test_a_transaction_of_a_private_investment_still_belongs_to_its_owner(self, monkeypatch):
        monkeypatch.setattr(investment_service, "get_investment", AsyncMock(return_value=_investment(user_id=1)))
        created = AsyncMock(side_effect=lambda _s, row: row)
        monkeypatch.setattr(investment_service.transaction_repository, "create", created)
        await investment_service.create_transaction(
            AsyncMock(), 3, USER, transaction_date=date(2026, 6, 1), amount=Decimal("50"), currency=Currency.USD, tx_type=TransactionType.buy
        )
        written = created.await_args.args[1]
        assert (written.user_id, written.pot_id) == (1, None)


class TestAPrivateEntryCannotBeFundedFromSharedMoney:
    # O1. The money really leaves the shared account, so the pot's value drops and every co-owner's
    # share falls with it — one person spending and everyone paying, with nothing recording it.
    # Refused at load_linked_account, which is the single chokepoint every expense, income,
    # settlement and recurring-plan default funding link passes through.

    @pytest.mark.asyncio
    async def test_a_shared_funding_account_is_refused_with_its_own_reason(self, monkeypatch):
        monkeypatch.setattr(account_service.account_repository, "get_by_id_any_scope", AsyncMock(return_value=_account(user_id=None, pot_id=5)))
        with pytest.raises(PrivateEntryFromSharedAccountError):
            await account_service.load_linked_account(AsyncMock(), USER, 7)

    @pytest.mark.asyncio
    async def test_the_refusal_says_what_to_do_instead(self, monkeypatch):
        # A bare 404 would also have refused it — the owner filter alone does that — but it tells the
        # user nothing, which is why this is an explicit check rather than an inherited side effect.
        monkeypatch.setattr(account_service.account_repository, "get_by_id_any_scope", AsyncMock(return_value=_account(user_id=None, pot_id=5)))
        with pytest.raises(PrivateEntryFromSharedAccountError) as excinfo:
            await account_service.load_linked_account(AsyncMock(), USER, 7)
        assert "withdrawal" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_a_private_account_of_the_users_own_still_funds_normally(self, monkeypatch):
        monkeypatch.setattr(account_service.account_repository, "get_by_id_any_scope", AsyncMock(return_value=_account(user_id=1)))
        assert (await account_service.load_linked_account(AsyncMock(), USER, 7)).id == 7

    @pytest.mark.asyncio
    async def test_no_link_at_all_stays_a_no_op(self, monkeypatch):
        lookup = AsyncMock()
        monkeypatch.setattr(account_service.account_repository, "get_by_id_any_scope", lookup)
        assert await account_service.load_linked_account(AsyncMock(), USER, None) is None
        lookup.assert_not_awaited()


class TestATransferStaysInsideOneScope:
    # A transfer is net-worth-neutral BY CONSTRUCTION, and that is only true within one scope: moving
    # joint money into a personal account takes value from the other owners. Enforced in the service
    # AND in app/domain/, because no CHECK constraint can span two FK'd rows.

    def _wire(self, monkeypatch, source, destination):
        from app.services import transfer_service

        accounts = {source.id: source, destination.id: destination}

        async def get_account(_session, account_id, _user):
            return accounts[account_id]

        monkeypatch.setattr(transfer_service.account_service, "get_account_in_scope", AsyncMock(side_effect=get_account))

        async def create_row(_session, transfer):
            transfer.id = 1
            return transfer

        created = AsyncMock(side_effect=create_row)
        monkeypatch.setattr(transfer_service.transfer_repository, "create", created)
        return transfer_service, created

    @pytest.mark.asyncio
    async def test_a_private_to_shared_transfer_is_refused(self, monkeypatch):
        from app.domain import TransferCrossScopeError

        svc, created = self._wire(
            monkeypatch,
            Account(id=1, user_id=1, name="mine", type=AccountType.bank, currency="USD", opening_date=date(2026, 1, 1)),
            Account(id=2, user_id=None, pot_id=5, name="joint", type=AccountType.bank, currency="USD", opening_date=date(2026, 1, 1)),
        )
        with pytest.raises(TransferCrossScopeError):
            await svc.create_transfer(AsyncMock(), USER, from_account_id=1, to_account_id=2, date=date(2026, 6, 1), from_amount=Decimal("10"))
        created.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_shared_to_private_transfer_is_refused_too(self, monkeypatch):
        from app.domain import TransferCrossScopeError

        svc, created = self._wire(
            monkeypatch,
            Account(id=1, user_id=None, pot_id=5, name="joint", type=AccountType.bank, currency="USD", opening_date=date(2026, 1, 1)),
            Account(id=2, user_id=1, name="mine", type=AccountType.bank, currency="USD", opening_date=date(2026, 1, 1)),
        )
        with pytest.raises(TransferCrossScopeError):
            await svc.create_transfer(AsyncMock(), USER, from_account_id=1, to_account_id=2, date=date(2026, 6, 1), from_amount=Decimal("10"))
        created.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_transfer_between_two_pot_accounts_is_stamped_with_the_pot(self, monkeypatch):
        # And carries NO user_id, which is what makes its own RLS policy gate it on pot WRITE access —
        # the thing that stops a read-only member moving money out of an account they can only see.
        svc, created = self._wire(
            monkeypatch,
            Account(id=1, user_id=None, pot_id=5, name="a", type=AccountType.bank, currency="USD", opening_date=date(2026, 1, 1)),
            Account(id=2, user_id=None, pot_id=5, name="b", type=AccountType.bank, currency="USD", opening_date=date(2026, 1, 1)),
        )
        await svc.create_transfer(AsyncMock(), USER, from_account_id=1, to_account_id=2, date=date(2026, 6, 1), from_amount=Decimal("10"))
        written = created.await_args.args[1]
        assert (written.user_id, written.pot_id) == (None, 5)

    @pytest.mark.asyncio
    async def test_a_private_to_private_transfer_still_belongs_to_its_owner(self, monkeypatch):
        svc, created = self._wire(
            monkeypatch,
            Account(id=1, user_id=1, name="a", type=AccountType.bank, currency="USD", opening_date=date(2026, 1, 1)),
            Account(id=2, user_id=1, name="b", type=AccountType.bank, currency="USD", opening_date=date(2026, 1, 1)),
        )
        await svc.create_transfer(AsyncMock(), USER, from_account_id=1, to_account_id=2, date=date(2026, 6, 1), from_amount=Decimal("10"))
        written = created.await_args.args[1]
        assert (written.user_id, written.pot_id) == (1, None)


class TestExportAndRestoreAcrossTheBoundary:
    # The asymmetry, and it is deliberate on both sides: an export answers "what does Renly hold about
    # me", and a portfolio you co-own is part of that answer — but a restore cannot rebuild a shared
    # pot from one member's file without issuing units to placeholders standing in for real people.

    @pytest.mark.asyncio
    async def test_the_scoped_tables_are_read_with_BOTH_branches(self, monkeypatch):
        # Without the pot branch every shared holding vanishes from a user's export with no error at
        # all, which is the one failure mode an export must never have. Asserted on the SQL the
        # repository emitted, because a stub session returns whatever it was told either way.
        from app.repositories import export_repository

        emitted = []

        class _Result:
            def scalars(self):
                return self

            def all(self):
                return []

        class _Session:
            async def execute(self, stmt, *_a, **_k):
                emitted.append(str(stmt))
                return _Result()

        await export_repository.dump_user_data(_Session(), 1)
        scoped = [q for q in emitted if " FROM investments" in q or "\nFROM investments" in q]
        assert scoped, "no investments query was emitted at all"
        assert any("pot_id IN" in q and "user_id =" in q for q in scoped), scoped

    @pytest.mark.asyncio
    async def test_every_scoped_table_declares_itself_private_only_for_restore(self):
        # The five tables whose user_id became an OWNER. account_reconciliations is absent from
        # RESTORE_SPECS entirely (a reconciliation is a true-up against a balance the restore has just
        # re-derived), so it needs no flag — and asserting that explicitly stops a future reader from
        # "fixing" the apparent omission.
        from app.domain.restore_specs import RESTORE_SPECS

        by_key = {spec.key: spec for spec in RESTORE_SPECS}
        for key in ("investments", "accounts", "investment_snapshots", "transactions", "transfers"):
            assert by_key[key].private_only, f"{key} would restore co-owned rows"
        assert "account_reconciliations" not in by_key

    def test_a_co_owned_row_in_a_file_is_skipped_rather_than_privatised(self):
        # Nulling the pot instead would hand the restoring user sole ownership of something several
        # people own — inventing a transfer of value nobody agreed to.
        from app.domain.restore_specs import RESTORE_SPECS

        spec = next(s for s in RESTORE_SPECS if s.key == "investments")
        assert spec.private_only is True
        assert "pot_id" not in spec.null_fields


class TestAccountDeletionAcrossTheBoundary:
    @pytest.mark.asyncio
    async def test_an_orphaned_groups_holdings_are_absorbed_before_the_account_goes(self, monkeypatch):
        # Ordering is the whole rule. Every pot_id FK is ON DELETE RESTRICT, so deleting an orphaned
        # group that still owns holdings simply fails — and after the user row is gone there is no id
        # left to assign them to.
        from app.services import user_account_service as svc

        calls = []
        monkeypatch.setattr(svc.auth_service, "verify_password", AsyncMock(return_value=True))
        monkeypatch.setattr(svc.group_repository, "list_orphaned_group_ids", AsyncMock(return_value=[10]))
        monkeypatch.setattr(svc.invite_repository, "delete_by_email", AsyncMock(side_effect=lambda *a, **k: calls.append("invite")))
        monkeypatch.setattr(svc.user_repository, "delete", AsyncMock(side_effect=lambda *a, **k: calls.append("delete_user")))
        monkeypatch.setattr(svc.group_repository, "delete_by_ids", AsyncMock(side_effect=lambda *a, **k: calls.append("delete_groups")))
        absorb = AsyncMock(side_effect=lambda *a, **k: calls.append("absorb"))
        monkeypatch.setattr(svc.pot_service, "absorb_group_pots", absorb)

        user = User(id=1, name="S", email="u@test", password_hash="x", session_epoch=0)
        await svc.delete_account(AsyncMock(), AsyncMock(), user, "pw", "u@test")

        assert "absorb" in calls, "an orphaned group's holdings were never absorbed"
        assert calls.index("absorb") < calls.index("delete_user"), calls
        assert absorb.await_args.args[1:] == ([10], 1)
