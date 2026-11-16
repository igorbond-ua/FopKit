import datetime
import io
import zipfile
from decimal import Decimal
from unittest import mock
from xml.sax.saxutils import escape

from django.test import TestCase
from django.urls import reverse

from . import nbu, requisites, services
from .models import IncomeEntry, MonthRecord, PaymentRequisite, User
from .money import AmountError, convert_to_kopiykas, format_kopiykas, parse_amount_minor, percent_ceil

TODAY = datetime.date(2026, 11, 13)


def fixed_today():
    return TODAY


class MoneyTests(TestCase):
    def test_amount_rounds_up_to_kopiyka(self):
        self.assertEqual(parse_amount_minor("10,001"), 1001)
        self.assertEqual(parse_amount_minor("10.00"), 1000)
        self.assertEqual(parse_amount_minor("1 250,5"), 125050)

    def test_invalid_amounts(self):
        for value in ("", "abc", "0", "-5", "nan"):
            with self.assertRaises(AmountError):
                parse_amount_minor(value)

    def test_spec_rounding_examples(self):
        self.assertEqual(convert_to_kopiykas(1000, Decimal("41.2543")), 41255)
        self.assertEqual(percent_ceil(1001, 5), 51)

    def test_format(self):
        self.assertEqual(format_kopiykas(5588237), "55\u00a0882,37")
        self.assertEqual(format_kopiykas(None), "—")

    def test_minimum_esv_2026(self):
        self.assertEqual(services.minimum_esv(2026), 190234)


class NbuTests(TestCase):
    def test_weekend_uses_friday(self):
        self.assertEqual(nbu.rate_date_for(datetime.date(2026, 11, 14)), datetime.date(2026, 11, 13))
        self.assertEqual(nbu.rate_date_for(datetime.date(2026, 11, 15)), datetime.date(2026, 11, 13))
        self.assertEqual(nbu.rate_date_for(datetime.date(2026, 11, 16)), datetime.date(2026, 11, 16))

    def test_steps_back_when_no_rate_published(self):
        responses = {datetime.date(2026, 11, 16): None, datetime.date(2026, 11, 15): Decimal("41.5")}
        with mock.patch.object(nbu, "fetch_rate", side_effect=lambda code, day: responses.get(day)):
            self.assertEqual(nbu.official_rate("usd", datetime.date(2026, 11, 16)), Decimal("41.5"))


