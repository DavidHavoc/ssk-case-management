from datetime import date, datetime, timedelta
from io import StringIO

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse
from django.utils import timezone
from openpyxl import Workbook

from apps.audit.models import AuditEvent
from apps.casework.models import (
    Assessment,
    Beneficiary,
    BeneficiaryWorkbookImport,
    CenterServiceOffering,
    EnrollmentSpecialistAssignment,
    ServiceDefinition,
    ServiceEnrollment,
    ServiceVisit,
)
from apps.casework.workbook_import import (
    HEADERS,
    WorkbookImportError,
    apply_workbook,
    read_workbook,
    validate_destination,
)
from apps.centers.models import Center
from apps.core.authorization import can_create_case_record, enrollments_for_user

from .factories import make_specialist, set_active_center

pytestmark = pytest.mark.django_db


def source_row(**changes):
    values = {
        "services": "შინმოვლა, საკვების მიწოდება",
        "full_name": "Synthetic Workbook Person",
        "personal_id": "00000000001",
        "address": "Synthetic private address",
        "phone": "N/A",
        "sex": "მდედრობითი",
        "source_status": "Synthetic unverified status",
        "birth_date": date(1950, 1, 17),
        "source_age": 75,
        "barthel_category": "I კატეგორია - 0 - 65",
        "specialist": "Synthetic Responsible Person",
        "household": "შვილი, მეუღლე",
        "start_date": date(2025, 2, 13),
        "application_number": 12,
        "notes": "Synthetic private workbook note",
        "end_date": None,
        "exit_reason": None,
    }
    values.update(changes)
    return [values[key] for key, _ in HEADERS]


def workbook_path(tmp_path, *rows):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append([label for _, label in HEADERS])
    for row in rows or (source_row(),):
        sheet.append(row)
    path = tmp_path / "synthetic.xlsx"
    workbook.save(path)
    return path


def destination(manager, center, **changes):
    result = {
        "actor": manager,
        "center_code": center.code,
        "center_name": center.name,
        "link_specialists": False,
    }
    result.update(changes)
    return result


def test_parse_uncertainty_without_guessing(tmp_path):
    path = workbook_path(
        tmp_path,
        source_row(
            personal_id=1234567890,
            birth_date=date(2961, 11, 17),
            application_number=date(2026, 1, 1),
            end_date=None,
            exit_reason="Synthetic exit",
        ),
    )
    plan = read_workbook(path)
    row = plan.rows[0]
    assert row.person["personal_id"] == ""
    assert row.person["birth_date"] is None
    assert row.person["application_contract_number"] == ""
    assert row.person["phone"] == ""
    assert row.status == "exited"
    assert row.end is None
    assert row.source["personal_id"] == "1234567890"
    assert row.source["barthel_category"] == "I კატეგორია - 0 - 65"
    assert set(row.issues) == {"personal_id", "birth_date", "application_number", "end_date"}
    assert plan.summary()["enrollments"] == 2


def test_dates_and_future_intake(tmp_path):
    plan = read_workbook(
        workbook_path(tmp_path, source_row(birth_date="01/17/1950", start_date="9/16/2026")),
        today=date(2026, 9, 15),
    )
    assert plan.rows[0].person["birth_date"] == date(1950, 1, 17)
    assert plan.rows[0].status == "pending"
    assert plan.rows[0].start == date(2026, 9, 16)


@pytest.mark.parametrize(
    "changes",
    [
        {"services": "Unknown"},
        {"full_name": None},
        {"notes": "=1+1"},
    ],
)
def test_invalid_source_blocks_without_personal_values(tmp_path, changes):
    with pytest.raises(WorkbookImportError) as error:
        read_workbook(workbook_path(tmp_path, source_row(**changes)))
    assert "Synthetic" not in str(error.value)
    assert "00000000001" not in str(error.value)


def test_duplicates_and_undated_visits_are_not_silently_imported(tmp_path):
    with pytest.raises(WorkbookImportError, match="duplicate"):
        read_workbook(workbook_path(tmp_path, source_row(), source_row()))
    with pytest.raises(WorkbookImportError, match="visit data"):
        read_workbook(workbook_path(tmp_path, source_row() + [None, 12]))


