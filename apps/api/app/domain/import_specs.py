# Per-entity import specs: target fields, header aliases for auto-detection, and value coercers.
# The import engine is generic; each importable entity contributes one spec here.

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from app.domain.currency import SUPPORTED_CURRENCIES, is_supported
from app.models.investment import InvestmentCategory


# Supported import data types. Investments first; more entities are added as the engine is reused.
class ImportEntity(StrEnum):
    investments = "investments"


# A single target field in an import spec. coerce raises ValueError(message) on an invalid value.
@dataclass(frozen=True)
class FieldSpec:
    key: str
    required: bool
    aliases: frozenset[str]
    coerce: Callable[[str], object]


# An import spec for one entity: its target fields and the field used to detect duplicates.
@dataclass(frozen=True)
class ImportSpec:
    entity: ImportEntity
    fields: tuple[FieldSpec, ...]
    dedup_field: str


# Category labels (EN/ES + each enum value) → InvestmentCategory, for the category column.
_CATEGORY_ALIASES: dict[str, InvestmentCategory] = {
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


# Maps a category label to an InvestmentCategory. Raises ValueError if unrecognized.
def _coerce_category(raw: str) -> InvestmentCategory:
    category = _CATEGORY_ALIASES.get(raw.strip().lower())
    if category is None:
        valid = ", ".join(member.value for member in InvestmentCategory)
        raise ValueError(f"Unknown category '{raw.strip()}'. Use one of: {valid}.")
    return category


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


# Import spec for investments (top-level entity; dedup on name).
INVESTMENTS_SPEC = ImportSpec(
    entity=ImportEntity.investments,
    dedup_field="name",
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
            _coerce_category,
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

_SPECS: dict[ImportEntity, ImportSpec] = {
    ImportEntity.investments: INVESTMENTS_SPEC,
}


# Returns the import spec for an entity.
def get_spec(entity: ImportEntity) -> ImportSpec:
    return _SPECS[entity]
