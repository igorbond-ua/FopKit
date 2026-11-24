import base64
import json
import logging
from urllib.parse import urlparse

import requests

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import urlencode
from django.views.decorators.http import require_POST

from . import cabinet, nbu, requisites, services
from .forms import IncomeForm, ProfileForm
from .models import IncomeEntry, MonthRecord, PayerCard

logger = logging.getLogger(__name__)

RECENT_LIMIT = 40
RATE_ERROR = "Не вдалося отримати курс НБУ. Спробуйте ще раз трохи пізніше."


def _base_context(request):
    """Context shared by all pages that extend page_base.html."""
    return {
        "profile_form": ProfileForm(instance=request.user),
        "payer_card": PayerCard.objects.filter(user=request.user).first(),
        "tax_group": services.TAX_GROUP,
    }


def _int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _valid_year(value):
    year = _int_or_none(value)
    return year if year in services.available_years() else services.today().year


def _valid_month(value):
    month = _int_or_none(value)
    return month if month is not None and 1 <= month <= 12 else None


def dashboard_url(year, month=None):
    params = {"year": year}
    if month:
        params["month"] = month
    return f"{reverse('dashboard')}?{urlencode(params)}"


def render_dashboard(request, year, *, income_form=None, profile_form=None, open_dialog="", open_month=None, status=200):
    user = request.user
    services.fill_started_months_esv(user)
    rows, has_data = services.build_year_table(user, year)
    year_entries = list(IncomeEntry.objects.filter(user=user, received_on__year=year))
    recent_entries = list(IncomeEntry.objects.filter(user=user)[:RECENT_LIMIT])
    context = {
        **_base_context(request),
        "active_tab": "dashboard",
        "year": year,
        "years": services.available_years(),
        "rows": rows,
        "has_data": has_data,
        "recent_entries": recent_entries,
        "income_form": income_form or IncomeForm(initial={"received_on": services.today()}),
        "profile_form": profile_form or ProfileForm(instance=user),
        "dialog_data": services.dialog_data(year_entries, recent_entries),
        "currencies": IncomeEntry.Currency.choices,
        "open_dialog": open_dialog,
        "open_month": open_month or "",
    }
    return render(request, "ledger/dashboard.html", context, status=status)


@login_required
def dashboard(request):
    year = _valid_year(request.GET.get("year"))
    return render_dashboard(request, year, open_month=_valid_month(request.GET.get("month")))


@login_required
@require_POST
def income_add(request):
    year = _valid_year(request.POST.get("year"))
    form = IncomeForm(request.POST)
    if form.is_valid():
        data = form.cleaned_data
        try:
            entry = services.add_income(request.user, data["received_on"], data["currency"], data["amount"])
        except nbu.RateUnavailable:
            form.add_error(None, RATE_ERROR)
        else:
            messages.success(request, "Прибуток додано.")
            return redirect(dashboard_url(entry.received_on.year))
    return render_dashboard(request, year, income_form=form, status=400)


@login_required
@require_POST
def income_edit(request, entry_id):
    entry = get_object_or_404(IncomeEntry, pk=entry_id, user=request.user)
    year = _valid_year(request.POST.get("return_year"))
    month = _valid_month(request.POST.get("return_month"))
    form = IncomeForm(request.POST)
    if not form.is_valid():
        errors = "; ".join(str(error) for field_errors in form.errors.values() for error in field_errors)
        messages.error(request, f"Зміни не збережено. {errors}")
        return redirect(dashboard_url(year, month))
    data = form.cleaned_data
    try:
        services.edit_income(entry, data["received_on"], data["currency"], data["amount"])
    except nbu.RateUnavailable:
        messages.error(request, f"Зміни не збережено. {RATE_ERROR}")
        return redirect(dashboard_url(year, month))
    messages.success(request, "Зміни збережено.")
    return redirect(dashboard_url(year, month))


