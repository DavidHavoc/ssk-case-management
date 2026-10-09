from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone, translation

from apps.audit.models import AuditEvent
from apps.casework.models import (
    Assessment,
    Beneficiary,
    BeneficiaryCodeSequence,
    BeneficiaryStaffingPeriod,
    EnrollmentSpecialistAssignment,
    IndividualPlan,
    ServiceEnrollment,
    ServiceVisit,
)
from apps.casework.services import (
    create_enrollment,
    replace_beneficiary_staffing,
    transfer_enrollment,
)
from apps.casework.staffing import responsibility_rows, responsible_specialists
from apps.casework.workspace import build_enrollment_workspace_rows
from apps.core.authorization import active_enrollment_assignments_for_user, enrollments_for_user

from .factories import (
    add_specialist_center,
    capture_legacy_assignment,
    make_beneficiary,
    make_specialist,
    make_visit,
    set_active_center,
)

pytestmark = pytest.mark.django_db
HISTORY_ERROR = "Recorded casework already uses this date. Choose a later replacement date."


@pytest.mark.parametrize("language", ["en", "ka"])
@pytest.mark.parametrize("failure", ["displacement", "closure"])
def test_staffing_endpoint_preserves_history_and_inputs_on_date_errors(
    client, beneficiary_a, specialist_a, coordinator_a, center_a, language, failure
):
    today = timezone.localdate()
    if failure == "closure":
        replace_beneficiary_staffing(
            beneficiary=beneficiary_a,
            lead=specialist_a,
            effective_date=today,
            center=center_a,
            actor=coordinator_a,
        )
        today += timedelta(days=1)
    replacement = make_specialist(center_a, "route-replacement")
    helper = make_specialist(center_a, "route-helper")
    client.force_login(coordinator_a)
    set_active_center(client, center_a)
    with patch("django.utils.timezone.localdate", return_value=today):
        visit = make_visit(beneficiary_a, specialist_a, visit_date=today)
        original_history = list(beneficiary_a.staffing_periods.values())
        original_assignments = list(EnrollmentSpecialistAssignment.objects.values())
        original_visit = ServiceVisit.objects.values().get(pk=visit.pk)
        success_events = AuditEvent.objects.filter(target_type="BeneficiaryStaffingPeriod").count()
        with translation.override(language):
            url = reverse("beneficiary_staffing_update", args=[beneficiary_a.pk])
            data = {
                "lead": str(replacement.pk),
                "helper": str(helper.pk),
                "effective_date": today.isoformat(),
            }
            response = client.post(url, data)
            assert response.status_code == 200
            form = response.context["form"]
            assert set(form.errors) == {"effective_date"}
            assert form.errors["effective_date"] == [translation.gettext(HISTORY_ERROR)]
            assert translation.gettext(HISTORY_ERROR) in response.content.decode()
            for key, value in data.items():
                assert form[key].value() == value
            assert list(beneficiary_a.staffing_periods.values()) == original_history
            assert list(EnrollmentSpecialistAssignment.objects.values()) == original_assignments
            assert ServiceVisit.objects.values().get(pk=visit.pk) == original_visit
            assert (
                AuditEvent.objects.filter(target_type="BeneficiaryStaffingPeriod").count()
                == success_events
            )

            # The same submitted pair succeeds from the next business date.
            data["effective_date"] = (today + timedelta(days=1)).isoformat()
            response = client.post(url, data)
            assert response.status_code == 302
            pair = beneficiary_a.staffing_periods.get(valid_from=today + timedelta(days=1))
            assert (pair.lead_id, pair.helper_id) == (replacement.pk, helper.pk)
            assert (
                AuditEvent.objects.filter(target_type="BeneficiaryStaffingPeriod").count()
                == success_events + 1
            )
            assert list(EnrollmentSpecialistAssignment.objects.values()) == original_assignments
            assert ServiceVisit.objects.values().get(pk=visit.pk) == original_visit


