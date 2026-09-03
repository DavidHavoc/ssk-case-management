from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import gettext

from apps.accounts.roles import CENTRAL_HR, COORDINATOR
from apps.audit.models import AuditEvent
from apps.casework.forms import (
    AssessmentForm,
    EnrollmentAssignmentForm,
    EnrollmentServiceScheduleForm,
    IndividualPlanForm,
    ServiceVisitForm,
)
from apps.casework.models import (
    AttachmentParentType,
    CenterServiceOffering,
    EnrollmentSpecialistAssignment,
    PrivateAttachment,
    ServiceVisit,
)
from apps.casework.services import transfer_enrollment
from apps.core.authorization import (
    assessments_for_user,
    beneficiaries_for_user,
    enrollments_for_user,
    plans_for_user,
    staff_profiles_for_user,
    visits_for_user,
)

from .factories import (
    ensure_visit_catalogs,
    make_assessment,
    make_plan,
    make_specialist,
    set_active_center,
)

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()


@pytest.fixture(autouse=True)
def private_media_root(tmp_path, settings):
    settings.PRIVATE_MEDIA_ROOT = tmp_path / "private"
    return settings.PRIVATE_MEDIA_ROOT


def _enrollment(beneficiary):
    return beneficiary.enrollments.get(service__code="LEGACY-OTHER")


def _replace_assignments(enrollment, specialist, *intervals):
    enrollment.specialist_assignments.filter(specialist=specialist).delete()
    return [
        EnrollmentSpecialistAssignment.objects.create(
            enrollment=enrollment,
            specialist=specialist,
            assignment_role=EnrollmentSpecialistAssignment.Role.PRIMARY,
            valid_from=valid_from,
            valid_to=valid_to,
            legacy_dates_incomplete=valid_from is None,
        )
        for valid_from, valid_to in intervals
    ]


def _attachment(parent, user, filename="assignment-history.pdf"):
    return PrivateAttachment.objects.create(
        parent_type=AttachmentParentType.SERVICE_VISIT,
        parent_id=parent.pk,
        center=parent.center,
        file=SimpleUploadedFile(
            filename,
            b"%PDF-1.7\nSynthetic assignment history",
            content_type="application/pdf",
        ),
        original_filename=filename,
        content_type="application/pdf",
        uploaded_by=user,
    )


def test_assignment_intervals_are_inclusive_from_and_exclusive_to(
    specialist_a, center_a, beneficiary_a
):
    enrollment = _enrollment(beneficiary_a)
    user = specialist_a.staff_profile.user
    assignment = _replace_assignments(
        enrollment,
        specialist_a,
        (TODAY, TODAY + timedelta(days=1)),
    )[0]

    assert assignment.is_effective(TODAY)
    assert not assignment.is_effective(TODAY + timedelta(days=1))
    assert enrollments_for_user(user, center_a, as_of=TODAY).filter(pk=enrollment.pk).exists()
    assert (
        not enrollments_for_user(user, center_a, as_of=TODAY + timedelta(days=1))
        .filter(pk=enrollment.pk)
        .exists()
    )

    legacy = beneficiary_a.specialist_assignments.get(specialist=specialist_a)
    legacy.from_date = TODAY
    legacy.to_date = TODAY + timedelta(days=1)
    assert legacy.is_effective(TODAY)
    assert not legacy.is_effective(TODAY + timedelta(days=1))
    legacy.to_date = TODAY
    with pytest.raises(ValidationError, match="later than from date"):
        legacy.full_clean()


def test_unknown_legacy_start_does_not_grant_current_access(specialist_a, center_a, beneficiary_a):
    enrollment = _enrollment(beneficiary_a)
    user = specialist_a.staff_profile.user
    enrollment.specialist_assignments.filter(specialist=specialist_a).delete()
    with pytest.raises(ValidationError, match="Valid from is required"):
        EnrollmentSpecialistAssignment.objects.create(
            enrollment=enrollment,
            specialist=specialist_a,
        )
    assignment = _replace_assignments(enrollment, specialist_a, (None, None))[0]

    assert not assignment.is_effective(TODAY)
    assert assignment.effective_status == "unknown"
    assert not enrollments_for_user(user, center_a, as_of=TODAY).filter(pk=enrollment.pk).exists()

    legacy = beneficiary_a.specialist_assignments.get(specialist=specialist_a)
    assert legacy.from_date is None
    assert not legacy.is_effective(TODAY)


