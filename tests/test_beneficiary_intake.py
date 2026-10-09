from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.urls import reverse
from django.utils import timezone, translation

from apps.audit.models import AuditEvent
from apps.casework.forms import BeneficiaryIntakeForm
from apps.casework.intake import save_beneficiary_intake
from apps.casework.intake_schema import INTAKE_FIELDS, MULTI_CHOICES
from apps.casework.models import (
    Beneficiary,
    BeneficiaryIntake,
    BeneficiaryIntakeRevision,
    BeneficiaryStaffingPeriod,
    PrivateAttachment,
)
from apps.casework.services import replace_beneficiary_staffing
from apps.centers.models import StaffProfile

from .factories import add_specialist_center, make_plan, make_specialist, set_active_center

pytestmark = pytest.mark.django_db


@pytest.fixture
def pair(beneficiary_a, specialist_a, center_a, manager):
    helper = make_specialist(center_a, "intake-helper")
    replace_beneficiary_staffing(
        beneficiary=beneficiary_a,
        lead=specialist_a,
        helper=helper,
        effective_date=timezone.localdate(),
        center=center_a,
        actor=manager,
    )
    return specialist_a, helper


def answers():
    return {
        "health_condition": "  Synthetic condition\nOriginal text  ",
        "general_conditions": ["stable", "severe", "monitoring"],
        "health_problems": ["diabetes", "dementia", "other"],
        "health_problems_other": "  Synthetic additional problem  ",
        "functional_conditions": ["independent", "bedbound", "daily_assistance"],
        "cognitive_conditions": ["oriented", "dementia", "other"],
        "cognitive_other": "Synthetic cognitive narrative",
        "allergies": "yes",
        "allergies_description": "Synthetic allergy",
        "current_medications": "Synthetic medication\nSecond line",
        "treating_doctor_name": "Synthetic doctor",
        "treating_doctor_contact": "+995 555 000 222, doctor@example.invalid",
        "other_services": "yes",
        "other_services_details": "Synthetic support\nSecond line",
        "living_situation": "other",
        "living_situation_notes": "Synthetic arrangement",
        "service_consent": "no",
        "care_sharing_consent": "yes",
        "confidentiality_consent": "",
        "media_consent": "decline",
        "initial_care_services": list(dict(MULTI_CHOICES["initial_care_services"])),
    }


def post_values(values):
    return {"intake-present": "1", **{f"intake-{key}": value for key, value in values.items()}}


@pytest.mark.parametrize("language", ["en", "ka"])
@pytest.mark.parametrize("role", ["manager", "coordinator_a"])
def test_all_fields_create_edit_detail_and_clear(
    client, request, center_a, specialist_a, language, role
):
    user = request.getfixturevalue(role)
    client.force_login(user)
    set_active_center(client, center_a)
    data = {
        "full_name": "Synthetic intake person",
        "enrollment-offering": str(center_a.service_offerings.get(service__code="HOME-CARE").pk),
        "enrollment-status": "active",
        "enrollment-start_date": timezone.localdate().isoformat(),
        "staffing-lead": str(specialist_a.pk),
        "staffing-effective_date": timezone.localdate().isoformat(),
        **post_values(answers()),
    }
    with translation.override(language):
        response = client.post(reverse("beneficiary_create"), data)
        assert response.status_code == 302, (
            response.context and response.context["intake_form"].errors
        )
        person = Beneficiary.objects.get(full_name=data["full_name"])
        record = person.intake
        for key, value in answers().items():
            assert getattr(record, key) == value
        assert person.diagnoses.count() == person.plans.count() == person.visits.count() == 0
        assert person.enrollments.count() == 1
        for route in ("beneficiary_update", "beneficiary_intake_update", "beneficiary_detail"):
            response = client.get(reverse(route, args=[person.pk]))
            assert response.status_code == 200
            body = response.content.decode()
            assert ("Health information" if language == "en" else "ჯანმრთელობის ინფორმაცია") in body
            assert ("I do not agree" if language == "en" else "მე არ ვეთანხმები") in body
            assert "Synthetic condition" in body
            assert "doctor@example.invalid" in body
        for decision in ("no", ""):
            updated = answers() | {
                "allergies": decision,
                "other_services": decision,
                "health_problems": ["chronic"],
                "cognitive_conditions": ["memory"],
            }
            response = client.post(
                reverse("beneficiary_intake_update", args=[person.pk]), post_values(updated)
            )
            assert response.status_code == 302
            record.refresh_from_db()
            assert record.allergies == decision
            assert record.allergies_description == record.other_services_details == ""
            assert record.health_problems_other == record.cognitive_other == ""
        response = client.post(
            reverse("beneficiary_intake_update", args=[person.pk]), {"intake-present": "1"}
        )
        assert response.status_code == 302
        record.refresh_from_db()
        assert all(
            getattr(record, key) == ([] if key in MULTI_CHOICES else "") for key in INTAKE_FIELDS
        )
        assert record.revisions.count() == 4
        assert (
            record.revisions.first().before_values["health_condition"]
            == answers()["health_condition"]
        )
        assert all(
            event.metadata == {}
            for event in AuditEvent.objects.filter(target_type="BeneficiaryIntake")
        )


