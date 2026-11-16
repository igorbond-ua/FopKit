from decimal import ROUND_CEILING, Decimal, InvalidOperation

MAX_AMOUNT_MINOR = 10**13


class AmountError(ValueError):
    pass


def parse_amount_minor(text):
    """Parse a user-entered amount into cents or kopiykas, rounding up."""
    cleaned = str(text).strip().replace("\u00a0", "").replace(" ", "").replace(",", ".")
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        raise AmountError("Введіть суму числом, наприклад 1250,50.")
    if not value.is_finite() or value <= 0:
        raise AmountError("Сума має бути більшою за нуль.")
    minor = int((value * 100).to_integral_value(rounding=ROUND_CEILING))
    if minor > MAX_AMOUNT_MINOR:
        raise AmountError("Сума завелика.")
    return minor


def convert_to_kopiykas(amount_minor, rate):
    return int((Decimal(amount_minor) * rate).to_integral_value(rounding=ROUND_CEILING))


def percent_ceil(kopiykas, percent):
    return -(-kopiykas * percent // 100)


def format_kopiykas(value):
    if value is None:
        return "—"
    sign = "-" if value < 0 else ""
    whole, fraction = divmod(abs(value), 100)
    whole_text = f"{whole:,}".replace(",", "\u00a0")
    return f"{sign}{whole_text},{fraction:02d}"


def input_kopiykas(value):
    whole, fraction = divmod(value, 100)
    return f"{whole},{fraction:02d}"


def format_rate(rate):
    if rate is None:
        return "—"
    text = format(rate.normalize(), "f")
    whole, _, fraction = text.partition(".")
    return f"{whole},{fraction.ljust(4, '0')}"
