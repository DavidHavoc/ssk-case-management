import json
from datetime import date, timedelta
from io import StringIO

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.casework.early_intervention_docx_import import FORMAT, read_docx_register
from apps.casework.models import (
    Assessment,
    Beneficiary,
    BeneficiaryWorkbookImport,
    EnrollmentSpecialistAssignment,
    ServiceEnrollment,
    ServiceVisit,
)
from apps.casework.workbook_import import WorkbookImportError, apply_workbook, validate_destination
from apps.core.authorization import can_create_case_record

from .factories import set_active_center

pytestmark = pytest.mark.django_db


def source_row(**changes):
    row = {
        "number": 1,
        "voucher_number": "00042",
        "first_name": "Synthetic",
        "last_name": "Child",
        "personal_id": "00000000001",
        "birth_date": "17.05.2020.",
        "guardian": "Synthetic\n Guardian პ/ნ 00000000002",
        "services": [
            {
                "kind": "Synthetic service kind",
                "count": "08",
                "location": "Synthetic location",
                "supervision": "Synthetic supervisor",
            }
        ],
    }
    row.update(changes)
    return row


def register_path(tmp_path, *rows, **changes):
    document = {
        "format": FORMAT,
        "source_sha256": "c" * 64,
        "source_heading": "Synthetic private DOCX heading: 2017 program, June",
        "rows": list(rows or [source_row()]),
    }
    document.update(changes)
    path = tmp_path / "synthetic-docx.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def read(path, **changes):
    today = timezone.localdate()
    options = {
        "reporting_period": today.strftime("%Y-%m"),
        "snapshot_date": today.isoformat(),
        "confirmed_active": True,
    }
    options.update(changes)
    return read_docx_register(path, **options)


def destination(manager, center):
    return {
        "actor": manager,
        "center_code": center.code,
        "center_name": center.name,
        "link_specialists": False,
    }


@pytest.mark.parametrize("confirmed_active", [False, True])
def test_person_snapshot_and_source_without_invented_history(
    tmp_path, manager, center_a, coordinator_a, confirmed_active
):
    plan = read(register_path(tmp_path), confirmed_active=confirmed_active)
    row = plan.rows[0]
    assert row.person["birth_date"] == date(2020, 5, 17)
    assert row.person["guardian_parent"] == "Synthetic Guardian"
    assert row.person["application_contract_number"] == "00042"
    result = apply_workbook(plan, **destination(manager, center_a), allow_incomplete=True)
    assert result == {
        "created": 1,
        "skipped": 0,
        "enrollments_created": 1,
        "assignments_created": 0,
    }
    person = Beneficiary.objects.get()
    enrollment = ServiceEnrollment.objects.get()
    assert person.personal_id == "00000000001"
    assert person.enrollment_date is None
    assert person.first_service_date is None
    assert person.application_contract_number == "00042"
    assert enrollment.start_date is None
    assert enrollment.legacy_dates_incomplete
    assert enrollment.current_center == center_a
    assert enrollment.status_on(plan.snapshot_on) == ("active" if confirmed_active else "pending")
    assert enrollment.status_on(plan.snapshot_on - timedelta(days=1)) is None
    assert (
        can_create_case_record(coordinator_a, center_a, enrollment, plan.snapshot_on)
        is confirmed_active
    )
    assert not ServiceVisit.objects.exists()
    assert not Assessment.objects.exists()
    assert not EnrollmentSpecialistAssignment.objects.exists()
    source = BeneficiaryWorkbookImport.objects.get()
    assert "00000000002" in source.source_values["guardian"]
    assert source.source_values["birth_date"] == "17.05.2020."
    assert source.source_values["voucher_number"] == "00042"
    assert json.loads(source.source_values["services"]) == source_row()["services"]
    assert source.source_values["reporting_period"] == plan.snapshot_on.strftime("%Y-%m")


def test_unclear_fields_and_adult_birth_are_preserved(tmp_path):
    plan = read(
        register_path(
            tmp_path, source_row(personal_id="123", birth_date="17.05.3020", guardian="-")
        )
    )
    row = plan.rows[0]
    assert row.person["personal_id"] == ""
    assert row.person["birth_date"] is None
    assert row.person["guardian_parent"] == ""
    assert row.source["personal_id"] == "123"
    assert row.source["birth_date"] == "17.05.3020"
    assert set(row.issues) == {"start_date", "personal_id", "birth_date", "guardian"}
    adult = read(register_path(tmp_path, source_row(birth_date="17.05.1990"))).rows[0]
    assert adult.person["birth_date"] == date(1990, 5, 17)
    assert "age_review" in adult.issues


