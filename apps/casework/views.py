from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.db.models.deletion import ProtectedError
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.accounts.roles import is_coordinator, is_specialist, is_system_manager
from apps.audit.models import AuditEvent
from apps.audit.services import record_event
from apps.core.authorization import (
    assessments_for_user,
    assigned_beneficiaries_for_specialist,
    assigned_enrollments_for_specialist,
    beneficiaries_for_user,
    can_create_case_record,
    can_view_restricted_beneficiary_fields,
    current_assessments_for_user,
    diagnoses_for_user,
    enrollments_for_user,
    get_authorized_object,
    plans_for_user,
    schedules_for_user,
    social_statuses_for_user,
    summaries_for_user,
    visits_for_user,
)
from apps.core.decorators import active_center_required

from .assessment_engine import (
    comparison_for_assessment,
    complete_assessment,
    replace_draft_responses,
)
from .forms import (
    AssessmentForm,
    AssessmentResponseFormSet,
    BeneficiaryDiagnosisFormSet,
    BeneficiaryForm,
    BeneficiarySocialStatusFormSet,
    EnrollmentAssignmentFormSet,
    EnrollmentIntakeForm,
    EnrollmentServiceScheduleForm,
    EnrollmentTransferForm,
    EnrollmentTransitionForm,
    EnrollmentUpdateForm,
    GoalOutcomeMeasurementForm,
    IndividualPlanForm,
    IndividualPlanGoalForm,
    IndividualPlanGoalFormSet,
    IndividualPlanReviewForm,
    ServiceVisitForm,
    validate_plan_goals,
)
from .models import (
    Assessment,
    AttachmentParentType,
    Beneficiary,
    CenterServiceOffering,
    IndividualPlan,
    IndividualPlanGoal,
    PrivateAttachment,
    ServiceDefinition,
    ServiceEnrollment,
    ServiceVisit,
)
from .private_attachments import (
    case_attachments,
)
from .services import (
    create_enrollment,
    record_goal_status_transition,
    record_service_visit_correction,
    reenroll_beneficiary,
    save_plan_period,
    service_visit_snapshot,
    transfer_enrollment,
    transition_enrollment,
)
from .timeline import beneficiary_timeline_page
from .workspace import build_enrollment_workspace_rows, build_workspace_documents


def _page(request, queryset, per_page: int = 30):
    return Paginator(queryset, per_page).get_page(request.GET.get("page"))


def _can_manage_restricted(user) -> bool:
    return is_system_manager(user) or is_coordinator(user)


def _has_effective_active_enrollment(user, center) -> bool:
    on_date = timezone.localdate()
    return any(
        can_create_case_record(user, center, enrollment, on_date)
        for enrollment in enrollments_for_user(user, center, as_of=on_date)
    )


def _audit_read(request, obj, target_type: str) -> None:
    record_event(
        actor=request.user,
        event_type=AuditEvent.EventType.SENSITIVE_READ,
        target_type=target_type,
        target_id=obj.pk,
        center=getattr(obj, "center", None) or request.ssk_center,
    )


def _authorized_request_object(
    request,
    queryset,
    pk,
    target_type: str,
    *,
    event_type: str = AuditEvent.EventType.SENSITIVE_READ,
):
    try:
        return get_authorized_object(queryset, pk)
    except Http404:
        record_event(
            actor=request.user,
            event_type=event_type,
            target_type=target_type,
            target_id=pk,
            center=request.ssk_center,
            outcome=AuditEvent.Outcome.DENIED,
        )
        raise


def _legacy_intake_post(request):
    if request.method != "POST" or "enrollment-offering" in request.POST:
        return request.POST or None
    legacy_service_type = request.POST.get("service_type", "other")
    service = ServiceDefinition.objects.filter(
        code=f"LEGACY-{legacy_service_type.replace('_', '-').upper()}"
    ).first()
    offering = CenterServiceOffering.objects.filter(
        center=request.ssk_center,
        service=service,
        is_active=True,
    ).first()
    data = request.POST.copy()
    if offering:
        data["enrollment-offering"] = str(offering.pk)
    code = request.POST.get("beneficiary_code", "").strip().upper()
    data["enrollment-episode_code"] = f"{code}-E01"
    legacy_status = request.POST.get("service_status", "applied")
    data["enrollment-status"] = {
        "active": ServiceEnrollment.Status.ACTIVE,
        "on_hold": ServiceEnrollment.Status.PENDING,
        "exited": ServiceEnrollment.Status.PENDING,
    }.get(legacy_status, ServiceEnrollment.Status.PENDING)
    data["enrollment-start_date"] = request.POST.get("enrollment_date") or str(timezone.localdate())
    return data


def _beneficiary_list(request, *, specialist_workspace=False):
    if specialist_workspace:
        if not is_specialist(request.user):
            raise PermissionDenied
        queryset = assigned_beneficiaries_for_specialist(request.user, request.ssk_center)
        authorized_enrollments = assigned_enrollments_for_specialist(
            request.user,
            request.ssk_center,
        )
    else:
        queryset = beneficiaries_for_user(request.user, request.ssk_center)
        authorized_enrollments = enrollments_for_user(request.user, request.ssk_center)
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    service_type = request.GET.get("service_type", "").strip()
    if query:
        queryset = queryset.filter(
            Q(full_name__icontains=query) | Q(beneficiary_code__icontains=query)
        )
    if status:
        queryset = queryset.filter(enrollments__in=authorized_enrollments.filter(status=status))
    if service_type:
        queryset = queryset.filter(
            enrollments__in=authorized_enrollments.filter(service_id=service_type)
        )
    queryset = queryset.distinct()
    page_obj = _page(request, queryset)
    page_enrollments = authorized_enrollments.filter(
        beneficiary_id__in=[beneficiary.pk for beneficiary in page_obj.object_list]
    )
    workspace_rows = build_enrollment_workspace_rows(
        page_enrollments,
        visits=visits_for_user(request.user, request.ssk_center),
        assessments=current_assessments_for_user(request.user, request.ssk_center),
        plans=plans_for_user(request.user, request.ssk_center),
        as_of=timezone.localdate(),
    )
    rows_by_beneficiary = {}
    for row in workspace_rows:
        rows_by_beneficiary.setdefault(row.enrollment.beneficiary_id, []).append(row)
    for beneficiary in page_obj.object_list:
        beneficiary.workspace_enrollments = rows_by_beneficiary.get(beneficiary.pk, [])
    return render(
        request,
        "casework/beneficiary_list.html",
        {
            "page_obj": page_obj,
            "query": query,
            "selected_status": status,
            "selected_service_type": service_type,
            "status_choices": ServiceEnrollment.Status.choices,
            "service_type_choices": ServiceDefinition.objects.filter(is_active=True),
            "can_create": _can_manage_restricted(request.user) and not specialist_workspace,
            "specialist_workspace": specialist_workspace,
        },
    )


