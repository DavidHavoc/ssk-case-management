"""Authorized plan previews and draft editing. Signing lives in plan_signing."""

from datetime import datetime

from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from apps.accounts.roles import is_coordinator, is_system_manager
from apps.audit.models import AuditEvent
from apps.audit.services import record_event
from apps.core.authorization import (
    assessments_for_user,
    enrollments_for_user,
    get_authorized_object,
    plans_for_user,
    specialist_profile_for_user,
)
from apps.core.decorators import active_center_required

from .assessment_signing import CARE_NOTICE
from .forms import InterventionPlanForm, SignedPlanStatusForm
from .models import Assessment, CareNeedLevel, FunctionalDependencyLevel, IndividualPlan
from .services import save_plan_period
from .staffing import responsible_specialists


def barthel_summary(user, center, person, on_date):
    assessment = (
        assessments_for_user(user, center)
        .filter(
            beneficiary=person,
            scoring_tool=Assessment.ScoringTool.BARTHEL,
            status=Assessment.Status.COMPLETED,
            assessment_date__lte=on_date,
        )
        .order_by("-assessment_date", "-created_at")
        .first()
    )
    # An imported intake index has no verified assessment date. Show it separately
    # on the beneficiary page, rather than presenting it as a completed assessment.
    if not assessment:
        return None
    return {
        "assessment_id": str(assessment.pk),
        "date": assessment.assessment_date.isoformat(),
        "score": str(assessment.total_score),
        "dependency": str(assessment.get_functional_dependency_level_display()),
        "care_need": str(assessment.get_care_need_level_display()),
        "additional_care_needs": assessment.additional_care_needs,
    }


def preview_date(value):
    if not value:
        return timezone.localdate()
    try:
        return datetime.strptime(value, "%d/%m/%Y").date()
    except ValueError:
        result = parse_date(value)
        if result is None:
            raise ValueError("Invalid plan date") from None
        return result


def barthel_bands():
    return [
        {
            "range": score,
            "dependency": str(dict(FunctionalDependencyLevel.choices)[level]),
            "care_need": str(dict(CareNeedLevel.choices)[need]),
        }
        for score, level, need in (
            ("0-20", "total", "very_high"),
            ("21-60", "severe", "high"),
            ("61-90", "moderate", "moderate"),
            ("91-99", "slight", "low"),
            ("100", "independent", "minimal"),
        )
    ]


@active_center_required
@never_cache
@require_GET
def plan_beneficiary_preview(request):
    try:
        enrollment = get_authorized_object(
            enrollments_for_user(request.user, request.ssk_center), request.GET.get("enrollment")
        )
    except (ValidationError, ValueError, TypeError) as exc:
        raise Http404 from exc
    try:
        on_date = preview_date(request.GET.get("date", ""))
    except ValueError as exc:
        raise Http404 from exc
    specialists = (
        responsible_specialists(enrollment, on_date)
        .filter(center_assignments__center=request.ssk_center)
        .distinct()
    )
    if not (is_system_manager(request.user) or is_coordinator(request.user)):
        specialists = specialists.filter(
            pk=getattr(specialist_profile_for_user(request.user), "pk", None)
        )
    record_event(
        actor=request.user,
        center=request.ssk_center,
        event_type=AuditEvent.EventType.SENSITIVE_READ,
        target_type="PlanBeneficiaryPreview",
        target_id=enrollment.pk,
    )
    return JsonResponse(
        {
            "barthel": barthel_summary(
                request.user, request.ssk_center, enrollment.beneficiary, on_date
            ),
            "specialists": [{"id": str(item.pk), "label": str(item)} for item in specialists],
            "previous_plans": [
                {"id": str(item.pk), "label": str(item)}
                for item in plans_for_user(request.user, request.ssk_center).filter(
                    enrollment=enrollment, plan_kind=request.GET.get("kind", "individual")
                )
            ],
        }
    )


def intervention_plan_form(request, instance=None, initial_enrollment=None):
    plan = instance or IndividualPlan(
        center=request.ssk_center, workflow_version=2, plan_start_date=timezone.localdate()
    )
    if hasattr(plan, "signed_document"):
        form = SignedPlanStatusForm(
            request.POST if request.method == "POST" else None,
            instance=plan,
            user=request.user,
            center=request.ssk_center,
        )
        if request.method == "POST" and form.is_valid():
            with transaction.atomic():
                plan = save_plan_period(form.save(commit=False))
                record_event(
                    actor=request.user,
                    center=plan.center,
                    event_type=AuditEvent.EventType.UPDATE,
                    target_type="IndividualPlan",
                    target_id=plan.pk,
                )
            return redirect("plan_detail", pk=plan.pk)
        return render(
            request,
            "casework/plan_record_form.html",
            {
                "plan": plan,
                "form": form,
                "title": _("Update plan status"),
            },
        )
    if not instance:
        kind = request.GET.get("kind")
        if kind in IndividualPlan.Kind.values:
            plan.plan_kind = kind
    if initial_enrollment:
        plan.enrollment = initial_enrollment
        plan.beneficiary = initial_enrollment.beneficiary
    form = InterventionPlanForm(
        request.POST if request.method == "POST" else None,
        instance=plan,
        user=request.user,
        center=request.ssk_center,
    )
    if request.method == "POST" and "preview" not in request.POST and form.is_valid():
        try:
            with transaction.atomic():
                plan = form.save(commit=False)
                plan = save_plan_period(plan)
                record_event(
                    actor=request.user,
                    center=plan.center,
                    event_type=AuditEvent.EventType.UPDATE
                    if instance
                    else AuditEvent.EventType.CREATE,
                    target_type="IndividualPlan",
                    target_id=plan.pk,
                )
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            return redirect("plan_detail", pk=plan.pk)
    person = None
    try:
        enrollment_id = form.data.get("enrollment") if form.is_bound else plan.enrollment_id
        enrollment = form.fields["enrollment"].queryset.filter(pk=enrollment_id).first()
        person = enrollment.beneficiary if enrollment else None
    except (ValidationError, ValueError, TypeError):
        pass
    if "preview" in request.POST:
        form._errors = {}
    try:
        on_date = (
            preview_date(form.data.get("plan_start_date", ""))
            if form.is_bound
            else plan.plan_start_date
        )
    except ValueError:
        on_date = plan.plan_start_date
    return render(
        request,
        "casework/intervention_plan_form.html",
        {
            "form": form,
            "plan": plan,
            "barthel": barthel_summary(request.user, request.ssk_center, person, on_date)
            if person
            else None,
            "barthel_bands": barthel_bands(),
            "care_notice": CARE_NOTICE,
            "title": _("Update plan") if instance else _("New plan"),
        },
    )
