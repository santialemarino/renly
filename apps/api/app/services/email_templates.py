# Builders for the account-lifecycle emails (SHELL-3 / AUTH-1, AUTH-2, AUTH-5, AUTH-8). Pure
# functions returning an EmailMessage; no provider or I/O concerns live here.
#
# Transactional emails are the ONE place the backend produces user-facing prose (there is no
# frontend renderer for them), so — unlike every other API response, which stays locale-agnostic —
# they carry their own en/es catalog and are localized to the recipient's stored language. Callers
# resolve the locale (the signup verification uses the language the web passes to /auth/register;
# existing-user flows read the stored `language`; anti-enumeration + invite sends fall back to the
# default locale) and pass it in; an unknown locale falls back to the default per string.

import html

from app.schemas.settings import SUPPORTED_LANGUAGES
from app.services.email_service import EmailMessage

_PRODUCT_NAME = "Renly"
# The email fallback locale is the app's default language, so it can't drift from
# settings_service.DEFAULT_LANGUAGE (both derive from SUPPORTED_LANGUAGES[0]) — the anti-enumeration
# sends rely on the two being equal.
_DEFAULT_LOCALE = SUPPORTED_LANGUAGES[0]

# Localized subject + body per email. Bodies are TEXT (never markup); `{product}`/`{link}` and the
# feedback placeholders are filled by each builder.
_STRINGS: dict[str, dict[str, dict[str, str]]] = {
    "en": {
        "verification": {
            "subject": "Verify your {product} email",
            "body": (
                "Welcome to {product}.\n\n"
                "Confirm your email address to activate your account:\n{link}\n\n"
                "If you didn't create this account, you can ignore this message."
            ),
        },
        "account_exists": {
            "subject": "You already have a {product} account",
            "body": (
                "You already have a {product} account with this email.\n\n"
                "You can log in here:\n{link}\n\n"
                'If you forgot your password, use the "Forgot password" link on the login page.\n\n'
                "If you didn't try to sign up, you can safely ignore this message."
            ),
        },
        "password_reset": {
            "subject": "Reset your {product} password",
            "body": (
                "We received a request to reset your {product} password.\n\n"
                "Choose a new password here:\n{link}\n\n"
                "This link expires soon and can be used once. If you didn't request a reset, "
                "ignore this message — your password won't change."
            ),
        },
        "email_change": {
            "subject": "Confirm your new {product} email",
            "body": (
                "Confirm this address to use it for your {product} account:\n{link}\n\n"
                "Until you confirm, your account email stays unchanged. If you didn't request this, "
                "ignore this message."
            ),
        },
        "invite": {
            "subject": "You're invited to {product}",
            "body": (
                "You've been invited to {product}.\n\n"
                "Create your account here:\n{link}\n\n"
                "This invite is tied to your email address and can be used once. If you weren't "
                "expecting it, you can ignore this message."
            ),
        },
        "group_invite": {
            "subject": "{inviter} invited you to {group} on {product}",
            "body": (
                '{inviter} invited you to the group "{group}" on {product}.\n\n'
                "Open this link to join:\n{link}\n\n"
                "You need to be logged in to your {product} account — the link takes you to the login "
                "page if you are not. It works once and expires soon. If you were not expecting this, "
                "you can ignore this message."
            ),
        },
        "email_change_taken": {
            "subject": "This email already has a {product} account",
            "body": (
                "Someone tried to switch a {product} account to this email, but it already belongs "
                "to an account.\n\n"
                "If that was you, log in to the existing account instead:\n{link}\n\n"
                "Otherwise, you can safely ignore this message."
            ),
        },
        "feedback_notification": {
            "subject": "New {product} feedback: {category}",
            "body": "New {product} feedback ({category}) from {submitter}:\n\n{message}",
        },
    },
    "es": {
        "verification": {
            "subject": "Verificá tu correo de {product}",
            "body": (
                "Te damos la bienvenida a {product}.\n\n"
                "Confirmá tu dirección de correo para activar tu cuenta:\n{link}\n\n"
                "Si no creaste esta cuenta, podés ignorar este mensaje."
            ),
        },
        "account_exists": {
            "subject": "Ya tenés una cuenta de {product}",
            "body": (
                "Ya tenés una cuenta de {product} con este correo.\n\n"
                "Podés iniciar sesión acá:\n{link}\n\n"
                'Si olvidaste tu contraseña, usá el enlace "¿Olvidaste tu contraseña?" en la '
                "página de inicio de sesión.\n\n"
                "Si no intentaste registrarte, podés ignorar este mensaje sin problema."
            ),
        },
        "password_reset": {
            "subject": "Restablecé tu contraseña de {product}",
            "body": (
                "Recibimos una solicitud para restablecer tu contraseña de {product}.\n\n"
                "Elegí una nueva contraseña acá:\n{link}\n\n"
                "Este enlace vence pronto y se puede usar una sola vez. Si no solicitaste el "
                "cambio, ignorá este mensaje: tu contraseña no va a cambiar."
            ),
        },
        "email_change": {
            "subject": "Confirmá tu nuevo correo de {product}",
            "body": (
                "Confirmá esta dirección para usarla en tu cuenta de {product}:\n{link}\n\n"
                "Hasta que la confirmes, el correo de tu cuenta no cambia. Si no solicitaste esto, "
                "ignorá este mensaje."
            ),
        },
        "invite": {
            "subject": "Te invitaron a {product}",
            "body": (
                "Te invitaron a {product}.\n\n"
                "Creá tu cuenta acá:\n{link}\n\n"
                "Esta invitación está asociada a tu dirección de correo y se puede usar una sola "
                "vez. Si no la esperabas, podés ignorar este mensaje."
            ),
        },
        "group_invite": {
            "subject": "{inviter} te invitó a {group} en {product}",
            "body": (
                '{inviter} te invitó al grupo "{group}" en {product}.\n\n'
                "Abrí este enlace para unirte:\n{link}\n\n"
                "Necesitás estar conectado a tu cuenta de {product}: si no lo estás, el enlace te "
                "lleva a la página de inicio de sesión. Se puede usar una sola vez y vence pronto. "
                "Si no esperabas esta invitación, podés ignorar este mensaje."
            ),
        },
        "email_change_taken": {
            "subject": "Este correo ya tiene una cuenta de {product}",
            "body": (
                "Alguien intentó cambiar el correo de una cuenta de {product} a esta dirección, "
                "pero ya pertenece a una cuenta.\n\n"
                "Si fuiste vos, iniciá sesión en la cuenta existente:\n{link}\n\n"
                "Si no, podés ignorar este mensaje sin problema."
            ),
        },
        "feedback_notification": {
            "subject": "Nuevo comentario de {product}: {category}",
            "body": "Nuevo comentario de {product} ({category}) de {submitter}:\n\n{message}",
        },
    },
}

