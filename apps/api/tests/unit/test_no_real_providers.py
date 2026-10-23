import httpx
import pytest

from app.services import web_push
from app.services.email_service import ConsoleEmailService, EmailMessage, ResendEmailService, get_email_service

# The suite-wide guard in tests/conftest.py, shown to hold: whatever `.env` says, the app's email adapter
# is the console one, and a request that would reach a real provider is refused AND recorded — the record
# being what fails the test at teardown, since the code it is refused inside swallows the refusal. The
# hosts are `.invalid`, so even with the guard removed nothing here could reach a real service.

_MESSAGE = EmailMessage(to="nobody@test.local", subject="s", html="<p>h</p>", text="h")


class TestNoTestReachesARealProvider:
    def test_the_email_adapter_is_the_console_one(self):
        assert isinstance(get_email_service(), ConsoleEmailService)

    # A real Resend send, as the adapter makes it: refused, recorded, and the record then emptied so this
    # test (which means to make the attempt) is not itself failed by the guard.
    @pytest.mark.asyncio
    async def test_a_real_email_send_is_refused_and_recorded(self, monkeypatch, no_real_provider):
        monkeypatch.setattr(ResendEmailService, "_API_URL", "https://resend.invalid/emails")
        with pytest.raises(httpx.ConnectError):
            await ResendEmailService(api_key="re_test", sender="Renly <noreply@renly.app>").send(_MESSAGE)
        assert no_real_provider.attempts == ["POST https://resend.invalid/emails"]
        no_real_provider.attempts.clear()

    # A real web push through a real client: web_push.send swallows the failure and reports "not sent, not
    # gone", so the record is the only trace — exactly the case the teardown assertion exists for.
    @pytest.mark.asyncio
    async def test_a_real_push_is_refused_and_recorded(self, monkeypatch, no_real_provider):
        monkeypatch.setattr(web_push.settings, "vapid_private_key", "8k-gkNejcLRJJwv7K8TnrWveF1NIlnwK9TpJKQQPfIE")
        target = web_push.PushTarget(
            endpoint="https://push.invalid/subscription/abc",
            p256dh="BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4",
            auth="BTBZMqHH6r4Tts7J_aSIgg",
        )
        async with httpx.AsyncClient() as client:
            assert await web_push.send(client, target, {"title": "t", "body": "b", "url": "u"}) == (False, False)
        assert no_real_provider.attempts == ["POST https://push.invalid/subscription/abc"]
        no_real_provider.attempts.clear()
