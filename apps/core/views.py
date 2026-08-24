from __future__ import annotations

import csv
from datetime import date, datetime
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.dateparse import parse_date
from django.utils.translation import gettext as _

from apps.accounts.roles import is_central_hr, is_coordinator, is_system_manager
from apps.audit.models import AuditEvent
from apps.audit.services import record_event
from apps.casework.models import (
    Assessment,
    IndividualPlan,
    ServiceActivityDefinition,
    ServiceEnrollment,
    ServiceVisit,
    VisitLocationDefinition,
)
from apps.casework.services import monthly_service_delivery_rows

from .authorization import (
    CenterSelectionRequired,
    active_center_for_request,
    beneficiaries_for_user,
    current_assessments_for_user,
    enrollments_for_user,
    plans_for_user,
    schedules_for_user,
    specialists_for_center,
    visits_for_user,
)
from .decorators import active_center_required
from .reporting import plan_outcome_rows, report_headers, report_rows, safe_csv_value


def _parse_report_date(value: str):
    try:
        return datetime.strptime(value, "%d/%m/%Y").date()
    except (TypeError, ValueError):
        return parse_date(value)


REPORT_TYPES = {
    "beneficiaries": _("Beneficiaries"),
    "enrollments": _("Service enrollments"),
    "visits": _("Service visits"),
    "service_delivery": _("Planned versus delivered service"),
    "assessments": _("Assessments"),
    "plans": _("Individual plans"),
    "plan_outcomes": _("Plan goals and outcomes"),
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
                visit_month=date.today().replace(day=1), status=ServiceVisit.Status.COMPLETED
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
        "enrollments": enrollments_for_user,
        "visits": visits_for_user,
        "assessments": current_assessments_for_user,
        "plans": plans_for_user,
        "plan_outcomes": plans_for_user,
    }
    queryset = selectors[report_type](request.user, center)
    query = request.GET.get("q", "").strip()
    if query:
        if report_type == "beneficiaries":
            queryset = queryset.filter(
                Q(full_name__icontains=query) | Q(beneficiary_code__icontains=query)
            )
        elif report_type == "enrollments":
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
        "enrollments": "start_date",
        "visits": "visit_date",
        "assessments": "assessment_date",
        "plans": "plan_start_date",
        "plan_outcomes": "plan_start_date",
    }
    date_field = date_fields[report_type]
    if from_date and date_field:
        queryset = queryset.filter(**{f"{date_field}__gte": from_date})
    if to_date and date_field:
        queryset = queryset.filter(**{f"{date_field}__lte": to_date})
    specialist_id = request.GET.get("specialist", "")
    if specialist_id and report_type not in {"beneficiaries", "enrollments"}:
        queryset = queryset.filter(specialist_id=specialist_id)
    if specialist_id and report_type == "enrollments":
        queryset = queryset.filter(specialist_assignments__specialist_id=specialist_id)
    status = request.GET.get("status", "")
    status_field = {
        "beneficiaries": None,
        "enrollments": "status",
        "visits": "status",
        "assessments": "assessment_type",
        "plans": "status",
        "plan_outcomes": "status",
    }[report_type]
    if status and status_field:
        queryset = queryset.filter(**{status_field: status})
    if report_type == "visits":
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
    return monthly_service_delivery_rows(schedules, visits)


def _report_status_choices(report_type: str):
    return {
        "beneficiaries": (),
        "enrollments": ServiceEnrollment.Status.choices,
        "visits": ServiceVisit.Status.choices,
        "service_delivery": (),
        "assessments": Assessment.AssessmentType.choices,
        "plans": IndividualPlan.Status.choices,
        "plan_outcomes": IndividualPlan.Status.choices,
    }[report_type]


@active_center_required
def report_view(request):
    report_type = request.GET.get("type", "visits")
    if report_type not in REPORT_TYPES:
        report_type = "visits"
    if report_type == "service_delivery":
        rows = _service_delivery_rows(request)
    else:
        rows = _report_queryset(request, report_type)
        if report_type == "plan_outcomes":
            rows = plan_outcome_rows(
                rows,
                as_of=_parse_report_date(request.GET.get("to_date", "")),
            )
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
            "can_export": is_system_manager(request.user) or is_coordinator(request.user),
        },
    )


@active_center_required
def report_export(request):
    requested_report_type = request.GET.get("type", "visits")
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
    if report_type == "service_delivery":
        queryset = _service_delivery_rows(request)
    else:
        queryset = _report_queryset(request, report_type)
        if report_type == "plan_outcomes":
            queryset = plan_outcome_rows(
                queryset,
                as_of=_parse_report_date(request.GET.get("to_date", "")),
            )
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="ssk-{report_type}.csv"'
    response.write("\ufeff")
    writer = csv.writer(response)
    if report_type == "service_delivery":
        headers = [
            _("Month"),
            _("Beneficiary code"),
            _("Beneficiary"),
            _("Enrollment code"),
            _("Service"),
            _("Activity"),
            _("Delivery location"),
            _("Format"),
            _("Planned visits"),
            _("Delivered visits"),
            _("Visit variance"),
            _("Planned units"),
            _("Delivered units"),
            _("Unit variance"),
            _("Delivered duration minutes"),
            _("No show"),
            _("Cancelled"),
        ]
    else:
        headers = report_headers(report_type)
    writer.writerow([safe_csv_value(value) for value in headers])
    count = 0
    for row in (
        queryset if report_type == "service_delivery" else report_rows(report_type, queryset)
    ):
        if report_type == "service_delivery":
            values = [
                row.schedule_month.strftime("%Y-%m"),
                row.beneficiary.beneficiary_code,
                row.beneficiary.full_name,
                row.enrollment.episode_code,
                row.enrollment.service,
                row.activity,
                row.delivery_location,
                row.participation_format,
                row.planned_visits,
                row.delivered_visits,
                row.visit_variance,
                row.planned_units,
                row.delivered_units,
                row.unit_variance,
                row.delivered_duration_minutes,
                row.no_show_count,
                row.cancelled_count,
            ]
            writer.writerow([safe_csv_value(value) for value in values])
        else:
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
