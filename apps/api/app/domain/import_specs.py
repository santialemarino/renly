# Per-entity import specs: target fields, header aliases for auto-detection, and value coercers.
# The import engine is generic; each importable entity contributes one spec here.

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date as date_type
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from enum import StrEnum

from app.domain.currency import SUPPORTED_CURRENCIES, is_supported
from app.models.expense_entry import ExpenseCategory
from app.models.income_entry import IncomeCategory
from app.models.investment import InvestmentCategory


# Supported import data types. Top-level entities (owned directly by the user) ship first.
class ImportEntity(StrEnum):
    investments = "investments"
    expenses = "expenses"
    income = "income"


# A single target field in an import spec. coerce raises ValueError(message) on an invalid value.
@dataclass(frozen=True)
class FieldSpec:
    key: str
    required: bool
    aliases: frozenset[str]
    coerce: Callable[[str], object]


# An import spec for one entity: its target fields and the fields whose values form the dedup key.
# dedup_fields is a tuple so entities with no natural key can soft-match on a composite (e.g. an
# expense on date + amount + currency + category + notes); single-field entities use a 1-tuple.
@dataclass(frozen=True)
class ImportSpec:
    entity: ImportEntity
    fields: tuple[FieldSpec, ...]
    dedup_fields: tuple[str, ...]


# Investment category labels (EN/ES + each enum value) → InvestmentCategory.
_INVESTMENT_CATEGORY_ALIASES: dict[str, InvestmentCategory] = {
    "cedears": InvestmentCategory.cedears,
    "cedear": InvestmentCategory.cedears,
    "corporate_bonds": InvestmentCategory.corporate_bonds,
    "corporate bonds": InvestmentCategory.corporate_bonds,
    "obligaciones negociables": InvestmentCategory.corporate_bonds,
    "crypto": InvestmentCategory.crypto,
    "cripto": InvestmentCategory.crypto,
    "criptomonedas": InvestmentCategory.crypto,
    "dollars": InvestmentCategory.dollars,
    "dolares": InvestmentCategory.dollars,
    "dólares": InvestmentCategory.dollars,
    "fci": InvestmentCategory.fci,
    "government_bonds": InvestmentCategory.government_bonds,
    "government bonds": InvestmentCategory.government_bonds,
    "bonos": InvestmentCategory.government_bonds,
    "other": InvestmentCategory.other,
    "otro": InvestmentCategory.other,
    "otros": InvestmentCategory.other,
    "real_estate": InvestmentCategory.real_estate,
    "real estate": InvestmentCategory.real_estate,
    "inmuebles": InvestmentCategory.real_estate,
    "stocks": InvestmentCategory.stocks,
    "acciones": InvestmentCategory.stocks,
    "term_deposit": InvestmentCategory.term_deposit,
    "term deposit": InvestmentCategory.term_deposit,
    "plazo fijo": InvestmentCategory.term_deposit,
}

