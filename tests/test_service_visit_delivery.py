from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.audit.models import AuditEvent
from apps.casework.models import (
    EnrollmentServiceSchedule,
    EnrollmentSpecialistAssignment,
    ServiceEnrollment,
    ServiceVisit,
    ServiceVisitCorrection,
    SpecialistMonthlyServiceSummary,
)
from apps.casework.services import monthly_service_delivery_rows
from apps.core.authorization import schedules_for_user, visits_for_user

from .factories import (
    add_specialist_center,
    ensure_visit_catalogs,
    make_beneficiary,
    make_specialist,
    make_visit,
    set_active_center,
)

pytestmark = pytest.mark.django_db


def test_monthly_schedule_and_visit_totals_are_kept_separate(
    coordinator_a, center_a, beneficiary_a, specialist_a
):
    enrollment = beneficiary_a.enrollments.get()
    activity, location = ensure_visit_catalogs()
    EnrollmentServiceSchedule.objects.create(
        enrollment=enrollment,
        schedule_month=date(2026, 4, 1),
        activity=activity,
        delivery_location=location,
        participation_format="individual",
        planned_visits=4,
        planned_units=Decimal("6"),
    )
    make_visit(beneficiary_a, specialist_a, visit_date=date(2026, 4, 10))
    make_visit(beneficiary_a, specialist_a, visit_date=date(2026, 4, 17))
    make_visit(
        beneficiary_a,
        specialist_a,
        visit_date=date(2026, 4, 24),
        status=ServiceVisit.Status.CANCELLED,
    )

    rows = monthly_service_delivery_rows(
        schedules_for_user(coordinator_a, center_a),
        visits_for_user(coordinator_a, center_a),
    )

    assert len(rows) == 1
    row = rows[0]
    assert row.planned_visits == 4
    assert row.planned_units == Decimal("6")
    assert row.delivered_visits == 2
    assert row.delivered_units == Decimal("4")
    assert row.visit_variance == -2
    assert row.cancelled_count == 1


def test_undelivered_visits_never_contribute_service_units(beneficiary_a, specialist_a):
    planned = make_visit(
        beneficiary_a,
        specialist_a,
        visit_date=date(2026, 5, 5),
        status=ServiceVisit.Status.PLANNED,
    )
    cancelled = make_visit(
        beneficiary_a,
        specialist_a,
        visit_date=date(2026, 5, 6),
        status=ServiceVisit.Status.CANCELLED,
    )
    summary = SpecialistMonthlyServiceSummary.objects.get(
        specialist=specialist_a,
        center=beneficiary_a.center,
        summary_month=date(2026, 5, 1),
    )

    assert planned.service_units == 0
    assert cancelled.service_units == 0
    assert cancelled.cancellation_reason
    assert summary.planned_count == 1
    assert summary.cancelled_count == 1
    assert summary.total_service_units == 0


def test_visit_correction_requires_reason_and_keeps_before_after_audit(
    client, coordinator_a, center_a, beneficiary_a, specialist_a
):
    visit = make_visit(beneficiary_a, specialist_a, visit_date=date(2026, 4, 12))
    client.force_login(coordinator_a)
    set_active_center(client, center_a)
    payload = {
        "enrollment": str(visit.enrollment_id),
        "specialist": str(specialist_a.pk),
        "visit_date": "2026-04-12",
        "activity": str(visit.activity_id),
        "delivery_location": str(visit.delivery_location_id),
        "participation_format": "individual",
        "status": ServiceVisit.Status.COMPLETED,
        "service_units": "3",
        "duration_minutes": "75",
        "participants": "1",
        "cancellation_reason": "",
        "notes": "Corrected synthetic visit.",
    }

    missing_reason = client.post(reverse("visit_update", kwargs={"pk": visit.pk}), payload)
    assert missing_reason.status_code == 200
    assert ServiceVisitCorrection.objects.filter(visit=visit).count() == 0

    payload["correction_reason"] = "Corrected duration from source record."
    response = client.post(reverse("visit_update", kwargs={"pk": visit.pk}), payload)

    assert response.status_code == 302
    correction = ServiceVisitCorrection.objects.get(visit=visit)
    assert correction.before_values["duration_minutes"] == 60
    assert correction.after_values["duration_minutes"] == 75
    assert correction.reason == payload["correction_reason"]
    assert AuditEvent.objects.filter(
        actor=coordinator_a,
        event_type=AuditEvent.EventType.UPDATE,
        target_type="ServiceVisit",
        target_id=visit.pk,
    ).exists()


