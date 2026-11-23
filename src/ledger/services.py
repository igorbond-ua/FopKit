from django.db import transaction
from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone

from . import cabinet, nbu, requisites
from .models import IncomeEntry, MonthRecord, PaymentRequisite, TaxSettlementAccount, TaxSettlementOperation
from .money import convert_to_kopiykas, format_kopiykas, format_rate, input_kopiykas, percent_ceil

FIRST_YEAR = 2026
SETTLEMENT_FIRST_YEAR = 2012
TAX_GROUP = 3
SINGLE_TAX_PERCENT = 5
MILITARY_LEVY_PERCENT = 1
ESV_PERCENT = 22
# Minimum monthly wage by year. Add the new value each January.
MIN_WAGE_KOPIYKAS = {2026: 864_700}

MONTH_NAMES = [
    "Січень", "Лютий", "Березень", "Квітень", "Травень", "Червень",
    "Липень", "Серпень", "Вересень", "Жовтень", "Листопад", "Грудень",
]

TAX_COLUMNS = [
    ("single_tax", "single_tax_kopiykas", "single_tax_paid"),
    ("military_levy", "military_levy_kopiykas", "military_levy_paid"),
    ("esv", "esv_kopiykas", "esv_paid"),
]
PAID_FIELDS = {kind: (value_field, paid_field) for kind, value_field, paid_field in TAX_COLUMNS}


def today():
    return timezone.localdate()


def available_years():
    return list(range(FIRST_YEAR, max(FIRST_YEAR, today().year) + 1))


def minimum_esv(year):
    known = [y for y in MIN_WAGE_KOPIYKAS if y <= year] or [min(MIN_WAGE_KOPIYKAS)]
    return percent_ceil(MIN_WAGE_KOPIYKAS[max(known)], ESV_PERCENT)


def month_has_started(year, month):
    current = today()
    return (year, month) <= (current.year, current.month)


def recalculate_month(user, year, month, *, clear_paid=False):
    total = IncomeEntry.objects.filter(
        user=user, received_on__year=year, received_on__month=month
    ).aggregate(total=Sum("amount_uah_kopiykas"))["total"]
    record, _ = MonthRecord.objects.get_or_create(user=user, year=year, month=month)
    record.income_uah_kopiykas = total
    if total is None:
        record.single_tax_kopiykas = None
        record.military_levy_kopiykas = None
    else:
        record.single_tax_kopiykas = percent_ceil(total, SINGLE_TAX_PERCENT)
        record.military_levy_kopiykas = percent_ceil(total, MILITARY_LEVY_PERCENT)
    if month_has_started(year, month) and record.esv_kopiykas is None:
        record.esv_kopiykas = minimum_esv(year)
    if clear_paid:
        record.single_tax_paid = False
        record.military_levy_paid = False
        record.esv_paid = False
    record.save()
    return record


def fill_started_months_esv(user):
    """Store minimum ESV for every started month of the current year and of years that already have data."""
    current = today()
    years = set(
        MonthRecord.objects.filter(user=user, year__gte=FIRST_YEAR).values_list("year", flat=True)
    )
    if current.year >= FIRST_YEAR:
        years.add(current.year)
    for year in sorted(y for y in years if y <= current.year):
        last_month = current.month if year == current.year else 12
        existing = {r.month: r for r in MonthRecord.objects.filter(user=user, year=year)}
        for month in range(1, last_month + 1):
            record = existing.get(month)
            if record is None:
                MonthRecord.objects.create(user=user, year=year, month=month, esv_kopiykas=minimum_esv(year))
            elif record.esv_kopiykas is None:
                record.esv_kopiykas = minimum_esv(year)
                record.save(update_fields=["esv_kopiykas"])


def _apply_income(entry, received_on, currency, amount_minor):
    if currency == IncomeEntry.Currency.UAH:
        entry.amount_minor = None
        entry.rate = None
        entry.amount_uah_kopiykas = amount_minor
    else:
        keep_rate = (
            entry.pk is not None
            and entry.rate is not None
            and entry.currency == currency
            and entry.received_on == received_on
        )
        rate = entry.rate if keep_rate else nbu.official_rate(currency, received_on)
        entry.amount_minor = amount_minor
        entry.rate = rate
        entry.amount_uah_kopiykas = convert_to_kopiykas(amount_minor, rate)
    entry.received_on = received_on
    entry.currency = currency


