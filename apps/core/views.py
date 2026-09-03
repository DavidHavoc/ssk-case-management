from __future__ import annotations

import csv
from datetime import datetime
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from apps.accounts.roles import is_central_hr, is_coordinator, is_specialist, is_system_manager
from apps.audit.models import AuditEvent
from apps.audit.services import record_event
from apps.casework.models import (
    Assessment,
    EnrollmentStateEvent,
    IndividualPlan,
    IndividualPlanGoal,
    IndividualPlanReview,
    Municipality,
    Region,
    ServiceActivityDefinition,
    ServiceDefinition,
    ServiceEnrollment,
    ServiceVisit,
    VisitLocationDefinition,
)
from apps.casework.services import monthly_service_delivery_rows

from .authorization import (
    CenterSelectionRequired,
    active_center_for_request,
    active_enrollment_assignments_for_user,
    beneficiaries_for_user,
    current_assessments_for_user,
    enrollment_events_for_user,
    enrollments_for_user,
    plans_for_user,
    schedules_for_user,
    specialists_for_center,
    visits_for_user,
)
from .decorators import active_center_required
from .reminders import authorized_reminders
from .reporting import (
    assessment_progress_rows,
    beneficiary_breakdown_rows,
    beneficiary_outcome_rows,
    data_quality_exception_rows,
    enrollment_trend_rows,
    plan_goal_rows,
    plan_outcome_rows,
    report_headers,
    report_rows,
    safe_csv_value,
    specialist_caseload_rows,
    visit_exception_rows,
)


def _parse_report_date(value: str):
    try:
        return datetime.strptime(value, "%d/%m/%Y").date()
    except (TypeError, ValueError):
        return parse_date(value)


REPORT_TYPES = {
    "beneficiary_breakdown": gettext_lazy("Beneficiaries by service and geography"),
    "caseload": gettext_lazy("Specialist caseload and active assignments"),
    "service_delivery": gettext_lazy("Planned versus delivered service"),
    "visit_exceptions": gettext_lazy("No-shows, cancellations, and overdue visits"),
    "assessments": gettext_lazy("Initial, repeated, and final assessments"),
    "assessment_progress": gettext_lazy("Assessment progress and delayed domains"),
    "plan_goals": gettext_lazy("Plan goals by category and status"),
    "beneficiary_outcomes": gettext_lazy("Beneficiary outcomes"),
    "enrollment_trends": gettext_lazy("Enrollment lifecycle trends"),
    "data_quality": gettext_lazy("Data-quality exceptions"),
    "beneficiaries": gettext_lazy("Beneficiary detail"),
    "enrollments": gettext_lazy("Enrollment detail"),
    "visits": gettext_lazy("Visit detail"),
    "plans": gettext_lazy("Plan detail"),
    "plan_outcomes": gettext_lazy("Plan goals and outcomes detail"),
}


