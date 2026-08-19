from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.db.models.deletion import ProtectedError
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _

from apps.accounts.roles import is_coordinator, is_system_manager
from apps.audit.models import AuditEvent
from apps.audit.services import record_event
from apps.core.authorization import (
    assessments_for_user,
    beneficiaries_for_user,
    can_view_restricted_beneficiary_fields,
    get_authorized_object,
    plans_for_user,
    summaries_for_user,
    visits_for_user,
)
from apps.core.decorators import active_center_required

from .forms import (
    AssessmentDomainScoreFormSet,
    AssessmentForm,
    BeneficiaryAssignmentFormSet,
    BeneficiaryForm,
    IndividualPlanForm,
    IndividualPlanGoalFormSet,
    ServiceVisitForm,
    validate_plan_goals,
)
from .models import (
    Assessment,
    AttachmentParentType,
    Beneficiary,
    IndividualPlan,
    PrivateAttachment,
    ServiceVisit,
)
from .private_attachments import (
    case_attachments,
)
from .timeline import beneficiary_timeline_page


def _page(request, queryset, per_page: int = 30):
    return Paginator(queryset, per_page).get_page(request.GET.get("page"))


def _can_manage_restricted(user) -> bool:
    return is_system_manager(user) or is_coordinator(user)


def _audit_read(request, obj, target_type: str) -> None:
    record_event(
        actor=request.user,
        event_type=AuditEvent.EventType.SENSITIVE_READ,
        target_type=target_type,
        target_id=obj.pk,
        center=obj.center,
    )


@active_center_required
def beneficiary_list(request):
    queryset = beneficiaries_for_user(request.user, request.ssk_center)
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    service_type = request.GET.get("service_type", "").strip()
    if query:
        queryset = queryset.filter(
            Q(full_name__icontains=query) | Q(beneficiary_code__icontains=query)
        )
    if status:
        queryset = queryset.filter(service_status=status)
    if service_type:
        queryset = queryset.filter(service_type=service_type)
    return render(
        request,
        "casework/beneficiary_list.html",
        {
            "page_obj": _page(request, queryset),
            "query": query,
            "selected_status": status,
            "selected_service_type": service_type,
            "status_choices": Beneficiary.ServiceStatus.choices,
            "service_type_choices": Beneficiary.ServiceType.choices,
            "can_create": _can_manage_restricted(request.user),
        },
    )


@active_center_required
def beneficiary_detail(request, pk):
    beneficiary = get_authorized_object(
        beneficiaries_for_user(request.user, request.ssk_center), pk
    )
    restricted = can_view_restricted_beneficiary_fields(request.user, beneficiary)
    attachments = (
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
        page_number=request.GET.get("timeline_page"),
    )
    return render(
        request,
        "casework/beneficiary_detail.html",
        {
            "beneficiary": beneficiary,
            "show_restricted": restricted,
            "attachments": attachments,
            "attachment_parent_type": AttachmentParentType.BENEFICIARY,
            "can_delete": is_system_manager(request.user),
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
    formset = BeneficiaryAssignmentFormSet(
        request.POST or None,
        instance=beneficiary,
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
        formset_valid = formset.is_valid()
        attachment_valid = attachment_form.is_valid()
        if form_valid and formset_valid and attachment_valid:
            with attachment_workflow.atomic_uploads() as attachment_uploader:
                beneficiary = form.save()
                formset.instance = beneficiary
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
            "formset": formset,
            "attachment_form": attachment_form,
            "title": _("New beneficiary"),
        },
    )


@active_center_required
def beneficiary_update(request, pk):
    beneficiary = get_authorized_object(
        beneficiaries_for_user(request.user, request.ssk_center), pk
    )
    form = BeneficiaryForm(
        request.POST or None,
        instance=beneficiary,
        user=request.user,
        center=request.ssk_center,
    )
    formset = None
    if _can_manage_restricted(request.user):
        formset = BeneficiaryAssignmentFormSet(
            request.POST or None,
            instance=beneficiary,
            prefix="assignments",
            form_kwargs={"center": request.ssk_center},
        )
    formset_valid = formset.is_valid() if request.method == "POST" and formset else True
    if request.method == "POST" and form.is_valid() and formset_valid:
        with transaction.atomic():
            form.save()
            if formset:
                formset.save()
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
        {"form": form, "formset": formset, "title": _("Update beneficiary")},
    )


