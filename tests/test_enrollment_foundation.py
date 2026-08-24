from datetime import date

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import translation

from apps.casework.age import calculate_completed_age, ssk_age_band
from apps.casework.models import (
    BeneficiaryDiagnosis,
    BeneficiarySocialStatus,
    CenterServiceOffering,
    DiagnosisDefinition,
    EnrollmentCenterPlacement,
    EnrollmentSpecialistAssignment,
    EnrollmentStateEvent,
    Municipality,
    Region,
    ServiceEnrollment,
    SocialStatusDefinition,
)
from apps.casework.services import (
    admit_enrollment,
    complete_enrollment,
    create_enrollment,
    reenroll_beneficiary,
    resume_enrollment,
    suspend_enrollment,
    transfer_enrollment,
)
from apps.core.authorization import (
    beneficiaries_for_user,
    diagnoses_for_user,
    social_statuses_for_user,
    visits_for_user,
)

from .factories import add_specialist_center, make_coordinator, make_visit, set_active_center

pytestmark = pytest.mark.django_db


def _offering(center, code):
    return CenterServiceOffering.objects.get(center=center, service__code=code)


def _create_assigned_enrollment(
    beneficiary,
    specialist,
    offering,
    episode_code,
    actor,
    *,
    status=ServiceEnrollment.Status.ACTIVE,
    start_date=date(2026, 2, 1),
):
    enrollment = create_enrollment(
        beneficiary=beneficiary,
        offering=offering,
        episode_code=episode_code,
        start_date=start_date,
        status=status,
        actor=actor,
    )
    EnrollmentSpecialistAssignment.objects.create(
        enrollment=enrollment,
        specialist=specialist,
        assignment_role=EnrollmentSpecialistAssignment.Role.PRIMARY,
        valid_from=start_date,
    )
    return enrollment


def test_beneficiary_supports_multiple_simultaneous_service_enrollments(
    beneficiary_a, specialist_a, center_a, coordinator_a
):
    early = _create_assigned_enrollment(
        beneficiary_a,
        specialist_a,
        _offering(center_a, "EARLY-INTERVENTION"),
        "SYN-EARLY-001",
        coordinator_a,
    )
    food = _create_assigned_enrollment(
        beneficiary_a,
        specialist_a,
        _offering(center_a, "FOOD-DELIVERY"),
        "SYN-FOOD-001",
        coordinator_a,
    )

    assert early.service != food.service
    assert beneficiary_a.enrollments.filter(status=ServiceEnrollment.Status.ACTIVE).count() == 3

    with pytest.raises(ValidationError, match="overlapping enrollment"):
        create_enrollment(
            beneficiary=beneficiary_a,
            offering=_offering(center_a, "FOOD-DELIVERY"),
            episode_code="SYN-FOOD-DUPLICATE",
            start_date=date(2026, 3, 1),
            status=ServiceEnrollment.Status.ACTIVE,
            actor=coordinator_a,
        )


def test_enrollment_history_transfer_completion_and_reenrollment(
    beneficiary_a,
    specialist_a,
    center_a,
    center_b,
    coordinator_a,
):
    offering = _offering(center_a, "HOME-CARE")
    enrollment = _create_assigned_enrollment(
        beneficiary_a,
        specialist_a,
        offering,
        "SYN-HISTORY-001",
        coordinator_a,
        status=ServiceEnrollment.Status.PENDING,
        start_date=date(2026, 2, 1),
    )
    admit_enrollment(
        enrollment,
        effective_date=date(2026, 2, 2),
        reason="Synthetic admission",
        actor=coordinator_a,
    )
    suspend_enrollment(
        enrollment,
        effective_date=date(2026, 3, 1),
        reason="Synthetic suspension",
        actor=coordinator_a,
    )
    resume_enrollment(
        enrollment,
        effective_date=date(2026, 3, 15),
        reason="Synthetic resumption",
        actor=coordinator_a,
    )
    add_specialist_center(specialist_a, center_b)
    transfer_enrollment(
        enrollment,
        destination_offering=_offering(center_b, "HOME-CARE"),
        effective_date=date(2026, 4, 1),
        reason="Synthetic transfer",
        actor=coordinator_a,
    )
    complete_enrollment(
        enrollment,
        effective_date=date(2026, 5, 1),
        reason="Synthetic completion",
        actor=coordinator_a,
    )
    enrollment.refresh_from_db()

    assert enrollment.status == ServiceEnrollment.Status.COMPLETED
    assert enrollment.end_date == date(2026, 5, 1)
    assert list(enrollment.state_events.values_list("kind", flat=True)) == [
        EnrollmentStateEvent.Kind.CREATED,
        EnrollmentStateEvent.Kind.ADMISSION,
        EnrollmentStateEvent.Kind.SUSPENSION,
        EnrollmentStateEvent.Kind.RESUMPTION,
        EnrollmentStateEvent.Kind.TRANSFER,
        EnrollmentStateEvent.Kind.COMPLETION,
    ]
    placements = list(enrollment.center_placements.order_by("valid_from"))
    assert [(row.center, row.valid_from, row.valid_to) for row in placements] == [
        (center_a, date(2026, 2, 1), date(2026, 4, 1)),
        (center_b, date(2026, 4, 1), date(2026, 5, 1)),
    ]

    new_enrollment = reenroll_beneficiary(
        enrollment,
        offering=_offering(center_b, "HOME-CARE"),
        episode_code="SYN-HISTORY-002",
        start_date=date(2026, 6, 1),
        actor=coordinator_a,
    )
    assert new_enrollment.prior_enrollment == enrollment
    assert new_enrollment.state_events.get().kind == EnrollmentStateEvent.Kind.RE_ENROLLMENT