def health_view(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()
    return JsonResponse({"status": "ok"})


@login_required
def dashboard(request):
    try:
        request.ssk_center = active_center_for_request(request)
    except CenterSelectionRequired:
        query = urlencode({"next": request.get_full_path()})
        return redirect(f"{reverse('center_select')}?{query}")
    except PermissionDenied:
        if is_central_hr(request.user):
            return redirect("staff_list")
        raise
    center = request.ssk_center
    if is_specialist(request.user) and not (
        is_coordinator(request.user) or is_system_manager(request.user)
    ):
        return redirect("specialist_workspace")
    beneficiaries = beneficiaries_for_user(request.user, center)
    enrollments = enrollments_for_user(request.user, center)
    visits = visits_for_user(request.user, center)
    assessments = current_assessments_for_user(request.user, center)
    plans = plans_for_user(request.user, center)
    return render(
        request,
        "core/dashboard.html",
        {
            "beneficiary_count": beneficiaries.count(),
            "enrollment_count": enrollments.count(),
            "visits_this_month": visits.filter(
                visit_month=timezone.localdate().replace(day=1),
                status=ServiceVisit.Status.COMPLETED,
            ).count(),
            "active_plan_count": plans.filter(status=IndividualPlan.Status.ACTIVE).count(),
            "assessment_count": assessments.count(),
            "recent_visits": visits[:8],
        },
    )


def _report_queryset(request, report_type: str):
    center = request.ssk_center
    selectors = {
        "beneficiaries": beneficiaries_for_user,
        "beneficiary_breakdown": enrollments_for_user,
        "enrollments": enrollments_for_user,
        "visits": visits_for_user,
        "visit_exceptions": visits_for_user,
        "assessments": current_assessments_for_user,
        "assessment_progress": current_assessments_for_user,
        "plans": plans_for_user,
        "plan_goals": plans_for_user,
        "beneficiary_outcomes": plans_for_user,
        "plan_outcomes": plans_for_user,
    }
    queryset = selectors[report_type](request.user, center)
    query = request.GET.get("q", "").strip()
    if query:
        if report_type == "beneficiaries":
            queryset = queryset.filter(
                Q(full_name__icontains=query) | Q(beneficiary_code__icontains=query)
            )
        elif report_type in {"beneficiary_breakdown", "enrollments"}:
            queryset = queryset.filter(
                Q(beneficiary__full_name__icontains=query)
                | Q(beneficiary__beneficiary_code__icontains=query)
                | Q(episode_code__icontains=query)
            )
        else:
            queryset = queryset.filter(
                Q(beneficiary__full_name__icontains=query)
                | Q(beneficiary__beneficiary_code__icontains=query)
            )
    from_date = _parse_report_date(request.GET.get("from_date", ""))
    to_date = _parse_report_date(request.GET.get("to_date", ""))
    date_fields = {
        "beneficiaries": None,
        "beneficiary_breakdown": "start_date",
        "enrollments": "start_date",
        "visits": "visit_date",
        "visit_exceptions": "visit_date",
        "assessments": "assessment_date",
        "assessment_progress": "assessment_date",
        "plans": "plan_start_date",
        "plan_goals": "plan_start_date",
        "beneficiary_outcomes": "plan_start_date",
        "plan_outcomes": "plan_start_date",
    }
    date_field = date_fields[report_type]
    if from_date and date_field:
        queryset = queryset.filter(**{f"{date_field}__gte": from_date})
    if to_date and date_field:
        queryset = queryset.filter(**{f"{date_field}__lte": to_date})
    specialist_id = request.GET.get("specialist", "")
    if specialist_id and report_type not in {
        "beneficiaries",
        "beneficiary_breakdown",
        "enrollments",
    }:
        queryset = queryset.filter(specialist_id=specialist_id)
    if specialist_id and report_type in {"beneficiary_breakdown", "enrollments"}:
        queryset = queryset.filter(specialist_assignments__specialist_id=specialist_id)
    status = request.GET.get("status", "")
    status_field = {
        "beneficiaries": None,
        "beneficiary_breakdown": "status",
        "enrollments": "status",
        "visits": "status",
        "visit_exceptions": None,
        "assessments": "assessment_type",
        "assessment_progress": "assessment_type",
        "plans": "status",
        "plan_goals": None,
        "beneficiary_outcomes": None,
        "plan_outcomes": "status",
    }[report_type]
    if status and status_field:
        queryset = queryset.filter(**{status_field: status})
    service_id = request.GET.get("service", "")
    if service_id:
        if report_type in {"beneficiary_breakdown", "enrollments"}:
            queryset = queryset.filter(service_id=service_id)
        elif report_type != "beneficiaries":
            queryset = queryset.filter(enrollment__service_id=service_id)
    region_id = request.GET.get("region", "")
    municipality_id = request.GET.get("municipality", "")
    if region_id:
        if report_type == "beneficiaries":
            queryset = queryset.filter(region_ref_id=region_id)
        elif report_type in {"beneficiary_breakdown", "enrollments"}:
            queryset = queryset.filter(beneficiary__region_ref_id=region_id)
        else:
            queryset = queryset.filter(beneficiary__region_ref_id=region_id)
    if municipality_id:
        if report_type == "beneficiaries":
            queryset = queryset.filter(municipality_ref_id=municipality_id)
        elif report_type in {"beneficiary_breakdown", "enrollments"}:
            queryset = queryset.filter(beneficiary__municipality_ref_id=municipality_id)
        else:
            queryset = queryset.filter(beneficiary__municipality_ref_id=municipality_id)
    if report_type in {"visits", "visit_exceptions"}:
        activity_id = request.GET.get("activity", "")
        location_id = request.GET.get("location", "")
        if activity_id:
            queryset = queryset.filter(activity_id=activity_id)
        if location_id:
            queryset = queryset.filter(delivery_location_id=location_id)
    return queryset.distinct()


def _service_delivery_rows(request):
    schedules = schedules_for_user(request.user, request.ssk_center)
    visits = visits_for_user(request.user, request.ssk_center)
    query = request.GET.get("q", "").strip()
    if query:
        schedule_query = (
            Q(enrollment__beneficiary__full_name__icontains=query)
            | Q(enrollment__beneficiary__beneficiary_code__icontains=query)
            | Q(enrollment__episode_code__icontains=query)
        )
        visit_query = (
            Q(beneficiary__full_name__icontains=query)
            | Q(beneficiary__beneficiary_code__icontains=query)
            | Q(enrollment__episode_code__icontains=query)
        )
        schedules = schedules.filter(schedule_query)
        visits = visits.filter(visit_query)
    from_date = _parse_report_date(request.GET.get("from_date", ""))
    to_date = _parse_report_date(request.GET.get("to_date", ""))
    if from_date:
        schedules = schedules.filter(schedule_month__gte=from_date.replace(day=1))
        visits = visits.filter(visit_date__gte=from_date)
    if to_date:
        schedules = schedules.filter(schedule_month__lte=to_date.replace(day=1))
        visits = visits.filter(visit_date__lte=to_date)
    activity_id = request.GET.get("activity", "")
    if activity_id:
        schedules = schedules.filter(activity_id=activity_id)
        visits = visits.filter(activity_id=activity_id)
    location_id = request.GET.get("location", "")
    if location_id:
        schedules = schedules.filter(delivery_location_id=location_id)
        visits = visits.filter(delivery_location_id=location_id)
    service_id = request.GET.get("service", "")
    if service_id:
        schedules = schedules.filter(enrollment__service_id=service_id)
        visits = visits.filter(enrollment__service_id=service_id)
    specialist_id = request.GET.get("specialist", "")
    if specialist_id:
        schedules = schedules.filter(
            enrollment__specialist_assignments__specialist_id=specialist_id
        )
        visits = visits.filter(specialist_id=specialist_id)
    return monthly_service_delivery_rows(schedules, visits)


def _caseload_rows(request, *, as_of):
    assignments = active_enrollment_assignments_for_user(
        request.user,
        request.ssk_center,
        as_of=as_of,
    )
    specialist_id = request.GET.get("specialist", "")
    service_id = request.GET.get("service", "")
    status = request.GET.get("status", "")
    query = request.GET.get("q", "").strip()
    if specialist_id:
        assignments = assignments.filter(specialist_id=specialist_id)
    if service_id:
        assignments = assignments.filter(enrollment__service_id=service_id)
    if status:
        assignments = assignments.filter(enrollment__status=status)
    if query:
        assignments = assignments.filter(
            Q(specialist__staff_profile__user__first_name__icontains=query)
            | Q(specialist__staff_profile__user__last_name__icontains=query)
            | Q(specialist__staff_profile__employee_number__icontains=query)
        )
    return specialist_caseload_rows(assignments)


def _enrollment_trend_rows(request):
    events = enrollment_events_for_user(request.user, request.ssk_center)
    from_date = _parse_report_date(request.GET.get("from_date", ""))
    to_date = _parse_report_date(request.GET.get("to_date", ""))
    status = request.GET.get("status", "")
    service_id = request.GET.get("service", "")
    if from_date:
        events = events.filter(effective_date__gte=from_date)
    if to_date:
        events = events.filter(effective_date__lte=to_date)
    if status:
        events = events.filter(kind=status)
    if service_id:
        events = events.filter(enrollment__service_id=service_id)
    return enrollment_trend_rows(events)


def _data_quality_rows(request, *, as_of):
    enrollments = _report_queryset(request, "beneficiary_breakdown")
    assessments = current_assessments_for_user(request.user, request.ssk_center).filter(
        enrollment__in=enrollments
    )
    plans = plans_for_user(request.user, request.ssk_center).filter(enrollment__in=enrollments)
    rows = data_quality_exception_rows(
        enrollments,
        assessments,
        plans,
        center=request.ssk_center,
        as_of=as_of,
        include_restricted_operations=(
            is_system_manager(request.user) or is_coordinator(request.user)
        ),
    )
    selected_issue = request.GET.get("status", "")
    return [row for row in rows if not selected_issue or row.issue_code == selected_issue]


def _operational_report_rows(request, report_type: str):
    as_of = _parse_report_date(request.GET.get("to_date", "")) or timezone.localdate()
    if report_type == "beneficiary_breakdown":
        return beneficiary_breakdown_rows(
            _report_queryset(request, report_type),
            center_name=request.ssk_center.name,
            as_of=as_of,
            selected_age_band=request.GET.get("age_band", ""),
        )
    if report_type == "caseload":
        return _caseload_rows(request, as_of=as_of)
    if report_type == "service_delivery":
        return _service_delivery_rows(request)
    if report_type == "visit_exceptions":
        rows = visit_exception_rows(_report_queryset(request, report_type), as_of=as_of)
        selected_kind = request.GET.get("status", "")
        return [row for row in rows if not selected_kind or row.exception_kind == selected_kind]
    if report_type == "assessment_progress":
        return assessment_progress_rows(_report_queryset(request, report_type))
    if report_type == "plan_goals":
        return plan_goal_rows(
            _report_queryset(request, report_type),
            as_of=_parse_report_date(request.GET.get("to_date", "")),
            selected_status=request.GET.get("status", ""),
        )
    if report_type == "beneficiary_outcomes":
        return beneficiary_outcome_rows(
            _report_queryset(request, report_type),
            as_of=_parse_report_date(request.GET.get("to_date", "")),
            selected_outcome=request.GET.get("status", ""),
        )
    if report_type == "enrollment_trends":
        return _enrollment_trend_rows(request)
    if report_type == "data_quality":
        return _data_quality_rows(request, as_of=as_of)
    rows = _report_queryset(request, report_type)
    if report_type == "plan_outcomes":
        return plan_outcome_rows(
            rows,
            as_of=_parse_report_date(request.GET.get("to_date", "")),
        )
    return rows


def _report_status_choices(report_type: str):
    return {
        "beneficiaries": (),
        "beneficiary_breakdown": ServiceEnrollment.Status.choices,
        "caseload": ServiceEnrollment.Status.choices,
        "enrollments": ServiceEnrollment.Status.choices,
        "visits": ServiceVisit.Status.choices,
        "service_delivery": (),
        "visit_exceptions": (
            ("overdue", _("Overdue planned visit")),
            (ServiceVisit.Status.NO_SHOW, _("No show")),
            (ServiceVisit.Status.CANCELLED, _("Cancelled")),
        ),
        "assessments": Assessment.AssessmentType.choices,
        "assessment_progress": Assessment.AssessmentType.choices,
        "plans": IndividualPlan.Status.choices,
        "plan_goals": IndividualPlanGoal.Status.choices,
        "beneficiary_outcomes": IndividualPlanReview.ConditionOutcome.choices,
        "enrollment_trends": EnrollmentStateEvent.Kind.choices,
        "data_quality": (
            ("beneficiary_document", _("Missing beneficiary document")),
            ("enrollment_contract", _("Missing enrollment contract number")),
            ("enrollment_dates", _("Enrollment dates need review")),
            ("birth_date", _("Missing birth date")),
            ("region", _("Missing region")),
            ("municipality", _("Missing municipality")),
            ("assessment_review", _("Overdue assessment review")),
            ("plan_review", _("Overdue plan review")),
            ("plan_review_date", _("Missing plan review date")),
            ("goal_review", _("Goal requires review")),
        ),
        "plan_outcomes": IndividualPlan.Status.choices,
    }[report_type]


@active_center_required
def report_view(request):
    report_type = request.GET.get("type", "beneficiary_breakdown")
    if report_type not in REPORT_TYPES:
        report_type = "beneficiary_breakdown"
    rows = _operational_report_rows(request, report_type)
    row_count = len(rows) if isinstance(rows, list) else rows.count()
    record_event(
        actor=request.user,
        event_type=AuditEvent.EventType.SENSITIVE_READ,
        target_type="Report",
        center=request.ssk_center,
        metadata={"record_count": row_count, "report_type": report_type},
    )
    return render(
        request,
        "core/reports.html",
        {
            "report_types": REPORT_TYPES,
            "report_type": report_type,
            "rows": rows[:500],
            "row_count": row_count,
            "status_choices": _report_status_choices(report_type),
            "specialists": specialists_for_center(request.ssk_center),
            "activities": ServiceActivityDefinition.objects.filter(is_active=True),
            "locations": VisitLocationDefinition.objects.filter(is_active=True),
            "services": ServiceDefinition.objects.filter(
                center_offerings__center=request.ssk_center,
                center_offerings__is_active=True,
            ).distinct(),
            "regions": Region.objects.filter(is_active=True),
            "municipalities": Municipality.objects.filter(is_active=True).select_related("region"),
            "age_band_choices": (
                ("0-3", _("0-3")),
                ("3-5", _("3-5")),
                ("5-7", _("5-7")),
                ("outside", _("Outside 0-7")),
                ("unknown", _("Unknown")),
            ),
            "show_specialist_filter": report_type
            not in {"beneficiaries", "enrollment_trends", "data_quality"},
            "show_service_filter": report_type != "beneficiaries",
            "show_geography_filters": report_type == "beneficiary_breakdown",
            "show_age_band_filter": report_type == "beneficiary_breakdown",
            "show_activity_filters": report_type
            in {"visits", "service_delivery", "visit_exceptions"},
            "can_export": is_system_manager(request.user) or is_coordinator(request.user),
        },
    )


@active_center_required
def report_export(request):
    requested_report_type = request.GET.get("type", "beneficiary_breakdown")
    if not (is_system_manager(request.user) or is_coordinator(request.user)):
        record_event(
            actor=request.user,
            event_type=AuditEvent.EventType.EXPORT,
            target_type="Report",
            center=request.ssk_center,
            outcome=AuditEvent.Outcome.DENIED,
            metadata={
                "format": "csv",
                "report_type": (
                    requested_report_type if requested_report_type in REPORT_TYPES else "invalid"
                ),
            },
        )
        raise PermissionDenied
    report_type = requested_report_type
    if report_type not in REPORT_TYPES:
        record_event(
            actor=request.user,
            event_type=AuditEvent.EventType.EXPORT,
            target_type="Report",
            center=request.ssk_center,
            outcome=AuditEvent.Outcome.DENIED,
            metadata={"format": "csv", "report_type": "invalid"},
        )
        raise PermissionDenied
    queryset = _operational_report_rows(request, report_type)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="ssk-{report_type}.csv"'
    response.write("\ufeff")
    writer = csv.writer(response)
    headers = report_headers(report_type)
    writer.writerow([safe_csv_value(value) for value in headers])
    count = 0
    for row in report_rows(report_type, queryset):
        writer.writerow(row)
        count += 1
    record_event(
        actor=request.user,
        event_type=AuditEvent.EventType.EXPORT,
        target_type="Report",
        center=request.ssk_center,
        metadata={"format": "csv", "record_count": count, "report_type": report_type},
    )
    return response


@active_center_required
def reminder_list(request):
    reminders = authorized_reminders(
        request.user,
        request.ssk_center,
        as_of=timezone.localdate(),
    )
    category = request.GET.get("category", "")
    if category:
        reminders = [item for item in reminders if item.category == category]
    return render(
        request,
        "core/reminders.html",
        {
            "reminders": reminders,
            "reminder_count": len(reminders),
            "selected_category": category,
            "category_choices": (
                ("assessment", _("Assessments")),
                ("plan_review", _("Plan reviews")),
                ("enrollment", _("Enrollments")),
                ("contract", _("Contracts")),
                ("data_quality", _("Data quality")),
            ),
        },
    )


@active_center_required
def audit_log(request):
    if not is_system_manager(request.user):
        raise PermissionDenied
    events = AuditEvent.objects.filter(center=request.ssk_center).select_related("actor", "center")[
        :500
    ]
    return render(request, "audit/event_list.html", {"events": events})


def permission_denied_view(request, exception=None):
    return render(request, "errors/403.html", status=403)


def not_found_view(request, exception=None):
    return render(request, "errors/404.html", status=404)


def server_error_view(request):
    return render(request, "errors/500.html", status=500)
