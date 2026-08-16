from datetime import date

import pytest
from django.contrib.auth.models import Permission
from django.urls import reverse

from apps.audit.models import AuditEvent
from apps.centers.models import StaffProfile
from apps.core.authorization import (
    accessible_centers,
    assessments_for_user,
    beneficiaries_for_user,
    can_view_staff_directory,
    plans_for_user,
    staff_profiles_for_user,
    summaries_for_user,
    visits_for_user,
)

from .factories import make_assessment, make_center, make_plan, make_visit, set_active_center

pytestmark = pytest.mark.django_db


def test_system_manager_can_query_all_centers(manager, beneficiary_a, beneficiary_b):
    assert set(beneficiaries_for_user(manager)) == {beneficiary_a, beneficiary_b}


def test_manager_can_view_all_employee_profiles_and_details(
    client, manager, coordinator_a, specialist_a, specialist_b, center_a, center_b
):
    client.force_login(manager)

    response = client.get(reverse("staff_list"))
    body = response.content.decode()
    assert response.status_code == 200
    assert coordinator_a.staff_profile.display_name in body
    assert specialist_a.staff_profile.display_name in body
    assert specialist_b.staff_profile.display_name in body
    assert center_a.name in body
    assert center_b.name in body
    assert set(staff_profiles_for_user(manager)) == {
        coordinator_a.staff_profile,
        specialist_a.staff_profile,
        specialist_b.staff_profile,
    }

    response = client.get(reverse("staff_detail", kwargs={"pk": specialist_b.staff_profile.pk}))
    body = response.content.decode()
    assert response.status_code == 200
    assert specialist_b.staff_profile.user.email in body
    assert specialist_b.staff_profile.employee_number in body
    assert specialist_b.description in body
    assert center_b.name in body
    assert AuditEvent.objects.filter(
        event_type=AuditEvent.EventType.SENSITIVE_READ,
        target_type="StaffProfile",
        target_id=specialist_b.staff_profile.pk,
        actor=manager,
    ).exists()


def test_staff_directory_requires_manager_role_or_explicit_permission(
    client, coordinator_a, specialist_a, specialist_b
):
    client.force_login(coordinator_a)
    assert not can_view_staff_directory(coordinator_a)
    assert client.get(reverse("staff_list")).status_code == 403
    assert (
        client.get(
            reverse("staff_detail", kwargs={"pk": specialist_a.staff_profile.pk})
        ).status_code
        == 403
    )

    permission = Permission.objects.get(
        codename="view_staffprofile", content_type__app_label="centers"
    )
    coordinator_a.user_permissions.add(permission)
    coordinator_a = coordinator_a.__class__.objects.get(pk=coordinator_a.pk)
    assert can_view_staff_directory(coordinator_a)

    response = client.get(reverse("staff_list"))
    body = response.content.decode()
    assert response.status_code == 200
    assert specialist_a.staff_profile.display_name in body
    assert specialist_b.staff_profile.display_name in body

    response = client.get(reverse("staff_detail", kwargs={"pk": specialist_b.staff_profile.pk}))
    assert response.status_code == 200
    assert specialist_b.staff_profile.user.email in response.content.decode()


def test_staff_directory_center_filter_and_invalid_center_are_safe(
    client, manager, specialist_a, specialist_b, center_a
):
    client.force_login(manager)
    response = client.get(reverse("staff_list"), {"center": str(center_a.pk)})
    body = response.content.decode()
    assert response.status_code == 200
    assert specialist_a.staff_profile.display_name in body
    assert specialist_b.staff_profile.display_name not in body

    response = client.get(reverse("staff_list"), {"center": "not-a-uuid"})
    assert response.status_code == 200
    assert specialist_a.staff_profile.display_name not in response.content.decode()


def test_coordinator_cannot_list_or_open_other_center(
    client, coordinator_a, center_a, beneficiary_a, beneficiary_b
):
    client.force_login(coordinator_a)
    set_active_center(client, center_a)

    response = client.get(reverse("beneficiary_list"))
    assert response.status_code == 200
    assert beneficiary_a.full_name in response.content.decode()
    assert beneficiary_b.full_name not in response.content.decode()

    response = client.get(reverse("beneficiary_detail", kwargs={"pk": beneficiary_b.pk}))
    assert response.status_code == 404


def test_specialist_can_open_only_assigned_beneficiary(
    client, specialist_a, center_a, beneficiary_a, beneficiary_b
):
    user = specialist_a.staff_profile.user
    client.force_login(user)
    set_active_center(client, center_a)

    assigned = client.get(reverse("beneficiary_detail", kwargs={"pk": beneficiary_a.pk}))
    assert assigned.status_code == 200
    assert beneficiary_a.full_name in assigned.content.decode()

    denied = client.get(reverse("beneficiary_detail", kwargs={"pk": beneficiary_b.pk}))
    assert denied.status_code == 404


