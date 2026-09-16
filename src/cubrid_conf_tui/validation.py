"""Conservative configuration-text semantics for validated metadata."""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .document import ConfigurationError
from .metadata import MetadataEntry, RawValue

INTEGER = re.compile(r"[+-]?\d+")
DECIMAL = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")
SIZE = re.compile(
    r"(?P<number>\+?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)"
    r"(?P<unit>B|K|KB|M|MB|G|GB|T|TB|P|PB)?",
    re.IGNORECASE,
)
TIME = re.compile(
    r"(?P<number>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)"
    r"(?P<unit>ms|msec|s|sec|min|h)?",
    re.IGNORECASE,
)
SIZE_FACTORS = {
    "B": 1,
    "K": 1024,
    "KB": 1024,
    "M": 1024**2,
    "MB": 1024**2,
    "G": 1024**3,
    "GB": 1024**3,
    "T": 1024**4,
    "TB": 1024**4,
    "P": 1024**5,
    "PB": 1024**5,
}
TIME_FACTORS = {
    "MS": 1,
    "MSEC": 1,
    "S": 1000,
    "SEC": 1000,
    "MIN": 60_000,
    "H": 3_600_000,
}
TRUE_BOOLEAN_TEXT = frozenset({"yes", "y", "1", "true", "on"})
FALSE_BOOLEAN_TEXT = frozenset({"no", "n", "0", "false", "off"})


@dataclass(frozen=True)
class ValidationOutcome:
    limitations: tuple[str, ...]


def _display(raw: RawValue) -> str | None:
    if raw.state != "value":
        return None
    if isinstance(raw.value, float):
        return format(raw.value, "g")
    return str(raw.value)


def _range_text(metadata: MetadataEntry, suffix: str = "") -> str:
    lower = _display(metadata.lower)
    upper = _display(metadata.upper)
    if lower is not None and upper is not None:
        return f" from {lower} to {upper}{suffix}"
    if lower is not None:
        return f" at least {lower}{suffix}"
    if upper is not None:
        return f" at most {upper}{suffix}"
    return ""


def _range_is_authoritative(metadata: MetadataEntry) -> bool:
    return (
        metadata.semantics.bounds_source == "static"
        and not metadata.semantics.unit_adjusted
        and _artifact_role_is_authoritative(metadata)
    )


def _artifact_role_is_authoritative(metadata: MetadataEntry) -> bool:
    role = metadata.provenance.artifact.role
    return (role == "server" and metadata.server and not metadata.client) or (
        role == "client" and metadata.client and not metadata.server
    )


def _has_raw_bounds(metadata: MetadataEntry) -> bool:
    return metadata.lower.state == "value" or metadata.upper.state == "value"


def validation_limitations(metadata: MetadataEntry) -> tuple[str, ...]:
    limitations: list[str] = []
    semantics = metadata.semantics
    if semantics.bounds_source == "helper_cpu":
        limitations.append("helper CPU bounds are displayed but not enforced")
    if semantics.unit_adjusted:
        limitations.append("adjusted-unit bounds are displayed but not enforced")
    if (
        semantics.bounds_source == "static"
        and not semantics.unit_adjusted
        and _has_raw_bounds(metadata)
        and not _artifact_role_is_authoritative(metadata)
    ):
        limitations.append(
            "bounds from a different or shared artifact role are displayed "
            "but not enforced"
        )
    if metadata.default.state == "value" and not _artifact_role_is_authoritative(
        metadata
    ):
        limitations.append(
            "compiled default from a different or shared artifact role is not universal"
        )
    if metadata.type_name == "keyword" and semantics.keywords is None:
        limitations.append(
            "keyword table unavailable; raw keyword IDs are not used as "
            "configuration text"
        )
    if metadata.has_custom_callbacks:
        limitations.append("custom callback constraints are unavailable")
    limitations.append("startup/cross-parameter checks are unavailable")
    return tuple(limitations)


