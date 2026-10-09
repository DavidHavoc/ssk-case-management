from datetime import date

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from apps.casework.models import (
    AssessmentInstrument,
    BeneficiaryWorkbookImport,
    GoalCategory,
    ServiceEnrollment,
)
from apps.casework.services import reenroll_beneficiary, transfer_enrollment, transition_enrollment

from .factories import make_assessment, make_plan, make_visit


def _rows(apps):
    return {
        model._meta.label: sorted(list(model.objects.values()), key=repr)
        for model in apps.get_models(include_auto_created=True)
    }


@pytest.mark.django_db(transaction=True)
def test_retirement_preserves_all_synthetic_relationships_and_reverses(
    beneficiary_a, specialist_a, coordinator_a, center_a, center_b
):
    # Transactional migration tests flush migration-seeded catalogs between tests.
    AssessmentInstrument.objects.get_or_create(
        code="OTHER", defaults={"name": "Synthetic instrument", "lineage_code": "OTHER"}
    )
    GoalCategory.objects.get_or_create(
        code="LEGACY-UNCLASSIFIED",
        defaults={"name_en": "Synthetic category", "name_ka": "სინთეზური კატეგორია"},
    )
    enrollment = beneficiary_a.enrollments.get()
    visit = make_visit(beneficiary_a, specialist_a)
    assessment = make_assessment(beneficiary_a, specialist_a)
    plan = make_plan(beneficiary_a, specialist_a)
    enrollment = transfer_enrollment(
        enrollment,
        destination_offering=center_b.service_offerings.get(service=enrollment.service),
        effective_date=date(2026, 7, 1),
        reason="Synthetic transfer history",
        actor=coordinator_a,
    )
    enrollment = transition_enrollment(
        enrollment,
        new_state=ServiceEnrollment.Status.EXITED,
        effective_date=date(2026, 8, 1),
        reason="Synthetic exit history",
        actor=coordinator_a,
    )
    later = reenroll_beneficiary(
        enrollment,
        offering=center_b.service_offerings.get(service=enrollment.service),
        start_date=date(2026, 9, 1),
        actor=coordinator_a,
    )
    # Exact historical spelling must survive even a later form/model save.
    original_code = "Synthetic-old-Code-e01"
    ServiceEnrollment.objects.filter(pk=enrollment.pk).update(episode_code=original_code)
    ServiceEnrollment.objects.filter(pk=later.pk).update(episode_code="SYNTHETIC-OLD-E02")
    source = BeneficiaryWorkbookImport.objects.create(
        beneficiary=beneficiary_a,
        source_digest="b" * 64,
        source_row=1,
        source_values={"episode_code": original_code, "start_date": "Synthetic source date"},
        review_issues=["start_date"],
    )
    before = [("casework", "0014_beneficiary_emergency_contacts")]
    after = [("casework", "0015_retire_operational_enrollment_codes")]
    executor = MigrationExecutor(connection)
    leaves = executor.loader.graph.leaf_nodes()
    try:
        executor.migrate(before)
        old_apps = executor.loader.project_state(before).apps
        original = _rows(old_apps)
        executor = MigrationExecutor(connection)
        executor.migrate(after)
        new_apps = executor.loader.project_state(after).apps
        assert _rows(new_apps) == original
        Enrollment = new_apps.get_model("casework", "ServiceEnrollment")
        assert Enrollment.objects.get(pk=enrollment.pk).episode_code == original_code
        assert Enrollment.objects.get(pk=later.pk).prior_enrollment_id == enrollment.pk
        for name, record in [
            ("ServiceVisit", visit),
            ("Assessment", assessment),
            ("IndividualPlan", plan),
        ]:
            assert (
                new_apps.get_model("casework", name).objects.get(pk=record.pk).enrollment_id
                == enrollment.pk
            )
        assert (
            new_apps.get_model("casework", "BeneficiaryWorkbookImport")
            .objects.get(pk=source.pk)
            .source_values["episode_code"]
            == original_code
        )
        assert Enrollment._meta.get_field("episode_code").null
        assert not Enrollment._meta.get_field("episode_code").editable
        assert Enrollment._meta.get_field("start_date").verbose_name == "Enrollment date"

        # Multiple uncoded episodes do not collide with the unique legacy column.
        service = new_apps.get_model("casework", "ServiceDefinition").objects.get(code="HOME-CARE")
        uncoded = [
            Enrollment.objects.create(beneficiary_id=beneficiary_a.pk, service=service)
            for _ in range(2)
        ]
        assert all(row.episode_code is None and row.start_date is None for row in uncoded)
        with_uncoded = _rows(new_apps)
        with pytest.raises(RuntimeError, match="uncoded enrollments exist"):
            MigrationExecutor(connection).migrate(before)
        assert _rows(new_apps) == with_uncoded
        Enrollment.objects.filter(pk__in=[row.pk for row in uncoded]).delete()

        # A schema reversal before uncoded enrollments exist is exact and lossless.
        MigrationExecutor(connection).migrate(before)
        assert _rows(old_apps) == original
        MigrationExecutor(connection).migrate(after)
        assert _rows(new_apps) == original
    finally:
        MigrationExecutor(connection).migrate(leaves)