def test_inspect_and_preview_never_write(tmp_path, manager, center_a):
    path = workbook_path(tmp_path)
    plan = read_workbook(path)
    validate_destination(plan, **destination(manager, center_a))
    output = StringIO()
    call_command("import_beneficiary_workbook", str(path), inspect=True, stdout=output)
    assert "Synthetic" not in output.getvalue()
    assert '"beneficiaries": 1' in output.getvalue()
    assert Beneficiary.objects.count() == 0
    assert AuditEvent.objects.count() == 0
    assert ServiceDefinition.objects.get(code="HOME-CARE").valid_from == date(2026, 1, 1)


def test_two_services_one_person_and_repeat_is_noop(tmp_path, manager, center_a):
    plan = read_workbook(workbook_path(tmp_path))
    result = apply_workbook(plan, **destination(manager, center_a))
    assert result["created"] == 1
    assert result["enrollments_created"] == 2
    person = Beneficiary.objects.get()
    assert person.personal_id == "00000000001"
    assert person.barthel_index is None
    assert person.family_status == ""
    assert person.notes == ""
    assert person.diagnosis_status == ""
    assert person.workbook_import.source_values["household"] == "შვილი, მეუღლე"
    assert person.enrollments.count() == 2
    assert Assessment.objects.count() == ServiceVisit.objects.count() == 0
    for enrollment in person.enrollments.all():
        assert enrollment.center_placements.get().center == center_a
        assert enrollment.status_on(date(2025, 3, 1)) == "active"
        assert enrollment.service.valid_from == date(2025, 2, 13)
    audits = AuditEvent.objects.count()
    assert apply_workbook(plan, **destination(manager, center_a))["skipped"] == 1
    assert Beneficiary.objects.count() == 1
    assert AuditEvent.objects.count() == audits


def test_review_approval_and_atomic_rollback(tmp_path, manager, center_a, monkeypatch):
    plan = read_workbook(workbook_path(tmp_path, source_row(personal_id=123)))
    with pytest.raises(WorkbookImportError, match="allow-incomplete"):
        apply_workbook(plan, **destination(manager, center_a))
    assert Beneficiary.objects.count() == 0

    def fail(*args, **kwargs):
        raise ValidationError("Synthetic confidential value must not leak")

    monkeypatch.setattr(ServiceEnrollment, "save", fail)
    with pytest.raises(WorkbookImportError) as error:
        apply_workbook(plan, **destination(manager, center_a), allow_incomplete=True)
    assert "confidential" not in str(error.value)
    assert Beneficiary.objects.count() == 0
    assert BeneficiaryWorkbookImport.objects.count() == 0
    assert AuditEvent.objects.count() == 0
    assert ServiceDefinition.objects.get(code="HOME-CARE").valid_from == date(2026, 1, 1)


def test_exited_without_date_cannot_gain_service_access(tmp_path, manager, center_a):
    plan = read_workbook(workbook_path(tmp_path, source_row(exit_reason="Synthetic exit")))
    apply_workbook(plan, **destination(manager, center_a), allow_incomplete=True)
    person = Beneficiary.objects.get()
    assert person.service_status == "exited"
    for enrollment in person.enrollments.all():
        assert enrollment.end_date is None
        assert enrollment.legacy_dates_incomplete
        assert enrollment.status_on(timezone.localdate()) is None
        assert not can_create_case_record(manager, center_a, enrollment, timezone.localdate())


def test_matching_staff_gets_current_service_access_only(tmp_path, manager, specialist_a, center_a):
    name = specialist_a.staff_profile.user.get_full_name()
    plan = read_workbook(workbook_path(tmp_path, source_row(specialist=name)))
    result = apply_workbook(plan, **destination(manager, center_a, link_specialists=True))
    assert result["assignments_created"] == 2
    assert enrollments_for_user(specialist_a.staff_profile.user, center_a).count() == 2
    for assignment in EnrollmentSpecialistAssignment.objects.all():
        assert assignment.valid_from == timezone.localdate()
        assert not assignment.is_effective(timezone.localdate() - timedelta(days=1))