def test_assignment_policy_frontend_strings_have_georgian_translations(center_a):
    with translation.override("ka"):
        form = EnrollmentAssignmentForm(center=center_a)
        assert "წვდომა იწყება" in str(form.fields["valid_from"].help_text)
        assert "წვდომა სრულდება" in str(form.fields["valid_to"].help_text)
        assert gettext("Future") == "სამომავლო"
        assert gettext("Expired") == "ვადაგასული"
        assert gettext("Unknown assignment dates") == "დანიშვნის თარიღები უცნობია"
        assert gettext("Central HR") == "ცენტრალური HR"


@pytest.mark.parametrize(
    ("valid_from", "valid_to", "authorized"),
    [
        (TODAY + timedelta(days=1), None, False),
        (TODAY - timedelta(days=10), TODAY, False),
        (TODAY, None, True),
        (TODAY - timedelta(days=10), TODAY + timedelta(days=1), True),
    ],
)
def test_current_future_and_expired_assignment_access(
    specialist_a,
    center_a,
    beneficiary_a,
    valid_from,
    valid_to,
    authorized,
):
    enrollment = _enrollment(beneficiary_a)
    user = specialist_a.staff_profile.user
    _replace_assignments(enrollment, specialist_a, (valid_from, valid_to))

    assert (
        enrollments_for_user(user, center_a, as_of=TODAY).filter(pk=enrollment.pk).exists()
        is authorized
    )
    assert beneficiaries_for_user(user, center_a).filter(pk=beneficiary_a.pk).exists() is authorized


def test_removed_current_assignment_does_not_revive_expired_or_legacy_access(
    specialist_a, center_a, beneficiary_a
):
    enrollment = _enrollment(beneficiary_a)
    user = specialist_a.staff_profile.user
    expired, current = _replace_assignments(
        enrollment,
        specialist_a,
        (TODAY - timedelta(days=60), TODAY - timedelta(days=30)),
        (TODAY - timedelta(days=1), TODAY + timedelta(days=30)),
    )

    assert enrollments_for_user(user, center_a, as_of=TODAY).filter(pk=enrollment.pk).exists()
    current.delete()
    assert EnrollmentSpecialistAssignment.objects.filter(pk=expired.pk).exists()
    assert not enrollments_for_user(user, center_a, as_of=TODAY).filter(pk=enrollment.pk).exists()

    enrollment.specialist_assignments.all().delete()
    assert beneficiary_a.specialist_assignments.filter(specialist=specialist_a).exists()
    assert not enrollments_for_user(user, center_a, as_of=TODAY).filter(pk=enrollment.pk).exists()


def test_overlapping_active_rows_grant_access_only_until_the_last_row_is_removed(
    specialist_a, center_a, beneficiary_a
):
    enrollment = _enrollment(beneficiary_a)
    first, second = _replace_assignments(
        enrollment,
        specialist_a,
        (TODAY - timedelta(days=10), TODAY + timedelta(days=10)),
        (TODAY - timedelta(days=1), TODAY + timedelta(days=20)),
    )
    user = specialist_a.staff_profile.user

    assert enrollments_for_user(user, center_a, as_of=TODAY).filter(pk=enrollment.pk).exists()
    first.delete()
    assert enrollments_for_user(user, center_a, as_of=TODAY).filter(pk=enrollment.pk).exists()
    second.delete()
    assert not enrollments_for_user(user, center_a, as_of=TODAY).filter(pk=enrollment.pk).exists()