def _case_list(request, *, model, selector, template_name, choices):
    queryset = selector(request.user, request.ssk_center)
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    if query:
        queryset = queryset.filter(
            Q(beneficiary__full_name__icontains=query)
            | Q(beneficiary__beneficiary_code__icontains=query)
        )
    if status:
        queryset = queryset.filter(**{choices[0]: status})
    return render(
        request,
        template_name,
        {
            "page_obj": _page(request, queryset),
            "query": query,
            "selected_status": status,
            "status_choices": choices[1],
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
    visit = get_authorized_object(visits_for_user(request.user, request.ssk_center), pk)
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
            "can_delete": is_system_manager(request.user),
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
    )


@active_center_required
def visit_update(request, pk):
    visit = get_authorized_object(visits_for_user(request.user, request.ssk_center), pk)
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
    request, *, model, form_class, title, detail_route, target_type, instance=None
):
    form = form_class(
        request.POST or None,
        instance=instance or model(center=request.ssk_center),
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
def assessment_list(request):
    return _case_list(
        request,
        model=Assessment,
        selector=assessments_for_user,
        template_name="casework/assessment_list.html",
        choices=("assessment_type", Assessment.AssessmentType.choices),
    )


@active_center_required
def assessment_detail(request, pk):
    assessment = get_authorized_object(assessments_for_user(request.user, request.ssk_center), pk)
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
            "can_delete": is_system_manager(request.user),
        },
    )


@active_center_required
def assessment_create(request):
    return _assessment_form(request)


@active_center_required
def assessment_update(request, pk):
    assessment = get_authorized_object(assessments_for_user(request.user, request.ssk_center), pk)
    return _assessment_form(request, assessment)


def _assessment_form(request, instance=None):
    assessment = instance or Assessment(center=request.ssk_center)
    form = AssessmentForm(
        request.POST or None,
        instance=assessment,
        user=request.user,
        center=request.ssk_center,
    )
    formset = AssessmentDomainScoreFormSet(
        request.POST or None, instance=assessment, prefix="domains"
    )
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        with transaction.atomic():
            assessment = form.save()
            formset.instance = assessment
            formset.save()
            record_event(
                actor=request.user,
                event_type=(
                    AuditEvent.EventType.UPDATE if instance else AuditEvent.EventType.CREATE
                ),
                target_type="Assessment",
                target_id=assessment.pk,
                center=assessment.center,
            )
        messages.success(request, _("Assessment saved."))
        return redirect("assessment_detail", pk=assessment.pk)
    return render(
        request,
        "casework/assessment_form.html",
        {
            "form": form,
            "formset": formset,
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
    plan = get_authorized_object(plans_for_user(request.user, request.ssk_center), pk)
    attachments = case_attachments(request.user, request.ssk_center).list(
        AttachmentParentType.INDIVIDUAL_PLAN, plan.pk
    )
    _audit_read(request, plan, "IndividualPlan")
    return render(
        request,
        "casework/plan_detail.html",
        {
            "plan": plan,
            "attachments": attachments,
            "attachment_parent_type": AttachmentParentType.INDIVIDUAL_PLAN,
            "can_delete": is_system_manager(request.user),
        },
    )


@active_center_required
def plan_create(request):
    return _plan_form(request)


@active_center_required
def plan_update(request, pk):
    plan = get_authorized_object(plans_for_user(request.user, request.ssk_center), pk)
    return _plan_form(request, plan)


def _plan_form(request, instance=None):
    plan = instance or IndividualPlan(center=request.ssk_center)
    form = IndividualPlanForm(
        request.POST or None,
        instance=plan,
        user=request.user,
        center=request.ssk_center,
    )
    formset = IndividualPlanGoalFormSet(request.POST or None, instance=plan, prefix="goals")
    form_valid = form.is_valid() if request.method == "POST" else False
    formset_valid = formset.is_valid() if request.method == "POST" else False
    if form_valid and formset_valid:
        try:
            validate_plan_goals(form, formset)
        except ValidationError as exc:
            form.add_error("status", exc)
        else:
            with transaction.atomic():
                plan = form.save()
                formset.instance = plan
                formset.save()
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
