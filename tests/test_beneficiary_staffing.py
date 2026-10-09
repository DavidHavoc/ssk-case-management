from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.urls import reverse
from django.utils import timezone, translation

from apps.casework.forms import BeneficiaryStaffingForm, ServiceVisitForm
from apps.casework.models import (
    BeneficiaryStaffingPeriod,
    EnrollmentSpecialistAssignment,
)
from apps.casework.services import (
    create_enrollment,
    replace_beneficiary_staffing,
    transfer_enrollment,
    transition_enrollment,
)
from apps.casework.staffing import (
    current_staffing,
    responsibility_rows,
    responsible_specialists,
    staffing_needs_review,
)
from apps.core.authorization import beneficiaries_for_user, enrollments_for_user, visits_for_user

from .factories import (
    add_specialist_center,
    capture_legacy_assignment,
    make_specialist,
    make_visit,
    set_active_center,
)

pytestmark = pytest.mark.django_db
TODAY = timezone.localdate()


def appoint(person, lead, manager, center, helper=None, on_date=TODAY):
    return replace_beneficiary_staffing(
        beneficiary=person,
        lead=lead,
        helper=helper,
        effective_date=on_date,
        center=center,
        actor=manager,
    )


def test_form_requires_one_lead_optional_helper_and_rejects_extra_rows(center_a, specialist_a):
    assert not BeneficiaryStaffingForm(data={"effective_date": TODAY}, center=center_a).is_valid()
    data = {"lead": specialist_a.pk, "effective_date": TODAY}
    assert BeneficiaryStaffingForm(data=data, center=center_a).is_valid()
    assert not BeneficiaryStaffingForm(
        data={**data, "helper": specialist_a.pk}, center=center_a
    ).is_valid()
    for key in ("assignments-TOTAL_FORMS", "assignments-2-specialist"):
        assert not BeneficiaryStaffingForm(data={**data, key: "3"}, center=center_a).is_valid()


@pytest.mark.parametrize("inactive", ["user", "staff", "membership", "center"])
def test_choices_recheck_deactivation(center_a, specialist_a, specialist_b, inactive):
    if inactive == "user":
        specialist_a.staff_profile.user.is_active = False
        specialist_a.staff_profile.user.save()
    elif inactive == "staff":
        specialist_a.staff_profile.status = "inactive"
        specialist_a.staff_profile.save()
    elif inactive == "membership":
        specialist_a.center_assignments.all().delete()
    else:
        center_a.is_active = False
        center_a.save()
    choices = BeneficiaryStaffingForm(center=center_a).fields["lead"].queryset
    assert not choices.filter(pk__in=[specialist_a.pk, specialist_b.pk]).exists()


def test_pair_shared_across_two_services_and_later_service(
    beneficiary_a, specialist_a, center_a, manager
):
    helper = make_specialist(center_a, "staffing-helper")
    pair = appoint(beneficiary_a, specialist_a, manager, center_a, helper)
    for code in ("HOME-CARE", "FOOD-DELIVERY"):
        create_enrollment(
            beneficiary=beneficiary_a,
            offering=center_a.service_offerings.get(service__code=code),
            start_date=TODAY,
            status="active",
            actor=manager,
        )
    assert beneficiary_a.staffing_periods.count() == 1
    for specialist in (specialist_a, helper):
        authorized = enrollments_for_user(specialist.staff_profile.user, center_a)
        assert authorized.filter(beneficiary=beneficiary_a).count() == 3
        for enrollment in authorized:
            assert responsible_specialists(enrollment, TODAY).filter(pk=specialist.pk).exists()
    assert pair.helper_id == helper.pk


