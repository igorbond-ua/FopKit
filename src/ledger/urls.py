from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path(
        "login/",
        auth_views.LoginView.as_view(template_name="ledger/login.html", redirect_authenticated_user=True),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("income/", views.income_add, name="income_add"),
    path("income/<int:entry_id>/", views.income_edit, name="income_edit"),
    path("income/<int:entry_id>/delete/", views.income_delete, name="income_delete"),
    path("months/<int:year>/<int:month>/<str:kind>/toggle/", views.toggle_paid, name="toggle_paid"),
    path("esv/", views.skip_esv, name="skip_esv"),
    path("profile/", views.profile, name="profile"),
    path("profile/sync/", views.profile_sync, name="profile_sync"),
    path("requisites/", views.requisites_page, name="requisites"),
    path("requisites/refresh/", views.refresh_requisites, name="refresh_requisites"),
    path("settlements/", views.settlements, name="settlements"),
    path("settlements/sync/", views.settlements_sync, name="settlements_sync"),
    path("kep/tsp/", views.kep_tsp, name="kep_tsp"),
]