@login_required
@require_POST
def income_delete(request, entry_id):
    entry = get_object_or_404(IncomeEntry, pk=entry_id, user=request.user)
    services.delete_income(entry)
    messages.success(request, "Прибуток видалено.")
    year = _valid_year(request.POST.get("return_year"))
    return redirect(dashboard_url(year, _valid_month(request.POST.get("return_month"))))


@login_required
@require_POST
def toggle_paid(request, year, month, kind):
    if kind not in services.PAID_FIELDS:
        raise Http404
    value_field, paid_field = services.PAID_FIELDS[kind]
    record = get_object_or_404(MonthRecord, user=request.user, year=year, month=month)
    if getattr(record, value_field) is None or (kind == "esv" and request.user.skip_esv):
        raise Http404
    setattr(record, paid_field, not getattr(record, paid_field))
    record.save(update_fields=[paid_field])
    return redirect(dashboard_url(_valid_year(year)))


@login_required
@require_POST
def skip_esv(request):
    request.user.skip_esv = request.POST.get("skip_esv") == "1"
    request.user.save(update_fields=["skip_esv"])
    return redirect(dashboard_url(_valid_year(request.POST.get("year"))))


@login_required
@require_POST
def profile(request):
    # After saving profile, always go to dashboard (cabinet can be opened from any page)
    form = ProfileForm(request.POST, instance=request.user)
    if form.is_valid():
        user = form.save()
        if form.cleaned_data["new_password"]:
            update_session_auth_hash(request, user)
        messages.success(request, "Дані кабінету збережено.")
        return redirect(dashboard_url(services.today().year))
    request.user.refresh_from_db()
    year = _valid_year(request.POST.get("year"))
    return render_dashboard(request, year, profile_form=form, open_dialog="cabinet", status=400)


def _signed_login(request):
    """(username, password) of the signed cabinet login sent by the browser, or None."""
    try:
        body = json.loads(request.body)
        username = body.get("username", "").strip()
        password = body.get("password", "").strip()
    except (ValueError, AttributeError):
        return None
    return (username, password) if username and password else None


@login_required
@require_POST
def profile_sync(request):
    """Refresh profile fields from "Дані платника" in the tax cabinet."""
    login = _signed_login(request)
    if login is None:
        return JsonResponse({"error": "Підпис відсутній."}, status=400)
    try:
        changed = services.sync_payer_card(request.user, *login)
    except cabinet.SignatureExpiredError as exc:
        return JsonResponse({"error": str(exc)}, status=401)
    except cabinet.CabinetError as exc:
        logger.warning("Payer card sync failed for user %s: %s", request.user.pk, exc)
        return JsonResponse({"error": str(exc)}, status=502)
    except Exception as exc:
        logger.exception("Payer card sync crashed for user %s", request.user.pk)
        return JsonResponse(
            {"error": f"Не вдалося обробити дані платника: {type(exc).__name__}: {exc}"},
            status=500,
        )
    if changed:
        labels = ", ".join(str(ProfileForm.base_fields[name].label) for name in changed)
        messages.success(request, f"Дані з податкової оновлено. Змінились: {labels}.")
    else:
        messages.success(request, "Дані з податкової перевірено. Змін немає.")
    return JsonResponse({"ok": True})


@login_required
@require_POST
def refresh_requisites(request):
    url = reverse("requisites")
    user = request.user
    if not user.tax_region or not user.community.strip():
        messages.error(request, "Щоб оновити реквізити, вкажіть у кабінеті область обліку і територіальну громаду.")
        return redirect(url)
    try:
        changed = services.refresh_requisites(user)
    except requisites.RequisitesUnavailable as exc:
        messages.error(request, f"Реквізити не оновлено. {exc} Спробуйте пізніше.")
        return redirect(url)
    if changed:
        names = ", ".join(kind.label for kind in changed)
        messages.success(request, f"Реквізити оновлено з сайту податкової. Змінились: {names}.")
    else:
        messages.success(request, "Реквізити перевірено на сайті податкової. Змін немає.")
    return redirect(url)


