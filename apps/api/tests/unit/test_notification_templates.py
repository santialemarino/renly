# The two channels the backend renders itself: email and web push.
#
# Most of this file is STRUCTURAL, deliberately. The catalog is a hand-maintained nested dict with a
# string per event per locale, and its failure modes are all silent: an event with no entry raises a
# KeyError inside a fan-out that swallows exceptions, a Spanish string interpolating a placeholder the
# English one does not raises only for Spanish readers, and a push string that grew an `{amount}` puts
# a money figure on a lock screen with nothing anywhere to notice. Each of those is one assertion here.

import re
from decimal import Decimal

import pytest

from app.models.notification import NotificationEvent
from app.services import notification_templates as templates

_LOCALES = ("en", "es")
# Every value any template interpolates, so one payload renders all of them. Deliberately a single
# dict rather than one per event: a template that grew a placeholder nobody supplies is exactly what
# the render test below has to catch, and a per-event payload would simply be updated alongside it.
_PAYLOAD = {
    "group": "Casa",
    "pot": "Depto Palermo",
    "actor": "Santi",
    "member": "Ana",
    "inviter": "Santi",
    "invitee": "Nico",
    "from_member": "Santi",
    "to_member": "Ana",
    "creditor": "Ana",
    "amount": "90000",
    "currency": "ARS",
}
_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def _keys(locale: str) -> set[str]:
    return set(templates._STRINGS[locale])


def _template_keys() -> list[str]:
    return sorted(key for key in _keys("en") if not key.startswith("_"))


class TestCatalogStructure:
    def test_both_locales_carry_exactly_the_same_keys(self):
        assert _keys("en") == _keys("es")

    def test_every_event_has_at_least_one_template(self):
        # The failure this prevents: adding an event to the enum, wiring it in a service, and having
        # every email and push for it raise a KeyError inside a fan-out that logs and moves on.
        covered = {key.split(".")[0] for key in _template_keys()}
        assert {event.value for event in NotificationEvent} - covered == set()

    def test_every_template_belongs_to_a_real_event(self):
        # The other direction: a template for an event that has been removed or renamed is dead copy
        # that reads as coverage.
        values = {event.value for event in NotificationEvent}
        assert {key.split(".")[0] for key in _template_keys()} - values == set()

    def test_every_template_carries_all_three_fields(self):
        for locale in _LOCALES:
            for key in _template_keys():
                assert set(templates._STRINGS[locale][key]) == {"subject", "body", "push"}, f"{locale}/{key}"

    def test_the_two_locales_interpolate_the_same_placeholders(self):
        # A Spanish body naming `{member}` where the English one names `{actor}` raises only for
        # Spanish readers, on an event nobody tested in Spanish. Compared per FIELD, because the
        # subject and the body legitimately differ from each other.
        for key in _template_keys():
            for field in ("subject", "body", "push"):
                english = set(_PLACEHOLDER.findall(templates._STRINGS["en"][key][field]))
                spanish = set(_PLACEHOLDER.findall(templates._STRINGS["es"][key][field]))
                assert english == spanish, f"{key}/{field}: en={english} es={spanish}"

    def test_no_push_string_carries_a_money_figure(self):
        # The lock-screen rule, enforced structurally rather than by review: a push renders where
        # anyone holding the phone reads it, so the amount waits for the app.
        for locale in _LOCALES:
            for key in _template_keys():
                push = templates._STRINGS[locale][key]["push"]
                assert "{amount}" not in push and "{currency}" not in push, f"{locale}/{key}"

    def test_every_placeholder_a_template_uses_is_one_a_payload_supplies(self):
        # `{link}`, `{product}` and `{settings_link}` are filled by the builders; everything else has
        # to come out of the payload, and a name no producer writes is a KeyError at send time.
        supplied = set(_PAYLOAD) | {"link", "product", "settings_link"}
        for locale in _LOCALES:
            for key in set(_template_keys()) | {"_footer"}:
                for field, text in templates._STRINGS[locale][key].items():
                    assert set(_PLACEHOLDER.findall(text)) <= supplied, f"{locale}/{key}/{field}"


