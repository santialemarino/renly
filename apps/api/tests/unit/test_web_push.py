# Web push: the encryption, the VAPID header, and what the sender does with each answer.
#
# The encryption test is the one that matters and it is not a self-consistency check: RFC 8291 §5
# publishes a complete worked example — both key pairs, the auth secret, the salt and the expected
# ciphertext — so this asserts the implementation reproduces the specification byte for byte. That is
# the evidence that justified writing the encryption rather than adding a dependency for it.

import base64
from datetime import UTC, datetime

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from jose import jwt

from app.services import web_push

# RFC 8291 §5, verbatim.
_RFC_UA_PUBLIC = "BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4"
_RFC_AUTH = "BTBZMqHH6r4Tts7J_aSIgg"
_RFC_AS_PRIVATE = "yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw"
_RFC_SALT = "DGv6ra1nlYgDCS1FRnbzlw"
_RFC_PLAINTEXT = b"When I grow up, I want to be a watermelon"
_RFC_BODY = (
    "DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8wEqKK6PBru3jl7A_"
    "yl95bQpu6cVPTpK4Mqgkf1CXztLVBSt2Ks3oZwbuwXPXLWyouBWLVWGNWQexSgSxsj_Qulcy4a-fN"
)

# A key pair of our own, for the tests that are not about the RFC's vector.
_LOCAL_PRIVATE = "8k-gkNejcLRJJwv7K8TnrWveF1NIlnwK9TpJKQQPfIE"


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _point(key: ec.EllipticCurvePublicKey) -> bytes:
    return key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


def _target(endpoint: str = "https://push.example.net/subscription/abc") -> web_push.PushTarget:
    return web_push.PushTarget(endpoint=endpoint, p256dh=_RFC_UA_PUBLIC, auth=_RFC_AUTH)


class TestEncryption:
    def test_the_rfc_8291_worked_example_is_reproduced_byte_for_byte(self):
        ephemeral = ec.derive_private_key(int.from_bytes(_unb64(_RFC_AS_PRIVATE), "big"), ec.SECP256R1())
        body = web_push.encrypt(_RFC_PLAINTEXT, _target(), salt=_unb64(_RFC_SALT), ephemeral_key=ephemeral)
        assert base64.urlsafe_b64encode(body).rstrip(b"=").decode() == _RFC_BODY

    def test_the_header_carries_the_salt_the_record_size_and_our_own_public_key(self):
        # RFC 8188 §2.1's framing, asserted on the bytes rather than inferred: 16 salt, 4 record size,
        # 1 key-id length, then the 65-byte uncompressed point. A body whose header were laid out any
        # other way would decrypt to nothing in a browser and fail with no message anywhere.
        ephemeral = ec.generate_private_key(ec.SECP256R1())
        body = web_push.encrypt(b"hi", _target(), salt=b"0123456789abcdef", ephemeral_key=ephemeral)
        assert body[:16] == b"0123456789abcdef"
        assert int.from_bytes(body[16:20], "big") == 4096
        assert body[20] == 65
        assert body[21:86] == _point(ephemeral.public_key())

    def test_two_sends_of_the_same_payload_differ(self):
        # A fresh salt and a fresh ephemeral key per message. Identical ciphertext twice would mean one
        # of them is being reused, which is the one way this construction actually breaks.
        first = web_push.encrypt(b"same", _target())
        second = web_push.encrypt(b"same", _target())
        assert first != second

    def test_the_SALT_is_fresh_even_though_the_key_already_is(self):
        # Asserted on the first sixteen bytes rather than on the whole body, because a fresh ephemeral
        # key alone already makes two bodies differ — so the test above passes even with the salt pinned
        # to a constant, and this is what actually holds the salt to being random. A mutation sweep is
        # what found that; the test above had looked like coverage of both.
        salts = {web_push.encrypt(b"same", _target())[:16] for _ in range(5)}
        assert len(salts) == 5


class TestConfiguration:
    def test_no_key_means_push_is_off_rather_than_broken(self, monkeypatch):
        monkeypatch.setattr(web_push.settings, "vapid_private_key", None)
        assert web_push.is_configured() is False
        assert web_push.public_key() is None

    def test_the_public_key_is_derived_from_the_private_one(self, monkeypatch):
        # The property that removes a whole failure mode: there is no second setting to get wrong, so a
        # browser can never subscribe against a key this deployment cannot sign for.
        monkeypatch.setattr(web_push.settings, "vapid_private_key", _LOCAL_PRIVATE)
        derived = web_push.public_key()
        expected = ec.derive_private_key(int.from_bytes(_unb64(_LOCAL_PRIVATE), "big"), ec.SECP256R1()).public_key()
        assert _unb64(derived) == _point(expected)


