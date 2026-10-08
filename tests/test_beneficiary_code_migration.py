from datetime import UTC, datetime

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_center_numbering_migrates_and_restores_original_codes():
    before = [("casework", "0011_beneficiaryworkbookimport")]
    after = [("casework", "0013_number_existing_beneficiaries")]
    executor = MigrationExecutor(connection)
    leaves = executor.loader.graph.leaf_nodes()
    try:
        executor.migrate(before)
        old_apps = executor.loader.project_state(before).apps
        Center = old_apps.get_model("centers", "Center")
        Person = old_apps.get_model("casework", "Beneficiary")
        Source = old_apps.get_model("casework", "BeneficiaryWorkbookImport")
        Enrollment = old_apps.get_model("casework", "ServiceEnrollment")
        Service = old_apps.get_model("casework", "ServiceDefinition")
        center_a = Center.objects.create(code="SYN-A", name="Synthetic A")
        center_b = Center.objects.create(code="SYN-B", name="Synthetic B")
        first = Person.objects.create(
            center=center_a,
            beneficiary_code="WB-SYNTHETIC-00009",
            full_name="Synthetic Z",
            service_type="other",
            service_status="exited",
        )
        second = Person.objects.create(
            center=center_a,
            beneficiary_code="SYN-A_B001",
            full_name="Synthetic A",
            service_type="other",
        )
        other = Person.objects.create(
            center=center_b,
            beneficiary_code="WB-SYNTHETIC-00001",
            full_name="Synthetic B",
            service_type="other",
        )
        Person.objects.filter(pk=first.pk).update(created_at=datetime(2026, 9, 1, tzinfo=UTC))
        source = Source.objects.create(
            beneficiary=first,
            source_digest="a" * 64,
            source_row=9,
            source_values={"notes": "Synthetic preserved source"},
            review_issues=["start_date"],
        )
        service, _ = Service.objects.get_or_create(
            code="HOME-CARE",
            defaults={
                "name_en": "Synthetic Home Care",
                "name_ka": "Synthetic",
                "family": "home_care",
            },
        )
        enrollment = Enrollment.objects.create(
            beneficiary=first,
            service=service,
            episode_code="WB-SYNTHETIC-00009-HC",
            status="exited",
        )
        original_people = {row["id"]: row for row in Person.objects.values()}
        original_source = Source.objects.values().get(pk=source.pk)
        original_enrollment = Enrollment.objects.values().get(pk=enrollment.pk)

        executor = MigrationExecutor(connection)
        executor.migrate(after)
        new_apps = executor.loader.project_state(after).apps
        NewPerson = new_apps.get_model("casework", "Beneficiary")
        Sequence = new_apps.get_model("casework", "BeneficiaryCodeSequence")
        assert NewPerson.objects.get(pk=first.pk).beneficiary_code == "SYN-A_B001"
        assert NewPerson.objects.get(pk=second.pk).beneficiary_code == "SYN-A_B002"
        assert NewPerson.objects.get(pk=other.pk).beneficiary_code == "SYN-B_B001"
        assert Sequence.objects.get(center_id=center_a.pk).last_number == 2
        assert Sequence.objects.get(center_id=center_b.pk).last_number == 1
        for row in NewPerson.objects.values():
            assert (
                row.pop("legacy_beneficiary_code") == original_people[row["id"]]["beneficiary_code"]
            )
            row["beneficiary_code"] = original_people[row["id"]]["beneficiary_code"]
            assert row == original_people[row["id"]]
        assert (
            new_apps.get_model("casework", "BeneficiaryWorkbookImport")
            .objects.values()
            .get(pk=source.pk)
            == original_source
        )
        assert (
            new_apps.get_model("casework", "ServiceEnrollment")
            .objects.values()
            .get(pk=enrollment.pk)
            == original_enrollment
        )

        executor = MigrationExecutor(connection)
        executor.migrate(before)
        restored = executor.loader.project_state(before).apps.get_model("casework", "Beneficiary")
        assert {row["id"]: row for row in restored.objects.values()} == original_people
    finally:
        MigrationExecutor(connection).migrate(leaves)