@mock.patch.object(services, "today", fixed_today)
class LedgerTests(TestCase):
    def setUp(self):
        self.user = User.objects.get(username="bond")
        self.client.force_login(self.user)

    def add(self, day, currency, amount, rate=Decimal("41.2543")):
        with mock.patch.object(nbu, "official_rate", return_value=rate):
            return self.client.post(
                reverse("income_add"),
                {"received_on": day, "currency": currency, "amount": amount, "year": 2026},
            )

    def test_bond_user_created_by_migration(self):
        self.assertEqual(self.user.display_name, "Бондаренко Ігор")
        self.assertTrue(self.user.check_password("123"))

    def test_login_required(self):
        self.client.logout()
        response = self.client.get(reverse("dashboard"))
        self.assertRedirects(response, f"{reverse('login')}?next=/", fetch_redirect_response=False)

    def test_add_uah_income_calculates_month(self):
        self.add("2026-11-03", "uah", "25000")
        record = MonthRecord.objects.get(user=self.user, year=2026, month=11)
        self.assertEqual(record.income_uah_kopiykas, 2500000)
        self.assertEqual(record.single_tax_kopiykas, 125000)
        self.assertEqual(record.military_levy_kopiykas, 25000)
        self.assertEqual(record.esv_kopiykas, 190234)

    def test_add_foreign_income_stores_rate(self):
        self.add("2026-11-12", "usd", "10")
        entry = IncomeEntry.objects.get(user=self.user)
        self.assertEqual(entry.amount_minor, 1000)
        self.assertEqual(entry.rate, Decimal("41.2543"))
        self.assertEqual(entry.amount_uah_kopiykas, 41255)

    def test_future_date_rejected(self):
        response = self.add("2026-11-20", "uah", "100")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(IncomeEntry.objects.exists())

    def test_dashboard_fills_started_months_esv(self):
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "Бондаренко Ігор · 3 група, без ПДВ · 2026")
        months = set(MonthRecord.objects.filter(user=self.user, year=2026).values_list("month", flat=True))
        self.assertEqual(months, set(range(1, 12)))

    def test_edit_moves_month_and_clears_paid(self):
        self.add("2026-10-15", "uah", "1000")
        record = MonthRecord.objects.get(user=self.user, year=2026, month=10)
        record.single_tax_paid = record.esv_paid = True
        record.save()
        entry = IncomeEntry.objects.get(user=self.user)
        self.client.post(
            reverse("income_edit", args=[entry.id]),
            {"received_on": "2026-11-02", "currency": "uah", "amount": "2000", "return_year": 2026},
        )
        october = MonthRecord.objects.get(user=self.user, year=2026, month=10)
        november = MonthRecord.objects.get(user=self.user, year=2026, month=11)
        self.assertIsNone(october.income_uah_kopiykas)
        self.assertFalse(october.single_tax_paid or october.esv_paid)
        self.assertEqual(november.income_uah_kopiykas, 200000)

    def test_delete_income_recalculates_month(self):
        self.add("2026-11-03", "uah", "1000")
        self.add("2026-11-05", "uah", "500")
        MonthRecord.objects.filter(user=self.user, year=2026, month=11).update(single_tax_paid=True)
        entry = IncomeEntry.objects.get(user=self.user, amount_uah_kopiykas=50000)
        response = self.client.post(
            reverse("income_delete", args=[entry.id]), {"return_year": 2026, "return_month": 11}
        )
        self.assertRedirects(response, "/?year=2026&month=11", fetch_redirect_response=False)
        record = MonthRecord.objects.get(user=self.user, year=2026, month=11)
        self.assertEqual(record.income_uah_kopiykas, 100000)
        self.assertEqual(record.single_tax_kopiykas, 5000)
        self.assertFalse(record.single_tax_paid)

    def test_delete_last_income_leaves_dashes(self):
        self.add("2026-11-03", "uah", "1000")
        entry = IncomeEntry.objects.get(user=self.user)
        self.client.post(reverse("income_delete", args=[entry.id]), {"return_year": 2026})
        record = MonthRecord.objects.get(user=self.user, year=2026, month=11)
        self.assertIsNone(record.income_uah_kopiykas)
        self.assertIsNone(record.single_tax_kopiykas)
        self.assertEqual(record.esv_kopiykas, 190234)

    def test_month_dialog_entry_taxes(self):
        self.add("2026-11-03", "uah", "10,01")
        payload = services.entry_payload(IncomeEntry.objects.get(user=self.user))
        self.assertEqual((payload["singleTax"], payload["militaryLevy"]), ("0,51", "0,11"))

    def test_new_income_clears_paid(self):
        self.add("2026-11-03", "uah", "1000")
        MonthRecord.objects.filter(user=self.user, year=2026, month=11).update(
            single_tax_paid=True, military_levy_paid=True, esv_paid=True
        )
        self.add("2026-11-05", "uah", "500")
        record = MonthRecord.objects.get(user=self.user, year=2026, month=11)
        self.assertFalse(record.single_tax_paid or record.military_levy_paid or record.esv_paid)
        self.assertEqual(record.income_uah_kopiykas, 150000)

    def test_edit_keeps_rate_when_only_amount_changes(self):
        self.add("2026-11-12", "eur", "100", rate=Decimal("46.0804"))
        entry = IncomeEntry.objects.get(user=self.user)
        with mock.patch.object(nbu, "official_rate", side_effect=AssertionError("must not refetch")):
            self.client.post(
                reverse("income_edit", args=[entry.id]),
                {"received_on": "2026-11-12", "currency": "eur", "amount": "200", "return_year": 2026},
            )
        entry.refresh_from_db()
        self.assertEqual(entry.amount_uah_kopiykas, 921608)

    def test_toggle_paid(self):
        self.add("2026-11-03", "uah", "100")
        url = reverse("toggle_paid", args=[2026, 11, "single_tax"])
        self.client.post(url)
        self.assertTrue(MonthRecord.objects.get(user=self.user, year=2026, month=11).single_tax_paid)
        self.client.post(url)
        self.assertFalse(MonthRecord.objects.get(user=self.user, year=2026, month=11).single_tax_paid)

    def test_quarter_paid_only_when_all_taxes_paid(self):
        self.add("2026-07-10", "uah", "100")
        services.fill_started_months_esv(self.user)
        MonthRecord.objects.filter(user=self.user, year=2026, month__in=[7, 8, 9]).update(
            single_tax_paid=True, military_levy_paid=True, esv_paid=True
        )
        rows, _ = services.build_year_table(self.user, 2026)
        third_quarter = next(row for row in rows if row["label"] == "3-квартал")
        self.assertIn("paid-row", third_quarter["css"])
        MonthRecord.objects.filter(user=self.user, year=2026, month=8).update(esv_paid=False)
        rows, _ = services.build_year_table(self.user, 2026)
        third_quarter = next(row for row in rows if row["label"] == "3-квартал")
        self.assertNotIn("paid-row", third_quarter["css"])

    def test_year_total_sums_months(self):
        self.add("2026-07-10", "uah", "100")
        self.add("2026-11-10", "uah", "200")
        rows, _ = services.build_year_table(self.user, 2026)
        total = rows[-1]
        self.assertEqual(total["label"], "Разом за рік")
        self.assertEqual(total["cells"][0]["value"], 30000)

    def test_skip_esv_hides_column(self):
        self.client.post(reverse("skip_esv"), {"skip_esv": "1", "year": 2026})
        self.user.refresh_from_db()
        rows, _ = services.build_year_table(self.user, 2026)
        self.assertTrue(all(row["cells"][3]["value"] is None for row in rows))

    def test_profile_update_and_password(self):
        response = self.client.post(
            reverse("profile"),
            {"last_name": "Бондаренко", "first_name": "Ігор", "tax_number": "1234567890",
             "new_password": "Kx9-long-pass", "year": 2026},
        )
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.tax_number, "1234567890")
        self.assertTrue(self.user.check_password("Kx9-long-pass"))

    def test_profile_rejects_bad_tax_number(self):
        response = self.client.post(
            reverse("profile"),
            {"last_name": "Бондаренко", "first_name": "Ігор", "tax_number": "12ab", "year": 2026},
        )
        self.assertEqual(response.status_code, 400)