class TestVapidHeader:
    def _claims(self, monkeypatch, endpoint: str) -> dict:
        monkeypatch.setattr(web_push.settings, "vapid_private_key", _LOCAL_PRIVATE)
        private = web_push._private_key()
        header = web_push._authorization(endpoint, private, now=1_700_000_000)
        token = header.removeprefix("vapid t=").split(",", 1)[0]
        return jwt.get_unverified_claims(token)

    def test_the_audience_is_the_push_services_origin_and_not_the_subscription(self, monkeypatch):
        # The rest of the endpoint IS the subscription. Signing it would let the push service correlate
        # our tokens with individual browsers, which is exactly what VAPID is not for.
        claims = self._claims(monkeypatch, "https://fcm.googleapis.com/fcm/send/abc123?x=1")
        assert claims["aud"] == "https://fcm.googleapis.com"

    def test_the_token_expires_within_a_day(self, monkeypatch):
        # RFC 8292 caps it at 24 hours and services reject anything longer, which fails every send.
        claims = self._claims(monkeypatch, "https://push.example.net/x")
        assert 0 < claims["exp"] - 1_700_000_000 <= 24 * 3600

    def test_the_subject_falls_back_to_the_apps_own_url(self, monkeypatch):
        monkeypatch.setattr(web_push.settings, "vapid_subject", None)
        monkeypatch.setattr(web_push.settings, "web_base_url", "https://renly.example")
        assert self._claims(monkeypatch, "https://push.example.net/x")["sub"] == "https://renly.example"

    def test_a_configured_subject_wins(self, monkeypatch):
        monkeypatch.setattr(web_push.settings, "vapid_subject", "mailto:ops@renly.example")
        assert self._claims(monkeypatch, "https://push.example.net/x")["sub"] == "mailto:ops@renly.example"

    def test_the_header_names_the_key_the_browser_subscribed_with(self, monkeypatch):
        monkeypatch.setattr(web_push.settings, "vapid_private_key", _LOCAL_PRIVATE)
        header = web_push._authorization("https://push.example.net/x", web_push._private_key())
        assert header.split(",k=")[1] == web_push.public_key()


class TestSend:
    async def _send(self, monkeypatch, handler) -> tuple[bool, bool]:
        monkeypatch.setattr(web_push.settings, "vapid_private_key", _LOCAL_PRIVATE)
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            return await web_push.send(client, _target(), {"title": "Casa", "body": "hi", "url": "/shared/1"})

    @pytest.mark.asyncio
    async def test_a_201_is_a_success_and_not_a_dead_subscription(self, monkeypatch):
        assert await self._send(monkeypatch, lambda _r: httpx.Response(201)) == (True, False)

    @pytest.mark.asyncio
    async def test_a_410_reports_the_subscription_gone_so_the_caller_deletes_it(self, monkeypatch):
        # The one failure worth acting on: the browser revoked it or was reinstalled, and retrying
        # forever would send to a dead endpoint on every event.
        assert await self._send(monkeypatch, lambda _r: httpx.Response(410)) == (False, True)

    @pytest.mark.asyncio
    async def test_a_404_is_treated_the_same_way(self, monkeypatch):
        assert await self._send(monkeypatch, lambda _r: httpx.Response(404)) == (False, True)

    @pytest.mark.asyncio
    async def test_a_rate_limit_is_a_failure_that_KEEPS_the_subscription(self, monkeypatch):
        # A transient answer must not cost somebody their subscription; only 404/410 mean gone.
        assert await self._send(monkeypatch, lambda _r: httpx.Response(429)) == (False, False)

    @pytest.mark.asyncio
    async def test_a_network_failure_is_swallowed(self, monkeypatch):
        # A push is best-effort: the notification is already in the recipient's feed, so an unreachable
        # push service must never surface to the request that produced the event.
        def _boom(_request):
            raise httpx.ConnectError("no route")

        assert await self._send(monkeypatch, _boom) == (False, False)

    @pytest.mark.asyncio
    async def test_an_unconfigured_deployment_sends_nothing_and_says_so(self, monkeypatch):
        monkeypatch.setattr(web_push.settings, "vapid_private_key", None)
        called = False

        def _handler(_request):
            nonlocal called
            called = True
            return httpx.Response(201)

        async with httpx.AsyncClient(transport=httpx.MockTransport(_handler)) as client:
            assert await web_push.send(client, _target(), {"title": "x", "body": "y", "url": "/"}) == (False, False)
        assert called is False

    @pytest.mark.asyncio
    async def test_the_request_carries_the_encoding_the_body_is_actually_in(self, monkeypatch):
        # aes128gcm, a TTL, and an Authorization header. A missing Content-Encoding is accepted by the
        # push service and then silently discarded by the browser, which is the worst failure shape
        # available — nothing anywhere reports it.
        seen: dict = {}

        def _handler(request: httpx.Request) -> httpx.Response:
            seen.update(request.headers)
            seen["body"] = request.content
            return httpx.Response(201)

        await self._send(monkeypatch, _handler)
        assert seen["content-encoding"] == "aes128gcm"
        assert seen["content-type"] == "application/octet-stream"
        assert int(seen["ttl"]) > 0
        assert seen["authorization"].startswith("vapid t=")
        # The body is the sealed record, so its first 16 bytes are a salt and it is longer than the
        # 86-byte header — never the plaintext JSON.
        assert len(seen["body"]) > 86 and b"Casa" not in seen["body"]


def test_the_vapid_token_verifies_against_the_public_key_the_browser_holds(monkeypatch):
    # End to end for the signature itself: a push service checks the token against the `k=` parameter,
    # so a token this key cannot verify is one every send is rejected for.
    monkeypatch.setattr(web_push.settings, "vapid_private_key", _LOCAL_PRIVATE)
    private = web_push._private_key()
    header = web_push._authorization("https://push.example.net/x", private, now=int(datetime.now(UTC).timestamp()))
    token, key = header.removeprefix("vapid t=").split(",k=")
    claims = jwt.decode(
        token,
        {
            "kty": "EC",
            "crv": "P-256",
            "x": base64.urlsafe_b64encode(_unb64(key)[1:33]).rstrip(b"=").decode(),
            "y": base64.urlsafe_b64encode(_unb64(key)[33:]).rstrip(b"=").decode(),
        },
        algorithms=["ES256"],
        options={"verify_aud": False},
    )
    assert claims["aud"] == "https://push.example.net"