@active_center_required
def beneficiary_list(request):
    return _beneficiary_list(request)


@active_center_required
def specialist_workspace(request):
    return _beneficiary_list(request, specialist_workspace=True)


@active_center_required
def beneficiary_detail(request, pk):
    beneficiary = _authorized_request_object(
        request,
        beneficiaries_for_user(request.user, request.ssk_center),
        pk,
        "Beneficiary",
    )
    authorized_enrollments = enrollments_for_user(request.user, request.ssk_center).filter(
        beneficiary=beneficiary
    )
    selected_enrollment = None
    selected_id = request.GET.get("enrollment")
    if selected_id:
        selected_enrollment = authorized_enrollments.filter(pk=selected_id).first()
        if selected_enrollment is None:
            record_event(
                actor=request.user,
                event_type=AuditEvent.EventType.SENSITIVE_READ,
                target_type="ServiceEnrollment",
                outcome=AuditEvent.Outcome.DENIED,
                center=request.ssk_center,
            )
            raise Http404
    if selected_enrollment is None:
        selected_enrollment = authorized_enrollments.first()
    if selected_enrollment is None:
        raise Http404
    restricted = can_view_restricted_beneficiary_fields(
        request.user, beneficiary, request.ssk_center
    )
    beneficiary_attachments = (
        case_attachments(request.user, request.ssk_center).list(
            AttachmentParentType.BENEFICIARY, beneficiary.pk
        )
        if restricted
        else []
    )
    _audit_read(request, beneficiary, "Beneficiary")
    timeline_page = beneficiary_timeline_page(
        user=request.user,
        center=request.ssk_center,
        beneficiary=beneficiary,
        enrollment=selected_enrollment,
        page_number=request.GET.get("timeline_page"),
    )
    authorized_visits = visits_for_user(request.user, request.ssk_center).filter(
        enrollment=selected_enrollment
    )
    authorized_schedules = schedules_for_user(request.user, request.ssk_center).filter(
        enrollment=selected_enrollment
    )
    authorized_assessments = current_assessments_for_user(
        request.user,
        request.ssk_center,
    ).filter(enrollment=selected_enrollment)
    authorized_plans = plans_for_user(request.user, request.ssk_center).filter(
        enrollment=selected_enrollment
    )
    workspace_summary = build_enrollment_workspace_rows(
        [selected_enrollment],
        visits=authorized_visits,
        assessments=authorized_assessments,
        plans=authorized_plans,
        as_of=timezone.localdate(),
    )[0]
    related_attachments = case_attachments(
        request.user,
        request.ssk_center,
    ).timeline_for_beneficiary(beneficiary, selected_enrollment)
    workspace_documents = build_workspace_documents(
        related_attachments,
        beneficiary_attachments=beneficiary_attachments,
        beneficiary_id=beneficiary.pk,
    )
    can_add_case_record = can_create_case_record(
        request.user,
        request.ssk_center,
        selected_enrollment,
        timezone.localdate(),
    )
    return render(
        request,
        "casework/beneficiary_detail.html",
        {
            "beneficiary": beneficiary,
            "enrollments": authorized_enrollments,
            "selected_enrollment": selected_enrollment,
            "diagnoses": diagnoses_for_user(
                request.user,
                request.ssk_center,
                enrollment=selected_enrollment,
            ),
            "social_statuses": social_statuses_for_user(
                request.user,
                request.ssk_center,
                enrollment=selected_enrollment,
            ),
            "show_restricted": restricted,
            "workspace_summary": workspace_summary,
            "workspace_visits": authorized_visits[:10],
            "workspace_schedules": authorized_schedules[:10],
            "workspace_assessments": authorized_assessments[:10],
            "workspace_plans": authorized_plans.prefetch_related("goals")[:10],
            "workspace_documents": workspace_documents,
            "attachment_parent_type": AttachmentParentType.BENEFICIARY,
            "can_delete": is_system_manager(request.user),
            "can_add_case_record": can_add_case_record,
            "timeline_page": timeline_page,
        },
    )


@active_center_required
def beneficiary_create(request):
    if not _can_manage_restricted(request.user):
        raise PermissionDenied
    beneficiary = Beneficiary(center=request.ssk_center)
    form = BeneficiaryForm(
        request.POST or None, instance=beneficiary, user=request.user, center=request.ssk_center
    )
    intake_data = _legacy_intake_post(request)
    enrollment_form = EnrollmentIntakeForm(
        intake_data,
        prefix="enrollment",
        center=request.ssk_center,
    )
    enrollment_draft = ServiceEnrollment(beneficiary=beneficiary)
    formset = EnrollmentAssignmentFormSet(
        request.POST or None,
        instance=enrollment_draft,
        prefix="assignments",
        form_kwargs={"center": request.ssk_center},
    )
    attachment_workflow = case_attachments(request.user, request.ssk_center)
    attachment_form = attachment_workflow.optional_form(
        request.POST or None,
        request.FILES or None,
        prefix="attachment",
    )
    if request.method == "POST":
        form_valid = form.is_valid()
        enrollment_valid = enrollment_form.is_valid()
        formset_valid = formset.is_valid()
        attachment_valid = attachment_form.is_valid()
        if form_valid and enrollment_valid and formset_valid and attachment_valid:
            with attachment_workflow.atomic_uploads() as attachment_uploader:
                beneficiary = form.save()
                enrollment = create_enrollment(
                    beneficiary=beneficiary,
                    offering=enrollment_form.cleaned_data["offering"],
                    episode_code=enrollment_form.cleaned_data["episode_code"],
                    start_date=enrollment_form.cleaned_data["start_date"],
                    status=enrollment_form.cleaned_data["status"],
                    first_service_date=enrollment_form.cleaned_data["first_service_date"],
                    application_contract_number=enrollment_form.cleaned_data[
                        "application_contract_number"
                    ],
                    notes=enrollment_form.cleaned_data["notes"],
                    actor=request.user,
                )
                formset.instance = enrollment
                formset.save()
                record_event(
                    actor=request.user,
                    event_type=AuditEvent.EventType.CREATE,
                    target_type="Beneficiary",
                    target_id=beneficiary.pk,
                    center=beneficiary.center,
                )
                attachment_uploader.create(
                    parent=beneficiary,
                    parent_type=AttachmentParentType.BENEFICIARY,
                    upload=attachment_form.cleaned_data.get("file"),
                )
            messages.success(request, _("Beneficiary created."))
            return redirect("beneficiary_detail", pk=beneficiary.pk)
    return render(
        request,
        "casework/beneficiary_form.html",
        {
            "form": form,
            "enrollment_form": enrollment_form,
            "formset": formset,
            "attachment_form": attachment_form,
            "title": _("New beneficiary"),
        },
    )