def test_current_assignee_reads_history_but_cannot_change_pre_assignment_records(
    client, coordinator_a, specialist_a, center_a, beneficiary_a
):
    enrollment = _enrollment(beneficiary_a)
    historical_date = TODAY - timedelta(days=30)
    visit = ServiceVisit.objects.filter(enrollment=enrollment).first()
    if visit is None:
        from .factories import make_visit

        visit = make_visit(beneficiary_a, specialist_a, visit_date=historical_date)
    assessment = make_assessment(
        beneficiary_a,
        specialist_a,
        assessment_date=historical_date,
    )
    plan = make_plan(beneficiary_a, specialist_a)
    attachment = _attachment(visit, coordinator_a)
    _replace_assignments(enrollment, specialist_a, (date(2026, 1, 1), TODAY))

    current_specialist = make_specialist(center_a, "continuity-current")
    EnrollmentSpecialistAssignment.objects.create(
        enrollment=enrollment,
        specialist=current_specialist,
        assignment_role=EnrollmentSpecialistAssignment.Role.SECONDARY,
        valid_from=TODAY,
    )
    user = current_specialist.staff_profile.user

    with patch("apps.core.authorization.timezone.localdate", return_value=TODAY):
        assert visits_for_user(user, center_a).filter(pk=visit.pk).exists()
        assert assessments_for_user(user, center_a).filter(pk=assessment.pk).exists()
        assert plans_for_user(user, center_a).filter(pk=plan.pk).exists()
        assert not visits_for_user(user, center_a, for_change=True).filter(pk=visit.pk).exists()
        assert (
            not assessments_for_user(user, center_a, for_change=True)
            .filter(pk=assessment.pk)
            .exists()
        )
        assert not plans_for_user(user, center_a, for_change=True).filter(pk=plan.pk).exists()

        client.force_login(user)
        set_active_center(client, center_a)
        list_response = client.get(reverse("visit_list"))
        assert list_response.status_code == 200
        assert beneficiary_a.full_name in list_response.content.decode()
        for route in ("assessment_list", "plan_list"):
            assert beneficiary_a.full_name in client.get(reverse(route)).content.decode()
        for route, record in (
            ("visit_detail", visit),
            ("assessment_detail", assessment),
            ("plan_detail", plan),
        ):
            assert client.get(reverse(route, kwargs={"pk": record.pk})).status_code == 200
        for route, record in (
            ("visit_update", visit),
            ("assessment_update", assessment),
            ("plan_update", plan),
        ):
            assert client.get(reverse(route, kwargs={"pk": record.pk})).status_code == 404

        for report_type in ("visits", "assessments", "plans"):
            report = client.get(reverse("reports"), {"type": report_type})
            assert report.status_code == 200
            assert beneficiary_a.full_name in report.content.decode()
        detail = client.get(
            reverse("beneficiary_detail", kwargs={"pk": beneficiary_a.pk}),
            {"enrollment": enrollment.pk},
        )
        assert detail.status_code == 200
        assert attachment.original_filename in detail.content.decode()
        assert (
            client.get(reverse("attachment_download", kwargs={"pk": attachment.pk})).status_code
            == 200
        )
        assert (
            client.get(
                reverse(
                    "attachment_upload",
                    kwargs={
                        "parent_type": AttachmentParentType.SERVICE_VISIT,
                        "parent_id": visit.pk,
                    },
                )
            ).status_code
            == 404
        )


def test_expired_and_future_assignees_are_denied_every_routine_path(
    client, coordinator_a, specialist_a, center_a, beneficiary_a
):
    from .factories import make_visit

    enrollment = _enrollment(beneficiary_a)
    visit = make_visit(
        beneficiary_a,
        specialist_a,
        visit_date=TODAY - timedelta(days=20),
    )
    attachment = _attachment(visit, coordinator_a, "expired-denied.pdf")
    assessment = make_assessment(
        beneficiary_a,
        specialist_a,
        assessment_date=TODAY - timedelta(days=19),
    )
    plan = make_plan(beneficiary_a, specialist_a)
    _replace_assignments(enrollment, specialist_a, (date(2026, 1, 1), TODAY))
    future_specialist = make_specialist(center_a, "future-assignee")
    EnrollmentSpecialistAssignment.objects.create(
        enrollment=enrollment,
        specialist=future_specialist,
        valid_from=TODAY + timedelta(days=1),
    )

    with patch("apps.core.authorization.timezone.localdate", return_value=TODAY):
        for user in (specialist_a.staff_profile.user, future_specialist.staff_profile.user):
            client.force_login(user)
            set_active_center(client, center_a)
            assert client.get(reverse("beneficiary_list")).status_code == 200
            assert (
                beneficiary_a.full_name
                not in client.get(reverse("beneficiary_list")).content.decode()
            )
            assert (
                client.get(
                    reverse("beneficiary_detail", kwargs={"pk": beneficiary_a.pk})
                ).status_code
                == 404
            )
            assert client.get(reverse("visit_detail", kwargs={"pk": visit.pk})).status_code == 404
            assert (
                client.get(reverse("assessment_detail", kwargs={"pk": assessment.pk})).status_code
                == 404
            )
            assert client.get(reverse("plan_detail", kwargs={"pk": plan.pk})).status_code == 404
            for route, record in (
                ("visit_update", visit),
                ("assessment_update", assessment),
                ("plan_update", plan),
            ):
                assert client.get(reverse(route, kwargs={"pk": record.pk})).status_code == 404
            assert (
                client.get(reverse("attachment_download", kwargs={"pk": attachment.pk})).status_code
                == 404
            )
            for route in ("visit_list", "assessment_list", "plan_list"):
                assert beneficiary_a.full_name not in client.get(reverse(route)).content.decode()
            for report_type in ("visits", "assessments", "plans"):
                report = client.get(reverse("reports"), {"type": report_type})
                assert report.status_code == 200
                assert beneficiary_a.full_name not in report.content.decode()
            assert client.get(reverse("report_export"), {"type": "visits"}).status_code == 403

    assert AuditEvent.objects.filter(
        actor=specialist_a.staff_profile.user,
        event_type=AuditEvent.EventType.SENSITIVE_READ,
        target_type="Beneficiary",
        outcome=AuditEvent.Outcome.DENIED,
    ).exists()
    assert AuditEvent.objects.filter(
        actor=future_specialist.staff_profile.user,
        event_type=AuditEvent.EventType.DOWNLOAD,
        target_type="PrivateAttachment",
        outcome=AuditEvent.Outcome.DENIED,
    ).exists()
    assert AuditEvent.objects.filter(
        actor=future_specialist.staff_profile.user,
        event_type=AuditEvent.EventType.EXPORT,
        target_type="Report",
        outcome=AuditEvent.Outcome.DENIED,
    ).exists()