@pytest.mark.parametrize("language", ["en", "ka"])
@pytest.mark.parametrize(
    "choice,detail,value",
    [
        ("health_problems", "health_problems_other", ["other"]),
        ("cognitive_conditions", "cognitive_other", ["other"]),
        ("allergies", "allergies_description", "yes"),
        ("other_services", "other_services_details", "yes"),
        ("living_situation", "living_situation_notes", "other"),
    ],
)
def test_conditional_validation_both_form_and_model(
    manager, center_a, beneficiary_a, language, choice, detail, value
):
    with translation.override(language):
        form = BeneficiaryIntakeForm(
            post_values({choice: value, detail: "  "}),
            user=manager,
            center=center_a,
            beneficiary=beneficiary_a,
            prefix="intake",
        )
        assert not form.is_valid()
        assert detail in form.errors
        assert ("Please provide details" if language == "en" else "გთხოვთ, მიუთითოთ") in str(
            form.errors
        )
        record = BeneficiaryIntake(beneficiary=beneficiary_a, **{choice: value})
        with pytest.raises(ValidationError) as exc:
            record.save()
        assert detail in exc.value.message_dict


@pytest.mark.parametrize(
    "field",
    list(MULTI_CHOICES)
    + [
        "allergies",
        "other_services",
        "living_situation",
        "service_consent",
        "care_sharing_consent",
        "confidentiality_consent",
        "media_consent",
    ],
)
@pytest.mark.parametrize("language", ["en", "ka"])
def test_invalid_codes_rejected(manager, center_a, beneficiary_a, field, language):
    with translation.override(language):
        value = ["forged"] if field in MULTI_CHOICES else "forged"
        form = BeneficiaryIntakeForm(
            post_values({field: value}),
            user=manager,
            center=center_a,
            beneficiary=beneficiary_a,
            prefix="intake",
        )
        assert not form.is_valid() and field in form.errors
        with pytest.raises(ValidationError):
            BeneficiaryIntake(beneficiary=beneficiary_a, **{field: value}).save()


@pytest.mark.parametrize("value", ["stable", {}, ["stable", "stable"], [False], [None]])
def test_malformed_json_choices_are_rejected(beneficiary_a, value):
    with pytest.raises(ValidationError):
        BeneficiaryIntake(beneficiary=beneficiary_a, general_conditions=value).save()


@pytest.mark.parametrize("role", ["lead", "helper"])
@pytest.mark.parametrize("language", ["en", "ka"])
def test_confirmed_specialist_projection_and_forged_post(
    client, manager, center_a, beneficiary_a, pair, role, language
):
    save_beneficiary_intake(
        beneficiary=beneficiary_a, actor=manager, center=center_a, values=answers()
    )
    user = pair[0 if role == "lead" else 1].staff_profile.user
    client.force_login(user)
    set_active_center(client, center_a)
    original = beneficiary_a.intake
    with translation.override(language):
        for route in ("beneficiary_detail", "beneficiary_intake_update", "beneficiary_update"):
            response = client.get(reverse(route, args=[beneficiary_a.pk]))
            assert response.status_code == 200
            body = response.content.decode()
            assert "Synthetic condition" in body
            for forbidden in (
                "emergency_contact",
                "guardian_parent",
                "personal_id",
                "service_consent",
                "media_consent",
            ):
                assert forbidden not in body
            assert "Synthetic address" not in body and "Synthetic guardian" not in body
            assert (
                "Consent and confidentiality"
                if language == "en"
                else "თანხმობა და კონფიდენციალურობა"
            ) not in body
        response = client.post(
            reverse("beneficiary_intake_update", args=[beneficiary_a.pk]),
            post_values(
                answers()
                | {
                    "health_condition": "Synthetic specialist update",
                    "service_consent": "yes",
                    "media_consent": "agree",
                }
            )
            | {"personal_id": "FORGED", "emergency_contact_name": "FORGED"},
        )
        assert response.status_code == 302
        original.refresh_from_db()
        assert original.health_condition == "Synthetic specialist update"
        assert original.service_consent == "no" and original.media_consent == "decline"
        assert "service_consent" not in original.revisions.first().after_values
        beneficiary_a.refresh_from_db()
        assert beneficiary_a.personal_id != "FORGED" and beneficiary_a.emergency_contact_name == ""
        assert (
            client.get(
                reverse("attachment_upload", args=["beneficiary", beneficiary_a.pk])
            ).status_code
            == 404
        )