@active_center_required
def beneficiary_update(request, pk):
    beneficiary = _authorized_request_object(
        request,
        beneficiaries_for_user(request.user, request.ssk_center),
        pk,
        "Beneficiary",
        event_type=AuditEvent.EventType.UPDATE,
    )
    form = BeneficiaryForm(
        request.POST or None,
        instance=beneficiary,
        user=request.user,
        center=request.ssk_center,
    )
    diagnosis_formset = None
    social_status_formset = None
    if _can_manage_restricted(request.user):
        classification_data = (
            request.POST
            if request.method == "POST" and "diagnoses-TOTAL_FORMS" in request.POST
            else None
        )
        diagnosis_formset = BeneficiaryDiagnosisFormSet(
            classification_data,
            instance=beneficiary,
            prefix="diagnoses",
            queryset=diagnoses_for_user(request.user, request.ssk_center),
            form_kwargs={
                "beneficiary": beneficiary,
                "user": request.user,
                "center": request.ssk_center,
            },
        )
        status_data = (
            request.POST
            if request.method == "POST" and "social-statuses-TOTAL_FORMS" in request.POST
            else None
        )
        social_status_formset = BeneficiarySocialStatusFormSet(
            status_data,
            instance=beneficiary,
            prefix="social-statuses",
            queryset=social_statuses_for_user(request.user, request.ssk_center),
            form_kwargs={
                "beneficiary": beneficiary,
                "user": request.user,
                "center": request.ssk_center,
            },
        )
    diagnosis_valid = (
        diagnosis_formset.is_valid()
        if request.method == "POST" and diagnosis_formset and diagnosis_formset.is_bound
        else True
    )
    status_valid = (
        social_status_formset.is_valid()
        if request.method == "POST" and social_status_formset and social_status_formset.is_bound
        else True
    )
    if request.method == "POST" and form.is_valid() and diagnosis_valid and status_valid:
        with transaction.atomic():
            form.save()
            if diagnosis_formset and diagnosis_formset.is_bound:
                rows = diagnosis_formset.save(commit=False)
                for row in rows:
                    row.recorded_by = request.user
                    row.save()
                for row in diagnosis_formset.deleted_objects:
                    row.delete()
            if social_status_formset and social_status_formset.is_bound:
                rows = social_status_formset.save(commit=False)
                for row in rows:
                    row.recorded_by = request.user
                    row.save()
                for row in social_status_formset.deleted_objects:
                    row.delete()
            record_event(
                actor=request.user,
                event_type=AuditEvent.EventType.UPDATE,
                target_type="Beneficiary",
                target_id=beneficiary.pk,
                center=beneficiary.center,
            )
        messages.success(request, _("Beneficiary updated."))
        return redirect("beneficiary_detail", pk=beneficiary.pk)
    return render(
        request,
        "casework/beneficiary_form.html",
        {
            "form": form,
            "diagnosis_formset": diagnosis_formset,
            "social_status_formset": social_status_formset,
            "title": _("Update beneficiary"),
        },
    )


def _authorized_enrollment(request, pk) -> ServiceEnrollment:
    return _authorized_request_object(
        request,
        enrollments_for_user(request.user, request.ssk_center),
        pk,
        "ServiceEnrollment",
    )


def _initial_enrollment_for_create(request) -> ServiceEnrollment | None:
    enrollment_id = request.GET.get("enrollment", "").strip()
    if not enrollment_id:
        return None
    return _authorized_request_object(
        request,
        enrollments_for_user(request.user, request.ssk_center),
        enrollment_id,
        "ServiceEnrollment",
        event_type=AuditEvent.EventType.CREATE,
    )


@active_center_required
def enrollment_create(request, beneficiary_pk):
    if not _can_manage_restricted(request.user):
        raise PermissionDenied
    beneficiary = get_authorized_object(
        beneficiaries_for_user(request.user, request.ssk_center), beneficiary_pk
    )
    form = EnrollmentIntakeForm(
        request.POST or None,
        center=request.ssk_center,
    )
    draft = ServiceEnrollment(beneficiary=beneficiary)
    formset = EnrollmentAssignmentFormSet(
        request.POST or None,
        instance=draft,
        prefix="assignments",
        form_kwargs={"center": request.ssk_center},
    )
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        try:
            with transaction.atomic():
                enrollment = create_enrollment(
                    beneficiary=beneficiary,
                    offering=form.cleaned_data["offering"],
                    episode_code=form.cleaned_data["episode_code"],
                    start_date=form.cleaned_data["start_date"],
                    status=form.cleaned_data["status"],
                    first_service_date=form.cleaned_data["first_service_date"],
                    application_contract_number=form.cleaned_data["application_contract_number"],
                    notes=form.cleaned_data["notes"],
                    actor=request.user,
                )
                formset.instance = enrollment
                formset.save()
                record_event(
                    actor=request.user,
                    event_type=AuditEvent.EventType.CREATE,
                    target_type="ServiceEnrollment",
                    target_id=enrollment.pk,
                    center=request.ssk_center,
                )
        except (ValidationError, ValueError) as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, _("Service enrollment created."))
            return redirect(
                f"{reverse('beneficiary_detail', kwargs={'pk': beneficiary.pk})}"
                f"?enrollment={enrollment.pk}"
            )
    return render(
        request,
        "casework/enrollment_form.html",
        {
            "form": form,
            "formset": formset,
            "beneficiary": beneficiary,
            "title": _("New service enrollment"),
        },
    )