def test_current_assignment_cannot_create_records_after_exclusive_end(
    specialist_a, center_a, beneficiary_a
):
    enrollment = _enrollment(beneficiary_a)
    user = specialist_a.staff_profile.user
    assignment_end = TODAY + timedelta(days=1)
    _replace_assignments(enrollment, specialist_a, (TODAY - timedelta(days=1), assignment_end))
    activity, location = ensure_visit_catalogs()
    common = {
        "enrollment": enrollment.pk,
        "specialist": specialist_a.pk,
    }

    with patch("apps.core.authorization.timezone.localdate", return_value=TODAY):
        visit_form = ServiceVisitForm(
            data={
                **common,
                "visit_date": assignment_end,
                "activity": activity.pk,
                "delivery_location": location.pk,
                "participation_format": "individual",
                "status": ServiceVisit.Status.PLANNED,
                "service_units": "0",
                "duration_minutes": "45",
                "participants": "1",
                "cancellation_reason": "",
                "notes": "Synthetic future visit.",
            },
            user=user,
            center=center_a,
        )
        assessment_form = AssessmentForm(
            data={
                **common,
                "assessment_date": assignment_end,
                "assessment_type": "initial",
                "scoring_tool": "other",
                "total_score": "1",
                "service_schedule_count": "0",
            },
            user=user,
            center=center_a,
        )
        plan_form = IndividualPlanForm(
            data={
                **common,
                "status": "draft",
                "plan_start_date": assignment_end,
                "plan_end_date": "",
                "review_frequency": "monthly",
                "notes": "Synthetic future plan.",
            },
            user=user,
            center=center_a,
        )
        schedule_form = EnrollmentServiceScheduleForm(
            data={
                "enrollment": enrollment.pk,
                "schedule_month": assignment_end.strftime("%Y-%m"),
                "activity": activity.pk,
                "delivery_location": location.pk,
                "participation_format": "individual",
                "planned_visits": "1",
                "planned_units": "1",
                "expected_participants": "1",
                "notes": "Synthetic future schedule.",
            },
            user=user,
            center=center_a,
        )

        for form in (visit_form, assessment_form, plan_form):
            assert specialist_a not in form.fields["specialist"].queryset

        for form in (visit_form, assessment_form, plan_form, schedule_form):
            assert not form.is_valid()
            assert "not effective on the selected record date" in str(form.errors)


def test_transferred_current_assignee_can_read_prior_center_record_and_attachment(
    client,
    coordinator_a,
    specialist_a,
    specialist_b,
    center_a,
    center_b,
    beneficiary_a,
):
    from .factories import make_visit

    enrollment = _enrollment(beneficiary_a)
    visit = make_visit(
        beneficiary_a,
        specialist_a,
        visit_date=TODAY - timedelta(days=30),
    )
    attachment = _attachment(visit, coordinator_a, "prior-center-visible.pdf")
    destination = CenterServiceOffering.objects.get(center=center_b, service=enrollment.service)
    transfer_enrollment(
        enrollment,
        destination_offering=destination,
        effective_date=TODAY,
        reason="Synthetic authorization transfer",
        actor=coordinator_a,
    )
    EnrollmentSpecialistAssignment.objects.create(
        enrollment=enrollment,
        specialist=specialist_b,
        valid_from=TODAY,
    )

    with patch("apps.core.authorization.timezone.localdate", return_value=TODAY):
        client.force_login(specialist_b.staff_profile.user)
        set_active_center(client, center_b)
        assert client.get(reverse("visit_detail", kwargs={"pk": visit.pk})).status_code == 200
        assert (
            client.get(reverse("attachment_download", kwargs={"pk": attachment.pk})).status_code
            == 200
        )
        detail = client.get(
            reverse("beneficiary_detail", kwargs={"pk": beneficiary_a.pk}),
            {"enrollment": enrollment.pk},
        )
        assert detail.status_code == 200
        assert attachment.original_filename in detail.content.decode()


