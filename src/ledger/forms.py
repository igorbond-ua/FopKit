import datetime
import re

from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm

from . import services
from .models import IncomeEntry, User
from .money import AmountError, parse_amount_minor

DATE_INPUT = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")

LOGIN_RE = re.compile(r"^[a-z0-9_.-]+$")
LOGIN_MIN, LOGIN_MAX = 3, 32
PASSWORD_MAX = 128


class LoginForm(AuthenticationForm):
    """Logins are stored in lower case, so "Bond" and "bond" are the same account."""

    def clean_username(self):
        return self.cleaned_data["username"].strip().lower()


class RegisterForm(forms.Form):
    username = forms.CharField(
        label="Логін",
        max_length=LOGIN_MAX,
        help_text="Від 3 до 32 символів: латинські літери, цифри, крапка, дефіс і підкреслення. Регістр не важливий.",
        widget=forms.TextInput(attrs={"autocomplete": "username", "autocapitalize": "none", "spellcheck": "false"}),
    )
    password = forms.CharField(
        label="Пароль",
        max_length=PASSWORD_MAX,
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "box"

    def clean_username(self):
        value = self.cleaned_data["username"].strip().lower()
        if not LOGIN_MIN <= len(value) <= LOGIN_MAX:
            raise forms.ValidationError(f"Логін — від {LOGIN_MIN} до {LOGIN_MAX} символів.")
        if not LOGIN_RE.fullmatch(value):
            raise forms.ValidationError(
                "Дозволені лише латинські літери, цифри, крапка, дефіс і підкреслення."
            )
        if User.objects.filter(username__iexact=value).exists():
            raise forms.ValidationError("Цей логін уже зайнятий.")
        return value

    def save(self):
        return User.objects.create_user(
            username=self.cleaned_data["username"], password=self.cleaned_data["password"]
        )


class IncomeForm(forms.Form):
    received_on = forms.DateField(label="Дата", widget=DATE_INPUT)
    amount = forms.CharField(
        label="Сума",
        max_length=32,
        widget=forms.TextInput(attrs={"inputmode": "decimal", "placeholder": "0,00", "autocomplete": "off"}),
    )
    currency = forms.ChoiceField(
        label="Валюта",
        choices=IncomeEntry.Currency.choices,
        initial=IncomeEntry.Currency.UAH,
        widget=forms.RadioSelect,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("received_on", "amount"):
            self.fields[name].widget.attrs["class"] = "box"

    def clean_received_on(self):
        value = self.cleaned_data["received_on"]
        if value > services.today():
            raise forms.ValidationError("Дата не може бути в майбутньому.")
        if value < datetime.date(services.FIRST_YEAR, 1, 1):
            raise forms.ValidationError(f"Облік ведеться з {services.FIRST_YEAR} року.")
        return value

    def clean_amount(self):
        try:
            return parse_amount_minor(self.cleaned_data["amount"])
        except AmountError as exc:
            raise forms.ValidationError(str(exc))


class ProfileForm(forms.ModelForm):
    new_password = forms.CharField(
        label="Новий пароль",
        required=False,
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text="Якщо поле порожнє, пароль лишається попередній.",
    )

    class Meta:
        model = User
        fields = [
            "last_name",
            "first_name",
            "middle_name",
            "tax_number",
            "birth_date",
            "phone",
            "email",
            "registration_address",
            "fop_registered_on",
            "primary_kved",
            "tax_office_code",
            "tax_office_name",
            "tax_region",
            "community",
        ]
        labels = {
            "last_name": "Прізвище",
            "first_name": "Ім'я",
            "email": "Електронна пошта",
        }
        widgets = {
            "birth_date": DATE_INPUT,
            "fop_registered_on": DATE_INPUT,
            "tax_number": forms.TextInput(attrs={"inputmode": "numeric", "maxlength": "10"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "box"
        # Values from the tax service win over manual input; disabled fields keep the stored value.
        self.dps_fields = services.dps_fields(self.instance) if self.instance.pk else set()
        for name in self.dps_fields & set(self.fields):
            self.fields[name].disabled = True
            self.fields[name].widget.attrs["class"] = "box from-dps"

    def clean_tax_number(self):
        value = self.cleaned_data["tax_number"].strip()
        if value and (len(value) != 10 or not value.isdigit()):
            raise forms.ValidationError("РНОКПП — це 10 цифр.")
        return value

    def clean_new_password(self):
        value = self.cleaned_data["new_password"]
        if value:
            password_validation.validate_password(value, self.instance)
        return value

    def save(self, commit=True):
        user = super().save(commit=False)
        if self.cleaned_data["new_password"]:
            user.set_password(self.cleaned_data["new_password"])
        if commit:
            user.save()
        return user
