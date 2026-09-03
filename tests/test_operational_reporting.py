from datetime import date, timedelta
from unittest.mock import patch

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone, translation

from apps.casework.models import (
    EnrollmentStateEvent,
    IndividualPlanGoal,
    IndividualPlanReview,
    Municipality,
    ServiceEnrollment,
    ServiceVisit,
)

from .factories import (
    make_assessment,
    make_beneficiary,
    make_plan,
    make_specialist,
    make_visit,
    set_active_center,
)

pytestmark = pytest.mark.django_db

OPERATIONAL_REPORT_TYPES = (
    "beneficiary_breakdown",
    "caseload",
    "service_delivery",
    "visit_exceptions",
    "assessments",
    "assessment_progress",
    "plan_goals",
    "beneficiary_outcomes",
    "enrollment_trends",
    "data_quality",
)


def _prepare_operational_records(beneficiary, specialist):
    today = timezone.localdate()
    visit = make_visit(
        beneficiary,
        specialist,
        visit_date=today - timedelta(days=3),
        status=ServiceVisit.Status.NO_SHOW,
    )
    assessment = make_assessment(
        beneficiary,
        specialist,
        assessment_date=today - timedelta(days=20),
    )
    plan = make_plan(beneficiary, specialist)
    IndividualPlanReview.objects.create(
        plan=plan,
        review_date=today - timedelta(days=1),
        condition_outcome=IndividualPlanReview.ConditionOutcome.STABLE,
        rationale="Synthetic stable outcome.",
        recorded_by=specialist.staff_profile.user,
    )
    return visit, assessment, plan


def test_every_operational_report_and_export_stays_inside_authorized_center(
    client,
    coordinator_a,
    center_a,
    beneficiary_a,
    beneficiary_b,
    specialist_a,
    specialist_b,
):
    _prepare_operational_records(beneficiary_a, specialist_a)
    _prepare_operational_records(beneficiary_b, specialist_b)
    client.force_login(coordinator_a)
    set_active_center(client, center_a)

    for report_type in OPERATIONAL_REPORT_TYPES:
        response = client.get(reverse("reports"), {"type": report_type})
        exported = client.get(reverse("report_export"), {"type": report_type})

        assert response.status_code == 200
        assert response.context["report_type"] == report_type
        assert beneficiary_b.beneficiary_code not in response.content.decode()
        assert beneficiary_b.full_name not in response.content.decode()
        assert exported.status_code == 200
        assert beneficiary_b.beneficiary_code not in exported.content.decode("utf-8-sig")
        assert beneficiary_b.full_name not in exported.content.decode("utf-8-sig")


def test_specialist_reports_omit_restricted_beneficiary_values(
    client,
    specialist_a,
    center_a,
    beneficiary_a,
):
    _prepare_operational_records(beneficiary_a, specialist_a)
    restricted_values = (
        beneficiary_a.personal_id,
        beneficiary_a.address,
        beneficiary_a.guardian_parent,
        beneficiary_a.phone,
        beneficiary_a.email,
        beneficiary_a.application_contract_number,
        beneficiary_a.notes,
    )
    client.force_login(specialist_a.staff_profile.user)
    set_active_center(client, center_a)

    for report_type in OPERATIONAL_REPORT_TYPES:
        response = client.get(reverse("reports"), {"type": report_type})
        body = response.content.decode()

        assert response.status_code == 200
        assert all(value not in body for value in restricted_values if value)
    data_quality = client.get(reverse("reports"), {"type": "data_quality"}).content.decode()
    assert "No beneficiary document is attached" not in data_quality
    assert "Enrollment contract number is missing" not in data_quality


def test_beneficiary_breakdown_filters_service_status_age_and_geography(
    client,
    coordinator_a,
    center_a,
    beneficiary_a,
):
    municipality = Municipality.objects.select_related("region").first()
    beneficiary_a.birth_date = date(2023, 8, 24)
    beneficiary_a.region_ref = municipality.region
    beneficiary_a.municipality_ref = municipality
    beneficiary_a.save()
    enrollment = beneficiary_a.enrollments.get()
    client.force_login(coordinator_a)
    set_active_center(client, center_a)

    response = client.get(
        reverse("reports"),
        {
            "type": "beneficiary_breakdown",
            "to_date": "24/08/2026",
            "service": enrollment.service_id,
            "status": ServiceEnrollment.Status.ACTIVE,
            "age_band": "3-5",
            "region": municipality.region_id,
            "municipality": municipality.pk,
        },
    )

    assert response.status_code == 200
    assert len(response.context["rows"]) == 1
    row = response.context["rows"][0]
    assert row.age_band == "3-5"
    assert row.beneficiary_count == 1
    assert row.enrollment_count == 1

    excluded = client.get(
        reverse("reports"),
        {"type": "beneficiary_breakdown", "status": ServiceEnrollment.Status.SUSPENDED},
    )
    assert list(excluded.context["rows"]) == []


