from datetime import date

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.audit.models import AuditEvent
from apps.casework.models import Assessment, IndividualPlan, ServiceVisit

from .factories import make_beneficiary, make_visit, set_active_center

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
            "goals-TOTAL_FORMS": "3",
            "goals-INITIAL_FORMS": "0",
            "goals-MIN_NUM_FORMS": "0",
            "goals-MAX_NUM_FORMS": "1000",
            "goals-0-status": "planned",
            "goals-1-status": "planned",
            "goals-2-status": "planned",
        },
    )
    assert response.status_code == 200
    assert "At least one goal is required" in response.content.decode()
    assert IndividualPlan.objects.count() == 0


def test_assessment_requires_domain_score_in_form_workflow(
    client, coordinator_a, center_a, specialist_a, beneficiary_a
):
    client.force_login(coordinator_a)
    set_active_center(client, center_a)
    response = client.post(
        reverse("assessment_create"),
        {
            "beneficiary": str(beneficiary_a.pk),
            "specialist": str(specialist_a.pk),
            "assessment_date": "2026-01-15",
            "assessment_type": Assessment.AssessmentType.INITIAL,
            "scoring_tool": Assessment.ScoringTool.OTHER,
            "total_score": "1",
            "service_schedule_count": "0",
            "domains-TOTAL_FORMS": "3",
            "domains-INITIAL_FORMS": "0",
            "domains-MIN_NUM_FORMS": "0",
            "domains-MAX_NUM_FORMS": "1000",
        },
    )
    assert response.status_code == 200
    assert "At least one domain score is required" in response.content.decode()
    assert Assessment.objects.count() == 0


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
