from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from threading import Barrier

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.utils import translation

from apps.casework.models import (
    Assessment,
    BeneficiarySpecialistAssignment,
    IndividualPlan,
    ServiceActivityDefinition,
    ServiceVisit,
    SpecialistMonthlyServiceSummary,
    VisitLocationDefinition,
)

from .factories import (
    add_specialist_center,
    ensure_visit_catalogs,
    make_assessment,
    make_beneficiary,
    make_plan,
    make_specialist,
    make_visit,
)

pytestmark = pytest.mark.django_db


def test_age_is_calculated_from_date_of_birth(beneficiary_a):
    beneficiary_a.birth_date = date(2000, 8, 20)
    assert beneficiary_a.age >= 25
    assert beneficiary_a.age_category == "Adult"


def test_beneficiary_rejects_future_birth_and_invalid_dates(beneficiary_a):
    beneficiary_a.birth_date = date(2099, 1, 1)
    with pytest.raises(ValidationError, match="future"):
        beneficiary_a.save()


def test_legacy_text_normalization_and_phone_validation(center_a, beneficiary_a):
    center_a.phone = "not a phone"
    with pytest.raises(ValidationError, match="valid phone"):
        center_a.save()

    beneficiary_a.refresh_from_db()
    beneficiary_a.region = "  Synthetic Region  "
    beneficiary_a.municipality = "  Synthetic Municipality  "
    beneficiary_a.guardian_parent = "  Synthetic Guardian  "
    beneficiary_a.notes = "  Synthetic note  "
    beneficiary_a.save()
    assert beneficiary_a.region == "Synthetic Region"
    assert beneficiary_a.municipality == "Synthetic Municipality"
    assert beneficiary_a.guardian_parent == "Synthetic Guardian"
    assert beneficiary_a.notes == "Synthetic note"

    beneficiary_a.refresh_from_db()
    beneficiary_a.enrollment_date = date(2026, 5, 1)
    beneficiary_a.exit_date = date(2026, 4, 1)
    with pytest.raises(ValidationError, match="enrollment"):
        beneficiary_a.save()


def test_validation_message_is_available_in_georgian(beneficiary_a):
    beneficiary_a.birth_date = date(2099, 1, 1)
    with translation.override("ka"):
        with pytest.raises(ValidationError) as exc_info:
            beneficiary_a.save()
        message = str(exc_info.value)
    assert "დაბადების თარიღი არ შეიძლება მომავალში იყოს" in message


def test_specialist_must_be_assigned_to_beneficiary_center(center_a, center_b, specialist_b):
    beneficiary = make_beneficiary(center_b, specialist_b)
    specialist_a = make_specialist(center_a, "wrong-center")
    with pytest.raises(ValidationError, match="not assigned to this center"):
        BeneficiarySpecialistAssignment.objects.create(
            beneficiary=beneficiary,
            specialist=specialist_a,
            assignment_role=BeneficiarySpecialistAssignment.Role.SECONDARY,
        )


def test_multi_center_specialist_can_be_assigned_without_changing_primary_center(
    center_a, center_b
):
    specialist = make_specialist(center_a, "multi")
    add_specialist_center(specialist, center_b)
    beneficiary = make_beneficiary(center_b, specialist)
    specialist.staff_profile.refresh_from_db()
    assert beneficiary.specialists.get() == specialist
    assert specialist.staff_profile.primary_center == center_a


def test_service_visit_normalizes_month_cancelled_units_and_rebuilds_summary(
    beneficiary_a, specialist_a
):
    visit = make_visit(beneficiary_a, specialist_a, visit_date=date(2026, 4, 22))
    assert visit.visit_month == date(2026, 4, 1)
    summary = SpecialistMonthlyServiceSummary.objects.get(
        specialist=specialist_a, center=beneficiary_a.center, summary_month=date(2026, 4, 1)
    )
    assert summary.completed_visits == 1
    assert summary.total_service_units == Decimal("2")
    assert summary.total_duration_minutes == 60

    visit.status = ServiceVisit.Status.CANCELLED
    visit.cancellation_reason = "Synthetic schedule change."
    visit.save()
    visit.refresh_from_db()
    summary.refresh_from_db()
    assert visit.service_units == 0
    assert summary.completed_visits == 0
    assert summary.cancelled_count == 1