# Localized labels for the feedback category enum, shown in the admin notification (matches the
# frontend `feedback.categories.*` keys).
_FEEDBACK_CATEGORIES: dict[str, dict[str, str]] = {
    "en": {"bug": "Bug", "idea": "Idea", "question": "Question", "other": "Other"},
    "es": {"bug": "Error", "idea": "Idea", "question": "Pregunta", "other": "Otro"},
}


# Wraps plain body text in a minimal HTML document so the message renders in both HTML and plain-text
# clients. Escapes each line — the body is TEXT, never markup — so user-controlled content (e.g. a
# feedback message) can't inject HTML into the recipient's inbox.
def _html(body: str) -> str:
    paragraphs = "".join(f"<p>{html.escape(line)}</p>" for line in body.strip().split("\n\n"))
    return f'<div style="font-family: sans-serif; line-height: 1.5;">{paragraphs}</div>'


# Returns the {subject, body} block for a template in the given locale, falling back to the default
# locale for an unknown language or a locale that's missing the key.
def _strings(key: str, locale: str) -> dict[str, str]:
    catalog = _STRINGS.get(locale, _STRINGS[_DEFAULT_LOCALE])
    return catalog.get(key) or _STRINGS[_DEFAULT_LOCALE][key]


# Builds a localized message for a link-carrying template (all builders except feedback share this).
def _link_email(key: str, to: str, link: str, locale: str) -> EmailMessage:
    strings = _strings(key, locale)
    text = strings["body"].format(product=_PRODUCT_NAME, link=link)
    subject = strings["subject"].format(product=_PRODUCT_NAME)
    return EmailMessage(to=to, subject=subject, html=_html(text), text=text)