# Expense category labels (EN/ES + each enum value) → ExpenseCategory.
_EXPENSE_CATEGORY_ALIASES: dict[str, ExpenseCategory] = {
    "card_fees_and_taxes": ExpenseCategory.card_fees_and_taxes,
    "card fees and taxes": ExpenseCategory.card_fees_and_taxes,
    "card fees": ExpenseCategory.card_fees_and_taxes,
    "comisiones y impuestos de tarjeta": ExpenseCategory.card_fees_and_taxes,
    "clothing": ExpenseCategory.clothing,
    "clothes": ExpenseCategory.clothing,
    "ropa": ExpenseCategory.clothing,
    "indumentaria": ExpenseCategory.clothing,
    "dining": ExpenseCategory.dining,
    "restaurants": ExpenseCategory.dining,
    "salidas": ExpenseCategory.dining,
    "restaurantes": ExpenseCategory.dining,
    "education": ExpenseCategory.education,
    "educación": ExpenseCategory.education,
    "educacion": ExpenseCategory.education,
    "entertainment": ExpenseCategory.entertainment,
    "entretenimiento": ExpenseCategory.entertainment,
    "ocio": ExpenseCategory.entertainment,
    "food": ExpenseCategory.food,
    "groceries": ExpenseCategory.food,
    "comida": ExpenseCategory.food,
    "supermercado": ExpenseCategory.food,
    "alimentos": ExpenseCategory.food,
    "gifts": ExpenseCategory.gifts,
    "gift": ExpenseCategory.gifts,
    "regalos": ExpenseCategory.gifts,
    "regalo": ExpenseCategory.gifts,
    "health": ExpenseCategory.health,
    "salud": ExpenseCategory.health,
    "médico": ExpenseCategory.health,
    "medico": ExpenseCategory.health,
    "home_maintenance": ExpenseCategory.home_maintenance,
    "home maintenance": ExpenseCategory.home_maintenance,
    "hogar": ExpenseCategory.home_maintenance,
    "mantenimiento del hogar": ExpenseCategory.home_maintenance,
    "insurance": ExpenseCategory.insurance,
    "seguro": ExpenseCategory.insurance,
    "seguros": ExpenseCategory.insurance,
    "kids": ExpenseCategory.kids,
    "children": ExpenseCategory.kids,
    "niños": ExpenseCategory.kids,
    "ninos": ExpenseCategory.kids,
    "hijos": ExpenseCategory.kids,
    "other": ExpenseCategory.other,
    "otro": ExpenseCategory.other,
    "otros": ExpenseCategory.other,
    "personal_care": ExpenseCategory.personal_care,
    "personal care": ExpenseCategory.personal_care,
    "cuidado personal": ExpenseCategory.personal_care,
    "pets": ExpenseCategory.pets,
    "pet": ExpenseCategory.pets,
    "mascotas": ExpenseCategory.pets,
    "mascota": ExpenseCategory.pets,
    "rent": ExpenseCategory.rent,
    "alquiler": ExpenseCategory.rent,
    "renta": ExpenseCategory.rent,
    "sports": ExpenseCategory.sports,
    "sport": ExpenseCategory.sports,
    "deportes": ExpenseCategory.sports,
    "deporte": ExpenseCategory.sports,
    "subscriptions": ExpenseCategory.subscriptions,
    "subscription": ExpenseCategory.subscriptions,
    "suscripciones": ExpenseCategory.subscriptions,
    "suscripción": ExpenseCategory.subscriptions,
    "suscripcion": ExpenseCategory.subscriptions,
    "taxes": ExpenseCategory.taxes,
    "tax": ExpenseCategory.taxes,
    "impuestos": ExpenseCategory.taxes,
    "impuesto": ExpenseCategory.taxes,
    "transport": ExpenseCategory.transport,
    "transportation": ExpenseCategory.transport,
    "transporte": ExpenseCategory.transport,
    "travel": ExpenseCategory.travel,
    "viajes": ExpenseCategory.travel,
    "viaje": ExpenseCategory.travel,
    "utilities": ExpenseCategory.utilities,
    "servicios": ExpenseCategory.utilities,
    "servicios públicos": ExpenseCategory.utilities,
    "servicios publicos": ExpenseCategory.utilities,
    "expensas": ExpenseCategory.utilities,
}

