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
from apps.casework.early_intervention_import import FORMAT, read_pdf_register
from apps.casework.models import (
    Assessment,
    Beneficiary,
    BeneficiaryWorkbookImport,
    ServiceEnrollment,
    ServiceVisit,
)
from apps.casework.workbook_import import WorkbookImportError, apply_workbook, validate_destination
from apps.core.authorization import can_create_case_record, enrollments_for_user

from .factories import set_active_center

pytestmark = pytest.mark.django_db


def source_row(**changes):
    row = {
        "number": 1,
        "first_name": "Synthetic",
        "last_name": "Child",
        "personal_id": "00000000001",
        "birth_date": "17.05.2020",
        "guardian": "00000000002 \u00ad Synthetic\nGuardian",
        "individual_count": 6,
        "group_count": 0,
        "home_count": 3,
        "center_count": 0,
        "total_count": 6,
        "delay_domains": 0,
    }
    row.update(changes)
    return row


def register_path(tmp_path, *rows, **changes):
    rows = list(rows or [source_row()])
    document = {
        "format": FORMAT,
        "source_sha256": "a" * 64,
        "source_heading": "Synthetic private PDF heading: 2017 program, September",
        "reported_total": sum(row["total_count"] for row in rows),
        "rows": rows,
    }
    document.update(changes)
    path = tmp_path / "synthetic.json"
    path.write_text(json.dumps(document))
    return path


def read(path, **changes):
    today = timezone.localdate()
    options = {
        "reporting_period": today.strftime("%Y-%m"),
        "snapshot_date": today.isoformat(),
        "confirmed_active": True,
    }
    options.update(changes)
    return read_pdf_register(path, **options)


def destination(manager, center):
    return {
        "actor": manager,
        "center_code": center.code,
        "center_name": center.name,
        "link_specialists": False,
    }


def test_person_snapshot_and_restricted_evidence_without_fabricated_history(
    tmp_path, manager, center_a, coordinator_a
):
    plan = read(register_path(tmp_path))
    row = plan.rows[0]
    assert row.person["personal_id"] == "00000000001"
    assert row.person["guardian_parent"] == "Synthetic Guardian"
    assert row.person["birth_date"] == date(2020, 5, 17)
    assert set(row.issues) == {"start_date", "location_totals"}
    result = apply_workbook(plan, **destination(manager, center_a), allow_incomplete=True)
    assert result == {
        "created": 1,
        "skipped": 0,
        "enrollments_created": 1,
        "assignments_created": 0,
    }
    person = Beneficiary.objects.get()
    enrollment = ServiceEnrollment.objects.get()
    assert person.enrollment_date is None
    assert person.first_service_date is None
    assert person.sex == ""
    assert person.address == ""
    assert enrollment.service.code == "EARLY-INTERVENTION"
    assert enrollment.episode_code is None
    assert enrollment.start_date is None
    assert enrollment.legacy_dates_incomplete
    assert enrollment.current_center == center_a
    assert enrollment.status_on(plan.snapshot_on) == "active"
    earlier = plan.snapshot_on - timedelta(days=1)
    assert enrollment.status_on(earlier) is None
    assert can_create_case_record(coordinator_a, center_a, enrollment, plan.snapshot_on)
    assert not can_create_case_record(manager, center_a, enrollment, earlier)
    assert enrollments_for_user(coordinator_a, center_a).count() == 1
    assert not ServiceVisit.objects.exists()
    assert not Assessment.objects.exists()
    source = BeneficiaryWorkbookImport.objects.get()
    assert source.source_values["home_count"] == "3"
    assert source.source_values["total_count"] == "6"
    assert "00000000002" in source.source_values["guardian"]
    assert "2017" in source.source_values["source_heading"]
    assert source.source_values["reporting_period"] == plan.snapshot_on.strftime("%Y-%m")


def test_unconfirmed_status_cannot_authorize_delivery(tmp_path, manager, center_a):
    plan = read(register_path(tmp_path), confirmed_active=False)
    apply_workbook(plan, **destination(manager, center_a), allow_incomplete=True)
    enrollment = ServiceEnrollment.objects.get()
    assert enrollment.status == "pending"
    assert enrollment.status_on(plan.snapshot_on) == "pending"
    assert not can_create_case_record(manager, center_a, enrollment, plan.snapshot_on)


def test_import_requires_existing_center_and_active_manager(tmp_path, manager, center_a):
    plan = read(register_path(tmp_path))
    options = destination(manager, center_a)
    options["center_code"] = "MISSING-SYNTHETIC"
    with pytest.raises(WorkbookImportError, match="existing center"):
        apply_workbook(plan, **options, allow_incomplete=True)
    options = destination(manager, center_a)
    manager.is_active = False
    with pytest.raises(PermissionDenied):
        apply_workbook(plan, **options, allow_incomplete=True)
    assert not Beneficiary.objects.exists()


