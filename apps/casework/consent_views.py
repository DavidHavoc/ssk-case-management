"""Authenticated review and stored-document routes for assisted consent signing."""

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods

from apps.audit.models import AuditEvent
from apps.audit.services import record_event
from apps.core.decorators import active_center_required

from .consent_signing import (
    DOCUMENT_CSP,
    ConsentSigningForm,
    authorized_consent_beneficiary,
    authorized_signed_consent,
    consent_review,
    document_html,
    finalize_consent,
    issue_review_token,
)
from .models import AttachmentParentType
from .private_attachments import signed_consent_attachments


def _authorized(request, pk, *, signed=False):
    try:
        selector = authorized_signed_consent if signed else authorized_consent_beneficiary
        return selector(pk, request.user, request.ssk_center)
    except (Http404, PermissionDenied):
        record_event(
            actor=request.user,
            event_type=AuditEvent.EventType.SENSITIVE_READ,
            target_type="SignedConsent",
            target_id=pk,
            outcome=AuditEvent.Outcome.DENIED,
        )
        raise


@active_center_required
@never_cache
@require_http_methods(["GET", "POST"])
def consent_sign(request, pk):
    person = _authorized(request, pk)
    language = request.LANGUAGE_CODE if request.LANGUAGE_CODE in {"en", "ka"} else "en"
    review = consent_review(person, language)
    form = ConsentSigningForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            record = finalize_consent(
                person=person,
                actor=request.user,
                center=request.ssk_center,
                language=language,
                values=form.cleaned_data,
            )
        except ValidationError as exc:
            form.add_error(None, exc.messages)
        except OSError:
            form.add_error(
                None,
                _(
                    "The signed consent could not be stored. Please try again with a fresh "
                    "signature."
                ),
            )
        else:
            return redirect("consent_document", pk=record.pk)
    # Rebuild after failure. Never replay a submitted drawing onto an updated document.
    person = _authorized(request, pk)
    review = consent_review(person, language)
    token = issue_review_token(person, request.user, request.ssk_center, review)
    if form.is_bound:
        form.data = form.data.copy()
        form.data["signature_data"] = ""
        form.data["review_token"] = token
        form.data["reviewed"] = ""
    else:
        form.initial["review_token"] = token
    if request.method == "GET":
        record_event(
            actor=request.user,
            center=request.ssk_center,
            event_type=AuditEvent.EventType.SENSITIVE_READ,
            target_type="ConsentReview",
            target_id=person.pk,
        )
    return render(
        request,
        "casework/consent_sign.html",
        {"beneficiary": person, "document": review, "form": form},
    )


@active_center_required
@never_cache
@require_GET
def consent_print(request, pk):
    person = _authorized(request, pk)
    review = consent_review(person, request.LANGUAGE_CODE)
    record_event(
        actor=request.user,
        center=request.ssk_center,
        event_type=AuditEvent.EventType.SENSITIVE_READ,
        target_type="ConsentReview",
        target_id=person.pk,
    )
    response = HttpResponse(document_html(review), content_type="text/html; charset=utf-8")
    response["Content-Security-Policy"] = DOCUMENT_CSP
    return response


def _artifact(request, record):
    files = signed_consent_attachments(request.user, request.ssk_center)
    attachment = files.list(AttachmentParentType.SIGNED_CONSENT, record.pk).get(
        original_filename="signed-consent.txt"
    )
    return files.download(attachment.pk)


@active_center_required
@never_cache
@require_GET
def consent_document(request, pk):
    record = _authorized(request, pk, signed=True)
    response = _artifact(request, record)
    response["Content-Type"] = "text/html; charset=utf-8"
    response["Content-Disposition"] = 'inline; filename="signed-consent.html"'
    response["Content-Security-Policy"] = DOCUMENT_CSP
    return response


@active_center_required
@never_cache
@require_GET
def consent_download(request, pk):
    record = _authorized(request, pk, signed=True)
    response = _artifact(request, record)
    response["Content-Type"] = "text/html; charset=utf-8"
    response["Content-Disposition"] = 'attachment; filename="signed-consent.html"'
    response["Content-Security-Policy"] = DOCUMENT_CSP
    return response