def add_income(user, received_on, currency, amount_minor):
    entry = IncomeEntry(user=user)
    _apply_income(entry, received_on, currency, amount_minor)
    with transaction.atomic():
        entry.save()
        recalculate_month(user, received_on.year, received_on.month, clear_paid=True)
    return entry


def edit_income(entry, received_on, currency, amount_minor):
    old_month = (entry.received_on.year, entry.received_on.month)
    _apply_income(entry, received_on, currency, amount_minor)
    new_month = (received_on.year, received_on.month)
    with transaction.atomic():
        entry.save()
        for year, month in {old_month, new_month}:
            recalculate_month(entry.user, year, month, clear_paid=True)
    return entry


def delete_income(entry):
    year, month = entry.received_on.year, entry.received_on.month
    with transaction.atomic():
        entry.delete()
        recalculate_month(entry.user, year, month, clear_paid=True)


def _add(total, value):
    if value is None:
        return total
    return value if total is None else total + value


def build_year_table(user, year):
    records = {r.month: r for r in MonthRecord.objects.filter(user=user, year=year)}
    has_data = any(r.has_values() for r in records.values())
    rows = []
    year_sums = [None] * 4
    for quarter in range(4):
        quarter_sums = [None] * 4
        quarter_paid_flags = []
        for month in range(quarter * 3 + 1, quarter * 3 + 4):
            record = records.get(month)
            income = record.income_uah_kopiykas if record else None
            cells = [{"value": income, "paid": False, "action": "month"}]
            quarter_sums[0] = _add(quarter_sums[0], income)
            for index, (kind, value_field, paid_field) in enumerate(TAX_COLUMNS, start=1):
                value = getattr(record, value_field) if record else None
                if kind == "esv" and user.skip_esv:
                    value = None
                paid = bool(record and value is not None and getattr(record, paid_field))
                cells.append({
                    "value": value,
                    "paid": paid,
                    "action": "toggle" if value is not None else "",
                    "toggle_url": reverse("toggle_paid", args=[year, month, kind]) if value is not None else "",
                })
                quarter_sums[index] = _add(quarter_sums[index], value)
                if value is not None:
                    quarter_paid_flags.append(paid)
            rows.append({"css": "", "label": MONTH_NAMES[month - 1], "month": month, "cells": cells})
        quarter_paid = bool(quarter_paid_flags) and all(quarter_paid_flags)
        rows.append({
            "css": "quarter paid-row" if quarter_paid else "quarter",
            "label": f"{quarter + 1}-квартал",
            "month": "",
            "cells": [{"value": value, "paid": False, "action": ""} for value in quarter_sums],
        })
        year_sums = [_add(total, value) for total, value in zip(year_sums, quarter_sums)]
    rows.append({
        "css": "year-total",
        "label": "Разом за рік",
        "month": "",
        "cells": [{"value": value, "paid": False, "action": ""} for value in year_sums],
    })
    return rows, has_data


def entry_payload(entry):
    foreign = entry.currency != IncomeEntry.Currency.UAH
    input_minor = entry.amount_minor if foreign else entry.amount_uah_kopiykas
    return {
        "id": entry.id,
        "date": entry.received_on.isoformat(),
        "dateLabel": entry.received_on.strftime("%d.%m.%Y"),
        "uah": format_kopiykas(entry.amount_uah_kopiykas),
        "currency": entry.currency,
        "currencyLabel": entry.get_currency_display(),
        "amount": format_kopiykas(entry.amount_minor) if foreign else "—",
        "amountInput": input_kopiykas(input_minor),
        "rate": format_rate(entry.rate) if foreign else "—",
        "singleTax": format_kopiykas(percent_ceil(entry.amount_uah_kopiykas, SINGLE_TAX_PERCENT)),
        "militaryLevy": format_kopiykas(percent_ceil(entry.amount_uah_kopiykas, MILITARY_LEVY_PERCENT)),
    }


PAYMENT_NAMES = {
    PaymentRequisite.Kind.SINGLE_TAX: "Єдиний податок",
    PaymentRequisite.Kind.ESV: "Єдиний внесок",
    PaymentRequisite.Kind.MILITARY_LEVY: "Військовий збір",
}
REQUISITE_FIELDS = ("recipient", "recipient_code", "bank", "iban", "code")


