from __future__ import annotations

from collections.abc import Iterable

from django.db.models import QuerySet


def safe_csv_value(value) -> str:
    if value is None:
        return ""
    text = str(value)
    if text.startswith(("=", "+", "-", "@", "\t", "\r", "\n")):
        return f"'{text}"
    return text


def report_headers(report_type: str) -> list[str]:
    return {
        "beneficiaries": ["Code", "Name", "Service type", "Status", "Enrollment date"],
        "visits": [
            "Beneficiary code",
            "Beneficiary",
            "Specialist",
            "Visit date",
            "Visit type",
            "Status",
            "Units",
            "Duration minutes",
        ],
        "assessments": [
            "Beneficiary code",
            "Beneficiary",
            "Specialist",
            "Date",
            "Type",
            "Scoring tool",
            "Total score",
        ],
        "plans": [
            "Beneficiary code",
            "Beneficiary",
            "Specialist",
            "Status",
            "Start date",
            "End date",
            "Review frequency",
        ],
    }[report_type]


def report_rows(report_type: str, queryset: QuerySet) -> Iterable[list[str]]:
    for row in queryset.iterator(chunk_size=500):
        if report_type == "beneficiaries":
            values = [
                row.beneficiary_code,
                row.full_name,
                row.get_service_type_display(),
                row.get_service_status_display(),
                row.enrollment_date,
            ]
        elif report_type == "visits":
            values = [
                row.beneficiary.beneficiary_code,
                row.beneficiary.full_name,
                str(row.specialist),
                row.visit_date,
                row.get_visit_type_display(),
                row.get_status_display(),
                row.service_units,
                row.duration_minutes,
            ]
        elif report_type == "assessments":
            values = [
                row.beneficiary.beneficiary_code,
                row.beneficiary.full_name,
                str(row.specialist),
                row.assessment_date,
                row.get_assessment_type_display(),
                row.get_scoring_tool_display(),
                row.total_score,
            ]
        else:
            values = [
                row.beneficiary.beneficiary_code,
                row.beneficiary.full_name,
                str(row.specialist),
                row.get_status_display(),
                row.plan_start_date,
                row.plan_end_date,
                row.get_review_frequency_display(),
            ]
        yield [safe_csv_value(value) for value in values]
