from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods

from apps.audit.models import AuditEvent
from apps.audit.services import record_event
from apps.core.decorators import active_center_required

from .consent_signing import DOCUMENT_CSP
from .models import AttachmentParentType, IndividualPlan
from .plan_signing import (
    PlanSigningForm,
    authorized_plan,
    authorized_signed_plan,
    finalize_plan,
    issue_plan_token,
    plan_document_html,
    plan_review,
)
from .private_attachments import signed_plan_attachments


def _authorized(request, pk, *, signed=False, for_change=False):
    try:
        selector = authorized_signed_plan if signed else authorized_plan
        return selector(pk, request.user, request.ssk_center, for_change=for_change)
    except (Http404, PermissionDenied):
        record_event(
            actor=request.user,
            event_type=AuditEvent.EventType.SENSITIVE_READ,
            target_type="SignedPlan" if signed else "Plan",
            target_id=pk,
            outcome=AuditEvent.Outcome.DENIED,
        )
        raise


@active_center_required
@never_cache
@require_http_methods(["GET", "POST"])
def plan_sign(request, pk):
    plan = _authorized(request, pk, for_change=True)
    language = request.LANGUAGE_CODE if request.LANGUAGE_CODE in {"en", "ka"} else "en"
    form = PlanSigningForm(
        request.POST if request.method == "POST" else None, request.FILES or None
    )
    if request.method == "POST" and form.is_valid():
        try:
            record = finalize_plan(
                plan=plan,
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
                _("The signed plan could not be stored. Please try again with a fresh signature."),
            )
        else:
            return redirect("plan_detail", pk=record.plan_id)
    if plan.workflow_version != 2 or plan.status != IndividualPlan.Status.DRAFT:
        return redirect("plan_detail", pk=plan.pk)
    plan = _authorized(request, pk, for_change=True)
    review = plan_review(plan, language, request.user, request.ssk_center)
    token = issue_plan_token(plan, request.user, request.ssk_center, review)
    if form.is_bound:
        form.data = form.data.copy()
        form.data.update({"signature_data": "", "review_token": token, "reviewed": ""})
    else:
        form.initial.update(
            {
                "review_token": token,
                "signer_name": plan.beneficiary.full_name,
                "signer_role": "beneficiary",
            }
        )
    record_event(
        actor=request.user,
        center=request.ssk_center,
        event_type=AuditEvent.EventType.SENSITIVE_READ,
        target_type="PlanReview",
        target_id=plan.pk,
    )
    return render(
        request,
        "casework/plan_sign.html",
        {
            "plan": plan,
            "document": review,
            "form": form,
        },
    )


@active_center_required
@never_cache
@require_GET
def plan_print(request, pk):
    plan = _authorized(request, pk)
    if plan.workflow_version != 2:
        raise Http404
    signed = getattr(plan, "signed_document", None)
    if signed:
        return redirect("plan_document", pk=signed.pk)
    review = plan_review(plan, request.LANGUAGE_CODE, request.user, request.ssk_center)
    record_event(
        actor=request.user,
        center=request.ssk_center,
        event_type=AuditEvent.EventType.SENSITIVE_READ,
        target_type="PlanReview",
        target_id=plan.pk,
    )
    response = HttpResponse(plan_document_html(review), content_type="text/html; charset=utf-8")
    response["Content-Security-Policy"] = DOCUMENT_CSP
    return response


@active_center_required
@never_cache
@require_GET
def plan_document(request, pk):
    return _document_response(request, pk, download=False)


@active_center_required
@never_cache
@require_GET
def plan_download(request, pk):
    return _document_response(request, pk, download=True)


def _document_response(request, pk, *, download):
    record = _authorized(request, pk, signed=True)
    files = signed_plan_attachments(request.user, request.ssk_center)
    attachment = files.list(AttachmentParentType.SIGNED_PLAN, record.pk).get(
        original_filename="signed-plan.txt"
    )
    response = files.download(attachment.pk)
    response["Content-Type"] = "text/html; charset=utf-8"
    disposition = "attachment" if download else "inline"
    response["Content-Disposition"] = f'{disposition}; filename="signed-plan.html"'
    response["Content-Security-Policy"] = DOCUMENT_CSP
    return response


@active_center_required
@never_cache
@require_GET
def plan_signature_download(request, pk):
    record = _authorized(request, pk, signed=True)
    files = signed_plan_attachments(request.user, request.ssk_center)
    attachment = (
        files.list(AttachmentParentType.SIGNED_PLAN, record.pk)
        .exclude(original_filename="signed-plan.txt")
        .get()
    )
    return files.download(attachment.pk)