@active_center_required
def enrollment_update(request, pk):
    if not _can_manage_restricted(request.user):
        raise PermissionDenied
    enrollment = _authorized_enrollment(request, pk)
    form = EnrollmentUpdateForm(request.POST or None, instance=enrollment)
    formset = EnrollmentAssignmentFormSet(
        request.POST or None,
        instance=enrollment,
        prefix="assignments",
        form_kwargs={"center": request.ssk_center},
    )
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        with transaction.atomic():
            form.save()
            formset.save()
            record_event(
                actor=request.user,
                event_type=AuditEvent.EventType.UPDATE,
                target_type="ServiceEnrollment",
                target_id=enrollment.pk,
                center=request.ssk_center,
            )
        messages.success(request, _("Service enrollment updated."))
        return redirect(
            f"{reverse('beneficiary_detail', kwargs={'pk': enrollment.beneficiary_id})}"
            f"?enrollment={enrollment.pk}"
        )
    return render(
        request,
        "casework/enrollment_form.html",
        {
            "form": form,
            "formset": formset,
            "beneficiary": enrollment.beneficiary,
            "enrollment": enrollment,
            "title": _("Update service enrollment"),
        },
    )


@active_center_required
def enrollment_transition(request, pk, action):
    if not _can_manage_restricted(request.user):
        raise PermissionDenied
    enrollment = _authorized_enrollment(request, pk)
    actions = {
        "admit": (ServiceEnrollment.Status.ACTIVE, _("Admit enrollment")),
        "suspend": (ServiceEnrollment.Status.SUSPENDED, _("Suspend enrollment")),
        "resume": (ServiceEnrollment.Status.ACTIVE, _("Resume enrollment")),
        "complete": (ServiceEnrollment.Status.COMPLETED, _("Complete enrollment")),
        "exit": (ServiceEnrollment.Status.EXITED, _("Exit enrollment")),
        "cancel": (ServiceEnrollment.Status.CANCELLED, _("Cancel enrollment")),
    }
    if action not in actions:
        raise Http404
    new_state, title = actions[action]
    form = EnrollmentTransitionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            transition_enrollment(
                enrollment,
                new_state=new_state,
                effective_date=form.cleaned_data["effective_date"],
                reason=form.cleaned_data["reason"],
                notes=form.cleaned_data["notes"],
                actor=request.user,
            )
        except (ValidationError, ValueError) as exc:
            form.add_error(None, exc)
        else:
            record_event(
                actor=request.user,
                event_type=AuditEvent.EventType.UPDATE,
                target_type="ServiceEnrollment",
                target_id=enrollment.pk,
                center=request.ssk_center,
            )
            messages.success(request, _("Enrollment history updated."))
            return redirect(
                f"{reverse('beneficiary_detail', kwargs={'pk': enrollment.beneficiary_id})}"
                f"?enrollment={enrollment.pk}"
            )
    return render(
        request,
        "casework/simple_form.html",
        {"form": form, "title": title, "enrollment": enrollment},
    )


@active_center_required
def enrollment_transfer(request, pk):
    if not _can_manage_restricted(request.user):
        raise PermissionDenied
    enrollment = _authorized_enrollment(request, pk)
    form = EnrollmentTransferForm(request.POST or None, enrollment=enrollment)
    if request.method == "POST" and form.is_valid():
        try:
            transfer_enrollment(
                enrollment,
                destination_offering=form.cleaned_data["destination_offering"],
                effective_date=form.cleaned_data["effective_date"],
                reason=form.cleaned_data["reason"],
                notes=form.cleaned_data["notes"],
                actor=request.user,
            )
        except (ValidationError, ValueError) as exc:
            form.add_error(None, exc)
        else:
            record_event(
                actor=request.user,
                event_type=AuditEvent.EventType.UPDATE,
                target_type="ServiceEnrollment",
                target_id=enrollment.pk,
                center=request.ssk_center,
            )
            messages.success(request, _("Enrollment transferred."))
            return redirect("beneficiary_list")
    return render(
        request,
        "casework/simple_form.html",
        {"form": form, "title": _("Transfer enrollment"), "enrollment": enrollment},
    )


@active_center_required
def enrollment_reenroll(request, pk):
    if not _can_manage_restricted(request.user):
        raise PermissionDenied
    prior = _authorized_enrollment(request, pk)
    form = EnrollmentIntakeForm(
        request.POST or None,
        center=request.ssk_center,
        service=prior.service,
    )
    draft = ServiceEnrollment(beneficiary=prior.beneficiary, service=prior.service)
    formset = EnrollmentAssignmentFormSet(
        request.POST or None,
        instance=draft,
        prefix="assignments",
        form_kwargs={"center": request.ssk_center},
    )
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        try:
            with transaction.atomic():
                enrollment = reenroll_beneficiary(
                    prior,
                    offering=form.cleaned_data["offering"],
                    episode_code=form.cleaned_data["episode_code"],
                    start_date=form.cleaned_data["start_date"],
                    status=form.cleaned_data["status"],
                    application_contract_number=form.cleaned_data["application_contract_number"],
                    notes=form.cleaned_data["notes"],
                    actor=request.user,
                )
                formset.instance = enrollment
                formset.save()
        except (ValidationError, ValueError) as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, _("Beneficiary re-enrolled."))
            return redirect(
                f"{reverse('beneficiary_detail', kwargs={'pk': prior.beneficiary_id})}"
                f"?enrollment={enrollment.pk}"
            )
    return render(
        request,
        "casework/enrollment_form.html",
        {
            "form": form,
            "formset": formset,
            "beneficiary": prior.beneficiary,
            "enrollment": prior,
            "title": _("Re-enroll beneficiary"),
        },
    )


def _case_list(request, *, model, selector, template_name, choices):
    queryset = selector(request.user, request.ssk_center)
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    if query:
        queryset = queryset.filter(
            Q(beneficiary__full_name__icontains=query)
            | Q(beneficiary__beneficiary_code__icontains=query)
            | Q(enrollment__episode_code__icontains=query)
        )
    if status:
        queryset = queryset.filter(**{choices[0]: status})
    page_obj = _page(request, queryset)
    return render(
        request,
        template_name,
        {
            "page_obj": page_obj,
            "query": query,
            "selected_status": status,
            "status_choices": choices[1],
            "can_create": _has_effective_active_enrollment(request.user, request.ssk_center),
            "can_manage_enrollments": _can_manage_restricted(request.user),
        },
    )


