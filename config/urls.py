from django.conf.urls.i18n import i18n_patterns
from django.contrib.auth import views as auth_views
from django.urls import include, path
from django.views.i18n import set_language

from apps.accounts.views import RateLimitedLoginView, RateLimitedPasswordResetView

urlpatterns = [path("i18n/set-language/", set_language, name="set_language")]

urlpatterns += i18n_patterns(
    path("accounts/login/", RateLimitedLoginView.as_view(), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path(
        "accounts/password-reset/",
        RateLimitedPasswordResetView.as_view(),
        name="password_reset",
    ),
    path(
        "accounts/password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(),
        name="password_reset_done",
    ),
    path(
        "accounts/reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path(
        "accounts/reset/done/",
        auth_views.PasswordResetCompleteView.as_view(),
        name="password_reset_complete",
    ),
    path("", include("apps.core.urls")),
    path("centers/", include("apps.centers.urls")),
    path("casework/", include("apps.casework.urls")),
)

handler403 = "apps.core.views.permission_denied_view"
handler404 = "apps.core.views.not_found_view"
handler500 = "apps.core.views.server_error_view"