def test_reassignment_preserves_authorship_and_continuity_history(
    beneficiary_a, specialist_a, center_a, manager, client
):
    historical = make_visit(beneficiary_a, specialist_a)
    before = historical.specialist_id
    new = make_specialist(center_a, "new-person-lead")
    appoint(beneficiary_a, new, manager, center_a)
    assert not beneficiaries_for_user(specialist_a.staff_profile.user, center_a).exists()
    assert visits_for_user(new.staff_profile.user, center_a).filter(pk=historical.pk).exists()
    assert (
        not visits_for_user(new.staff_profile.user, center_a, for_change=True)
        .filter(pk=historical.pk)
        .exists()
    )
    historical.refresh_from_db()
    assert historical.specialist_id == before
    enrollment = beneficiary_a.enrollments.get()
    assert (
        responsible_specialists(enrollment, historical.visit_date)
        .filter(pk=specialist_a.pk)
        .exists()
    )
    with pytest.raises(ValidationError):
        make_visit(beneficiary_a, specialist_a, visit_date=TODAY)
    assert make_visit(beneficiary_a, new, visit_date=TODAY).specialist_id == new.pk


def test_future_replacements_are_disjoint_and_expiration_never_revives_legacy(
    beneficiary_a, specialist_a, center_a, manager
):
    first = appoint(beneficiary_a, specialist_a, manager, center_a)
    new = make_specialist(center_a, "future-person-lead")
    future = TODAY + timedelta(days=10)
    second = appoint(beneficiary_a, new, manager, center_a, on_date=future)
    first.refresh_from_db()
    assert first.valid_to == future
    user = new.staff_profile.user
    assert not enrollments_for_user(user, center_a, as_of=future - timedelta(days=1)).exists()
    assert enrollments_for_user(user, center_a, as_of=future).exists()
    assert not enrollments_for_user(
        specialist_a.staff_profile.user, center_a, as_of=future
    ).exists()
    second.valid_to = future + timedelta(days=10)
    second.save()
    assert not enrollments_for_user(user, center_a, as_of=second.valid_to).exists()
    assert not enrollments_for_user(
        specialist_a.staff_profile.user, center_a, as_of=second.valid_to
    ).exists()


