from datetime import date

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.audit.models import AuditEvent
from apps.casework.models import (
    Assessment,
    GoalCategory,
    IndividualPlan,
    IndividualPlanGoal,
    ServiceVisit,
)

from .factories import (
    make_assessment_template,
    make_beneficiary,
    make_plan,
    make_visit,
    set_active_center,
)

pytestmark = pytest.mark.django_db


def test_sensitive_detail_read_creates_audit_event(client, coordinator_a, center_a, beneficiary_a):
    client.force_login(coordinator_a)
    set_active_center(client, center_a)
    response = client.get(reverse("beneficiary_detail", kwargs={"pk": beneficiary_a.pk}))
    assert response.status_code == 200
    assert AuditEvent.objects.filter(
        event_type=AuditEvent.EventType.SENSITIVE_READ,
        target_type="Beneficiary",
        target_id=beneficiary_a.pk,
        actor=coordinator_a,
    ).exists()


def test_active_plan_requires_goal_in_form_workflow(
    client, coordinator_a, center_a, specialist_a, beneficiary_a
):
    client.force_login(coordinator_a)
    set_active_center(client, center_a)
    response = client.post(
        reverse("plan_create"),
        {
            "beneficiary": str(beneficiary_a.pk),
            "specialist": str(specialist_a.pk),
            "status": IndividualPlan.Status.ACTIVE,
            "plan_start_date": "2026-01-01",
            "plan_end_date": "2026-06-01",
            "review_frequency": IndividualPlan.ReviewFrequency.MONTHLY,
            "goals-TOTAL_FORMS": "0",
            "goals-INITIAL_FORMS": "0",
            "goals-MIN_NUM_FORMS": "0",
            "goals-MAX_NUM_FORMS": "1000",
        },
    )
    assert response.status_code == 200
    assert "At least one goal is required" in response.content.decode()
    assert IndividualPlan.objects.count() == 0


def test_goal_can_be_added_directly_without_replacing_existing_goals(
    client, coordinator_a, center_a, specialist_a, beneficiary_a
):
    plan = make_plan(beneficiary_a, specialist_a)
    existing_goal = plan.goals.get()
    category = GoalCategory.objects.get(code="LEGACY-UNCLASSIFIED")
    client.force_login(coordinator_a)
    set_active_center(client, center_a)
    url = reverse("plan_goal_create", kwargs={"plan_pk": plan.pk})

    response = client.get(url)

    assert response.status_code == 200
    assert existing_goal.goal in response.content.decode()
    response = client.post(
        url,
        {
            "goal": "Second synthetic goal",
            "category": str(category.pk),
            "baseline": "Synthetic starting point",
            "measurable_target": "Synthetic target is met",
            "measurement_type": IndividualPlanGoal.MeasurementType.NARRATIVE,
            "responsible_specialist": str(specialist_a.pk),
            "target_date": "2026-05-01",
            "status": IndividualPlanGoal.Status.IN_PROGRESS,
            "progress_notes": "Synthetic progress notes",
        },
    )

    assert response.status_code == 302
    assert response.url == reverse("plan_detail", kwargs={"pk": plan.pk})
    assert plan.goals.filter(pk=existing_goal.pk, goal=existing_goal.goal).exists()
    assert plan.goals.filter(goal="Second synthetic goal").exists()
    assert plan.goals.count() == 2
    assert AuditEvent.objects.filter(
        event_type=AuditEvent.EventType.CREATE,
        target_type="IndividualPlanGoal",
        target_id=plan.goals.get(goal="Second synthetic goal").pk,
        actor=coordinator_a,
    ).exists()

    response = client.get(response.url)
    body = response.content.decode()
    assert existing_goal.goal in body
    assert "Second synthetic goal" in body
    assert url in body


def test_goal_create_rejects_plan_outside_active_center(
    client, manager, center_b, specialist_a, beneficiary_a
):
    plan = make_plan(beneficiary_a, specialist_a)
    client.force_login(manager)
    set_active_center(client, center_b)

    response = client.post(
        reverse("plan_goal_create", kwargs={"plan_pk": plan.pk}),
        {
            "goal": "Unauthorized synthetic goal",
            "status": IndividualPlanGoal.Status.PLANNED,
        },
    )

    assert response.status_code == 404
    assert not plan.goals.filter(goal="Unauthorized synthetic goal").exists()


