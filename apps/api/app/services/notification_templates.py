# The prose for the two channels the BACKEND renders: email and web push.
#
# Why these two and not the feed. The API stays locale-agnostic everywhere it can, and the in-app feed
# obeys that — a notification row stores the event plus its payload, and the web renders the sentence
# from its own translation files, so the feed re-reads in whatever language the reader is using now and
# a copy fix reaches rows written months ago. Email and push have no frontend renderer at send time,
# which is the same reason transactional emails are the one place the backend produces prose. They are
# localized to the recipient's stored language, falling back per string.
#
# A push carries NO figures, and the difference from the email is deliberate rather than an oversight:
# a push renders on a lock screen where anyone holding the phone reads it, while the email is already
# behind an inbox. So the push says who did what in which group, and the amount waits for the app.
#
# Every string here interpolates values the caller lifts straight out of the notification's payload —
# the same payload the web renders the feed from — so the two channels cannot describe one event
# differently.

from decimal import ROUND_HALF_UP, Decimal

from app.models.notification import NotificationEvent
from app.schemas.settings import SUPPORTED_LANGUAGES
from app.services.email_service import EmailMessage
from app.services.email_templates import html_body

_PRODUCT_NAME = "Renly"
# Same fallback locale as the transactional emails, derived from the same tuple so the two cannot drift.
_DEFAULT_LOCALE = SUPPORTED_LANGUAGES[0]