class TestRendering:
    @pytest.mark.parametrize("locale", _LOCALES)
    def test_every_template_renders_in_both_locales(self, locale):
        for key in _template_keys():
            event = NotificationEvent(key.split(".")[0])
            variant = key.split(".")[1] if "." in key else None
            payload = {**_PAYLOAD, **({"variant": variant} if variant else {})}
            message = templates.notification_email(
                "a@test.local", event, payload, link="https://renly.test/shared/1", settings_link="https://renly.test/notifications", locale=locale
            )
            assert message.subject and "{" not in message.subject
            assert "https://renly.test/shared/1" in message.text
            assert "{" not in templates.push_body(event, payload, locale)

    @pytest.mark.parametrize("locale", _LOCALES)
    def test_a_NAMELESS_pot_reads_as_its_label_and_never_as_None(self, locale):
        # `pots.name` is NULL for a group's DEFAULT pot — the pot most groups only ever have — so this
        # is the common case, not the edge one. And it does not raise: "{pot}".format(pot=None) happily
        # prints "None", so the failure would have shipped as an email and a lock-screen line reading
        # "None is due a new valuation" while the feed, which has its own fallback, read correctly.
        payload = {**_PAYLOAD, "pot": None}
        for key in _template_keys():
            if "{pot}" not in "".join(templates._STRINGS[locale][key].values()):
                continue
            event = NotificationEvent(key.split(".")[0])
            variant = key.split(".")[1] if "." in key else None
            rendered = {**payload, **({"variant": variant} if variant else {})}
            message = templates.notification_email(
                "a@test.local", event, rendered, link="https://renly.test/x", settings_link="https://renly.test/n", locale=locale
            )
            for text in (message.subject, message.text, templates.push_body(event, rendered, locale)):
                assert "None" not in text, f"{key} rendered a nameless pot as None in {locale}"

    @pytest.mark.parametrize("locale", _LOCALES)
    def test_the_nameless_label_is_the_one_the_web_shows(self, locale):
        # The same pot must not have two names. This asserts the API's label against the WEB's
        # `common.potDefaultLabel`, read out of the translation file rather than restated, so the two
        # cannot drift into "Shared money" in an inbox and something else in the app.
        #
        # It is a `common` key rather than a per-namespace one because THREE surfaces now render it —
        # the notification feed, the Shared module and the dashboard's undivided-pot line — and the
        # first two used to hold byte-identical copies under two namespaces.
        import json
        from pathlib import Path

        web = json.loads((Path(__file__).resolve().parents[3] / "web" / "translations" / f"{locale}.json").read_text())
        assert templates._strings("_pot", locale)["name"] == web["common"]["potDefaultLabel"]

    def test_an_unknown_locale_falls_back_to_english(self):
        message = templates.notification_email(
            "a@test.local",
            NotificationEvent.member_joined,
            _PAYLOAD,
            link="https://renly.test/shared/1",
            settings_link="https://renly.test/notifications",
            locale="fr",
        )
        assert message.subject == "Ana joined Casa"

    def test_the_email_names_the_preferences_page_so_it_can_be_turned_off(self):
        # Not decoration: an email people cannot find the switch for is an email they mark as spam.
        message = templates.notification_email(
            "a@test.local",
            NotificationEvent.snapshot_due,
            _PAYLOAD,
            link="https://renly.test/shared/pots/5",
            settings_link="https://renly.test/notifications",
            locale="en",
        )
        assert "https://renly.test/notifications" in message.text

    def test_the_html_body_escapes_a_name_somebody_chose(self):
        # A group name is user-controlled and reaches an inbox, so the wrapper has to escape it. Shared
        # with the transactional emails through email_templates.html_body precisely so there is one
        # escaping rule rather than two.
        payload = {**_PAYLOAD, "group": "<script>alert(1)</script>"}
        message = templates.notification_email(
            "a@test.local", NotificationEvent.member_joined, payload, link="https://renly.test/x", settings_link="https://renly.test/n", locale="en"
        )
        assert "<script>" not in message.html and "&lt;script&gt;" in message.html

    def test_the_variant_decides_the_sentence(self):
        # One event, two facts. A contribution and a withdrawal are the same enum value and must not
        # read the same way, and the variant travels in the payload so no caller picks the wording.
        added = templates.push_body(NotificationEvent.pot_movement, {**_PAYLOAD, "variant": "contribution"}, "en")
        took = templates.push_body(NotificationEvent.pot_movement, {**_PAYLOAD, "variant": "withdrawal"}, "en")
        assert added != took and "added" in added and "took" in took


class TestAmountFormatting:
    # The one place the backend formats money for a person to read. It has to match what the app shows
    # — grouped thousands, at most two decimals, and NO trailing zero — so these are the same expected
    # strings `Intl.NumberFormat` produces with `minimumFractionDigits: 0, maximumFractionDigits: 2`,
    # computed by hand rather than by calling the formatter twice.
    #
    # The `.50` and `.5` cases are the ones that matter: they are what separates this rule from
    # "two decimals always", and a notification printing 150,000.50 beside a feed row printing
    # 150,000.5 is the same figure rendered two ways on two surfaces describing one event.
    @pytest.mark.parametrize(
        ("value", "locale", "expected"),
        [
            ("90000", "en", "90,000"),
            ("90000", "es", "90.000"),
            ("90000.00", "en", "90,000"),
            ("90000.55", "en", "90,000.55"),
            ("90000.55", "es", "90.000,55"),
            ("150000.50", "en", "150,000.5"),
            ("150000.50", "es", "150.000,5"),
            ("150000.5", "en", "150,000.5"),
            ("0.10", "en", "0.1"),
            ("0.10", "es", "0,1"),
            ("150000.505", "en", "150,000.51"),
            ("1234567.89", "en", "1,234,567.89"),
            ("1234567.89", "es", "1.234.567,89"),
            ("0.07", "en", "0.07"),
            ("0.07", "es", "0,07"),
            ("120", "en", "120"),
            ("-45.50", "en", "-45.5"),
            ("-45.50", "es", "-45,5"),
            ("-45.55", "en", "-45.55"),
        ],
    )
    def test_a_figure_reads_the_way_the_app_shows_it(self, value, locale, expected):
        assert templates._amount(value, locale) == expected

    def test_an_unreadable_figure_is_shown_verbatim_rather_than_losing_the_email(self):
        # The sentence around it is still true, and an odd-looking figure is visible where a dropped
        # email is not.
        assert templates._amount("not a number", "en") == "not a number"

    def test_the_email_renders_the_figure_and_the_push_does_not(self):
        payload = {**_PAYLOAD, "amount": Decimal("90000.50")}
        message = templates.notification_email(
            "a@test.local",
            NotificationEvent.shared_expense_added,
            payload,
            link="https://renly.test/shared/1",
            settings_link="https://renly.test/notifications",
            locale="es",
        )
        assert "90.000,5 ARS" in message.text
        assert "90" not in templates.push_body(NotificationEvent.shared_expense_added, payload, "es")