def test_goal_can_be_updated_directly_without_changing_other_goals(
    client, coordinator_a, center_a, specialist_a, beneficiary_a
):
    plan = make_plan(beneficiary_a, specialist_a)
    goal = plan.goals.get()
    other_goal = IndividualPlanGoal.objects.create(
        plan=plan,
        category=GoalCategory.objects.get(code="LEGACY-UNCLASSIFIED"),
        goal="Other synthetic goal",
        baseline="Other synthetic baseline",
        measurable_target="Other synthetic target",
        responsible_specialist=specialist_a,
        target_date=date(2026, 5, 20),
        status=IndividualPlanGoal.Status.PLANNED,
    )
    client.force_login(coordinator_a)
    set_active_center(client, center_a)
    url = reverse("plan_goal_update", kwargs={"plan_pk": plan.pk, "pk": goal.pk})

    response = client.get(reverse("plan_detail", kwargs={"pk": plan.pk}))
    assert response.status_code == 200
    assert url in response.content.decode()

    response = client.get(url)
    assert response.status_code == 200
    assert goal.goal in response.content.decode()
    response = client.post(
        url,
        {
            "goal": "Updated synthetic goal",
            "category": str(goal.category_id),
            "baseline": "Updated synthetic baseline",
            "measurable_target": "Updated measurable target",
            "measurement_type": IndividualPlanGoal.MeasurementType.NARRATIVE,
            "responsible_specialist": str(specialist_a.pk),
            "target_date": "2026-05-15",
            "status": IndividualPlanGoal.Status.ACHIEVED,
            "achieved_date": "2026-04-20",
            "evidence": "Synthetic outcome evidence",
            "progress_notes": "Updated synthetic progress notes",
        },
    )

    assert response.status_code == 302
    assert response.url == reverse("plan_detail", kwargs={"pk": plan.pk})
    goal.refresh_from_db()
    other_goal.refresh_from_db()
    assert goal.goal == "Updated synthetic goal"
    assert goal.status == IndividualPlanGoal.Status.ACHIEVED
    assert goal.progress_notes == "Updated synthetic progress notes"
    assert other_goal.goal == "Other synthetic goal"
    assert plan.goals.count() == 2
    assert AuditEvent.objects.filter(
        event_type=AuditEvent.EventType.UPDATE,
        target_type="IndividualPlanGoal",
        target_id=goal.pk,
        actor=coordinator_a,
    ).exists()


def test_goal_update_rejects_goal_from_another_plan(
    client, coordinator_a, center_a, specialist_a, beneficiary_a
):
    plan = make_plan(beneficiary_a, specialist_a)
    another_plan = make_plan(
        beneficiary_a,
        specialist_a,
        status=IndividualPlan.Status.DRAFT,
    )
    another_goal = another_plan.goals.get()
    original_text = another_goal.goal
    client.force_login(coordinator_a)
    set_active_center(client, center_a)

    response = client.post(
        reverse(
            "plan_goal_update",
            kwargs={"plan_pk": plan.pk, "pk": another_goal.pk},
        ),
        {
            "goal": "Mismatched synthetic goal",
            "status": IndividualPlanGoal.Status.ACHIEVED,
        },
    )

    assert response.status_code == 404
    another_goal.refresh_from_db()
    assert another_goal.goal == original_text


def test_assessment_requires_valid_template_response_in_form_workflow(
    client, coordinator_a, center_a, specialist_a, beneficiary_a
):
    template = make_assessment_template()
    template_field = template.fields.get(code="SYNTHETIC_SCORE")
    enrollment = beneficiary_a.enrollments.get(service__code="LEGACY-OTHER")
    client.force_login(coordinator_a)
    set_active_center(client, center_a)
    response = client.post(
        reverse("assessment_create"),
        {
            "enrollment": str(enrollment.pk),
            "specialist": str(specialist_a.pk),
            "assessment_date": "2026-01-15",
            "assessment_type": Assessment.AssessmentType.INITIAL,
            "template_version": str(template.pk),
            "service_schedule_count": "0",
            "responses-TOTAL_FORMS": "1",
            "responses-INITIAL_FORMS": "0",
            "responses-MIN_NUM_FORMS": "0",
            "responses-MAX_NUM_FORMS": "1000",
            "responses-0-template_field": str(template_field.pk),
            "responses-0-state": "assessed",
            "responses-0-value": "",
            "responses-0-notes": "",
        },
    )
    assert response.status_code == 200
    assert "A numeric response is required" in response.content.decode()
    assert Assessment.objects.count() == 0


