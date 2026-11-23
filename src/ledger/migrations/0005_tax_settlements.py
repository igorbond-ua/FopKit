from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("ledger", "0004_bond_tax_location"),
    ]

    operations = [
        migrations.CreateModel(
            name="TaxSettlementAccount",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("user", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="settlement_accounts",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("year", models.PositiveSmallIntegerField()),
                ("account_id", models.CharField(max_length=64)),
                ("tax_office_code", models.IntegerField()),
                ("tax_office_name", models.CharField(max_length=300)),
                ("payment_code", models.BigIntegerField()),
                ("payment_name", models.CharField(max_length=500)),
                ("charged_kopiykas", models.BigIntegerField(null=True, blank=True)),
                ("paid_kopiykas", models.BigIntegerField(null=True, blank=True)),
                ("returned_kopiykas", models.BigIntegerField(null=True, blank=True)),
                ("penalty_kopiykas", models.BigIntegerField(null=True, blank=True)),
                ("arrears_kopiykas", models.BigIntegerField(null=True, blank=True)),
                ("overpaid_kopiykas", models.BigIntegerField(null=True, blank=True)),
                ("penalty_balance_kopiykas", models.BigIntegerField(null=True, blank=True)),
                ("total_balance_kopiykas", models.BigIntegerField(null=True, blank=True)),
                ("budget_iban", models.CharField(max_length=34, blank=True)),
                ("synced_at", models.DateTimeField()),
            ],
            options={"db_table": "tax_settlement_accounts"},
        ),
        migrations.AddConstraint(
            model_name="taxsettlementaccount",
            constraint=models.UniqueConstraint(
                fields=["user", "year", "account_id"],
                name="settlement_account_per_user_year_id",
            ),
        ),
        migrations.CreateModel(
            name="TaxSettlementOperation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("account", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="operations",
                    to="ledger.taxsettlementaccount",
                )),
                ("operation_date", models.DateField()),
                ("operation_code", models.CharField(max_length=20, blank=True)),
                ("operation_name", models.CharField(max_length=500)),
                ("amount_kopiykas", models.BigIntegerField(null=True, blank=True)),
                ("charged_kopiykas", models.BigIntegerField(null=True, blank=True)),
                ("paid_returned_kopiykas", models.BigIntegerField(null=True, blank=True)),
                ("balance_kopiykas", models.BigIntegerField(null=True, blank=True)),
                ("penalty_kopiykas", models.BigIntegerField(null=True, blank=True)),
                ("penalty_balance_kopiykas", models.BigIntegerField(null=True, blank=True)),
            ],
            options={"db_table": "tax_settlement_operations", "ordering": ["operation_date", "id"]},
        ),
    ]