# One entry per event, and for two events a second entry per VARIANT — an ownership change reads
# differently for a first division than for a re-agreement, and a recorded payment reads differently to
# the person who paid than to the person who was paid. The variant is a payload field, so the caller
# never decides the wording.
#
# `subject` and `body` are the email; `push` is the lock-screen line (the push TITLE is always the group
# or pot name, supplied by the caller). `{link}` is filled with the page the notification points at.
_STRINGS: dict[str, dict[str, dict[str, str]]] = {
    "en": {
        "group_invited": {
            "subject": "{inviter} invited {invitee} to {group}",
            "body": ('{inviter} invited {invitee} to the group "{group}" on {product}.\n\nSee the group here:\n{link}'),
            "push": "{inviter} invited {invitee}",
        },
        "member_joined": {
            "subject": "{member} joined {group}",
            "body": '{member} joined the group "{group}" on {product}.\n\nSee the group here:\n{link}',
            "push": "{member} joined the group",
        },
        "ownership_changed.opening": {
            "subject": "{actor} divided {pot} between its owners",
            "body": ('{actor} recorded who owns what in "{pot}", in the group "{group}".\n\nSee the pot and its ownership here:\n{link}'),
            "push": "{actor} divided {pot} between its owners",
        },
        "ownership_changed.reagreement": {
            "subject": "{actor} recorded a change of split in {pot}",
            "body": (
                '{actor} recorded a change of split in "{pot}", in the group "{group}": '
                "from {from_member} to {to_member}.\n\n"
                "See the pot and its ownership here:\n{link}"
            ),
            "push": "{actor} recorded a change of split in {pot}",
        },
        "pot_movement.contribution": {
            "subject": "{member} added money to {pot}",
            "body": ('{member} added {amount} {currency} to "{pot}", in the group "{group}".\n\nSee the pot and its movements here:\n{link}'),
            "push": "{member} added money to {pot}",
        },
        "pot_movement.withdrawal": {
            "subject": "{member} took money out of {pot}",
            "body": ('{member} took {amount} {currency} out of "{pot}", in the group "{group}".\n\nSee the pot and its movements here:\n{link}'),
            "push": "{member} took money out of {pot}",
        },
        "snapshot_due": {
            "subject": "{pot} is due a new valuation",
            "body": (
                '"{pot}", in the group "{group}", is due a new valuation.\n\n'
                "Everything the pot is worth is measured from its holdings, so until they are valued "
                "again every share of it reads from an older figure.\n\n"
                "Value it here:\n{link}"
            ),
            "push": "{pot} is due a new valuation",
        },
        "settle_marked_paid.payee": {
            "subject": "{from_member} recorded a payment to you in {group}",
            "body": (
                '{from_member} recorded a payment of {amount} {currency} to you in the group "{group}".\n\n'
                "Confirm it once you have received it:\n{link}"
            ),
            "push": "{from_member} recorded a payment to you",
        },
        "settle_marked_paid.payer": {
            "subject": "{to_member} recorded your payment in {group}",
            "body": (
                '{to_member} recorded your payment of {amount} {currency} in the group "{group}".\n\nSee the group\'s settlements here:\n{link}'
            ),
            "push": "{to_member} recorded your payment",
        },
        "settle_confirmed": {
            "subject": "{to_member} confirmed your payment in {group}",
            "body": (
                '{to_member} confirmed your payment of {amount} {currency} in the group "{group}".\n\nSee the group\'s settlements here:\n{link}'
            ),
            "push": "{to_member} confirmed your payment",
        },
        "balance_written_off": {
            "subject": "{creditor} wrote off what you owed in {group}",
            "body": (
                '{creditor} wrote off {amount} {currency} you owed in the group "{group}". '
                "Nothing moved — they gave up the claim.\n\n"
                "See the group's balances here:\n{link}"
            ),
            "push": "{creditor} wrote off what you owed",
        },
        "shared_expense_added": {
            "subject": "{actor} added a shared expense to {group}",
            "body": ('{actor} added a shared expense of {amount} {currency} to the group "{group}".\n\nSee it and your share here:\n{link}'),
            "push": "{actor} added a shared expense",
        },
        "shared_income_added": {
            "subject": "{actor} added shared income to {group}",
            "body": ('{actor} added shared income of {amount} {currency} to the group "{group}".\n\nSee it and your share here:\n{link}'),
            "push": "{actor} added shared income",
        },
        "_footer": {
            "text": "You can change which notifications {product} sends you under Settings → Notifications:\n{settings_link}",
        },
    },
    "es": {
        "group_invited": {
            "subject": "{inviter} invitó a {invitee} a {group}",
            "body": ('{inviter} invitó a {invitee} al grupo "{group}" en {product}.\n\nPodés ver el grupo acá:\n{link}'),
            "push": "{inviter} invitó a {invitee}",
        },
        "member_joined": {
            "subject": "{member} se unió a {group}",
            "body": '{member} se unió al grupo "{group}" en {product}.\n\nPodés ver el grupo acá:\n{link}',
            "push": "{member} se unió al grupo",
        },
        "ownership_changed.opening": {
            "subject": "{actor} dividió {pot} entre sus dueños",
            "body": ('{actor} registró quién es dueño de qué en "{pot}", en el grupo "{group}".\n\nPodés ver el fondo y su reparto acá:\n{link}'),
            "push": "{actor} dividió {pot} entre sus dueños",
        },
        "ownership_changed.reagreement": {
            "subject": "{actor} registró un cambio de reparto en {pot}",
            "body": (
                '{actor} registró un cambio de reparto en "{pot}", en el grupo "{group}": '
                "de {from_member} a {to_member}.\n\n"
                "Podés ver el fondo y su reparto acá:\n{link}"
            ),
            "push": "{actor} registró un cambio de reparto en {pot}",
        },
        "pot_movement.contribution": {
            "subject": "{member} puso dinero en {pot}",
            "body": ('{member} puso {amount} {currency} en "{pot}", en el grupo "{group}".\n\nPodés ver el fondo y sus movimientos acá:\n{link}'),
            "push": "{member} puso dinero en {pot}",
        },
        "pot_movement.withdrawal": {
            "subject": "{member} sacó dinero de {pot}",
            "body": ('{member} sacó {amount} {currency} de "{pot}", en el grupo "{group}".\n\nPodés ver el fondo y sus movimientos acá:\n{link}'),
            "push": "{member} sacó dinero de {pot}",
        },
        "snapshot_due": {
            "subject": "{pot} necesita una nueva valuación",
            "body": (
                '"{pot}", en el grupo "{group}", necesita una nueva valuación.\n\n'
                "Todo lo que vale el fondo se calcula a partir de lo que tiene, así que hasta que se "
                "vuelva a valuar cada parte se lee sobre una cifra más vieja.\n\n"
                "Podés valuarlo acá:\n{link}"
            ),
            "push": "{pot} necesita una nueva valuación",
        },
        "settle_marked_paid.payee": {
            "subject": "{from_member} registró un pago a tu nombre en {group}",
            "body": (
                '{from_member} registró un pago de {amount} {currency} a tu nombre en el grupo "{group}".\n\n'
                "Confirmalo cuando lo hayas recibido:\n{link}"
            ),
            "push": "{from_member} registró un pago a tu nombre",
        },
        "settle_marked_paid.payer": {
            "subject": "{to_member} registró tu pago en {group}",
            "body": ('{to_member} registró tu pago de {amount} {currency} en el grupo "{group}".\n\nPodés ver los pagos del grupo acá:\n{link}'),
            "push": "{to_member} registró tu pago",
        },
        "settle_confirmed": {
            "subject": "{to_member} confirmó tu pago en {group}",
            "body": ('{to_member} confirmó tu pago de {amount} {currency} en el grupo "{group}".\n\nPodés ver los pagos del grupo acá:\n{link}'),
            "push": "{to_member} confirmó tu pago",
        },
        "balance_written_off": {
            "subject": "{creditor} dio por perdido lo que le debías en {group}",
            "body": (
                '{creditor} dio por perdidos {amount} {currency} que le debías en el grupo "{group}". '
                "No se movió nada: resignó el crédito.\n\n"
                "Podés ver los saldos del grupo acá:\n{link}"
            ),
            "push": "{creditor} dio por perdido lo que le debías",
        },
        "shared_expense_added": {
            "subject": "{actor} agregó un gasto compartido a {group}",
            "body": ('{actor} agregó un gasto compartido de {amount} {currency} al grupo "{group}".\n\nPodés verlo, con tu parte, acá:\n{link}'),
            "push": "{actor} agregó un gasto compartido",
        },
        "shared_income_added": {
            "subject": "{actor} agregó un ingreso compartido a {group}",
            "body": ('{actor} agregó un ingreso compartido de {amount} {currency} al grupo "{group}".\n\nPodés verlo, con tu parte, acá:\n{link}'),
            "push": "{actor} agregó un ingreso compartido",
        },
        "_footer": {
            "text": "Podés cambiar qué notificaciones te manda {product} en Configuración → Notificaciones:\n{settings_link}",
        },
    },
}