@pytest.mark.parametrize("role", ["lead", "helper"])
def test_overlapping_complete_pairs_and_bulk_writers_are_rejected(
    beneficiary_a, specialist_a, center_a, manager, role
):
    helper = make_specialist(center_a, "distinct-helper")
    appoint(beneficiary_a, specialist_a, manager, center_a, helper)
    values = dict(
        beneficiary=beneficiary_a,
        lead=specialist_a,
        helper=helper,
        confirmed_by=manager,
        valid_from=TODAY + timedelta(days=1),
    )
    if role == "lead":
        values["lead"] = make_specialist(center_a, "extra-lead")
    else:
        values["helper"] = make_specialist(center_a, "extra-helper")
    with pytest.raises(ValidationError, match="overlap"):
        BeneficiaryStaffingPeriod.objects.create(**values)
    with pytest.raises(ValidationError):
        BeneficiaryStaffingPeriod.objects.bulk_create([BeneficiaryStaffingPeriod(**values)])
    with pytest.raises(ValidationError):
        beneficiary_a.staffing_periods.update(lead=helper)
    # Bypass Python validation using a historical migration model; DB still protects the pair.
    Period = (
        MigrationExecutor(connection)
        .loader.project_state([("casework", "0016_beneficiary_staffing_periods")])
        .apps.get_model("casework", "BeneficiaryStaffingPeriod")
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        Period.objects.create(
            **{
                key + "_id"
                if key in {"beneficiary", "lead", "helper", "confirmed_by"}
                else key: value.pk if hasattr(value, "pk") else value
                for key, value in values.items()
            }
        )


def test_direct_writer_requires_eligible_pair_and_manager(
    beneficiary_a, specialist_a, specialist_b, center_a, manager
):
    with pytest.raises(PermissionDenied):
        appoint(beneficiary_a, specialist_a, specialist_a.staff_profile.user, center_a)
    with pytest.raises(ValidationError):
        appoint(beneficiary_a, None, manager, center_a)
    with pytest.raises(ValidationError):
        appoint(beneficiary_a, specialist_a, manager, center_a, specialist_a)
    with pytest.raises(ValidationError):
        appoint(beneficiary_a, specialist_b, manager, center_a)
    with pytest.raises(ValidationError):
        BeneficiaryStaffingPeriod.objects.create(
            beneficiary=beneficiary_a,
            lead=specialist_a,
            valid_from=TODAY,
            confirmed_by=specialist_a.staff_profile.user,
        )
    with pytest.raises(ValidationError):
        appoint(beneficiary_a, specialist_a, manager, center_a, on_date=TODAY - timedelta(days=1))


def test_transfer_membership_and_exit_do_not_bypass_placement(
    beneficiary_a, specialist_a, specialist_b, center_a, center_b, manager
):
    appoint(beneficiary_a, specialist_a, manager, center_a)
    enrollment = beneficiary_a.enrollments.get()
    transfer_date = TODAY + timedelta(days=1)
    transfer_enrollment(
        enrollment,
        destination_offering=center_b.service_offerings.get(service=enrollment.service),
        effective_date=transfer_date,
        reason="Synthetic staffing transfer",
        actor=manager,
    )
    assert enrollments_for_user(specialist_a.staff_profile.user, center_a, as_of=TODAY).exists()
    assert not enrollments_for_user(
        specialist_a.staff_profile.user, center_a, as_of=transfer_date
    ).exists()
    assert not enrollments_for_user(
        specialist_b.staff_profile.user, center_b, as_of=transfer_date
    ).exists()
    add_specialist_center(specialist_a, center_b)
    assert enrollments_for_user(
        specialist_a.staff_profile.user, center_b, as_of=transfer_date
    ).exists()
    enrollment.refresh_from_db()
    exit_date = TODAY + timedelta(days=2)
    transition_enrollment(
        enrollment,
        new_state="exited",
        effective_date=exit_date,
        reason="Synthetic staffing exit",
        actor=manager,
    )
    assert enrollments_for_user(
        specialist_a.staff_profile.user, center_b, as_of=transfer_date
    ).exists()
    assert not enrollments_for_user(
        specialist_a.staff_profile.user, center_b, as_of=exit_date
    ).exists()
    assert beneficiary_a.staffing_periods.exists()


def test_frozen_bridge_has_deadline_and_new_evidence_cannot_grant_access(
    beneficiary_a, specialist_a, center_a, manager
):
    assert staffing_needs_review(beneficiary_a, center_a)
    assert beneficiaries_for_user(specialist_a.staff_profile.user, center_a).exists()
    new = make_specialist(center_a, "uncaptured-evidence")
    EnrollmentSpecialistAssignment.objects.create(
        enrollment=beneficiary_a.enrollments.get(), specialist=new, valid_from=TODAY
    )
    assert not beneficiaries_for_user(new.staff_profile.user, center_a).exists()
    with patch(
        "apps.casework.staffing.timezone.localdate", return_value=TODAY + timedelta(days=90)
    ):
        assert not beneficiaries_for_user(specialist_a.staff_profile.user, center_a).exists()
    appoint(beneficiary_a, new, manager, center_a)
    assert beneficiaries_for_user(new.staff_profile.user, center_a).exists()
    assert not beneficiaries_for_user(specialist_a.staff_profile.user, center_a).exists()


def test_helper_casework_and_restricted_fields_files_and_forged_post_denial(
    client, beneficiary_a, specialist_a, center_a, coordinator_a
):
    helper = make_specialist(center_a, "helper-rights")
    appoint(beneficiary_a, specialist_a, coordinator_a, center_a, helper)
    user = helper.staff_profile.user
    visit = make_visit(beneficiary_a, helper, visit_date=TODAY)
    client.force_login(user)
    set_active_center(client, center_a)
    response = client.get(reverse("beneficiary_detail", args=[beneficiary_a.pk]))
    body = response.content.decode()
    assert response.status_code == 200
    assert beneficiary_a.personal_id not in body
    assert beneficiary_a.guardian_parent not in body
    assert (
        client.get(reverse("beneficiary_staffing_update", args=[beneficiary_a.pk])).status_code
        == 403
    )
    assert (
        client.post(
            reverse("beneficiary_staffing_update", args=[beneficiary_a.pk]),
            {"lead": helper.pk, "effective_date": TODAY},
        ).status_code
        == 403
    )
    assert (
        client.post(
            reverse("beneficiary_update", args=[beneficiary_a.pk]),
            {
                "full_name": beneficiary_a.full_name,
                "personal_id": "FORGED",
                "staffing-lead": helper.pk,
                "emergency_contact_name": "FORGED",
            },
        ).status_code
        == 302
    )
    beneficiary_a.refresh_from_db()
    assert beneficiary_a.personal_id != "FORGED"
    assert beneficiary_a.emergency_contact_name != "FORGED"
    assert current_staffing(beneficiary_a).lead_id == specialist_a.pk
    assert client.get(reverse("visit_update", args=[visit.pk])).status_code == 200


def test_labels_and_review_flag_translated(center_a):
    with translation.override("ka"):
        form = BeneficiaryStaffingForm(center=center_a)
        assert str(form.fields["lead"].label) == "მთავარი სპეციალისტი"
        assert str(form.fields["helper"].label) == "დამხმარე სპეციალისტი"
        assert (
            translation.gettext("Specialist assignment needs review")
            != "Specialist assignment needs review"
        )


@pytest.mark.django_db(transaction=True)
def test_simultaneous_staffing_updates_are_serialized(
    beneficiary_a, specialist_a, center_a, manager
):
    if connection.vendor != "postgresql":
        pytest.skip("Staffing row locks require PostgreSQL.")
    helper = make_specialist(center_a, "parallel-lead")
    barrier = Barrier(2)

    def write(specialist):
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            appoint(beneficiary_a, specialist, manager, center_a)
            return "saved"
        except ValidationError:
            return "rejected"
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        result = list(pool.map(write, [specialist_a, helper]))
    assert sorted(result) == ["rejected", "saved"]
    assert beneficiary_a.staffing_periods.count() == 1


def test_same_day_authorship_and_archive_cannot_be_rewritten(
    beneficiary_a, specialist_a, center_a, manager
):
    visit = make_visit(beneficiary_a, specialist_a, visit_date=TODAY)
    other = make_specialist(center_a, "same-day-replacement")
    with pytest.raises(ValidationError, match="Recorded casework"):
        appoint(beneficiary_a, other, manager, center_a)
    appoint(beneficiary_a, other, manager, center_a, on_date=TODAY + timedelta(days=1))
    assert responsible_specialists(visit.enrollment, TODAY).filter(pk=specialist_a.pk).exists()
    old = visit.enrollment.specialist_assignments.get()
    old.assignment_role = "secondary"
    with pytest.raises(ValidationError, match="read-only history"):
        old.save()
    with pytest.raises(ValidationError, match="read-only history"):
        old.delete()
    with pytest.raises(ValidationError, match="read-only history"):
        visit.enrollment.specialist_assignments.update(specialist=other)


def test_confirmed_helper_can_author_all_records_but_not_receive_beneficiary_files(
    client, beneficiary_a, specialist_a, center_a, manager, settings, tmp_path
):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.casework.models import AttachmentParentType, PrivateAttachment

    from .factories import make_assessment

    settings.PRIVATE_MEDIA_ROOT = tmp_path / "private"
    helper = make_specialist(center_a, "helper-all-records")
    appoint(beneficiary_a, specialist_a, manager, center_a, helper)
    # Factories use historical dates by default; the person-level appointment starts today.
    with patch("apps.casework.staffing.timezone.localdate", return_value=TODAY):
        assessment = make_assessment(beneficiary_a, helper, assessment_date=TODAY)
    from apps.casework.models import IndividualPlan

    plan = IndividualPlan.objects.create(
        enrollment=beneficiary_a.enrollments.get(),
        beneficiary=beneficiary_a,
        center=center_a,
        specialist=helper,
        plan_start_date=TODAY,
        plan_end_date=TODAY + timedelta(days=30),
        status="draft",
    )
    visit = make_visit(beneficiary_a, helper, visit_date=TODAY)
    restricted = PrivateAttachment.objects.create(
        parent_type=AttachmentParentType.BENEFICIARY,
        parent_id=beneficiary_a.pk,
        center=center_a,
        file=SimpleUploadedFile(
            "synthetic-restricted.pdf",
            b"%PDF-1.7\nSynthetic evidence",
            content_type="application/pdf",
        ),
        original_filename="synthetic-restricted.pdf",
        uploaded_by=manager,
    )
    ordinary = PrivateAttachment.objects.create(
        parent_type=AttachmentParentType.SERVICE_VISIT,
        parent_id=visit.pk,
        center=center_a,
        file=SimpleUploadedFile(
            "synthetic-visit.pdf", b"%PDF-1.7\nSynthetic visit", content_type="application/pdf"
        ),
        original_filename="synthetic-visit.pdf",
        uploaded_by=manager,
    )
    client.force_login(helper.staff_profile.user)
    set_active_center(client, center_a)
    for route, obj in (
        ("visit_update", visit),
        ("assessment_update", assessment),
        ("plan_update", plan),
    ):
        assert client.get(reverse(route, args=[obj.pk])).status_code == 200
    assert client.get(reverse("attachment_download", args=[restricted.pk])).status_code == 404
    response = client.get(reverse("attachment_download", args=[ordinary.pk]))
    assert response.status_code == 200
    helper.staff_profile.user.is_active = False
    helper.staff_profile.user.save()
    assert not enrollments_for_user(helper.staff_profile.user, center_a).exists()
    response.close()


@pytest.mark.django_db(transaction=True)
def test_database_serializes_concurrent_writers_that_bypass_forms(
    beneficiary_a, specialist_a, center_a, manager
):
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL exclusion constraint requires PostgreSQL.")
    other = make_specialist(center_a, "raw-concurrent")
    Period = (
        MigrationExecutor(connection)
        .loader.project_state([("casework", "0016_beneficiary_staffing_periods")])
        .apps.get_model("casework", "BeneficiaryStaffingPeriod")
    )
    barrier = Barrier(2)

    def write(profile):
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            Period.objects.create(
                beneficiary_id=beneficiary_a.pk,
                lead_id=profile.pk,
                confirmed_by_id=manager.pk,
                valid_from=TODAY,
            )
            return "saved"
        except IntegrityError:
            return "rejected"
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(write, [specialist_a, other])) == ["rejected", "saved"]
    assert beneficiary_a.staffing_periods.count() == 1