# Verification email sent after signup; the link confirms the address and unlocks login (AUTH-1).
def verification_email(to: str, link: str, locale: str = _DEFAULT_LOCALE) -> EmailMessage:
    return _link_email("verification", to, link, locale)


# Sent on registration when the address already has an account, so the response never reveals it (AUTH-5).
def account_exists_email(to: str, login_link: str, locale: str = _DEFAULT_LOCALE) -> EmailMessage:
    return _link_email("account_exists", to, login_link, locale)


# Password reset email; the link opens the reset form (AUTH-2). Single-use, time-limited token.
def password_reset_email(to: str, link: str, locale: str = _DEFAULT_LOCALE) -> EmailMessage:
    return _link_email("password_reset", to, link, locale)


# Verification email for a requested email change; sent to the NEW address (AUTH-8). Confirming it
# switches the account email over.
def email_change_email(to: str, link: str, locale: str = _DEFAULT_LOCALE) -> EmailMessage:
    return _link_email("email_change", to, link, locale)


# Invite email sent when an admin invites an address (invite-only access gate). The link opens signup
# with the email locked to this address; the token is single-use and time-limited.
def invite_email(to: str, link: str, locale: str = _DEFAULT_LOCALE) -> EmailMessage:
    return _link_email("invite", to, link, locale)


# Sent on a change-email request when the requested address already belongs to another account, so
# the response stays uniform and never reveals it (AUTH-8, anti-enumeration).
def email_change_taken_email(to: str, login_link: str, locale: str = _DEFAULT_LOCALE) -> EmailMessage:
    return _link_email("email_change_taken", to, login_link, locale)


# Invite email sent when a group admin invites someone to a seat (shared money). Distinct from
# invite_email above: that one grants platform signup and locks the address, whereas this link only
# links an EXISTING account to a group seat and grants no signup access. Localized to the sender's
# language — the recipient may not have an account yet, so there is no stored preference to read.
def group_invite_email(to: str, link: str, group_name: str, inviter_name: str, locale: str = _DEFAULT_LOCALE) -> EmailMessage:
    strings = _strings("group_invite", locale)
    text = strings["body"].format(product=_PRODUCT_NAME, link=link, group=group_name, inviter=inviter_name)
    subject = strings["subject"].format(product=_PRODUCT_NAME, group=group_name, inviter=inviter_name)
    return EmailMessage(to=to, subject=subject, html=_html(text), text=text)


# Notifies an admin that a user submitted feedback from the in-app form (SHELL-7). to = the admin;
# localized to the admin's stored language, including the category label.
def feedback_notification_email(to: str, submitter_email: str, category: str, message: str, locale: str = _DEFAULT_LOCALE) -> EmailMessage:
    strings = _strings("feedback_notification", locale)
    labels = _FEEDBACK_CATEGORIES.get(locale, _FEEDBACK_CATEGORIES[_DEFAULT_LOCALE])
    category_label = labels.get(str(category), str(category))
    text = strings["body"].format(product=_PRODUCT_NAME, category=category_label, submitter=submitter_email, message=message)
    subject = strings["subject"].format(product=_PRODUCT_NAME, category=category_label)
    return EmailMessage(to=to, subject=subject, html=_html(text), text=text)
