from datetime import timedelta

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder
from django.utils import timezone

from apps.casework.services import replace_beneficiary_staffing
from apps.core.authorization import enrollments_for_user

from .factories import make_specialist


def snapshot(apps):
    return {
        model._meta.label: sorted(list(model.objects.values()), key=repr)
        for model in apps.get_models(include_auto_created=True)
    }


@pytest.mark.django_db(transaction=True)
def test_backfill_preserves_every_original_row_and_only_confirms_unambiguous_teams(
    center_a, specialist_a, manager
):
    today = timezone.localdate()
    other = make_specialist(center_a, "migration-other")
    inactive = make_specialist(center_a, "migration-inactive")
    inactive.staff_profile.status = "inactive"
    inactive.staff_profile.save()
    old = [("casework", "0015_retire_operational_enrollment_codes")]
    new = [("casework", "0018_staffing_database_guards")]
    executor = MigrationExecutor(connection)
    leaves = executor.loader.graph.leaf_nodes()
    try:
        executor.migrate(old)
        apps = executor.loader.project_state(old).apps
        Person = apps.get_model("casework", "Beneficiary")
        Enrollment = apps.get_model("casework", "ServiceEnrollment")
        Placement = apps.get_model("casework", "EnrollmentCenterPlacement")
        Assignment = apps.get_model("casework", "EnrollmentSpecialistAssignment")
        Evidence = apps.get_model("casework", "BeneficiaryWorkbookImport")
        cases = {}
        for index, kind in enumerate(
            (
                "unique",
                "joint",
                "conflict",
                "unknown",
                "none",
                "exited",
                "inactive",
                "unique_helper",
            ),
            1,
        ):
            person = Person.objects.create(
                center_id=center_a.pk,
                full_name=f"Synthetic staffing {kind}",
                beneficiary_code=f"SYNTHETIC-MIGRATION-B{index:03}",
                service_type="other",
                service_status="active",
            )
            cases[kind] = person.pk
            Evidence.objects.create(
                beneficiary=person,
                source_digest=f"{index:064x}",
                source_row=index,
                source_values={"team": "Synthetic joint source evidence"},
                review_issues=["Synthetic evidence"],
            )
            codes = ("HOME-CARE", "FOOD-DELIVERY") if kind == "conflict" else ("HOME-CARE",)
            for code in codes:
                offering = center_a.service_offerings.get(service__code=code)
                enrollment = Enrollment.objects.create(
                    beneficiary=person,
                    service_id=offering.service_id,
                    start_date=today - timedelta(days=50),
                    status="exited" if kind == "exited" else "active",
                    end_date=today - timedelta(days=1) if kind == "exited" else None,
                )
                Placement.objects.create(
                    enrollment=enrollment,
                    center_id=center_a.pk,
                    offering_id=offering.pk,
                    valid_from=today - timedelta(days=50),
                    valid_to=enrollment.end_date,
                )
                if kind == "none":
                    continue
                lead = (
                    inactive
                    if kind == "inactive"
                    else other
                    if code == "FOOD-DELIVERY"
                    else specialist_a
                )
                Assignment.objects.create(
                    enrollment=enrollment,
                    specialist_id=lead.pk,
                    assignment_role="primary",
                    valid_from=None if kind == "unknown" else today - timedelta(days=40),
                    legacy_dates_incomplete=kind == "unknown",
                )
                if kind in {"joint", "unique_helper"}:
                    Assignment.objects.create(
                        enrollment=enrollment,
                        specialist_id=other.pk,
                        assignment_role="primary" if kind == "joint" else "secondary",
                        valid_from=today - timedelta(days=40),
                    )
        original = snapshot(apps)
        executor = MigrationExecutor(connection)
        executor.migrate(new)
        updated_apps = executor.loader.project_state(new).apps
        after = snapshot(updated_apps)
        assert {label: after[label] for label in original} == original
        Period = updated_apps.get_model("casework", "BeneficiaryStaffingPeriod")
        Grant = updated_apps.get_model("casework", "LegacyStaffingGrant")
        assert set(Period.objects.values_list("beneficiary_id", flat=True)) == {
            cases["unique"],
            cases["unique_helper"],
        }
        assert Period.objects.get(beneficiary_id=cases["unique_helper"]).helper_id == other.pk
        assert not Period.objects.get(beneficiary_id=cases["unique"]).helper_id
        assert Grant.objects.count() == 7
        assert set(Grant.objects.values_list("expires_on", flat=True)) == {today}
        assert not (
            enrollments_for_user(specialist_a.staff_profile.user, center_a)
            .filter(beneficiary_id=cases["joint"])
            .exists()
        )
        assert not (
            enrollments_for_user(other.staff_profile.user, center_a)
            .filter(beneficiary_id=cases["joint"])
            .exists()
        )
        assert (
            not enrollments_for_user(specialist_a.staff_profile.user, center_a)
            .filter(beneficiary_id=cases["unknown"])
            .exists()
        )
        # No staffing writes: exact rollback of all original rows and forward replay.
        executor = MigrationExecutor(connection)
        executor.migrate(old)
        assert snapshot(executor.loader.project_state(old).apps) == original
        executor = MigrationExecutor(connection)
        executor.migrate(new)
        from apps.casework.models import Beneficiary

        replace_beneficiary_staffing(
            beneficiary=Beneficiary.objects.get(pk=cases["joint"]),
            lead=other,
            helper=specialist_a,
            effective_date=today,
            center=center_a,
            actor=manager,
        )
        with pytest.raises(RuntimeError, match="guards remain installed"):
            MigrationExecutor(connection).migrate(old)
        assert ("casework", "0018_staffing_database_guards") in MigrationRecorder(
            connection
        ).applied_migrations()
        assert Evidence.objects.count() == 8
    finally:
        MigrationExecutor(connection).migrate(leaves)