def test_multiple_role_precedence_preserves_coordinator_case_scope(
    client, specialist_a, center_a, beneficiary_a
):
    enrollment = _enrollment(beneficiary_a)
    user = specialist_a.staff_profile.user
    _replace_assignments(enrollment, specialist_a, (date(2026, 1, 1), TODAY))
    user.groups.add(user.groups.model.objects.get(name=COORDINATOR))

    with patch("apps.core.authorization.timezone.localdate", return_value=TODAY):
        assert enrollments_for_user(user, center_a).filter(pk=enrollment.pk).exists()
        client.force_login(user)
        set_active_center(client, center_a)
        assert (
            client.get(reverse("beneficiary_detail", kwargs={"pk": beneficiary_a.pk})).status_code
            == 200
        )


def test_staff_directory_roles_and_mixed_role_scope(
    client,
    central_hr,
    coordinator_a,
    specialist_a,
    specialist_b,
    center_a,
):
    hr_attachment = PrivateAttachment.objects.create(
        parent_type=AttachmentParentType.STAFF_PROFILE,
        parent_id=specialist_a.staff_profile.pk,
        center=center_a,
        document_type=PrivateAttachment.DocumentType.EMPLOYEE_CONTRACT,
        file=SimpleUploadedFile(
            "synthetic-hr-contract.pdf",
            b"%PDF-1.7\nSynthetic HR contract",
            content_type="application/pdf",
        ),
        original_filename="synthetic-hr-contract.pdf",
        uploaded_by=central_hr,
    )
    client.force_login(central_hr)
    assert client.get(reverse("dashboard")).url == reverse("staff_list")
    response = client.get(reverse("staff_list"))
    assert response.status_code == 200
    assert specialist_a.staff_profile.display_name in response.content.decode()
    assert specialist_b.staff_profile.display_name in response.content.decode()
    assert specialist_b.staff_profile.user.email in response.content.decode()
    assert set(staff_profiles_for_user(central_hr)) >= {
        specialist_a.staff_profile,
        specialist_b.staff_profile,
    }
    download = client.get(reverse("staff_attachment_download", kwargs={"pk": hr_attachment.pk}))
    assert download.status_code == 200
    download.close()
    assert client.get(reverse("beneficiary_list")).status_code == 403

    client.force_login(coordinator_a)
    response = client.get(reverse("staff_list"))
    assert specialist_a.staff_profile.display_name in response.content.decode()
    assert specialist_b.staff_profile.display_name not in response.content.decode()
    assert specialist_a.staff_profile.user.email not in response.content.decode()
    document_response = client.get(
        reverse("staff_attachment_download", kwargs={"pk": hr_attachment.pk})
    )
    assert document_response.status_code == 403
    assert (
        client.get(
            reverse("staff_detail", kwargs={"pk": specialist_b.staff_profile.pk})
        ).status_code
        == 404
    )

    specialist_user = specialist_a.staff_profile.user
    client.force_login(specialist_user)
    assert client.get(reverse("staff_list")).status_code == 403
    permission = Permission.objects.get(
        codename="view_staffprofile",
        content_type__app_label="centers",
    )
    specialist_user.user_permissions.add(permission)
    specialist_user = type(specialist_user).objects.get(pk=specialist_user.pk)
    client.force_login(specialist_user)
    response = client.get(reverse("staff_list"))
    assert response.status_code == 200
    assert specialist_a.staff_profile.display_name in response.content.decode()
    assert specialist_b.staff_profile.display_name in response.content.decode()

    specialist_user.groups.add(specialist_user.groups.model.objects.get(name=CENTRAL_HR))
    specialist_user = type(specialist_user).objects.get(pk=specialist_user.pk)
    assert (
        staff_profiles_for_user(specialist_user).filter(pk=specialist_b.staff_profile.pk).exists()
    )
