import json
import os
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import Pool

# U20: the overdue-pot reminder fans out on ONE tick for an Argentina-facing app (everybody shares a
# timezone, and everybody who never synced one falls back to UTC 09:00). Before the batch, every due pot
# paid its own freshness reads and its own dispatch on a FRESH admin connection: 305 statements and 100
# connections at 100 pots.
#
# Two halves, each of which the other cannot stand in for:
#
#   * the COST, counted on the wire for every engine in the process (a class-level cursor listener) and
#     as pool checkouts, for 1, 10 and 100 due pots. Nothing is assumed about which reads are batched: a
#     per-pot read or a per-pot connection anywhere under the job shows up as a count that moves with N.
#   * the ANSWER, because a fixed count is easy to buy by telling people something different. The
#     batched job is held to one dispatch per stale pot, in pot order — what the job did before — over a
#     fixture reaching every branch a recipient has: every channel off, the feed off, email off, the daily
#     digest, two browsers, a reminder already sent this period, a fresh pot, a weekly pot, a viewer who
#     cannot write. Compared as the rows written, the emails and pushes sent, and the browsers stamped.
#
# Admin role (renly_admin, BYPASSRLS), as the scheduler runs it. Dispatch's own connection is redirected
# to this database, so the sequential half runs against the same rows.
from app.models.notification import NotificationEvent
from app.services import notification_service, pot_reminder_service

DB_URL = os.getenv("LEDGER_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DB_URL,
    reason="set LEDGER_TEST_DATABASE_URL (a real Postgres with the schema applied) to run these",
)

_PREFIX = "u20batch_"
# 00:00 UTC is 09:00 in Tokyo, the reminder hour, on a tick where a UTC-fallback user (09:00 UTC) is
# not due — so any other data in the database stays out of both halves.
_TICK = datetime(2026, 9, 2, 0, 0, tzinfo=UTC)
_TOKYO = "Asia/Tokyo"
_POT_COUNTS = (1, 10, 100)


@pytest_asyncio.fixture
async def factory(monkeypatch):
    engine = create_async_engine(DB_URL)
    make = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    # The connection dispatch opens for itself, pointed here rather than at DATABASE_ADMIN_URL.
    monkeypatch.setattr(notification_service, "AdminSessionLocal", make)
    async with make() as s:
        await _cleanup(s)
        await s.commit()
    yield make
    async with make() as s:
        await _cleanup(s)
        await s.commit()
    await engine.dispose()


# Everything this file writes. Pots and their children cascade from their group; notifications, settings,
# preferences and browsers cascade from their user.
async def _cleanup(s: AsyncSession) -> None:
    params = {"p": f"{_PREFIX}%"}
    users = "SELECT id FROM users WHERE email LIKE :p"
    pots = f"SELECT id FROM pots WHERE group_id IN (SELECT id FROM groups WHERE created_by IN ({users}))"
    await s.execute(text(f"DELETE FROM investments WHERE pot_id IN ({pots})"), params)
    await s.execute(text(f"DELETE FROM accounts WHERE pot_id IN ({pots})"), params)
    await s.execute(text(f"DELETE FROM groups WHERE created_by IN ({users})"), params)
    await s.execute(text("DELETE FROM users WHERE email LIKE :p"), params)


