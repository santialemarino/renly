# Web push: VAPID authentication (RFC 8292) plus aes128gcm payload encryption (RFC 8291/8188), sent
# over the app's existing async HTTP client.
#
# Written against the specifications rather than pulled in as a dependency, and that is a deliberate
# trade rather than a preference for hand-rolling. The usual library is synchronous — it would put the
# only blocking HTTP client in an otherwise fully async service, dragged in for one POST — while the
# three primitives this actually needs (ECDH, HKDF, AES-128-GCM) are already present via cryptography,
# and python-jose already signs the app's own tokens. The decisive half is that RFC 8291 §5 publishes a
# complete worked example with fixed keys and a fixed salt, so this implementation is pinned to the
# specification's own vector in tests/unit/test_web_push.py — which is stronger evidence than a
# dependency's version number.
#
# There is no third-party service and no standing cost: the browser's own push service (Google,
# Mozilla, Apple) is the endpoint, and VAPID is how it knows the message is from us.
#
# The subscription's p256dh and auth are SECRETS. Nothing in this module logs a subscription, an
# endpoint or a key; failures are logged by status code and nothing else.

import base64
import json
import logging
import os
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from jose import jwt

from app.config import settings

logger = logging.getLogger(__name__)

# How long a browser's push service should hold the message if the browser is offline. Four weeks is
# the common ceiling; a notification about last month's expense is still the truth about last month.
_TTL_SECONDS = 60 * 60 * 24 * 28
# VAPID tokens are minted per send and must not outlive the day (RFC 8292 caps them at 24h). Twelve
# hours keeps a captured header short-lived while leaving room for any clock skew at either end.
_VAPID_TOKEN_TTL_SECONDS = 60 * 60 * 12
_SEND_TIMEOUT_SECONDS = 10.0
# The record size the payload is sealed into. One record is enough for every message Renly sends; the
# field exists because RFC 8188 supports chunking, which nothing here needs.
_RECORD_SIZE = 4096
# Fixed strings from RFC 8291 §3.4 and RFC 8188 §2.2. The trailing NUL is part of each info string.
_KEY_INFO_PREFIX = b"WebPush: info\x00"
_CEK_INFO = b"Content-Encoding: aes128gcm\x00"
_NONCE_INFO = b"Content-Encoding: nonce\x00"
# RFC 8188 §2: the last record's plaintext ends with 0x02; earlier records would end with 0x01.
_LAST_RECORD_DELIMITER = b"\x02"
_UNCOMPRESSED_POINT_LENGTH = 65
# The push service says the subscription is gone with one of these, and it is the only response worth
# acting on: the browser has revoked it or been reinstalled, so the row is dead and is deleted.
_GONE_STATUSES = frozenset({404, 410})


# One browser to send to. A plain value object rather than the model, so this module never touches the
# database and can be driven straight from the RFC's example keys in a test.
@dataclass(frozen=True)
class PushTarget:
    endpoint: str
    p256dh: str
    auth: str


# base64url without padding, which is the encoding every value in this protocol uses.
def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


# Decodes base64url that may or may not carry its padding — browsers send it without, tooling with.
def _unb64(value: str) -> bytes:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded)


# The configured VAPID private key, or None when push is not configured on this deployment.
#
# The PUBLIC key is never configured: it is derived from this one on demand (see public_key). A pair
# read from two env vars can be mismatched, and the failure is invisible — every browser subscribes
# happily against the wrong applicationServerKey and every send is then rejected by the push service.
# Deriving removes that state from existing.
def _private_key() -> ec.EllipticCurvePrivateKey | None:
    raw = settings.vapid_private_key
    if not raw:
        return None
    return ec.derive_private_key(int.from_bytes(_unb64(raw), "big"), ec.SECP256R1())


# The uncompressed P-256 point a public key encodes to — the 65-byte form this protocol uses
# everywhere: the browser's key, ours, and the `k=` parameter of the Authorization header.
def _point(key: ec.EllipticCurvePublicKey) -> bytes:
    return key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


# Whether this deployment can send push at all. False with no key configured, which is the default —
# local dev and tests send nothing, exactly as Sentry stays inert without a DSN.
def is_configured() -> bool:
    return bool(settings.vapid_private_key)


