from datetime import date

import pytest
from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import reverse

from apps.casework.models import (
    GoalCategory,
    GoalOutcomeMeasurement,
    IndividualPlan,
    IndividualPlanGoal,
    IndividualPlanReview,
)
from apps.casework.services import record_goal_status_transition, save_plan_period

from .factories import make_assessment, make_plan, make_visit, set_active_center

pytestmark = pytest.mark.django_db


def _goal(plan, specialist, *, status=IndividualPlanGoal.Status.PLANNED, **kwargs):
    values = {
        "plan": plan,
        "category": GoalCategory.objects.get(code="LEGACY-UNCLASSIFIED"),
        "goal": "Synthetic measurable service-plan goal",
        "baseline": "Synthetic baseline",
        "measurable_target": "Synthetic measurable target",
        "responsible_specialist": specialist,
        "target_date": date(2026, 5, 1),
        "status": status,
    }
    values.update(kwargs)
    return IndividualPlanGoal.objects.create(**values)


def test_seeded_goal_categories_have_english_and_georgian_labels():
    expected = {
        "CHILD-SAFETY-HYGIENE",
        "INDIVIDUAL-DEVELOPMENT",
        "DAILY-ACTIVITIES",
        "POSITIVE-PARENTING",
        "KINDERGARTEN-SCHOOL-TRANSITION",
    }
    categories = GoalCategory.objects.filter(code__in=expected)

    assert set(categories.values_list("code", flat=True)) == expected
    assert all(category.name_en and category.name_ka for category in categories)


def test_goal_status_transitions_are_validated_and_recorded(
    beneficiary_a, specialist_a, coordinator_a
):
    plan = make_plan(beneficiary_a, specialist_a)
    goal = _goal(plan, specialist_a)
    goal.status = IndividualPlanGoal.Status.ACHIEVED
    goal.achieved_date = date(2026, 4, 1)
    goal.evidence = "Synthetic evidence"
    with pytest.raises(ValidationError, match="transition is not allowed"):
        goal.save()

    goal.status = IndividualPlanGoal.Status.IN_PROGRESS
    goal.achieved_date = None
    goal.evidence = ""
    goal.save()
    transition = record_goal_status_transition(
        goal,
        from_status=IndividualPlanGoal.Status.PLANNED,
        actor=coordinator_a,
        transition_date=date(2026, 2, 1),
    )
    assert transition.to_status == IndividualPlanGoal.Status.IN_PROGRESS

    goal.status = IndividualPlanGoal.Status.ACHIEVED
    goal.achieved_date = date(2026, 4, 1)
    goal.evidence = "Synthetic evidence"
    goal.save()
    record_goal_status_transition(
        goal,
        from_status=IndividualPlanGoal.Status.IN_PROGRESS,
        actor=coordinator_a,
        transition_date=date(2026, 4, 1),
        evidence=goal.evidence,
    )
    assert list(goal.status_history.values_list("to_status", flat=True)) == [
        IndividualPlanGoal.Status.IN_PROGRESS,
        IndividualPlanGoal.Status.ACHIEVED,
    ]


def test_activating_new_plan_period_supersedes_prior_period(beneficiary_a, specialist_a):
    old_plan = make_plan(beneficiary_a, specialist_a)
    new_plan = IndividualPlan.objects.create(
        enrollment=old_plan.enrollment,
        beneficiary=beneficiary_a,
        center=old_plan.center,
        specialist=specialist_a,
        status=IndividualPlan.Status.DRAFT,
        plan_start_date=date(2026, 6, 2),
        plan_end_date=date(2026, 12, 1),
        review_due_date=date(2026, 7, 2),
    )
    _goal(new_plan, specialist_a, target_date=date(2026, 8, 1))

    new_plan.status = IndividualPlan.Status.ACTIVE
    save_plan_period(new_plan)

    old_plan.refresh_from_db()
    new_plan.refresh_from_db()
    assert old_plan.status == IndividualPlan.Status.SUPERSEDED
    assert new_plan.previous_plan == old_plan
    assert new_plan.version_number == old_plan.version_number + 1


def test_plan_service_rejects_active_period_without_goals(beneficiary_a, specialist_a):
    enrollment = beneficiary_a.enrollments.get(service__code="LEGACY-OTHER")
    plan = IndividualPlan(
        enrollment=enrollment,
        beneficiary=beneficiary_a,
        center=enrollment.placement_on(date(2026, 2, 1)).center,
        specialist=specialist_a,
        status=IndividualPlan.Status.ACTIVE,
        plan_start_date=date(2026, 2, 1),
    )

    with pytest.raises(ValueError, match="requires at least one valid goal"):
        save_plan_period(plan)

    assert not IndividualPlan.objects.filter(pk=plan.pk).exists()