@login_required
def requisites_page(request):
    context = {
        **_base_context(request),
        "active_tab": "requisites",
        "requisite_slips": services.requisite_slips(request.user),
    }
    return render(request, "ledger/requisites.html", context)


@login_required
def settlements(request):
    year = _valid_settlement_year(request.GET.get("year"))
    accounts = services.get_settlements(request.user, year)
    selected_id = _int_or_none(request.GET.get("account"))
    # Default: select the first account
    selected = None
    if accounts:
        selected = next((a for a in accounts if a.id == selected_id), accounts[0])
    synced_at = selected.synced_at if selected else None
    context = {
        **_base_context(request),
        "active_tab": "settlements",
        "year": year,
        "years": services.settlement_years(),
        "accounts": accounts,
        "selected": selected,
        "operations": list(selected.operations.all()) if selected else [],
        "synced_at": synced_at,
    }
    return render(request, "ledger/settlements.html", context)


def _valid_settlement_year(value):
    year = _int_or_none(value)
    years = services.settlement_years()
    return year if year in years else services.today().year


@login_required
@require_POST
def settlements_sync(request):
    """
    Accept the signed OAuth2 credentials from the browser,
    exchange them for a Bearer token, fetch settlement data, and persist it.

    Expected JSON body:
      {
        "username": "{РНОКПП}-{РНОКПП}-{timestamp_ms}",
        "password": "<Base64 CAdES signature of the РНОКПП>",
        "year": 2026
      }
    """
    try:
        body = json.loads(request.body)
        kep_username = body.get("username", "").strip()
        kep_password = body.get("password", "").strip()
        year = int(body.get("year", services.today().year))
    except Exception:
        return JsonResponse({"error": "Невірний формат запиту."}, status=400)

    if not kep_username or not kep_password:
        return JsonResponse({"error": "Підпис відсутній."}, status=400)

    year = year if year in services.settlement_years() else services.today().year

    try:
        services.sync_settlements(request.user, kep_username, kep_password, year)
    except cabinet.SignatureExpiredError as exc:
        return JsonResponse({"error": str(exc)}, status=401)
    except cabinet.CabinetError as exc:
        logger.warning("Cabinet sync failed for user %s: %s", request.user.pk, exc)
        return JsonResponse({"error": str(exc)}, status=502)
    except Exception as exc:
        logger.exception("Settlements sync crashed for user %s", request.user.pk)
        return JsonResponse(
            {"error": f"Не вдалося обробити дані кабінету: {type(exc).__name__}: {exc}"},
            status=500,
        )

    return JsonResponse({"ok": True, "redirect": f"{reverse('settlements')}?year={year}"})



TSP_HOSTS = ("acsk.privatbank.ua",)


@login_required
@require_POST
def kep_tsp(request):
    """
    Forward an RFC 3161 time-stamp request to the key issuer's TSP server.

    The signing Worker runs on our origin and cannot reach plain-http TSP servers.
    Body: {"url": "<tsp url from the certificate>", "data": "<base64 DER request>"}
    """
    try:
        body = json.loads(request.body)
        url = body["url"]
        payload = base64.b64decode(body["data"])
    except (ValueError, KeyError, TypeError):
        return JsonResponse({"error": "Невірний формат запиту."}, status=400)

    if urlparse(url).hostname not in TSP_HOSTS:
        return JsonResponse({"error": "Сервер позначок часу не підтримується."}, status=400)

    try:
        resp = requests.post(
            url, data=payload, headers={"Content-Type": "application/tsp-request"}, timeout=10
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        return JsonResponse({"error": f"Сервер позначок часу недоступний: {exc}"}, status=502)

    return JsonResponse({"data": base64.b64encode(resp.content).decode()})
