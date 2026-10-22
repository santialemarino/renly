from datetime import UTC, datetime, timedelta

from apscheduler.triggers.cron import CronTrigger

from app import scheduler as scheduler_module

# Unit coverage for the scheduler misfire/coalesce policy, the month-end startup catch-up job (P08
# perf) and the staggered start times (U18). add_job is recorded so the config is asserted without starting a real event-loop
# scheduler.

# The add_job keyword arguments that are CronTrigger fields (the rest are job options).
_CRON_FIELDS = {"year", "month", "day", "week", "day_of_week", "hour", "minute", "second"}


# Records add_job calls so tests assert scheduling config without starting a real event-loop scheduler.
class _AddJobRecorder:
    def __init__(self):
        self.calls: list[tuple] = []

    def __call__(self, func, trigger=None, **kwargs):
        self.calls.append((func, trigger, kwargs))


class TestSchedulerConfig:
    def _record(self, monkeypatch) -> _AddJobRecorder:
        recorder = _AddJobRecorder()
        monkeypatch.setattr(scheduler_module.scheduler, "add_job", recorder)
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