def test_exception_assessment_goal_outcome_and_trend_filters(
    client,
    coordinator_a,
    center_a,
    beneficiary_a,
    specialist_a,
):
    today = timezone.localdate()
    overdue = make_visit(
        beneficiary_a,
        specialist_a,
        visit_date=today - timedelta(days=7),
        status=ServiceVisit.Status.PLANNED,
    )
    make_visit(
        beneficiary_a,
        specialist_a,
        visit_date=today - timedelta(days=6),
        status=ServiceVisit.Status.NO_SHOW,
    )
    initial = make_assessment(
        beneficiary_a,
        specialist_a,
        assessment_date=today - timedelta(days=40),
    )
    repeated = make_assessment(
        beneficiary_a,
        specialist_a,
        assessment_type="repeated",
        assessment_date=today - timedelta(days=10),
        previous=initial,
        template_version=initial.template_version,
    )
    plan = make_plan(beneficiary_a, specialist_a)
    IndividualPlanReview.objects.create(
        plan=plan,
        review_date=today - timedelta(days=1),
        condition_outcome=IndividualPlanReview.ConditionOutcome.STABLE,
        rationale="Synthetic stable outcome.",
        recorded_by=coordinator_a,
    )
    client.force_login(coordinator_a)
    set_active_center(client, center_a)

    exceptions = client.get(
        reverse("reports"),
        {
            "type": "visit_exceptions",
            "status": "overdue",
            "activity": overdue.activity_id,
            "location": overdue.delivery_location_id,
        },
    )
    assert [row.visit.pk for row in exceptions.context["rows"]] == [overdue.pk]

    assessments = client.get(
        reverse("reports"),
        {"type": "assessments", "status": "repeated"},
    )
    assert [row.pk for row in assessments.context["rows"]] == [repeated.pk]

    progress = client.get(
        reverse("reports"),
        {"type": "assessment_progress", "status": "repeated"},
    )
    assert progress.context["rows"][0].previous.pk == initial.pk
    assert progress.context["rows"][0].comparison_status == "Comparable"

    goals = client.get(
        reverse("reports"),
        {"type": "plan_goals", "status": IndividualPlanGoal.Status.IN_PROGRESS},
    )
    assert goals.context["rows"][0].status == IndividualPlanGoal.Status.IN_PROGRESS

    outcomes = client.get(
        reverse("reports"),
        {
            "type": "beneficiary_outcomes",
            "status": IndividualPlanReview.ConditionOutcome.STABLE,
        },
    )
    assert outcomes.context["rows"][0].condition_outcome == "Stable"

    trends = client.get(
        reverse("reports"),
        {
            "type": "enrollment_trends",
            "status": EnrollmentStateEvent.Kind.ADMISSION,
            "from_date": "01/01/2026",
            "to_date": "31/01/2026",
        },
    )
    assert {row.event_kind for row in trends.context["rows"]} == {
        EnrollmentStateEvent.Kind.ADMISSION
    }


def test_operational_exports_neutralize_formulas_in_every_dynamic_column(
    client,
    coordinator_a,
    center_a,
    beneficiary_a,
    specialist_a,
):
    specialist_a.staff_profile.user.first_name = "=SPECIALIST()"
    specialist_a.staff_profile.user.save(update_fields=["first_name"])
    beneficiary_a.full_name = "=BENEFICIARY()"
    beneficiary_a.save()
    visit = make_visit(
        beneficiary_a,
        specialist_a,
        visit_date=timezone.localdate() - timedelta(days=1),
        status=ServiceVisit.Status.CANCELLED,
    )
    visit.cancellation_reason = "=CANCEL()"
    visit.save(update_fields=["cancellation_reason", "updated_at"])
    make_plan(beneficiary_a, specialist_a)
    client.force_login(coordinator_a)
    set_active_center(client, center_a)

    caseload = client.get(reverse("report_export"), {"type": "caseload"})
    exceptions = client.get(reverse("report_export"), {"type": "visit_exceptions"})
    outcomes = client.get(reverse("report_export"), {"type": "beneficiary_outcomes"})

    assert "'=SPECIALIST()" in caseload.content.decode("utf-8-sig")
    assert "'=CANCEL()" in exceptions.content.decode("utf-8-sig")
    assert "'=BENEFICIARY()" in outcomes.content.decode("utf-8-sig")