@pytest.mark.parametrize(
    "denial",
    ["unassigned", "expired", "inactive_user", "inactive_staff", "membership", "cross_center"],
)
def test_specialist_denials(client, manager, center_a, center_b, beneficiary_a, pair, denial):
    lead, helper = pair
    user = lead.staff_profile.user
    if denial == "unassigned":
        user = make_specialist(center_a, "unassigned").staff_profile.user
    elif denial == "expired":
        future = timezone.localdate() + timedelta(days=2)
        with patch("django.utils.timezone.localdate", return_value=future):
            replace_beneficiary_staffing(
                beneficiary=beneficiary_a,
                lead=helper,
                helper=None,
                effective_date=future,
                center=center_a,
                actor=manager,
            )
        # Access should be absent at the effective replacement date.
        date_context = patch("django.utils.timezone.localdate", return_value=future)
    elif denial == "inactive_user":
        type(user).objects.filter(pk=user.pk).update(is_active=False)
    elif denial == "inactive_staff":
        StaffProfile.objects.filter(pk=lead.staff_profile_id).update(
            status=StaffProfile.Status.INACTIVE
        )
    elif denial == "membership":
        lead.center_assignments.all().delete()
    if denial == "cross_center":
        add_specialist_center(lead, center_b)
    client.force_login(user)
    set_active_center(client, center_b if denial == "cross_center" else center_a)
    if denial != "expired":
        from contextlib import nullcontext

        date_context = nullcontext()
    with date_context:
        response = client.post(
            reverse("beneficiary_intake_update", args=[beneficiary_a.pk]), post_values(answers())
        )
    assert response.status_code in (302, 403, 404)
    assert not BeneficiaryIntake.objects.filter(beneficiary=beneficiary_a).exists()


def test_legacy_bridge_does_not_expand_health_or_consent(
    client, specialist_a, center_a, beneficiary_a
):
    client.force_login(specialist_a.staff_profile.user)
    set_active_center(client, center_a)
    response = client.get(reverse("beneficiary_intake_update", args=[beneficiary_a.pk]))
    assert response.status_code == 200
    assert set(response.context["intake_form"].fields) == {"initial_care_services"}


@pytest.mark.parametrize("change", ["account", "staffing", "transfer"])
def test_save_rechecks_after_form_validation(
    manager, center_a, center_b, beneficiary_a, pair, change
):
    lead, helper = pair
    user = lead.staff_profile.user
    form = BeneficiaryIntakeForm(
        post_values(answers()),
        user=user,
        center=center_a,
        beneficiary=beneficiary_a,
        prefix="intake",
    )
    assert form.is_valid(), form.errors
    if change == "account":
        type(user).objects.filter(pk=user.pk).update(is_active=False)
    elif change == "staffing":
        tomorrow = timezone.localdate() + timedelta(days=1)
        with patch("django.utils.timezone.localdate", return_value=tomorrow):
            replace_beneficiary_staffing(
                beneficiary=beneficiary_a,
                lead=helper,
                helper=None,
                effective_date=tomorrow,
                center=center_a,
                actor=manager,
            )
        with (
            patch("django.utils.timezone.localdate", return_value=tomorrow),
            pytest.raises(PermissionDenied),
        ):
            form.save()
        return
    else:
        from apps.casework.services import transfer_enrollment

        destination = center_b.service_offerings.get(
            service=beneficiary_a.enrollments.first().service
        )
        transfer_enrollment(
            enrollment=beneficiary_a.enrollments.first(),
            destination_offering=destination,
            reason="Synthetic transfer",
            effective_date=timezone.localdate(),
            actor=manager,
        )
    with pytest.raises(PermissionDenied):
        form.save()
    assert not BeneficiaryIntake.objects.exists()


