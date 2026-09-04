from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.casework.models import (
    Beneficiary,
    CenterServiceOffering,
    EnrollmentSpecialistAssignment,
    ServiceDefinition,
    ServiceEnrollment,
)
from apps.casework.services import create_enrollment, transition_enrollment

from .factories import make_center, set_active_center

pytestmark = pytest.mark.django_db


def _service(code="CONFIGURABLE-SERVICE", *, family=ServiceDefinition.Family.FUTURE, active=True):
    return ServiceDefinition.objects.create(
        code=code,
        name_en=code.replace("-", " ").title(),
        name_ka=f"Synthetic {code}",
        family=family,
        is_active=active,
        source_version="SYNTHETIC-TEST",
    )


def _beneficiary(center):
    return Beneficiary.objects.create(
        beneficiary_code=f"BEN-{center.code}",
        service_type=Beneficiary.ServiceType.OTHER,
        center=center,
        full_name="Synthetic Offering Test Beneficiary",
    )


def test_system_manager_can_create_and_update_center_service_offering(client, manager):
    center = make_center("Synthetic Configuration Center")
    service = _service()
    client.force_login(manager)
    set_active_center(client, center)

    response = client.post(
        reverse("service_offering_create"),
        {
            "service": str(service.pk),
            "valid_from": "04/09/2026",
            "valid_to": "",
            "is_active": "on",
        },
    )

    assert response.status_code == 302
    offering = CenterServiceOffering.objects.get(center=center, service=service)
    assert offering.is_active
    assert AuditEvent.objects.filter(
        actor=manager,
        center=center,
        event_type=AuditEvent.EventType.CREATE,
        target_type="CenterServiceOffering",
        target_id=offering.pk,
    ).exists()

    response = client.post(
        reverse("service_offering_update", kwargs={"pk": offering.pk}),
        {
            "service": str(service.pk),
            "valid_from": "04/09/2026",
            "valid_to": "30/09/2026",
            "is_active": "",
        },
    )

    assert response.status_code == 302
    offering.refresh_from_db()
    assert offering.valid_to.isoformat() == "2026-09-30"
    assert not offering.is_active
    assert AuditEvent.objects.filter(
        actor=manager,
        center=center,
        event_type=AuditEvent.EventType.UPDATE,
        target_type="CenterServiceOffering",
        target_id=offering.pk,
    ).exists()


def test_center_detail_lists_offerings_and_new_center_empty_state(client, manager):
    center = make_center("Synthetic Empty Configuration Center")
    client.force_login(manager)
    set_active_center(client, center)

    response = client.get(reverse("center_detail"))

    assert response.status_code == 200
    body = response.content.decode()
    assert "No service offerings configured" in body
    assert reverse("service_offering_create") in body

    service = _service()
    offering = CenterServiceOffering.objects.create(center=center, service=service)
    response = client.get(reverse("center_detail"))
    body = response.content.decode()
    assert service.name_en in body
    assert reverse("service_offering_update", kwargs={"pk": offering.pk}) in body


def test_only_active_nonlegacy_unconfigured_services_can_be_added(client, manager):
    center = make_center("Synthetic Catalog Filter Center")
    available = _service("AVAILABLE-SERVICE")
    legacy = _service("LEGACY-CONFIG", family=ServiceDefinition.Family.LEGACY)
    inactive = _service("INACTIVE-CONFIG", active=False)
    configured = _service("ALREADY-CONFIGURED")
    CenterServiceOffering.objects.create(center=center, service=configured, is_active=False)
    client.force_login(manager)
    set_active_center(client, center)

    response = client.get(reverse("service_offering_create"))

    choices = response.context["form"].fields["service"].queryset
    assert available in choices
    assert legacy not in choices
    assert inactive not in choices
    assert configured not in choices


def test_duplicate_and_invalid_service_offerings_are_rejected(client, manager):
    center = make_center("Synthetic Validation Center")
    service = _service()
    CenterServiceOffering.objects.create(center=center, service=service)
    other_service = _service("DATE-VALIDATION-SERVICE")
    client.force_login(manager)
    set_active_center(client, center)

    duplicate = client.post(
        reverse("service_offering_create"),
        {
            "service": str(service.pk),
            "valid_from": "05/09/2026",
            "valid_to": "",
            "is_active": "on",
        },
    )
    assert duplicate.status_code == 200
    assert CenterServiceOffering.objects.filter(center=center, service=service).count() == 1

    invalid_dates = client.post(
        reverse("service_offering_create"),
        {
            "service": str(other_service.pk),
            "valid_from": "20/09/2026",
            "valid_to": "20/09/2026",
            "is_active": "on",
        },
    )
    assert invalid_dates.status_code == 200
    assert "Valid to must be later than valid from" in invalid_dates.content.decode()
    assert not CenterServiceOffering.objects.filter(center=center, service=other_service).exists()