def test_report_query_count_does_not_grow_per_goal_row(
    client,
    coordinator_a,
    center_a,
    beneficiary_a,
    specialist_a,
):
    make_plan(beneficiary_a, specialist_a)
    client.force_login(coordinator_a)
    set_active_center(client, center_a)

    with CaptureQueriesContext(connection) as baseline_queries:
        baseline = client.get(reverse("reports"), {"type": "plan_goals"})
    assert baseline.status_code == 200

    for number in range(5):
        specialist = make_specialist(center_a, f"query-specialist-{number}")
        beneficiary = make_beneficiary(
            center_a,
            specialist,
            name=f"Synthetic Query Beneficiary {number}",
        )
        make_plan(beneficiary, specialist)

    with CaptureQueriesContext(connection) as expanded_queries:
        expanded = client.get(reverse("reports"), {"type": "plan_goals"})
    assert expanded.status_code == 200
    assert len(expanded_queries) <= len(baseline_queries) + 2


def test_reminders_cover_due_work_contracts_and_data_quality_without_email(
    client,
    coordinator_a,
    center_a,
    beneficiary_a,
    beneficiary_b,
    specialist_a,
    specialist_b,
):
    today = timezone.localdate()
    assessment = make_assessment(
        beneficiary_a,
        specialist_a,
        assessment_date=today - timedelta(days=60),
    )
    assessment.next_review_date = today - timedelta(days=2)
    assessment.save(update_fields=["next_review_date", "updated_at"])
    hidden_assessment = make_assessment(
        beneficiary_b,
        specialist_b,
        assessment_date=today - timedelta(days=60),
    )
    hidden_assessment.next_review_date = today - timedelta(days=3)
    hidden_assessment.save(update_fields=["next_review_date", "updated_at"])
    plan = make_plan(beneficiary_a, specialist_a)
    plan.review_due_date = today + timedelta(days=5)
    plan.save(update_fields=["review_due_date", "updated_at"])
    enrollment = beneficiary_a.enrollments.get()
    enrollment.end_date = today + timedelta(days=10)
    enrollment.save(update_fields=["end_date", "updated_at"])
    specialist_a.staff_profile.contract_valid_until = today + timedelta(days=15)
    specialist_a.staff_profile.save(update_fields=["contract_valid_until", "updated_at"])
    client.force_login(coordinator_a)
    set_active_center(client, center_a)

    with patch("django.core.mail.send_mail") as send_mail:
        response = client.get(reverse("reminders"))

    body = response.content.decode()
    assert response.status_code == 200
    assert "Assessment review overdue" in body
    assert "Plan review upcoming" in body
    assert "Enrollment expires soon" in body
    assert "Staff contract expires soon" in body
    assert "No beneficiary document is attached" in body
    assert beneficiary_a.beneficiary_code in body
    assert beneficiary_b.beneficiary_code not in body
    send_mail.assert_not_called()

    data_quality = client.get(reverse("reminders"), {"category": "data_quality"})
    assert all(item.category == "data_quality" for item in data_quality.context["reminders"])


def test_reminder_query_count_does_not_grow_per_beneficiary(
    client,
    coordinator_a,
    center_a,
    beneficiary_a,
    specialist_a,
):
    client.force_login(coordinator_a)
    set_active_center(client, center_a)

    with CaptureQueriesContext(connection) as baseline_queries:
        baseline = client.get(reverse("reminders"))
    assert baseline.status_code == 200

    for number in range(5):
        specialist = make_specialist(center_a, f"reminder-specialist-{number}")
        make_beneficiary(
            center_a,
            specialist,
            name=f"Synthetic Reminder Beneficiary {number}",
        )

    with CaptureQueriesContext(connection) as expanded_queries:
        expanded = client.get(reverse("reminders"))
    assert expanded.status_code == 200
    assert len(expanded_queries) <= len(baseline_queries) + 2


def test_operational_reports_and_reminders_render_georgian_labels(
    client,
    coordinator_a,
    center_a,
    beneficiary_a,
):
    client.force_login(coordinator_a)
    set_active_center(client, center_a)

    with translation.override("ka"):
        report = client.get(reverse("reports"), {"type": "data_quality"})
        reminders = client.get(reverse("reminders"))

    assert "მონაცემთა ხარისხის გამონაკლისები" in report.content.decode()
    assert "შეხსენებები" in reminders.content.decode()
    assert "შეხსენებები მხოლოდ აპლიკაციაში ჩანს" in reminders.content.decode()
