from __future__ import annotations

from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from apps.core.forms import StyledFormMixin

from .models import LoginThrottle


def request_ip(request) -> str:
    if getattr(settings, "TRUST_X_FORWARDED_FOR", False):
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            return forwarded.split(",", 1)[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


class RateLimitedAuthenticationForm(AuthenticationForm):
    error_message = _("Unable to sign in. Check your credentials or try again later.")

    def _request_ip(self) -> str:
        return request_ip(self.request)

    def _throttle_keys(self) -> list[str]:
        username = str(self.data.get("username", ""))[:254]
        return [
            LoginThrottle.hash_key("username", username),
            LoginThrottle.hash_key("ip", self._request_ip()),
        ]

    def clean(self):
        keys = self._throttle_keys()
        if LoginThrottle.is_blocked(keys):
            raise ValidationError(self.error_message, code="rate_limited")
        try:
            cleaned_data = super().clean()
        except ValidationError as exc:
            LoginThrottle.register_failure(keys)
            raise ValidationError(self.error_message, code="invalid_login") from exc
        LoginThrottle.clear(keys)
        return cleaned_data


class StyledPasswordChangeForm(StyledFormMixin, PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_styles()