# Income category labels (EN/ES + each enum value) → IncomeCategory.
_INCOME_CATEGORY_ALIASES: dict[str, IncomeCategory] = {
    "bonus": IncomeCategory.bonus,
    "bono": IncomeCategory.bonus,
    "bonificación": IncomeCategory.bonus,
    "bonificacion": IncomeCategory.bonus,
    "aguinaldo": IncomeCategory.bonus,
    "card_credits_and_refunds": IncomeCategory.card_credits_and_refunds,
    "card credits and refunds": IncomeCategory.card_credits_and_refunds,
    "card credits": IncomeCategory.card_credits_and_refunds,
    "reintegros de tarjeta": IncomeCategory.card_credits_and_refunds,
    "dividends": IncomeCategory.dividends,
    "dividend": IncomeCategory.dividends,
    "dividendos": IncomeCategory.dividends,
    "freelance": IncomeCategory.freelance,
    "freelancing": IncomeCategory.freelance,
    "independiente": IncomeCategory.freelance,
    "honorarios": IncomeCategory.freelance,
    "gifts": IncomeCategory.gifts,
    "gift": IncomeCategory.gifts,
    "regalos": IncomeCategory.gifts,
    "regalo": IncomeCategory.gifts,
    "investment_returns": IncomeCategory.investment_returns,
    "investment returns": IncomeCategory.investment_returns,
    "returns": IncomeCategory.investment_returns,
    "rendimientos": IncomeCategory.investment_returns,
    "retornos de inversión": IncomeCategory.investment_returns,
    "retornos de inversion": IncomeCategory.investment_returns,
    "other": IncomeCategory.other,
    "otro": IncomeCategory.other,
    "otros": IncomeCategory.other,
    "refunds": IncomeCategory.refunds,
    "refund": IncomeCategory.refunds,
    "reintegros": IncomeCategory.refunds,
    "reembolsos": IncomeCategory.refunds,
    "reembolso": IncomeCategory.refunds,
    "rental_income": IncomeCategory.rental_income,
    "rental income": IncomeCategory.rental_income,
    "ingresos por alquiler": IncomeCategory.rental_income,
    "alquiler": IncomeCategory.rental_income,
    "salary": IncomeCategory.salary,
    "wage": IncomeCategory.salary,
    "wages": IncomeCategory.salary,
    "sueldo": IncomeCategory.salary,
    "salario": IncomeCategory.salary,
    "sales": IncomeCategory.sales,
    "sale": IncomeCategory.sales,
    "ventas": IncomeCategory.sales,
    "venta": IncomeCategory.sales,
}


# Builds a coercer mapping a category label to an enum member. Raises ValueError if unrecognized.
def _category_coercer[T: StrEnum](enum_cls: type[T], aliases: dict[str, T]) -> Callable[[str], T]:
    def coerce(raw: str) -> T:
        category = aliases.get(raw.strip().lower())
        if category is None:
            valid = ", ".join(member.value for member in enum_cls)
            raise ValueError(f"Unknown category '{raw.strip()}'. Use one of: {valid}.")
        return category

    return coerce


_coerce_investment_category = _category_coercer(InvestmentCategory, _INVESTMENT_CATEGORY_ALIASES)
_coerce_expense_category = _category_coercer(ExpenseCategory, _EXPENSE_CATEGORY_ALIASES)
_coerce_income_category = _category_coercer(IncomeCategory, _INCOME_CATEGORY_ALIASES)


# Normalizes a currency code (uppercased) and checks it is supported. Raises ValueError otherwise.
def _coerce_currency(raw: str) -> str:
    code = raw.strip().upper()
    if not is_supported(code):
        valid = ", ".join(sorted(SUPPORTED_CURRENCIES))
        raise ValueError(f"Unsupported currency '{raw.strip()}'. Use one of: {valid}.")
    return code


# Normalizes a ticker (uppercased, trimmed). Raises ValueError if too long.
def _coerce_ticker(raw: str) -> str:
    value = raw.strip().upper()
    if len(value) > 20:
        raise ValueError("Ticker is too long (max 20 characters).")
    return value


# Builds a coercer for a free-text field that trims and enforces a max length.
def _text_coercer(label: str, max_length: int) -> Callable[[str], str]:
    def coerce(raw: str) -> str:
        value = raw.strip()
        if len(value) > max_length:
            raise ValueError(f"{label} is too long (max {max_length} characters).")
        return value

    return coerce


