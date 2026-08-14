from django.contrib.auth.views import LoginView, PasswordResetView
from django.http import HttpResponseRedirect

from apps.audit.models import AuditEvent
from apps.audit.services import record_event

from .forms import RateLimitedAuthenticationForm, request_ip
from .models import LoginThrottle


class RateLimitedLoginView(LoginView):
    authentication_form = RateLimitedAuthenticationForm
    template_name = "registration/login.html"
    redirect_authenticated_user = True

    def form_valid(self, form):
        response = super().form_valid(form)
        record_event(
            actor=self.request.user,
            event_type=AuditEvent.EventType.LOGIN_SUCCESS,
            target_type="Authentication",
        )
        return response

    def form_invalid(self, form):
        record_event(
            actor=None,
            event_type=AuditEvent.EventType.LOGIN_FAILURE,
            target_type="Authentication",
            outcome=AuditEvent.Outcome.FAILURE,
        )
        return super().form_invalid(form)


class RateLimitedPasswordResetView(PasswordResetView):
    def form_valid(self, form):
        email = str(form.cleaned_data.get("email", ""))[:254]
        keys = [
            LoginThrottle.hash_key("password-reset-email", email),
            LoginThrottle.hash_key("password-reset-ip", request_ip(self.request)),
        ]
        if LoginThrottle.is_blocked(keys):
            return HttpResponseRedirect(self.get_success_url())
        LoginThrottle.register_failure(keys)
        return super().form_valid(form)