@pytest.mark.parametrize("marker", ["პ/ნ", "პ.ნ", "პ.ნ...", "/ნ"])
def test_whitespace_normalization_and_guardian_id_variants(tmp_path, marker):
    raw = source_row(
        personal_id="00000 000\n001",
        voucher_number=" 00 0\n42 ",
        guardian=f"Synthetic Guardian{marker}00000 000\n002",
    )
    row = read(register_path(tmp_path, raw)).rows[0]
    assert row.person["personal_id"] == "00000000001"
    assert row.person["application_contract_number"] == "00042"
    assert row.person["guardian_parent"] == "Synthetic Guardian"
    assert row.source["personal_id"] == raw["personal_id"]
    assert row.source["voucher_number"] == raw["voucher_number"]
    assert row.source["guardian"] == raw["guardian"]


@pytest.mark.parametrize(
    "guardian, expected_name",
    [
        ("Synthetic Guardian 00000 000\n002", "Synthetic Guardian"),
        ("00000 000\n002", ""),
        ("/ნ00000 000\n002", ""),
    ],
)
def test_trailing_guardian_identifiers_never_enter_operational_name(
    tmp_path, guardian, expected_name
):
    row = read(register_path(tmp_path, source_row(guardian=guardian))).rows[0]
    assert row.person["guardian_parent"] == expected_name
    assert row.source["guardian"] == guardian
    assert ("guardian" in row.issues) is (not expected_name)


def test_normalized_duplicate_ids_stop_and_duplicate_service_types_need_review(tmp_path):
    with pytest.raises(WorkbookImportError, match="duplicate personal ID"):
        read(
            register_path(tmp_path, source_row(), source_row(number=2, personal_id="00000 000001"))
        )
    services = [
        source_row()["services"][0],
        {**source_row()["services"][0], "kind": " Synthetic  service kind ", "count": "2"},
    ]
    row = read(register_path(tmp_path, source_row(services=services))).rows[0]
    assert "service_type_review" in row.issues
    assert json.loads(row.source["services"]) == services
    assert row.services == ("EARLY-INTERVENTION",)


@pytest.mark.parametrize(
    "kinds, duplicate",
    [
        (["ინდვიდ.", "ინდივიდ"], True),
        (["ჯგუფური.", "ჯგუფური"], True),
        (["ინდივიდ", "ჯგუფური."], False),
    ],
)
def test_service_type_alias_review_preserves_source(tmp_path, kinds, duplicate):
    services = [{**source_row()["services"][0], "kind": kind} for kind in kinds]
    row = read(register_path(tmp_path, source_row(services=services))).rows[0]
    assert ("service_type_review" in row.issues) is duplicate
    assert json.loads(row.source["services"]) == services


@pytest.mark.parametrize("birth", ["2020-05-17", "17.13.2020", "17.05.2020..", ""])
def test_invalid_dates_stay_in_source(tmp_path, birth):
    row = read(register_path(tmp_path, source_row(birth_date=birth))).rows[0]
    assert row.person["birth_date"] is None
    assert row.source["birth_date"] == birth
    assert "birth_date" in row.issues


@pytest.mark.parametrize(
    "changes",
    [
        {"format": "unknown"},
        {"source_sha256": "bad"},
        {"unexpected": "Synthetic"},
        {"rows": []},
        {"rows": [source_row(), source_row(number=2)]},
        {"rows": [source_row(number=True)]},
        {"rows": [source_row(number=2)]},
        {"rows": [source_row(first_name="")]},
        {"rows": [source_row(personal_id=123)]},
        {"rows": [source_row(extra="Synthetic")]},
        {"rows": [source_row(services=[])]},
        {"rows": [source_row(services=[{}])]},
        {"rows": [source_row(services=[{**source_row()["services"][0], "count": 8}])]},
        {"rows": [source_row(services=source_row()["services"] * 21)]},
    ],
)
def test_malformed_source_stops_without_personal_values(tmp_path, changes):
    with pytest.raises(WorkbookImportError) as error:
        read(register_path(tmp_path, **changes))
    assert "00000000001" not in str(error.value)
    assert "Guardian" not in str(error.value)