@pytest.mark.parametrize("language", ["en", "ka"])
def test_create_endpoint_maps_service_errors_and_rolls_back_the_whole_creation(
    client, specialist_a, coordinator_a, center_a, language
):
    today = timezone.localdate()
    client.force_login(coordinator_a)
    set_active_center(client, center_a)
    models = (Beneficiary, ServiceEnrollment, BeneficiaryStaffingPeriod, BeneficiaryCodeSequence)
    original_rows = {model: list(model.objects.values()) for model in models}
    original_events = AuditEvent.objects.count()

    def reject_after_staffing(**kwargs):
        replace_beneficiary_staffing(**kwargs)
        raise ValidationError(
            {
                "valid_from": translation.gettext(HISTORY_ERROR),
                "valid_to": translation.gettext(HISTORY_ERROR),
                "lead": translation.gettext("A lead specialist is required."),
                "beneficiary": translation.gettext(
                    "Staffing history is preserved. Create a replacement pair."
                ),
                "__all__": translation.gettext(
                    "Staffing periods cannot overlap, including future appointments."
                ),
            }
        )

    with translation.override(language):
        data = {
            "full_name": "Synthetic rollback beneficiary",
            "enrollment-offering": str(
                center_a.service_offerings.get(service__code="HOME-CARE").pk
            ),
            "enrollment-status": "active",
            "enrollment-start_date": today.isoformat(),
            "staffing-lead": str(specialist_a.pk),
            "staffing-effective_date": today.isoformat(),
        }
        with patch(
            "apps.casework.views.replace_beneficiary_staffing", side_effect=reject_after_staffing
        ):
            response = client.post(reverse("beneficiary_create"), data)
        assert response.status_code == 200
        form = response.context["staffing_form"]
        assert set(form.errors) == {"effective_date", "lead", "__all__"}
        assert form.errors["effective_date"] == [translation.gettext(HISTORY_ERROR)] * 2
        assert len(form.non_field_errors()) == 2
        assert response.context["form"]["full_name"].value() == data["full_name"]
        assert form["lead"].value() == data["staffing-lead"]
        assert form["effective_date"].value() == data["staffing-effective_date"]
        assert translation.gettext(HISTORY_ERROR) in response.content.decode()
    assert {model: list(model.objects.values()) for model in models} == original_rows
    assert AuditEvent.objects.count() == original_events


def test_staffing_endpoint_rolls_back_successful_closure_when_insertion_fails(
    client, beneficiary_a, specialist_a, coordinator_a, center_a
):
    today = timezone.localdate()
    replace_beneficiary_staffing(
        beneficiary=beneficiary_a,
        lead=specialist_a,
        effective_date=today,
        center=center_a,
        actor=coordinator_a,
    )
    original_history = list(beneficiary_a.staffing_periods.values())
    original_events = AuditEvent.objects.count()
    client.force_login(coordinator_a)
    set_active_center(client, center_a)
    with patch(
        "apps.casework.models.BeneficiaryStaffingPeriod.objects.create",
        side_effect=ValidationError({"valid_from": HISTORY_ERROR}),
    ):
        response = client.post(
            reverse("beneficiary_staffing_update", args=[beneficiary_a.pk]),
            {"lead": specialist_a.pk, "effective_date": (today + timedelta(days=1)).isoformat()},
        )
    assert response.status_code == 200
    assert response.context["form"].errors["effective_date"] == [HISTORY_ERROR]
    assert list(beneficiary_a.staffing_periods.values()) == original_history
    assert AuditEvent.objects.count() == original_events