class _Seeder:
    def __init__(self, s: AsyncSession) -> None:
        self.s = s

    async def scalar(self, sql: str, **params) -> int:
        return (await self.s.execute(text(sql), params)).scalar_one()

    async def user(self, name: str, *, settings: dict | None = None) -> int:
        user = await self.scalar(
            "INSERT INTO users (name, email, password_hash) VALUES (:n, :e, 'h') RETURNING id", n=name, e=f"{_PREFIX}{name}@test.local"
        )
        await self.s.execute(
            text("INSERT INTO user_settings (user_id, settings) VALUES (:u, CAST(:s AS jsonb))"),
            {"u": user, "s": json.dumps({"timezone": _TOKYO, **(settings or {})})},
        )
        return user

    async def preference(self, user: int, channel: str, *, enabled: bool) -> None:
        await self.s.execute(
            text(
                "INSERT INTO notification_preferences (user_id, event, channel, enabled) "
                "VALUES (:u, 'snapshot_due', CAST(:c AS notification_channel), :e)"
            ),
            {"u": user, "c": channel, "e": enabled},
        )

    async def browser(self, user: int, endpoint: str) -> None:
        await self.s.execute(
            text("INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth) VALUES (:u, :e, 'p', 'a')"),
            {"u": user, "e": f"https://push.test/{_PREFIX}{endpoint}"},
        )

    async def group(self, name: str, creator: int) -> int:
        return await self.scalar("INSERT INTO groups (name, kind, created_by) VALUES (:n, 'household', :u) RETURNING id", n=name, u=creator)

    async def member(self, group: int, user: int) -> int:
        return await self.scalar(
            "INSERT INTO group_members (group_id, user_id, display_name, role, is_active) VALUES (:g, :u, 'M', 'member', TRUE) RETURNING id",
            g=group,
            u=user,
        )

    # A pot holding one investment nobody has valued (overdue on any cadence) or, when `fresh`, one
    # account (valued as of the day asked about, so never overdue).
    async def pot(self, group: int, name: str, *, creator: int, writers=(), viewers=(), cadence: str = "monthly", fresh: bool = False) -> int:
        pot = await self.scalar(
            "INSERT INTO pots (group_id, name, base_currency, snapshot_cadence) VALUES (:g, :n, 'USD', CAST(:c AS pot_cadence)) RETURNING id",
            g=group,
            n=name,
            c=cadence,
        )
        if fresh:
            await self.s.execute(
                text(
                    "INSERT INTO accounts (pot_id, created_by, name, type, currency, opening_balance, opening_date, is_active) "
                    "VALUES (:p, :u, 'a', 'bank', 'USD', 0, '2026-01-01', TRUE)"
                ),
                {"p": pot, "u": creator},
            )
        else:
            await self.s.execute(
                text(
                    "INSERT INTO investments (pot_id, created_by, name, category, base_currency, is_active) "
                    "VALUES (:p, :u, 'i', 'stocks', 'USD', TRUE)"
                ),
                {"p": pot, "u": creator},
            )
        for member, can_write in [*((m, True) for m in writers), *((m, False) for m in viewers)]:
            await self.s.execute(
                text("INSERT INTO pot_member_permissions (pot_id, member_id, can_view, can_write) VALUES (:p, :m, TRUE, :w)"),
                {"p": pot, "m": member, "w": can_write},
            )
        return pot


# Counts statements on the wire, connection checkouts, and the most connections held AT ONCE, across
# every engine and pool in the process — so a dispatch opening its own connection is counted as surely
# as one borrowing the job's. The job's one session checks a connection out again after each commit
# (the fan-out commits its rows before it delivers), so checkouts is a small constant, not one.
async def _count(job) -> tuple[int, int, int, object]:
    statements: list[str] = []
    checkouts = [0]
    held = [0, 0]  # now, peak

    def on_statement(_conn, _cursor, statement, *_args) -> None:
        statements.append(statement)

    def on_checkout(*_args) -> None:
        checkouts[0] += 1
        held[0] += 1
        held[1] = max(held)

    def on_checkin(*_args) -> None:
        held[0] -= 1

    event.listen(Engine, "before_cursor_execute", on_statement)
    event.listen(Pool, "checkout", on_checkout)
    event.listen(Pool, "checkin", on_checkin)
    try:
        result = await job()
    finally:
        event.remove(Engine, "before_cursor_execute", on_statement)
        event.remove(Pool, "checkout", on_checkout)
        event.remove(Pool, "checkin", on_checkin)
    return len(statements), checkouts[0], held[1], result


# --- Cost ---


# N pots, each in its own group with its own Tokyo writer, every one of them overdue.
async def _seed_due_pots(make, n: int) -> None:
    async with make() as s:
        seed = _Seeder(s)
        for i in range(n):
            user = await seed.user(f"cost{n}_{i}")
            group = await seed.group(f"{_PREFIX}g{i}", user)
            await seed.pot(group, f"p{i}", creator=user, writers=[await seed.member(group, user)])
        await s.commit()


@pytest.mark.asyncio
async def test_a_tick_costs_the_same_statements_and_connections_however_many_pots_are_due(factory, monkeypatch):
    _Capture(monkeypatch)
    measured: dict[int, tuple[int, int, int, int]] = {}
    for n in _POT_COUNTS:
        async with factory() as s:
            await _cleanup(s)
            await s.commit()
        await _seed_due_pots(factory, n)

        async def job() -> int:
            async with factory() as session:
                return await pot_reminder_service.send_due_reminders(session, _TICK)

        measured[n] = await _count(job)
    print(f"\nreminder tick at N due pots -> (statements, checkouts, peak connections, told): {measured}")
    # The population is real: every pot was due and every writer was told.
    assert [measured[n][3] for n in _POT_COUNTS] == list(_POT_COUNTS)
    assert len({measured[n][:2] for n in _POT_COUNTS}) == 1, measured
    # The job's own connection is the only one: dispatch never checks out a second beside it.
    assert [measured[n][2] for n in _POT_COUNTS] == [1] * len(_POT_COUNTS), measured