@active_center_required
def visit_list(request):
    return _case_list(
        request,
        model=ServiceVisit,
        selector=visits_for_user,
        template_name="casework/visit_list.html",
        choices=("status", ServiceVisit.Status.choices),
    )


@active_center_required
def visit_detail(request, pk):
    visit = _authorized_request_object(
        request,
        visits_for_user(request.user, request.ssk_center),
        pk,
        "ServiceVisit",
    )
    attachments = case_attachments(request.user, request.ssk_center).list(
        AttachmentParentType.SERVICE_VISIT, visit.pk
    )
    _audit_read(request, visit, "ServiceVisit")
    return render(
        request,
        "casework/visit_detail.html",
        {
            "visit": visit,
            "attachments": attachments,
            "attachment_parent_type": AttachmentParentType.SERVICE_VISIT,
            "can_change_parent": visits_for_user(request.user, request.ssk_center, for_change=True)
            .filter(pk=visit.pk)
            .exists(),
            "can_delete": is_system_manager(request.user),
            "corrections": visit.corrections.select_related("corrected_by"),
        },
    )


@active_center_required
def visit_create(request):
    return _simple_case_form(
        request,
        model=ServiceVisit,
        form_class=ServiceVisitForm,
        title=_("New service visit"),
        detail_route="visit_detail",
        target_type="ServiceVisit",
        initial_enrollment=_initial_enrollment_for_create(request),
    )


@active_center_required
def visit_update(request, pk):
    visit = _authorized_request_object(
        request,
        visits_for_user(request.user, request.ssk_center, for_change=True),
        pk,
        "ServiceVisit",
        event_type=AuditEvent.EventType.UPDATE,
    )
    return _simple_case_form(
        request,
        model=ServiceVisit,
        form_class=ServiceVisitForm,
        title=_("Update service visit"),
        detail_route="visit_detail",
        target_type="ServiceVisit",
        instance=visit,
    )


def _simple_case_form(
    request,
    *,
    model,
    form_class,
    title,
    detail_route,
    target_type,
    instance=None,
    initial_enrollment=None,
):
    before_values = (
        service_visit_snapshot(instance)
        if instance is not None and isinstance(instance, ServiceVisit)
        else None
    )
    draft = model(center=request.ssk_center)
    if initial_enrollment is not None:
        draft.enrollment = initial_enrollment
        draft.beneficiary = initial_enrollment.beneficiary
    form = form_class(
        request.POST or None,
        instance=instance or draft,
        user=request.user,
        center=request.ssk_center,
    )
    attachment_workflow = case_attachments(request.user, request.ssk_center)
    attachment_form = (
        attachment_workflow.optional_form(
            request.POST or None,
            request.FILES or None,
            prefix="attachment",
        )
        if instance is None
        else None
    )
    if request.method == "POST":
        form_valid = form.is_valid()
        attachment_valid = attachment_form.is_valid() if attachment_form else True
        if form_valid and attachment_valid:
            with attachment_workflow.atomic_uploads() as attachment_uploader:
                obj = form.save()
                if before_values is not None:
                    record_service_visit_correction(
                        visit=obj,
                        corrected_by=request.user,
                        reason=form.cleaned_data["correction_reason"],
                        before_values=before_values,
                    )
                record_event(
                    actor=request.user,
                    event_type=(
                        AuditEvent.EventType.UPDATE if instance else AuditEvent.EventType.CREATE
                    ),
                    target_type=target_type,
                    target_id=obj.pk,
                    center=obj.center,
                )
                if attachment_form:
                    attachment_uploader.create(
                        parent=obj,
                        parent_type=AttachmentParentType.SERVICE_VISIT,
                        upload=attachment_form.cleaned_data.get("file"),
                    )
            messages.success(request, _("Changes saved."))
            return redirect(detail_route, pk=obj.pk)
    return render(
        request,
        "casework/simple_form.html",
        {"form": form, "attachment_form": attachment_form, "title": title},
    )


@active_center_required
def schedule_list(request):
    queryset = schedules_for_user(request.user, request.ssk_center)
    month = request.GET.get("month", "").strip()
    query = request.GET.get("q", "").strip()
    if month:
        try:
            year, month_number = [int(part) for part in month.split("-", 1)]
            queryset = queryset.filter(
                schedule_month__year=year,
                schedule_month__month=month_number,
            )
        except (TypeError, ValueError):
            messages.error(request, _("Month must use YYYY-MM format."))
    if query:
        queryset = queryset.filter(
            Q(enrollment__beneficiary__full_name__icontains=query)
            | Q(enrollment__beneficiary__beneficiary_code__icontains=query)
            | Q(enrollment__episode_code__icontains=query)
        )
    page_obj = _page(request, queryset)
    changeable_schedule_ids = set(
        schedules_for_user(request.user, request.ssk_center, for_change=True)
        .filter(pk__in=[row.pk for row in page_obj.object_list])
        .values_list("pk", flat=True)
    )
    return render(
        request,
        "casework/schedule_list.html",
        {
            "page_obj": page_obj,
            "selected_month": month,
            "query": query,
            "changeable_schedule_ids": changeable_schedule_ids,
            "can_create": _has_effective_active_enrollment(request.user, request.ssk_center),
            "can_manage_enrollments": _can_manage_restricted(request.user),
        },
    )


def _schedule_form(request, *, instance=None, enrollment=None):
    form = EnrollmentServiceScheduleForm(
        request.POST or None,
        instance=instance,
        user=request.user,
        center=request.ssk_center,
        enrollment=enrollment,
    )
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            schedule = form.save()
            record_event(
                actor=request.user,
                event_type=(
                    AuditEvent.EventType.UPDATE if instance else AuditEvent.EventType.CREATE
                ),
                target_type="EnrollmentServiceSchedule",
                target_id=schedule.pk,
                center=request.ssk_center,
            )
        messages.success(request, _("Service schedule saved."))
        return redirect("schedule_list")
    return render(
        request,
        "casework/simple_form.html",
        {
            "form": form,
            "title": _("Update monthly service schedule")
            if instance
            else _("New monthly service schedule"),
        },
    )


@active_center_required
def schedule_create(request, enrollment_pk=None):
    enrollment = None
    if enrollment_pk:
        enrollment = _authorized_request_object(
            request,
            enrollments_for_user(request.user, request.ssk_center),
            enrollment_pk,
            "ServiceEnrollment",
            event_type=AuditEvent.EventType.CREATE,
        )
    return _schedule_form(request, enrollment=enrollment)