def test_future_confirmation_does_not_activate_uncaptured_evidence_for_new_work(
    beneficiary_a, specialist_a, center_a, manager
):
    outsider = make_specialist(center_a, "uncaptured-before-future")
    enrollment = beneficiary_a.enrollments.get()
    EnrollmentSpecialistAssignment.objects.create(
        enrollment=enrollment, specialist=outsider, valid_from=TODAY
    )
    appoint(beneficiary_a, specialist_a, manager, center_a, on_date=TODAY + timedelta(days=7))
    assert not responsible_specialists(enrollment, TODAY).filter(pk=outsider.pk).exists()
    assert (
        not responsible_specialists(enrollment, TODAY + timedelta(days=1))
        .filter(pk=outsider.pk)
        .exists()
    )
    assert responsible_specialists(enrollment, TODAY).filter(pk=specialist_a.pk).exists()


def test_staffing_replacement_before_scheduled_exit_uses_the_effective_date(
    beneficiary_a, specialist_a, center_a, manager
):
    appoint(beneficiary_a, specialist_a, manager, center_a)
    enrollment = beneficiary_a.enrollments.get()
    transition_enrollment(
        enrollment,
        new_state="exited",
        effective_date=TODAY + timedelta(days=7),
        reason="Synthetic future staffing exit",
        actor=manager,
    )
    other = make_specialist(center_a, "lead-before-scheduled-exit")
    pair = appoint(beneficiary_a, other, manager, center_a, on_date=TODAY + timedelta(days=1))
    assert pair.lead_id == other.pk
    assert enrollments_for_user(
        other.staff_profile.user, center_a, as_of=TODAY + timedelta(days=1)
    ).exists()
    assert not enrollments_for_user(
        other.staff_profile.user, center_a, as_of=TODAY + timedelta(days=7)
    ).exists()