# --- Answer ---


# The rows, emails, pushes and stamped browsers one run left behind, for this file's users only, in an
# order-free shape. Emails and pushes are captured at the send so no provider is reached.
class _Capture:
    def __init__(self, monkeypatch) -> None:
        self.emails: list[tuple] = []
        self.pushes: list[tuple] = []

        async def send_email(user, event_, payload, locale, link) -> None:
            self.emails.append((user.email, event_.value, json.dumps(payload, sort_keys=True), locale, link))

        async def send_push(_client, subscription, event_, payload, locale, link):
            self.pushes.append((subscription.endpoint, event_.value, json.dumps(payload, sort_keys=True), locale, link))
            return (subscription, True, False)

        monkeypatch.setattr(notification_service, "_send_email", send_email)
        monkeypatch.setattr(notification_service, "_send_push", send_push)
        monkeypatch.setattr(notification_service.web_push, "is_configured", lambda: True)

    async def snapshot(self, make) -> dict:
        async with make() as s:
            rows = await s.execute(
                text(
                    "SELECT u.email, n.event::text, n.payload::text, n.dedupe_key, n.digest_pending FROM notifications n "
                    "JOIN users u ON u.id = n.user_id WHERE u.email LIKE :p"
                ),
                {"p": f"{_PREFIX}%"},
            )
            stamped = await s.execute(
                text("SELECT endpoint FROM push_subscriptions WHERE endpoint LIKE :p AND last_used_at IS NOT NULL"),
                {"p": f"https://push.test/{_PREFIX}%"},
            )
            normalised = [
                (email, ev, json.dumps(json.loads(payload), sort_keys=True), key, pending) for email, ev, payload, key, pending in rows.all()
            ]
            return {
                "rows": sorted(normalised),
                "emails": sorted(self.emails),
                "pushes": sorted(self.pushes),
                "stamped": sorted(e for (e,) in stamped.all()),
            }

    def reset(self) -> None:
        self.emails.clear()
        self.pushes.clear()


# Puts the database back to the state before a run: no rows but the ones already sent this period, and no
# browser stamped.
async def _rewind(make, already_sent: list[tuple[int, str, dict]]) -> None:
    async with make() as s:
        await s.execute(text("DELETE FROM notifications WHERE user_id IN (SELECT id FROM users WHERE email LIKE :p)"), {"p": f"{_PREFIX}%"})
        await s.execute(text("UPDATE push_subscriptions SET last_used_at = NULL WHERE endpoint LIKE :p"), {"p": f"https://push.test/{_PREFIX}%"})
        for user, key, payload in already_sent:
            await s.execute(
                text("INSERT INTO notifications (user_id, event, payload, dedupe_key) VALUES (:u, 'snapshot_due', CAST(:pl AS jsonb), :k)"),
                {"u": user, "pl": json.dumps(payload), "k": key},
            )
        await s.commit()