@pytest.mark.parametrize("team", ["lead", "pair", "legacy"])
def test_responsibility_queries_are_bounded_for_rows_workspace_and_caseload(
    client, beneficiary_a, specialist_a, center_a, manager, team
):
    today = timezone.localdate()
    helper = make_specialist(center_a, "bounded-helper") if team != "lead" else None

    def prepare(person):
        if team == "legacy":
            capture_legacy_assignment(
                EnrollmentSpecialistAssignment.objects.create(
                    enrollment=person.enrollments.get(),
                    specialist=helper,
                    assignment_role="primary",
                    valid_from=today,
                )
            )
        else:
            replace_beneficiary_staffing(
                beneficiary=person,
                lead=specialist_a,
                helper=helper,
                effective_date=today,
                center=center_a,
                actor=manager,
            )

    def measure():
        # Fresh users make role lookup costs identical in the two measurements.
        user = get_user_model().objects.get(pk=manager.pk)
        with CaptureQueriesContext(connection) as selector_queries:
            rows = active_enrollment_assignments_for_user(user, center_a, as_of=today)
        expected_people = set(Beneficiary.objects.values_list("pk", flat=True))
        expected_team = {specialist_a.pk} | ({helper.pk} if helper else set())
        assert {row.enrollment.beneficiary_id for row in rows} == expected_people
        assert {row.specialist_id for row in rows} == expected_team
        assert len(rows) == len(expected_people) * len(expected_team)
        assert all(row.confirmed == (team != "legacy") for row in rows)
        assert {row.assignment_role for row in rows} == (
            {"primary", "secondary"} if team == "pair" else {"primary"}
        )

        enrollments = list(enrollments_for_user(user, center_a))
        with CaptureQueriesContext(connection) as list_queries:
            list_rows = responsibility_rows(enrollments, today)
        assert {row.pk for row in list_rows} == {row.pk for row in rows}
        with CaptureQueriesContext(connection) as workspace_queries:
            workspace = build_enrollment_workspace_rows(
                enrollments,
                visits=ServiceVisit.objects.none(),
                assessments=Assessment.objects.none(),
                plans=IndividualPlan.objects.none(),
                as_of=today,
            )
        assert {row.pk for summary in workspace for row in summary.current_assignments} == {
            row.pk for row in rows
        }

        client.force_login(manager)
        set_active_center(client, center_a)
        with CaptureQueriesContext(connection) as report_queries:
            response = client.get(
                reverse("reports"),
                {"type": "caseload", "status": "active", "specialist": specialist_a.pk},
            )
        assert response.status_code == 200
        assert len(response.context["rows"]) == 1
        assert response.context["rows"][0].specialist.pk == specialist_a.pk
        assert response.context["rows"][0].beneficiary_count == len(expected_people)
        specialist_user = get_user_model().objects.get(
            pk=(helper or specialist_a).staff_profile.user_id
        )
        with CaptureQueriesContext(connection) as specialist_queries:
            specialist_rows = active_enrollment_assignments_for_user(specialist_user, center_a)
        assert {row.specialist_id for row in specialist_rows} == {(helper or specialist_a).pk}
        assert len(specialist_rows) == len(expected_people)
        return tuple(
            len(queries)
            for queries in (
                selector_queries,
                list_queries,
                workspace_queries,
                report_queries,
                specialist_queries,
            )
        )

    prepare(beneficiary_a)
    one = measure()
    for number in range(9):
        person = make_beneficiary(center_a, specialist_a, name=f"Synthetic bounded person {number}")
        prepare(person)
    ten = measure()
    print(
        f"{team} queries (selector, list, workspace, filtered report, specialist): "
        f"1={one}, 10={ten}"
    )
    assert ten == one
    assert ten[0] <= 13
    assert ten[1] <= 4
    assert ten[2] <= 4
    assert ten[3] <= 21
    for specialist in (specialist_a, helper):
        if specialist:
            user = specialist.staff_profile.user
            assigned = active_enrollment_assignments_for_user(user, center_a)
            assert len(assigned) == 10
            assert {row.specialist_id for row in assigned} == {specialist.pk}
            assert len(enrollments_for_user(user, center_a)) == 10