def validation_description(metadata: MetadataEntry) -> str:
    semantics = metadata.semantics
    if metadata.type_name == "boolean":
        rule = "Validation: boolean yes/no/default selector"
    elif semantics.unit == "size":
        rule = "Validation: size unit B, K/KB, M/MB, G/GB, T/TB or P/PB" + (
            _range_text(metadata, " bytes") if _range_is_authoritative(metadata) else ""
        )
    elif semantics.unit == "time":
        rule = "Validation: time unit ms/msec, s/sec, min or h" + (
            _range_text(metadata, " milliseconds")
            if _range_is_authoritative(metadata)
            else ""
        )
    elif metadata.type_name == "integer":
        rule = "Validation: whole decimal integer"
        if _range_is_authoritative(metadata):
            rule = "Validation: integer" + _range_text(metadata)
    elif metadata.type_name == "bigint":
        rule = "Validation: unsigned whole decimal integer"
        if _range_is_authoritative(metadata):
            rule += _range_text(metadata)
    elif metadata.type_name == "float":
        rule = "Validation: finite decimal float"
        if _range_is_authoritative(metadata):
            rule = "Validation: float" + _range_text(metadata)
    elif metadata.type_name == "string":
        rule = "Validation: string; empty text is distinct from null/default"
    elif metadata.type_name == "integer_list":
        rule = "Validation: comma-separated integer list; null/0 is a null sentinel"
    elif metadata.type_name == "keyword" and semantics.keywords:
        rule = "Validation: known keyword: " + ", ".join(
            keyword.text for keyword in semantics.keywords
        )
    elif metadata.type_name == "keyword":
        rule = "Validation: keyword table unavailable"
    else:
        rule = "Validation: type semantics unavailable"

    return rule + "\nLimited validation: " + "; ".join(validation_limitations(metadata))


def configuration_default_text(metadata: MetadataEntry) -> str | None:
    raw = metadata.default
    if (
        raw.state != "value"
        or metadata.semantics.bounds_source == "helper_cpu"
        or metadata.semantics.unit_adjusted
        or not _artifact_role_is_authoritative(metadata)
    ):
        return None
    value = raw.value
    if metadata.type_name == "boolean" and isinstance(value, bool):
        return "yes" if value else "no"
    if metadata.type_name == "keyword" and metadata.semantics.keywords:
        return next(
            (
                keyword.text
                for keyword in metadata.semantics.keywords
                if keyword.value == value
            ),
            None,
        )
    if metadata.type_name == "integer_list" and isinstance(value, list):
        return ",".join(str(item) for item in value)
    if metadata.type_name in {"integer", "bigint", "float", "string"}:
        return str(value)
    return None


def configuration_text_description(metadata: MetadataEntry) -> str:
    value = configuration_default_text(metadata)
    if value is None:
        return "Configuration default text: unavailable with current role evidence"
    return f"Configuration default text: {value}"


def describe_assignment(value: str | None, metadata: MetadataEntry | None) -> str:
    if value is None:
        return "<absent>"
    scalar, _ = unquote_configuration_text(value)
    if scalar == "":
        if value:
            return f"{value} (empty text)"
        return "<empty text>"
    normalized = scalar.lower()
    if normalized == "default":
        return f"{value} (default sentinel)"
    if metadata is None:
        return value
    if metadata.type_name == "boolean":
        if normalized in FALSE_BOOLEAN_TEXT:
            return f"{value} (false)"
        if normalized in TRUE_BOOLEAN_TEXT:
            return f"{value} (true)"
    if metadata.type_name in {"string", "integer_list"} and normalized in {
        "null",
        "0",
    }:
        return f"{value} (null sentinel)"
    if normalized == "0" and metadata.type_name in {"integer", "bigint", "float"}:
        return f"{value} (zero)"
    return value


def unquote_configuration_text(value: str) -> tuple[str, str | None]:
    """Return CUBRID's trimmed scalar plus a complete surrounding quote."""
    if len(value) >= 2 and value[0] in {'"', "'"} and value[-1] == value[0]:
        return value[1:-1].strip(" \t"), value[0]
    return value, None


def parse_boolean_text(value: str) -> bool | None:
    scalar, _ = unquote_configuration_text(value)
    normalized = scalar.lower()
    if normalized in TRUE_BOOLEAN_TEXT:
        return True
    if normalized in FALSE_BOOLEAN_TEXT:
        return False
    return None


def replace_scalar_preserving_quotes(original: str | None, replacement: str) -> str:
    if original is None:
        return replacement
    _, quote = unquote_configuration_text(original)
    if quote is None:
        return replacement
    inner = original[1:-1]
    leading_length = len(inner) - len(inner.lstrip(" \t"))
    trailing_start = max(leading_length, len(inner.rstrip(" \t")))
    return quote + inner[:leading_length] + replacement + inner[trailing_start:] + quote


def _decimal(value: str, reason: str) -> Decimal:
    if not DECIMAL.fullmatch(value):
        raise ConfigurationError(f"Invalid value: expected {reason}.")
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise ConfigurationError(f"Invalid value: expected {reason}.") from error
    if not parsed.is_finite():
        raise ConfigurationError(f"Invalid value: expected {reason}.")
    return parsed


