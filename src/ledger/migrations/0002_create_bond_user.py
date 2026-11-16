from django.contrib.auth.hashers import make_password
from django.db import migrations


def create_bond_user(apps, schema_editor):
    User = apps.get_model("ledger", "User")
    if User.objects.filter(username="bond").exists():
        return
    User.objects.create(
        username="bond",
        password=make_password("123"),
        last_name="Бондаренко",
        first_name="Ігор",
        is_active=True,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("ledger", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_bond_user, migrations.RunPython.noop),
    ]
