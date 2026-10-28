import ast
import asyncio
import logging
from datetime import UTC, datetime, timedelta

import pytest
from apscheduler.events import EVENT_JOB_ERROR
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app import scheduler as scheduler_module
from tests.unit.test_in_chunking import scheduler_walk

# Unit coverage for the scheduler misfire/coalesce policy, the month-end startup catch-up job (P08
# perf) and the staggered start times (U18). add_job is recorded so the config is asserted without starting a real event-loop
# scheduler.

# The add_job keyword arguments that are CronTrigger fields (the rest are job options).
_CRON_FIELDS = {"year", "month", "day", "week", "day_of_week", "hour", "minute", "second"}


# Records add_job calls so tests assert scheduling config without starting a real event-loop scheduler.
class _AddJobRecorder:
    def __init__(self):
        self.calls: list[tuple] = []
        self.listeners: list[tuple] = []

    def __call__(self, func, trigger=None, **kwargs):
        self.calls.append((func, trigger, kwargs))


class TestSchedulerConfig:
    def _record(self, monkeypatch) -> _AddJobRecorder:
        recorder = _AddJobRecorder()
        monkeypatch.setattr(scheduler_module.scheduler, "add_job", recorder)
        monkeypatch.setattr(scheduler_module.scheduler, "add_listener", lambda callback, mask: recorder.listeners.append((callback, mask)))
        monkeypatch.setattr(scheduler_module.scheduler, "start", lambda: None)
        scheduler_module.start_scheduler()
        return recorder

    # The scheduler runs in UTC so the *_HOUR_UTC cron hours fire at those UTC hours on any host.
    def test_scheduler_timezone_is_utc(self):
        assert str(scheduler_module.scheduler.timezone) == "UTC"

    # Every job must survive a late tick: hours-scale grace, coalesced to a single run.
    def test_all_jobs_have_misfire_grace_and_coalesce(self, monkeypatch):
        recorder = self._record(monkeypatch)
        assert len(recorder.calls) == 9
        for _func, _trigger, kwargs in recorder.calls:
            assert kwargs["misfire_grace_time"] == scheduler_module.MISFIRE_GRACE_SECONDS
            assert kwargs["coalesce"] is True

    # The one-shot month-end catch-up job is scheduled at startup.
    def test_startup_catchup_job_scheduled(self, monkeypatch):
        recorder = self._record(monkeypatch)
        ids = {kwargs["id"] for _f, _t, kwargs in recorder.calls}
        assert "auto_snapshots_startup_catchup" in ids

    # The overdue-valuation reminder runs HOURLY, and that is the whole reason it can fire at each
    # person's own local morning: the service filters the tick to the users whose local hour matches,
    # exactly as the auto-expense job does. A daily cron here would pick one global hour and be wrong
    # for everybody outside it.
    def test_the_pot_reminder_runs_hourly_so_it_can_follow_each_persons_clock(self, monkeypatch):
        recorder = self._record(monkeypatch)
        job = next(call for call in recorder.calls if call[2]["id"] == "send_pot_reminders")
        assert job[1] == "cron"
        assert job[2]["minute"] == scheduler_module.POT_REMINDERS_MINUTE and "hour" not in job[2]

    # The same rule, asserted over EVERY per-user-local-hour job rather than once per job. Each of these
    # picks its recipients by comparing the tick to a person's own clock, which only works if the tick
    # comes round every hour — pin an `hour` on any of them and it fires for one timezone and silently
    # never for the rest. A set difference, so a fourth such job added later is covered by being named
    # here rather than by somebody remembering to copy a test.
    def test_every_per_user_local_hour_job_runs_hourly(self, monkeypatch):
        recorder = self._record(monkeypatch)
        by_id = {kwargs["id"]: (trigger, kwargs) for _f, trigger, kwargs in recorder.calls}
        local_hour_jobs = {"generate_auto_expenses", "send_pot_reminders", "send_obligation_reminders", "send_notification_digests"}
        assert local_hour_jobs - set(by_id) == set()
        for job_id in local_hour_jobs:
            trigger, kwargs = by_id[job_id]
            assert trigger == "cron", job_id
            assert isinstance(kwargs["minute"], int) and "hour" not in kwargs, job_id

    # The digest runs LATER in the day than the two reminder jobs, and that ordering is the whole reason
    # a reminder raised this morning lands in tonight's summary rather than tomorrow's. All three filter
    # on the SAME person's local clock, so the comparison holds in every timezone — which is what makes
    # it assertable as a plain inequality between three constants rather than as job registration order.
    def test_the_digest_is_sent_after_the_days_reminders_are_raised(self):
        from app.services import notification_digest_service, obligation_reminder_service, pot_reminder_service

        assert notification_digest_service.DIGEST_HOUR_LOCAL > obligation_reminder_service.OBLIGATION_REMINDER_HOUR_LOCAL
        assert notification_digest_service.DIGEST_HOUR_LOCAL > pot_reminder_service.SNAPSHOT_REMINDER_HOUR_LOCAL

    # No two cron jobs ever start in the same minute (U18): every job opens a session on the small admin
    # pool, and four hourly jobs firing together at minute 0 measured a peak of 4 checkouts out of 5.
    # Derived from what start_scheduler registers, not from a list: each cron job's real CronTrigger is
    # walked across 40 days starting on a month's last day (so the month-end and the 1st-of-month jobs
    # fire inside the window) and every fire time must belong to exactly one job.
    def test_no_two_cron_jobs_start_in_the_same_minute(self, monkeypatch):
        recorder = self._record(monkeypatch)
        cron_jobs = {kwargs["id"]: kwargs for _f, trigger, kwargs in recorder.calls if trigger == "cron"}
        print(f"cron jobs checked: {sorted(cron_jobs)}")
        assert len(cron_jobs) >= 7

        start = datetime(2026, 1, 31, tzinfo=UTC)
        end = start + timedelta(days=40)
        fired_by: dict[datetime, str] = {}
        for job_id, kwargs in cron_jobs.items():
            fields = {k: v for k, v in kwargs.items() if k in _CRON_FIELDS}
            trigger = CronTrigger(timezone=UTC, **fields)
            fire = trigger.get_next_fire_time(None, start)
            fires = 0
            while fire is not None and fire < end:
                assert fire not in fired_by, f"{job_id} and {fired_by.get(fire)} both start at {fire.isoformat()}"
                fired_by[fire] = job_id
                fires += 1
                fire = trigger.get_next_fire_time(fire, fire + timedelta(seconds=1))
            assert fires > 0, f"{job_id} never fired inside the window, so the check proved nothing for it"


