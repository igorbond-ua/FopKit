"""
Client for the cabinet.tax.gov.ua private API.

Auth flow (OAuth2 Resource Owner Password Credentials):
1. Browser signs the РНОКПП with KEP (CAdES-BES, attached, Base64).
2. Our server POSTs to /ws/auth/oauth/token with:
   - grant_type=password
   - username="{РНОКПП}-{РНОКПП}-{timestamp_ms}"
   - password={Base64 CAdES}
   - Authorization: Basic <client_credentials>
3. Cabinet returns access_token (Bearer).
4. All subsequent API calls use Authorization: Bearer {access_token}.
"""

import logging
from decimal import Decimal

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://cabinet.tax.gov.ua/ws/api"
AUTH_URL = "https://cabinet.tax.gov.ua/ws/auth/oauth/token"
# OAuth2 client credentials (from cabinet SPA bundle)
CLIENT_BASIC = "QUU2ODY3NjY0QzA5NkM4M0UwNTMwMTAxMDA3RjQ1RjQ6QUU2ODY3NjY0QzA5NkM4M0UwNTMwMTAxMDA3RjQ1RjQ="
TIMEOUT = 15


class CabinetError(Exception):
    """Returned a non-2xx response or failed to parse."""


class SignatureExpiredError(CabinetError):
    """The cabinet rejected the signature (likely expired)."""


def get_token(username: str, password: str) -> str:
    """
    Exchange a signed username+password for a Bearer access_token.

    username = "{РНОКПП}-{РНОКПП}-{timestamp_ms}"
    password = Base64-encoded CAdES signature of the РНОКПП
    """
    try:
        resp = requests.post(
            AUTH_URL,
            data={"grant_type": "password", "username": username, "password": password},
            headers={
                "Authorization": f"Basic {CLIENT_BASIC}",
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        raise CabinetError(f"Не вдалося з'єднатися з кабінетом ДПС: {exc}") from exc

    if not resp.ok:
        raw = resp.text[:500]
        logger.warning("[cabinet] token error %s: %s", resp.status_code, raw)
        try:
            detail = resp.json().get("error_description") or raw
        except Exception:
            detail = raw
        if resp.status_code in (400, 401, 403):
            raise SignatureExpiredError(f"Кабінет ДПС відхилив підпис (HTTP {resp.status_code}): {detail}")
        raise CabinetError(f"Кабінет ДПС повернув помилку {resp.status_code}: {detail}")

    try:
        return resp.json()["access_token"]
    except Exception as exc:
        raise CabinetError("Не вдалося отримати токен від кабінету ДПС.") from exc


def _session(access_token: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    })
    return s


def _hrn_to_kopiykas(value) -> int | None:
    """Convert a float UAH value from the API into integer kopiykas."""
    if value is None:
        return None
    return int(Decimal(str(value)) * 100)


def _classification_code(account) -> int:
    """Budget classification code from the cabinet's account string, e.g. "30 11011700 UA46…"."""
    for part in str(account or "").split():
        if len(part) == 8 and part.isdigit():
            return int(part)
    return 0


def _settlement_balance(item) -> int | None:
    """
    Settlement balance as the cabinet shows it in the operations table:
    overpayment minus tax debt, including charges already made for the rest of the year.
    The *End fields hold that balance; the *0 fields are the balance as of today.
    """
    for overpaid_key, debt_key in (("pereplEnd", "nedoimEnd"), ("perepl0", "nedoim0")):
        overpaid = _hrn_to_kopiykas(item.get(overpaid_key))
        debt = _hrn_to_kopiykas(item.get(debt_key))
        if overpaid is not None or debt is not None:
            return (overpaid or 0) - abs(debt or 0)
    return None


def fetch_settlements(access_token: str, year: int) -> list[dict]:
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
        resp = _session(access_token).get(url, params={"year": year}, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise CabinetError(f"Не вдалося з'єднатися з кабінетом ДПС: {exc}") from exc

    if resp.status_code == 401 or (
        resp.status_code in (400, 403)
        and "підпис" in resp.text.lower()
    ):
        raise SignatureExpiredError("Кабінет ДПС не прийняв вхід. Натисніть «Синхронізувати» ще раз.")

    if not resp.ok:
        raise CabinetError(f"Кабінет ДПС повернув помилку {resp.status_code}.")

    try:
        data = resp.json()
    except Exception as exc:
        preview = resp.text[:300].replace("\n", " ")
        raise CabinetError(f"Кабінет ДПС повернув нечитабельну відповідь (HTTP {resp.status_code}): {preview}") from exc

    accounts = []
    for item in data:
        accounts.append({
            "account_id": str(item.get("idpmnt", "")),
            "tax_office_code": int(item.get("cSti") or 0),
            "tax_office_name": item.get("nameSti", ""),
            "payment_code": _classification_code(item.get("plat1")),
            "payment_name": item.get("namePlt", ""),
            "charged": _hrn_to_kopiykas(item.get("narah0")),
            "paid": _hrn_to_kopiykas(item.get("splbd0")),
            "returned": _hrn_to_kopiykas(item.get("povbd0")),
            "penalty": _hrn_to_kopiykas(item.get("penia0")),
            "arrears": _hrn_to_kopiykas(item.get("nedoim0")),
            "overpaid": _hrn_to_kopiykas(item.get("perepl0")),
            "penalty_balance": _hrn_to_kopiykas(item.get("sldpn0")),
            "total_balance": _settlement_balance(item),
            "budget_iban": item.get("budgetAccountIban", ""),
        })
    return accounts


def fetch_operations(access_token: str, year: int, tax_office_code: int, account_id: str, page: int = 0) -> list[dict]:
    """
    Fetch one page of operations for a single settlement account.

    Returns a list of operation dicts, each containing:
      operation_date, operation_code, operation_name,
      amount, charged, paid_returned, balance, penalty, penalty_balance
    """
    url = f"{BASE_URL}/ta/splatp/{year}/{tax_office_code}/{account_id}/pa"
    try:
        resp = _session(access_token).get(url, params={"page": page}, timeout=TIMEOUT)
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
