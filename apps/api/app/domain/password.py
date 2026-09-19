"""The ceiling bcrypt imposes on anything this app hashes."""

# bcrypt's own hard limit. It hashes at most 72 BYTES and, since 5.0, RAISES above that rather than
# truncating the way 4.x did — so any longer value reaching `hashpw`/`checkpw` is an unhandled
# ValueError, which the app answers as a 500.
#
# In `domain` rather than beside the request schemas because two different layers need it and neither
# owns it: the auth schemas cap every password field with it, and `api_key_service` caps the raw
# Bearer credential, which never passes through a schema at all. A constant defined in `schemas` and
# imported by a service would invert the dependency the layering rules set out.
MAX_PASSWORD_BYTES = 72


# Whether a value is short enough for bcrypt to hash, measured in ENCODED BYTES.
#
# Bytes rather than characters, and that distinction is the point: `á` is two bytes in UTF-8 and an
# emoji is four, so a 40-character accented passphrase is 80 bytes. A character-counting cap would
# accept all of those and hand them straight to bcrypt — and this is an es-locale app, so an accented
# passphrase is the ordinary case rather than an exotic one.
def within_bcrypt_limit(value: str) -> bool:
    return len(value.encode("utf-8")) <= MAX_PASSWORD_BYTES