@active_center_required
def schedule_update(request, pk):
    schedule = _authorized_request_object(
        request,
        schedules_for_user(request.user, request.ssk_center, for_change=True),
        pk,
        "EnrollmentServiceSchedule",
        event_type=AuditEvent.EventType.UPDATE,
    )
    return _schedule_form(request, instance=schedule)


@active_center_required
def assessment_list(request):
    return _case_list(
        request,
        model=Assessment,
        selector=current_assessments_for_user,
        template_name="casework/assessment_list.html",
        choices=("assessment_type", Assessment.AssessmentType.choices),
    )


@active_center_required
def assessment_detail(request, pk):
    assessment = _authorized_request_object(
        request,
        assessments_for_user(request.user, request.ssk_center),
        pk,
        "Assessment",
    )
    attachments = case_attachments(request.user, request.ssk_center).list(
        AttachmentParentType.ASSESSMENT, assessment.pk
    )
    _audit_read(request, assessment, "Assessment")
    return render(
        request,
        "casework/assessment_detail.html",
        {
            "assessment": assessment,
            "attachments": attachments,
            "attachment_parent_type": AttachmentParentType.ASSESSMENT,
            "can_change_parent": assessments_for_user(
                request.user, request.ssk_center, for_change=True
            )
            .filter(pk=assessment.pk)
            .exists(),
            "can_delete": (
                is_system_manager(request.user) and assessment.status == Assessment.Status.DRAFT
            ),
            "comparison": comparison_for_assessment(assessment),
        },
    )


@active_center_required
def assessment_create(request):
    return _assessment_form(
        request,
        initial_enrollment=_initial_enrollment_for_create(request),
    )


@active_center_required
def assessment_update(request, pk):
    assessment = _authorized_request_object(
        request,
        assessments_for_user(request.user, request.ssk_center, for_change=True),
        pk,
        "Assessment",
        event_type=AuditEvent.EventType.UPDATE,
    )
    return _assessment_form(request, assessment)


def _assessment_form(request, instance=None, initial_enrollment=None):
    assessment = instance or Assessment(center=request.ssk_center)
    if initial_enrollment is not None:
        assessment.enrollment = initial_enrollment
        assessment.beneficiary = initial_enrollment.beneficiary
    if not instance and request.method == "GET" and request.GET.get("template_version"):
        try:
            assessment._meta.get_field("template_version").target_field.to_python(
                request.GET["template_version"]
            )
        except (TypeError, ValueError, ValidationError):
            pass
        else:
            assessment.template_version_id = request.GET["template_version"]
    form = AssessmentForm(
        request.POST or None,
        instance=assessment,
        user=request.user,
        center=request.ssk_center,
    )
    selected_template_id = (
        request.POST.get("template_version")
        if request.method == "POST"
        else assessment.template_version_id
    )
    try:
        selected_template = (
            form.fields["template_version"].queryset.filter(pk=selected_template_id).first()
        )
    except (TypeError, ValueError, ValidationError):
        selected_template = None
    formset = AssessmentResponseFormSet(
        request.POST or None,
        prefix="responses",
        template_version=selected_template,
        assessment=assessment,
    )
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        try:
            with transaction.atomic():
                assessment = form.save()
                if assessment.status == Assessment.Status.DRAFT:
                    replace_draft_responses(assessment, formset.response_payloads)
                    assessment = complete_assessment(assessment)
                record_event(
                    actor=request.user,
                    event_type=(
                        AuditEvent.EventType.UPDATE if instance else AuditEvent.EventType.CREATE
                    ),
                    target_type="Assessment",
                    target_id=assessment.pk,
                    center=assessment.center,
                    metadata={
                        "template_version_id": str(assessment.template_version_id),
                        "instrument_code": assessment.template_version.instrument.code,
                    },
                )
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, _("Assessment saved."))
            return redirect("assessment_detail", pk=assessment.pk)
    return render(
        request,
        "casework/assessment_form.html",
        {
            "form": form,
            "formset": formset,
            "selected_template": selected_template,
            "title": _("Update assessment") if instance else _("New assessment"),
        },
    )


@active_center_required
def plan_list(request):
    return _case_list(
        request,
        model=IndividualPlan,
        selector=plans_for_user,
        template_name="casework/plan_list.html",
        choices=("status", IndividualPlan.Status.choices),
    )


@active_center_required
def plan_detail(request, pk):
    plan = _authorized_request_object(
        request,
        plans_for_user(request.user, request.ssk_center),
        pk,
        "IndividualPlan",
    )
    attachments = case_attachments(request.user, request.ssk_center).list(
        AttachmentParentType.INDIVIDUAL_PLAN, plan.pk
    )
    _audit_read(request, plan, "IndividualPlan")
    goals = plan.goals.select_related(
        "category",
        "responsible_specialist__staff_profile__user",
    ).prefetch_related(
        "assessment_findings__template_version__instrument",
        "measurements",
        "service_visits",
        "status_history__actor",
    )
    category_totals = list(
        goals.values("category_id", "category__name_en", "category__name_ka")
        .annotate(
            total=Count("id"),
            planned=Count("id", filter=Q(status=IndividualPlanGoal.Status.PLANNED)),
            in_progress=Count("id", filter=Q(status=IndividualPlanGoal.Status.IN_PROGRESS)),
            achieved=Count("id", filter=Q(status=IndividualPlanGoal.Status.ACHIEVED)),
            deferred=Count("id", filter=Q(status=IndividualPlanGoal.Status.DEFERRED)),
            cancelled=Count("id", filter=Q(status=IndividualPlanGoal.Status.CANCELLED)),
        )
        .order_by("category__reporting_order", "category__name_en")
    )
    overall_totals = goals.aggregate(
        total=Count("id"),
        planned=Count("id", filter=Q(status=IndividualPlanGoal.Status.PLANNED)),
        in_progress=Count("id", filter=Q(status=IndividualPlanGoal.Status.IN_PROGRESS)),
        achieved=Count("id", filter=Q(status=IndividualPlanGoal.Status.ACHIEVED)),
        deferred=Count("id", filter=Q(status=IndividualPlanGoal.Status.DEFERRED)),
        cancelled=Count("id", filter=Q(status=IndividualPlanGoal.Status.CANCELLED)),
    )
    can_change_parent = (
        plans_for_user(request.user, request.ssk_center, for_change=True)
        .filter(pk=plan.pk)
        .exists()
    )
    return render(
        request,
        "casework/plan_detail.html",
        {
            "plan": plan,
            "goals": goals,
            "category_totals": category_totals,
            "overall_totals": overall_totals,
            "reviews": plan.reviews.select_related(
                "recorded_by", "source_assessment__template_version__instrument"
            ),
            "attachments": attachments,
            "attachment_parent_type": AttachmentParentType.INDIVIDUAL_PLAN,
            "can_change_parent": can_change_parent,
            "can_add_plan_progress": can_create_case_record(
                request.user,
                request.ssk_center,
                plan.enrollment,
                timezone.localdate(),
            ),
            "can_delete": is_system_manager(request.user),
        },
    )