@mock.patch.object(services, "today", fixed_today)
class IsolationTests(TestCase):
    def setUp(self):
        self.owner = User.objects.get(username="bond")
        self.other = User.objects.create_user(username="other", password="Other-pass-123")
        with mock.patch.object(nbu, "official_rate", return_value=Decimal("41")):
            self.entry = services.add_income(self.owner, datetime.date(2026, 11, 3), "uah", 10000)
        self.client.force_login(self.other)

    def test_other_user_cannot_edit_entry(self):
        response = self.client.post(
            reverse("income_edit", args=[self.entry.id]),
            {"received_on": "2026-11-03", "currency": "uah", "amount": "1", "return_year": 2026},
        )
        self.assertEqual(response.status_code, 404)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.amount_uah_kopiykas, 10000)

    def test_other_user_cannot_delete_entry(self):
        response = self.client.post(reverse("income_delete", args=[self.entry.id]), {"return_year": 2026})
        self.assertEqual(response.status_code, 404)
        self.assertTrue(IncomeEntry.objects.filter(pk=self.entry.id).exists())

    def test_other_user_cannot_toggle(self):
        response = self.client.post(reverse("toggle_paid", args=[2026, 11, "single_tax"]))
        self.assertEqual(response.status_code, 404)

    def test_other_user_does_not_see_entries(self):
        response = self.client.get(reverse("dashboard"))
        self.assertNotContains(response, "100,00")

    def test_other_user_does_not_see_requisites(self):
        with mock.patch.object(requisites, "fetch", return_value=FETCHED):
            services.refresh_requisites(self.owner)
        response = self.client.get(reverse("dashboard"))
        self.assertNotContains(response, "UA678999980314010699000013933")