@pytest.mark.parametrize("invalid", ["intake", "enrollment", "attachment", "late_failure"])
def test_atomic_creation_no_person_intake_staffing_or_file(
    client, manager, center_a, specialist_a, settings, tmp_path, invalid
):
    settings.PRIVATE_MEDIA_ROOT = tmp_path
    client.force_login(manager)
    set_active_center(client, center_a)
    data = {
        "full_name": "Synthetic rejected intake",
        **post_values(answers()),
        "enrollment-offering": str(center_a.service_offerings.get(service__code="HOME-CARE").pk),
        "enrollment-status": "active",
        "enrollment-start_date": timezone.localdate().isoformat(),
        "staffing-lead": str(specialist_a.pk),
        "staffing-effective_date": timezone.localdate().isoformat(),
        "attachment-file": SimpleUploadedFile("synthetic.pdf", b"%PDF-1.4\nsynthetic"),
    }
    if invalid == "intake":
        data["intake-allergies_description"] = ""
    elif invalid == "enrollment":
        data["enrollment-first_service_date"] = "2020-01-01"
    elif invalid == "attachment":
        data["attachment-file"] = SimpleUploadedFile("synthetic.exe", b"not allowed")
    from contextlib import nullcontext

    original_save = PrivateAttachment.save

    def fail_after_file_save(attachment, *args, **kwargs):
        original_save(attachment, *args, **kwargs)
        raise ValidationError("Synthetic failure after file save")

    context = (
        patch.object(PrivateAttachment, "save", fail_after_file_save)
        if invalid == "late_failure"
        else nullcontext()
    )
    with context:
        response = client.post(reverse("beneficiary_create"), data)
    assert response.status_code == 200
    assert "Synthetic condition" in response.content.decode()
    assert not Beneficiary.objects.filter(full_name=data["full_name"]).exists()
    assert not BeneficiaryIntake.objects.exists() and not BeneficiaryIntakeRevision.objects.exists()
    assert not BeneficiaryStaffingPeriod.objects.exists() and not PrivateAttachment.objects.exists()
    assert not list(tmp_path.rglob("*.pdf"))


def test_invalid_intake_rolls_back_person_edit_and_omitted_form_preserves_intake(
    client, manager, center_a, beneficiary_a
):
    record = save_beneficiary_intake(
        beneficiary=beneficiary_a, actor=manager, center=center_a, values=answers()
    )
    client.force_login(manager)
    set_active_center(client, center_a)
    response = client.post(
        reverse("beneficiary_update", args=[beneficiary_a.pk]),
        {"full_name": "Synthetic rejected rename", **post_values({"allergies": "yes"})},
    )
    assert response.status_code == 200
    beneficiary_a.refresh_from_db()
    assert beneficiary_a.full_name != "Synthetic rejected rename"
    record.refresh_from_db()
    assert record.health_condition == answers()["health_condition"]
    response = client.post(
        reverse("beneficiary_update", args=[beneficiary_a.pk]),
        {"full_name": beneficiary_a.full_name},
    )
    assert response.status_code == 302
    record.refresh_from_db()
    assert (
        record.health_condition == answers()["health_condition"] and record.service_consent == "no"
    )


def test_blank_existing_person_and_formal_plan_preserved(
    client, manager, center_a, beneficiary_a, specialist_a
):
    plan = make_plan(beneficiary_a, specialist_a)
    before = dict(type(plan).objects.filter(pk=plan.pk).values().get())
    client.force_login(manager)
    set_active_center(client, center_a)
    response = client.get(reverse("beneficiary_detail", args=[beneficiary_a.pk]))
    assert (
        response.status_code == 200
        and "No intake information recorded." in response.content.decode()
    )
    assert not BeneficiaryIntake.objects.exists()
    save_beneficiary_intake(
        beneficiary=beneficiary_a, actor=manager, center=center_a, values=answers()
    )
    assert type(plan).objects.filter(pk=plan.pk).values().get() == before
    assert not beneficiary_a.diagnoses.exists()


def test_revision_is_restricted_append_only(manager, center_a, beneficiary_a):
    record = save_beneficiary_intake(
        beneficiary=beneficiary_a, actor=manager, center=center_a, values=answers()
    )
    revision = record.revisions.get()
    with pytest.raises(ValidationError):
        revision.save()
    with pytest.raises(TypeError):
        revision.delete()


