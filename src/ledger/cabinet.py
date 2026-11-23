"""
Client for the cabinet.tax.gov.ua private API.

Authorization header format (per official docs):
  РНОКПП signed with an internal CAdES signature that includes
  the signer's certificate and a timestamp, encoded in Base64.

The browser performs the signing (via kep.js) and sends only
the resulting Base64 string to our server.  We pass it straight
through as the Authorization header.
"""

import logging
from decimal import Decimal

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://cabinet.tax.gov.ua/ws/public_api"
TIMEOUT = 30


class CabinetError(Exception):
    """Returned a non-2xx response or failed to parse."""


class SignatureExpiredError(CabinetError):
    """The cabinet rejected the signature (likely expired)."""


def _session(authorization: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "Authorization": authorization,
        "Accept": "application/json",
        "Content-Type": "application/json",
    })
    return s


def _hrn_to_kopiykas(value) -> int | None:
    """Convert a float UAH value from the API into integer kopiykas."""
    if value is None:
        return None
    return int(Decimal(str(value)) * 100)


def fetch_settlements(authorization: str, year: int) -> list[dict]:
    """
    Fetch the settlement summary for *year*.

    Returns a list of account dicts, each containing:
      account_id, tax_office_code, tax_office_name,
      payment_code, payment_name,
      charged, paid, returned, penalty, arrears, overpaid,
      penalty_balance, total_balance, budget_iban
    """
    url = f"{BASE_URL}/ta/splatp"
    try:
        resp = _session(authorization).get(url, params={"year": year}, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise CabinetError(f"Не вдалося з'єднатися з кабінетом ДПС: {exc}") from exc

    if resp.status_code == 401 or (
        resp.status_code in (400, 403)
        and "підпис" in resp.text.lower()
    ):
        raise SignatureExpiredError("Підпис відхилено кабінетом ДПС.")

    if not resp.ok:
        raise CabinetError(f"Кабінет ДПС повернув помилку {resp.status_code}.")

    try:
        data = resp.json()
    except Exception as exc:
        raise CabinetError("Кабінет ДПС повернув нечитабельну відповідь.") from exc

    accounts = []
    for item in data:
        accounts.append({
            "account_id": str(item.get("idpmnt", "")),
            "tax_office_code": int(item.get("cSti", 0)),
            "tax_office_name": item.get("nameSti", ""),
            "payment_code": int(item.get("plat1", 0)),
            "payment_name": item.get("namePlt", ""),
            "charged": _hrn_to_kopiykas(item.get("narah0")),
            "paid": _hrn_to_kopiykas(item.get("splbd0")),
            "returned": _hrn_to_kopiykas(item.get("povbd0")),
            "penalty": _hrn_to_kopiykas(item.get("penia0")),
            "arrears": _hrn_to_kopiykas(item.get("nedoim0")),
            "overpaid": _hrn_to_kopiykas(item.get("perepl0")),
            "penalty_balance": _hrn_to_kopiykas(item.get("sldpn0")),
            "total_balance": _hrn_to_kopiykas(item.get("debtAll")),
            "budget_iban": item.get("budgetAccountIban", ""),
        })
    return accounts


def fetch_operations(authorization: str, year: int, tax_office_code: int, account_id: str, page: int = 0) -> list[dict]:
    """
    Fetch one page of operations for a single settlement account.

    Returns a list of operation dicts, each containing:
      operation_date, operation_code, operation_name,
      amount, charged, paid_returned, balance, penalty, penalty_balance
    """
    url = f"{BASE_URL}/ta/splatp/{year}/{tax_office_code}/{account_id}/pa"
    try:
        resp = _session(authorization).get(url, params={"page": page}, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise CabinetError(f"Не вдалося отримати операції: {exc}") from exc

    if resp.status_code == 401 or (
        resp.status_code in (400, 403)
        and "підпис" in resp.text.lower()
    ):
        raise SignatureExpiredError("Підпис відхилено кабінетом ДПС.")

    if not resp.ok:
        logger.warning("Cabinet operations %s %s page %d → %d", account_id, year, page, resp.status_code)
        return []

    try:
        payload = resp.json()
    except Exception:
        return []

    items = payload.get("content", payload) if isinstance(payload, dict) else payload
    ops = []
    for item in items:
        date_raw = item.get("dateoper", "")
        # API date format: "DD.MM.YYYY" or ISO
        try:
            from datetime import date
            if "." in date_raw:
                d, m, y = date_raw.split(".")
                op_date = date(int(y), int(m), int(d))
            else:
                from datetime import date as _date
                op_date = _date.fromisoformat(date_raw[:10])
        except Exception:
            op_date = None

        ops.append({
            "operation_date": op_date,
            "operation_code": str(item.get("vidpa", "")),
            "operation_name": item.get("namevid", ""),
            "amount": _hrn_to_kopiykas(item.get("isnull0")),
            "charged": _hrn_to_kopiykas(item.get("narah0")),
            "paid_returned": _hrn_to_kopiykas(item.get("splpov0")),
            "balance": _hrn_to_kopiykas(item.get("sld0")),
            "penalty": _hrn_to_kopiykas(item.get("penia0")),
            "penalty_balance": _hrn_to_kopiykas(item.get("sldpn0")),
        })
    return ops
