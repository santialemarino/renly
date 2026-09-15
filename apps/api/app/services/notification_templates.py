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

import logging
from datetime import date as date_type
from decimal import ROUND_HALF_UP, Decimal

from app.models.notification import NotificationEvent
from app.schemas.settings import SUPPORTED_LANGUAGES
from app.services.email_service import EmailMessage
from app.services.email_templates import html_body

logger = logging.getLogger(__name__)

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
        "ownership_changed.confirmed": {
            "subject": "{actor} agreed to the change of split in {pot}",
            "body": (
                '{actor} agreed to the change of split from {from_member} to {to_member} in "{pot}", '
                'in the group "{group}".\n\n'
                "The entry is now settled and can no longer be removed unless they take that back.\n\n"
                "See the pot and its ownership here:\n{link}"
            ),
            "push": "{actor} agreed to the change of split in {pot}",
        },
        "ownership_changed.unconfirmed": {
            "subject": "{actor} withdrew their agreement to the change of split in {pot}",
            "body": (
                '{actor} withdrew their agreement to the change of split from {from_member} to {to_member} in "{pot}", '
                'in the group "{group}".\n\n'
                "Nobody's share has changed; the entry can be removed again.\n\n"
                "See the pot and its ownership here:\n{link}"
            ),
            "push": "{actor} withdrew their agreement in {pot}",
        },
        "ownership_changed.deleted": {
            "subject": "{actor} removed an entry from {pot}'s ownership history",
            "body": (
                '{actor} removed an entry from the ownership history of "{pot}", in the group "{group}". '
                "Everyone's share has been recalculated without it.\n\n"
                "See the pot and its ownership here:\n{link}"
            ),
            "push": "{actor} removed an ownership entry from {pot}",
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
        "pot_movement.reconciliation_surplus": {
            "subject": "{actor} reconciled {account}",
            "body": (
                '{actor} checked "{account}", in the pot "{pot}", against what it really holds.\n\n'
                "It held {amount} {currency} MORE than the pot had recorded, so that much was added and "
                "divided between the owners in their shares.\n\n"
                "See the pot and what it holds here:\n{link}"
            ),
            "push": "{actor} reconciled {account}",
        },
        "pot_movement.reconciliation_shortfall": {
            "subject": "{actor} reconciled {account}",
            "body": (
                '{actor} checked "{account}", in the pot "{pot}", against what it really holds.\n\n'
                "It held {amount} {currency} LESS than the pot had recorded, so that much was taken off and "
                "divided between the owners in their shares.\n\n"
                "See the pot and what it holds here:\n{link}"
            ),
            "push": "{actor} reconciled {account}",
        },
        "pot_movement.reconciliation_removed": {
            "subject": "{actor} removed a reconciliation of {account}",
            "body": (
                '{actor} removed a reconciliation of "{account}", in the pot "{pot}".\n\n'
                "Its {amount} {currency} adjustment went with it, so the balance is back to what it was "
                "before that correction.\n\n"
                "See the pot and what it holds here:\n{link}"
            ),
            "push": "{actor} removed a reconciliation of {account}",
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
        # The two PRIVATE events. Both say what Renly DID or what the reader THEMSELVES declared, never
        # what a third party is about to do: Renly records a subscription charge after the fact, it does
        # not make it, and the bill below is due because the reader said it was.
        "plan_charged.subscription": {
            "subject": "{name} — {amount} {currency} recorded on {date}",
            "body": (
                '{product} recorded the "{name}" subscription charge of {amount} {currency}, dated {date}, '
                "because the plan says it bills then.\n\n"
                "Nothing was paid on your behalf — this is the expense entry, so your balances stay right "
                "without you adding it.\n\n"
                "See it here:\n{link}"
            ),
            "push": "{product} recorded your {name} charge",
        },
        "plan_charged.installment": {
            "subject": "{name} — {amount} {currency} instalment recorded on {date}",
            "body": (
                '{product} recorded the "{name}" instalment of {amount} {currency}, dated {date}, '
                "because the plan says that cuota falls then.\n\n"
                "Nothing was paid on your behalf — this is the expense entry, so your balances stay right "
                "without you adding it.\n\n"
                "See it here:\n{link}"
            ),
            "push": "{product} recorded your {name} instalment",
        },
        "obligation_due": {
            "subject": "{name} is due on {date}",
            "body": (
                '"{name}" — {amount} {currency} — is due on {date}.\n\n'
                "{product} does not pay it for you. Mark it paid once you have, and the next one moves "
                "forward on its own.\n\n"
                "See it here:\n{link}"
            ),
            "push": "{name} is due on {date}",
        },
        "_footer": {
            "text": "You can change which notifications {product} sends you under Settings → Notifications:\n{settings_link}",
        },
        # The daily digest's own wrapper, and the only copy it needs: every LINE of it is the event's own
        # `subject` string above, so an event added later is digestible the day it exists, with nothing
        # here to remember to extend.
        "_digest": {
            "subject_one": "Your {product} summary — 1 update",
            "subject_other": "Your {product} summary — {count} updates",
            "intro": "Here is everything {product} has for you since your last summary.",
            "more": "…and {count} more.",
            "see_all": "See them all here:\n{link}",
        },
        # What a NAMELESS pot is called. A group's default pot has no name (pots.name is NULL for it),
        # and it is the pot most groups only ever have — so without this the most common reminder of
        # all reads "None is due a new valuation". Same label the web renders it under
        # (`notifications.potFallback`), so one event does not have two names.
        "_pot": {"name": "Shared money"},
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
        "ownership_changed.confirmed": {
            "subject": "{actor} aceptó el cambio de reparto en {pot}",
            "body": (
                '{actor} aceptó el cambio de reparto de {from_member} a {to_member} en "{pot}", '
                'en el grupo "{group}".\n\n'
                "La entrada queda acordada y ya no se puede eliminar, salvo que retire esa aceptación.\n\n"
                "Podés ver el fondo y su reparto acá:\n{link}"
            ),
            "push": "{actor} aceptó el cambio de reparto en {pot}",
        },
        "ownership_changed.unconfirmed": {
            "subject": "{actor} retiró su aceptación del cambio de reparto en {pot}",
            "body": (
                '{actor} retiró su aceptación del cambio de reparto de {from_member} a {to_member} en "{pot}", '
                'en el grupo "{group}".\n\n'
                "La parte de cada uno no cambió; la entrada se puede volver a eliminar.\n\n"
                "Podés ver el fondo y su reparto acá:\n{link}"
            ),
            "push": "{actor} retiró su aceptación en {pot}",
        },
        "ownership_changed.deleted": {
            "subject": "{actor} eliminó una entrada del historial de titularidad de {pot}",
            "body": (
                '{actor} eliminó una entrada del historial de titularidad de "{pot}", en el grupo "{group}". '
                "La parte de cada uno se recalculó sin ella.\n\n"
                "Podés ver el fondo y su reparto acá:\n{link}"
            ),
            "push": "{actor} eliminó una entrada de titularidad de {pot}",
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
        "pot_movement.reconciliation_surplus": {
            "subject": "{actor} concilió {account}",
            "body": (
                '{actor} comparó "{account}", en el fondo "{pot}", con lo que realmente tiene.\n\n'
                "Tenía {amount} {currency} MÁS de lo que el fondo tenía registrado, así que se sumó esa "
                "diferencia y se repartió entre los dueños según sus partes.\n\n"
                "Podés ver el fondo y lo que tiene acá:\n{link}"
            ),
            "push": "{actor} concilió {account}",
        },
        "pot_movement.reconciliation_shortfall": {
            "subject": "{actor} concilió {account}",
            "body": (
                '{actor} comparó "{account}", en el fondo "{pot}", con lo que realmente tiene.\n\n'
                "Tenía {amount} {currency} MENOS de lo que el fondo tenía registrado, así que se restó esa "
                "diferencia y se repartió entre los dueños según sus partes.\n\n"
                "Podés ver el fondo y lo que tiene acá:\n{link}"
            ),
            "push": "{actor} concilió {account}",
        },
        "pot_movement.reconciliation_removed": {
            "subject": "{actor} eliminó una conciliación de {account}",
            "body": (
                '{actor} eliminó una conciliación de "{account}", en el fondo "{pot}".\n\n'
                "El ajuste de {amount} {currency} se fue con ella, así que el saldo volvió a ser el de "
                "antes de esa corrección.\n\n"
                "Podés ver el fondo y lo que tiene acá:\n{link}"
            ),
            "push": "{actor} eliminó una conciliación de {account}",
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
        "plan_charged.subscription": {
            "subject": "{name} — {amount} {currency} registrado el {date}",
            "body": (
                '{product} registró el cargo de la suscripción "{name}" por {amount} {currency}, con fecha '
                "{date}, porque el plan dice que se cobra ese día.\n\n"
                "No se pagó nada en tu nombre: este es el gasto registrado, así tus saldos quedan bien sin "
                "que lo cargues vos.\n\n"
                "Podés verlo acá:\n{link}"
            ),
            "push": "{product} registró tu cargo de {name}",
        },
        "plan_charged.installment": {
            "subject": "{name} — cuota de {amount} {currency} registrada el {date}",
            "body": (
                '{product} registró la cuota de "{name}" por {amount} {currency}, con fecha {date}, porque '
                "el plan dice que esa cuota cae ese día.\n\n"
                "No se pagó nada en tu nombre: este es el gasto registrado, así tus saldos quedan bien sin "
                "que lo cargues vos.\n\n"
                "Podés verlo acá:\n{link}"
            ),
            "push": "{product} registró tu cuota de {name}",
        },
        "obligation_due": {
            "subject": "{name} vence el {date}",
            "body": (
                '"{name}" — {amount} {currency} — vence el {date}.\n\n'
                "{product} no lo paga por vos. Marcalo como pagado cuando lo hayas hecho y el siguiente "
                "avanza solo.\n\n"
                "Podés verlo acá:\n{link}"
            ),
            "push": "{name} vence el {date}",
        },
        "_footer": {
            "text": "Podés cambiar qué notificaciones te manda {product} en Configuración → Notificaciones:\n{settings_link}",
        },
        "_digest": {
            "subject_one": "Tu resumen de {product} — 1 novedad",
            "subject_other": "Tu resumen de {product} — {count} novedades",
            "intro": "Esto es todo lo que {product} tiene para vos desde tu último resumen.",
            "more": "…y {count} más.",
            "see_all": "Podés verlas todas acá:\n{link}",
        },
        "_pot": {"name": "Dinero compartido"},
    },
}


# Thousand separators for the locales this app ships, since Spanish and English disagree about which
# character does which job.
_SEPARATORS = {"en": (",", "."), "es": (".", ",")}

# Month names and date order per locale, out here beside the separators rather than inside the catalog
# for the same reason those are: they are locale DATA, not copy anybody writes per event.
#
# Spelling the month out is the whole point. A due date is the most important word in the one event
# whose email is on by default, and every all-numeric form is ambiguous across exactly the two locales
# this app ships: 09/07 is 9 July to a Spanish reader and 7 September to an English one.
_MONTH_NAMES = {
    "en": ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"),
    "es": ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"),
}
_DATE_PATTERNS = {"en": "{month} {day}, {year}", "es": "{day} de {month} de {year}"}


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


# An ISO date as a sentence reads it: "September 18, 2026" / "18 de septiembre de 2026".
#
# Only a payload key literally called `date` goes through this (see _readable), which is what keeps it
# from touching `snapshot_due`'s `valued_as_of` — a field whose email does not mention the date at all
# and whose stored rows predate this rule.
#
# The web formats the same value with date-fns and produces a shorter label ("Sep 18, 2026"), and that
# difference is deliberate rather than drift: an inbox has room for the month and a table cell does
# not. What must never differ is the DAY, which is why both sides read the date-only string on its own
# local-midnight anchor and neither shifts it by a timezone.
#
# An unparseable value is shown verbatim, for the same reason an unparseable amount is: the sentence
# around it stays true, and an odd-looking date is visible where a dropped email is not.
def _date(value: str, locale: str) -> str:
    try:
        parsed = date_type.fromisoformat(value)
    except (TypeError, ValueError):
        return value
    months = _MONTH_NAMES.get(locale, _MONTH_NAMES[_DEFAULT_LOCALE])
    pattern = _DATE_PATTERNS.get(locale, _DATE_PATTERNS[_DEFAULT_LOCALE])
    return pattern.format(day=parsed.day, month=months[parsed.month - 1], year=parsed.year)


# The payload as the templates need to read it: money figures formatted, dates spelled out, and a
# nameless pot given the label it is known by. Applied once per message, by BOTH renderers, so no
# template has to remember it.
#
# The pot half is the one that bites. `pots.name` is NULL for a group's default pot — which is the pot
# most groups only ever have — and `"{pot} is due a new valuation".format(pot=None)` does not raise, it
# prints "None". The feed never showed that because the web substitutes its own localized fallback; the
# email and the push had no such step, so the same event read correctly in the app and wrongly in an
# inbox and on a lock screen.
def _readable(payload: dict, locale: str) -> dict:
    readable = dict(payload)
    if "amount" in readable:
        readable["amount"] = _amount(str(readable["amount"]), locale)
    if readable.get("date") is not None:
        readable["date"] = _date(str(readable["date"]), locale)
    if readable.get("pot") is None and "pot" in readable:
        readable["pot"] = _strings("_pot", locale)["name"]
    return readable


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
    return _strings(template_key(event, payload), locale)["push"].format(product=_PRODUCT_NAME, **_readable(payload, locale))


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


# One line of a digest: an event's own email SUBJECT, which is already the one-sentence form of it.
#
# Reusing the subject is what makes the digest need no per-event copy at all — a new event is
# digestible the day it is added, and the enumerated-list surface this file is full of does not grow by
# one more list. Returns None for a payload the sentence cannot be built from, so one unrenderable row
# costs its own line instead of the whole summary; the alternative is a render error inside a job that,
# like every send in this layer, is not allowed to raise.
def _digest_line(event: NotificationEvent, payload: dict, locale: str) -> str | None:
    try:
        return _strings(template_key(event, payload), locale)["subject"].format(product=_PRODUCT_NAME, **_readable(payload, locale))
    except Exception:
        logger.warning("Skipped a '%s' line in a notification digest.", event.value, exc_info=True)
        return None


# Everything one person was told since their last summary, as a single email.
#
# `items` is (event, payload) in the order things happened, oldest first. `link` is the notifications
# page, which is both where the full history lives and what the reader wants after reading a summary.
#
# `overflow` is how many further rows exist beyond the ones passed in: the job caps what it renders, so
# a heavy day produces a readable email rather than a five-hundred-line one, and the count is stated
# rather than the remainder silently dropped. Rows left out are still in the feed — the link reaches
# them — which is why capping is safe here in a way that dropping a single immediate email would not be.
def digest_email(
    to: str, items: list[tuple[NotificationEvent, dict]], *, link: str, settings_link: str, overflow: int = 0, locale: str = _DEFAULT_LOCALE
) -> EmailMessage:
    strings = _strings("_digest", locale)
    lines = [line for event, payload in items if (line := _digest_line(event, payload, locale)) is not None]
    body = "\n".join(f"• {line}" for line in lines)
    if overflow > 0:
        body = f"{body}\n{strings['more'].format(count=overflow)}"
    footer = _strings("_footer", locale)["text"].format(product=_PRODUCT_NAME, settings_link=settings_link)
    text = "\n\n".join(
        [
            strings["intro"].format(product=_PRODUCT_NAME),
            body,
            strings["see_all"].format(link=link),
            footer,
        ]
    )
    # The count in the subject is what the reader was TOLD about, so it counts the rows this email
    # covers — the rendered lines plus the overflow it names — and not the ones it happened to render.
    count = len(lines) + overflow
    key = "subject_one" if count == 1 else "subject_other"
    return EmailMessage(to=to, subject=strings[key].format(product=_PRODUCT_NAME, count=count), html=html_body(text), text=text)