def test_visit_rejects_cross_center_unassigned_and_closed_enrollment_combinations(
    center_a, center_b, beneficiary_a, specialist_a, specialist_b
):
    enrollment = beneficiary_a.enrollments.get()
    activity, location = ensure_visit_catalogs()
    cross_center = ServiceVisit(
        enrollment=enrollment,
        beneficiary=beneficiary_a,
        center=center_b,
        specialist=specialist_a,
        visit_date=date(2026, 4, 1),
        activity=activity,
        delivery_location=location,
        status=ServiceVisit.Status.COMPLETED,
        service_units=1,
        duration_minutes=30,
    )
    with pytest.raises(ValidationError, match="center must match"):
        cross_center.save()

    unassigned = ServiceVisit(
        enrollment=enrollment,
        beneficiary=beneficiary_a,
        center=center_a,
        specialist=specialist_b,
        visit_date=date(2026, 4, 1),
        activity=activity,
        delivery_location=location,
        status=ServiceVisit.Status.COMPLETED,
        service_units=1,
        duration_minutes=30,
    )
    with pytest.raises(ValidationError, match="not assigned"):
        unassigned.save()

    enrollment.status = ServiceEnrollment.Status.EXITED
    enrollment.end_date = date(2026, 6, 1)
    enrollment.save()
    closed = ServiceVisit(
        enrollment=enrollment,
        beneficiary=beneficiary_a,
        center=center_a,
        specialist=specialist_a,
        visit_date=date(2026, 6, 1),
        activity=activity,
        delivery_location=location,
        status=ServiceVisit.Status.COMPLETED,
        service_units=1,
        duration_minutes=30,
    )
    with pytest.raises(ValidationError, match="not open"):
        closed.save()


def test_multi_center_specialist_can_deliver_only_with_enrollment_assignment(center_a, center_b):
    specialist = make_specialist(center_a, "multi-service")
    add_specialist_center(specialist, center_b)
    beneficiary = make_beneficiary(center_b, specialist, name="Synthetic Multi Center Case")
    visit = make_visit(beneficiary, specialist, visit_date=date(2026, 3, 10))
    assert visit.center == center_b

    assignment = EnrollmentSpecialistAssignment.objects.get(
        enrollment=visit.enrollment,
        specialist=specialist,
    )
    assignment.valid_to = date(2026, 3, 15)
    assignment.save()
    with pytest.raises(ValidationError, match="not assigned"):
        make_visit(beneficiary, specialist, visit_date=date(2026, 3, 15))


def test_monthly_delivery_report_shows_activity_location_and_variance(
    client, coordinator_a, center_a, beneficiary_a, specialist_a
):
    enrollment = beneficiary_a.enrollments.get()
    activity, location = ensure_visit_catalogs()
    EnrollmentServiceSchedule.objects.create(
        enrollment=enrollment,
        schedule_month=date(2026, 4, 1),
        activity=activity,
        delivery_location=location,
        participation_format="individual",
        planned_visits=2,
        planned_units=2,
    )
    make_visit(beneficiary_a, specialist_a, visit_date=date(2026, 4, 9))
    client.force_login(coordinator_a)
    set_active_center(client, center_a)

    response = client.get(
        reverse("reports"),
        {
            "type": "service_delivery",
            "from_date": "2026-04-01",
            "to_date": "2026-04-30",
        },
    )

    body = response.content.decode()
    assert response.status_code == 200
    assert beneficiary_a.full_name in body
    assert activity.name_en in body
    assert location.name_en in body
    assert "Planned visits" in body
    assert "Delivered visits" in body
