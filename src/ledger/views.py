from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import urlencode
from django.views.decorators.http import require_POST

from . import nbu, requisites, services
from .forms import IncomeForm, ProfileForm
from .models import IncomeEntry, MonthRecord

RECENT_LIMIT = 40
RATE_ERROR = "Не вдалося отримати курс НБУ. Спробуйте ще раз трохи пізніше."


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
        "year": year,
        "years": services.available_years(),
        "rows": rows,
        "has_data": has_data,
        "recent_entries": recent_entries,
        "income_form": income_form or IncomeForm(initial={"received_on": services.today()}),
        "profile_form": profile_form or ProfileForm(instance=user),
        "tax_group": services.TAX_GROUP,
        "dialog_data": services.dialog_data(year_entries, recent_entries),
        "currencies": IncomeEntry.Currency.choices,
        "open_dialog": open_dialog,
        "open_month": open_month or "",
        "requisite_slips": services.requisite_slips(user),
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
    year = _valid_year(request.POST.get("year"))
    form = ProfileForm(request.POST, instance=request.user)
    if form.is_valid():
        user = form.save()
        if form.cleaned_data["new_password"]:
            update_session_auth_hash(request, user)
        messages.success(request, "Дані кабінету збережено.")
        return redirect(dashboard_url(year))
    request.user.refresh_from_db()
    return render_dashboard(request, year, profile_form=form, open_dialog="cabinet", status=400)


@login_required
@require_POST
def refresh_requisites(request):
    url = dashboard_url(_valid_year(request.POST.get("year")))
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