@active_center_required
def plan_create(request):
    return _plan_form(
        request,
        initial_enrollment=_initial_enrollment_for_create(request),
    )


@active_center_required
def plan_update(request, pk):
    plan = _authorized_request_object(
        request,
        plans_for_user(request.user, request.ssk_center, for_change=True),
        pk,
        "IndividualPlan",
        event_type=AuditEvent.EventType.UPDATE,
    )
    return _plan_form(request, plan)


@active_center_required
def plan_goal_create(request, plan_pk):
    plan = _authorized_request_object(
        request,
        plans_for_user(request.user, request.ssk_center, for_change=True),
        plan_pk,
        "IndividualPlan",
        event_type=AuditEvent.EventType.UPDATE,
    )
    form = IndividualPlanGoalForm(
        request.POST or None,
        user=request.user,
        center=request.ssk_center,
        plan=plan,
    )
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            goal = form.save(commit=False)
            goal.plan = plan
            goal.save()
            form.save_m2m()
            record_goal_status_transition(
                goal,
                from_status="",
                actor=request.user,
                transition_date=form.cleaned_data.get("status_change_date") or timezone.localdate(),
                reason=form.cleaned_data.get("status_change_reason", ""),
                evidence=goal.evidence,
            )
            record_event(
                actor=request.user,
                event_type=AuditEvent.EventType.CREATE,
                target_type="IndividualPlanGoal",
                target_id=goal.pk,
                center=plan.center,
            )
        messages.success(request, _("Goal added."))
        return redirect("plan_detail", pk=plan.pk)
    return render(
        request,
        "casework/plan_goal_form.html",
        {
            "form": form,
            "plan": plan,
            "title": _("Add goal"),
        },
    )


@active_center_required
def plan_goal_update(request, plan_pk, pk):
    plan = _authorized_request_object(
        request,
        plans_for_user(request.user, request.ssk_center, for_change=True),
        plan_pk,
        "IndividualPlan",
        event_type=AuditEvent.EventType.UPDATE,
    )
    goal = _authorized_request_object(
        request,
        plan.goals.all(),
        pk,
        "IndividualPlanGoal",
        event_type=AuditEvent.EventType.UPDATE,
    )
    old_status = goal.status
    form = IndividualPlanGoalForm(
        request.POST or None,
        instance=goal,
        user=request.user,
        center=request.ssk_center,
        plan=plan,
    )
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            goal = form.save()
            if old_status != goal.status:
                record_goal_status_transition(
                    goal,
                    from_status=old_status,
                    actor=request.user,
                    transition_date=form.cleaned_data.get("status_change_date")
                    or timezone.localdate(),
                    reason=form.cleaned_data.get("status_change_reason", ""),
                    evidence=goal.evidence,
                )
            record_event(
                actor=request.user,
                event_type=AuditEvent.EventType.UPDATE,
                target_type="IndividualPlanGoal",
                target_id=goal.pk,
                center=plan.center,
            )
        messages.success(request, _("Goal updated."))
        return redirect("plan_detail", pk=plan.pk)
    return render(
        request,
        "casework/plan_goal_form.html",
        {
            "form": form,
            "goal": goal,
            "plan": plan,
            "title": _("Update goal"),
        },
    )


@active_center_required
def plan_goal_measurement_create(request, plan_pk, goal_pk):
    plan = _authorized_request_object(
        request,
        plans_for_user(request.user, request.ssk_center),
        plan_pk,
        "IndividualPlan",
        event_type=AuditEvent.EventType.UPDATE,
    )
    goal = _authorized_request_object(
        request,
        plan.goals.all(),
        goal_pk,
        "IndividualPlanGoal",
        event_type=AuditEvent.EventType.UPDATE,
    )
    form = GoalOutcomeMeasurementForm(
        request.POST or None,
        user=request.user,
        center=request.ssk_center,
        goal=goal,
    )
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            measurement = form.save(commit=False)
            measurement.goal = goal
            measurement.recorded_by = request.user
            measurement.save()
            record_event(
                actor=request.user,
                event_type=AuditEvent.EventType.CREATE,
                target_type="GoalOutcomeMeasurement",
                target_id=measurement.pk,
                center=plan.center,
            )
        messages.success(request, _("Goal progress recorded."))
        return redirect("plan_detail", pk=plan.pk)
    return render(
        request,
        "casework/plan_record_form.html",
        {
            "form": form,
            "plan": plan,
            "goal": goal,
            "title": _("Record goal progress"),
        },
    )


@active_center_required
def plan_review_create(request, plan_pk):
    plan = _authorized_request_object(
        request,
        plans_for_user(request.user, request.ssk_center),
        plan_pk,
        "IndividualPlan",
        event_type=AuditEvent.EventType.UPDATE,
    )
    form = IndividualPlanReviewForm(
        request.POST or None,
        user=request.user,
        center=request.ssk_center,
        plan=plan,
    )
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            review = form.save(commit=False)
            review.plan = plan
            review.recorded_by = request.user
            review.save()
            record_event(
                actor=request.user,
                event_type=AuditEvent.EventType.CREATE,
                target_type="IndividualPlanReview",
                target_id=review.pk,
                center=plan.center,
            )
        messages.success(request, _("Plan review recorded."))
        return redirect("plan_detail", pk=plan.pk)
    return render(
        request,
        "casework/plan_record_form.html",
        {"form": form, "plan": plan, "title": _("Record plan review")},
    )