def test_review_gate_and_atomic_rollback(tmp_path, monkeypatch, manager, center_a):
    plan = read(register_path(tmp_path))
    with pytest.raises(WorkbookImportError, match="allow-incomplete"):
        apply_workbook(plan, **destination(manager, center_a))

    def fail(*args, **kwargs):
        raise ValidationError("Synthetic confidential value must not leak")

    monkeypatch.setattr(ServiceEnrollment, "save", fail)
    with pytest.raises(WorkbookImportError) as error:
        apply_workbook(plan, **destination(manager, center_a), allow_incomplete=True)
    assert "confidential" not in str(error.value)
    assert not Beneficiary.objects.exists()
    assert not BeneficiaryWorkbookImport.objects.exists()
    assert not AuditEvent.objects.exists()


def test_repeat_noop_changed_evidence_and_existing_person_require_review(
    tmp_path, manager, center_a
):
    path = register_path(tmp_path)
    plan = read(path)
    options = destination(manager, center_a)
    apply_workbook(plan, **options, allow_incomplete=True)
    assert apply_workbook(plan, **options, allow_incomplete=True)["created"] == 0
    changed = read(register_path(tmp_path, source_row(guardian="Synthetic Changed Guardian")))
    with pytest.raises(WorkbookImportError, match="source differs"):
        validate_destination(changed, **options)
    different_pdf = read(register_path(tmp_path, source_sha256="b" * 64))
    with pytest.raises(WorkbookImportError, match="already exists"):
        validate_destination(different_pdf, **options)
    assert Beneficiary.objects.count() == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"format": "unknown"},
        {"source_sha256": "bad"},
        {"reported_total": 999},
        {"rows": []},
        {"rows": [source_row(), source_row(number=2)]},
        {"rows": [source_row(home_count=-1)]},
        {"rows": [source_row(group_count=True)]},
        {"rows": [source_row(number=2)]},
        {"rows": [source_row(first_name="")]},
    ],
)
def test_invalid_source_stops_without_personal_values(tmp_path, changes):
    with pytest.raises(WorkbookImportError) as error:
        read(register_path(tmp_path, **changes))
    assert "00000000001" not in str(error.value)
    assert "Guardian" not in str(error.value)


def test_unclear_fields_are_preserved_and_not_guessed(tmp_path):
    plan = read(
        register_path(
            tmp_path,
            source_row(
                personal_id="123", birth_date="17.05.3020", guardian="-", individual_count=7
            ),
        )
    )
    row = plan.rows[0]
    assert row.person["personal_id"] == ""
    assert row.person["birth_date"] is None
    assert row.person["guardian_parent"] == ""
    assert row.source["personal_id"] == "123"
    assert set(row.issues) == {
        "start_date",
        "personal_id",
        "birth_date",
        "guardian",
        "service_totals",
        "location_totals",
    }


def test_future_period_or_snapshot_stops_import(tmp_path):
    path = register_path(tmp_path)
    with pytest.raises(WorkbookImportError, match="future"):
        read(path, reporting_period="3020-01")
    with pytest.raises(WorkbookImportError, match="future"):
        read(path, snapshot_date="3020-01-01")
    with pytest.raises(WorkbookImportError, match="YYYY-MM"):
        read(path, reporting_period="September")


def test_inspect_does_not_access_database_and_command_rejects_assignments(
    tmp_path, django_db_blocker
):
    output = StringIO()
    options = {
        "reporting_period": timezone.localdate().strftime("%Y-%m"),
        "snapshot_date": timezone.localdate().isoformat(),
        "inspect": True,
        "stdout": output,
    }
    path = register_path(tmp_path)
    with django_db_blocker.block():
        call_command("import_early_intervention_register", str(path), **options)
    assert '"pending": 1' in output.getvalue()
    assert "00000000001" not in output.getvalue()
    with pytest.raises(CommandError, match="no specialist"):
        call_command(
            "import_early_intervention_register", str(path), link_specialists=True, **options
        )


def test_source_information_remains_restricted_in_beneficiary_page(
    tmp_path, client, manager, center_a, coordinator_a, specialist_a
):
    plan = read(register_path(tmp_path))
    apply_workbook(plan, **destination(manager, center_a), allow_incomplete=True)
    enrollment = ServiceEnrollment.objects.get()
    from django.utils import timezone

    from apps.casework.services import replace_beneficiary_staffing

    replace_beneficiary_staffing(
        beneficiary=enrollment.beneficiary,
        lead=specialist_a,
        effective_date=timezone.localdate(),
        center=center_a,
        actor=manager,
    )

    url = reverse("beneficiary_detail", kwargs={"pk": enrollment.beneficiary_id})
    for user in (manager, coordinator_a):
        client.force_login(user)
        set_active_center(client, center_a)
        response = client.get(url)
        assert response.status_code == 200
        assert "Synthetic private PDF heading" in response.content.decode()
        assert "Location counts do not equal" in response.content.decode()
        assert "00000000002" in response.content.decode()
    client.force_login(specialist_a.staff_profile.user)
    set_active_center(client, center_a)
    response = client.get(url)
    assert response.status_code == 200
    assert response.context["workbook_details"] is None
    assert "Synthetic private PDF heading" not in response.content.decode()
    assert "00000000002" not in response.content.decode()