# U19: a job's failure is reported by the scheduler, once, rather than swallowed inside the job. The
# auto-snapshot job failed identically on every run once its reads passed the bind-parameter cap, and its
# wrapper turned that into one routine "failed" log line a month.
class _Boom(Exception):
    pass


# Stands in for AdminSessionLocal: opening the session raises, as a dead database would.
class _RaisingSession:
    async def __aenter__(self):
        raise _Boom("database unreachable")

    async def __aexit__(self, *exc):
        return False


class TestJobFailuresAreReported:
    # Every registered job lets its exception out, so APScheduler sees it — derived from what
    # start_scheduler registers, so a new job that swallows again fails here.
    @pytest.mark.asyncio
    async def test_no_job_swallows_its_exception(self, monkeypatch):
        recorder = TestSchedulerConfig()._record(monkeypatch)
        monkeypatch.setattr(scheduler_module, "AdminSessionLocal", _RaisingSession)
        assert len(recorder.calls) == 9
        for func, _trigger, _kwargs in recorder.calls:
            with pytest.raises(_Boom):
                await func()

    # The report is wired to APScheduler's own error event, on the scheduler the app starts.
    def test_the_failure_listener_is_registered(self, monkeypatch):
        recorder = TestSchedulerConfig()._record(monkeypatch)
        assert recorder.listeners == [(scheduler_module._report_job_failure, EVENT_JOB_ERROR)]

    # End to end on a real scheduler: a raising job reaches the listener, which logs it at CRITICAL with
    # the job's id and the prefix an alert keys on, and the scheduler keeps running.
    @pytest.mark.asyncio
    async def test_a_raising_job_is_logged_critical_with_its_id(self, caplog):
        async def failing_job():
            raise _Boom("past the cap")

        scheduler = AsyncIOScheduler(timezone="UTC")
        scheduler.add_listener(scheduler_module._report_job_failure, EVENT_JOB_ERROR)
        scheduler.add_job(failing_job, "date", run_date=datetime.now(UTC), id="u19_failing_job")
        with caplog.at_level(logging.CRITICAL, logger=scheduler_module.logger.name):
            scheduler.start()
            for _ in range(50):
                if any(r.levelno == logging.CRITICAL for r in caplog.records):
                    break
                await asyncio.sleep(0.02)
            assert scheduler.running
            scheduler.shutdown(wait=False)
        critical = [r for r in caplog.records if r.levelno == logging.CRITICAL]
        assert len(critical) == 1
        assert critical[0].getMessage().startswith("SCHEDULED JOB FAILED: u19_failing_job")
        assert isinstance(critical[0].exc_info[1], _Boom)

    # U20: a job's notification dispatch raises into the job only when the job passes its own session —
    # without one, dispatch opens its own and swallows, and the failure never reaches the listener above.
    # Derived from the scheduler's call graph (tests/unit/test_in_chunking.py's walk): every dispatch a
    # job can reach, outside the notification layer itself, passes `session=` — and passes a session:
    # `session=None` is the keyword with the swallowing path behind it, so it counts as not passing one.
    def test_every_dispatch_a_job_reaches_passes_the_jobs_session(self):
        calls = [
            (name, node)
            for name, fn in scheduler_walk().items()
            if not name.startswith("notification_service.")
            for node in ast.walk(fn)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and getattr(node.func.value, "id", None) == "notification_service"
            and node.func.attr in {"dispatch", "dispatch_many"}
        ]
        print(f"\nscheduled dispatch call sites: {sorted(name for name, _ in calls)}")
        assert len(calls) >= 3
        no_session = [
            name
            for name, node in calls
            if not any(kw.arg == "session" and not (isinstance(kw.value, ast.Constant) and kw.value.value is None) for kw in node.keywords)
        ]
        assert no_session == []