def test_other_roles_and_anonymous_users_cannot_manage_offerings(
    client,
    center_a,
    coordinator_a,
    specialist_a,
    central_hr,
):
    offering = center_a.service_offerings.exclude(
        service__family=ServiceDefinition.Family.LEGACY
    ).first()
    create_url = reverse("service_offering_create")
    update_url = reverse("service_offering_update", kwargs={"pk": offering.pk})

    for user in (coordinator_a, specialist_a.staff_profile.user, central_hr):
        client.force_login(user)
        set_active_center(client, center_a)
        assert client.get(create_url).status_code == 403
        assert client.post(update_url, {"is_active": ""}).status_code == 403

    client.logout()
    assert client.get(create_url).status_code == 302
    assert client.post(update_url, {"is_active": ""}).status_code == 302
    offering.refresh_from_db()
    assert offering.is_active


def test_new_offering_appears_in_enrollment_intake(client, manager):
    center = make_center("Synthetic Enrollment Configuration Center")
    service = _service()
    client.force_login(manager)
    set_active_center(client, center)
    client.post(
        reverse("service_offering_create"),
        {"service": str(service.pk), "valid_from": "", "valid_to": "", "is_active": "on"},
    )

    response = client.get(reverse("beneficiary_create"))

    choices = response.context["enrollment_form"].fields["offering"].queryset
    assert choices.get().service == service


def test_enrollment_forms_show_optional_extra_assignment_limited_to_active_center(
    client,
    manager,
    center_a,
    beneficiary_a,
    specialist_a,
    specialist_b,
):
    client.force_login(manager)
    set_active_center(client, center_a)

    create_response = client.get(
        reverse("enrollment_create", kwargs={"beneficiary_pk": beneficiary_a.pk})
    )
    create_formset = create_response.context["formset"]
    assert create_formset.total_form_count() == 1
    specialist_choices = create_formset.forms[0].fields["specialist"].queryset
    assert specialist_a in specialist_choices
    assert specialist_b not in specialist_choices
    assert create_formset.forms[0].empty_permitted

    existing = beneficiary_a.enrollments.get(service__code="LEGACY-OTHER")
    update_response = client.get(reverse("enrollment_update", kwargs={"pk": existing.pk}))
    assert update_response.context["formset"].total_form_count() == 2


def test_submitting_first_assignment_row_creates_enrollment_assignment(
    client,
    manager,
    center_a,
    beneficiary_a,
    specialist_a,
):
    offering = center_a.service_offerings.get(service__code="HOME-CARE")
    today = timezone.localdate()
    client.force_login(manager)
    set_active_center(client, center_a)

    response = client.post(
        reverse("enrollment_create", kwargs={"beneficiary_pk": beneficiary_a.pk}),
        {
            "offering": str(offering.pk),
            "episode_code": "SYNTHETIC-ASSIGNMENT-E01",
            "status": ServiceEnrollment.Status.ACTIVE,
            "start_date": today.strftime("%d/%m/%Y"),
            "first_service_date": "",
            "application_contract_number": "",
            "notes": "",
            "assignments-TOTAL_FORMS": "1",
            "assignments-INITIAL_FORMS": "0",
            "assignments-MIN_NUM_FORMS": "0",
            "assignments-MAX_NUM_FORMS": "1000",
            "assignments-0-specialist": str(specialist_a.pk),
            "assignments-0-assignment_role": EnrollmentSpecialistAssignment.Role.PRIMARY,
            "assignments-0-valid_from": today.strftime("%d/%m/%Y"),
            "assignments-0-valid_to": "",
        },
    )

    assert response.status_code == 302
    enrollment = ServiceEnrollment.objects.get(episode_code="SYNTHETIC-ASSIGNMENT-E01")
    assert enrollment.specialist_assignments.filter(specialist=specialist_a).exists()


def test_casework_creation_guidance_requires_effective_active_enrollment(client, manager):
    center = make_center("Synthetic Empty Workflow Center")
    service = _service()
    offering = CenterServiceOffering.objects.create(center=center, service=service)
    beneficiary = _beneficiary(center)
    today = timezone.localdate()
    enrollment = create_enrollment(
        beneficiary=beneficiary,
        offering=offering,
        episode_code="SYNTHETIC-PENDING-E01",
        start_date=today - timedelta(days=1),
        status=ServiceEnrollment.Status.PENDING,
        actor=manager,
    )
    client.force_login(manager)
    set_active_center(client, center)

    routes = (
        ("visit_list", "visit_create"),
        ("schedule_list", "schedule_create"),
        ("assessment_list", "assessment_create"),
        ("plan_list", "plan_create"),
    )
    for list_route, create_route in routes:
        response = client.get(reverse(list_route))
        body = response.content.decode()
        assert response.status_code == 200
        assert "active beneficiary enrollment is required" in body
        assert reverse(create_route) not in body
        assert reverse("beneficiary_list") in body

    transition_enrollment(
        enrollment,
        new_state=ServiceEnrollment.Status.ACTIVE,
        effective_date=today,
        reason="Synthetic admission",
        actor=manager,
    )

    for list_route, create_route in routes:
        response = client.get(reverse(list_route))
        assert reverse(create_route) in response.content.decode()


def test_offering_update_is_scoped_to_active_center(client, manager):
    center = make_center("Synthetic Scoped Offering Center")
    other_center = make_center("Synthetic Other Offering Center")
    offering = CenterServiceOffering.objects.create(center=other_center, service=_service())
    client.force_login(manager)
    set_active_center(client, center)

    response = client.get(reverse("service_offering_update", kwargs={"pk": offering.pk}))

    assert response.status_code == 404