def xlsx(rows):
    def cell(column, value):
        ref = f"{chr(ord('A') + column)}1"
        return f'<c r="{ref}" t="inlineStr"><is><t>{escape(value)}</t></is></c>'

    body = "".join(
        "<row>" + "".join(cell(i, value) for i, value in enumerate(row) if value) + "</row>" for row in rows
    )
    sheet = (
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{body}</sheetData></worksheet>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as book:
        book.writestr("xl/worksheets/sheet1.xml", sheet)
    return buffer.getvalue()


TAX_HEADER = [
    "Код обл.", "Населений пункт", "Отримувач", "Код отримувача (ЄДРПОУ)", "Банк отримувача",
    "Номер рахунку (IBAN)", "Код класифікації доходів бюджету", "Найменування",
]
TAX_ROWS = [
    ["Реквізити"],
    TAX_HEADER,
    ["13", "Белзька міська ТГ", "ГУК Львiв/Белзька тг/18050400", "38008294", "Казначейство", "UA001", "18050400", ""],
    ["13", "Львiвська мiська ТГ", "ГУК Львiв/Львівська тг/18050400", "38008294", "Казначейство",
     "UA678999980314010699000013933", "18050400", ""],
    ["13", "ЛЬВIВСЬКА ОБЛАСТЬ/М.ЛЬВIВ", "ГУК Львiв/Львів. обл/11011700", "38008294", "Казначейство",
     "UA438999980313131029000013001", "11011700", ""],
]
ESV_ROWS = [
    ["Реквізити рахунків для сплати єдиного внеску"],
    ["Банк отримувача", "Назва органу ДПС (отримувач)", "Код за ЄДРПОУ органу ДПС", "Номер рахунку (IBAN)",
     "Символ звітності", "Категорії"],
    ["Казначейство України (ЕАП)", "ГУДПС у Львівській області", "43968090", "UA728999980000355699201021301", "201", ""],
    ["Казначейство України (ЕАП)", "ГУДПС у Львівській області", "43968090", "UA928999980000355609204021301", "204", ""],
]
PAGE = """
<p><a href="https://tax.gov.ua/data/files/1.xlsx" target="_blank"><strong>1. Реквізити рахунків для сплати
податків, зборів та платежів</strong></a></p>
<p><a href="https://evil.example/2.xlsx">2. Реквізити рахунків для сплати єдиного внеску</a></p>
<p><a href="https://tax.gov.ua/data/files/2.xlsx">2. Реквізити рахунків для сплати єдиного внеску</a></p>
"""
FETCHED = {
    "single_tax": requisites.Requisite("ГУК Львiв/Львівська тг/18050400", "38008294", "Казначейство",
                                       "UA678999980314010699000013933", "18050400"),
    "military_levy": requisites.Requisite("ГУК Львiв/Львів. обл/11011700", "38008294", "Казначейство",
                                          "UA438999980313131029000013001", "11011700"),
    "esv": requisites.Requisite("ГУДПС у Львівській області", "43968090", "Казначейство України (ЕАП)",
                                "UA928999980000355609204021301", "204"),
}


class RequisitesParsingTests(TestCase):
    def test_find_tables_ignores_foreign_hosts(self):
        taxes, esv = requisites.find_tables(PAGE)
        self.assertEqual(taxes, "https://tax.gov.ua/data/files/1.xlsx")
        self.assertEqual(esv, "https://tax.gov.ua/data/files/2.xlsx")

    def test_parse_taxes_matches_community_with_latin_letters(self):
        result = requisites.parse_taxes(requisites.read_rows(xlsx(TAX_ROWS)), "Львівська міська ТГ")
        self.assertEqual(result["single_tax"].iban, "UA678999980314010699000013933")
        self.assertEqual(result["military_levy"].iban, "UA438999980313131029000013001")

    def test_parse_taxes_unknown_community(self):
        with self.assertRaises(requisites.RequisitesUnavailable):
            requisites.parse_taxes(requisites.read_rows(xlsx(TAX_ROWS)), "Неіснуюча ТГ")

    def test_parse_esv_picks_self_employed_symbol(self):
        result = requisites.parse_esv(requisites.read_rows(xlsx(ESV_ROWS)))
        self.assertEqual(result.iban, "UA928999980000355609204021301")
        self.assertEqual(result.recipient_code, "43968090")

    def test_fetch_downloads_page_and_tables(self):
        files = {
            requisites.page_url("lv"): PAGE.encode(),
            "https://tax.gov.ua/data/files/1.xlsx": xlsx(TAX_ROWS),
            "https://tax.gov.ua/data/files/2.xlsx": xlsx(ESV_ROWS),
        }
        with mock.patch.object(requisites, "download", side_effect=files.__getitem__):
            result = requisites.fetch("lv", "Львівська міська ТГ")
        self.assertEqual(result["esv"].code, "204")


class RequisitesViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.get(username="bond")
        self.client.force_login(self.user)

    def test_bond_has_lviv_location(self):
        self.assertEqual((self.user.tax_region, self.user.community), ("lv", "Львівська міська ТГ"))

    def test_refresh_saves_and_reports_changes(self):
        with mock.patch.object(requisites, "fetch", return_value=FETCHED):
            response = self.client.post(reverse("refresh_requisites"), {"year": 2026}, follow=True)
        self.assertContains(response, "Змінились: ЄП, ЄСВ, ВВ.")
        self.assertContains(response, "UA928999980000355609204021301")
        self.assertContains(response, "*;101;РНОКПП;Єдиний податок;;;")
        self.assertEqual(PaymentRequisite.objects.filter(user=self.user).count(), 3)
        with mock.patch.object(requisites, "fetch", return_value=FETCHED):
            response = self.client.post(reverse("refresh_requisites"), {"year": 2026}, follow=True)
        self.assertContains(response, "Змін немає.")

    def test_refresh_keeps_old_values_when_site_fails(self):
        with mock.patch.object(requisites, "fetch", return_value=FETCHED):
            services.refresh_requisites(self.user)
        error = requisites.RequisitesUnavailable("Сайт податкової не відповідає.")
        with mock.patch.object(requisites, "fetch", side_effect=error):
            response = self.client.post(reverse("refresh_requisites"), {"year": 2026}, follow=True)
        self.assertContains(response, "Реквізити не оновлено. Сайт податкової не відповідає.")
        self.assertContains(response, "UA678999980314010699000013933")

    def test_refresh_requires_location(self):
        User.objects.filter(pk=self.user.pk).update(community="")
        with mock.patch.object(requisites, "fetch", side_effect=AssertionError("must not fetch")):
            response = self.client.post(reverse("refresh_requisites"), {"year": 2026}, follow=True)
        self.assertContains(response, "вкажіть у кабінеті область обліку і територіальну громаду")