# Stands in for AdminSessionLocal when a job's body is driven with its service faked.
class _InertSession:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *exc):
        return False


# U25: the month-end auto-snapshot schedule, and the startup catch-up's idea of when that schedule last
# fired. The no-overlap test above walks this job's trigger but only asks that it collide with nothing —
# moving it to the 28th, or to another hour, passed. Each month's valuation is the one the evolution chart
# carries for that month, so a run on the 28th dates it days early and a month whose last day is the 31st
# misses its last three days of prices.
class TestTheMonthEndAutoSnapshot:
    # Fires on every month's LAST day — 28, 29, 30 or 31 — at AUTO_SNAPSHOTS_HOUR_UTC, and on no other day.
    # Walked across fourteen months that include a leap February.
    def test_it_fires_on_the_last_day_of_every_month_and_only_then(self, monkeypatch):
        recorder = TestSchedulerConfig()._record(monkeypatch)
        _func, trigger, kwargs = next(call for call in recorder.calls if call[2]["id"] == "generate_auto_snapshots")
        assert trigger == "cron"
        cron = CronTrigger(timezone=UTC, **{k: v for k, v in kwargs.items() if k in _CRON_FIELDS})
        fires = []
        fire = cron.get_next_fire_time(None, datetime(2027, 12, 1, tzinfo=UTC))
        while fire is not None and fire < datetime(2029, 2, 1, tzinfo=UTC):
            fires.append(fire)
            fire = cron.get_next_fire_time(fire, fire + timedelta(seconds=1))
        last_days = [
            (2027, 12, 31), (2028, 1, 31), (2028, 2, 29), (2028, 3, 31), (2028, 4, 30), (2028, 5, 31), (2028, 6, 30),
            (2028, 7, 31), (2028, 8, 31), (2028, 9, 30), (2028, 10, 31), (2028, 11, 30), (2028, 12, 31), (2029, 1, 31),
        ]  # fmt: skip
        assert fires == [datetime(y, m, d, scheduler_module.AUTO_SNAPSHOTS_HOUR_UTC, tzinfo=UTC) for y, m, d in last_days]

    # The catch-up decides "the month-end tick was missed" by rebuilding that tick's time, so it must be
    # handed the hour the cron really fires at — read off what start_scheduler registers rather than off
    # the constant both happen to name today.
    @pytest.mark.asyncio
    async def test_the_startup_catch_up_rebuilds_the_tick_the_cron_fires_at(self, monkeypatch):
        recorder = TestSchedulerConfig()._record(monkeypatch)
        cron_hour = next(kwargs["hour"] for _f, _t, kwargs in recorder.calls if kwargs["id"] == "generate_auto_snapshots")
        catch_up = next(func for func, _t, kwargs in recorder.calls if kwargs["id"] == "auto_snapshots_startup_catchup")
        seen: dict = {}

        async def recorded(_session, **kwargs):
            seen.update(kwargs)
            return False

        monkeypatch.setattr(scheduler_module, "AdminSessionLocal", _InertSession)
        monkeypatch.setattr(scheduler_module.auto_snapshot_service, "run_startup_catchup", recorded)
        await catch_up()
        assert seen == {"catchup_days": scheduler_module.AUTO_SNAPSHOTS_CATCHUP_DAYS, "snapshots_hour_utc": cron_hour}