def test_invalid_center_and_service_offering_relationships_are_rejected(
    beneficiary_a, center_a, center_b
):
    enrollment = beneficiary_a.enrollments.get(service__code="LEGACY-OTHER")
    wrong_center_offering = _offering(center_b, "HOME-CARE")
    placement = EnrollmentCenterPlacement(
        enrollment=enrollment,
        center=center_a,
        offering=wrong_center_offering,
        valid_from=date(2027, 1, 1),
    )
    with pytest.raises(ValidationError, match="does not belong"):
        placement.full_clean()

    wrong_service_offering = _offering(center_a, "FOOD-DELIVERY")
    placement.offering = wrong_service_offering
    with pytest.raises(ValidationError, match="does not provide"):
        placement.full_clean()


@pytest.mark.parametrize(
    ("birth_date", "reference_date", "years", "months", "band"),
    [
        (date(2023, 8, 20), date(2026, 8, 19), 2, 11, "0-3"),
        (date(2023, 8, 20), date(2026, 8, 20), 3, 0, "3-5"),
        (date(2021, 8, 20), date(2026, 8, 19), 4, 11, "3-5"),
        (date(2021, 8, 20), date(2026, 8, 20), 5, 0, "5-7"),
        (date(2019, 8, 20), date(2026, 8, 19), 6, 11, "5-7"),
        (date(2019, 8, 20), date(2026, 8, 20), 7, 0, None),
        (date(2020, 2, 29), date(2021, 2, 27), 0, 11, "0-3"),
        (date(2020, 2, 29), date(2021, 2, 28), 1, 0, "0-3"),
        (date(2020, 2, 29), date(2024, 2, 29), 4, 0, "3-5"),
    ],
)
def test_age_boundaries_and_leap_dates(birth_date, reference_date, years, months, band):
    age = calculate_completed_age(birth_date, reference_date)
    assert (age.years, age.months) == (years, months)
    assert ssk_age_band(age.total_months) == band


def test_region_and_municipality_relationship_validation(beneficiary_a):
    tbilisi = Region.objects.get(code="GEO-TB")
    kakheti = Region.objects.get(code="GEO-KA")
    telavi = Municipality.objects.get(code="GEO-MUN-TELAVI")

    beneficiary_a.region_ref = kakheti
    beneficiary_a.municipality_ref = telavi
    beneficiary_a.full_clean()

    beneficiary_a.region_ref = tbilisi
    with pytest.raises(ValidationError, match="does not belong"):
        beneficiary_a.full_clean()


def test_catalogs_render_the_configured_georgian_labels(center_a):
    service = _offering(center_a, "EARLY-INTERVENTION").service
    kakheti = Region.objects.get(code="GEO-KA")
    telavi = Municipality.objects.get(code="GEO-MUN-TELAVI")

    with translation.override("ka"):
        assert str(service) == "ადრეული ინტერვენცია"
        assert str(kakheti) == "კახეთი"
        assert str(telavi) == "თელავი, კახეთი"

    with translation.override("en"):
        assert str(service) == "Early Intervention"
        assert str(kakheti) == "Kakheti"
        assert str(telavi) == "Telavi, Kakheti"


