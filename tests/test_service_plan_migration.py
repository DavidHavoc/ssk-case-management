from datetime import date

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_service_plan_migration_preserves_plans_and_goals_with_review_markers():
    executor = MigrationExecutor(connection)
    old_target = [
        ("accounts", "0005_user_must_change_password"),
        ("casework", "0009_versioned_assessment_engine"),
    ]
    executor.migrate(old_target)
    old_apps = executor.loader.project_state(old_target).apps

    User = old_apps.get_model("accounts", "User")
    Center = old_apps.get_model("centers", "Center")
    StaffProfile = old_apps.get_model("centers", "StaffProfile")
    SpecialistProfile = old_apps.get_model("centers", "SpecialistProfile")
    Beneficiary = old_apps.get_model("casework", "Beneficiary")
    EnrollmentCenterPlacement = old_apps.get_model("casework", "EnrollmentCenterPlacement")
    EnrollmentSpecialistAssignment = old_apps.get_model(
        "casework", "EnrollmentSpecialistAssignment"
    )
    IndividualPlan = old_apps.get_model("casework", "IndividualPlan")
    IndividualPlanGoal = old_apps.get_model("casework", "IndividualPlanGoal")
    CenterServiceOffering = old_apps.get_model("casework", "CenterServiceOffering")
    ServiceDefinition = old_apps.get_model("casework", "ServiceDefinition")
    ServiceEnrollment = old_apps.get_model("casework", "ServiceEnrollment")

    center = Center.objects.create(code="PLAN-MIG", name="Synthetic Plan Migration Center")
    user = User.objects.create(username="plan.migration@example.invalid")
    staff = StaffProfile.objects.create(
        user=user,
        employee_number="PLAN-MIG-EMP",
        primary_center=center,
    )
    specialist = SpecialistProfile.objects.create(staff_profile=staff)
    beneficiary = Beneficiary.objects.create(
        beneficiary_code="PLAN-MIG-BEN",
        center=center,
        full_name="Synthetic Plan Migration Beneficiary",
        birth_date=date(2020, 1, 1),
        enrollment_date=date(2025, 1, 1),
    )
    service, _ = ServiceDefinition.objects.get_or_create(
        code="LEGACY-OTHER",
        defaults={
            "name_en": "Synthetic legacy service",
            "name_ka": "სინთეზური ძველი მომსახურება",
            "family": "legacy",
            "reporting_order": 1000,
        },
    )
    offering = CenterServiceOffering.objects.create(
        center=center,
        service=service,
        valid_from=date(2025, 1, 1),
    )
    enrollment = ServiceEnrollment.objects.create(
        beneficiary=beneficiary,
        service=service,
        episode_code="PLAN-MIG-E01",
        status="active",
        start_date=date(2025, 1, 1),
    )
    EnrollmentCenterPlacement.objects.create(
        enrollment=enrollment,
        center=center,
        offering=offering,
        valid_from=date(2025, 1, 1),
    )
    EnrollmentSpecialistAssignment.objects.create(
        enrollment=enrollment,
        specialist=specialist,
        assignment_role="primary",
        valid_from=date(2025, 1, 1),
    )
    first_plan = IndividualPlan.objects.create(
        enrollment=enrollment,
        beneficiary=beneficiary,
        center=center,
        specialist=specialist,
        status="active",
        plan_start_date=date(2025, 1, 1),
        plan_end_date=date(2025, 6, 30),
    )
    second_plan = IndividualPlan.objects.create(
        enrollment=enrollment,
        beneficiary=beneficiary,
        center=center,
        specialist=specialist,
        status="active",
        plan_start_date=date(2025, 7, 1),
    )
    first_goal = IndividualPlanGoal.objects.create(
        plan=first_plan,
        goal="Exact preserved first synthetic goal",
        target_date=date(2025, 5, 1),
        status="achieved",
        progress_notes="Exact preserved first progress note",
    )
    second_goal = IndividualPlanGoal.objects.create(
        plan=second_plan,
        goal="Exact preserved second synthetic goal",
        target_date=date(2025, 10, 1),
        status="in_progress",
        progress_notes="Exact preserved second progress note",
    )

    leaf_targets = executor.loader.graph.leaf_nodes()
    try:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        apps = executor.loader.project_state(executor.loader.graph.leaf_nodes()).apps
        NewPlan = apps.get_model("casework", "IndividualPlan")
        NewGoal = apps.get_model("casework", "IndividualPlanGoal")
        GoalStatusTransition = apps.get_model("casework", "GoalStatusTransition")

        migrated_first_plan = NewPlan.objects.get(pk=first_plan.pk)
        migrated_second_plan = NewPlan.objects.get(pk=second_plan.pk)
        migrated_first_goal = NewGoal.objects.get(pk=first_goal.pk)
        migrated_second_goal = NewGoal.objects.get(pk=second_goal.pk)
        results = {
            "first_version": migrated_first_plan.version_number,
            "first_status": migrated_first_plan.status,
            "second_version": migrated_second_plan.version_number,
            "second_status": migrated_second_plan.status,
            "previous_plan": migrated_second_plan.previous_plan_id,
            "first_goal": migrated_first_goal.goal,
            "second_goal": migrated_second_goal.goal,
            "first_notes": migrated_first_goal.progress_notes,
            "second_notes": migrated_second_goal.progress_notes,
            "first_category": migrated_first_goal.category.code,
            "second_category": migrated_second_goal.category.code,
            "first_specialist": migrated_first_goal.responsible_specialist_id,
            "second_specialist": migrated_second_goal.responsible_specialist_id,
            "review_markers": NewGoal.objects.filter(requires_review=True).count(),
            "status_history": GoalStatusTransition.objects.filter(
                goal_id__in=[first_goal.pk, second_goal.pk]
            ).count(),
        }
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(leaf_targets)

    assert results == {
        "first_version": 1,
        "first_status": "superseded",
        "second_version": 2,
        "second_status": "active",
        "previous_plan": first_plan.pk,
        "first_goal": "Exact preserved first synthetic goal",
        "second_goal": "Exact preserved second synthetic goal",
        "first_notes": "Exact preserved first progress note",
        "second_notes": "Exact preserved second progress note",
        "first_category": "LEGACY-UNCLASSIFIED",
        "second_category": "LEGACY-UNCLASSIFIED",
        "first_specialist": specialist.pk,
        "second_specialist": specialist.pk,
        "review_markers": 2,
        "status_history": 2,
    }