# Thousand separators for the locales this app ships, since Spanish and English disagree about which
# character does which job.
_SEPARATORS = {"en": (",", "."), "es": (".", ",")}


# A money figure as the app itself renders it: grouped thousands, at most two decimals, and no trailing
# zero at all — "90,000" for a whole figure and "150,000.5" for one that ends in a five.
#
# This is the ONE place the backend formats money for a person to read, and it exists because email is
# the one channel with no frontend renderer. It is deliberately the same RULE as the web's formatValue,
# which is `Intl.NumberFormat` with `minimumFractionDigits: 0` and `maximumFractionDigits: 2` — and the
# two are pinned to identical expected strings in their respective tests, which is the only mitigation
# available when one rule has to exist in two runtimes.
#
# The trailing-zero half is not cosmetic and was found by reading a real screen: a notification saying
# "150,000.50" beside a feed row saying "150,000.5" is the same figure printed two ways, on two surfaces
# describing the same event.
def _amount(value: str, locale: str) -> str:
    thousands, decimal = _SEPARATORS.get(locale, _SEPARATORS[_DEFAULT_LOCALE])
    try:
        number = Decimal(value)
    except (ArithmeticError, TypeError, ValueError):
        # A payload that cannot be read as a number is shown verbatim rather than dropping the whole
        # email: the sentence around it is still true, and an unreadable figure is visible.
        return value
    # ROUND_HALF_UP rather than Decimal's default banker's rounding, because Intl.NumberFormat rounds
    # half away from zero and this rule has to be the same one in both runtimes. Unreachable from a
    # real payload — every amount comes from a NUMERIC(18,2) column — but a rule that agrees only for
    # the inputs that happen to occur is a rule waiting to disagree.
    quantized = number.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    whole, _, fraction = f"{abs(quantized):.2f}".partition(".")
    grouped = f"{int(whole):,}".replace(",", thousands)
    sign = "-" if quantized < 0 else ""
    fraction = fraction.rstrip("0")
    return f"{sign}{grouped}{decimal}{fraction}" if fraction else f"{sign}{grouped}"


# The payload with its money figures rendered for reading, leaving every other value untouched. Applied
# once per message so no template has to remember to do it.
def _readable(payload: dict, locale: str) -> dict:
    if "amount" not in payload:
        return payload
    return {**payload, "amount": _amount(str(payload["amount"]), locale)}


# The {subject, body, push} block for one template key in one locale, falling back to the default
# locale for an unknown language or a locale missing that key — the same resolution email_templates
# uses, and for the same reason: a missing translation must degrade to English, never to a KeyError in
# the middle of a fan-out.
def _strings(key: str, locale: str) -> dict[str, str]:
    catalog = _STRINGS.get(locale, _STRINGS[_DEFAULT_LOCALE])
    return catalog.get(key) or _STRINGS[_DEFAULT_LOCALE][key]


# The template key for an event, plus its variant when the event has one. The variant travels in the
# payload (`variant`), so the sentence is decided by what happened rather than by the caller.
def template_key(event: NotificationEvent, payload: dict) -> str:
    variant = payload.get("variant")
    return f"{event.value}.{variant}" if variant else event.value


# The lock-screen line for one notification: no figures, ever. No amount is even formatted here — the
# push strings interpolate no `{amount}` at all, so there is nothing to leave out by accident.
def push_body(event: NotificationEvent, payload: dict, locale: str = _DEFAULT_LOCALE) -> str:
    return _strings(template_key(event, payload), locale)["push"].format(product=_PRODUCT_NAME, **payload)


# One notification as an email, localized to the recipient's stored language.
#
# `link` is the page the notification points at and `settings_link` the preferences page, both built by
# the caller from the web's own base URL — this module composes prose and knows no routes.
def notification_email(
    to: str, event: NotificationEvent, payload: dict, *, link: str, settings_link: str, locale: str = _DEFAULT_LOCALE
) -> EmailMessage:
    strings = _strings(template_key(event, payload), locale)
    readable = _readable(payload, locale)
    footer = _strings("_footer", locale)["text"].format(product=_PRODUCT_NAME, settings_link=settings_link)
    text = f"{strings['body'].format(product=_PRODUCT_NAME, link=link, **readable)}\n\n{footer}"
    subject = strings["subject"].format(product=_PRODUCT_NAME, **readable)
    return EmailMessage(to=to, subject=subject, html=html_body(text), text=text)