def test_diagnosis_and_social_status_visibility_is_enrollment_scoped(
    beneficiary_a, specialist_a, center_a, center_b, coordinator_a
):
    enrollment = beneficiary_a.enrollments.get(service__code="LEGACY-OTHER")
    diagnosis = DiagnosisDefinition.objects.create(
        code="SYN-DX-1",
        name_en="Synthetic diagnosis",
        name_ka="სინთეზური დიაგნოზი",
        coding_system="SYNTHETIC",
    )
    status = SocialStatusDefinition.objects.create(
        code="SYN-STATUS-1",
        name_en="Synthetic social status",
        name_ka="სინთეზური სოციალური სტატუსი",
    )
    visible_diagnosis = BeneficiaryDiagnosis.objects.create(
        beneficiary=beneficiary_a,
        enrollment=enrollment,
        definition=diagnosis,
        visible_to_specialists=True,
        recorded_by=coordinator_a,
    )
    hidden_diagnosis = BeneficiaryDiagnosis.objects.create(
        beneficiary=beneficiary_a,
        enrollment=enrollment,
        definition=diagnosis,
        visible_to_specialists=False,
        notes="Restricted synthetic evidence",
        recorded_by=coordinator_a,
    )
    visible_status = BeneficiarySocialStatus.objects.create(
        beneficiary=beneficiary_a,
        enrollment=enrollment,
        definition=status,
        visible_to_specialists=True,
        recorded_by=coordinator_a,
    )
    hidden_status = BeneficiarySocialStatus.objects.create(
        beneficiary=beneficiary_a,
        enrollment=enrollment,
        definition=status,
        visible_to_specialists=False,
        notes="Restricted synthetic status evidence",
        recorded_by=coordinator_a,
    )
    coordinator_b = make_coordinator(center_b, "classification-coordinator-b")
    other_center_enrollment = create_enrollment(
        beneficiary=beneficiary_a,
        offering=_offering(center_b, "HOME-CARE"),
        episode_code="SYN-CLASSIFICATION-B",
        start_date=date(2026, 2, 1),
        status=ServiceEnrollment.Status.ACTIVE,
        actor=coordinator_b,
    )
    other_center_diagnosis = BeneficiaryDiagnosis.objects.create(
        beneficiary=beneficiary_a,
        enrollment=other_center_enrollment,
        definition=diagnosis,
        visible_to_specialists=True,
        recorded_by=coordinator_b,
    )
    other_center_status = BeneficiarySocialStatus.objects.create(
        beneficiary=beneficiary_a,
        enrollment=other_center_enrollment,
        definition=status,
        visible_to_specialists=True,
        recorded_by=coordinator_b,
    )
    user = specialist_a.staff_profile.user

    assert set(diagnoses_for_user(user, center_a, enrollment=enrollment)) == {visible_diagnosis}
    assert hidden_diagnosis in diagnoses_for_user(coordinator_a, center_a, enrollment=enrollment)
    assert set(social_statuses_for_user(user, center_a, enrollment=enrollment)) == {visible_status}
    assert hidden_status in social_statuses_for_user(coordinator_a, center_a, enrollment=enrollment)
    assert other_center_diagnosis not in diagnoses_for_user(coordinator_a, center_a)
    assert other_center_status not in social_statuses_for_user(coordinator_a, center_a)
    assert other_center_diagnosis in diagnoses_for_user(coordinator_b, center_b)
    assert other_center_status in social_statuses_for_user(coordinator_b, center_b)


def test_transfer_revokes_old_center_card_and_preserves_event_time_access(
    client,
    beneficiary_a,
    specialist_a,
    center_a,
    center_b,
    coordinator_a,
):
    coordinator_b = make_coordinator(center_b, "coordinator-b")
    enrollment = beneficiary_a.enrollments.get(service__code="LEGACY-OTHER")
    visit = make_visit(
        beneficiary_a,
        specialist_a,
        visit_date=date(2026, 3, 1),
        enrollment=enrollment,
    )
    destination = CenterServiceOffering.objects.create(
        center=center_b,
        service=enrollment.service,
    )
    transfer_enrollment(
        enrollment,
        destination_offering=destination,
        effective_date=date(2026, 4, 1),
        reason="Synthetic authorization transfer",
        actor=coordinator_a,
    )

    assert beneficiary_a not in beneficiaries_for_user(coordinator_a, center_a)
    assert beneficiary_a in beneficiaries_for_user(coordinator_b, center_b)
    assert visit in visits_for_user(coordinator_a, center_a)
    assert visit not in visits_for_user(coordinator_b, center_b)

    client.force_login(coordinator_b)
    set_active_center(client, center_b)
    response = client.post(
        reverse("beneficiary_update", kwargs={"pk": beneficiary_a.pk}),
        {
            "beneficiary_code": beneficiary_a.beneficiary_code,
            "full_name": beneficiary_a.full_name,
            "personal_id": beneficiary_a.personal_id,
            "sex": beneficiary_a.sex,
            "birth_date": beneficiary_a.birth_date.isoformat(),
            "address": beneficiary_a.address,
            "guardian_parent": beneficiary_a.guardian_parent,
            "phone": beneficiary_a.phone,
            "email": beneficiary_a.email,
            "family_status": beneficiary_a.family_status,
            "notes": "Synthetic person update after transfer.",
        },
    )
    assert response.status_code == 302
    beneficiary_a.refresh_from_db()
    assert beneficiary_a.center == center_a