# Date input formats tried after the ISO fast path. Day-first (DD/MM/YYYY) wins ambiguous ties
# (Renly's primary locale is es-AR); the month-first variants only match dates day-first can't
# (e.g. 01/15/2026, where day 15 of month 1 is impossible), so unambiguous US dates still parse.
_DATE_FORMATS = ("%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%m/%d/%Y", "%m-%d-%Y")


# Parses a date from ISO (incl. an ISO datetime's date part) or common locale formats.
def _coerce_date(raw: str) -> date_type:
    text = raw.strip()
    iso_candidate = text.split("T")[0].split(" ")[0]
    try:
        return date_type.fromisoformat(iso_candidate)
    except ValueError:
        pass
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Invalid date '{text}'. Use YYYY-MM-DD (or DD/MM/YYYY).")


_AMOUNT_QUANT = Decimal("0.01")
# 18 total digits minus 2 decimal places leaves 16 integer digits (matches the DB column).
_MAX_AMOUNT_INT_DIGITS = 16
_MAX_AMOUNT = Decimal(10) ** _MAX_AMOUNT_INT_DIGITS


# Normalizes a localized number string to a plain Decimal-parseable form. Handles both "1.234,56"
# (AR/ES) and "1,234.56" (US): with both separators present the rightmost is the decimal mark; a
# lone separator before exactly three digits reads as a thousands group (1.000 / 1,000 → 1000),
# since money carries two decimals, not three.
def _normalize_decimal_string(raw: str) -> str:
    text = raw.strip().replace(" ", "").replace(" ", "")
    has_dot = "." in text
    has_comma = "," in text
    if has_dot and has_comma:
        decimal_sep = "." if text.rfind(".") > text.rfind(",") else ","
        grouping_sep = "," if decimal_sep == "." else "."
        return text.replace(grouping_sep, "").replace(decimal_sep, ".")
    if has_comma:
        return _resolve_single_separator(text, ",")
    if has_dot:
        return _resolve_single_separator(text, ".")
    return text


# Resolves a number string carrying a single separator type as either decimal or thousands grouping.
def _resolve_single_separator(text: str, sep: str) -> str:
    if text.count(sep) > 1:
        return text.replace(sep, "")
    integer, _, fraction = text.partition(sep)
    if len(fraction) == 3 and fraction.isdigit():
        return integer + fraction
    return text.replace(sep, ".")


# Parses a positive monetary amount, quantized to 2 decimals. Raises ValueError on a bad/<=0 value.
def _coerce_amount(raw: str) -> Decimal:
    try:
        value = Decimal(_normalize_decimal_string(raw))
    except InvalidOperation as exc:
        raise ValueError(f"Invalid amount '{raw.strip()}'.") from exc
    if not value.is_finite() or value <= 0:
        raise ValueError("Amount must be greater than zero.")
    # Bound the magnitude before quantizing — quantizing an astronomically large value raises
    # InvalidOperation (not ValueError), which would escape the per-row try/except in the service.
    if value >= _MAX_AMOUNT:
        raise ValueError("Amount is too large.")
    quantized = value.quantize(_AMOUNT_QUANT, rounding=ROUND_HALF_UP)
    if quantized >= _MAX_AMOUNT:
        raise ValueError("Amount is too large.")
    return quantized


# Header aliases shared by the date / amount / currency / notes columns across expense and income.
_DATE_ALIASES = frozenset({"date", "fecha", "día", "dia", "transaction date", "fecha de transacción", "fecha de transaccion", "fecha de operación"})
_AMOUNT_ALIASES = frozenset({"amount", "monto", "importe", "total", "valor", "cantidad", "value"})
_CURRENCY_ALIASES = frozenset({"currency", "moneda", "divisa", "ccy"})
_CATEGORY_ALIASES = frozenset({"category", "categoría", "categoria", "type", "tipo", "rubro"})
_NOTES_ALIASES = frozenset(
    {
        "notes",
        "notas",
        "note",
        "nota",
        "description",
        "descripción",
        "descripcion",
        "detail",
        "detalle",
        "comment",
        "comments",
        "comentario",
        "comentarios",
        "concepto",
        "merchant",
        "comercio",
        "observaciones",
    }
)


