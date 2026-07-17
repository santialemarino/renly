# Builders for the account-lifecycle emails (SHELL-3 / AUTH-1, AUTH-2, AUTH-5, AUTH-8). Pure
# functions returning an EmailMessage; no provider or I/O concerns live here.

import html

from app.services.email_service import EmailMessage

_PRODUCT_NAME = "Renly"


# Wraps plain body text in a minimal HTML document so the message renders in both HTML and plain-text
# clients. Escapes each line — the body is TEXT, never markup — so user-controlled content (e.g. a
# feedback message) can't inject HTML into the recipient's inbox.
def _html(body: str) -> str:
    paragraphs = "".join(f"<p>{html.escape(line)}</p>" for line in body.strip().split("\n\n"))
    return f'<div style="font-family: sans-serif; line-height: 1.5;">{paragraphs}</div>'


# Verification email sent after signup; the link confirms the address and unlocks login (AUTH-1).
def verification_email(to: str, link: str) -> EmailMessage:
    text = (
        f"Welcome to {_PRODUCT_NAME}.\n\n"
        f"Confirm your email address to activate your account:\n{link}\n\n"
        "If you didn't create this account, you can ignore this message."
    )
    return EmailMessage(to=to, subject=f"Verify your {_PRODUCT_NAME} email", html=_html(text), text=text)


# Sent on registration when the address already has an account, so the response never reveals it (AUTH-5).
def account_exists_email(to: str, login_link: str) -> EmailMessage:
    text = (
        f"You already have a {_PRODUCT_NAME} account with this email.\n\n"
        f"You can log in here:\n{login_link}\n\n"
        'If you forgot your password, use the "Forgot password" link on the login page.\n\n'
        "If you didn't try to sign up, you can safely ignore this message."
    )
    return EmailMessage(to=to, subject=f"You already have a {_PRODUCT_NAME} account", html=_html(text), text=text)


# Password reset email; the link opens the reset form (AUTH-2). Single-use, time-limited token.
def password_reset_email(to: str, link: str) -> EmailMessage:
    text = (
        f"We received a request to reset your {_PRODUCT_NAME} password.\n\n"
        f"Choose a new password here:\n{link}\n\n"
        "This link expires soon and can be used once. If you didn't request a reset, ignore this message — your password won't change."
    )
    return EmailMessage(to=to, subject=f"Reset your {_PRODUCT_NAME} password", html=_html(text), text=text)


# Verification email for a requested email change; sent to the NEW address (AUTH-8). Confirming it
# switches the account email over.
def email_change_email(to: str, link: str) -> EmailMessage:
    text = (
        f"Confirm this address to use it for your {_PRODUCT_NAME} account:\n{link}\n\n"
        "Until you confirm, your account email stays unchanged. If you didn't request this, ignore this message."
    )
    return EmailMessage(to=to, subject=f"Confirm your new {_PRODUCT_NAME} email", html=_html(text), text=text)


# Invite email sent when an admin invites an address (invite-only access gate). The link opens signup
# with the email locked to this address; the token is single-use and time-limited.
def invite_email(to: str, link: str) -> EmailMessage:
    text = (
        f"You've been invited to {_PRODUCT_NAME}.\n\n"
        f"Create your account here:\n{link}\n\n"
        "This invite is tied to your email address and can be used once. If you weren't expecting it, you can ignore this message."
    )
    return EmailMessage(to=to, subject=f"You're invited to {_PRODUCT_NAME}", html=_html(text), text=text)


# Sent on a change-email request when the requested address already belongs to another account, so
# the response stays uniform and never reveals it (AUTH-8, anti-enumeration).
def email_change_taken_email(to: str, login_link: str) -> EmailMessage:
    text = (
        f"Someone tried to switch a {_PRODUCT_NAME} account to this email, but it already belongs to an account.\n\n"
        f"If that was you, log in to the existing account instead:\n{login_link}\n\n"
        "Otherwise, you can safely ignore this message."
    )
    return EmailMessage(to=to, subject=f"This email already has a {_PRODUCT_NAME} account", html=_html(text), text=text)


# Notifies an admin that a user submitted feedback from the in-app form (SHELL-7). to = the admin.
def feedback_notification_email(to: str, submitter_email: str, category: str, message: str) -> EmailMessage:
    text = f"New {_PRODUCT_NAME} feedback ({category}) from {submitter_email}:\n\n{message}"
    return EmailMessage(to=to, subject=f"New {_PRODUCT_NAME} feedback: {category}", html=_html(text), text=text)