def refresh_requisites(user):
    """Fetch requisites from the tax service and return the kinds whose values changed."""
    fetched = requisites.fetch(user.tax_region, user.community)
    source_url = requisites.page_url(user.tax_region)
    now = timezone.now()
    changed = []
    with transaction.atomic():
        existing = {r.kind: r for r in PaymentRequisite.objects.filter(user=user)}
        for kind in PaymentRequisite.Kind:
            values = {field: getattr(fetched[kind.value], field) for field in REQUISITE_FIELDS}
            record = existing.get(kind.value) or PaymentRequisite(user=user, kind=kind.value, changed_at=now)
            if record.pk is None or any(getattr(record, f) != v for f, v in values.items()):
                changed.append(kind)
                record.changed_at = now
            for field, value in values.items():
                setattr(record, field, value)
            record.source_url = source_url
            record.checked_at = now
            record.save()
    return changed


def payment_purpose(user, kind):
    return f"*;101;{user.tax_number or 'РНОКПП'};{PAYMENT_NAMES[kind]};;;"


def requisite_slips(user):
    stored = {r.kind: r for r in PaymentRequisite.objects.filter(user=user)}
    return [
        {
            "title": kind.label,
            "code_label": "Символ звітності" if kind == PaymentRequisite.Kind.ESV else "Код класифікації доходів",
            "requisite": stored.get(kind.value),
            "purpose": payment_purpose(user, kind),
        }
        for kind in PaymentRequisite.Kind
    ]


def settlement_years():
    """List of years available in the settlement year picker (2012..current)."""
    return list(range(SETTLEMENT_FIRST_YEAR, max(SETTLEMENT_FIRST_YEAR, today().year) + 1))


def sync_settlements(user, authorization: str, year: int) -> None:
    """
    Fetch settlements from cabinet.tax.gov.ua and persist them.
    Replaces all existing rows for this user+year with fresh data.
    Raises cabinet.CabinetError / cabinet.SignatureExpiredError on failure.
    """
    now = timezone.now()
    accounts_data = cabinet.fetch_settlements(authorization, year)

    with transaction.atomic():
        # Delete existing data for this year and re-create
        TaxSettlementAccount.objects.filter(user=user, year=year).delete()

        for acc in accounts_data:
            account = TaxSettlementAccount.objects.create(
                user=user,
                year=year,
                account_id=acc["account_id"],
                tax_office_code=acc["tax_office_code"],
                tax_office_name=acc["tax_office_name"],
                payment_code=acc["payment_code"],
                payment_name=acc["payment_name"],
                charged_kopiykas=acc["charged"],
                paid_kopiykas=acc["paid"],
                returned_kopiykas=acc["returned"],
                penalty_kopiykas=acc["penalty"],
                arrears_kopiykas=acc["arrears"],
                overpaid_kopiykas=acc["overpaid"],
                penalty_balance_kopiykas=acc["penalty_balance"],
                total_balance_kopiykas=acc["total_balance"],
                budget_iban=acc["budget_iban"],
                synced_at=now,
            )
            # Fetch first page of operations for each account
            ops = cabinet.fetch_operations(
                authorization, year, acc["tax_office_code"], acc["account_id"], page=0
            )
            TaxSettlementOperation.objects.bulk_create([
                TaxSettlementOperation(
                    account=account,
                    operation_date=op["operation_date"],
                    operation_code=op["operation_code"],
                    operation_name=op["operation_name"],
                    amount_kopiykas=op["amount"],
                    charged_kopiykas=op["charged"],
                    paid_returned_kopiykas=op["paid_returned"],
                    balance_kopiykas=op["balance"],
                    penalty_kopiykas=op["penalty"],
                    penalty_balance_kopiykas=op["penalty_balance"],
                )
                for op in ops
                if op["operation_date"] is not None
            ])


def get_settlements(user, year: int):
    """Return list of TaxSettlementAccount objects with prefetched operations."""
    return list(
        TaxSettlementAccount.objects.filter(user=user, year=year)
        .prefetch_related("operations")
        .order_by("payment_code", "id")
    )


def dialog_data(year_entries, recent_entries):
    entries = {}
    months = {}
    for entry in year_entries:
        entries[entry.id] = entry_payload(entry)
        months.setdefault(entry.received_on.month, []).append(entry.id)
    for entry in recent_entries:
        entries.setdefault(entry.id, entry_payload(entry))
    return {"entries": entries, "months": months, "monthNames": MONTH_NAMES}