def test_legacy_bridge_cannot_follow_a_transfer_to_a_new_center(
    beneficiary_a, specialist_a, center_a, center_b, manager
):
    add_specialist_center(specialist_a, center_b)
    enrollment = beneficiary_a.enrollments.get()
    transfer_date = TODAY + timedelta(days=1)
    transfer_enrollment(
        enrollment,
        destination_offering=center_b.service_offerings.get(service=enrollment.service),
        effective_date=transfer_date,
        reason="Synthetic legacy bridge transfer",
        actor=manager,
    )
    assert enrollments_for_user(specialist_a.staff_profile.user, center_a, as_of=TODAY).exists()
    assert not enrollments_for_user(
        specialist_a.staff_profile.user, center_b, as_of=transfer_date
    ).exists()

    # Returning to the original center is a new placement, outside the captured bridge.
    transfer_enrollment(
        enrollment,
        destination_offering=center_a.service_offerings.get(service=enrollment.service),
        effective_date=transfer_date + timedelta(days=1),
        reason="Synthetic return to original center",
        actor=manager,
    )
    assert not enrollments_for_user(
        specialist_a.staff_profile.user, center_a, as_of=transfer_date + timedelta(days=1)
    ).exists()


def historical_helper_visit_form(person, lead, helper, center):
    capture_legacy_assignment(
        EnrollmentSpecialistAssignment.objects.create(
            enrollment=person.enrollments.get(),
            specialist=helper,
            assignment_role="secondary",
            valid_from=TODAY - timedelta(days=20),
        )
    )
    visit = make_visit(person, helper, visit_date=TODAY - timedelta(days=1))
    form = ServiceVisitForm(
        data={
            "enrollment": visit.enrollment_id,
            "specialist": helper.pk,
            "visit_date": visit.visit_date,
            "activity": visit.activity_id,
            "delivery_location": visit.delivery_location_id,
            "participation_format": visit.participation_format,
            "status": visit.status,
            "service_units": visit.service_units,
            "duration_minutes": visit.duration_minutes,
            "participants": visit.participants,
            "notes": "Changed after validation",
            "correction_reason": "Synthetic correction",
        },
        instance=visit,
        user=lead.staff_profile.user,
        center=center,
    )
    assert form.is_valid(), form.errors
    return form