@pytest.mark.parametrize("confirmed", [False, True])
@pytest.mark.parametrize("inactive", ["user", "staff", "membership", "center"])
def test_batched_responsibility_rechecks_eligibility_with_reused_prefetched_inputs(
    beneficiary_a, specialist_a, center_a, manager, confirmed, inactive
):
    today = timezone.localdate()
    if confirmed:
        replace_beneficiary_staffing(
            beneficiary=beneficiary_a,
            lead=specialist_a,
            effective_date=today,
            center=center_a,
            actor=manager,
        )
    enrollments = list(enrollments_for_user(manager, center_a))
    assert {row.specialist_id for row in responsibility_rows(enrollments, today)} == {
        specialist_a.pk
    }
    if inactive == "user":
        get_user_model().objects.filter(pk=specialist_a.staff_profile.user_id).update(
            is_active=False
        )
    elif inactive == "staff":
        type(specialist_a.staff_profile).objects.filter(pk=specialist_a.staff_profile_id).update(
            status="inactive"
        )
    elif inactive == "membership":
        specialist_a.center_assignments.all().delete()
    else:
        type(center_a).objects.filter(pk=center_a.pk).update(is_active=False)
    assert responsibility_rows(enrollments, today) == []
    assert active_enrollment_assignments_for_user(manager, center_a) == []


def test_batched_rows_preserve_historical_continuity_and_do_not_revive_legacy_access(
    beneficiary_a, specialist_a, center_a, manager
):
    today = timezone.localdate()
    replacement = make_specialist(center_a, "future-confirmed-lead")
    helper = make_specialist(center_a, "future-confirmed-helper")
    enrollment = beneficiary_a.enrollments.get()
    uncaptured = make_specialist(center_a, "uncaptured-legacy")
    EnrollmentSpecialistAssignment.objects.create(
        enrollment=enrollment, specialist=uncaptured, valid_from=today
    )
    period = replace_beneficiary_staffing(
        beneficiary=beneficiary_a,
        lead=replacement,
        helper=helper,
        effective_date=today + timedelta(days=7),
        center=center_a,
        actor=manager,
    )
    period.valid_to = today + timedelta(days=10)
    period.save(update_fields=["valid_to", "updated_at"])
    enrollments = list(enrollments_for_user(manager, center_a))
    for day, expected in (
        (today - timedelta(days=1), {specialist_a.pk}),
        (today, {specialist_a.pk}),
        (today + timedelta(days=6), {specialist_a.pk}),
        (today + timedelta(days=7), {replacement.pk, helper.pk}),
        (today + timedelta(days=10), set()),
    ):
        rows = responsibility_rows(enrollments, day)
        assert {row.specialist_id for row in rows} == expected
        assert (
            set(responsible_specialists(enrollment, day).values_list("pk", flat=True)) == expected
        )
    # At a future wall-clock date, original evidence remains available for continuity
    # before confirmation, while ended confirmed staffing never restores the bridge.
    with patch("django.utils.timezone.localdate", return_value=today + timedelta(days=10)):
        assert {row.specialist_id for row in responsibility_rows(enrollments, today)} == {
            specialist_a.pk,
            uncaptured.pk,
        }
        assert set(responsible_specialists(enrollment, today).values_list("pk", flat=True)) == {
            specialist_a.pk,
            uncaptured.pk,
        }
        assert responsibility_rows(enrollments, today + timedelta(days=10)) == []


def test_batched_legacy_rows_honor_the_exact_frozen_expiry(beneficiary_a, specialist_a):
    from apps.casework.models import LegacyStaffingGrant

    enrollments = list(beneficiary_a.enrollments.prefetch_related("specialist_assignments"))
    expiry = LegacyStaffingGrant.objects.get().expires_on
    assert {
        row.specialist_id for row in responsibility_rows(enrollments, expiry - timedelta(days=1))
    } == {specialist_a.pk}
    assert responsibility_rows(enrollments, expiry) == []
    with patch("django.utils.timezone.localdate", return_value=expiry):
        assert responsibility_rows(enrollments, expiry - timedelta(days=1)) == []


