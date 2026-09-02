from app import scheduler as scheduler_module

# Unit coverage for the scheduler misfire/coalesce policy + the month-end startup catch-up job
# (P08 perf). add_job is recorded so the config is asserted without starting a real event-loop
# scheduler.


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
        assert len(recorder.calls) == 7
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
        assert job[2]["minute"] == 0 and "hour" not in job[2]
