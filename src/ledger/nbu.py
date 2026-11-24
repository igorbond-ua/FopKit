import json
import logging
from datetime import timedelta
from decimal import Decimal

import httpx

logger = logging.getLogger(__name__)

RATE_URL = (
    "https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange"
    "?valcode={code}&date={day:%Y%m%d}&json"
)
CURRENCY_CODES = {"usd": "USD", "eur": "EUR"}
MAX_DAYS_BACK = 10


class RateUnavailable(Exception):
    pass


def rate_date_for(day):
    """Saturday and Sunday use Friday's official rate."""
    weekday = day.weekday()
    if weekday == 5:
        return day - timedelta(days=1)
    if weekday == 6:
        return day - timedelta(days=2)
    return day


def fetch_rate(code, day):
    url = RATE_URL.format(code=code, day=day)
    try:
        response = httpx.get(url, timeout=10)
        response.raise_for_status()
        data = json.loads(response.text, parse_float=Decimal)
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("NBU rate request failed for %s on %s: %s", code, day, exc)
        raise RateUnavailable from exc
    for item in data:
        if item.get("cc") == code and item.get("rate"):
            return Decimal(item["rate"])
    return None


def official_rate(currency, day):
    """Latest NBU rate published no later than the given day."""
    code = CURRENCY_CODES[currency]
    probe = rate_date_for(day)
    for _ in range(MAX_DAYS_BACK):
        rate = fetch_rate(code, probe)
        if rate:
            return rate
        probe -= timedelta(days=1)
    raise RateUnavailable