def _plan_form(request, instance=None, initial_enrollment=None):
    plan = instance or IndividualPlan(center=request.ssk_center)
    if initial_enrollment is not None:
        plan.enrollment = initial_enrollment
        plan.beneficiary = initial_enrollment.beneficiary
    existing_goal_statuses = dict(plan.goals.values_list("pk", "status")) if plan.pk else {}
    form = IndividualPlanForm(
        request.POST or None,
        instance=plan,
        user=request.user,
        center=request.ssk_center,
    )
    formset = IndividualPlanGoalFormSet(
        request.POST or None,
        instance=plan,
        prefix="goals",
        form_kwargs={"user": request.user, "center": request.ssk_center, "plan": plan},
    )
    form_valid = form.is_valid() if request.method == "POST" else False
    formset_valid = formset.is_valid() if request.method == "POST" else False
    if form_valid and formset_valid:
        try:
            validate_plan_goals(form, formset)
        except ValidationError as exc:
            form.add_error("status", exc)
        else:
            with transaction.atomic():
                plan = form.save(commit=False)
                plan = save_plan_period(
                    plan,
                    has_valid_goals=any(
                        row.cleaned_data for row in formset.forms if row.cleaned_data
                    ),
                )
                formset.instance = plan
                formset.save()
                for goal_form in formset.forms:
                    if not goal_form.cleaned_data or not goal_form.instance.pk:
                        continue
                    goal = goal_form.instance
                    old_status = existing_goal_statuses.get(goal.pk, "")
                    if old_status != goal.status:
                        record_goal_status_transition(
                            goal,
                            from_status=old_status,
                            actor=request.user,
                            transition_date=goal_form.cleaned_data.get("status_change_date")
                            or timezone.localdate(),
                            reason=goal_form.cleaned_data.get("status_change_reason", ""),
                            evidence=goal.evidence,
                        )
                record_event(
                    actor=request.user,
                    event_type=(
                        AuditEvent.EventType.UPDATE if instance else AuditEvent.EventType.CREATE
                    ),
                    target_type="IndividualPlan",
                    target_id=plan.pk,
                    center=plan.center,
                )
            messages.success(request, _("Individual plan saved."))
            return redirect("plan_detail", pk=plan.pk)
    return render(
        request,
        "casework/plan_form.html",
        {
            "form": form,
            "formset": formset,
            "title": _("Update individual plan") if instance else _("New individual plan"),
        },
    )


@active_center_required
def summary_list(request):
    queryset = summaries_for_user(request.user, request.ssk_center)
    month = request.GET.get("month", "").strip()
    if month:
        try:
            year, month_number = [int(part) for part in month.split("-", 1)]
            queryset = queryset.filter(summary_month__year=year, summary_month__month=month_number)
        except (TypeError, ValueError):
            messages.error(request, _("Month must use YYYY-MM format."))
    return render(
        request,
        "casework/summary_list.html",
        {"page_obj": _page(request, queryset), "selected_month": month},
    )


@active_center_required
def attachment_upload(request, parent_type, parent_id):
    result = case_attachments(request.user, request.ssk_center).upload(
        parent_type,
        parent_id,
        data=request.POST if request.method == "POST" else None,
        files=request.FILES if request.method == "POST" else None,
    )
    if result.saved:
        messages.success(request, _("Attachment uploaded securely."))
        return redirect(result.redirect_url)
    return render(
        request,
        "casework/attachment_form.html",
        {
            "form": result.form,
            "parent": result.parent,
            "cancel_url": result.redirect_url,
        },
    )


@active_center_required
def attachment_download(request, pk):
    return case_attachments(request.user, request.ssk_center).download(pk)


def _delete_case_record(
    request,
    *,
    pk,
    selector,
    parent_type: str,
    target_type: str,
    list_route: str,
    detail_route: str,
):
    if not is_system_manager(request.user):
        raise PermissionDenied
    obj = get_authorized_object(selector(request.user, request.ssk_center), pk)
    if request.method == "POST":
        target_id = obj.pk
        center = obj.center
        try:
            with transaction.atomic():
                obj.delete()
                PrivateAttachment.objects.filter(
                    parent_type=parent_type,
                    parent_id=target_id,
                    center=center,
                ).delete()
                record_event(
                    actor=request.user,
                    event_type=AuditEvent.EventType.DELETE,
                    target_type=target_type,
                    target_id=target_id,
                    center=center,
                )
        except ProtectedError:
            messages.error(
                request, _("This record is referenced by other records and cannot be deleted.")
            )
            return render(
                request,
                "casework/delete_confirm.html",
                {
                    "object": obj,
                    "cancel_url": reverse(detail_route, kwargs={"pk": target_id}),
                },
                status=409,
            )
        messages.success(request, _("Record deleted."))
        return redirect(list_route)
    return render(
        request,
        "casework/delete_confirm.html",
        {"object": obj, "cancel_url": reverse(detail_route, kwargs={"pk": obj.pk})},
    )


@active_center_required
def beneficiary_delete(request, pk):
    return _delete_case_record(
        request,
        pk=pk,
        selector=beneficiaries_for_user,
        parent_type=AttachmentParentType.BENEFICIARY,
        target_type="Beneficiary",
        list_route="beneficiary_list",
        detail_route="beneficiary_detail",
    )


@active_center_required
def visit_delete(request, pk):
    return _delete_case_record(
        request,
        pk=pk,
        selector=visits_for_user,
        parent_type=AttachmentParentType.SERVICE_VISIT,
        target_type="ServiceVisit",
        list_route="visit_list",
        detail_route="visit_detail",
    )


@active_center_required
def assessment_delete(request, pk):
    return _delete_case_record(
        request,
        pk=pk,
        selector=assessments_for_user,
        parent_type=AttachmentParentType.ASSESSMENT,
        target_type="Assessment",
        list_route="assessment_list",
        detail_route="assessment_detail",
    )


@active_center_required
def plan_delete(request, pk):
    return _delete_case_record(
        request,
        pk=pk,
        selector=plans_for_user,
        parent_type=AttachmentParentType.INDIVIDUAL_PLAN,
        target_type="IndividualPlan",
        list_route="plan_list",
        detail_route="plan_detail",
    )


@active_center_required
def attachment_delete(request, pk):
    if request.method != "POST":
        raise Http404
    parent_url = case_attachments(request.user, request.ssk_center).delete(pk)
    messages.success(request, _("Attachment deleted."))
    return redirect(parent_url)