@pytest.mark.parametrize("commit", [True, False])
def test_actor_reassignment_between_validation_and_save_cannot_change_helper_history(
    beneficiary_a, specialist_a, center_a, manager, commit
):
    helper = make_specialist(center_a, "stale-form-helper")
    form = historical_helper_visit_form(beneficiary_a, specialist_a, helper, center_a)
    original_notes = type(form.instance).objects.get(pk=form.instance.pk).notes
    draft = form.save(commit=False) if not commit else None
    new = make_specialist(center_a, "stale-form-new-lead")
    appoint(beneficiary_a, new, manager, center_a, helper)
    # The helper's historic responsibility still passes model validation; the actor lost access.
    assert (
        responsible_specialists(form.instance.enrollment, form.instance.visit_date)
        .filter(pk=helper.pk)
        .exists()
    )
    with pytest.raises(PermissionDenied):
        form.save() if commit else draft.save()
    form.instance.refresh_from_db()
    assert form.instance.notes == original_notes


@pytest.mark.parametrize("inactive", ["user", "staff", "membership"])
def test_actor_eligibility_is_rechecked_after_form_validation(
    beneficiary_a, specialist_a, center_a, inactive
):
    helper = make_specialist(center_a, "deactivated-actor-helper")
    form = historical_helper_visit_form(beneficiary_a, specialist_a, helper, center_a)
    if inactive == "user":
        specialist_a.staff_profile.user.is_active = False
        specialist_a.staff_profile.user.save()
    elif inactive == "staff":
        specialist_a.staff_profile.status = "inactive"
        specialist_a.staff_profile.save()
    else:
        specialist_a.center_assignments.all().delete()
    with pytest.raises(PermissionDenied):
        form.save()


def test_legacy_joint_roles_are_not_relabelled_as_confirmed_leads(
    beneficiary_a, specialist_a, center_a
):
    joint = make_specialist(center_a, "legacy-joint-role")
    capture_legacy_assignment(
        EnrollmentSpecialistAssignment.objects.create(
            enrollment=beneficiary_a.enrollments.get(), specialist=joint, valid_from=TODAY
        )
    )
    rows = responsibility_rows(beneficiary_a.enrollments.all(), TODAY)
    assert len(rows) == 2
    assert {str(row.get_assignment_role_display()) for row in rows} == {"Primary"}
    assert current_staffing(beneficiary_a) is None