@pytest.mark.django_db(transaction=True)
def test_intake_schema_migration_leaves_existing_people_unrecorded():
    executor = MigrationExecutor(connection)
    previous = [("casework", "0018_staffing_database_guards")]
    target = [("casework", "0019_beneficiary_intake")]
    leaves = executor.loader.graph.leaf_nodes()
    try:
        executor.migrate(previous)
        apps = executor.loader.project_state(previous).apps
        center = apps.get_model("centers", "Center").objects.create(
            code="INTAKE-MIG", name="Synthetic migration center"
        )
        person = apps.get_model("casework", "Beneficiary").objects.create(
            center=center,
            beneficiary_code="INTAKE-MIG_B001",
            full_name="Synthetic migration person",
        )
        MigrationExecutor(connection).migrate(target)
        assert Beneficiary.objects.filter(pk=person.pk).exists()
        assert not BeneficiaryIntake.objects.exists()
        record = BeneficiaryIntake.objects.create(beneficiary_id=person.pk)
        assert all(
            getattr(record, key) == ([] if key in MULTI_CHOICES else "") for key in INTAKE_FIELDS
        )
        MigrationExecutor(connection).migrate(previous)
        assert Beneficiary.objects.filter(pk=person.pk).exists()
    finally:
        MigrationExecutor(connection).migrate(leaves)


@pytest.mark.parametrize("role", ["coordinator_a", "central_hr", "specialist_b"])
def test_other_center_and_unprivileged_role_denied(client, request, center_a, beneficiary_a, role):
    actor = request.getfixturevalue(role)
    user = actor.staff_profile.user if role == "specialist_b" else actor
    client.force_login(user)
    set_active_center(client, center_a)
    if role == "coordinator_a":
        StaffProfile.objects.filter(user=user).update(status=StaffProfile.Status.INACTIVE)
    response = client.post(
        reverse("beneficiary_intake_update", args=[beneficiary_a.pk]), post_values(answers())
    )
    assert response.status_code in (403, 404)
    assert not BeneficiaryIntake.objects.exists()


def test_direct_service_rejects_forged_consent_and_empty_unauthorized_request(
    center_a, beneficiary_a, pair
):
    lead, helper = pair
    with pytest.raises(PermissionDenied):
        save_beneficiary_intake(
            beneficiary=beneficiary_a,
            center=center_a,
            actor=lead.staff_profile.user,
            values={"media_consent": "agree"},
        )
    outsider = make_specialist(center_a, "intake-outsider").staff_profile.user
    with pytest.raises(PermissionDenied):
        save_beneficiary_intake(
            beneficiary=beneficiary_a, center=center_a, actor=outsider, values={}
        )
    assert not BeneficiaryIntake.objects.exists()


def test_intake_is_excluded_from_lists_reports_exports_and_search(
    client, manager, center_a, beneficiary_a, specialist_a
):
    from apps.core.views import REPORT_TYPES

    from .factories import make_assessment, make_visit

    marker = "SYNTHETIC-INTAKE-PRIVATE-NARRATIVE"
    make_visit(beneficiary_a, specialist_a)
    make_assessment(beneficiary_a, specialist_a)
    make_plan(beneficiary_a, specialist_a)
    save_beneficiary_intake(
        beneficiary=beneficiary_a,
        center=center_a,
        actor=manager,
        values={
            "health_condition": marker,
            "treating_doctor_contact": "doctor-private@example.invalid",
        },
    )
    client.force_login(manager)
    set_active_center(client, center_a)
    for route in ("dashboard", "beneficiary_list"):
        response = client.get(reverse(route))
        assert (
            marker not in response.content.decode()
            and "doctor-private@example.invalid" not in response.content.decode()
        )
    response = client.get(reverse("beneficiary_list"), {"q": marker})
    assert response.context["page_obj"].paginator.count == 0
    for report in REPORT_TYPES:
        for route in ("reports", "report_export"):
            response = client.get(reverse(route), {"type": report})
            assert response.status_code == 200
            assert marker not in response.content.decode()