def _bounded(metadata: MetadataEntry, value: Decimal, suffix: str = "") -> None:
    if not _range_is_authoritative(metadata):
        return
    if metadata.lower.state == "value":
        lower = Decimal(str(metadata.lower.value))
        if value < lower:
            raise ConfigurationError(
                f"Invalid value: expected at least {metadata.lower.value}{suffix}."
            )
    if metadata.upper.state == "value":
        upper = Decimal(str(metadata.upper.value))
        if value > upper:
            raise ConfigurationError(
                f"Invalid value: expected at most {metadata.upper.value}{suffix}."
            )


def _unit_value(metadata: MetadataEntry, value: str) -> Decimal:
    pattern = SIZE if metadata.semantics.unit == "size" else TIME
    match = pattern.fullmatch(value)
    label = (
        "supported size unit"
        if metadata.semantics.unit == "size"
        else "supported time unit"
    )
    if match is None:
        raise ConfigurationError(f"Invalid value: expected a {label}.")
    number = _decimal(match.group("number"), label)
    if metadata.semantics.unit == "size" and number < 0:
        raise ConfigurationError("Invalid value: size cannot be negative.")
    unit = match.group("unit")
    if metadata.semantics.unit == "time" and number < 0 and unit is not None:
        raise ConfigurationError(
            "Invalid value: a negative time sentinel cannot have a unit."
        )
    factors = SIZE_FACTORS if metadata.semantics.unit == "size" else TIME_FACTORS
    factor = factors[
        (unit or ("B" if metadata.semantics.unit == "size" else "MS")).upper()
    ]
    converted = number * factor
    if converted < -(2**63) or converted >= 2**64:
        raise ConfigurationError("Invalid value: unit-bearing value is out of range.")
    return Decimal(int(converted))


def validate_configuration_value(
    metadata: MetadataEntry, value: str
) -> ValidationOutcome:
    limitations = list(validation_limitations(metadata))

    scalar, _ = unquote_configuration_text(value)
    normalized = scalar.lower()
    if normalized == "default":
        return ValidationOutcome(tuple(limitations))

    if metadata.semantics.unit != "none":
        parsed = _unit_value(metadata, scalar)
        _bounded(
            metadata,
            parsed,
            " bytes" if metadata.semantics.unit == "size" else " milliseconds",
        )
        return ValidationOutcome(tuple(limitations))

    if metadata.type_name == "boolean":
        if normalized not in TRUE_BOOLEAN_TEXT | FALSE_BOOLEAN_TEXT:
            raise ConfigurationError("Invalid value: expected boolean yes or no.")
    elif metadata.type_name == "integer":
        if not INTEGER.fullmatch(scalar):
            raise ConfigurationError("Invalid value: expected a whole decimal integer.")
        parsed = Decimal(scalar)
        if parsed < -(2**31) or parsed >= 2**31:
            raise ConfigurationError("Invalid value: integer is out of range.")
        _bounded(metadata, parsed)
    elif metadata.type_name == "bigint":
        if not INTEGER.fullmatch(scalar):
            raise ConfigurationError(
                "Invalid value: expected an unsigned whole decimal integer."
            )
        parsed = Decimal(scalar)
        if parsed < 0 or parsed >= 2**64:
            raise ConfigurationError("Invalid value: unsigned integer is out of range.")
        _bounded(metadata, parsed)
    elif metadata.type_name == "float":
        parsed = _decimal(scalar, "finite decimal number")
        if abs(parsed) > Decimal("3.4028235e38"):
            raise ConfigurationError("Invalid value: float is out of range.")
        _bounded(metadata, parsed)
    elif metadata.type_name == "string":
        pass
    elif metadata.type_name == "integer_list":
        if normalized not in {"null", "0"}:
            items = scalar.split(",")
            if not 1 <= len(items) <= 1023 or any(
                not INTEGER.fullmatch(item) for item in items
            ):
                raise ConfigurationError(
                    "Invalid value: expected up to 1023 comma-separated "
                    "decimal integers."
                )
            if any(not -(2**31) <= int(item) < 2**31 for item in items):
                raise ConfigurationError("Invalid value: list integer is out of range.")
    elif metadata.type_name == "keyword":
        if metadata.semantics.keywords is None:
            pass
        elif normalized not in {
            keyword.text.lower() for keyword in metadata.semantics.keywords
        }:
            raise ConfigurationError("Invalid value: expected a known keyword.")
    else:
        limitations.insert(0, "type semantics are unavailable")
    return ValidationOutcome(tuple(limitations))