# Import spec for investments (top-level entity; dedup on name).
INVESTMENTS_SPEC = ImportSpec(
    entity=ImportEntity.investments,
    dedup_fields=("name",),
    fields=(
        FieldSpec(
            "name",
            True,
            frozenset(
                {"name", "nombre", "investment", "investment name", "activo", "instrumento", "asset", "description", "descripción", "descripcion"}
            ),
            _text_coercer("Name", 255),
        ),
        FieldSpec(
            "category",
            True,
            frozenset({"category", "categoría", "categoria", "type", "tipo", "asset class", "clase"}),
            _coerce_investment_category,
        ),
        FieldSpec(
            "base_currency",
            True,
            frozenset({"base_currency", "base currency", "currency", "moneda", "divisa", "ccy"}),
            _coerce_currency,
        ),
        FieldSpec(
            "ticker",
            False,
            frozenset({"ticker", "symbol", "símbolo", "simbolo", "ticker symbol"}),
            _coerce_ticker,
        ),
        FieldSpec(
            "broker",
            False,
            frozenset({"broker", "bróker", "broker name", "account", "cuenta", "exchange", "alyc"}),
            _text_coercer("Broker", 100),
        ),
        FieldSpec(
            "notes",
            False,
            frozenset({"notes", "notas", "note", "nota", "comment", "comments", "comentario", "comentarios", "observaciones"}),
            _text_coercer("Notes", 500),
        ),
    ),
)

# Import spec for expenses (top-level entity; no natural key, so soft dedup on a composite).
EXPENSES_SPEC = ImportSpec(
    entity=ImportEntity.expenses,
    dedup_fields=("date", "amount", "currency", "category", "notes"),
    fields=(
        FieldSpec("date", True, _DATE_ALIASES, _coerce_date),
        FieldSpec("amount", True, _AMOUNT_ALIASES, _coerce_amount),
        FieldSpec("currency", True, _CURRENCY_ALIASES, _coerce_currency),
        FieldSpec("category", False, _CATEGORY_ALIASES, _coerce_expense_category),
        FieldSpec(
            "payment_method",
            False,
            frozenset({"payment_method", "payment method", "method", "medio de pago", "método de pago", "metodo de pago", "forma de pago", "medio"}),
            _text_coercer("Payment method", 20),
        ),
        FieldSpec("notes", False, _NOTES_ALIASES, _text_coercer("Notes", 500)),
    ),
)

# Import spec for income (top-level entity; no natural key, so soft dedup on a composite).
INCOME_SPEC = ImportSpec(
    entity=ImportEntity.income,
    dedup_fields=("date", "amount", "currency", "category", "notes"),
    fields=(
        FieldSpec("date", True, _DATE_ALIASES, _coerce_date),
        FieldSpec("amount", True, _AMOUNT_ALIASES, _coerce_amount),
        FieldSpec("currency", True, _CURRENCY_ALIASES, _coerce_currency),
        FieldSpec("category", False, _CATEGORY_ALIASES, _coerce_income_category),
        FieldSpec("notes", False, _NOTES_ALIASES, _text_coercer("Notes", 500)),
    ),
)

_SPECS: dict[ImportEntity, ImportSpec] = {
    ImportEntity.investments: INVESTMENTS_SPEC,
    ImportEntity.expenses: EXPENSES_SPEC,
    ImportEntity.income: INCOME_SPEC,
}


# Returns the import spec for an entity.
def get_spec(entity: ImportEntity) -> ImportSpec:
    return _SPECS[entity]