def test_imported_evidence_is_preserved_and_never_inferred(
    client, manager, center_a, beneficiary_a
):
    from apps.casework.models import BeneficiaryWorkbookImport

    evidence = BeneficiaryWorkbookImport.objects.create(
        beneficiary=beneficiary_a,
        source_digest="a" * 64,
        source_row=1,
        source_values={"health": "Synthetic source condition", "doctor": "Synthetic source doctor"},
        review_issues=["Synthetic review flag"],
    )
    before = BeneficiaryWorkbookImport.objects.filter(pk=evidence.pk).values().get()
    client.force_login(manager)
    set_active_center(client, center_a)
    response = client.get(reverse("beneficiary_update", args=[beneficiary_a.pk]))
    assert response.context["intake_form"].initial == {}
    save_beneficiary_intake(
        beneficiary=beneficiary_a, center=center_a, actor=manager, values=answers()
    )
    assert BeneficiaryWorkbookImport.objects.filter(pk=evidence.pk).values().get() == before


def test_all_new_strings_have_georgian_translations(manager, center_a, beneficiary_a):
    from django.utils.translation import gettext

    from apps.casework.intake_schema import MULTI_CHOICES

    with translation.override("en"):
        english_form = BeneficiaryIntakeForm(
            user=manager, center=center_a, beneficiary=beneficiary_a
        )
        labels = {name: str(field.label) for name, field in english_form.fields.items()}
        options_en = {
            name: [str(label) for _code, label in options]
            for name, options in MULTI_CHOICES.items()
        }
    with translation.override("ka"):
        form = BeneficiaryIntakeForm(user=manager, center=center_a, beneficiary=beneficiary_a)
        assert all(str(field.label) != labels[name] for name, field in form.fields.items())
        for name, options in MULTI_CHOICES.items():
            assert all(
                str(label) != english
                for (_code, label), english in zip(options, options_en[name], strict=True)
            )
        assert dict(form.fields["allergies"].choices)["yes"] == "კი"
        assert dict(form.fields["other_services"].choices)["yes"] == "დიახ"
        assert gettext("Future") == "სამომავლო"


@pytest.mark.django_db(transaction=True)
def test_intake_save_serializes_with_staffing_replacement(center_a, beneficiary_a, manager, pair):
    if connection.vendor != "postgresql":
        pytest.skip("Intake and staffing row locking requires PostgreSQL.")
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from django.db import close_old_connections, transaction

    lead, helper = pair
    form = BeneficiaryIntakeForm(
        post_values({"health_condition": "Synthetic racing update"}),
        user=lead.staff_profile.user,
        center=center_a,
        beneficiary=beneficiary_a,
        prefix="intake",
    )
    assert form.is_valid()
    barrier = Barrier(2)

    def write_intake():
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            form.save()
            return "saved"
        except PermissionDenied:
            return "denied"
        finally:
            close_old_connections()

    tomorrow = timezone.localdate() + timedelta(days=1)
    with patch("django.utils.timezone.localdate", return_value=tomorrow):
        with ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic():
                Beneficiary.objects.select_for_update().get(pk=beneficiary_a.pk)
                future = pool.submit(write_intake)
                barrier.wait(timeout=10)
                replace_beneficiary_staffing(
                    beneficiary=beneficiary_a,
                    lead=helper,
                    helper=None,
                    effective_date=tomorrow,
                    center=center_a,
                    actor=manager,
                )
            assert future.result(timeout=10) == "denied"
    assert not BeneficiaryIntake.objects.exists()


def test_partial_service_clear_keeps_associated_narrative_in_revision(
    manager, center_a, beneficiary_a
):
    record = save_beneficiary_intake(
        beneficiary=beneficiary_a, center=center_a, actor=manager, values=answers()
    )
    save_beneficiary_intake(
        beneficiary=beneficiary_a, center=center_a, actor=manager, values={"health_problems": []}
    )
    record.refresh_from_db()
    assert record.health_problems_other == ""
    assert (
        record.revisions.first().before_values["health_problems_other"]
        == answers()["health_problems_other"]
    )
    assert record.revisions.first().after_values["health_problems_other"] == ""


def test_service_uses_persisted_person_scope(coordinator_a, center_a, beneficiary_b):
    forged_unsaved = Beneficiary(pk=beneficiary_b.pk, center=center_a)
    with pytest.raises(PermissionDenied):
        save_beneficiary_intake(
            beneficiary=forged_unsaved,
            center=center_a,
            actor=coordinator_a,
            values={"health_condition": "Synthetic forged person scope"},
        )
    assert not BeneficiaryIntake.objects.exists()