def test_database_constraints_reject_invalid_derived_visit_values(beneficiary_a, specialist_a):
    visit = make_visit(beneficiary_a, specialist_a, visit_date=date(2026, 4, 22))

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ServiceVisit.objects.filter(pk=visit.pk).update(visit_month=date(2026, 4, 2))

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ServiceVisit.objects.filter(pk=visit.pk).update(
                status=ServiceVisit.Status.CANCELLED,
                service_units=Decimal("1"),
            )


def test_visit_rejects_unassigned_specialist(beneficiary_a, specialist_b):
    activity, location = ensure_visit_catalogs()
    visit = ServiceVisit(
        beneficiary=beneficiary_a,
        center=beneficiary_a.center,
        specialist=specialist_b,
        visit_date=date(2026, 1, 1),
        activity=activity,
        delivery_location=location,
        status=ServiceVisit.Status.COMPLETED,
        service_units=1,
    )
    with pytest.raises(ValidationError, match="not assigned to this beneficiary"):
        visit.save()


def test_assessment_chain_rules(beneficiary_a, specialist_a):
    repeated = Assessment(
        beneficiary=beneficiary_a,
        center=beneficiary_a.center,
        specialist=specialist_a,
        assessment_date=date(2026, 2, 1),
        assessment_type=Assessment.AssessmentType.REPEATED,
        scoring_tool=Assessment.ScoringTool.OTHER,
    )
    with pytest.raises(ValidationError, match="previous assessment is required"):
        repeated.save()

    initial = make_assessment(beneficiary_a, specialist_a)
    repeated.previous_assessment = initial
    repeated.save()
    assert repeated.assessment_cycle_number == 2


def test_assessment_previous_must_match_beneficiary(
    beneficiary_a, beneficiary_b, specialist_a, specialist_b
):
    previous = make_assessment(beneficiary_b, specialist_b)
    repeated = Assessment(
        beneficiary=beneficiary_a,
        center=beneficiary_a.center,
        specialist=specialist_a,
        assessment_date=date(2026, 2, 1),
        assessment_type=Assessment.AssessmentType.REPEATED,
        scoring_tool=Assessment.ScoringTool.OTHER,
        previous_assessment=previous,
    )
    with pytest.raises(ValidationError, match="same beneficiary"):
        repeated.save()


def test_individual_plan_date_validation(beneficiary_a, specialist_a):
    plan = IndividualPlan(
        beneficiary=beneficiary_a,
        center=beneficiary_a.center,
        specialist=specialist_a,
        status=IndividualPlan.Status.DRAFT,
        plan_start_date=date(2026, 5, 1),
        plan_end_date=date(2026, 4, 1),
    )
    with pytest.raises(ValidationError, match="cannot be before"):
        plan.save()


def test_factory_creates_plan_with_goal(beneficiary_a, specialist_a):
    plan = make_plan(beneficiary_a, specialist_a)
    assert plan.goals.count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_visit_creation_keeps_monthly_summary_complete(
    center_a, specialist_a, beneficiary_a
):
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL advisory-lock verification")

    barrier = Barrier(2)
    beneficiary_id = beneficiary_a.pk
    specialist_id = specialist_a.pk
    activity, location = ensure_visit_catalogs()
    activity_id = activity.pk
    location_id = location.pk

    def create_visit(day: int) -> None:
        close_old_connections()
        try:
            with transaction.atomic():
                beneficiary = BeneficiarySpecialistAssignment.objects.get(
                    beneficiary_id=beneficiary_id,
                    specialist_id=specialist_id,
                ).beneficiary
                specialist = beneficiary.specialists.get(pk=specialist_id)
                activity = ServiceActivityDefinition.objects.get(pk=activity_id)
                location = VisitLocationDefinition.objects.get(pk=location_id)
                barrier.wait(timeout=10)
                ServiceVisit.objects.create(
                    beneficiary=beneficiary,
                    center=beneficiary.center,
                    specialist=specialist,
                    visit_date=date(2026, 7, day),
                    activity=activity,
                    delivery_location=location,
                    status=ServiceVisit.Status.COMPLETED,
                    service_units=1,
                    duration_minutes=30,
                )
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(create_visit, day) for day in (10, 11)]
        for future in futures:
            future.result(timeout=20)

    summary = SpecialistMonthlyServiceSummary.objects.get(
        specialist_id=specialist_id,
        center=center_a,
        summary_month=date(2026, 7, 1),
    )
    assert summary.completed_visits == 2
    assert summary.total_service_units == Decimal("2")
    assert summary.total_duration_minutes == 60