def test_cross_center_and_ambiguous_names_do_not_grant_access(
    tmp_path, manager, center_a, specialist_b
):
    name = specialist_b.staff_profile.user.get_full_name()
    plan = read_workbook(workbook_path(tmp_path, source_row(specialist=name)))
    result = apply_workbook(
        plan, **destination(manager, center_a, link_specialists=True), allow_incomplete=True
    )
    assert result["assignments_created"] == 0
    assert "specialist" in BeneficiaryWorkbookImport.objects.get().review_issues

    first = make_specialist(center_a, "duplicate-first")
    second = make_specialist(center_a, "duplicate-second")
    second.staff_profile.user.first_name = first.staff_profile.user.first_name
    second.staff_profile.user.last_name = first.staff_profile.user.last_name
    second.staff_profile.user.save()
    plan = read_workbook(
        workbook_path(
            tmp_path,
            source_row(
                personal_id="00000000002", specialist=first.staff_profile.user.get_full_name()
            ),
        )
    )
    result = apply_workbook(
        plan, **destination(manager, center_a, link_specialists=True), allow_incomplete=True
    )
    assert result["assignments_created"] == 0


def test_non_manager_and_existing_person_conflicts_are_rejected(
    tmp_path, coordinator_a, manager, center_a
):
    plan = read_workbook(workbook_path(tmp_path))
    with pytest.raises(PermissionDenied):
        apply_workbook(plan, **destination(coordinator_a, center_a))
    apply_workbook(plan, **destination(manager, center_a))
    changed = read_workbook(workbook_path(tmp_path, source_row(notes="Changed source")))
    with pytest.raises(WorkbookImportError, match="already exists"):
        apply_workbook(changed, **destination(manager, center_a))
    assert Beneficiary.objects.count() == 1


def test_new_center_is_created_with_only_requested_services(tmp_path, manager):
    plan = read_workbook(workbook_path(tmp_path, source_row(services="შინმოვლა")))
    apply_workbook(
        plan,
        actor=manager,
        center_code="SYNTHETIC-IMPORT",
        center_name="Synthetic Import Center",
        link_specialists=False,
    )
    center = Center.objects.get(code="SYNTHETIC-IMPORT")
    assert CenterServiceOffering.objects.filter(center=center).count() == 1


def test_restricted_source_is_not_in_specialist_context_or_html(
    tmp_path, client, manager, center_a, specialist_a, coordinator_a
):
    plan = read_workbook(
        workbook_path(
            tmp_path, source_row(specialist=specialist_a.staff_profile.user.get_full_name())
        )
    )
    apply_workbook(plan, **destination(manager, center_a, link_specialists=True))
    person = Beneficiary.objects.get()
    url = reverse("beneficiary_detail", kwargs={"pk": person.pk})
    for user in (manager, coordinator_a):
        client.force_login(user)
        set_active_center(client, center_a)
        response = client.get(url)
        assert response.status_code == 200
        assert "Synthetic private workbook note" in response.content.decode()
        assert response.context["workbook_details"] is not None
    client.force_login(specialist_a.staff_profile.user)
    set_active_center(client, center_a)
    response = client.get(url)
    assert response.status_code == 200
    assert response.context["workbook_details"] is None
    assert "Synthetic private workbook note" not in response.content.decode()
    assert "Synthetic unverified status" not in response.content.decode()


def test_command_rejects_apply_inspect_combination(tmp_path):
    with pytest.raises(CommandError):
        call_command(
            "import_beneficiary_workbook", str(workbook_path(tmp_path)), inspect=True, apply=True
        )


def test_imported_dates_are_typed(tmp_path):
    plan = read_workbook(
        workbook_path(
            tmp_path,
            source_row(
                birth_date=datetime(1950, 1, 17), end_date="2/23/2026", exit_reason="Synthetic exit"
            ),
        )
    )
    assert plan.rows[0].person["birth_date"] == date(1950, 1, 17)
    assert plan.rows[0].end == date(2026, 2, 23)