def test_review_gate_atomic_rollback_and_actor(tmp_path, monkeypatch, manager, center_a):
    plan = read(register_path(tmp_path))
    with pytest.raises(WorkbookImportError, match="allow-incomplete"):
        apply_workbook(plan, **destination(manager, center_a))
    with pytest.raises(WorkbookImportError, match="existing center"):
        apply_workbook(
            plan,
            actor=manager,
            center_code="MISSING",
            center_name="Missing",
            link_specialists=False,
            allow_incomplete=True,
        )
    manager.is_active = False
    with pytest.raises(PermissionDenied):
        apply_workbook(plan, **destination(manager, center_a), allow_incomplete=True)
    manager.is_active = True

    def fail(*args, **kwargs):
        raise ValidationError("Synthetic confidential value must not leak")

    monkeypatch.setattr(ServiceEnrollment, "save", fail)
    with pytest.raises(WorkbookImportError) as error:
        apply_workbook(plan, **destination(manager, center_a), allow_incomplete=True)
    assert "confidential" not in str(error.value)
    assert not Beneficiary.objects.exists()
    assert not BeneficiaryWorkbookImport.objects.exists()
    assert not AuditEvent.objects.exists()


def test_repeat_skips_changed_source_and_existing_ids_stop(tmp_path, manager, center_a):
    plan = read(register_path(tmp_path))
    options = destination(manager, center_a)
    apply_workbook(plan, **options, allow_incomplete=True)
    assert apply_workbook(plan, **options, allow_incomplete=True)["skipped"] == 1
    changed = read(register_path(tmp_path, source_row(voucher_number="Synthetic changed voucher")))
    with pytest.raises(WorkbookImportError, match="source differs"):
        validate_destination(changed, **options)
    different = read(register_path(tmp_path, source_sha256="d" * 64))
    with pytest.raises(WorkbookImportError, match="already exists"):
        validate_destination(different, **options)
    assert Beneficiary.objects.count() == 1


def test_inspection_has_no_database_access_and_rejects_assignments(tmp_path, django_db_blocker):
    path = register_path(tmp_path)
    output = StringIO()
    options = {
        "reporting_period": timezone.localdate().strftime("%Y-%m"),
        "snapshot_date": timezone.localdate().isoformat(),
        "inspect": True,
        "stdout": output,
    }
    with django_db_blocker.block():
        call_command("import_early_intervention_docx_register", str(path), **options)
    assert '"pending": 1' in output.getvalue()
    assert "00000000001" not in output.getvalue()
    with pytest.raises(CommandError, match="no responsible specialist"):
        call_command(
            "import_early_intervention_docx_register", str(path), link_specialists=True, **options
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"reporting_period": "3020-01"},
        {"snapshot_date": "3020-01-01"},
        {"reporting_period": "June"},
        {"snapshot_date": "20260927"},
    ],
)
def test_invalid_reporting_period_or_snapshot(tmp_path, changes):
    with pytest.raises(WorkbookImportError):
        read(register_path(tmp_path), **changes)


def test_source_display_is_restricted(
    tmp_path, client, manager, center_a, coordinator_a, specialist_a
):
    plan = read(register_path(tmp_path))
    apply_workbook(plan, **destination(manager, center_a), allow_incomplete=True)
    enrollment = ServiceEnrollment.objects.get()
    EnrollmentSpecialistAssignment.objects.create(
        enrollment=enrollment, specialist=specialist_a, valid_from=plan.snapshot_on
    )
    url = reverse("beneficiary_detail", kwargs={"pk": enrollment.beneficiary_id})
    for user in (manager, coordinator_a):
        client.force_login(user)
        set_active_center(client, center_a)
        response = client.get(url)
        assert response.status_code == 200
        content = response.content.decode()
        assert "Synthetic private DOCX heading" in content
        assert "00000000002" in content
        assert "Synthetic supervisor" in content
    client.force_login(specialist_a.staff_profile.user)
    set_active_center(client, center_a)
    response = client.get(url)
    assert response.status_code == 200
    assert response.context["workbook_details"] is None
    assert "Synthetic private DOCX heading" not in response.content.decode()
    assert "00000000002" not in response.content.decode()
