from django.db import migrations


def set_bond_location(apps, schema_editor):
    User = apps.get_model("ledger", "User")
    User.objects.filter(username="bond", tax_region="", community="").update(
        tax_region="lv",
        community="Львівська міська ТГ",
    )


class Migration(migrations.Migration):
    dependencies = [
        ("ledger", "0003_payment_requisites"),
    ]

    operations = [
        migrations.RunPython(set_bond_location, migrations.RunPython.noop),
    ]
