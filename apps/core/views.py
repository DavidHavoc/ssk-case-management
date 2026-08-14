from __future__ import annotations

import csv
from datetime import date

from django.core.exceptions import PermissionDenied
from django.db import connection
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils.dateparse import parse_date
from django.utils.translation import gettext as _

from apps.accounts.roles import is_coordinator, is_system_manager
from apps.audit.models import AuditEvent
from apps.audit.services import record_event
from apps.casework.models import Assessment, Beneficiary, IndividualPlan, ServiceVisit

from .authorization import (
    assessments_for_user,
    beneficiaries_for_user,
    plans_for_user,
    specialists_for_center,
    visits_for_user,
)
from .decorators import active_center_required
from .reporting import report_headers, report_rows, safe_csv_value

REPORT_TYPES = {
    "beneficiaries": _("Beneficiaries"),
    "visits": _("Service visits"),
    "assessments": _("Assessments"),
    "plans": _("Individual plans"),
}


def health_view(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()
    return JsonResponse({"status": "ok"})


@active_center_required
def dashboard(request):
    center = request.ssk_center
    beneficiaries = beneficiaries_for_user(request.user, center)
    visits = visits_for_user(request.user, center)
    assessments = assessments_for_user(request.user, center)
    plans = plans_for_user(request.user, center)
    return render(
        request,
        "core/dashboard.html",
        {
            "beneficiary_count": beneficiaries.count(),
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
        "visits": visits_for_user,
        "assessments": assessments_for_user,
        "plans": plans_for_user,
    }
    queryset = selectors[report_type](request.user, center)
    query = request.GET.get("q", "").strip()
    if query:
        if report_type == "beneficiaries":
            queryset = queryset.filter(
                Q(full_name__icontains=query) | Q(beneficiary_code__icontains=query)
            )
        else:
            queryset = queryset.filter(
                Q(beneficiary__full_name__icontains=query)
                | Q(beneficiary__beneficiary_code__icontains=query)
            )
    from_date = parse_date(request.GET.get("from_date", ""))
    to_date = parse_date(request.GET.get("to_date", ""))
    date_fields = {
        "beneficiaries": "enrollment_date",
        "visits": "visit_date",
        "assessments": "assessment_date",
        "plans": "plan_start_date",
    }
    date_field = date_fields[report_type]
    if from_date:
        queryset = queryset.filter(**{f"{date_field}__gte": from_date})
    if to_date:
        queryset = queryset.filter(**{f"{date_field}__lte": to_date})
    specialist_id = request.GET.get("specialist", "")
    if specialist_id and report_type != "beneficiaries":
        queryset = queryset.filter(specialist_id=specialist_id)
    status = request.GET.get("status", "")
    status_field = {
        "beneficiaries": "service_status",
        "visits": "status",
        "assessments": "assessment_type",
        "plans": "status",
    }[report_type]
    if status:
        queryset = queryset.filter(**{status_field: status})
    return queryset


def _report_status_choices(report_type: str):
    return {
        "beneficiaries": Beneficiary.ServiceStatus.choices,
        "visits": ServiceVisit.Status.choices,
        "assessments": Assessment.AssessmentType.choices,
        "plans": IndividualPlan.Status.choices,
    }[report_type]


@active_center_required
def report_view(request):
    report_type = request.GET.get("type", "visits")
    if report_type not in REPORT_TYPES:
        report_type = "visits"
    queryset = _report_queryset(request, report_type)
    return render(
        request,
        "core/reports.html",
        {
            "report_types": REPORT_TYPES,
            "report_type": report_type,
            "rows": queryset[:500],
            "row_count": queryset.count(),
            "status_choices": _report_status_choices(report_type),
            "specialists": specialists_for_center(request.ssk_center),
            "can_export": is_system_manager(request.user) or is_coordinator(request.user),
        },
    )


@active_center_required
def report_export(request):
    if not (is_system_manager(request.user) or is_coordinator(request.user)):
        raise PermissionDenied
    report_type = request.GET.get("type", "visits")
    if report_type not in REPORT_TYPES:
        raise PermissionDenied
    queryset = _report_queryset(request, report_type)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="ssk-{report_type}.csv"'
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow([safe_csv_value(value) for value in report_headers(report_type)])
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
