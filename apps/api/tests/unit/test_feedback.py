import pytest
from pydantic import ValidationError

from app.models.feedback import Feedback, FeedbackCategory
from app.models.user import User
from app.schemas.feedback import FeedbackCreate
from app.services import feedback_service, settings_service

# Coverage for the in-app feedback channel (SHELL-7): request-body validation (category + message
# bounds), and the service flow — store the row, then notify every admin by email best-effort (an
# email outage never fails the submission). Repositories + the email provider are faked (no DB /
# network).


# --- Schema validation ---


class TestFeedbackCreateSchema:
    def test_accepts_a_valid_body_and_strips_the_message(self):
        body = FeedbackCreate(category=FeedbackCategory.bug, message="  Something is off  ")
        assert body.category == FeedbackCategory.bug
        assert body.message == "Something is off"  # RequestBase strips (mode="before")

    def test_rejects_an_empty_or_whitespace_message(self):
        with pytest.raises(ValidationError):
            FeedbackCreate(category=FeedbackCategory.idea, message="")
        with pytest.raises(ValidationError):
            FeedbackCreate(category=FeedbackCategory.idea, message="   ")  # stripped to "" → min_length

    def test_rejects_a_message_over_the_cap(self):
        with pytest.raises(ValidationError):
            FeedbackCreate(category=FeedbackCategory.other, message="x" * 2001)

    def test_rejects_an_unknown_category(self):
        with pytest.raises(ValidationError):
            FeedbackCreate(category="complaint", message="Anything")


# --- Service flow (faked repos + email) ---


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1

    async def flush(self) -> None:
        return None


class FakeFeedbackRepo:
    def __init__(self, rows: list[tuple[Feedback, str]] | None = None) -> None:
        self.created: list[Feedback] = []
        self.rows = rows or []
        self._next_id = 1

    async def list_all_with_email(self, session):
        return self.rows

    async def create(self, session, feedback):
        feedback.id = self._next_id
        self._next_id += 1
        self.created.append(feedback)
        return feedback


class FakeUserRepo:
    def __init__(self, admin_emails: list[str]) -> None:
        # Build admin User rows (id + email) — the service resolves each admin's language by id.
        self.admins = [User(id=i + 1, name=f"Admin {i + 1}", email=email, password_hash="h", is_admin=True) for i, email in enumerate(admin_emails)]

    async def list_admins(self, session):
        return self.admins


# Language stub: every admin resolves to English (the localization itself is covered in
# test_email_service.py; here we only need the notification flow not to hit the real settings repo).
async def _langs_en(session, user_ids):
    return {user_id: "en" for user_id in user_ids}


class FakeEmailService:
    def __init__(self, fail_for: set[str] | None = None) -> None:
        self.sent = []
        self.fail_for = fail_for or set()

    async def send(self, message) -> None:
        if message.to in self.fail_for:
            raise RuntimeError("provider down")
        self.sent.append(message)


@pytest.fixture
def wired(monkeypatch):
    feedback_repo = FakeFeedbackRepo()
    user_repo = FakeUserRepo(admin_emails=["a@example.com", "b@example.com"])
    email = FakeEmailService()
    monkeypatch.setattr(feedback_service, "feedback_repository", feedback_repo)
    monkeypatch.setattr(feedback_service, "user_repository", user_repo)
    monkeypatch.setattr(feedback_service, "get_email_service", lambda: email)
    monkeypatch.setattr(settings_service, "get_languages_by_user_ids", _langs_en)
    return feedback_repo, user_repo, email


def _user() -> User:
    return User(id=42, name="Sender", email="sender@example.com", password_hash="h")


class TestCreateFeedback:
    @pytest.mark.asyncio
    async def test_stores_the_row_commits_and_returns_it(self, wired):
        feedback_repo, _users, _email = wired
        session = FakeSession()
        data = FeedbackCreate(category=FeedbackCategory.bug, message="It broke")

        result = await feedback_service.create_feedback(session, FakeSession(), _user(), data)

        assert len(feedback_repo.created) == 1
        stored = feedback_repo.created[0]
        assert stored.user_id == 42 and stored.category == FeedbackCategory.bug and stored.message == "It broke"
        assert session.commits == 1
        assert result.id == stored.id and result.category == FeedbackCategory.bug and result.message == "It broke"

    @pytest.mark.asyncio
    async def test_notifies_every_admin_with_the_submitter_and_message(self, wired):
        _feedback_repo, _users, email = wired
        data = FeedbackCreate(category=FeedbackCategory.idea, message="Add dark mode")

        await feedback_service.create_feedback(FakeSession(), FakeSession(), _user(), data)

        assert {m.to for m in email.sent} == {"a@example.com", "b@example.com"}
        body = email.sent[0]
        assert "sender@example.com" in body.text and "Add dark mode" in body.text and "Idea" in body.subject

    @pytest.mark.asyncio
    async def test_email_failure_does_not_break_submission(self, monkeypatch):
        feedback_repo = FakeFeedbackRepo()
        monkeypatch.setattr(feedback_service, "feedback_repository", feedback_repo)
        monkeypatch.setattr(feedback_service, "user_repository", FakeUserRepo(["a@example.com", "b@example.com"]))
        monkeypatch.setattr(settings_service, "get_languages_by_user_ids", _langs_en)
        # First admin's send raises; the request must still succeed and the other admin still gets it.
        email = FakeEmailService(fail_for={"a@example.com"})
        monkeypatch.setattr(feedback_service, "get_email_service", lambda: email)

        result = await feedback_service.create_feedback(
            FakeSession(), FakeSession(), _user(), FeedbackCreate(category=FeedbackCategory.other, message="hi")
        )

        assert result.id is not None and len(feedback_repo.created) == 1
        assert [m.to for m in email.sent] == ["b@example.com"]  # the surviving send went through

    @pytest.mark.asyncio
    async def test_no_admins_stores_without_sending(self, monkeypatch):
        feedback_repo = FakeFeedbackRepo()
        monkeypatch.setattr(feedback_service, "feedback_repository", feedback_repo)
        monkeypatch.setattr(feedback_service, "user_repository", FakeUserRepo([]))
        email = FakeEmailService()
        monkeypatch.setattr(feedback_service, "get_email_service", lambda: email)

        result = await feedback_service.create_feedback(
            FakeSession(), FakeSession(), _user(), FeedbackCreate(category=FeedbackCategory.bug, message="hi")
        )

        assert result.id is not None and len(feedback_repo.created) == 1 and email.sent == []


class TestListFeedback:
    @pytest.mark.asyncio
    async def test_maps_rows_to_admin_responses_with_email(self, monkeypatch):
        rows = [
            (Feedback(id=2, user_id=5, category=FeedbackCategory.bug, message="second"), "b@example.com"),
            (Feedback(id=1, user_id=9, category=FeedbackCategory.idea, message="first"), "c@example.com"),
        ]
        monkeypatch.setattr(feedback_service, "feedback_repository", FakeFeedbackRepo(rows=rows))

        result = await feedback_service.list_feedback(FakeSession())

        assert [(r.id, r.email, r.message) for r in result] == [
            (2, "b@example.com", "second"),
            (1, "c@example.com", "first"),
        ]