def test_plan_reviews_and_measurements_are_append_only(beneficiary_a, specialist_a, coordinator_a):
    plan = make_plan(beneficiary_a, specialist_a)
    goal = plan.goals.get()
    assessment = make_assessment(beneficiary_a, specialist_a)
    measurement = GoalOutcomeMeasurement.objects.create(
        goal=goal,
        measurement_date=date(2026, 2, 1),
        rating="Prompted",
        unit_or_scale="Independent, prompted, not completed",
        interpretation="Synthetic progress",
        recorded_by=coordinator_a,
        source_assessment=assessment,
    )
    review = IndividualPlanReview.objects.create(
        plan=plan,
        review_date=date(2026, 2, 2),
        condition_outcome=IndividualPlanReview.ConditionOutcome.IMPROVED,
        rationale="Synthetic reviewed conclusion",
        recorded_by=coordinator_a,
        source_assessment=assessment,
    )

    measurement.notes = "Attempted overwrite"
    with pytest.raises(ValidationError, match="append-only"):
        measurement.save()
    review.rationale = "Attempted overwrite"
    with pytest.raises(ValidationError, match="append-only"):
        review.save()


def test_assessment_and_visit_links_cannot_cross_enrollments(
    beneficiary_a, specialist_a, beneficiary_b, specialist_b
):
    plan = make_plan(beneficiary_a, specialist_a)
    goal = plan.goals.get()
    assessment_a = make_assessment(beneficiary_a, specialist_a)
    assessment_b = make_assessment(beneficiary_b, specialist_b)
    visit_a = make_visit(beneficiary_a, specialist_a)
    visit_b = make_visit(beneficiary_b, specialist_b)

    goal.assessment_findings.add(assessment_a)
    visit_a.goals_worked_on.add(goal)
    assert goal.assessment_findings.get() == assessment_a
    assert visit_a.goals_worked_on.get() == goal

    with transaction.atomic():
        with pytest.raises(ValidationError, match="goal enrollment"):
            goal.assessment_findings.add(assessment_b)
    with transaction.atomic():
        with pytest.raises(ValidationError, match="same enrollment"):
            visit_b.goals_worked_on.add(goal)


def test_plan_outcome_report_uses_derived_goal_counts_and_latest_review(
    client, coordinator_a, center_a, beneficiary_a, specialist_a
):
    plan = make_plan(beneficiary_a, specialist_a)
    _goal(plan, specialist_a, goal="Synthetic planned goal")
    _goal(
        plan,
        specialist_a,
        goal="Synthetic achieved goal",
        status=IndividualPlanGoal.Status.ACHIEVED,
        achieved_date=date(2026, 3, 1),
        evidence="Synthetic achieved evidence",
    )
    IndividualPlanReview.objects.create(
        plan=plan,
        review_date=date(2026, 4, 1),
        condition_outcome=IndividualPlanReview.ConditionOutcome.STABLE,
        rationale="Synthetic stable conclusion",
        recorded_by=coordinator_a,
    )
    client.force_login(coordinator_a)
    set_active_center(client, center_a)

    response = client.get(reverse("reports"), {"type": "plan_outcomes"})

    assert response.status_code == 200
    overall = next(row for row in response.context["rows"] if row.category is None)
    assert overall.total_goals == 3
    assert overall.planned_goals == 1
    assert overall.in_progress_goals == 1
    assert overall.achieved_goals == 1
    assert overall.condition_outcome == "Stable"


def test_nested_plan_history_routes_enforce_parent_authorization(
    client, manager, center_b, beneficiary_a, specialist_a
):
    plan = make_plan(beneficiary_a, specialist_a)
    goal = plan.goals.get()
    client.force_login(manager)
    set_active_center(client, center_b)

    assert client.get(reverse("plan_review_create", kwargs={"plan_pk": plan.pk})).status_code == 404
    assert (
        client.get(
            reverse(
                "plan_goal_measurement_create",
                kwargs={"plan_pk": plan.pk, "goal_pk": goal.pk},
            )
        ).status_code
        == 404
    )
    assert not IndividualPlanReview.objects.filter(plan=plan).exists()
    assert not GoalOutcomeMeasurement.objects.filter(goal=goal).exists()


def test_current_assignee_can_append_only_on_an_effective_record_date(
    client, center_a, beneficiary_a, specialist_a
):
    plan = make_plan(beneficiary_a, specialist_a)
    goal = plan.goals.get()
    assignment = plan.enrollment.specialist_assignments.get(specialist=specialist_a)
    assignment.valid_from = date(2026, 2, 1)
    assignment.save()
    client.force_login(specialist_a.staff_profile.user)
    set_active_center(client, center_a)
    url = reverse(
        "plan_goal_measurement_create",
        kwargs={"plan_pk": plan.pk, "goal_pk": goal.pk},
    )

    assert client.get(url).status_code == 200
    rejected = client.post(
        url,
        {
            "measurement_date": "2026-01-15",
            "rating": "Synthetic early rating",
        },
    )
    assert rejected.status_code == 200
    assert "assignment is not effective" in rejected.content.decode()
    accepted = client.post(
        url,
        {
            "measurement_date": "2026-03-01",
            "rating": "Synthetic current rating",
        },
    )
    assert accepted.status_code == 302
    assert GoalOutcomeMeasurement.objects.filter(
        goal=goal,
        rating="Synthetic current rating",
    ).exists()