@pytest.mark.parametrize("confirmed", [False, True])
def test_batched_rows_recheck_transfer_boundaries_and_original_legacy_placement(
    beneficiary_a, specialist_a, center_a, center_b, manager, confirmed
):
    today = timezone.localdate()
    if confirmed:
        replace_beneficiary_staffing(
            beneficiary=beneficiary_a,
            lead=specialist_a,
            effective_date=today,
            center=center_a,
            actor=manager,
        )
    enrollments = list(enrollments_for_user(manager, center_a))
    enrollment = enrollments[0]
    boundary = today + timedelta(days=1)
    transfer_enrollment(
        enrollment,
        destination_offering=center_b.service_offerings.get(service=enrollment.service),
        effective_date=boundary,
        reason="Synthetic batched transfer",
        actor=manager,
    )
    assert {row.specialist_id for row in responsibility_rows(enrollments, today)} == {
        specialist_a.pk
    }
    assert responsibility_rows(enrollments, boundary) == []
    add_specialist_center(specialist_a, center_b)
    assert {row.specialist_id for row in responsibility_rows(enrollments, boundary)} == (
        {specialist_a.pk} if confirmed else set()
    )
    transfer_enrollment(
        enrollment,
        destination_offering=center_a.service_offerings.get(service=enrollment.service),
        effective_date=boundary + timedelta(days=1),
        reason="Synthetic batched return",
        actor=manager,
    )
    assert {
        row.specialist_id for row in responsibility_rows(enrollments, boundary + timedelta(days=1))
    } == ({specialist_a.pk} if confirmed else set())


def test_beneficiary_workspace_selection_and_caseload_filters_keep_pair_scope(
    client, beneficiary_a, beneficiary_b, specialist_a, specialist_b, center_a, manager
):
    today = timezone.localdate()
    helper = make_specialist(center_a, "workspace-batch-helper")
    replace_beneficiary_staffing(
        beneficiary=beneficiary_a,
        lead=specialist_a,
        helper=helper,
        effective_date=today,
        center=center_a,
        actor=manager,
    )
    added = create_enrollment(
        beneficiary=beneficiary_a,
        offering=center_a.service_offerings.get(service__code="HOME-CARE"),
        start_date=today,
        status="active",
        actor=manager,
    )
    for specialist in (specialist_a, helper):
        client.force_login(specialist.staff_profile.user)
        set_active_center(client, center_a)
        response = client.get(
            reverse("beneficiary_detail", args=[beneficiary_a.pk]), {"enrollment": added.pk}
        )
        assert response.status_code == 200
        summary = response.context["workspace_summary"]
        assert summary.enrollment.pk == added.pk
        assert {row.specialist_id for row in summary.current_assignments} == {
            specialist_a.pk,
            helper.pk,
        }
        body = response.content.decode()
        assert str(specialist_a) in body and str(helper) in body
        assert beneficiary_b.full_name not in body
        denied = client.get(
            reverse("beneficiary_detail", args=[beneficiary_a.pk]),
            {"enrollment": beneficiary_b.enrollments.get().pk},
        )
        assert denied.status_code == 404

    client.force_login(manager)
    set_active_center(client, center_a)
    for filters, expected in (
        ({}, {specialist_a.pk, helper.pk}),
        ({"specialist": helper.pk}, {helper.pk}),
        ({"service": added.service_id}, {specialist_a.pk, helper.pk}),
        ({"status": "suspended"}, set()),
        ({"q": helper.staff_profile.employee_number}, {helper.pk}),
        ({"q": str(helper)}, {helper.pk}),
        ({"specialist": specialist_b.pk}, set()),
    ):
        response = client.get(reverse("reports"), {"type": "caseload", **filters})
        assert response.status_code == 200
        rows = response.context["rows"]
        assert {row.specialist.pk for row in rows} == expected
        assert all(row.beneficiary_count == 1 for row in rows)
        assert all(row.enrollment_count == (1 if "service" in filters else 2) for row in rows)
