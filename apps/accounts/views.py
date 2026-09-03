from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.views import LoginView, PasswordChangeView
from django.db import transaction
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext as _

from apps.audit.models import AuditEvent
from apps.audit.services import record_event
from apps.core.authorization import casework_home_route

from .forms import RateLimitedAuthenticationForm, StyledPasswordChangeForm


class RateLimitedLoginView(LoginView):
    authentication_form = RateLimitedAuthenticationForm
    template_name = "registration/login.html"
    redirect_authenticated_user = True

    def get_success_url(self):
        redirect_url = self.get_redirect_url()
        if redirect_url:
            return redirect_url
        return reverse(casework_home_route(self.request.user))

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


class RequiredPasswordChangeView(PasswordChangeView):
    form_class = StyledPasswordChangeForm
    template_name = "registration/password_change_required.html"

    def get_success_url(self):
        return reverse(casework_home_route(self.request.user))

    def form_valid(self, form):
        with transaction.atomic():
            user = form.save()
            user.must_change_password = False
            user.save(update_fields=["must_change_password"])
            update_session_auth_hash(self.request, user)
            record_event(
                actor=user,
                event_type=AuditEvent.EventType.UPDATE,
                target_type="Authentication",
                metadata={"result": "required_password_changed"},
            )
        messages.success(self.request, _("Your password has been changed."))
        return redirect(self.get_success_url())