def test_assessment_form_calculates_total_from_structured_response(
    client, coordinator_a, center_a, specialist_a, beneficiary_a
):
    template = make_assessment_template()
    template_field = template.fields.get(code="SYNTHETIC_SCORE")
    enrollment = beneficiary_a.enrollments.get(service__code="LEGACY-OTHER")
    client.force_login(coordinator_a)
    set_active_center(client, center_a)
    response = client.post(
        reverse("assessment_create"),
        {
            "enrollment": str(enrollment.pk),
            "specialist": str(specialist_a.pk),
            "responsible_specialists": [str(specialist_a.pk)],
            "assessment_date": "2026-01-15",
            "assessment_type": Assessment.AssessmentType.INITIAL,
            "template_version": str(template.pk),
            "service_schedule_count": "0",
            "progress_summary": "Synthetic progress",
            "recommendations": "Synthetic recommendation",
            "notes": "Synthetic note",
            "responses-TOTAL_FORMS": "1",
            "responses-INITIAL_FORMS": "0",
            "responses-MIN_NUM_FORMS": "0",
            "responses-MAX_NUM_FORMS": "1000",
            "responses-0-template_field": str(template_field.pk),
            "responses-0-state": "assessed",
            "responses-0-value": "8",
            "responses-0-notes": "Synthetic response note",
        },
    )
    assert response.status_code == 302
    assessment = Assessment.objects.get()
    assert assessment.status == Assessment.Status.COMPLETED
    assert assessment.total_score == 8
    assert assessment.responses.get().numeric_value == 8
    assert list(assessment.responsible_specialists.all()) == [specialist_a]


def test_center_selector_rejects_unassigned_center(client, coordinator_a, center_a, center_b):
    client.force_login(coordinator_a)
    set_active_center(client, center_a)
    response = client.post(reverse("center_select"), {"center": str(center_b.pk)})
    assert response.status_code == 404


def test_visit_list_query_count_does_not_grow_per_row(
    client, specialist_a, center_a, beneficiary_a
):
    user = specialist_a.staff_profile.user
    make_visit(beneficiary_a, specialist_a, visit_date=date(2026, 1, 1))
    client.force_login(user)
    set_active_center(client, center_a)
    with CaptureQueriesContext(connection) as baseline:
        response = client.get(reverse("visit_list"))
        assert response.status_code == 200

    for day in range(2, 12):
        beneficiary = make_beneficiary(center_a, specialist_a, name=f"Synthetic Beneficiary {day}")
        make_visit(beneficiary, specialist_a, visit_date=date(2026, 1, day))
    with CaptureQueriesContext(connection) as expanded:
        response = client.get(reverse("visit_list"))
        assert response.status_code == 200
    assert len(expanded) <= len(baseline) + 2


def test_visit_and_summary_write_roll_back_together(
    client, monkeypatch, coordinator_a, center_a, specialist_a, beneficiary_a
):
    def fail_summary(*args, **kwargs):
        raise RuntimeError("synthetic summary failure")

    monkeypatch.setattr("apps.casework.signals.rebuild_monthly_summary", fail_summary)
    client.force_login(coordinator_a)
    set_active_center(client, center_a)
    client.raise_request_exception = False

    response = client.post(
        reverse("visit_create"),
        {
            "beneficiary": str(beneficiary_a.pk),
            "specialist": str(specialist_a.pk),
            "visit_date": "2026-08-01",
            "visit_type": ServiceVisit.VisitType.CENTER,
            "status": ServiceVisit.Status.COMPLETED,
            "service_units": "1",
            "duration_minutes": "30",
        },
    )

    assert response.status_code == 500
    assert not ServiceVisit.objects.filter(visit_date=date(2026, 8, 1)).exists()
