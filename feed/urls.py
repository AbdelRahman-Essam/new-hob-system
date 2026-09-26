from django.contrib.auth import views as auth_views
from django.urls import path
from . import views as v
urlpatterns = [
    path("login/", auth_views.LoginView.as_view(template_name="feed/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("users/", v.users_view, name="users"),
    path("users/new/", v.user_form, name="user_new"),
    path("users/<int:pk>/edit/", v.user_form, name="user_edit"),
    path("users/<int:pk>/delete/", v.user_delete, name="user_delete"),
    path("", v.dashboard, name="dashboard"),
    path("regions/", v.regions, name="regions"),
    path("regions/new/", v.region_form, name="region_new"),
    path("regions/<int:pk>/edit/", v.region_form, name="region_edit"),
    path("customers/", v.customers, name="customers"),
    path("customers/new/", v.customer_form, name="customer_new"),
    path("customers/<int:pk>/", v.customer_detail, name="customer_detail"),
    path("customers/<int:pk>/edit/", v.customer_form, name="customer_edit"),
    path("customers/<int:cpk>/tx/new/", v.tx_form, name="tx_new"),
    path("tx/<int:pk>/edit/", v.tx_form, name="tx_edit"),
    path("delete/<str:kind>/<int:pk>/", v.delete, name="delete"),
    path("reports/", v.report, name="report"),
    path("settings/", v.settings_view, name="settings"),
    path("backup/", v.backup, name="backup"),
    path("restore/", v.restore, name="restore"),
]