def test_inactive_staff_profile_revokes_center_and_case_access(
    client, coordinator_a, specialist_a, center_a, beneficiary_a
):
    coordinator_a.staff_profile.status = StaffProfile.Status.INACTIVE
    coordinator_a.staff_profile.save(update_fields=["status", "updated_at"])
    specialist_user = specialist_a.staff_profile.user
    specialist_a.staff_profile.status = StaffProfile.Status.INACTIVE
    specialist_a.staff_profile.save(update_fields=["status", "updated_at"])

    assert not accessible_centers(coordinator_a).exists()
    assert not accessible_centers(specialist_user).exists()
    assert not beneficiaries_for_user(specialist_user, center_a).exists()

    for user in (coordinator_a, specialist_user):
        client.force_login(user)
        set_active_center(client, center_a)
        assert client.get(reverse("dashboard")).status_code == 403
        assert (
            client.get(reverse("beneficiary_detail", kwargs={"pk": beneficiary_a.pk})).status_code
            == 403
        )


def test_specialist_detail_and_update_never_expose_or_change_restricted_fields(
    client, specialist_a, center_a, beneficiary_a
):
    user = specialist_a.staff_profile.user
    client.force_login(user)
    set_active_center(client, center_a)
    original_personal_id = beneficiary_a.personal_id

    response = client.get(reverse("beneficiary_detail", kwargs={"pk": beneficiary_a.pk}))
    body = response.content.decode()
    assert original_personal_id not in body
    assert beneficiary_a.address not in body
    assert beneficiary_a.email not in body

    response = client.post(
        reverse("beneficiary_update", kwargs={"pk": beneficiary_a.pk}),
        {
            "beneficiary_code": beneficiary_a.beneficiary_code,
            "service_type": beneficiary_a.service_type,
            "service_status": beneficiary_a.service_status,
            "full_name": beneficiary_a.full_name,
            "birth_date": beneficiary_a.birth_date.isoformat(),
            "enrollment_date": beneficiary_a.enrollment_date.isoformat(),
            "notes": "Updated authorized note.",
            "personal_id": "UNAUTHORIZED-CHANGE",
            "address": "Unauthorized address",
        },
    )
    assert response.status_code == 302
    beneficiary_a.refresh_from_db()
    assert beneficiary_a.personal_id == original_personal_id
    assert beneficiary_a.notes == "Updated authorized note."


def test_case_records_enforce_center_and_specialist_rules(
    client,
    specialist_a,
    specialist_b,
    center_a,
    beneficiary_a,
    beneficiary_b,
):
    visit_a = make_visit(beneficiary_a, specialist_a)
    assessment_a = make_assessment(beneficiary_a, specialist_a)
    plan_a = make_plan(beneficiary_a, specialist_a)
    visit_b = make_visit(beneficiary_b, specialist_b, visit_date=date(2026, 2, 1))
    assessment_b = make_assessment(beneficiary_b, specialist_b, assessment_date=date(2026, 2, 1))
    plan_b = make_plan(beneficiary_b, specialist_b)

    user = specialist_a.staff_profile.user
    assert list(visits_for_user(user, center_a)) == [visit_a]
    assert list(assessments_for_user(user, center_a)) == [assessment_a]
    assert list(plans_for_user(user, center_a)) == [plan_a]

    client.force_login(user)
    set_active_center(client, center_a)
    for route, record in (
        ("visit_detail", visit_b),
        ("assessment_detail", assessment_b),
        ("plan_detail", plan_b),
    ):
        assert client.get(reverse(route, kwargs={"pk": record.pk})).status_code == 404


def test_cross_center_form_submission_is_rejected(
    client, coordinator_a, center_a, specialist_b, beneficiary_b
):
    client.force_login(coordinator_a)
    set_active_center(client, center_a)
    response = client.post(
        reverse("visit_create"),
        {
            "beneficiary": str(beneficiary_b.pk),
            "specialist": str(specialist_b.pk),
            "visit_date": "2026-03-10",
            "visit_type": "center_visit",
            "status": "completed",
            "service_units": "1",
            "duration_minutes": "45",
        },
    )
    assert response.status_code == 200
    assert "Select a valid choice" in response.content.decode()


def test_specialist_sees_only_own_monthly_summary(
    client,
    specialist_a,
    specialist_b,
    center_a,
    beneficiary_a,
    beneficiary_b,
):
    make_visit(beneficiary_a, specialist_a)
    make_visit(beneficiary_b, specialist_b, visit_date=date(2026, 1, 16))
    user = specialist_a.staff_profile.user
    summaries = summaries_for_user(user, center_a)
    assert summaries.count() == 1
    assert summaries.get().specialist == specialist_a

    client.force_login(user)
    set_active_center(client, center_a)
    response = client.get(reverse("summary_list"))
    assert response.status_code == 200
    assert str(specialist_a) in response.content.decode()
    assert str(specialist_b) not in response.content.decode()


def test_center_delete_is_system_manager_only(client, manager, coordinator_a, center_a):
    client.force_login(coordinator_a)
    set_active_center(client, center_a)
    assert client.post(reverse("center_delete")).status_code == 403
    assert center_a.__class__.objects.filter(pk=center_a.pk).exists()

    empty_center = make_center("Synthetic Empty Center")
    client.force_login(manager)
    set_active_center(client, empty_center)
    response = client.post(reverse("center_delete"))
    assert response.status_code == 302
    assert not center_a.__class__.objects.filter(pk=empty_center.pk).exists()
