from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods

from apps.audit.models import AuditEvent
from apps.audit.services import record_event
from apps.core.decorators import active_center_required

from .assessment_signing import (
    AssessmentSigningForm,
    assessment_document_html,
    assessment_review,
    authorized_assessment,
    authorized_signed_assessment,
    finalize_assessment,
    issue_assessment_token,
)
from .consent_signing import DOCUMENT_CSP
from .models import Assessment, AttachmentParentType
from .private_attachments import signed_assessment_attachments


def _authorized(request, pk, *, signed=False, for_change=False):
    try:
        selector = authorized_signed_assessment if signed else authorized_assessment
        return selector(pk, request.user, request.ssk_center, for_change=for_change)
    except (Http404, PermissionDenied):
        record_event(
            actor=request.user,
            event_type=AuditEvent.EventType.SENSITIVE_READ,
            target_type="SignedAssessment" if signed else "Assessment",
            target_id=pk,
            outcome=AuditEvent.Outcome.DENIED,
        )
        raise


@active_center_required
@never_cache
@require_http_methods(["GET", "POST"])
def assessment_sign(request, pk):
    assessment = _authorized(request, pk, for_change=True)
    language = request.LANGUAGE_CODE if request.LANGUAGE_CODE in {"en", "ka"} else "en"
    form = AssessmentSigningForm(
        request.POST if request.method == "POST" else None, request.FILES or None
    )
    if request.method == "POST" and form.is_valid():
        try:
            record = finalize_assessment(
                assessment=assessment,
                actor=request.user,
                center=request.ssk_center,
                language=language,
                data=request.POST,
                files=request.FILES,
            )
        except ValidationError as exc:
            form.add_error(None, exc.messages)
        except OSError:
            from django.utils.translation import gettext as _

            form.add_error(
                None,
                _(
                    "The signed assessment could not be stored. Please try again with a "
                    "fresh signature."
                ),
            )
        else:
            return redirect("assessment_detail", pk=record.assessment_id)
    if assessment.status != Assessment.Status.DRAFT:
        return redirect("assessment_detail", pk=assessment.pk)
    assessment = _authorized(request, pk, for_change=True)
    review = assessment_review(assessment, language)
    token = issue_assessment_token(assessment, request.user, request.ssk_center, review)
    if form.is_bound:
        form.data = form.data.copy()
        form.data.update({"signature_data": "", "review_token": token, "reviewed": ""})
    else:
        form.initial.update(
            {
                "review_token": token,
                "signer_name": assessment.beneficiary.full_name,
                "signer_role": "beneficiary",
            }
        )
    record_event(
        actor=request.user,
        center=request.ssk_center,
        event_type=AuditEvent.EventType.SENSITIVE_READ,
        target_type="AssessmentReview",
        target_id=assessment.pk,
    )
    return render(
        request,
        "casework/assessment_sign.html",
        {
            "assessment": assessment,
            "document": review,
            "form": form,
        },
    )


@active_center_required
@never_cache
@require_GET
def assessment_print(request, pk):
    assessment = _authorized(request, pk)
    review = assessment_review(assessment, request.LANGUAGE_CODE)
    record_event(
        actor=request.user,
        center=request.ssk_center,
        event_type=AuditEvent.EventType.SENSITIVE_READ,
        target_type="AssessmentReview",
        target_id=assessment.pk,
    )
    response = HttpResponse(
        assessment_document_html(review), content_type="text/html; charset=utf-8"
    )
    response["Content-Security-Policy"] = DOCUMENT_CSP
    return response


@active_center_required
@never_cache
@require_GET
def assessment_document(request, pk):
    return _document_response(request, pk, download=False)


@active_center_required
@never_cache
@require_GET
def assessment_download(request, pk):
    return _document_response(request, pk, download=True)


def _document_response(request, pk, *, download):
    record = _authorized(request, pk, signed=True)
    files = signed_assessment_attachments(request.user, request.ssk_center)
    attachment = files.list(AttachmentParentType.SIGNED_ASSESSMENT, record.pk).get(
        original_filename="signed-assessment.txt"
    )
    response = files.download(attachment.pk)
    response["Content-Type"] = "text/html; charset=utf-8"
    disposition = "attachment" if download else "inline"
    response["Content-Disposition"] = f'{disposition}; filename="signed-assessment.html"'
    response["Content-Security-Policy"] = DOCUMENT_CSP
    return response


@active_center_required
@never_cache
@require_GET
def assessment_signature_download(request, pk):
    record = _authorized(request, pk, signed=True)
    files = signed_assessment_attachments(request.user, request.ssk_center)
    attachment = (
        files.list(AttachmentParentType.SIGNED_ASSESSMENT, record.pk)
        .exclude(original_filename="signed-assessment.txt")
        .get()
    )
    return files.download(attachment.pk)