@pytest.mark.asyncio
async def test_the_batched_tick_tells_everyone_exactly_what_one_dispatch_per_pot_did(factory, monkeypatch):
    async with factory() as s:
        seed = _Seeder(s)
        # Every channel at its default (all three on for this event), Spanish, two browsers.
        ana = await seed.user("ana", settings={"language": "es"})
        await seed.browser(ana, "ana-laptop")
        await seed.browser(ana, "ana-phone")
        # Email off; on the daily digest, which therefore queues nothing for them.
        ben = await seed.user("ben", settings={"notification_email_cadence": "daily"})
        await seed.preference(ben, "email", enabled=False)
        # On the daily digest with email on: the row is queued and no email goes now. Pushed at once.
        cai = await seed.user("cai", settings={"notification_email_cadence": "daily"})
        await seed.browser(cai, "cai-phone")
        # Every channel off: no row at all.
        dov = await seed.user("dov")
        for channel in ("in_app", "email", "push"):
            await seed.preference(dov, channel, enabled=False)
        # The feed off: the row is still written (it is the dedupe record), and the email still goes.
        eli = await seed.user("eli")
        await seed.preference(eli, "in_app", enabled=False)
        # Can see every pot, can write none: never reminded.
        fay = await seed.user("fay")

        home = await seed.group(f"{_PREFIX}Casa", ana)
        trip = await seed.group(f"{_PREFIX}Viaje", cai)
        ana_m, ben_m, cai_h, fay_m = [await seed.member(home, u) for u in (ana, ben, cai, fay)]
        cai_t, dov_t, eli_t = [await seed.member(trip, u) for u in (cai, dov, eli)]
        depto = await seed.pot(home, "Depto", creator=ana, writers=[ana_m, ben_m], viewers=[fay_m])
        auto = await seed.pot(home, None, creator=ana, writers=[ana_m, cai_h])
        hotel = await seed.pot(trip, "Hotel", creator=cai, writers=[dov_t])
        await seed.pot(trip, "Fresco", creator=cai, writers=[eli_t], fresh=True)
        semanal = await seed.pot(trip, "Semanal", creator=cai, writers=[eli_t, cai_t], cadence="weekly")
        await s.commit()

    def payload(group_id, group, pot_id, pot) -> dict:
        return {"group_id": group_id, "group": group, "pot_id": pot_id, "pot": pot, "valued_as_of": None}

    # Ana and Cai were already told about the nameless pot this month: the index refuses both repeats.
    # For Ana it is her LATER item (Depto comes first and is written); for Cai it is the EARLIER one, and
    # his later item (Semanal) must still be written and delivered — one recipient, a refused item before
    # a written one, in one batch.
    already_sent = [
        (ana, f"pot:{auto}:2026-09", payload(home, f"{_PREFIX}Casa", auto, None)),
        (cai, f"pot:{auto}:2026-09", payload(home, f"{_PREFIX}Casa", auto, None)),
    ]
    capture = _Capture(monkeypatch)

    await _rewind(factory, already_sent)
    async with factory() as session:
        told_batched = await pot_reminder_service.send_due_reminders(session, _TICK)
    batched = await capture.snapshot(factory)

    capture.reset()
    await _rewind(factory, already_sent)
    told_sequential = 0
    for pot_id, group_id, group, name, writers, key in [
        (depto, home, f"{_PREFIX}Casa", "Depto", [ana, ben], "2026-09"),
        (auto, home, f"{_PREFIX}Casa", None, [ana, cai], "2026-09"),
        (hotel, trip, f"{_PREFIX}Viaje", "Hotel", [dov], "2026-09"),
        (semanal, trip, f"{_PREFIX}Viaje", "Semanal", [cai, eli], "2026-W36"),
    ]:
        told_sequential += await notification_service.dispatch(
            NotificationEvent.snapshot_due, writers, payload(group_id, group, pot_id, name), dedupe_key=f"pot:{pot_id}:{key}"
        )
    sequential = await capture.snapshot(factory)

    print(f"\nequivalence population: {({k: len(v) for k, v in batched.items()}, told_batched)}")
    assert batched == sequential
    assert told_batched == told_sequential
    # The fixture reached what it was built to reach: the deduped repeat, the queued digest, the
    # feed-off row, both of Ana's browsers, and nobody who cannot write or wants nothing.
    emails = {row[0] for row in batched["rows"]}
    assert len([row for row in batched["rows"] if row[0].startswith(f"{_PREFIX}ana")]) == 2
    assert any(pending for *_, pending in batched["rows"])
    assert f"{_PREFIX}eli@test.local" in emails
    assert not {f"{_PREFIX}dov@test.local", f"{_PREFIX}fay@test.local"} & emails
    assert len(batched["stamped"]) == 3
    assert told_batched == 4
    # Held absolutely too, not only against the sequential half (which runs the same delivery code): the
    # repeat Ana was refused reaches none of her channels.
    about_auto = f'"pot_id": {auto}'
    assert not [sent for sent in batched["emails"] + batched["pushes"] if ("ana" in sent[0] or "cai" in sent[0]) and about_auto in sent[2]]
    # And Cai's later item, after his refused one, still reached him: its row (queued for his digest) and
    # its push, and nothing else new.
    semanal_key = f"pot:{semanal}:2026-W36"
    cai_rows = [row for row in batched["rows"] if row[0] == f"{_PREFIX}cai@test.local"]
    assert sorted(row[3] for row in cai_rows) == sorted([f"pot:{auto}:2026-09", semanal_key])
    assert [(row[2], row[4]) for row in cai_rows if row[3] == semanal_key] == [
        (json.dumps(payload(trip, f"{_PREFIX}Viaje", semanal, "Semanal"), sort_keys=True), True)
    ]
    assert [sent[2] for sent in batched["pushes"] if "cai" in sent[0]] == [
        json.dumps(payload(trip, f"{_PREFIX}Viaje", semanal, "Semanal"), sort_keys=True)
    ]
