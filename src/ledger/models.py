from django.contrib.auth.models import AbstractUser
from django.db import models

from .requisites import REGIONS


class User(AbstractUser):
    username = models.CharField("логін", max_length=150, unique=True, db_column="login")
    password = models.CharField("пароль", max_length=128, db_column="password_hash")
    middle_name = models.CharField("по батькові", max_length=150, blank=True)
    tax_number = models.CharField("РНОКПП", max_length=10, blank=True)
    birth_date = models.DateField("дата народження", null=True, blank=True)
    phone = models.CharField("телефон", max_length=32, blank=True)
    registration_address = models.CharField("адреса реєстрації", max_length=500, blank=True)
    fop_registered_on = models.DateField("дата реєстрації ФОП", null=True, blank=True)
    primary_kved = models.CharField("основний КВЕД", max_length=200, blank=True)
    tax_office_code = models.CharField("код контролюючого органу", max_length=20, blank=True)
    tax_office_name = models.CharField("назва контролюючого органу", max_length=300, blank=True)
    tax_region = models.CharField("область обліку", max_length=20, blank=True, choices=list(REGIONS.items()))
    community = models.CharField(
        "територіальна громада",
        max_length=200,
        blank=True,
        help_text="Як у таблиці податкової, наприклад «Львівська міська ТГ».",
    )
    skip_esv = models.BooleanField("не розраховувати ЄСВ", default=False)

    class Meta:
        db_table = "users"

    @property
    def display_name(self):
        name = " ".join(part for part in (self.last_name, self.first_name) if part)
        return name or self.username


class IncomeEntry(models.Model):
    class Currency(models.TextChoices):
        UAH = "uah", "грн"
        EUR = "eur", "євро"
        USD = "usd", "долар"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="income_entries")
    received_on = models.DateField()
    currency = models.CharField(max_length=3, choices=Currency.choices)
    amount_minor = models.BigIntegerField(null=True, blank=True)
    rate = models.DecimalField(max_digits=16, decimal_places=6, null=True, blank=True)
    amount_uah_kopiykas = models.BigIntegerField()

    class Meta:
        db_table = "income_entries"
        ordering = ["-received_on", "-id"]
        indexes = [models.Index(fields=["user", "received_on"])]


class MonthRecord(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="month_records")
    year = models.PositiveSmallIntegerField()
    month = models.PositiveSmallIntegerField()
    income_uah_kopiykas = models.BigIntegerField(null=True, blank=True)
    single_tax_kopiykas = models.BigIntegerField(null=True, blank=True)
    military_levy_kopiykas = models.BigIntegerField(null=True, blank=True)
    esv_kopiykas = models.BigIntegerField(null=True, blank=True)
    single_tax_paid = models.BooleanField(default=False)
    military_levy_paid = models.BooleanField(default=False)
    esv_paid = models.BooleanField(default=False)

    class Meta:
        db_table = "month_records"
        constraints = [
            models.UniqueConstraint(fields=["user", "year", "month"], name="month_record_per_user_month"),
        ]

    def has_values(self):
        return any(
            value is not None
            for value in (
                self.income_uah_kopiykas,
                self.single_tax_kopiykas,
                self.military_levy_kopiykas,
                self.esv_kopiykas,
            )
        )


class TaxSettlementAccount(models.Model):
    """Зведення за одним бюджетним рахунком за рік — з API /ta/splatp."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="settlement_accounts")
    year = models.PositiveSmallIntegerField()
    account_id = models.CharField(max_length=64)
    tax_office_code = models.IntegerField()
    tax_office_name = models.CharField(max_length=300)
    payment_code = models.BigIntegerField()
    payment_name = models.CharField(max_length=500)
    charged_kopiykas = models.BigIntegerField(null=True, blank=True)
    paid_kopiykas = models.BigIntegerField(null=True, blank=True)
    returned_kopiykas = models.BigIntegerField(null=True, blank=True)
    penalty_kopiykas = models.BigIntegerField(null=True, blank=True)
    arrears_kopiykas = models.BigIntegerField(null=True, blank=True)
    overpaid_kopiykas = models.BigIntegerField(null=True, blank=True)
    penalty_balance_kopiykas = models.BigIntegerField(null=True, blank=True)
    total_balance_kopiykas = models.BigIntegerField(null=True, blank=True)
    budget_iban = models.CharField(max_length=34, blank=True)
    synced_at = models.DateTimeField()

    class Meta:
        db_table = "tax_settlement_accounts"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "year", "account_id"],
                name="settlement_account_per_user_year_id",
            )
        ]


class TaxSettlementOperation(models.Model):
    """Одна операція з особового рахунку — з API /ta/splatp/{year}/{cSti}/{id}/pa."""

    account = models.ForeignKey(TaxSettlementAccount, on_delete=models.CASCADE, related_name="operations")
    operation_date = models.DateField()
    operation_code = models.CharField(max_length=20, blank=True)
    operation_name = models.CharField(max_length=500)
    amount_kopiykas = models.BigIntegerField(null=True, blank=True)
    charged_kopiykas = models.BigIntegerField(null=True, blank=True)
    paid_returned_kopiykas = models.BigIntegerField(null=True, blank=True)
    balance_kopiykas = models.BigIntegerField(null=True, blank=True)
    penalty_kopiykas = models.BigIntegerField(null=True, blank=True)
    penalty_balance_kopiykas = models.BigIntegerField(null=True, blank=True)

    class Meta:
        db_table = "tax_settlement_operations"
        ordering = ["operation_date", "id"]


class PayerCard(models.Model):
    """Знімок «Даних платника» з кабінету ДПС (/ws/api/payer_card)."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="payer_card")
    groups = models.JSONField(default=list)
    filled_fields = models.JSONField(default=list)
    synced_at = models.DateTimeField()

    class Meta:
        db_table = "payer_cards"


class PaymentRequisite(models.Model):
    class Kind(models.TextChoices):
        SINGLE_TAX = "single_tax", "ЄП"
        ESV = "esv", "ЄСВ"
        MILITARY_LEVY = "military_levy", "ВВ"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="payment_requisites")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    recipient = models.CharField(max_length=300)
    recipient_code = models.CharField(max_length=20)
    bank = models.CharField(max_length=300)
    iban = models.CharField(max_length=34)
    code = models.CharField(max_length=20)
    source_url = models.URLField(max_length=300)
    checked_at = models.DateTimeField()
    changed_at = models.DateTimeField()

    class Meta:
        db_table = "payment_requisites"
        constraints = [
            models.UniqueConstraint(fields=["user", "kind"], name="payment_requisite_per_user_kind"),
        ]