# The applicationServerKey the browser needs, base64url-encoded, or None when push is not configured.
# Derived from the private key, so the two can never disagree.
def public_key() -> str | None:
    private = _private_key()
    return None if private is None else _b64(_point(private.public_key()))


# Encrypts one payload for one subscription, returning the aes128gcm body of RFC 8188 §2.1:
#   salt (16) | record size (4, big-endian) | key id length (1) | our public key (65) | ciphertext
#
# `salt` and `ephemeral_key` are injectable ONLY so the RFC's worked example can be reproduced exactly;
# every real send generates both fresh, and reusing a salt with a key would be a genuine break.
def encrypt(payload: bytes, target: PushTarget, *, salt: bytes | None = None, ephemeral_key: ec.EllipticCurvePrivateKey | None = None) -> bytes:
    salt = salt or os.urandom(16)
    ephemeral_key = ephemeral_key or ec.generate_private_key(ec.SECP256R1())
    ua_point = _unb64(target.p256dh)
    ua_public = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_point)
    as_point = _point(ephemeral_key.public_key())

    shared = ephemeral_key.exchange(ec.ECDH(), ua_public)
    # RFC 8291 §3.4: the auth secret salts the first derivation and the two public keys are the info,
    # which is what binds the result to this exact pair of parties.
    ikm = HKDF(algorithm=SHA256(), length=32, salt=_unb64(target.auth), info=_KEY_INFO_PREFIX + ua_point + as_point).derive(shared)
    cek = HKDF(algorithm=SHA256(), length=16, salt=salt, info=_CEK_INFO).derive(ikm)
    nonce = HKDF(algorithm=SHA256(), length=12, salt=salt, info=_NONCE_INFO).derive(ikm)

    ciphertext = AESGCM(cek).encrypt(nonce, payload + _LAST_RECORD_DELIMITER, None)
    return salt + _RECORD_SIZE.to_bytes(4, "big") + bytes([_UNCOMPRESSED_POINT_LENGTH]) + as_point + ciphertext


# The Authorization header value proving the message is from this deployment (RFC 8292).
#
# `aud` is the push service's ORIGIN and nothing more of the endpoint — the rest of the URL is the
# subscription itself, and signing it would let the service correlate our tokens with individual
# browsers. `sub` is a contact the service can reach if we misbehave; it defaults to the app's own
# public URL, which is a valid subject and cannot go stale the way a hard-coded address would.
def _authorization(endpoint: str, private: ec.EllipticCurvePrivateKey, *, now: int | None = None) -> str:
    parsed = urlparse(endpoint)
    claims = {
        "aud": f"{parsed.scheme}://{parsed.netloc}",
        "exp": (now if now is not None else int(time.time())) + _VAPID_TOKEN_TTL_SECONDS,
        "sub": settings.vapid_subject or settings.web_base_url,
    }
    pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    token = jwt.encode(claims, pem, algorithm="ES256")
    return f"vapid t={token},k={_b64(_point(private.public_key()))}"


# Sends one notification to one browser.
#
# Returns True when the push service accepted it, False otherwise — and `gone` in the result is the
# only failure the caller acts on: 404/410 means the browser revoked the subscription or was
# reinstalled, so the row is dead and the caller deletes it. Everything else (a rate limit, an outage)
# is transient and the subscription stays.
#
# Never raises. A push is best-effort by nature: the notification is already in the recipient's feed,
# and a push service being down must not fail the request that produced it.
async def send(client: httpx.AsyncClient, target: PushTarget, payload: dict) -> tuple[bool, bool]:
    private = _private_key()
    if private is None:
        return (False, False)
    try:
        body = encrypt(json.dumps(payload).encode(), target)
        response = await client.post(
            target.endpoint,
            content=body,
            headers={
                "Authorization": _authorization(target.endpoint, private),
                "Content-Encoding": "aes128gcm",
                "Content-Type": "application/octet-stream",
                "TTL": str(_TTL_SECONDS),
            },
            timeout=_SEND_TIMEOUT_SECONDS,
        )
    except Exception:
        # No endpoint and no keys in the message: a push subscription is a credential.
        logger.warning("Web push send failed before a response was received.", exc_info=True)
        return (False, False)
    if response.is_success:
        return (True, False)
    gone = response.status_code in _GONE_STATUSES
    if not gone:
        logger.warning("Web push rejected with status %d.", response.status_code)
    return (False, gone)