def test_database_preserves_staffing_history_even_for_a_raw_delete(
    beneficiary_a, specialist_a, center_a, manager
):
    if connection.vendor != "postgresql":
        pytest.skip("The database history deletion guard requires PostgreSQL.")
    period = appoint(beneficiary_a, specialist_a, manager, center_a)
    Period = (
        MigrationExecutor(connection)
        .loader.project_state([("casework", "0016_beneficiary_staffing_periods")])
        .apps.get_model("casework", "BeneficiaryStaffingPeriod")
    )
    from django.db import DatabaseError

    with pytest.raises(DatabaseError), transaction.atomic():
        Period.objects.filter(pk=period.pk).delete()
    assert beneficiary_a.staffing_periods.filter(pk=period.pk).exists()


@pytest.mark.django_db(transaction=True)
def test_reassignment_serializes_with_an_already_validated_casework_write(
    beneficiary_a, specialist_a, center_a, manager
):
    if connection.vendor != "postgresql":
        pytest.skip("The casework and staffing shared lock requires PostgreSQL.")
    helper = make_specialist(center_a, "concurrent-actor-helper")
    form = historical_helper_visit_form(beneficiary_a, specialist_a, helper, center_a)
    draft = form.save(commit=False)
    new = make_specialist(center_a, "concurrent-actor-new-lead")
    barrier = Barrier(2)

    def save_casework():
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            draft.save()
            return "saved"
        except PermissionDenied:
            return "denied"
        finally:
            close_old_connections()

    from apps.casework.models import Beneficiary

    with ThreadPoolExecutor(max_workers=1) as pool:
        with transaction.atomic():
            Beneficiary.objects.select_for_update().get(pk=beneficiary_a.pk)
            future = pool.submit(save_casework)
            barrier.wait(timeout=10)
            appoint(beneficiary_a, new, manager, center_a, helper)
        assert future.result(timeout=10) == "denied"
    draft.refresh_from_db()
    assert draft.notes != "Changed after validation"


@pytest.mark.parametrize("operation", ["upload", "delete"])
def test_attachment_changes_recheck_staffing_after_the_initial_parent_lookup(
    beneficiary_a, specialist_a, center_a, manager, settings, tmp_path, operation
):
    from django.core.files.uploadedfile import SimpleUploadedFile
    from django.http import Http404

    from apps.casework import private_attachments
    from apps.casework.models import AttachmentParentType, PrivateAttachment

    settings.PRIVATE_MEDIA_ROOT = tmp_path / "private"
    helper = make_specialist(center_a, "stale-file-helper")
    form = historical_helper_visit_form(beneficiary_a, specialist_a, helper, center_a)
    visit = form.instance
    existing = PrivateAttachment.objects.create(
        parent_type=AttachmentParentType.SERVICE_VISIT,
        parent_id=visit.pk,
        center=center_a,
        file=SimpleUploadedFile("existing.pdf", b"%PDF-1.7\nSynthetic existing file"),
        original_filename="existing.pdf",
        uploaded_by=manager,
    )
    workflow = private_attachments.case_attachments(specialist_a.staff_profile.user, center_a)
    new = make_specialist(center_a, "stale-file-new-lead")
    original = private_attachments._authorize_parent
    looked_up = False

    def reassign_after_lookup(*args, **kwargs):
        nonlocal looked_up
        parent = original(*args, **kwargs)
        if not looked_up:
            looked_up = True
            appoint(beneficiary_a, new, manager, center_a, helper)
        return parent

    with patch.object(private_attachments, "_authorize_parent", side_effect=reassign_after_lookup):
        with pytest.raises(Http404):
            if operation == "upload":
                workflow.upload(
                    AttachmentParentType.SERVICE_VISIT,
                    visit.pk,
                    data={},
                    files={"file": SimpleUploadedFile("new.pdf", b"%PDF-1.7\nSynthetic new file")},
                )
            else:
                workflow.delete(existing.pk)
    assert PrivateAttachment.objects.filter(parent_id=visit.pk).count() == 1
    assert existing.file.storage.exists(existing.file.name)
    assert current_staffing(beneficiary_a).lead_id == new.pk
